"""Host-only tests for near-time typed/native displacement consistency."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts import review_native_motion_pair as motion

ROOT = Path(__file__).resolve().parents[1]
GAME_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
TICKS = 639284177321390013


class MotionPairTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = {
            "processId": 6940,
            "processStartUtcTicks": TICKS,
            "executableSha256": GAME_SHA,
        }
        self.request = {
            "schemaVersion": 1,
            "evidenceKind": "native-pointer-follow-request/1",
            "target": self.target,
            "rootRva": "0x32E0200",
            "offsets": ["0x0"],
            "terminalByteLength": 816,
            "maxDurationMilliseconds": 5000,
        }
        self.req = self.root / "request.json"
        self.src = self.root / "source.json"
        self.a = self.root / "native-a.json"
        self.b = self.root / "native-b.json"
        self.write(self.req, self.request)
        self.source = {
            "schemaVersion": 1,
            "evidenceKind": "typed-wire-snapshot-inspection/1",
            "status": "advanced-in-covered-scope",
            "identity": dict(self.target),
            "source": {
                "before": {
                    "status": "complete",
                    "snapshotSha256": "A" * 64,
                    "startedAtUtc": "2026-10-25T00:29:59Z",
                    "completedAtUtc": "2026-10-25T00:30:00Z",
                },
                "after": {
                    "status": "complete",
                    "snapshotSha256": "B" * 64,
                    "startedAtUtc": "2026-10-25T00:34:59Z",
                    "completedAtUtc": "2026-10-25T00:35:00Z",
                },
            },
            "selected": {
                "before": {
                    "playerUnitId": "u035400012FA2D207",
                    "wireSha256": "C" * 64,
                    "sequence": 100,
                    "frameTime": 200.5,
                    "xyz": {"x": 100.001, "y": 200.002, "z": 300.0},
                },
                "after": {
                    "playerUnitId": "u035400012FA2D207",
                    "wireSha256": "D" * 64,
                    "sequence": 125,
                    "frameTime": 212.5,
                    "xyz": {"x": 101.202, "y": 200.002, "z": 300.0},
                },
            },
        }
        self.write(self.src, self.source)
        self.before = self.make_native("2026-10-25T00:30:20Z", (100.0, 200.0, 300.0))
        self.after = self.make_native("2026-10-25T00:35:20Z", (101.2, 200.0, 300.0))
        self.write(self.a, self.before)
        self.write(self.b, self.after)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")

    def make_native(self, at, coords):
        blob = bytearray(816)
        struct.pack_into("<fff", blob, 0x320, *coords)
        owner = 0x211D37C0010
        identity = {
            **self.target,
            "moduleBaseAddress": 0x7FF6EBDA0000,
            "moduleSize": 62611456,
            "executablePath": r"C:\RIFT_TRANSFER\RIFT\rift_x64.exe",
        }
        return {
            "schemaVersion": 1,
            "evidenceKind": "native-pointer-follow/1",
            "requestSha256": hashlib.sha256(self.req.read_bytes()).hexdigest().upper(),
            "completedAtUtc": at,
            "chain": {"rootRva": 0x32E0200, "offsets": [0]},
            "resolution": {
                "status": "complete",
                "reason": None,
                "expectedIdentity": identity,
                "observedIdentity": dict(identity),
                "hops": [{
                    "level": 1,
                    "pointerAddress": identity["moduleBaseAddress"] + 0x32E0200,
                    "pointerBytes": base64.b64encode(struct.pack("<Q", owner)).decode(),
                    "pointerValue": owner,
                    "offset": 0,
                    "resolvedAddress": owner,
                }],
                "terminalAddress": owner,
                "terminalRead": {
                    "status": "success",
                    "bytes": base64.b64encode(blob).decode(),
                },
                "failedRead": None,
                "failedReadAddress": None,
            },
        }

    def inspect(self, **options):
        return motion.review(self.a, self.b, self.req, self.src,
                             hashlib.sha256(self.src.read_bytes()).hexdigest().upper(),
                             **options)

    def test_near_time_consistent_displacement_is_candidate_only(self):
        result = self.inspect()
        self.assertEqual(result["status"], "candidate-motion-consistent")
        self.assertEqual(result["qualification"],
                         "candidate-only-no-stimulus-or-clock-skew-proof")
        self.assertEqual(result["playerUnitId"], "u035400012FA2D207")
        self.assertAlmostEqual(result["nativeDisplacement"]["x"], 1.2, places=4)
        self.assertAlmostEqual(result["typedDisplacement"]["x"], 1.201, places=3)
        self.assertEqual(result["nativeMinusTypedSampleTimeSeconds"],
                         {"before": 20.0, "after": 20.0})
        self.assertTrue(all(x["allAxesWithinTolerance"]
                            for x in result["endpointAgreement"].values()))
        self.assertTrue(any("correlation is not causation" in line
                            for line in result["limitations"]))

    def test_stationary_source_cannot_qualify_motion(self):
        self.source["selected"]["after"]["xyz"]["x"] = 100.001
        self.write(self.src, self.source)
        self.assertEqual(self.inspect()["status"], "insufficient-source-motion")

    def test_lua_moves_native_does_not(self):
        self.after = self.make_native("2026-10-25T00:35:20Z", (100.0, 200.0, 300.0))
        self.write(self.b, self.after)
        result = self.inspect()
        self.assertEqual(result["status"], "candidate-motion-disagrees")
        self.assertFalse(result["endpointAgreement"]["after"]["allAxesWithinTolerance"])

    def test_opposite_native_direction_is_disagreement_not_promotion(self):
        self.write(self.b, self.make_native("2026-10-25T00:35:20Z", (98.0, 200.0, 300.0)))
        self.assertEqual(self.inspect()["status"], "candidate-motion-disagrees")

    def test_expired_source_to_native_lag_blocks(self):
        self.write(self.a, self.make_native("2026-10-25T00:33:21Z", (100.0, 200.0, 300.0)))
        with self.assertRaisesRegex(motion.native.EvidenceError, "lag"):
            self.inspect()

    def test_fractional_seconds_above_limit_do_not_round_into_admission(self):
        # +180.0004 s rounds to +180.000 in the displayed millisecond result.
        self.write(self.a, self.make_native("2026-10-25T00:33:00.000400Z", (100.0, 200.0, 300.0)))
        with self.assertRaisesRegex(motion.native.EvidenceError, "lag"):
            self.inspect()

    def test_crossed_before_after_time_intervals_block(self):
        self.write(self.a, self.make_native("2026-10-25T00:35:01Z", (100.0, 200.0, 300.0)))
        with self.assertRaisesRegex(motion.native.EvidenceError, "overlap"):
            self.inspect()

    def test_reversed_native_times_block(self):
        self.write(self.b, self.make_native("2026-10-25T00:29:59Z", (101.2, 200.0, 300.0)))
        with self.assertRaisesRegex(motion.native.EvidenceError, "chronological"):
            self.inspect()

    def test_typed_player_identity_and_advancing_wire_required(self):
        self.source["selected"]["after"]["playerUnitId"] = "uOTHER"
        self.write(self.src, self.source)
        with self.assertRaisesRegex(motion.native.EvidenceError, "player identity"):
            self.inspect()
        self.source["selected"]["after"]["playerUnitId"] = "u035400012FA2D207"
        self.source["selected"]["after"]["wireSha256"] = "C" * 64
        self.write(self.src, self.source)
        with self.assertRaisesRegex(motion.native.EvidenceError, "advance"):
            self.inspect()

    def test_source_capture_must_be_complete_and_ordered(self):
        self.source["source"]["after"]["status"] = "partial"
        self.write(self.src, self.source)
        with self.assertRaisesRegex(motion.native.EvidenceError, "incomplete"):
            self.inspect()
        self.source["source"]["after"]["status"] = "complete"
        self.source["source"]["after"]["startedAtUtc"] = "2026-10-25T00:35:01Z"
        self.write(self.src, self.source)
        with self.assertRaisesRegex(motion.native.EvidenceError, "reversed times"):
            self.inspect()

    def test_rejects_wrong_epoch_invalid_native_pointer_or_duplicate_bytes(self):
        self.after["resolution"]["observedIdentity"]["processStartUtcTicks"] -= 1
        self.write(self.b, self.after)
        with self.assertRaisesRegex(motion.native.EvidenceError, "epoch"):
            self.inspect()
        self.after["resolution"]["observedIdentity"]["processStartUtcTicks"] = TICKS
        self.after["resolution"]["hops"][0]["pointerValue"] += 8
        self.write(self.b, self.after)
        with self.assertRaisesRegex(motion.native.EvidenceError, "pointer"):
            self.inspect()
        self.a.write_bytes(self.b.read_bytes())
        with self.assertRaises(motion.native.EvidenceError):
            self.inspect()

    def test_rejects_changed_typed_source_digest(self):
        with self.assertRaisesRegex(motion.native.EvidenceError, "SHA-256 pin"):
            motion.review(self.a, self.b, self.req, self.src, "F" * 64)

    def test_rejects_unbounded_thresholds(self):
        for kwargs in ({"tolerance": 0}, {"tolerance": 0.5},
                       {"max_pair_lag_seconds": 301},
                       {"max_pair_lag_seconds": float("nan")},
                       {"min_movement_units": 0.01},
                       {"min_movement_units": 11}):
            with self.subTest(kwargs=kwargs), self.assertRaises(motion.native.EvidenceError):
                self.inspect(**kwargs)

    def test_cli_deterministic_no_overwrite_and_direct_entry(self):
        a = self.root / "review-a.json"
        b = self.root / "review-b.json"
        common = ["--native-before", str(self.a), "--native-after", str(self.b),
                  "--request", str(self.req), "--typed-comparison", str(self.src),
                  "--typed-sha256", hashlib.sha256(self.src.read_bytes()).hexdigest().upper()]
        self.assertEqual(motion.main(common + ["--output", str(a)]), 0)
        self.assertEqual(motion.main(common + ["--output", str(b)]), 0)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(motion.main(common + ["--output", str(a)]), 2)
        self.assertEqual(json.loads(a.read_bytes())["status"], "candidate-motion-consistent")

    def test_direct_script_entry_resolves_repo_imports(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "review_native_motion_pair.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--typed-comparison", completed.stdout)

    def test_duplicate_json_is_rejected(self):
        self.src.write_text('{"status":"advanced","status":"other"}', encoding="utf-8")
        with self.assertRaisesRegex(motion.native.EvidenceError, "duplicate JSON"):
            self.inspect()


ACTUAL = ROOT / "artifacts" / "update-recovery-20261023-01"
ACTUAL_REPORT = ACTUAL / "rr2-v16-native-pointer-reviewed-live-oct24-01"
ACTUAL_TYPED = ACTUAL / "rr2-inline-oct24-01-recovered" / "pair-a1-b2-typed-comparison.json"
ACTUAL_REQUEST = ACTUAL / "rr2-v16-pointer-a-oct24-01" / "request.json"


class ActualOldEvidenceCannotClaimMotion(unittest.TestCase):
    @unittest.skipUnless(
        all(path.is_file() for path in (
            ACTUAL_REPORT / "rr2-v16ptr-a-report.json",
            ACTUAL_REPORT / "rr2-v16ptr-b-report.json",
            ACTUAL_TYPED,
            ACTUAL_REQUEST,
        )), "real ignored V16 guest originals required")
    def test_old_stationary_lua_source_cannot_form_before_after_motion_pair(self):
        # Both real native reports followed both typed captures; these are not
        # interleaved before/after clusters, independent of the >2-hour lag.
        with self.assertRaisesRegex(motion.native.EvidenceError, "overlap"):
            motion.review(
                ACTUAL_REPORT / "rr2-v16ptr-a-report.json",
                ACTUAL_REPORT / "rr2-v16ptr-b-report.json",
                ACTUAL_REQUEST, ACTUAL_TYPED,
                "CF353BD49E6D5D7FFC810C6C8C3AF8C049D26B10F2F9700257DEBBC9486274D5")


if __name__ == "__main__":
    unittest.main()
