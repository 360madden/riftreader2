"""Verify fixed-command native snapshots and extract exact RR2CASTREF1 wires.

Each input is one exact output directory from `scout-copy-casting-reference-native`,
including its index-bound `source-request.json`.  The operation publishes only
to a new directory, and delegates wire semantics and cross-capture continuity
to `inspect_casting_reference`.  Multiple wires within one memory snapshot are
retained as candidates but never used as separate continuity observations.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

from scripts import inspect_casting_reference as wire_decoder


GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
CAPTURE_KIND = "native-casting-reference-inline-capture/1"
CAPTURE_REQUEST_KIND = "native-casting-reference-inline-capture-request/1"
SNAPSHOT_KIND = "native-memory-snapshot/1"
SNAPSHOT_REQUEST_KIND = "native-memory-snapshot-request/1"
PAGE_BYTES = 4096
PAGE_COUNT = 7
WINDOW_BYTES = PAGE_BYTES * PAGE_COUNT
MAX_JSON_BYTES = 2 * 1024 * 1024
SHA = re.compile(r"[0-9A-F]{64}\Z")
CAPTURE_FILE = re.compile(r"capture-(\d{2})\.(request|snapshot)\.json\Z")
MANIFEST_KEYS = {
    "schemaVersion", "evidenceKind", "sourceRequestFile", "requestSha256", "implementation", "request",
    "identity", "startedAtUtc", "completedAtUtc", "status", "reason", "scout",
    "capturedCandidates", "publishedSnapshots", "copyLimited", "candidates", "limitations",
}
CAPTURE_REQUEST_KEYS = {
    "schemaVersion", "evidenceKind", "target", "startAddress", "maxScanBytes",
    "maxDurationMilliseconds", "maxRegionCount", "maxMatchCount", "maxCopiedCandidates",
}
IDENTITY_KEYS = {
    "processId", "processStartUtcTicks", "executablePath", "executableSha256",
    "moduleBaseAddress", "moduleSize",
}
TARGET_KEYS = {"processId", "processStartUtcTicks", "executableSha256"}
SNAPSHOT_REQUEST_KEYS = {
    "schemaVersion", "evidenceKind", "target", "maxDurationMilliseconds", "ranges"}
RANGE_KEYS = {"addressKind", "address", "byteLength"}
SNAPSHOT_KEYS = {
    "schemaVersion", "evidenceKind", "source", "identity", "startedAtUtc",
    "completedAtUtc", "status", "reason", "chunks", "limitations"}
SOURCE_KEYS = {
    "requestEvidenceKind", "requestSha256", "requestSha256Verification", "implementation"}
CHUNK_KEYS = {
    "address", "requestedByteLength", "status", "bytesRead", "bytesBase64",
    "bytesSha256", "win32ErrorCode", "reason"}
CANDIDATE_KEYS = {
    "markerAddress", "status", "reason", "requestFile", "requestSha256",
    "snapshotFile", "snapshotSha256"}


class CastingSnapshotError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CastingSnapshotError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _read(path: Path, limit: int = MAX_JSON_BYTES) -> bytes:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= limit:
        raise CastingSnapshotError(f"bounded-regular-file-required:{path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise CastingSnapshotError(f"file-size-changed:{path.name}")
    return raw


def _json(path: Path, limit: int = MAX_JSON_BYTES) -> tuple[dict, bytes]:
    raw = _read(path, limit)
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(
                               CastingSnapshotError(f"json-nonfinite:{item}")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CastingSnapshotError(f"json-invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise CastingSnapshotError(f"json-object-required:{path.name}")
    return value, raw


def _exact(value, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise CastingSnapshotError(f"shape:{label}")
    return value


def _utc(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise CastingSnapshotError(f"utc:{label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CastingSnapshotError(f"utc:{label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise CastingSnapshotError(f"utc:{label}")
    return parsed


def _address(value, label: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9A-F]+", value):
        raise CastingSnapshotError(f"address:{label}")
    number = int(value[2:], 16)
    if number < 0x10000 or value != f"0x{number:X}":
        raise CastingSnapshotError(f"address:{label}")
    return number


def _target(value, pid: int, ticks: int, game_sha: str, label: str) -> dict:
    target = _exact(value, TARGET_KEYS, label)
    if (target.get("processId") != pid or type(target.get("processId")) is not int
            or target.get("processStartUtcTicks") != ticks
            or type(target.get("processStartUtcTicks")) is not int
            or target.get("executableSha256") != game_sha):
        raise CastingSnapshotError(f"identity:{label}")
    return target


def _identity(value, pid: int, ticks: int, game_sha: str, label: str) -> dict:
    identity = _exact(value, IDENTITY_KEYS, label)
    _target({key: identity[key] for key in TARGET_KEYS}, pid, ticks, game_sha, label)
    if (not isinstance(identity["executablePath"], str) or not identity["executablePath"]
            or type(identity["moduleBaseAddress"]) is not int
            or type(identity["moduleSize"]) is not int or identity["moduleSize"] <= 0):
        raise CastingSnapshotError(f"identity:{label}")
    return identity


def _implementation(value, bundle_sha: str, label: str) -> dict:
    keys = {"toolVersion", "deploymentKind", "assemblySha256", "bundleFileName", "bundleSha256"}
    implementation = _exact(value, keys, label)
    if (not isinstance(implementation["toolVersion"], str)
            or not 0 < len(implementation["toolVersion"]) <= 128
            or implementation["deploymentKind"] != "single-file-bundle"
            or implementation["assemblySha256"] is not None
            or not isinstance(implementation["bundleFileName"], str)
            or implementation["bundleSha256"] != bundle_sha):
        raise CastingSnapshotError(f"implementation:{label}")
    return implementation


def _extract_wires(data: bytes, base: int) -> list[tuple[int, bytes, dict]]:
    found = []
    cursor = 0
    while True:
        offset = data.find(wire_decoder.PREFIX, cursor)
        if offset < 0:
            break
        payload = offset + len(wire_decoder.PREFIX)
        end = data.find(wire_decoder.SUFFIX, payload,
                        min(len(data), payload + wire_decoder.MAX_JSON_BYTES
                            + len(wire_decoder.SUFFIX)))
        if end < 0:
            raise CastingSnapshotError("malformed-or-incomplete-wire-in-complete-window")
        raw = data[offset:end + len(wire_decoder.SUFFIX)]
        try:
            decoded = wire_decoder.decode_wire(raw)
        except wire_decoder.CastingReferenceError as exc:
            raise CastingSnapshotError(f"strict-wire:{exc}") from exc
        found.append((base + offset, raw, decoded))
        cursor = end + len(wire_decoder.SUFFIX)
    return found


def _snapshot_pair(capture: Path, candidate: dict, *, pid: int, ticks: int,
                   game_sha: str, bundle_sha: str, manifest_identity: dict,
                   implementation: dict, max_duration: int) -> dict:
    request_name, snapshot_name = candidate["requestFile"], candidate["snapshotFile"]
    matched_a = CAPTURE_FILE.fullmatch(request_name) if isinstance(request_name, str) else None
    matched_b = CAPTURE_FILE.fullmatch(snapshot_name) if isinstance(snapshot_name, str) else None
    if (matched_a is None or matched_b is None or matched_a.group(1) != matched_b.group(1)
            or matched_a.group(2) != "request" or matched_b.group(2) != "snapshot"):
        raise CastingSnapshotError("candidate-file-names")
    request, request_raw = _json(capture / request_name, 64 * 1024)
    snapshot, snapshot_raw = _json(capture / snapshot_name)
    request_sha, snapshot_sha = _sha(request_raw), _sha(snapshot_raw)
    if (candidate["requestSha256"] != request_sha
            or candidate["snapshotSha256"] != snapshot_sha):
        raise CastingSnapshotError("candidate-file-sha")

    _exact(request, SNAPSHOT_REQUEST_KEYS, "snapshot-request")
    if request["schemaVersion"] != 1 or request["evidenceKind"] != SNAPSHOT_REQUEST_KIND:
        raise CastingSnapshotError("snapshot-request-kind")
    if request["maxDurationMilliseconds"] != max_duration:
        raise CastingSnapshotError("snapshot-request-duration")
    _target(request["target"], pid, ticks, game_sha, "snapshot-request-target")
    ranges = request["ranges"]
    if not isinstance(ranges, list) or len(ranges) != 1:
        raise CastingSnapshotError("snapshot-request-ranges")
    range_value = _exact(ranges[0], RANGE_KEYS, "snapshot-request-range")
    if (range_value["addressKind"] != "absolute-session-address"
            or range_value["byteLength"] != WINDOW_BYTES
            or type(range_value["byteLength"]) is not int):
        raise CastingSnapshotError("snapshot-request-range")
    window_start = _address(range_value["address"], "window-start")

    _exact(snapshot, SNAPSHOT_KEYS, "snapshot")
    if (snapshot["schemaVersion"] != 1 or snapshot["evidenceKind"] != SNAPSHOT_KIND
            or snapshot["status"] != "complete" or snapshot["reason"] is not None):
        raise CastingSnapshotError("snapshot-not-complete")
    source = _exact(snapshot["source"], SOURCE_KEYS, "snapshot-source")
    if (source["requestEvidenceKind"] != SNAPSHOT_REQUEST_KIND
            or source["requestSha256"] != request_sha
            or source["requestSha256Verification"] != "producer-declared"
            or _implementation(source["implementation"], bundle_sha, "snapshot-implementation")
            != implementation):
        raise CastingSnapshotError("snapshot-source")
    if _identity(snapshot["identity"], pid, ticks, game_sha, "snapshot") != manifest_identity:
        raise CastingSnapshotError("snapshot-manifest-identity")
    if _utc(snapshot["completedAtUtc"], "snapshot-completed") < _utc(
            snapshot["startedAtUtc"], "snapshot-started"):
        raise CastingSnapshotError("snapshot-time-order")

    chunks = snapshot["chunks"]
    if not isinstance(chunks, list) or len(chunks) != PAGE_COUNT:
        raise CastingSnapshotError("snapshot-seven-pages-required")
    pages = []
    for index, chunk in enumerate(chunks):
        _exact(chunk, CHUNK_KEYS, f"chunk-{index}")
        expected_address = window_start + index * PAGE_BYTES
        if (_address(chunk["address"], f"chunk-{index}") != expected_address
                or chunk["requestedByteLength"] != PAGE_BYTES
                or chunk["status"] != "success" or chunk["bytesRead"] != PAGE_BYTES
                or chunk["win32ErrorCode"] is not None or chunk["reason"] is not None
                or not isinstance(chunk["bytesBase64"], str)
                or not isinstance(chunk["bytesSha256"], str)
                or not SHA.fullmatch(chunk["bytesSha256"])):
            raise CastingSnapshotError(f"chunk-contract:{index}")
        try:
            raw = base64.b64decode(chunk["bytesBase64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise CastingSnapshotError(f"chunk-base64:{index}") from exc
        if len(raw) != PAGE_BYTES or _sha(raw) != chunk["bytesSha256"]:
            raise CastingSnapshotError(f"chunk-content:{index}")
        pages.append(raw)
    joined = b"".join(pages)
    marker = _address(candidate["markerAddress"], "candidate-marker")
    if not window_start <= marker < window_start + WINDOW_BYTES:
        raise CastingSnapshotError("candidate-marker-outside-window")
    wires = _extract_wires(joined, window_start)
    marker_wires = [item for item in wires if item[0] == marker]
    if len(marker_wires) != 1:
        raise CastingSnapshotError("candidate-marker-wire-not-unique")
    address, _, _ = marker_wires[0]
    return {
        "requestPath": str((capture / request_name).resolve(strict=True)),
        "requestSha256": request_sha,
        "snapshotPath": str((capture / snapshot_name).resolve(strict=True)),
        "snapshotSha256": snapshot_sha,
        "markerAddress": f"0x{address:X}",
        "wireCandidateCount": len(wires),
        "wires": [
            {"address": f"0x{wire_address:X}", "wire": raw_wire, "decoded": decoded}
            for wire_address, raw_wire, decoded in wires
        ],
    }


def _capture(capture: Path, *, pid: int, ticks: int,
             game_sha: str, bundle_sha: str) -> dict:
    if not capture.is_dir() or capture.is_symlink():
        raise CastingSnapshotError("capture-directory-required")
    manifest, manifest_raw = _json(capture / "index.json")
    _exact(manifest, MANIFEST_KEYS, "manifest")
    source_request_name = manifest["sourceRequestFile"]
    if source_request_name != "source-request.json":
        raise CastingSnapshotError("source-request-file-name")
    command_request = capture / source_request_name
    original_request, original_raw = _json(command_request, 64 * 1024)
    _exact(original_request, CAPTURE_REQUEST_KEYS, "command-request")
    request_sha = _sha(original_raw)
    if (manifest["schemaVersion"] != 1 or manifest["evidenceKind"] != CAPTURE_KIND
            or manifest["requestSha256"] != request_sha
            or manifest["request"] != original_request
            or manifest["status"] != "complete" or manifest["reason"] is not None
            or manifest["copyLimited"] is not False):
        raise CastingSnapshotError("manifest-contract")
    if (original_request["schemaVersion"] != 1
            or original_request["evidenceKind"] != CAPTURE_REQUEST_KIND):
        raise CastingSnapshotError("command-request-kind")
    _target(original_request["target"], pid, ticks, game_sha, "command-target")
    _address(original_request["startAddress"], "command-start")
    for name, minimum, maximum in (
            ("maxScanBytes", 64 * 1024, 512 * 1024 * 1024),
            ("maxDurationMilliseconds", 1, 30_000),
            ("maxRegionCount", 1, 32_768),
            ("maxMatchCount", 1, 128),
            ("maxCopiedCandidates", 1, 8)):
        value = original_request[name]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise CastingSnapshotError(f"command-bound:{name}")
    identity = _identity(manifest["identity"], pid, ticks, game_sha, "manifest")
    implementation = _implementation(manifest["implementation"], bundle_sha, "manifest")
    if _utc(manifest["completedAtUtc"], "manifest-completed") < _utc(
            manifest["startedAtUtc"], "manifest-started"):
        raise CastingSnapshotError("manifest-time-order")
    if not isinstance(manifest["scout"], dict) or manifest["scout"].get("status") != "complete":
        raise CastingSnapshotError("manifest-scout-incomplete")
    candidates = manifest["candidates"]
    if (not isinstance(candidates, list) or len(candidates) > 128
            or isinstance(manifest["capturedCandidates"], bool)
            or not isinstance(manifest["capturedCandidates"], int)
            or isinstance(manifest["publishedSnapshots"], bool)
            or not isinstance(manifest["publishedSnapshots"], int)):
        raise CastingSnapshotError("manifest-candidates")
    published = []
    expected_files = {"index.json", source_request_name}
    for candidate in candidates:
        _exact(candidate, CANDIDATE_KEYS, "candidate")
        has_files = candidate["requestFile"] is not None or candidate["snapshotFile"] is not None
        if not has_files:
            continue
        if (candidate["status"] != "complete" or candidate["reason"] is not None
                or any(candidate[key] is None for key in (
                    "requestFile", "requestSha256", "snapshotFile", "snapshotSha256"))):
            raise CastingSnapshotError("published-candidate-not-complete")
        published.append(_snapshot_pair(
            capture, candidate, pid=pid, ticks=ticks, game_sha=game_sha,
            bundle_sha=bundle_sha, manifest_identity=identity,
            implementation=implementation,
            max_duration=original_request["maxDurationMilliseconds"]))
        expected_files.update((candidate["requestFile"], candidate["snapshotFile"]))
    if (manifest["publishedSnapshots"] != len(published)
            or manifest["capturedCandidates"] != len(published)
            or not published):
        raise CastingSnapshotError("published-candidate-count")
    entries = list(capture.iterdir())
    if ({path.name for path in entries if path.is_file()} != expected_files
            or any(path.is_dir() or path.is_symlink() for path in entries)):
        raise CastingSnapshotError("capture-files-unreferenced-or-missing")
    unique_wires = {}
    strict_wire_count = 0
    for publication in published:
        strict_wire_count += publication["wireCandidateCount"]
        for found in publication["wires"]:
            if found["address"] == publication["markerAddress"]:
                unique_wires.setdefault(found["decoded"]["wireSha256"], found)
    return {
        "capturePath": str(capture.resolve(strict=True)),
        "manifestSha256": _sha(manifest_raw),
        "commandRequestPath": str(command_request.resolve(strict=True)),
        "commandRequestSha256": request_sha,
        "identity": identity,
        "implementation": implementation,
        "candidateCount": len(candidates),
        "publications": published,
        "wireCandidates": list(unique_wires.values()),
        "strictWireCount": strict_wire_count,
    }


def _unique_continuity_chain(sources: list[dict]) -> list[dict]:
    chains = [[candidate] for candidate in sources[0]["wireCandidates"]]
    if not chains:
        raise CastingSnapshotError("no-strict-wire-candidate")
    for source in sources[1:]:
        extended = []
        for chain in chains:
            for candidate in source["wireCandidates"]:
                trial = [dict(item["decoded"], path=item["address"])
                         for item in chain + [candidate]]
                try:
                    wire_decoder.inspect_decoded(trial)
                except wire_decoder.CastingReferenceError:
                    continue
                extended.append(chain + [candidate])
                if len(extended) > 256:
                    raise CastingSnapshotError("wire-continuity-ambiguous")
        chains = extended
        if not chains:
            raise CastingSnapshotError("no-cross-capture-wire-continuity")
    signatures = {}
    for chain in chains:
        signature = tuple(item["decoded"]["wireSha256"] for item in chain)
        signatures.setdefault(signature, chain)
    if len(signatures) != 1:
        raise CastingSnapshotError("wire-continuity-ambiguous")
    return next(iter(signatures.values()))


def extract(captures: list[Path], output: Path, *,
            pid: int, ticks: int, game_sha: str, bundle_sha: str) -> dict:
    if (not captures or len(captures) > wire_decoder.MAX_WIRES
            or type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0
            or game_sha != GAME_SHA or not SHA.fullmatch(bundle_sha)):
        raise CastingSnapshotError("arguments-invalid")
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise CastingSnapshotError("output-must-be-absent-with-existing-parent")
    sources = [_capture(capture, pid=pid, ticks=ticks,
                        game_sha=game_sha, bundle_sha=bundle_sha)
               for capture in captures]
    identity = sources[0]["identity"]
    implementation = sources[0]["implementation"]
    if any(source["identity"] != identity or source["implementation"] != implementation
           for source in sources[1:]):
        raise CastingSnapshotError("cross-capture-native-identity-changed")
    chain = _unique_continuity_chain(sources)
    decoded_frames = []
    for index, candidate in enumerate(chain, 1):
        decoded = dict(candidate["decoded"])
        decoded["path"] = str((output / f"wire-{index:02}.bin").resolve())
        decoded_frames.append(decoded)
    try:
        inspection = wire_decoder.inspect_decoded(decoded_frames)
    except wire_decoder.CastingReferenceError as exc:
        raise CastingSnapshotError(f"wire-continuity:{exc}") from exc
    result = {
        "schemaVersion": 1,
        "evidenceKind": "casting-reference-snapshot-extraction/1",
        "status": inspection["status"],
        "observedReady": inspection["observedReady"],
        "identity": identity,
        "implementation": implementation,
        "sources": [{key: value for key, value in source.items()
                     if key not in ("publications", "wireCandidates")}
                    | {"markerWireCandidateCount": len(source["wireCandidates"]),
                       "publications": [
                           {key: value for key, value in publication.items() if key != "wires"}
                           for publication in source["publications"]]}
                    for source in sources],
        "inspection": inspection,
        "limitations": [
            "Only complete seven-page snapshots from the fixed casting-reference command are accepted.",
            "Multiple wires inside one snapshot are candidates, not independent time observations.",
            "Observed-ready requires two separately acquired identity-stable advancing frames.",
            "API/native views may share a getter or cache; extraction is not independent arithmetic proof.",
        ],
    }
    with tempfile.TemporaryDirectory(prefix=".rr2-cast-extract-", dir=output.parent) as temporary:
        stage = Path(temporary)
        for index, candidate in enumerate(chain, 1):
            with (stage / f"wire-{index:02}.bin").open("xb") as stream:
                stream.write(candidate["wire"])
        with (stage / "extraction.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        if output.exists() or output.is_symlink():
            raise CastingSnapshotError("output-appeared-during-publication")
        os.rename(stage, output)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--process-id", required=True, type=int)
    parser.add_argument("--process-start-ticks", required=True, type=int)
    parser.add_argument("--game-sha256", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = extract(
            args.capture, args.output,
            pid=args.process_id, ticks=args.process_start_ticks,
            game_sha=args.game_sha256, bundle_sha=args.bundle_sha256)
        print(json.dumps({"status": result["status"], "output": str(args.output.resolve()),
                          "observedReady": result["observedReady"]}))
        return 0
    except (OSError, CastingSnapshotError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
