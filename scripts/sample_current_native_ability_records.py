"""Collect current-build raw candidate ability records without game input."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import math
import ntpath
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
READER_SHA = "F4148B838AF694EF95FD46DE76859CE9DF55194A9FE8BE1DF74FC2F8F0BCE80F"
READER = ROOT / "artifacts/native-ability-records-20261107/publish/RiftReader2.Live.exe"
EVIDENCE = ROOT / "artifacts/native-ability-records-20261107/runs"
QUALIFICATION = "candidate-only; membership, freshness and restart unverified"

def validate_keys(keys):
    if not isinstance(keys,list) or not 1 <= len(keys) <= 128 or any(type(k) is not int or not 0 <= k <= 0xffffffff for k in keys) or len(set(keys)) != len(keys):
        raise ValueError("invalid-ability-keys")

def validate_report(report, *, pid, ticks, keys):
    validate_keys(keys)
    def integer(x, low=0, high=2**64-1): return type(x) is int and low <= x <= high
    def invalid(): raise ValueError("native-ability-record-report-invalid")
    if (not isinstance(report,dict) or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1
        or report.get("contractVersion") != "native-current-ability-records-candidate-sample/1" or report.get("status") != "complete"): invalid()
    o = report.get("observation")
    if not isinstance(o,dict) or o.get("qualification") != QUALIFICATION: invalid()
    identity = o.get("identity")
    if (not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1)
        or type(identity.get("processId")) is not int or identity["processId"] != pid
        or type(identity.get("processStartUtcTicks")) is not int or identity["processStartUtcTicks"] != ticks
        or identity.get("executableSha256") != GAME_SHA): invalid()
    try:
        start=datetime.fromisoformat(o["startedAtUtc"].replace("Z","+00:00")); end=datetime.fromisoformat(o["completedAtUtc"].replace("Z","+00:00"))
    except (KeyError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
    if not integer(o.get("selector"),0,65535) or not integer(o.get("tlsIndex"),0,1087) or not integer(o.get("collection"),1): invalid()
    rows=o.get("records")
    if not isinstance(rows,list) or len(rows)!=len(keys): invalid()
    for row,key in zip(rows,keys):
        if not isinstance(row,dict) or not integer(row.get("key"),0,0xffffffff) or row["key"] != key: invalid()
        status=row.get("status"); address=row.get("recordAddress"); flag=row.get("apiListFilterNonzeroRaw"); child=row.get("child"); secondary=row.get("secondaryChild"); full=row.get("fullIdCandidate")
        if status in ("cache-miss","cache-null-holder","cache-null-record"):
            if any(x is not None for x in (address,flag,child,secondary,full)): invalid()
        elif status=="unverified-type":
            if not integer(address,1) or any(x is not None for x in (flag,child,secondary,full)): invalid()
        elif status=="type-verified-candidate":
            if not integer(address,1) or not integer(flag,0,255): invalid()
            for c in (child,secondary):
                if not isinstance(c,dict): invalid()
                st=c.get("status"); addr=c.get("address"); loc=c.get("localizationKey")
                if st=="null":
                    if not integer(addr) or addr != 0 or not integer(loc,0,0xffffffff) or loc != 0: invalid()
                elif st=="unverified-type":
                    if not integer(addr,1) or loc is not None: invalid()
                elif st=="type-verified-candidate":
                    if not integer(addr,1) or not integer(loc,0,0xffffffff): invalid()
                else: invalid()
            known=child["localizationKey"] is not None and secondary["localizationKey"] is not None
            if known:
                if not isinstance(full,str) or re.fullmatch(r"A[0-9A-F]{16}",full) is None or int(full[1:9],16)!=key: invalid()
            elif full is not None: invalid()
        else: invalid()
    return {"recordCount":len(rows),"acquisitionDurationMilliseconds":(end-start).total_seconds()*1000,"qualification":QUALIFICATION}

def build_launch(guest_exe, guest_keys, guest_report, pid, ticks, key_sha):
    folder = ntpath.dirname(guest_exe)
    if not folder or any(ntpath.dirname(path).lower() != folder.lower() for path in (guest_keys, guest_report)):
        raise ValueError("guest-paths-must-share-directory")
    return (
        "$ErrorActionPreference='Stop';"
        "$d=" + ps_literal(folder) + ";"
        "$exe=$d+" + ps_literal("\\" + ntpath.basename(guest_exe)) + ";"
        "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
        + ps_literal(READER_SHA) + "){throw 'guest-reader-sha-mismatch'};"
        "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
        "if($g.ProcessName -cne 'rift_x64' -or "
        "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
        + "){throw 'game-epoch-changed'};"
        "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
        + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
        "$keyfile=$d+" + ps_literal("\\" + ntpath.basename(guest_keys)) + ";"
        "if((Get-FileHash -LiteralPath $keyfile -Algorithm SHA256).Hash -cne " + ps_literal(key_sha) + "){throw 'guest-keys-sha-mismatch'};"
        "$keys=[IO.File]::ReadAllText($keyfile);"
        "$out=$d+" + ps_literal("\\" + ntpath.basename(guest_report)) + ";"
        "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
        "& $exe sample-current-ability-records --pid " + str(pid) + " --start-ticks " + str(ticks)
        + " --keys $keys --output $out | Out-Null;"
        "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
        "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};"
        "if((Get-Item -LiteralPath $out).Length -gt 1000000){throw 'native-report-too-large'}"
        )


def run(lab: str, keys: list[int]) -> dict:
    validate_keys(keys)
    if lab not in ("lab1", "lab2"):
        raise ValueError("invalid-lab")
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117327712 or digest(READER) != READER_SHA:
        raise ValueError("published-native-reader-sha-or-path-mismatch")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\current-ability-records-" + READER_SHA[:16]
    guest_exe = guest_root + r"\RiftReader2.Live.exe"
    guest_report = guest_root + r"\sample-" + token + ".json"
    guest_probe = guest_root + r"\identity-" + token + ".json"
    guest_keys = guest_root + r"\keys-" + token + ".txt"
    key_bytes = ",".join(str(key) for key in keys).encode("ascii")
    key_sha = hashlib.sha256(key_bytes).hexdigest().upper()
    key_file = output / "keys.txt"
    with key_file.open("xb") as stream:
        stream.write(key_bytes)

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
        guest.powershell("if(Test-Path -LiteralPath " + ps_literal(guest_keys) + "){throw 'guest-key-file-exists'}", timeout=30)
        guest.run("copyFileFromHostToGuest", str(key_file), guest_keys, timeout=50)
        launch = build_launch(guest_exe, guest_keys, guest_report, pid, ticks, key_sha)
        guest.powershell(launch, timeout=130)
        guest.copy_from_guest(guest_report, output / "samples.json", timeout=70)
    with (output / "samples.json").open("rb") as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("native-report-too-large")
    parsed = json.loads(raw.decode("utf-8-sig"))
    metrics = validate_report(parsed, pid=pid, ticks=ticks, keys=keys)
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
        "keysSha256": key_sha,
        "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sourceReport": str(output / "samples.json"),
        "metrics": metrics,
        "limitation": "Raw cache candidates only; membership, freshness and restart semantics remain unverified."
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab",choices=("lab1","lab2"),required=True)
    parser.add_argument("--key", action="append", required=True, type=lambda v:int(v,0))
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.lab,args.key)),flush=True)
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc)[:160]}),flush=True)
        raise SystemExit(2) from None

if __name__ == "__main__": main()
