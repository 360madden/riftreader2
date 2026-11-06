from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import extract_casting_reference_snapshots as extract
from tests.test_inspect_casting_reference import snapshot as wire_snapshot, wire


PID = 7164
TICKS = 639294897866244204
BUNDLE_SHA = "B" * 64
WINDOW_START = 0x20000000
MARKER_OFFSET = 2 * extract.PAGE_BYTES + 100


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def identity():
    return {
        "processId": PID,
        "processStartUtcTicks": TICKS,
        "executablePath": r"C:\Game\rift_x64.exe",
        "executableSha256": extract.GAME_SHA,
        "moduleBaseAddress": 0x140000000,
        "moduleSize": 63164416,
    }


def target():
    return {key: identity()[key] for key in extract.TARGET_KEYS}


def implementation():
    return {
        "toolVersion": "test-reader",
        "deploymentKind": "single-file-bundle",
        "assemblySha256": None,
        "bundleFileName": "RiftReader2.Live.exe",
        "bundleSha256": BUNDLE_SHA,
    }


def write_json(path: Path, value) -> bytes:
    raw = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def make_capture(root: Path, name: str, sequence: int, clock: float, *,
                 extra_wire: bytes | None = None):
    capture = root / name
    capture.mkdir()
    command_request = {
        "schemaVersion": 1,
        "evidenceKind": extract.CAPTURE_REQUEST_KIND,
        "target": target(),
        "startAddress": "0x10000",
        "maxScanBytes": 536870912,
        "maxDurationMilliseconds": 30000,
        "maxRegionCount": 32768,
        "maxMatchCount": 128,
        "maxCopiedCandidates": 8,
    }
    command_path = capture / "source-request.json"
    command_raw = write_json(command_path, command_request)

    source_request = {
        "schemaVersion": 1,
        "evidenceKind": extract.SNAPSHOT_REQUEST_KIND,
        "target": target(),
        "maxDurationMilliseconds": 30000,
        "ranges": [{"addressKind": "absolute-session-address",
                    "address": f"0x{WINDOW_START:X}", "byteLength": extract.WINDOW_BYTES}],
    }
    request_name = "capture-01.request.json"
    request_raw = write_json(capture / request_name, source_request)
    selected_wire = wire(wire_snapshot(sequence, clock))
    window = bytearray(b"\xCC" * extract.WINDOW_BYTES)
    window[MARKER_OFFSET:MARKER_OFFSET + len(selected_wire)] = selected_wire
    if extra_wire is not None:
        window[100:100 + len(extra_wire)] = extra_wire
    chunks = []
    for index in range(extract.PAGE_COUNT):
        page = bytes(window[index * extract.PAGE_BYTES:(index + 1) * extract.PAGE_BYTES])
        chunks.append({
            "address": f"0x{WINDOW_START + index * extract.PAGE_BYTES:X}",
            "requestedByteLength": extract.PAGE_BYTES,
            "status": "success",
            "bytesRead": extract.PAGE_BYTES,
            "bytesBase64": base64.b64encode(page).decode("ascii"),
            "bytesSha256": sha(page),
            "win32ErrorCode": None,
            "reason": None,
        })
    snapshot_value = {
        "schemaVersion": 1,
        "evidenceKind": extract.SNAPSHOT_KIND,
        "source": {
            "requestEvidenceKind": extract.SNAPSHOT_REQUEST_KIND,
            "requestSha256": sha(request_raw),
            "requestSha256Verification": "producer-declared",
            "implementation": implementation(),
        },
        "identity": identity(),
        "startedAtUtc": "2026-11-06T14:00:00.0000000Z",
        "completedAtUtc": "2026-11-06T14:00:00.1000000Z",
        "status": "complete",
        "reason": None,
        "chunks": chunks,
        "limitations": ["test fixture"],
    }
    snapshot_name = "capture-01.snapshot.json"
    snapshot_raw = write_json(capture / snapshot_name, snapshot_value)
    candidate = {
        "markerAddress": f"0x{WINDOW_START + MARKER_OFFSET:X}",
        "status": "complete",
        "reason": None,
        "requestFile": request_name,
        "requestSha256": sha(request_raw),
        "snapshotFile": snapshot_name,
        "snapshotSha256": sha(snapshot_raw),
    }
    manifest = {
        "schemaVersion": 1,
        "evidenceKind": extract.CAPTURE_KIND,
        "sourceRequestFile": "source-request.json",
        "requestSha256": sha(command_raw),
        "implementation": implementation(),
        "request": command_request,
        "identity": identity(),
        "startedAtUtc": "2026-11-06T14:00:00.0000000Z",
        "completedAtUtc": "2026-11-06T14:00:00.2000000Z",
        "status": "complete",
        "reason": None,
        "scout": {"status": "complete"},
        "capturedCandidates": 1,
        "publishedSnapshots": 1,
        "copyLimited": False,
        "candidates": [candidate],
        "limitations": ["test fixture"],
    }
    write_json(capture / "index.json", manifest)
    return capture, command_path


