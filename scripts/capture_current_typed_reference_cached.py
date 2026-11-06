"""Capture verified RRAPIVAL2 frames with the already deployed Lab reader.

This is an isolated short-window acquisition path.  It preserves the accepted
two-run archive contract but never uploads or replaces the 117 MB reader.  The
managed workflow and guest reader hashes are checked before and after capture.
It sends no game input and does not reload or restart RIFT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_vitals import staged_script
from scripts.sample_current_native_xyz import GAME_SHA
from scripts.verify_typed_inline_archive import verify_and_publish


EVIDENCE = ROOT / "artifacts/native-current-reference-cached/runs"
WORKFLOW = ROOT / "artifacts/control-fleet-live/lab1/workflow.json"
IDENTITY_LIMIT = 8192
ARCHIVE_LIMIT = 16 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9A-F]{64}")
EXPECTED_READER_SHA = "362ECD5A1BE3F10BD3AE9E78B66FA0B56D390E5DD7234B4B5997649926B83A53"
SOURCE_PATHS = (
    Path(__file__).resolve(),
    ROOT / "scripts/lab_codex.py",
    ROOT / "scripts/inventory_passive_rift_sources.py",
    ROOT / "scripts/sample_current_native_vitals.py",
    ROOT / "scripts/sample_current_native_xyz.py",
    ROOT / "scripts/verify_typed_inline_archive.py",
    ROOT / "scripts/vm_console_native.py",
    ROOT / "scripts/vmware_guest_session.py",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def bounded(path: Path, limit: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("returned-evidence-file-invalid")
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if not value or len(value) > limit:
        raise ValueError("returned-evidence-size-invalid")
    return value


def source_pins(paths: tuple[Path, ...] = SOURCE_PATHS) -> dict[str, str]:
    pins = {}
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError("capture-source-pin-invalid")
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("capture-source-pin-invalid")
        pins[str(resolved)] = sha(resolved.read_bytes())
    return pins


def write_new_text(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def publish_transfer(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("returned-evidence-destination-exists")
    os.rename(source, destination)  # Windows refuses an existing destination.


def artifact_receipt(paths: dict[str, Path]) -> dict[str, dict[str, object]]:
    result = {}
    for label, path in paths.items():
        raw = bounded(path, ARCHIVE_LIMIT)
        result[label] = {
            "path": str(path.resolve(strict=True)),
            "byteLength": len(raw),
            "sha256": sha(raw),
        }
    return result


def require_proof_request(proof: dict, request_sha: str) -> None:
    runs = proof.get("runs") if isinstance(proof, dict) else None
    if (not isinstance(request_sha, str) or not SHA_PATTERN.fullmatch(request_sha)
            or not isinstance(runs, list) or len(runs) != 2
            or any(not isinstance(run, dict)
                   or run.get("inputRequestSha256") != request_sha for run in runs)):
        raise ValueError("recovered-run-host-request-mismatch")


def load_identity(path: Path, *, game_sha: str, reader_sha: str) -> dict:
    try:
        value = json.loads(
            bounded(path, IDENTITY_LIMIT).decode("utf-8-sig"),
            object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("fresh-game-or-reader-identity-invalid") from exc
    expected = {"schemaVersion", "evidenceKind", "pid", "ticks", "sha", "readerSha"}
    if (not isinstance(value, dict) or set(value) != expected
            or value.get("schemaVersion") != 1
            or value.get("evidenceKind") != "cached-reader-game-identity/1"
            or type(value.get("pid")) is not int or value["pid"] < 1
            or type(value.get("ticks")) is not int or value["ticks"] < 1
            or value.get("sha") != game_sha or value.get("readerSha") != reader_sha):
        raise ValueError("fresh-game-or-reader-identity-invalid")
    return value


def load_workflow(path: Path = WORKFLOW) -> tuple[dict, str, str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("managed-workflow-required")
    raw = bounded(path, 64 * 1024)
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("managed-workflow-invalid") from exc
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ValueError("managed-workflow-invalid")
    reader_sha = value.get("readerSha256")
    guest_directory = value.get("guestDirectory")
    guest_path = PureWindowsPath(guest_directory) if isinstance(guest_directory, str) else None
    if (not isinstance(reader_sha, str) or not SHA_PATTERN.fullmatch(reader_sha)
            or reader_sha != EXPECTED_READER_SHA
            or not isinstance(guest_directory, str) or not guest_directory):
        raise ValueError("managed-reader-pin-invalid")
    if (not guest_path.is_absolute() or ".." in guest_path.parts):
        raise ValueError("managed-reader-path-invalid")
    reader = str(guest_path / "RiftReader2.Live.exe")
    return value, sha(raw), reader, reader_sha


def require_pins(pins: dict[str, str], workflow_sha: str,
                 workflow_path: Path = WORKFLOW) -> None:
    if source_pins(tuple(Path(path) for path in pins)) != pins:
        raise ValueError("cached-capture-source-changed-during-run")
    _, current_workflow_sha, _, _ = load_workflow(workflow_path)
    if current_workflow_sha != workflow_sha:
        raise ValueError("managed-workflow-changed-during-run")


def capture(lab: str = "lab1", *, session_id: str | None = None,
            reader: Path | None = None, reader_sha256: str | None = None) -> dict:
    if session_id is not None:
        from scripts.capture_current_typed_reference import capture as staged_capture
        if reader is None or reader_sha256 is None:
            raise ValueError("rr2-reference-requires-reviewed-reader-and-sha256;legacy-cached-reader-unsupported")
        return staged_capture(lab, reader, reader_sha256, session_id)
    raise ValueError("rr2-reference-session-id-required;legacy-cached-capture-disabled")


def _historical_capture(lab: str = "lab1") -> dict:
    if lab != "lab1":
        raise ValueError("cached-capture-requires-lab1-managed-reader")
    workflow_path = WORKFLOW
    pins = source_pins()
    source_path = str(Path(__file__).resolve())
    source_sha = pins[source_path]
    workflow, workflow_sha, guest_reader, reader_sha = load_workflow(workflow_path)
    require_pins(pins, workflow_sha, workflow_path)

    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / lab / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + r"\typed-reference-cached-" + token
    guest_identity = guest_root + r"\identity.json"
    guest_request = guest_root + r"\request.json"
    guest_archive = guest_root + r"\two-runs.zip"
    guest_archive_sha = guest_archive + ".sha256"

    with api._session(config, settings, vm, output) as guest:
        preflight = (
            "$ErrorActionPreference='Stop';$folder=" + ps_literal(guest_root) + ";"
            "if(Test-Path -LiteralPath $folder){throw 'guest-staging-exists'};"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$reader=" + ps_literal(guest_reader) + ";"
            "if(!(Test-Path -LiteralPath $reader -PathType Leaf)){throw 'managed-reader-missing'};"
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne "
            + ps_literal(reader_sha) + "){throw 'managed-reader-sha-mismatch'};"
            "$games=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($games.Count -ne 1){throw 'exactly-one-game-required'};$g=$games[0];"
            "$gameSha=(Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash;"
            "if($gameSha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$data=[ordered]@{schemaVersion=1;evidenceKind='cached-reader-game-identity/1';"
            "pid=[int]$g.Id;ticks=[long]$g.StartTime.ToUniversalTime().Ticks;"
            "sha=$gameSha;readerSha=" + ps_literal(reader_sha) + "};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_identity)
            + ",($data|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))"
        )
        staged_script(guest, preflight, output / "preflight.ps1",
                      settings["guestRoot"] + "\\typed-ref-cached-preflight-" + token + ".ps1",
                      timeout=80)
        identity_transfer = output / ".identity.transfer"
        identity_path = output / "identity.json"
        guest.copy_from_guest(guest_identity, identity_transfer, timeout=50)
        publish_transfer(identity_transfer, identity_path)
        identity = load_identity(identity_path, game_sha=GAME_SHA, reader_sha=reader_sha)
        pid, ticks = identity.get("pid"), identity.get("ticks")

        request = {
            "schemaVersion": 1,
            "evidenceKind": "native-typed-inline-capture-request/1",
            "target": {"processId": pid, "processStartUtcTicks": ticks,
                       "executableSha256": GAME_SHA},
            "startAddress": "0x10000", "maxScanBytes": 536870912,
            "maxDurationMilliseconds": 30000, "maxRegionCount": 32768,
            "maxMatchCount": 128, "maxCopiedCandidates": 8,
        }
        request_path = output / "request.json"
        write_new_text(request_path, json.dumps(request, indent=2) + "\n")
        request_sha = sha(bounded(request_path, IDENTITY_LIMIT))
        guest.run("copyFileFromHostToGuest", str(request_path), guest_request, timeout=50)
        run1, run2 = guest_root + r"\run-01", guest_root + r"\run-02"
        capture_script = (
            "$ErrorActionPreference='Stop';$reader=" + ps_literal(guest_reader) + ";"
            "$request=" + ps_literal(guest_request) + ";$run1=" + ps_literal(run1)
            + ";$run2=" + ps_literal(run2) + ";"
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne "
            + ps_literal(reader_sha) + "){throw 'managed-reader-sha-mismatch-before'};"
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
            "if($g.ProcessName -cne 'rift_x64' -or [long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
            + "){throw 'postflight-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
            + ps_literal(GAME_SHA) + "){throw 'postflight-game-build-changed'};"
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne "
            + ps_literal(reader_sha) + "){throw 'managed-reader-sha-mismatch-after'};"
            "Compress-Archive -LiteralPath $run1,$run2 -DestinationPath "
            + ps_literal(guest_archive) + " -CompressionLevel Optimal;"
            "[IO.File]::WriteAllText(" + ps_literal(guest_archive_sha)
            + ",(Get-FileHash -LiteralPath " + ps_literal(guest_archive)
            + " -Algorithm SHA256).Hash,(New-Object Text.UTF8Encoding($false)))"
        )
        staged_script(guest, capture_script, output / "capture.ps1",
                      settings["guestRoot"] + "\\typed-ref-cached-capture-" + token + ".ps1",
                      timeout=100)
        archive = output / "two-runs.zip"
        archive_transfer = output / ".two-runs.zip.transfer"
        archive_sha_path = output / "two-runs.zip.sha256"
        archive_sha_transfer = output / ".two-runs.zip.sha256.transfer"
        guest.copy_from_guest(guest_archive, archive_transfer, timeout=80)
        publish_transfer(archive_transfer, archive)
        guest.copy_from_guest(guest_archive_sha, archive_sha_transfer, timeout=50)
        publish_transfer(archive_sha_transfer, archive_sha_path)

    require_pins(pins, workflow_sha, workflow_path)
    raw = bounded(archive, ARCHIVE_LIMIT)
    archive_sha = bounded(archive_sha_path, 256).decode("utf-8-sig").strip().upper()
    if sha(raw) != archive_sha or not SHA_PATTERN.fullmatch(archive_sha):
        raise ValueError("guest-archive-sha-mismatch")
    recovered = output / "recovered"
    proof = verify_and_publish(
        archive, archive_sha, recovered, pid=pid, ticks=ticks, game_sha=GAME_SHA,
        bundle_sha=reader_sha, min_separation_seconds=1.0)
    require_proof_request(proof, request_sha)
    require_pins(pins, workflow_sha, workflow_path)
    proof_path = recovered / "archive-proof.json"
    artifacts = artifact_receipt({
        "managedWorkflow": workflow_path,
        "captureSource": Path(__file__),
        "guestIdentity": identity_path,
        "captureRequest": request_path,
        "preflightScript": output / "preflight.ps1",
        "captureScript": output / "capture.ps1",
        "guestArchive": archive,
        "guestArchiveSha256": archive_sha_path,
        "archiveProof": proof_path,
    })
    if (artifacts["managedWorkflow"]["sha256"] != workflow_sha
            or artifacts["captureSource"]["sha256"] != source_sha):
        raise ValueError("recorded-provenance-changed-during-run")
    require_pins(pins, workflow_sha, workflow_path)
    summary = {
        "schemaVersion": 1, "status": "verified-cached-reader-originals-returned",
        "lab": lab, "vmIdentity": vm, "target": request["target"],
        "readerSha256": reader_sha, "workflowSha256": workflow_sha,
        "captureSourceSha256": source_sha, "managedGuestReader": guest_reader,
        "acceptedReaderSha256": EXPECTED_READER_SHA,
        "hostRequestSha256": request_sha,
        "sourcePins": {path: {"path": path, "sha256": digest}
                       for path, digest in sorted(pins.items())},
        "artifacts": artifacts,
        "archiveSha256": archive_sha, "runCount": len(proof["runs"]),
        "snapshotCounts": [item["snapshotCount"] for item in proof["runs"]],
        "output": str(output), "readerTransferredToGuest": False,
        "gameInputSent": False, "reloadOrRestartUsed": False,
        "typedFrameQualified": False,
        "limitations": [
            "The managed guest reader was hash-verified, not uploaded or replaced.",
            "Two scans remain sequential and are not an atomic API observation.",
        ],
    }
    write_new_text(output / "summary.json", json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1",), default="lab1")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--reader", type=Path, required=True)
    parser.add_argument("--reader-sha256", required=True)
    args = parser.parse_args()
    try:
        result = capture(args.lab, session_id=args.session_id, reader=args.reader,
                         reader_sha256=args.reader_sha256)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
