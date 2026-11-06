"""Capture two bounded current-build RR2R1 reference runs from one lab.

The operation uses LabCodex's VM-specific cached-credential preflight, stages an
explicitly SHA-pinned reader, performs two read-only scans eight seconds apart,
and returns one SHA-pinned archive. It sends no game input and does not reload an
addon, restart RIFT, or interpret the typed source as native field semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.inspect_typed_resource import require_session_id
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_vitals import checked_sha, staged_script
from scripts.sample_current_native_xyz import GAME_SHA, digest
from scripts.verify_typed_inline_archive import verify_and_publish

EVIDENCE = ROOT / "artifacts/native-current-reference/runs"
IDENTITY_LIMIT = 8192
ARCHIVE_LIMIT = 16 * 1024 * 1024


def bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if not value or len(value) > limit:
        raise ValueError("returned-evidence-size-invalid")
    return value


def require_reference_reader(reader: Path) -> None:
    # The reviewed SHA pins the artifact; the literal check prevents accidentally
    # selecting a historical binary whose default scout silently targets RRAPIVAL2.
    if digest(reader) == "362ECD5A1BE3F10BD3AE9E78B66FA0B56D390E5DD7234B4B5997649926B83A53":
        raise ValueError("legacy-deployed-reader-unsupported")
    raw = reader.read_bytes()
    if b"RR2R1|" not in raw and "RR2R1|".encode("utf-16-le") not in raw:
        raise ValueError("reader-does-not-contain-rr2-reference-marker")


def capture(lab: str, reader: Path, reader_sha256: str, session_id: str) -> dict:
    require_session_id(session_id)
    reader = reader.absolute()
    reader_sha256 = checked_sha(reader_sha256)
    if (lab not in ("lab1", "lab2") or not reader.is_file() or reader.is_symlink()
            or reader.name != "RiftReader2.Live.exe" or digest(reader) != reader_sha256):
        raise ValueError("lab-or-reader-identity-invalid")

    require_reference_reader(reader)
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\typed-reference-" + token
    guest_reader = guest_root + r"\RiftReader2.Live.exe"
    guest_identity = guest_root + r"\identity.json"
    guest_request = guest_root + r"\request.json"
    guest_archive = guest_root + r"\two-runs.zip"
    guest_archive_sha = guest_archive + ".sha256"

    with api._session(config, settings, vm, output) as guest:
        preflight = (
            "$ErrorActionPreference='Stop';$folder=" + ps_literal(guest_root) + ";"
            "if(Test-Path -LiteralPath $folder){throw 'guest-staging-exists'};"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$games=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($games.Count -ne 1){throw 'exactly-one-game-required'};$g=$games[0];"
            "$sha=(Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash;"
            "if($sha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$data=[ordered]@{pid=[int]$g.Id;ticks=[long]$g.StartTime.ToUniversalTime().Ticks;sha=$sha};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_identity)
            + ",($data|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))"
        )
        staged_script(guest, preflight, output / "preflight.ps1",
                      settings["guestRoot"] + "\\typed-ref-preflight-" + token + ".ps1",
                      timeout=80)
        guest.copy_from_guest(guest_identity, output / "identity.json", timeout=50)
        identity = json.loads(bounded(output / "identity.json", IDENTITY_LIMIT).decode("utf-8-sig"))
        pid, ticks = identity.get("pid"), identity.get("ticks")
        if (type(pid) is not int or pid < 1 or type(ticks) is not int or ticks < 1
                or identity.get("sha") != GAME_SHA):
            raise ValueError("fresh-game-identity-invalid")

        request = {
            "schemaVersion": 1,
            "evidenceKind": "native-typed-inline-capture-request/1",
            "target": {"processId": pid, "processStartUtcTicks": ticks,
                       "executableSha256": GAME_SHA},
            "startAddress": "0x10000",
            "maxScanBytes": 536870912,
            "maxDurationMilliseconds": 30000,
            "maxRegionCount": 32768,
            "maxMatchCount": 128,
            "maxCopiedCandidates": 8,
            "marker": "RR2R1|",
        }
        request_path = output / "request.json"
        request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8", newline="\n")
        guest.run("copyFileFromHostToGuest", str(reader), guest_reader, timeout=180)
        guest.run("copyFileFromHostToGuest", str(request_path), guest_request, timeout=50)
        run1, run2 = guest_root + r"\run-01", guest_root + r"\run-02"
        capture_script = (
            "$ErrorActionPreference='Stop';$reader=" + ps_literal(guest_reader) + ";"
            "$request=" + ps_literal(guest_request) + ";$run1=" + ps_literal(run1)
            + ";$run2=" + ps_literal(run2) + ";"
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne "
            + ps_literal(reader_sha256) + "){throw 'reader-sha-mismatch'};"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if($g.ProcessName -cne 'rift_x64' -or [long]$g.StartTime.ToUniversalTime().Ticks -ne "
            + str(ticks) + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'game-build-changed'};"
            "& $reader scout-copy-typed-native --request $request --output $run1|Out-Null;"
            "$exit1=$LASTEXITCODE;if($exit1 -notin 0,3 -or !(Test-Path (Join-Path $run1 'index.json'))){throw 'run1-failed'};"
            "Copy-Item -LiteralPath $request -Destination (Join-Path $run1 'input.request.json');"
            "Start-Sleep -Seconds 8;"
            "& $reader scout-copy-typed-native --request $request --output $run2|Out-Null;"
            "$exit2=$LASTEXITCODE;if($exit2 -notin 0,3 -or !(Test-Path (Join-Path $run2 'index.json'))){throw 'run2-failed'};"
            "Copy-Item -LiteralPath $request -Destination (Join-Path $run2 'input.request.json');"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if([long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks) + "){throw 'postflight-epoch-changed'};"
            "Compress-Archive -LiteralPath $run1,$run2 -DestinationPath " + ps_literal(guest_archive)
            + " -CompressionLevel Optimal;"
            "[IO.File]::WriteAllText(" + ps_literal(guest_archive_sha)
            + ",(Get-FileHash -LiteralPath " + ps_literal(guest_archive)
            + " -Algorithm SHA256).Hash,(New-Object Text.UTF8Encoding($false)))"
        )
        staged_script(guest, capture_script, output / "capture.ps1",
                      settings["guestRoot"] + "\\typed-ref-capture-" + token + ".ps1",
                      timeout=180)
        archive = output / "two-runs.zip"
        guest.copy_from_guest(guest_archive, archive, timeout=80)
        guest.copy_from_guest(guest_archive_sha, output / "two-runs.zip.sha256", timeout=50)

    raw = bounded(archive, ARCHIVE_LIMIT)
    archive_sha = bounded(output / "two-runs.zip.sha256", 256).decode("utf-8-sig").strip().upper()
    if hashlib.sha256(raw).hexdigest().upper() != checked_sha(archive_sha):
        raise ValueError("guest-archive-sha-mismatch")
    recovered = output / "recovered"
    proof = verify_and_publish(
        archive, archive_sha, recovered, pid=pid, ticks=ticks, game_sha=GAME_SHA,
        bundle_sha=reader_sha256, min_separation_seconds=1.0, marker="RR2R1|")
    summary = {
        "schemaVersion": 1,
        "status": "verified-originals-returned",
        "lab": lab,
        "vmIdentity": vm,
        "target": request["target"],
        "readerSha256": reader_sha256,
        "protocol": "RR2R1", "sessionId": session_id,
        "archiveSha256": archive_sha,
        "runCount": len(proof["runs"]),
        "snapshotCounts": [item["snapshotCount"] for item in proof["runs"]],
        "output": str(output),
        "gameInputSent": False,
        "reloadOrRestartUsed": False,
        "typedFrameQualified": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--reader", required=True, type=Path)
    parser.add_argument("--reader-sha256", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    try:
        result = capture(args.lab, args.reader, args.reader_sha256, args.session_id)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