class CastingReferenceSnapshotExtractionTests(unittest.TestCase):
    def test_continuity_chain_uses_separate_captures_and_rejects_ambiguity(self):
        def candidate(sequence, clock, *, target_id="uPLAYER"):
            value = wire_snapshot(sequence, clock)
            value["targetId"]["value"] = target_id
            value["ability"]["target"]["value"] = target_id
            raw = wire(value)
            return {"address": f"0x{sequence:X}", "wire": raw,
                    "decoded": extract.wire_decoder.decode_wire(raw)}

        first = candidate(10, 101.0)
        stale = candidate(4, 100.1, target_id="uSTALE")
        second = candidate(11, 101.3)
        chain = extract._unique_continuity_chain([
            {"wireCandidates": [first, stale]}, {"wireCandidates": [second]}])
        self.assertEqual([10, 11], [item["decoded"]["sequence"] for item in chain])

        another_first = candidate(20, 201.0)
        another_second = candidate(21, 201.3)
        with self.assertRaisesRegex(extract.CastingSnapshotError, "ambiguous"):
            extract._unique_continuity_chain([
                {"wireCandidates": [first, another_first]},
                {"wireCandidates": [second, another_second]}])

    def test_two_complete_captures_publish_exact_wires_and_ready_continuity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = make_capture(root, "one", 10, 101.0)
            second = make_capture(root, "two", 11, 101.3)
            output = root / "result"
            result = extract.extract(
                [first[0], second[0]], output,
                pid=PID, ticks=TICKS, game_sha=extract.GAME_SHA, bundle_sha=BUNDLE_SHA)
            self.assertTrue(result["observedReady"])
            self.assertEqual("observed-ready", result["status"])
            self.assertTrue((output / "wire-01.bin").is_file())
            self.assertTrue((output / "wire-02.bin").is_file())
            self.assertTrue((output / "extraction.json").is_file())

    def test_one_snapshot_never_claims_ready_and_extra_wire_is_not_continuity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            extra = wire(wire_snapshot(2, 100.1))
            capture, request = make_capture(root, "one", 3, 100.3, extra_wire=extra)
            output = root / "result"
            result = extract.extract([capture], output, pid=PID, ticks=TICKS,
                                     game_sha=extract.GAME_SHA, bundle_sha=BUNDLE_SHA)
            self.assertFalse(result["observedReady"])
            self.assertEqual("continuity-unproven", result["status"])
            self.assertEqual(2, result["sources"][0]["strictWireCount"])
            self.assertEqual(1, result["sources"][0]["markerWireCandidateCount"])
            self.assertEqual(1, result["inspection"]["frameCount"])

    def test_chunk_hash_contiguity_and_complete_status_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for kind in ("hash", "address", "partial"):
                case = root / kind; case.mkdir()
                capture, request = make_capture(case, "capture", 1, 100.25)
                snapshot_path = capture / "capture-01.snapshot.json"
                value = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if kind == "hash":
                    value["chunks"][2]["bytesSha256"] = "0" * 64
                elif kind == "address":
                    value["chunks"][2]["address"] = f"0x{WINDOW_START + 3 * extract.PAGE_BYTES:X}"
                else:
                    value["status"] = "partial"; value["reason"] = "read-hole"
                raw = write_json(snapshot_path, value)
                manifest_path = capture / "index.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["candidates"][0]["snapshotSha256"] = sha(raw)
                write_json(manifest_path, manifest)
                with self.subTest(kind=kind), self.assertRaises(extract.CastingSnapshotError):
                    extract.extract([capture], case / "result", pid=PID, ticks=TICKS,
                                    game_sha=extract.GAME_SHA, bundle_sha=BUNDLE_SHA)

    def test_request_source_marker_identity_and_bundle_mismatches_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cases = ("request", "source", "marker", "identity", "bundle")
            for kind in cases:
                case = root / kind; case.mkdir()
                capture, request = make_capture(case, "capture", 1, 100.25)
                if kind == "request":
                    request.write_text(request.read_text(encoding="utf-8") + " ", encoding="utf-8")
                elif kind == "marker":
                    manifest = json.loads((capture / "index.json").read_text(encoding="utf-8"))
                    manifest["candidates"][0]["markerAddress"] = f"0x{WINDOW_START + 20:X}"
                    write_json(capture / "index.json", manifest)
                elif kind == "identity":
                    snapshot_path = capture / "capture-01.snapshot.json"
                    value = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    value["identity"]["processId"] += 1
                    raw = write_json(snapshot_path, value)
                    manifest = json.loads((capture / "index.json").read_text(encoding="utf-8"))
                    manifest["candidates"][0]["snapshotSha256"] = sha(raw)
                    write_json(capture / "index.json", manifest)
                elif kind == "source":
                    snapshot_path = capture / "capture-01.snapshot.json"
                    value = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    value["source"]["requestSha256"] = "0" * 64
                    raw = write_json(snapshot_path, value)
                    manifest = json.loads((capture / "index.json").read_text(encoding="utf-8"))
                    manifest["candidates"][0]["snapshotSha256"] = sha(raw)
                    write_json(capture / "index.json", manifest)
                expected_bundle = "C" * 64 if kind == "bundle" else BUNDLE_SHA
                with self.subTest(kind=kind), self.assertRaises(extract.CastingSnapshotError):
                    extract.extract([capture], case / "result", pid=PID, ticks=TICKS,
                                    game_sha=extract.GAME_SHA, bundle_sha=expected_bundle)

    def test_partial_manifest_malformed_wire_and_existing_output_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture, request = make_capture(root, "capture", 1, 100.25)
            output = root / "existing"; output.mkdir()
            with self.assertRaisesRegex(extract.CastingSnapshotError, "output"):
                extract.extract([capture], output, pid=PID, ticks=TICKS,
                                game_sha=extract.GAME_SHA, bundle_sha=BUNDLE_SHA)
            manifest_path = capture / "index.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "partial"; manifest["reason"] = "time-budget"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(extract.CastingSnapshotError, "manifest"):
                extract.extract([capture], root / "partial", pid=PID, ticks=TICKS,
                                game_sha=extract.GAME_SHA, bundle_sha=BUNDLE_SHA)


if __name__ == "__main__":
    unittest.main()
