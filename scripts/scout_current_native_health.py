"""One-shot, read-only native HP candidate scout in an identity-pinned RIFT VM.

Values are independently observed references, not qualified native fields. Uses
existing Windows guest access and the running RiftReader2.Live binary; never
sends game input, modifies process memory, or reloads an addon.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.vmware_guest_session import POWERSHELL, SessionError

BUILD = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"

GUEST = r'''
param([int]$GamePid,[long]$Ticks,[int]$ReaderPid,[int]$Health,
      [string]$Build,[string]$StartAddress,[string]$Out)
$ErrorActionPreference='Stop'
$g=Get-Process -Id $GamePid -ErrorAction Stop
if($g.ProcessName -ne 'rift_x64' -or [long]$g.StartTime.ToUniversalTime().Ticks -ne $Ticks){
    throw 'game-identity-mismatch'
}
if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -ne $Build){
    throw 'game-build-mismatch'
}
$r=Get-Process -Id $ReaderPid -ErrorAction Stop
if($r.ProcessName -ne 'RiftReader2.Live' -or !(Test-Path -LiteralPath $r.Path)){
    throw 'native-reader-unavailable'
}
if(Test-Path -LiteralPath $Out){throw 'output-already-exists'}
[void][IO.Directory]::CreateDirectory($Out)
$req=Join-Path $Out 'request.json'
$scan=Join-Path $Out 'scan'
$p=@{schemaVersion=1;evidenceKind='native-value-scout-request/1';
    target=@{processId=$GamePid;processStartUtcTicks=$Ticks;executableSha256=$Build};
    startAddress=$StartAddress;contextBeforeBytes=32;contextAfterBytes=64;
    maxScanBytes=1073741824;maxDurationMilliseconds=25000;
    maxRegionCount=32768;maxMatchCount=128;
    references=@(
      @{name='hp-i32';type='int32';value=[string]$Health},
      @{name='hp-f32';type='float32';value=[string]$Health},
      @{name='hp-f64';type='float64';value=[string]$Health}
    )}
$utf8=New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($req,($p|ConvertTo-Json -Depth 8),$utf8)
& $r.Path scout-values-native --request $req --output $scan | Out-Null
$exitCode=$LASTEXITCODE
$index=Join-Path $scan 'index.json'
if(!(Test-Path -LiteralPath $index)){throw ('scout-no-index-'+$exitCode)}
$summary=Get-Content -LiteralPath $index -Raw | ConvertFrom-Json
$zip=$Out+'.zip'
Compress-Archive -Path (Join-Path $scan '*'),$req -DestinationPath $zip
$receipt=@{schemaVersion=1;gamePid=$GamePid;gameStartTicks=$Ticks;
    executableSha256=$Build;readerPid=$ReaderPid;healthReference=$Health;
    scoutExitCode=$exitCode;scoutStatus=[string]$summary.status;
    scoutReason=[string]$summary.reason;archiveSha256=(Get-FileHash -LiteralPath $zip).Hash}
[IO.File]::WriteAllText(($Out+'.receipt.json'),($receipt|ConvertTo-Json),$utf8)
'''


def run(lab: str, pid: int, ticks: int, reader: int, health: int,
        start_address: str = "0xDC91D1A000") -> dict:
    if lab not in ("lab1", "lab2") or min(pid, ticks, reader, health) <= 0:
        raise ValueError("invalid-arguments")
    if (not re.fullmatch(r"0x[0-9A-F]{1,12}", start_address) or
            int(start_address, 16) < 0x10000 or start_address != f"0x{int(start_address, 16):X}"):
        raise ValueError("invalid-start-address")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    native = api._native(config, settings, api.run_root / ".doctor")
    vm_identity = api.collect_identity(native)
    identifier = uuid.uuid4().hex
    folder = ROOT / "artifacts/native-current-health" / lab / identifier
    folder.mkdir(parents=True, exist_ok=False)
    guest_prefix = settings["guestRoot"] + "\\native-hp-" + identifier
    guest_script = guest_prefix + ".ps1"
    guest_out = guest_prefix + "-evidence"
    with tempfile.TemporaryDirectory() as temporary:
        local_script = Path(temporary) / "scout.ps1"
        local_script.write_text(GUEST, encoding="utf-8")
        digest = hashlib.sha256(local_script.read_bytes()).hexdigest().upper()
        with api._session(config, settings, vm_identity, folder) as guest:
            guest.run("copyFileFromHostToGuest", str(local_script), guest_script)
            try:
                guest.powershell("if((Get-FileHash -LiteralPath '" + guest_script +
                                 "').Hash -ne '" + digest +
                                 "'){throw 'staged-source-hash-mismatch'}")
                guest.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                          "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                          guest_script, "-GamePid", str(pid), "-Ticks", str(ticks),
                          "-ReaderPid", str(reader), "-Health", str(health),
                          "-Build", BUILD, "-StartAddress", start_address,
                          "-Out", guest_out, timeout=100)
                guest.copy_from_guest(guest_out + ".receipt.json", folder / "receipt.json")
                guest.copy_from_guest(guest_out + ".zip", folder / "scout.zip", timeout=100)
            finally:
                try:
                    guest.powershell("Remove-Item -LiteralPath '" + guest_script +
                                     "' -Force -ErrorAction SilentlyContinue")
                except SessionError:
                    pass
    receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8-sig"))
    if (receipt.get("gamePid"), receipt.get("gameStartTicks"),
            receipt.get("executableSha256"), receipt.get("healthReference")) != (pid, ticks, BUILD, health):
        raise ValueError("guest-receipt-identity-mismatch")
    saved = folder / "scout.zip"
    if hashlib.sha256(saved.read_bytes()).hexdigest().upper() != receipt["archiveSha256"]:
        raise ValueError("guest-evidence-hash-mismatch")
    with zipfile.ZipFile(saved) as archive:
        indexes = [n for n in archive.namelist() if n == "index.json"]
        if len(indexes) != 1:
            raise ValueError("index-missing-or-duplicate")
        index = json.loads(archive.read(indexes[0]))
    if index.get("evidenceKind") != "native-value-scout/1":
        raise ValueError("unrecognized-evidence")
    result = {
        "lab": lab, "gamePid": pid, "gameStartTicks": ticks, "gameSha256": BUILD,
        "healthSeed": health, "startAddress": start_address,
        "status": index.get("status"),
        "reason": index.get("reason"), "examinedBytes": index.get("examinedBytes"),
        "matchCount": len(index.get("candidates", [])),
        "nextAddress": index.get("nextAddress"), "archiveSha256": receipt["archiveSha256"],
        "qualification": "candidate-only; independent changing-state proof required",
        "artifactDirectory": str(folder),
    }
    (folder / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    p.add_argument("--game-pid", type=int, required=True)
    p.add_argument("--game-start-ticks", type=int, required=True)
    p.add_argument("--reader-pid", type=int, required=True)
    p.add_argument("--health", type=int, required=True)
    p.add_argument("--start-address", default="0xDC91D1A000")
    a = p.parse_args()
    print(json.dumps(run(a.lab, a.game_pid, a.game_start_ticks,
                         a.reader_pid, a.health, a.start_address), indent=2))


if __name__ == "__main__":
    main()
