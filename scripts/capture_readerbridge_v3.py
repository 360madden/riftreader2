"""Acquire two bounded, identity-pinned ReaderBridge v3 generations.

This tool reads the selected physical process through the existing guarded
native readers and retains the acquired bytes. It sends no game input, changes
no GUI state, and publishes candidate evidence with ``ready: false``.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical, physical_rift, telemetry_scope_locator
from scripts.capture_physical_telemetry_zone import ReadOnlyWindowsProcess
from scripts.readerbridge_v3 import CONTROL, MAGIC, PACKET_SIZE, PRODUCER, decode_packet

MIB = 1024 * 1024
# Shared with offline replay so a permitted capture always has a valid source name.
INITIAL_SCOUT_ATTEMPTS = 3
MAX_SCOUT_ATTEMPTS = 4
SCOUT_COMMAND = "scout-values-native"
CAPTURE_COMMAND = "capture-native"
RBRG_PREFIX = "1196573266"
RRAP_PREFIX = "1346458194"
LIMITATIONS = [
    "ready is false: this is retained candidate evidence, not an operational data source.",
    "The capture does not prove API publication or changed-state field semantics.",
    "Hostility, death, learned abilities, and ability readiness are not established.",
    "Absolute addresses are valid only for the admitted process epoch and are never reused after restart.",
]


class CaptureError(ValueError):
    pass


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CaptureError("duplicate-json-key:" + key)
        value[key] = item
    return value


def _loads_json(raw, label: str) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               CaptureError("nonfinite-json-number:" + value)))
    except CaptureError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"invalid-json:{label}") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"invalid-json-object:{label}")
    return value


def _read_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise CaptureError(f"invalid-json:{path.name}") from exc
    return _loads_json(raw, path.name)


def _target(value: dict) -> dict:
    try:
        return {"processId": value["processId"],
                "processStartUtcTicks": int(value["processStartUtcTicks"]),
                "executableSha256": value["executableSha256"].upper()}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CaptureError("invalid-process-identity") from exc


def _same_target(left: dict, right: dict) -> bool:
    return _target(left) == _target(right)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _run_native(command: str, request: Path, output: Path, runner, *, native_reader=None) -> None:
    executable = physical_rift._native_reader_path(native_reader)
    completed = runner([str(executable), command, "--request", str(request),
                        "--output", str(output)], cwd=ROOT, capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
    allowed = (0, 3) if command == SCOUT_COMMAND else (0,)
    if completed.returncode not in allowed:
        raise CaptureError(f"native-{command}-failed:{completed.returncode}")


def _stderr_progress(event: dict) -> None:
    print(json.dumps(event, separators=(",", ":"), allow_nan=False), file=sys.stderr, flush=True)


def _validate_seed(seed: dict, current: dict, scan_mib: int) -> tuple[int, int]:
    if seed.get("evidenceKind") != "native-value-scout/1" or not _same_target(seed.get("identity", {}), current):
        raise CaptureError("seed-process-epoch-or-build-mismatch")
    spans = seed.get("coveredSpans")
    if not isinstance(spans, list) or not spans:
        raise CaptureError("seed-covered-span-missing")
    try:
        base = int(spans[0]["baseAddress"], 16)
        length = int(spans[0]["byteLength"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CaptureError("invalid-seed-covered-span") from exc
    if base < 0x10000 or length <= 0:
        raise CaptureError("invalid-seed-covered-span")
    return base, min(length, scan_mib * MIB)


def _scout_request(target: dict, base: int, length: int) -> dict:
    return {"schemaVersion": 1, "evidenceKind": "native-value-scout-request/1",
            "target": target, "startAddress": f"0x{base:X}",
            "references": [
                {"name": "readerbridge-prefix", "type": "int32", "value": RBRG_PREFIX},
                {"name": "coord-prefix", "type": "int32", "value": RRAP_PREFIX},
            ],
            "contextBeforeBytes": 0, "contextAfterBytes": 508,
            "maxScanBytes": length, "maxDurationMilliseconds": 3000,
            "maxRegionCount": 32768, "maxMatchCount": 64}


def _validate_scout(index: dict, target: dict, directory: Path) -> list[tuple[dict, bytes]]:
    status, reason = index.get("status"), index.get("reason")
    ordinary_partial = status == "partial" and reason in {
        "byte-budget-exceeded", "candidate-budget-exceeded", "time-budget-exceeded"}
    if (index.get("evidenceKind") != "native-value-scout/1"
            or not (status == "complete" or ordinary_partial)
            or not _same_target(index.get("identity", {}), target)
            or not _same_target(index.get("request", {}).get("target", {}), target)):
        raise CaptureError("invalid-scout-owner-or-status")
    result = []
    for candidate in index.get("candidates", []):
        if candidate.get("status") != "success":
            continue
        name = candidate.get("snapshotFile")
        if not isinstance(name, str) or Path(name).name != name:
            raise CaptureError("invalid-scout-snapshot-name")
        raw_file = directory / name
        if raw_file.is_symlink():
            raise CaptureError("invalid-scout-snapshot-path")
        raw = raw_file.read_bytes()
        if hashlib.sha256(raw).hexdigest().upper() != candidate.get("snapshotSha256"):
            raise CaptureError("scout-snapshot-hash-mismatch")
        snap = _loads_json(raw, name)
        chunks = snap.get("chunks")
        if (snap.get("evidenceKind") != "native-memory-snapshot/1"
                or snap.get("status") != "complete" or not _same_target(snap.get("identity", {}), target)
                or not isinstance(chunks, list) or len(chunks) != 1):
            raise CaptureError("invalid-scout-snapshot")
        chunk = chunks[0]
        try:
            data = base64.b64decode(chunk["bytesBase64"], validate=True)
        except Exception as exc:
            raise CaptureError("invalid-scout-snapshot-bytes") from exc
        if (chunk.get("status") != "success" or chunk.get("bytesRead") != len(data)
                or hashlib.sha256(data).hexdigest().upper() != chunk.get("bytesSha256")):
            raise CaptureError("invalid-scout-snapshot-byte-evidence")
        result.append((candidate, data))
    return result


def _companion(data: bytes) -> dict | None:
    text = data.split(b"\0", 1)[0]
    if not text.startswith(b"RRAPICOORD1|"):
        return None
    try:
        parts = text.decode("utf-8").split("|")[1:]
        fields = dict(part.split("=", 1) for part in parts)
        result = {"sequence": int(fields["seq"]), "sampledAt": fields["sampledAt"],
                "playerId": fields["playerId"], "name": fields["name"],
                "status": fields["status"], "x": float(fields["x"]),
                "y": float(fields["y"]), "z": float(fields["z"])}
        if not all(math.isfinite(result[name]) for name in ("x", "y", "z")):
            raise CaptureError("nonfinite-rrap-coordinate")
        return result
    except CaptureError:
        raise
    except (UnicodeError, ValueError, KeyError) as exc:
        raise CaptureError("invalid-rrap-companion") from exc


def _packet_control_sequence(data: bytes) -> int | None:
    """Return the advertised generation for a context beginning at real RBRG3 magic."""
    if len(data) < 40 or not data.startswith(MAGIC):
        return None
    match = CONTROL.fullmatch(data[8:40])
    return int(match[2], 16) if match is not None else None


def _locate_packet_scopes(pid, scan_bytes, reader_factory):
    """Find bounded scout windows containing decodable packets in this process."""
    window_latest = {}
    with reader_factory(pid) as reader:
        def validate_at(address):
            try:
                decoded = decode_packet(reader.read(address, PACKET_SIZE))
            except ValueError:
                return False
            start = max(0x10000, (address // scan_bytes) * scan_bytes)
            window_latest[start] = max(window_latest.get(start, 0), decoded["sequence"])
            return True

        survey = telemetry_scope_locator.discover(reader, marker=MAGIC, scan_bytes=scan_bytes,
                                                  max_scopes=3, validate_at=validate_at)
    starts = [int(start, 16) for start in survey["candidateStartAddresses"]]
    return survey, sorted(starts, key=window_latest.__getitem__, reverse=True)


def _require_advancing(decoded: dict, generations: list[dict]) -> None:
    if not generations:
        return
    previous = generations[-1]
    if (decoded["sequence"] <= previous["sequence"]
            or decoded["sourceTimeMs"] <= previous["sourceTimeMs"]):
        raise CaptureError("readerbridge-generation-not-advancing")


def _canonical_unit_key(value) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CaptureError("invalid-runtime-self-id") from exc
    if not 0 < number <= 0xFFFFFFFFFFFFFFFF:
        raise CaptureError("invalid-runtime-self-id")
    return f"u{number:016X}"


def _capture_request(target: dict, address: int) -> dict:
    sizes = (4096, 4096, 200)
    offset = 0
    ranges = []
    for index, size in enumerate(sizes):
        ranges.append({"id": f"packet-{index}", "addressKind": "absolute-session-address",
                       "address": f"0x{address + offset:X}", "byteLength": size})
        offset += size
    return {"schemaVersion": 1, "evidenceKind": "native-memory-read-request/1",
            "target": target, "sampling": {"sampleCount": 1, "intervalMilliseconds": 0,
                                             "maxDurationMilliseconds": 1000},
            "ranges": ranges}


def _packet_from_capture(report: dict, target: dict, request: dict) -> bytes:
    capture = report.get("capture", {})
    samples = capture.get("samples")
    if (report.get("evidenceKind") != "native-memory-semantic-unqualified"
            or report.get("request") != request or capture.get("status") != "complete"
            or not _same_target(capture.get("identity", {}), target)
            or not isinstance(samples, list) or len(samples) != 1):
        raise CaptureError("invalid-packet-capture-owner-or-status")
    observed = samples[0].get("ranges")
    if not isinstance(observed, list) or len(observed) != 3:
        raise CaptureError("invalid-packet-capture-ranges")
    by_id = {item.get("rangeId"): item for item in observed}
    chunks = []
    for expected in request["ranges"]:
        item = by_id.get(expected["id"])
        try:
            data = base64.b64decode(item["bytesBase64"], validate=True)
        except Exception as exc:
            raise CaptureError("invalid-packet-capture-bytes") from exc
        if (item.get("status") != "success" or item.get("requestedAddress") != expected["address"]
                or item.get("resolvedAddress") != expected["address"]
                or item.get("requestedByteLength") != expected["byteLength"]
                or item.get("bytesRead") != len(data) or len(data) != expected["byteLength"]
                or hashlib.sha256(data).hexdigest().upper() != item.get("bytesSha256")):
            raise CaptureError("invalid-packet-range-evidence")
        chunks.append(data)
    packet = b"".join(chunks)
    if len(packet) != PACKET_SIZE:
        raise CaptureError("invalid-packet-size")
    return packet


def _read_current_self(selection, reader, read_context):
    readout = read_context(selection, "player-context", native_reader=reader)
    if (readout.get("status") != "complete" or readout.get("nativeRead") != "player-context"
            or readout.get("target") != selection["target"]):
        raise CaptureError("player-context-unavailable-or-owner-changed")
    values = readout.get("nativeValues", {})
    try:
        sampled = datetime.fromisoformat(values["sampledAtUtc"])
        age = (datetime.now(timezone.utc) - sampled).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise CaptureError("invalid-player-context-time") from exc
    if not -0.1 <= age <= 2:
        raise CaptureError("stale-player-context")
    return _canonical_unit_key(values.get("unitKey")), readout


def _retain_player_context(readout, destination):
    source = readout.get("nativeOutput")
    if source is None:
        return None
    raw = Path(source).read_bytes()
    sha = hashlib.sha256(raw).hexdigest().upper()
    recorded_sha = readout.get("nativeSourceSha256")
    if recorded_sha is not None and recorded_sha.upper() != sha:
        raise CaptureError("native-player-context-source-changed")
    document = _loads_json(raw, "native-player-context")
    if (not _same_target(document.get("observation", {}).get("identity", {}), readout["target"])
            or physical_rift._native_values("player-context", document) != readout["nativeValues"]):
        raise CaptureError("native-player-context-source-mismatch")
    with destination.open("xb") as stream:
        stream.write(raw)
    return {"file": destination.name, "sha256": sha}


SELECTED_TARGET_SOURCES = {
    "selectedBefore": ("selected-before.json", "selected-target"),
    "nameBefore": ("name-before.json", "target-name"),
    "nameAfter": ("name-after.json", "target-name"),
    "selectedAfter": ("selected-after.json", "selected-target"),
}


def _retain_selected_target(selection, reader, read_native, directory, keys):
    sources = {}
    for key in keys:
        filename, kind = SELECTED_TARGET_SOURCES[key]
        path = directory / filename
        readout = read_native(selection, kind, output=path, native_reader=reader)
        if (readout.get("status") != "complete" or readout.get("nativeRead") != kind
                or readout.get("target") != selection["target"] or readout.get("nativeOutput") != str(path)):
            raise CaptureError("native-selected-target-source-unavailable:" + key)
        with path.open("rb") as stream:
            raw = stream.read(MIB + 1)
        if not 0 < len(raw) <= MIB:
            raise CaptureError("native-selected-target-source-size-invalid:" + key)
        document = _loads_json(raw, filename)
        if (not _same_target(document.get("observation", {}).get("identity", {}), selection["target"])
                or physical_rift._native_values(kind, document) != readout["nativeValues"]):
            raise CaptureError("native-selected-target-source-mismatch:" + key)
        sha = hashlib.sha256(raw).hexdigest().upper()
        recorded_sha = readout.get("nativeSourceSha256")
        if recorded_sha is not None and recorded_sha.upper() != sha:
            raise CaptureError("native-selected-target-source-changed:" + key)
        sources[key] = {"file": filename, "sha256": sha}
    return sources


def _installed_addon_file(path, expected_sha):
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MIB:
            return {"status": "invalid-file"}
        # Windows marks files that would require a cloud recall before reading.
        recall_flags = stat.FILE_ATTRIBUTE_OFFLINE | 0x00040000 | 0x00400000
        if getattr(metadata, "st_file_attributes", 0) & recall_flags:
            return {"status": "cloud-recall-required"}
        with path.open("rb") as stream:
            raw = stream.read(MIB + 1)
        after = path.lstat()
        if (len(raw) != metadata.st_size or after.st_size != metadata.st_size
                or after.st_mtime_ns != metadata.st_mtime_ns):
            return {"status": "changed-during-read"}
    except (FileNotFoundError, NotADirectoryError):
        return {"status": "missing"}
    except OSError:
        return {"status": "unreadable"}
    sha = hashlib.sha256(raw).hexdigest().upper()
    return {"status": "readable", "sha256": sha, "matchesDecoderReference": sha == expected_sha}


def check_installed_addon():
    """Compare the local startup files with the decoder's reference producer."""
    try:
        directory = observe_physical.local_rift_addons_root() / "ReaderBridge"
        if directory.is_symlink():
            raise ValueError("readerbridge-addon-directory-is-link")
    except (OSError, ValueError) as exc:
        return {"status": "blocked", "reason": str(exc)[:240]}
    files = {
        "RiftAddon.toc": _installed_addon_file(directory / "RiftAddon.toc", PRODUCER["startupManifestSha256"]),
        "ReaderBridge.lua": _installed_addon_file(directory / "ReaderBridge.lua", PRODUCER["schemaSourceSha256"]),
    }
    readable = all(row["status"] == "readable" for row in files.values())
    return {"status": "files-present" if readable else "blocked", "directory": str(directory), "files": files,
            "referenceVersion": PRODUCER["schemaSourceVersion"],
            "matchesDecoderReference": all(row.get("matchesDecoderReference") for row in files.values())}


