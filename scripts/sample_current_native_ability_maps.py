"""Collect current-build raw candidate ability maps without game input."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
READER_SHA = "BF3EFA6508E4AFDE2C0201BF7B193EE5AE7955E5BE6C5A386B9B625BD33979C7"
READER = ROOT / "artifacts/native-map-command-20261107/publish/RiftReader2.Live.exe"
EVIDENCE = ROOT / "artifacts/native-map-command-20261107/runs"
QUALIFICATION = "candidate-only; learned-ability, API-cooldown, freshness and restart semantics unverified"

def validate_report(report: dict, *, pid: int, ticks: int) -> dict:
    def integer(x, low=0, high=2**64-1):
        return type(x) is int and low <= x <= high
    def real(x):
        return type(x) in (int, float) and math.isfinite(x)
    def invalid():
        raise ValueError("native-ability-map-report-invalid")
    if (not isinstance(report, dict) or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1
        or report.get("contractVersion") != "native-current-ability-maps-candidate-sample/1"
        or report.get("status") != "complete" or report.get("qualification") != QUALIFICATION): invalid()
    o = report.get("observation")
    if not isinstance(o, dict) or o.get("qualification") != QUALIFICATION: invalid()
    identity = o.get("identity")
    if (not isinstance(identity, dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1)
        or type(identity.get("processId")) is not int or identity["processId"] != pid
        or type(identity.get("processStartUtcTicks")) is not int or identity["processStartUtcTicks"] != ticks
        or identity.get("executableSha256") != GAME_SHA): invalid()
    try:
        start = datetime.fromisoformat(o["startedAtUtc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(o["completedAtUtc"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds() != 0 or end.utcoffset().total_seconds() != 0 or end < start: invalid()
    if any(not integer(o.get(k),1) for k in ("nativeUnitKey", "context", "clockPointer")): invalid()
    before, after = o.get("clockBefore"), o.get("clockAfter")
    if not real(before) or not real(after) or after < before: invalid()
    maps = o.get("maps")
    if not isinstance(maps,list) or len(maps) != 2: invalid()
    total = 0
    for m, offset, stride in zip(maps,(0x1c0,0x240),(0x28,0x18)):
        if not isinstance(m,dict) or any(not integer(m.get(k)) for k in ("offset","bucketBase","stride","bucketCount","entryCount")): invalid()
        count, buckets, base = m["entryCount"], m["bucketCount"], m["bucketBase"]
        if m["offset"] != offset or m["stride"] != stride or buckets > 4096 or count > 512 or (not buckets and (count or base)) or (buckets and not base): invalid()
        entries = m.get("entries")
        if not isinstance(entries,list) or len(entries) != count: invalid()
        total += count
        for e in entries:
            if not isinstance(e,dict) or not integer(e.get("address"),1) or not integer(e.get("key"),0,2**32-1): invalid()
            raw, vhex, shex = e.get("rawHex"),e.get("valueRawHex"),e.get("secondaryRawHex")
            if not all(isinstance(x,str) and re.fullmatch(r"[0-9a-fA-F]+",x) for x in (raw,vhex,shex)) or len(raw)!=48 or len(vhex)!=8 or len(shex)!=8 or raw[32:40].lower()!=vhex.lower() or raw[40:48].lower()!=shex.lower(): invalid()
            if int.from_bytes(bytes.fromhex(raw[16:24]),"little") != e["key"]: invalid()
            for key, hx in (("value",vhex),("secondary",shex)):
                scalar=struct.unpack("<f",bytes.fromhex(hx))[0]; value=e.get(key)
                if (math.isfinite(scalar) and (not real(value) or abs(value) > 3.4028234663852886e38 or struct.pack("<f", value) != bytes.fromhex(hx))) or (not math.isfinite(scalar) and value is not None): invalid()
    if total > 512: invalid()
    return {"entryCount": total, "mapCount": len(maps), "clockBefore": before, "clockAfter": after, "acquisitionDurationMilliseconds": (end-start).total_seconds()*1000, "qualification": QUALIFICATION}

def run(lab: str) -> dict:
    if lab not in ("lab1", "lab2"):
        raise ValueError("invalid-lab")
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117307232 or digest(READER) != READER_SHA:
        raise ValueError("published-native-reader-sha-or-path-mismatch")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\current-ability-maps-" + READER_SHA[:16]
    guest_exe = guest_root + r"\RiftReader2.Live.exe"
    guest_report = guest_root + r"\sample-" + token + ".json"
    guest_probe = guest_root + r"\identity-" + token + ".json"

    with api._session(config, settings, vm, output) as guest:
        preflight = (
            "$ErrorActionPreference='Stop';"
            "$folder=" + ps_literal(guest_root) + ";"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;"
            "if($sha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$exe=" + ps_literal(guest_exe) + ";"
            "$installed=Test-Path -LiteralPath $exe -PathType Leaf;"
            "if($installed -and (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
            + ps_literal(READER_SHA) + "){throw 'guest-reader-hash-collision'};"
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;"
            "sha=$sha;installed=[bool]$installed};"
            "$probe=" + ps_literal(guest_probe) + ";"
            "$bytes=[Text.Encoding]::UTF8.GetBytes(($data|ConvertTo-Json -Compress));"
            "$f=[IO.File]::Open($probe,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);"
            "try{$f.Write($bytes,0,$bytes.Length)}finally{$f.Dispose()}"
        )
        guest.powershell(preflight, timeout=80)
        guest.copy_from_guest(guest_probe, output / "identity.json", timeout=50)
        identity = json.loads((output / "identity.json").read_text(encoding="utf-8-sig"))
        pid, ticks = identity["pid"], identity["ticks"]
        if (type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0
                or identity.get("sha") != GAME_SHA or type(identity.get("installed")) is not bool):
            raise ValueError("guest-native-sampler-identity-invalid")
        installed = identity["installed"]
        if not installed:
            guest.run("copyFileFromHostToGuest", str(READER), guest_exe, timeout=180)
        launch = (
            "$ErrorActionPreference='Stop';"
            "$exe=" + ps_literal(guest_exe) + ";"
            "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
            + ps_literal(READER_SHA) + "){throw 'guest-reader-sha-mismatch'};"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if($g.ProcessName -cne 'rift_x64' -or "
            "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
            + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
            "$out=" + ps_literal(guest_report) + ";"
            "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
            "& $exe sample-current-ability-maps --pid " + str(pid) + " --start-ticks " + str(ticks)
            + " --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
            "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};"
            "if((Get-Item -LiteralPath $out).Length -gt 1000000){throw 'native-report-too-large'}"
        )
        guest.powershell(launch, timeout=130)
        guest.copy_from_guest(guest_report, output / "samples.json", timeout=70)
    with (output / "samples.json").open("rb") as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("native-report-too-large")
    parsed = json.loads(raw.decode("utf-8-sig"))
    metrics = validate_report(parsed, pid=pid, ticks=ticks)
    summary = {
        "schemaVersion": 1,
        "status": "candidate-only",
        "lab": lab,
        "vmIdentity": vm,
        "gameProcessId": pid,
        "gameProcessStartUtcTicks": ticks,
        "gameSha256": GAME_SHA,
        "readerExecutableSha256": READER_SHA,
        "guestReaderReused": installed,
        "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceReport": str(output / "samples.json"),
        "metrics": metrics,
        "limitation": "Raw candidate maps only; learned ability, API cooldown, freshness and restart semantics remain unverified."
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.lab)), flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:160]}), flush=True)
        raise SystemExit(2) from None

if __name__ == "__main__":
    main()
