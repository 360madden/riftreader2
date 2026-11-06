"""Plan bounded read-only native image scopes from the exact RIFT process PE.

This reads PE section *headers*, not process bytes; no scanner is started.
A resulting writable section remains only a candidate memory-search scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.vmware_guest_session import POWERSHELL, SessionError


GUEST = r'''
$ErrorActionPreference='Stop'
$game=Get-Process -Id $ExpectedPid -ErrorAction Stop
if($game.ProcessName -ne 'rift_x64' -or !(Test-Path -LiteralPath $game.Path -PathType Leaf)){
    throw 'rift-game-not-found'
}
$ticks=[string]$game.StartTime.ToUniversalTime().Ticks
$sha=(Get-FileHash -LiteralPath $game.Path -Algorithm SHA256).Hash
if($ticks -ne $ExpectedTicks -or $sha -ne $ExpectedSha){throw 'game-identity-mismatch'}
if(Test-Path -LiteralPath $OutputPath){throw 'output-already-exists'}
$base=[uint64]$game.MainModule.BaseAddress.ToInt64()
$moduleSize=[uint64]$game.MainModule.ModuleMemorySize
$file=[IO.File]::Open($game.Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
$reader=New-Object IO.BinaryReader($file)
try {
    if($reader.ReadUInt16() -ne 0x5A4D){throw 'pe-dos-signature-invalid'}
    $file.Position=0x3C
    $peOffset=$reader.ReadInt32()
    if($peOffset -lt 64 -or $peOffset -gt 4194304 -or $peOffset+24 -ge $file.Length){
        throw 'pe-header-offset-invalid'
    }
    $file.Position=$peOffset
    if($reader.ReadUInt32() -ne 0x00004550){throw 'pe-signature-invalid'}
    $machine=$reader.ReadUInt16()
    if($machine -ne 0x8664){throw 'pe-not-amd64'}
    $count=$reader.ReadUInt16()
    if($count -lt 1 -or $count -gt 96){throw 'pe-section-count-out-of-bounds'}
    $file.Position=$peOffset+20
    $optionalHeaderBytes=$reader.ReadUInt16()
    if($optionalHeaderBytes -lt 112 -or $optionalHeaderBytes -gt 4096){
        throw 'pe-optional-header-size-invalid'
    }
    $sectionStart=[long]$peOffset+24+[long]$optionalHeaderBytes
    $sections=@(for($i=0;$i -lt $count;$i++){
        $position=$sectionStart+[long]$i*40
        if($position+40 -gt $file.Length){throw 'pe-section-table-truncated'}
        $file.Position=$position
        $name=[Text.Encoding]::ASCII.GetString($reader.ReadBytes(8)).TrimEnd([char]0)
        $virtualSize=[uint64]$reader.ReadUInt32()
        $rva=[uint64]$reader.ReadUInt32()
        $rawSize=[uint64]$reader.ReadUInt32()
        $file.Position=$position+36
        $flags=[uint64]$reader.ReadUInt32()
        if($rva -gt $moduleSize -or $virtualSize -gt $moduleSize - $rva){
            throw 'pe-section-outside-running-module'
        }
        [pscustomobject]@{
            name=$name;rva=('0x{0:X}' -f $rva)
            virtualBytes=[long]$virtualSize;rawBytes=[long]$rawSize
            characteristics=('0x{0:X8}' -f $flags)
            writable=(($flags -band 0x80000000) -ne 0)
            runtimeStart=('0x{0:X}' -f ($base+$rva))
        }
    })
} finally {
    $reader.Dispose()
    $file.Dispose()
}
$writable=@($sections|Where-Object {$_.writable -and $_.virtualBytes -gt 0})
$report=@{
    schemaVersion=1;evidenceKind='rift-image-scope-plan/1'
    acquiredUtc=[DateTime]::UtcNow.ToString('o')
    computer=$env:COMPUTERNAME
    game=@{processId=$game.Id;processStartUtcTicks=[long]$ticks;executableSha256=$sha
           executablePath=$game.Path;moduleBase=('0x{0:X}' -f $base)
           moduleSize=[long]$moduleSize}
    peMachine='0x8664'
    sections=$sections
    writableSections=$writable
    writableVirtualBytes=[long](($writable|Measure-Object -Property virtualBytes -Sum).Sum)
    limitation='PE header planning only. No game memory was read or written; runtime section protections remain unverified.'
}
$report|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $OutputPath -Encoding UTF8
'''


def run(lab: str, game_pid: int, start_ticks: int, game_sha: str) -> dict:
    if lab not in ("lab1", "lab2") or game_pid <= 0 or start_ticks <= 0:
        raise ValueError("invalid-lab-or-game-identity")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", game_sha):
        raise ValueError("invalid-game-sha")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    native = api._native(config, settings, api.run_root / ".doctor")
    identity = api.collect_identity(native)
    folder = ROOT / "artifacts" / "native-module-scopes" / lab / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    guest_prefix = settings["guestRoot"] + "\\pe-scope-" + uuid.uuid4().hex
    guest_script = guest_prefix + ".ps1"
    guest_output = guest_prefix + ".json"
    source = "\n".join([
        "$ExpectedPid=" + str(game_pid),
        "$ExpectedTicks=" + ps_literal(str(start_ticks)),
        "$ExpectedSha=" + ps_literal(game_sha.upper()),
        "$OutputPath=" + ps_literal(guest_output),
        "try {", GUEST, "} catch {",
        "$failure=@{status='error';category=$_.Exception.GetType().Name;" +
        "reason=$_.Exception.Message}",
        "$failure|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $OutputPath -Encoding UTF8",
        "}",
    ])
    with tempfile.TemporaryDirectory() as temporary:
        local_script = Path(temporary) / "inspect.ps1"
        local_script.write_text(source, encoding="utf-8")
        script_sha = hashlib.sha256(local_script.read_bytes()).hexdigest().upper()
        with api._session(config, settings, identity, folder) as guest:
            guest.run("copyFileFromHostToGuest", str(local_script), guest_script)
            try:
                guest.powershell(
                    "if((Get-FileHash -LiteralPath " + ps_literal(guest_script) +
                    ").Hash -ne " + ps_literal(script_sha) +
                    "){throw 'pe-scope-script-sha-mismatch'}", timeout=30)
                guest.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                          "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-File", guest_script, timeout=45)
                guest.copy_from_guest(guest_output, folder / "scope-plan.json")
            finally:
                try:
                    guest.powershell("Remove-Item -LiteralPath " + ps_literal(guest_script) +
                                     " -Force -ErrorAction SilentlyContinue", timeout=30)
                except SessionError:
                    pass
    result = json.loads((folder / "scope-plan.json").read_text(encoding="utf-8-sig"))
    if result.get("status") == "error":
        raise ValueError("pe-scope-guest-rejected:" +
                         str(result.get("category")) + ":" + str(result.get("reason"))[:500])
    game = result["game"]
    if (result["schemaVersion"] != 1 or result["evidenceKind"] != "rift-image-scope-plan/1" or
            game["processId"] != game_pid or game["processStartUtcTicks"] != start_ticks or
            game["executableSha256"].upper() != game_sha.upper()):
        raise ValueError("pe-scope-plan-identity-mismatch")
    if any(not section["writable"] for section in result["writableSections"]):
        raise ValueError("pe-scope-plan-writable-selection-invalid")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    p.add_argument("--game-pid", type=int, required=True)
    p.add_argument("--game-start-ticks", type=int, required=True)
    p.add_argument("--game-sha", required=True)
    a = p.parse_args()
    report = run(a.lab, a.game_pid, a.game_start_ticks, a.game_sha)
    print(json.dumps({
        "lab": a.lab, "game": report["game"], "peMachine": report["peMachine"],
        "writableSections": report["writableSections"],
        "writableVirtualBytes": report["writableVirtualBytes"],
        "limitation": report["limitation"],
    }, indent=2))


if __name__ == "__main__":
    main()