def acquire(expected_host: str, physical_pid: int, seed_index: Path | None, output: Path,
            *, scan_mib: int = 16, native_reader=None, include_selected_target=False, runner=subprocess.run, sleep=time.sleep,
            selector=physical_rift.select_physical, read_context=physical_rift.read_native,
            progress=_stderr_progress, reader_factory=ReadOnlyWindowsProcess) -> dict:
    # Native commands run from the checkout, even when invoked from elsewhere.
    seed_index = None if seed_index is None else Path(seed_index).absolute()
    output = Path(output).absolute()
    if output.exists():
        raise CaptureError("output-already-exists")
    if type(scan_mib) is not int or not 1 <= scan_mib <= 32:
        raise CaptureError("scan-mib-out-of-range")
    if not physical_rift.is_local_host(expected_host):
        raise CaptureError("host-mismatch")
    reader = physical_rift._native_reader_path(native_reader)
    if not reader.is_file():
        raise CaptureError("native-reader-not-built")
    selection = selector(expected_host=expected_host, physical_pid=physical_pid)
    if selection.get("status") != "ready":
        raise CaptureError("physical-selection-not-ready:" + str(selection.get("reason", "unknown")))
    owner = selection.get("target", {})
    target = _target(owner)
    if seed_index is not None:
        base, scan_bytes = _validate_seed(_read_json(seed_index), target, scan_mib)
        starts = [base]
    self_id, before = _read_current_self(selection, reader, read_context)
    output.mkdir(parents=True, exist_ok=False)
    before_ref = _retain_player_context(before, output / "native-player-before.json")
    selected_target_refs = {}
    if include_selected_target:
        selected_target_refs.update(_retain_selected_target(
            selection, reader, read_context, output, ("selectedBefore", "nameBefore")))
    scope = {"seedIndex": str(seed_index) if seed_index is not None else None,
             "maxAttempts": INITIAL_SCOUT_ATTEMPTS}
    if seed_index is None:
        scan_bytes = scan_mib * MIB
        survey, starts = _locate_packet_scopes(physical_pid, scan_bytes, reader_factory)
        if selector(expected_host=expected_host, physical_pid=physical_pid).get("target") != owner:
            raise CaptureError("process-changed-during-readerbridge-discovery")
        location_report = output / "scope-survey.json"
        _write_json(location_report, dict(survey, host=expected_host, target=target, inputSent=False))
        if not starts:
            raise CaptureError("no-readerbridge-packet-scope-in-bounded-search")
        scope.update(method="bounded-private-map", mapSurveyFile=str(location_report),
                     candidateStartAddresses=[f"0x{start:X}" for start in starts])
    scope.update(startAddress=f"0x{starts[0]:X}", maxScanBytes=scan_bytes)
    progress({"stage": "admitted", "processId": target["processId"],
              "startAddress": scope["startAddress"], "maxScanBytes": scan_bytes})
    generations = []
    attempts = []
    window_index = 0
    for attempt in range(1, MAX_SCOUT_ATTEMPTS + 1):
        if attempt > scope["maxAttempts"]:
            break
        if attempt > 1:
            sleep(1.1)
        previous_count = len(generations)
        scout_request = _scout_request(target, starts[window_index], scan_bytes)
        scout_request_path = output / f"attempt-{attempt}.scout.request.json"
        scout_directory = output / f"attempt-{attempt}.scout"
        _write_json(scout_request_path, scout_request)
        _run_native(SCOUT_COMMAND, scout_request_path, scout_directory, runner, native_reader=reader)
        index_path = scout_directory / "index.json"
        index = _read_json(index_path)
        candidates = _validate_scout(index, target, scout_directory)
        packet_candidates = [(c, d, sequence) for c, d in candidates
                             if "readerbridge-prefix" in c.get("referenceNames", [])
                             and (sequence := _packet_control_sequence(d)) is not None]
        packet_candidates.sort(key=lambda item: item[2], reverse=True)
        found_companions = []
        rejected_companions = 0
        for _, data in candidates:
            try:
                companion = _companion(data)
            except CaptureError:
                rejected_companions += 1
                continue
            if companion is not None:
                found_companions.append(companion)
        companions = [item for item in found_companions
                      if item["status"] == "pass" and item["playerId"] == self_id]
        companion_sequences = {item["sequence"] for item in companions}
        matched_packets = [item for item in packet_candidates if item[2] in companion_sequences]
        attempt_summary = {"attempt": attempt, "scoutIndex": str(index_path),
                           "startAddress": scout_request["startAddress"],
                           "packetCandidateCount": len(packet_candidates),
                           "companionCandidateCount": len(found_companions),
                           "rejectedCompanionCount": rejected_companions,
                           "matchedPacketCandidateCount": len(matched_packets)}
        attempts.append(attempt_summary)
        progress({"stage": "scouted", **attempt_summary})
        # Read only the newest header with a matching self companion.
        for candidate, _, expected_sequence in matched_packets[:1]:
            try:
                address = int(candidate["address"], 16)
                request = _capture_request(target, address)
                request_path = output / f"attempt-{attempt}.capture.request.json"
                report_path = output / f"attempt-{attempt}.capture.json"
                _write_json(request_path, request)
                _run_native(CAPTURE_COMMAND, request_path, report_path, runner, native_reader=reader)
                report = _read_json(report_path)
                packet = _packet_from_capture(report, target, request)
                decoded = decode_packet(packet)
                if decoded["sequence"] != expected_sequence:
                    raise CaptureError("readerbridge-packet-changed-after-scout")
                player = decoded["sections"]["P"]
                same = [item for item in companions if item["sequence"] == decoded["sequence"]
                        and item["name"] == player["name"]]
                same = [item for item in same
                        if Decimal(item["sampledAt"]) * 1000 == decoded["sourceTimeMs"]]
                if not same:
                    raise CaptureError("same-generation-companion-not-found")
                _require_advancing(decoded, generations)
                packet_path = output / f"generation-{len(generations) + 1}.bin"
                packet_path.write_bytes(packet)
                generations.append({"sequence": decoded["sequence"],
                                    "sourceTimeMs": decoded["sourceTimeMs"],
                                    "packetSha256": decoded["packetSha256"],
                                    "packetFile": str(packet_path), "packetAddress": candidate["address"],
                                    "player": player, "flags": decoded["flags"],
                                    "health": decoded["health"], "power": decoded["power"],
                                    "companion": same[0], "captureReport": str(report_path)})
                progress({"stage": "generation-captured", "attempt": attempt,
                          "sequence": decoded["sequence"], "generationCount": len(generations)})
                break
            except (CaptureError, ValueError, KeyError, InvalidOperation) as exc:
                attempt_summary["candidateFailure"] = str(exc)
                progress({"stage": "candidate-rejected", "attempt": attempt,
                          "reason": str(exc)})
        if len(generations) == 2 and generations[1]["sequence"] > generations[0]["sequence"]:
            break
        # Reserve one additional confirmation attempt when there is exactly
        # one valid generation. A search with no valid data remains capped
        # at three attempts; two advancing generations are still mandatory.
        if attempt == INITIAL_SCOUT_ATTEMPTS and len(generations) == 1:
            scope["maxAttempts"] = MAX_SCOUT_ATTEMPTS
        if len(generations) == previous_count:
            window_index = (window_index + 1) % len(starts)
    if len(generations) != 2 or generations[1]["sequence"] <= generations[0]["sequence"]:
        raise CaptureError("two-advancing-generations-not-observed")
    final_id, after = _read_current_self(selection, reader, read_context)
    if final_id != self_id:
        raise CaptureError("player-changed-during-readerbridge-acquisition")
    after_ref = _retain_player_context(after, output / "native-player-after.json")
    if include_selected_target:
        selected_target_refs.update(_retain_selected_target(
            selection, reader, read_context, output, ("nameAfter", "selectedAfter")))
    result = {"schemaVersion": 1, "evidenceKind": "readerbridge-v3-bounded-acquisition/1",
              "status": "captured", "ready": False, "inputSent": False,
              "guiStateChanged": False, "host": selection["ownerHost"], "target": target, "selfId": self_id,
              "scope": scope,
              "generations": generations, "attempts": attempts, "limitations": LIMITATIONS}
    if before_ref is not None and after_ref is not None:
        result["nativePlayerContext"] = {"before": before_ref, "after": after_ref}
    if include_selected_target:
        result["nativeSelectedTarget"] = selected_target_refs
    result["nextCheck"] = ("Independently correlate a controlled changed state before treating any "
                           "decoded field as qualified; reacquire from a fresh scout after every restart.")
    _write_json(output / "result.json", result)
    progress({"stage": "complete", "generationCount": 2, "ready": False,
              "result": str(output / "result.json")})
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--physical-pid", type=int)
    mode.add_argument("--check-dependencies", action="store_true",
                      help="check the installed addon and native reader without selecting RIFT")
    parser.add_argument("--seed-index", type=Path)
    parser.add_argument("--auto-map", action="store_true",
                        help="find bounded scout windows in current readable private memory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-reader", type=Path, help="absolute path to a local published reader")
    parser.add_argument("--scan-mib", type=int,
                        help="bounded first-span scan size (1-32 MiB; default 16)")
    parser.add_argument("--include-selected-target", action="store_true",
                        help="retain bounded native target name and level reads around the Lua packets")
    args = parser.parse_args(argv)
    if args.check_dependencies:
        if args.auto_map or any(value is not None for value in (args.seed_index, args.output, args.scan_mib)):
            parser.error("--check-dependencies accepts only --expected-host, --native-reader and --include-selected-target")
        kinds = ("player-context", "selected-target", "target-name") if args.include_selected_target else "player-context"
        result = physical_rift.check_native_reader(
            args.expected_host, args.native_reader, kind=kinds,
            additional_commands=(SCOUT_COMMAND, CAPTURE_COMMAND))
        addon = ({"status": "not-checked", "reason": "host-mismatch"} if result.get("reason") == "host-mismatch"
                 else check_installed_addon())
        if result["status"] == "ready" and addon["status"] != "files-present":
            result.update(status="blocked", reason="readerbridge-installed-addon-unavailable")
        print(json.dumps(dict(result, installedAddon=addon, inputSent=False, readerBridgePublisher="unverified")))
        return 0 if result["status"] == "ready" else 2
    if args.output is None or args.auto_map == (args.seed_index is not None):
        parser.error("--physical-pid requires --output and exactly one of --seed-index or --auto-map")
    try:
        print(json.dumps(acquire(args.expected_host, args.physical_pid, args.seed_index,
                                 args.output, scan_mib=16 if args.scan_mib is None else args.scan_mib,
                                 native_reader=args.native_reader,
                                 include_selected_target=args.include_selected_target), allow_nan=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "ready": False, "inputSent": False,
                          "reason": str(exc)}, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
