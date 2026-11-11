"""Offline helper-receipt calibration: strict candidate-only import."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_move_key_calibration as calibrator


def receipt():
    return {
        "status": "input-inserted-game-response-unverified",
        "machine": "AMD-DESKTOP",
        "processId": 44888,
        "processStartUtcTicks": 639299470183328173,
        "executableSha256": "A" * 64,
        "keys": ["w"],
        "holdMilliseconds": 400,
        "windowsInputInserted": True,
        "windowsInputAttempted": True,
        "allRequestedKeyDownsInserted": True,
        "keyDownAttempts": 1,
        "keyDownInsertions": 1,
        "insertionUncertain": False,
        "boundedActionCompleted": True,
        "releaseSucceeded": True,
        "targetLost": False,
        "cancelled": False,
        "observedMilliseconds": 408.2,
        "gameResponseVerified": False,
        "error": None,
        "xyzFeedback": {
            "status": "candidate-native-xyz-feedback",
            "beforeXYZ": {
                "startedAtUtc": "2026-11-11T14:54:05.100Z",
                "completedAtUtc": "2026-11-11T14:54:05.110Z",
                "unitKey": "42", "x": 10.0, "y": 3.0, "z": 20.0
            },
            "afterXYZ": {
                "startedAtUtc": "2026-11-11T14:54:05.800Z",
                "completedAtUtc": "2026-11-11T14:54:05.810Z",
                "unitKey": "42", "x": 8.0, "y": 3.0, "z": 20.5
            },
            "deltaXYZ": {"x": -2.0, "y": 0.0, "z": 0.5},
            "planarDisplacementCandidate": math.hypot(2, .5),
            "captureGapSeconds": .69,
            "movementCandidate": True,
            "gameResponseVerified": False,
        },
    }


class HelperCalibrationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "helper.json"
        self.save(receipt())

    def save(self, report):
        self.path.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")

    def analyze(self):
        return calibrator.from_helper_receipt(self.path)

    def test_uses_observed_not_requested_hold_and_retains_provenance(self):
        result = self.analyze()
        self.assertEqual("offline-helper-move-calibration-candidate", result["status"])
        self.assertAlmostEqual(-2 / 408.2, result["dxPerMillisecondCandidate"])
        self.assertAlmostEqual(.5 / 408.2, result["dzPerMillisecondCandidate"])
        self.assertEqual(408, result["calibrationHoldMillisecondsRounded"])
        self.assertEqual(400, result["requestedHoldMilliseconds"])
        self.assertEqual(408.2, result["observedHoldMilliseconds"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["actionVerified"])
        self.assertFalse(result["headingQualified"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertRegex(result["sourceReceiptSha256"], r"^[A-F0-9]{64}$")

    def test_accepts_single_longer_q_e_w_s_candidate(self):
        for key in ("w", "s", "q", "e"):
            with self.subTest(key=key):
                report = receipt()
                report["keys"] = [key]
                report["holdMilliseconds"] = 500
                report["observedMilliseconds"] = 520
                self.save(report)
                result = self.analyze()
                self.assertEqual(key, result["key"])
                self.assertEqual(520, result["calibrationHoldMillisecondsRounded"])
                self.assertAlmostEqual(-2 / 520, result["dxPerMillisecondCandidate"])

    def test_rejects_unverified_delivery_release_or_nonmovement_key(self):
        base = receipt()
        for field, invalid in (
            ("windowsInputInserted", False), ("releaseSucceeded", False),
            ("boundedActionCompleted", False), ("insertionUncertain", True),
            ("targetLost", True), ("cancelled", True), ("gameResponseVerified", True),
            ("keyDownInsertions", 0)):
            with self.subTest(field=field):
                report = deepcopy(base)
                report[field] = invalid
                self.save(report)
                with self.assertRaisesRegex(ValueError, "delivery-or-release"):
                    self.analyze()
        for keys in (["a"], ["w", "q"], ["w", "w"], []):
            report = deepcopy(base)
            report["keys"] = keys
            self.save(report)
            with self.assertRaisesRegex(ValueError, "movement-key"):
                self.analyze()

    def test_rejects_native_owner_delta_and_time_mismatches(self):
        for update, expected in (
            (lambda r: r["xyzFeedback"]["afterXYZ"].update(unitKey="99"), "player-changed"),
            (lambda r: r["xyzFeedback"]["deltaXYZ"].update(x=12.0), "delta-mismatch"),
            (lambda r: r["xyzFeedback"].update(planarDisplacementCandidate=20), "distance-mismatch"),
            (lambda r: r["xyzFeedback"].update(captureGapSeconds=10), "gap-mismatch"),
            (lambda r: r["xyzFeedback"]["afterXYZ"].update(startedAtUtc="2026-11-11T14:54:05.105Z"),
             "capture-gap"),
        ):
            report = receipt()
            update(report)
            self.save(report)
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                self.analyze()

    def test_rejects_overlong_hold_implausible_motion_and_bad_identity(self):
        base = receipt()
        for field, value, expected in (
            ("observedMilliseconds", 1001, "observed-hold"),
            ("observedMilliseconds", 501, "observed-hold"),
            ("processStartUtcTicks", 0, "identity"),
            ("executableSha256", "not-a-sha", "identity"),
            ("processId", -1, "identity"),
        ):
            report = deepcopy(base)
            report[field] = value
            self.save(report)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, expected):
                self.analyze()
        report = receipt()
        report["xyzFeedback"]["afterXYZ"]["x"] = -20
        report["xyzFeedback"]["deltaXYZ"]["x"] = -30
        report["xyzFeedback"]["planarDisplacementCandidate"] = math.hypot(30, .5)
        self.save(report)
        with self.assertRaisesRegex(ValueError, "implausible"):
            self.analyze()

    def test_refuses_duplicate_json_and_does_not_overwrite_result(self):
        self.path.write_text('{"status":"ok","status":"ok"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate-helper-receipt-field"):
            self.analyze()
        self.save(receipt())
        dest = self.root / "calibration.json"
        args = ["--receipt", str(self.path), "--out", str(dest)]
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(0, calibrator.main(args))
        self.assertEqual(json.loads(stream.getvalue()),
                         json.loads(dest.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(2, calibrator.main(args))
        self.assertEqual("blocked", json.loads(stream.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
