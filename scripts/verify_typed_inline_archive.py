"""Verify and recover two exact-epoch native typed inline-capture runs from one guest ZIP.

This is an offline, bounded, no-overwrite artifact operation. It does not contact
a VM, invoke a capture executable or treat prefix matches as valid Lua frames.
Run the existing strict C# snapshot loader/typed-wire inspector on recovered
originals before accepting any field-level evidence.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_MEMBERS = 40
NAME = re.compile(r"run-0[12]/(?:index|input\.request|capture-0[1-8]\.(?:request|snapshot))\.json\Z")
CAPTURE = re.compile(r"capture-(0[1-8])\.(request|snapshot)\.json\Z")
SHA256 = re.compile(r"[0-9A-Fa-f]{64}\Z")
BUNDLE_KIND = "native-typed-inline-capture/1"
REQUEST_KIND = "native-typed-inline-capture-request/1"
SNAPSHOT_KIND = "native-memory-snapshot/1"
SNAPSHOT_REQUEST_KIND = "native-memory-snapshot-request/1"


class ArchiveError(ValueError):
    """The candidate archive is outside the strict supported evidence scope."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha_match(value: object, expected: str) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value)) and value.upper() == expected


def _json(raw: bytes, label: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ArchiveError(f"{label}: duplicate JSON property")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise ArchiveError(f"{label}: invalid JSON ({type(exc).__name__})") from exc
    if not isinstance(value, dict):
        raise ArchiveError(f"{label}: object JSON required")
    return value


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ArchiveError(f"{label}: UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveError(f"{label}: invalid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ArchiveError(f"{label}: timezone must be UTC")
    return parsed


def _epoch(obj: object, pid: int, ticks: int, game_sha: str, label: str) -> None:
    if not isinstance(obj, dict):
        raise ArchiveError(f"{label}: missing exact process identity")
    if (type(obj.get("processId")) is not int or obj["processId"] != pid
            or type(obj.get("processStartUtcTicks")) is not int
            or obj["processStartUtcTicks"] != ticks
            or not _sha_match(obj.get("executableSha256"), game_sha)):
        raise ArchiveError(f"{label}: target process epoch or executable hash differs")


def _check_snapshot_chunks(snapshot: dict, label: str) -> None:
    chunks = snapshot.get("chunks")
    if not isinstance(chunks, list) or len(chunks) > 128:
        raise ArchiveError(f"{label}: invalid snapshot chunks")
    for index, chunk in enumerate(chunks):
        name = f"{label} chunk {index}"
        if not isinstance(chunk, dict):
            raise ArchiveError(f"{name}: chunk object required")
        encoded = chunk.get("bytesBase64")
        if encoded is None:
            if chunk.get("status") == "success":
                raise ArchiveError(f"{name}: success lacks saved bytes")
            continue
        if not isinstance(encoded, str):
            raise ArchiveError(f"{name}: encoded bytes must be text")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ArchiveError(f"{name}: invalid base64") from exc
        if (len(raw) > 4096 or type(chunk.get("bytesRead")) is not int
                or chunk["bytesRead"] != len(raw)
                or not _sha_match(chunk.get("bytesSha256"), _sha(raw))):
            raise ArchiveError(f"{name}: byte length or SHA-256 mismatch")
        if chunk.get("status") == "success" and (
                type(chunk.get("requestedByteLength")) is not int
                or chunk["requestedByteLength"] != len(raw)):
            raise ArchiveError(f"{name}: success has incomplete chunk")


def _check_run(files: dict[str, bytes], name: str, pid: int, ticks: int,
               game_sha: str, bundle_sha: str) -> dict:
    prefix = name + "/"
    index_raw = files.get(prefix + "index.json")
    original_request = files.get(prefix + "input.request.json")
    if index_raw is None or original_request is None:
        raise ArchiveError(f"{name}: index and original input request are both required")
    report = _json(index_raw, prefix + "index.json")
    request = _json(original_request, prefix + "input.request.json")
    if report.get("schemaVersion") != 1 or report.get("evidenceKind") != BUNDLE_KIND:
        raise ArchiveError(f"{name}: unsupported typed inline report kind/version")
    if request.get("schemaVersion") != 1 or request.get("evidenceKind") != REQUEST_KIND:
        raise ArchiveError(f"{name}: unsupported input request kind/version")
    if not _sha_match(report.get("requestSha256"), _sha(original_request)):
        raise ArchiveError(f"{name}: original input request SHA mismatch")
    if report.get("request") != request:
        raise ArchiveError(f"{name}: embedded request differs from original input bytes")
    _epoch(request.get("target"), pid, ticks, game_sha, f"{name} request")
    _epoch(report.get("identity"), pid, ticks, game_sha, f"{name} report")
    implementation = report.get("implementation")
    if not isinstance(implementation, dict) or not _sha_match(
            implementation.get("bundleSha256"), bundle_sha):
        raise ArchiveError(f"{name}: capture implementation bundle SHA mismatch")
    started = _utc(report.get("startedAtUtc"), f"{name} startedAtUtc")
    completed = _utc(report.get("completedAtUtc"), f"{name} completedAtUtc")
    if completed < started:
        raise ArchiveError(f"{name}: acquisition time reversed")
    if report.get("status") not in ("complete", "partial", "identity-invalidated"):
        raise ArchiveError(f"{name}: unknown acquisition status")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 128:
        raise ArchiveError(f"{name}: invalid candidates list")
    expected = {prefix + "index.json", prefix + "input.request.json"}
    snapshots = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ArchiveError(f"{name}: candidate must be object")
        source = candidate.get("requestFile")
        result = candidate.get("snapshotFile")
        if source is None and result is None:
            continue
        if not isinstance(source, str) or not isinstance(result, str):
            raise ArchiveError(f"{name}: candidate must reference a complete file pair")
        matched_a = CAPTURE.fullmatch(source)
        matched_b = CAPTURE.fullmatch(result)
        if (matched_a is None or matched_b is None or matched_a.group(1) != matched_b.group(1)
                or matched_a.group(2) != "request" or matched_b.group(2) != "snapshot"):
            raise ArchiveError(f"{name}: unapproved candidate artifact names")
        source_name, snapshot_name = prefix + source, prefix + result
        if source_name in expected or snapshot_name in expected:
            raise ArchiveError(f"{name}: duplicate candidate reference")
        expected.update((source_name, snapshot_name))
        if source_name not in files or snapshot_name not in files:
            raise ArchiveError(f"{name}: referenced source or snapshot missing")
        if not _sha_match(candidate.get("requestSha256"), _sha(files[source_name])):
            raise ArchiveError(f"{name}: candidate original request hash mismatches")
        if not _sha_match(candidate.get("snapshotSha256"), _sha(files[snapshot_name])):
            raise ArchiveError(f"{name}: candidate original snapshot hash mismatches")
        source_doc = _json(files[source_name], source_name)
        snapshot = _json(files[snapshot_name], snapshot_name)
        if (source_doc.get("schemaVersion") != 1
                or source_doc.get("evidenceKind") != SNAPSHOT_REQUEST_KIND
                or snapshot.get("schemaVersion") != 1
                or snapshot.get("evidenceKind") != SNAPSHOT_KIND):
            raise ArchiveError(f"{name}: candidate snapshot schema mismatch")
        _epoch(source_doc.get("target"), pid, ticks, game_sha, source_name)
        _epoch(snapshot.get("identity"), pid, ticks, game_sha, snapshot_name)
        src = snapshot.get("source")
        if (not isinstance(src, dict)
                or src.get("requestEvidenceKind") != SNAPSHOT_REQUEST_KIND
                or not _sha_match(src.get("requestSha256"), _sha(files[source_name]))):
            raise ArchiveError(f"{name}: snapshot source-request provenance differs")
        impl = src.get("implementation")
        if not isinstance(impl, dict) or not _sha_match(impl.get("bundleSha256"), bundle_sha):
            raise ArchiveError(f"{name}: snapshot bundle provenance differs")
        _check_snapshot_chunks(snapshot, snapshot_name)
        snapshots += 1
    if type(report.get("publishedSnapshots")) is not int or report["publishedSnapshots"] != snapshots:
        raise ArchiveError(f"{name}: published snapshot count disagrees with references")
    actual = {file for file in files if file.startswith(prefix)}
    if actual != expected:
        raise ArchiveError(f"{name}: archive has missing or unreferenced run files")
    return {
        "run": name, "startedAtUtc": started.isoformat(),
        "completedAtUtc": completed.isoformat(), "status": report["status"],
        "indexSha256": _sha(index_raw), "inputRequestSha256": _sha(original_request),
        "candidateCount": len(candidates), "snapshotCount": snapshots,
    }


def verify_archive(archive: Path, archive_sha: str, *, pid: int, ticks: int,
                   game_sha: str, bundle_sha: str, min_separation_seconds: float = 1.0,
                   marker: str | None = None
                   ) -> tuple[dict[str, bytes], dict]:
    """Check all bounded archive members before returning any publishable bytes."""
    if (not archive.is_file() or archive.is_symlink()
            or archive.stat().st_size > MAX_ARCHIVE_BYTES
            or archive.stat().st_size == 0):
        raise ArchiveError("ZIP must be an existing non-symlink file within 16 MiB")
    if (type(pid) is not int or pid < 1 or type(ticks) is not int or ticks < 1
            or not isinstance(min_separation_seconds, (int, float))
            or not 0 < min_separation_seconds <= 3600
            or not isinstance(game_sha, str) or not SHA256.fullmatch(game_sha)
            or not isinstance(bundle_sha, str) or not SHA256.fullmatch(bundle_sha)
            or not isinstance(archive_sha, str) or not SHA256.fullmatch(archive_sha)):
        raise ArchiveError("invalid pinned archive, process or bundle inputs")
    with archive.open("rb") as stream:
        archive_bytes = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("ZIP grew beyond the 16 MiB pinned limit")
    if not _sha_match(archive_sha, _sha(archive_bytes)):
        raise ArchiveError("guest ZIP SHA-256 differs from expected")
    files: dict[str, bytes] = {}
    with ZipFile(BytesIO(archive_bytes)) as zipped:
        members = zipped.infolist()
        if len(members) > MAX_MEMBERS:
            raise ArchiveError("too many ZIP members")
        total = 0
        seen: set[str] = set()
        for info in members:
            name = info.filename
            if name in seen:
                raise ArchiveError("duplicate ZIP member")
            seen.add(name)
            if info.flag_bits & 0x1 or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                raise ArchiveError("unsupported or encrypted ZIP member")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ArchiveError("symbolic ZIP member refused")
            if info.is_dir():
                if name not in ("run-01/", "run-02/"):
                    raise ArchiveError("unexpected ZIP directory")
                continue
            if not NAME.fullmatch(name) or "\\" in name:
                raise ArchiveError("unexpected ZIP member name or path")
            if not 0 < info.file_size <= MAX_FILE_BYTES:
                raise ArchiveError("invalid ZIP member size")
            total += info.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ArchiveError("ZIP expands beyond 8 MiB limit")
            with zipped.open(info) as source:
                raw = source.read(info.file_size + 1)
            if len(raw) != info.file_size:
                raise ArchiveError("ZIP member decoded size differs")
            files[name] = raw
    a = _check_run(files, "run-01", pid, ticks, game_sha.upper(), bundle_sha.upper())
    b = _check_run(files, "run-02", pid, ticks, game_sha.upper(), bundle_sha.upper())
    a_finish = datetime.fromisoformat(a["completedAtUtc"])
    b_start = datetime.fromisoformat(b["startedAtUtc"])
    if (b_start - a_finish).total_seconds() < min_separation_seconds:
        raise ArchiveError("second acquisition is not sufficiently separated in time")
    receipt = {
        "schemaVersion": 1, "evidenceKind": "native-typed-inline-archive-proof/1",
        "archiveSha256": _sha(archive_bytes), "archiveBytes": len(archive_bytes),
        "target": {"processId": pid, "processStartUtcTicks": ticks,
                   "executableSha256": game_sha.upper()},
        "bundleSha256": bundle_sha.upper(), "totalRecoveredBytes": sum(map(len, files.values())),
        "runs": [a, b], "files": [
            {"path": name, "byteLength": len(raw), "sha256": _sha(raw)}
            for name, raw in sorted(files.items())
        ],
        "scope": "offline-content-integrity-only",
        "typedFrameQualified": False,
        "nativeXyzQualified": False,
    }
    if marker is not None:
        if marker not in ("RR2R1|", "RRAPIVAL2|"):
            raise ArchiveError("unsupported expected marker")
        for name in ("run-01", "run-02"):
            index = _json(files[name + "/index.json"], name)
            request = _json(files[name + "/input.request.json"], name)
            if (request.get("marker", "RRAPIVAL2|") != marker
                    or index.get("request", {}).get("marker", "RRAPIVAL2|") != marker
                    or (marker == "RR2R1|" and index.get("marker") != marker)):
                raise ArchiveError("capture request or scout marker mismatch")
    return files, receipt


def _read_small_receipt(path: Path, label: str) -> tuple[dict, str]:
    if (not path.is_file() or path.is_symlink()
            or not 0 < path.stat().st_size <= 8192):
        raise ArchiveError(f"{label}: receipt must be a bounded original file")
    with path.open("rb") as source:
        raw = source.read(8193)
    if len(raw) > 8192:
        raise ArchiveError(f"{label}: receipt too large")
    return _json(raw, label), _sha(raw)


def _transfer_proof(archive: Path, archive_sha: str, archive_bytes: int, *,
                    claim_path: Path | None, upload_path: Path | None,
                    pid: int, ticks: int, game_sha: str, bundle_sha: str,
                    expected_guest: str, claim_kind: str = "inline") -> dict | None:
    """Bind an exact-kind guest ZIP claim to the receiver's actual content receipt."""
    if claim_kind not in ("inline", "pointer"):
        raise ArchiveError("unsupported guest ZIP claim kind")
    expected_claim = ("guest-typed-inline-zip-claim/1" if claim_kind == "inline"
                      else "guest-native-pointer-zip-claim/1")
    expected_upload = ("content-addressed-guest-map-transfer" if claim_kind == "inline"
                       else "content-addressed-guest-pointer-transfer")
    if claim_path is None and upload_path is None:
        return None  # Host-only synthetic fixture; do not invent guest attribution.
    if claim_path is None or upload_path is None:
        raise ArchiveError("guest archive needs both claim and upload receipts")
    claim, claim_hash = _read_small_receipt(claim_path, "guest ZIP claim")
    delivered, upload_hash = _read_small_receipt(upload_path, "guest ZIP upload receipt")
    if (type(claim.get("schemaVersion")) is not int
            or claim["schemaVersion"] != 1
            or claim.get("evidenceKind") != expected_claim
            or claim.get("source") != "guest-declared-only"
            or claim.get("guest") != expected_guest):
        raise ArchiveError("guest ZIP claim has wrong schema or peer")
    _epoch(claim.get("target"), pid, ticks, game_sha.upper(), "guest ZIP claim")
    if (not _sha_match(claim.get("bundleSha256"), bundle_sha.upper())
            or not _sha_match(claim.get("zipSha256"), archive_sha.upper())
            or type(claim.get("zipBytes")) is not int
            or claim["zipBytes"] != archive_bytes):
        raise ArchiveError("guest ZIP claim differs from exact original bytes")
    if (type(delivered.get("schemaVersion")) is not int
            or delivered["schemaVersion"] != 1
            or delivered.get("purpose") != expected_upload
            or delivered.get("state") != "received"
            or delivered.get("guest") != claim["guest"]
            or type(delivered.get("bytes")) is not int
            or delivered["bytes"] != archive_bytes
            or not _sha_match(delivered.get("sha256"), archive_sha.upper())):
        raise ArchiveError("guest upload receipt differs from exact ZIP claim/bytes")
    original_path = delivered.get("destination")
    if (not isinstance(original_path, str)
            or Path(original_path).resolve(strict=True) != archive.resolve(strict=True)):
        raise ArchiveError("guest upload receipt points at a different ZIP")
    return {
        "state": "claim-upload-and-extracted-bytes-agree",
        "guest": claim["guest"],
        "claimReceiptSha256": claim_hash,
        "uploadReceiptSha256": upload_hash,
        "zipSha256": archive_sha.upper(),
        "zipBytes": archive_bytes,
    }


def verify_and_publish(archive: Path, archive_sha: str, output: Path, *,
                       pid: int, ticks: int, game_sha: str, bundle_sha: str,
                       min_separation_seconds: float = 1.0,
                       marker: str | None = None,
                       claim_path: Path | None = None,
                       upload_path: Path | None = None,
                       expected_guest: str = "192.168.56.128") -> dict:
    """Publish originals atomically to a new folder, never modifying an existing report."""
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ArchiveError("output must be absent and parent directory must already exist")
    files, receipt = verify_archive(
        archive, archive_sha, pid=pid, ticks=ticks, game_sha=game_sha,
        bundle_sha=bundle_sha, min_separation_seconds=min_separation_seconds, marker=marker)
    transfer = _transfer_proof(
        archive, receipt["archiveSha256"], receipt["archiveBytes"],
        claim_path=claim_path, upload_path=upload_path,
        pid=pid, ticks=ticks, game_sha=game_sha, bundle_sha=bundle_sha,
        expected_guest=expected_guest)
    if transfer is not None:
        receipt["guestTransfer"] = transfer
    with tempfile.TemporaryDirectory(prefix=".rr2-inline-stage-", dir=output.parent) as staging:
        stage = Path(staging)
        for name, raw in sorted(files.items()):
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        with (stage / "archive-proof.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if output.exists() or output.is_symlink():
            raise ArchiveError("output appeared during verification")
        os.rename(stage, output)  # Windows rename refuses an existing target.
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--process-id", required=True, type=int)
    parser.add_argument("--process-start-ticks", required=True, type=int)
    parser.add_argument("--game-sha256", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--marker", choices=("RR2R1|", "RRAPIVAL2|"))
    parser.add_argument("--claim-receipt", type=Path)
    parser.add_argument("--upload-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_and_publish(
            args.archive, args.expected_sha256, args.output,
            pid=args.process_id, ticks=args.process_start_ticks,
            game_sha=args.game_sha256, bundle_sha=args.bundle_sha256,
            claim_path=args.claim_receipt, upload_path=args.upload_receipt, marker=args.marker)
    except (ArchiveError, BadZipFile, OSError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"state": "verified-and-published",
                      "archiveSha256": result["archiveSha256"],
                      "snapshots": sum(x["snapshotCount"] for x in result["runs"]),
                      "typedFrameQualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
