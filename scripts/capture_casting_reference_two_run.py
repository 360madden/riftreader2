"""Capture two bounded RR2CASTREF1 runs on Lab 1 with one pinned reader upload.

The wrapper sends no game input and performs no addon deployment, reload or
restart.  It requires the four installed RiftReader2Casting files to match the
current repository sources before and after two exact-process read-only scans.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import shutil
import sys
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.lab_codex import LabCodex
from scripts.sample_current_native_vitals import checked_sha, staged_script
from scripts.sample_current_native_xyz import GAME_SHA, digest


EVIDENCE = ROOT / "artifacts/casting-reference-two-run/runs"
ADDON_ROOT = ROOT / "addon/RiftReader2Casting"
ADDON_FILES = ("RiftAddon.toc", "model.lua", "ability_reference.lua", "main.lua")
GUEST_ADDON = PureWindowsPath(
    r"C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2Casting")
SOURCE_FILES = (
    "scripts/capture_casting_reference_two_run.py",
    "src/RiftReader2.Live/CastingReferenceInlineCaptureCore.cs",
    "src/RiftReader2.Live/CastingReferenceInlineCaptureCommand.cs",
    "src/RiftReader2.Live/NativeCommandRunner.cs",
)
REQUEST_KIND = "native-casting-reference-inline-capture-request/1"
EVIDENCE_KIND = "native-casting-reference-inline-capture/1"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_FILES = 64
SHA = re.compile(r"[0-9A-F]{64}")


class CastingCaptureError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CastingCaptureError("duplicate-json-key:" + key)
        value[key] = item
    return value


def _load_json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CastingCaptureError(label + ":invalid-json") from exc
    if not isinstance(value, dict):
        raise CastingCaptureError(label + ":object-required")
    return value


def _pins() -> dict[str, str]:
    return {name: _sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def _addon_pins() -> dict[str, str]:
    pins = {}
    for name in ADDON_FILES:
        path = ADDON_ROOT / name
        if not path.is_file() or path.is_symlink():
            raise CastingCaptureError("addon-source-file-invalid:" + name)
        pins[name] = _sha(path.read_bytes())
    return pins


def _require_pins(source_pins: dict[str, str], addon_pins: dict[str, str]) -> None:
    if _pins() != source_pins:
        raise CastingCaptureError("capture-source-changed-during-run")
    if _addon_pins() != addon_pins:
        raise CastingCaptureError("addon-source-changed-during-run")


def _request(pid: int, ticks: int) -> dict:
    if type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0:
        raise CastingCaptureError("process-identity-invalid")
    return {
        "schemaVersion": 1,
        "evidenceKind": REQUEST_KIND,
        "target": {"processId": pid, "processStartUtcTicks": ticks,
                   "executableSha256": GAME_SHA},
        "startAddress": "0x10000",
        "maxScanBytes": 536870912,
        "maxDurationMilliseconds": 30000,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
    }


def _utc(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise CastingCaptureError(label + ":utc-required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CastingCaptureError(label + ":utc-invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise CastingCaptureError(label + ":utc-required")
    return parsed


def verify_archive(archive: Path, expected_sha: str, recovered: Path,
                   request: dict, reader_sha: str) -> dict:
    expected_sha = checked_sha(expected_sha)
    if not archive.is_file() or archive.is_symlink() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise CastingCaptureError("archive-file-invalid")
    raw_archive = archive.read_bytes()
    if _sha(raw_archive) != expected_sha:
        raise CastingCaptureError("archive-sha256-mismatch")
    if recovered.exists():
        raise CastingCaptureError("recovered-output-exists")
    entries: list[dict] = []
    indexes = []
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        files = [item for item in members if not item.is_dir()]
        if len(files) < 4 or len(files) > MAX_ARCHIVE_FILES:
            raise CastingCaptureError("archive-file-count-invalid")
        total = 0
        seen = set()
        for item in files:
            name = item.filename.replace("\\", "/")
            parts = name.split("/")
            if (len(parts) != 2 or parts[0] not in ("run-01", "run-02")
                    or not parts[1] or parts[1] in (".", "..")
                    or name in seen
                    or ((item.external_attr >> 16) & 0o170000) == 0o120000):
                raise CastingCaptureError("archive-entry-path-invalid")
            seen.add(name)
            total += item.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise CastingCaptureError("archive-expanded-size-invalid")
        recovered.mkdir(parents=True, exist_ok=False)
        try:
            for item in files:
                name = item.filename.replace("\\", "/")
                data = bundle.read(item)
                if len(data) != item.file_size:
                    raise CastingCaptureError("archive-entry-size-invalid")
                path = recovered.joinpath(*name.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                entries.append({"path": name, "bytes": len(data), "sha256": _sha(data)})
            for run in ("run-01", "run-02"):
                indexes.append(_verify_run(recovered / run, request, reader_sha))
            if (indexes[1]["started"] - indexes[0]["completed"]).total_seconds() < 1.0:
                raise CastingCaptureError("run-separation-below-one-second")
        except Exception:
            # The caller owns the unique output root. Leave no recovered tree that
            # could be mistaken for verified originals after a failed check.
            shutil.rmtree(recovered, ignore_errors=True)
            raise
    proof = {
        "schemaVersion": 1,
        "evidenceKind": "casting-reference-two-run-archive-proof/1",
        "archiveSha256": expected_sha,
        "archiveBytes": len(raw_archive),
        "files": sorted(entries, key=lambda item: item["path"]),
        "runs": [{"name": item["name"], "indexSha256": item["indexSha256"],
                  "startedAtUtc": item["startedRaw"], "completedAtUtc": item["completedRaw"],
                  "publishedSnapshots": item["publishedSnapshots"]} for item in indexes],
        "minimumSeparationSeconds": 1.0,
    }
    (recovered / "archive-proof.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8", newline="\n")
    return proof


def _verify_run(folder: Path, request: dict, reader_sha: str) -> dict:
    index_path = folder / "index.json"
    if not index_path.is_file() or index_path.is_symlink():
        raise CastingCaptureError(folder.name + ":index-missing")
    index_raw = index_path.read_bytes()
    index = _load_json(index_raw, folder.name + ":index")
    source_name = index.get("sourceRequestFile")
    if source_name != "source-request.json":
        raise CastingCaptureError(folder.name + ":source-request-name-invalid")
    source_path = folder / source_name
    if not source_path.is_file() or source_path.is_symlink():
        raise CastingCaptureError(folder.name + ":source-request-missing")
    source_raw = source_path.read_bytes()
    if index.get("requestSha256") != _sha(source_raw) or _load_json(
            source_raw, folder.name + ":source-request") != request or index.get("request") != request:
        raise CastingCaptureError(folder.name + ":request-provenance-mismatch")
    if index.get("schemaVersion") != 1 or index.get("evidenceKind") != EVIDENCE_KIND:
        raise CastingCaptureError(folder.name + ":manifest-contract-invalid")
    identity = index.get("identity")
    if (not isinstance(identity, dict) or identity.get("processId") != request["target"]["processId"]
            or identity.get("processStartUtcTicks") != request["target"]["processStartUtcTicks"]
            or identity.get("executableSha256") != GAME_SHA):
        raise CastingCaptureError(folder.name + ":identity-mismatch")
    implementation = index.get("implementation")
    if (not isinstance(implementation, dict) or implementation.get("deploymentKind") != "single-file-bundle"
            or implementation.get("bundleSha256") != reader_sha):
        raise CastingCaptureError(folder.name + ":reader-identity-mismatch")
    candidates = index.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 128:
        raise CastingCaptureError(folder.name + ":candidate-list-invalid")
    allowed = {"index.json", source_name}
    published = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise CastingCaptureError(folder.name + ":candidate-invalid")
        names = (candidate.get("requestFile"), candidate.get("snapshotFile"))
        hashes = (candidate.get("requestSha256"), candidate.get("snapshotSha256"))
        if names == (None, None) and hashes == (None, None):
            continue
        request_name, snapshot_name = names
        request_match = (re.fullmatch(r"capture-(\d{2})\.request\.json", request_name)
                         if isinstance(request_name, str) else None)
        snapshot_match = (re.fullmatch(r"capture-(\d{2})\.snapshot\.json", snapshot_name)
                          if isinstance(snapshot_name, str) else None)
        if (request_match is None or snapshot_match is None
                or request_match.group(1) != snapshot_match.group(1)
                or not all(isinstance(value, str) and SHA.fullmatch(value) for value in hashes)):
            raise CastingCaptureError(folder.name + ":candidate-reference-invalid")
        for name, expected in zip(names, hashes):
            path = folder / name
            if not path.is_file() or path.is_symlink() or _sha(path.read_bytes()) != expected:
                raise CastingCaptureError(folder.name + ":candidate-hash-mismatch")
            allowed.add(name)
        published += 1
    actual = {path.name for path in folder.iterdir() if path.is_file()}
    if actual != allowed or index.get("publishedSnapshots") != published:
        raise CastingCaptureError(folder.name + ":file-closure-invalid")
    started_raw, completed_raw = index.get("startedAtUtc"), index.get("completedAtUtc")
    started, completed = _utc(started_raw, folder.name + ":started"), _utc(
        completed_raw, folder.name + ":completed")
    if completed < started:
        raise CastingCaptureError(folder.name + ":time-order-invalid")
    return {"name": folder.name, "indexSha256": _sha(index_raw),
            "started": started, "completed": completed,
            "startedRaw": started_raw, "completedRaw": completed_raw,
            "publishedSnapshots": published}


def capture(reader: Path, reader_sha256: str) -> dict:
    reader = reader.resolve()
    reader_sha256 = checked_sha(reader_sha256)
    if (not reader.is_file() or reader.is_symlink() or reader.name != "RiftReader2.Live.exe"
            or digest(reader) != reader_sha256):
        raise CastingCaptureError("reader-identity-invalid")
    source_pins, addon_pins = _pins(), _addon_pins()
    api = LabCodex()
    _, _, config, settings = api._configuration("lab1")
    vm = api.collect_identity(api._native(config, settings, api.run_root / ".doctor"))
    token = uuid.uuid4().hex
    output = EVIDENCE / token
    output.mkdir(parents=True, exist_ok=False)
    guest_root = settings["guestRoot"] + "\\casting-reference-" + token
    guest_reader = guest_root + "\\RiftReader2.Live.exe"
    guest_identity = guest_root + "\\preflight.json"
    guest_request = guest_root + "\\request.json"
    guest_archive = guest_root + "\\two-runs.zip"
    guest_archive_sha = guest_archive + ".sha256"
    request_path = output / "request.json"

    with api._session(config, settings, vm, output) as guest:
        addon_checks = []
        for name, expected in addon_pins.items():
            path = str(GUEST_ADDON / name)
            addon_checks.append(
                "if(!(Test-Path -LiteralPath " + ps_literal(path) + " -PathType Leaf)){throw 'addon-file-missing:" + name + "'};"
                "$h=(Get-FileHash -LiteralPath " + ps_literal(path) + " -Algorithm SHA256).Hash;"
                "if($h -cne " + ps_literal(expected) + "){throw 'addon-sha-mismatch:" + name + "'};"
                "$files+=[ordered]@{name=" + ps_literal(name) + ";sha256=$h};")
        preflight = (
            "$ErrorActionPreference='Stop';$folder=" + ps_literal(guest_root) + ";"
            "if(Test-Path -LiteralPath $folder){throw 'guest-staging-exists'};"
            "[IO.Directory]::CreateDirectory($folder)|Out-Null;$files=@();" + "".join(addon_checks) +
            "$games=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);"
            "if($games.Count -ne 1){throw 'exactly-one-game-required'};$g=$games[0];"
            "$gameSha=(Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash;"
            "if($gameSha -cne " + ps_literal(GAME_SHA) + "){throw 'rift-build-mismatch'};"
            "$data=[ordered]@{pid=[int]$g.Id;ticks=[long]$g.StartTime.ToUniversalTime().Ticks;"
            "sha=$gameSha;addonFiles=$files;atUtc=[DateTime]::UtcNow.ToString('O')};"
            "[IO.File]::WriteAllText(" + ps_literal(guest_identity) + ",($data|ConvertTo-Json -Depth 5 -Compress),"
            "(New-Object Text.UTF8Encoding($false)))")
        staged_script(guest, preflight, output / "preflight.ps1",
                      settings["guestRoot"] + "\\casting-ref-preflight-" + token + ".ps1", timeout=80)
        guest.copy_from_guest(guest_identity, output / "preflight.json", timeout=50)
        identity = _load_json((output / "preflight.json").read_bytes(), "preflight")
        pid, ticks = identity.get("pid"), identity.get("ticks")
        if (type(pid) is not int or type(ticks) is not int or identity.get("sha") != GAME_SHA
                or {item.get("name"): item.get("sha256") for item in identity.get("addonFiles", [])}
                != addon_pins):
            raise CastingCaptureError("fresh-preflight-invalid")
        request = _request(pid, ticks)
        request_raw = (json.dumps(request, indent=2) + "\n").encode()
        request_path.write_bytes(request_raw)
        guest.run("copyFileFromHostToGuest", str(reader), guest_reader, timeout=180)
        guest.run("copyFileFromHostToGuest", str(request_path), guest_request, timeout=50)
        run1, run2 = guest_root + "\\run-01", guest_root + "\\run-02"
        post_addon = "".join(addon_checks)
        script = (
            "$ErrorActionPreference='Stop';$reader=" + ps_literal(guest_reader) + ";"
            "$request=" + ps_literal(guest_request) + ";$run1=" + ps_literal(run1) + ";$run2=" + ps_literal(run2) + ";"
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne " + ps_literal(reader_sha256)
            + "){throw 'reader-sha-mismatch-before'};"
            "& $reader scout-copy-casting-reference-native --request $request --output $run1|Out-Null;"
            "$e1=$LASTEXITCODE;if($e1 -notin 0,3 -or !(Test-Path (Join-Path $run1 'index.json'))){throw 'run1-failed'};"
            "Start-Sleep -Seconds 1;"
            "& $reader scout-copy-casting-reference-native --request $request --output $run2|Out-Null;"
            "$e2=$LASTEXITCODE;if($e2 -notin 0,3 -or !(Test-Path (Join-Path $run2 'index.json'))){throw 'run2-failed'};"
            "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
            "if([long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks) + "){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne " + ps_literal(GAME_SHA)
            + "){throw 'game-build-changed'};$files=@();" + post_addon +
            "if((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -cne " + ps_literal(reader_sha256)
            + "){throw 'reader-sha-mismatch-after'};"
            "Compress-Archive -LiteralPath $run1,$run2 -DestinationPath " + ps_literal(guest_archive)
            + " -CompressionLevel Optimal;"
            "[IO.File]::WriteAllText(" + ps_literal(guest_archive_sha) + ",(Get-FileHash -LiteralPath "
            + ps_literal(guest_archive) + " -Algorithm SHA256).Hash,(New-Object Text.UTF8Encoding($false)))")
        staged_script(guest, script, output / "capture.ps1",
                      settings["guestRoot"] + "\\casting-ref-capture-" + token + ".ps1", timeout=120)
        archive = output / "two-runs.zip"
        archive_transfer = output / ".two-runs.zip.transfer"
        archive_sha_path = output / "two-runs.zip.sha256"
        archive_sha_transfer = output / ".two-runs.zip.sha256.transfer"
        guest.copy_from_guest(guest_archive, archive_transfer, timeout=80)
        guest.copy_from_guest(guest_archive_sha, archive_sha_transfer, timeout=50)
        returned_sha = checked_sha(archive_sha_transfer.read_text(encoding="utf-8-sig").strip())
        if digest(archive_transfer) != returned_sha:
            raise CastingCaptureError("returned-archive-sha256-mismatch")
        archive_transfer.replace(archive)
        archive_sha_transfer.replace(archive_sha_path)

    _require_pins(source_pins, addon_pins)
    archive_sha = checked_sha(
        (output / "two-runs.zip.sha256").read_text(encoding="utf-8-sig").strip())
    proof = verify_archive(archive, archive_sha, output / "recovered", request, reader_sha256)
    _require_pins(source_pins, addon_pins)
    summary = {
        "schemaVersion": 1, "status": "verified-casting-reference-originals-returned",
        "lab": "lab1", "vmIdentity": vm, "target": request["target"],
        "readerSha256": reader_sha256, "sourcePins": source_pins,
        "addonSourceAndInstalledPins": addon_pins, "archiveSha256": archive_sha,
        "archiveProofSha256": _sha((output / "recovered/archive-proof.json").read_bytes()),
        "runCount": 2, "output": str(output), "gameInputSent": False,
        "addonDeployedOrReloaded": False, "gameRestarted": False,
        "limitations": [
            "Installed file hashes do not independently prove the addon was loaded in this process.",
            "Each partial scan is bounded coverage and not a whole-process absence claim.",
            "Strict RR2CASTREF1 decoding and cross-run continuity are separate offline gates."
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", required=True, type=Path)
    parser.add_argument("--reader-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = capture(args.reader, args.reader_sha256)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
