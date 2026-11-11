"""Self-contained offline tests for SHA-pinned unbound RR2A1/native comparisons."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_physical_player_context_pair as context
from scripts import replay_physical_rr2a1 as replay

KEY = "239816685251645959"
BUILD = context.BUILD_SHA
IDENTITY = {
    "processId": 123, "processStartUtcTicks": 638000000000000001,
    "executableSha256": BUILD,
}
NATIVE = {"identity": {"host": "AMD-DESKTOP", "processId": 123,
                       "processStartUtcTicks": str(IDENTITY["processStartUtcTicks"]),
                       "executableSha256": BUILD},
          "selfKeyCandidate": KEY,
          "lastPositionCandidate": {"x": 10.0, "y": 20.0, "z": 30.0}}


def save_json(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    return replay.sha(path.read_bytes())


def fixture(root, *, second_clock=20, second_sequence=2, first_sequence=1, epoch=1):
    folder = root / "scan"
    folder.mkdir()
    request = {"marker": "RR2A1|", "target": deepcopy(IDENTITY)}
    request_sha = save_json(root / "request.json", request)
    candidates = []
    for i, (seq, clock) in enumerate(((first_sequence, 10), (second_sequence, second_clock)), 1):
        frame = {"schemaVersion": 1, "addonVersion": "0.1.0",
                 "sequence": seq, "epoch": epoch,
                 "clock": {"status": "ok", "value": clock},
                 "player": {"status": "ok", "value": "u" + format(int(KEY), "016X")},
                 "fields": {field: {"status": "ok", "value": value} for field, value
                            in (("coordX", 10.002), ("coordY", 20.003), ("coordZ", 30.004))}}
        raw = replay.PREFIX + json.dumps(frame).encode("ascii") + replay.SUFFIX
        chunk = raw + bytes(4096 - len(raw))
        address = 0x10000 * i
        snapshot = {"evidenceKind": "native-memory-snapshot/1", "status": "complete",
                    "identity": deepcopy(IDENTITY),
                    "chunks": [{"status": "success", "address": hex(address),
                                "requestedByteLength": 4096, "bytesRead": 4096,
                                "bytesBase64": base64.b64encode(chunk).decode("ascii"),
                                "bytesSha256": replay.sha(chunk)}]}
        filename = f"capture-{i:02d}.snapshot.json"
        checksum = save_json(folder / filename, snapshot)
        candidates.append({"status": "complete", "snapshotFile": filename,
                           "snapshotSha256": checksum, "markerAddress": hex(address)})
    index = {"schemaVersion": 1, "evidenceKind": "native-typed-inline-capture/1",
             "marker": "RR2A1|", "status": "partial",
             "request": request, "requestSha256": request_sha,
             "identity": deepcopy(IDENTITY), "candidates": candidates}
    path = folder / "index.json"
    save_json(path, index)
    return path


class ReplayTests(unittest.TestCase):
    def test_independent_lua_native_candidate_xyz(self):
        with tempfile.TemporaryDirectory() as d:
            index = fixture(Path(d))
            with patch.object(replay.native, "verified_bracket",
                              return_value=(NATIVE, "A" * 64, None, None)):
                report = replay.replay(index, Path(d) / "native-summary.json")
            self.assertEqual(report["luaFrameCount"], 2)
            self.assertEqual(report["luaEpochCandidate"], 1)
            self.assertEqual(report["lastSequence"], 2)
            self.assertAlmostEqual(report["maxAbsCoordinateDifferenceCandidate"]["z"], .004)
            self.assertEqual(report["status"], "candidate-only")
            self.assertIn("not nonce-bound", report["qualification"])

    def test_corrupt_snapshot_or_changed_native_epoch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            index = fixture(Path(d))
            candidate = index.parent / "capture-01.snapshot.json"
            candidate.write_bytes(candidate.read_bytes() + b" ")
            with patch.object(replay.native, "verified_bracket",
                              return_value=(NATIVE, "A" * 64, None, None)):
                with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                    replay.replay(index, Path(d) / "native-summary.json")
        with tempfile.TemporaryDirectory() as d:
            index = fixture(Path(d))
            other = deepcopy(NATIVE)
            other["identity"]["processStartUtcTicks"] = "1"
            with patch.object(replay.native, "verified_bracket",
                              return_value=(other, "A" * 64, None, None)):
                with self.assertRaisesRegex(ValueError, "process-identity-mismatch"):
                    replay.replay(index, Path(d) / "native-summary.json")

    def test_reject_nonadvancing_frames_and_never_overwrite_output(self):
        with tempfile.TemporaryDirectory() as d:
            index = fixture(Path(d), second_clock=10)
            with patch.object(replay.native, "verified_bracket",
                              return_value=(NATIVE, "A" * 64, None, None)):
                with self.assertRaisesRegex(ValueError, "nonadvancing"):
                    replay.replay(index, Path(d) / "native-summary.json")
            output = Path(d) / "existing.json"
            output.write_text("preserve", encoding="utf-8")
            self.assertEqual(replay.main(["--scan-index", str(index),
                                         "--native-bracket", str(Path(d) / "native"),
                                         "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
