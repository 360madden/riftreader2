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




def timed_receipt():
    result = receipt()
    result["inputCallTiming"] = {
        "startedAtUtc": "2026-11-11T14:54:05.200Z",
        "completedAtUtc": "2026-11-11T14:54:05.620Z",
        "monotonicElapsedMilliseconds": 420,
        "executorObservedMilliseconds": 408.2,
        "utcOrderValid": True,
        "wallClockConsistentWithMonotonic": True,
        "exactKeyDownUpTimesKnown": False,
    }
    result["keySendEvents"] = [
        {"key": "w", "phase": "key-down",
         "callStartedAtUtc": "2026-11-11T14:54:05.205Z",
         "callCompletedAtUtc": "2026-11-11T14:54:05.206Z",
         "sendCallElapsedMilliseconds": 1.0, "inserted": True},
        {"key": "w", "phase": "key-up",
         "callStartedAtUtc": "2026-11-11T14:54:05.605Z",
         "callCompletedAtUtc": "2026-11-11T14:54:05.606Z",
         "sendCallElapsedMilliseconds": 1.0, "inserted": True},
    ]
    result["keyHoldWindows"] = [{
        "key": "w",
        "status": "candidate-sendinput-hold-bounds",
        "minimumMillisecondsCandidate": 399,
        "maximumMillisecondsCandidate": 401,
        "midpointMillisecondsCandidate": 400,
        "downCallStartedAtUtc": "2026-11-11T14:54:05.205Z",
        "downCallCompletedAtUtc": "2026-11-11T14:54:05.206Z",
        "upCallStartedAtUtc": "2026-11-11T14:54:05.605Z",
        "upCallCompletedAtUtc": "2026-11-11T14:54:05.606Z",
        "exactKeyDownUpTimesKnown": False,
        "gameResponseVerified": False,
    }]
    return result

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

    def test_forward_pose_comparison_checks_angle_owner_and_order(self):
        from tests.test_analyze_physical_turn_pair import matrix
        r = timed_receipt()
        bearing = math.degrees(math.atan2(-2, .5))
        row = {"identity": {k: r[k] for k in ("processId", "processStartUtcTicks", "executableSha256")},
               "playerKeyDecimal": "42", "playerEntityDecimal": "100",
               "actorComponentDecimal": "200", "positionComponentDecimal": "300",
               "actorMatrix": matrix(-bearing, 0x398)}
        def sample(stamp):
            return dict(row, startedAtUtc=stamp, completedAtUtc=stamp)
        r["poseFeedback"] = {"status": "candidate-native-actor-pose-feedback",
                             "beforePose": sample("2026-11-11T14:54:05.150Z"),
                             "afterPose": sample("2026-11-11T14:54:05.820Z")}
        self.save(r)
        result = self.analyze()["forwardPoseComparisonCandidate"]
        self.assertAlmostEqual(result["travelDegreesFromPositiveZTowardPositiveX"], bearing)
        self.assertAlmostEqual(result["travelMinusNegatedBeforeActorDegrees"], 0, places=4)
        changed = deepcopy(r)
        endpoint = changed["xyzFeedback"]["afterXYZ"]
        changed["poseFeedback"]["afterPose"]["positionBracketCandidate"] = {
            "playerKeyDecimal": "42", "before": endpoint, "after": dict(endpoint, z=endpoint["z"] + 1)}
        self.save(changed)
        result = self.analyze()
        self.assertNotIn("forwardPoseComparisonCandidate", result)
        self.assertGreater(result["horizontalDisplacementCandidate"], 0)
        for field, value, reason in (("playerKeyDecimal", "43", "owner-mismatch"),
                                     ("startedAtUtc", "2026-11-11T14:54:05.600Z", "timing-mismatch")):
            changed = deepcopy(r)
            changed["poseFeedback"]["afterPose"][field] = value
            self.save(changed)
            with self.assertRaisesRegex(ValueError, reason):
                self.analyze()

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

    def test_new_receipt_uses_key_down_up_window_instead_of_executor_overhead(self):
        self.save(timed_receipt())
        result = self.analyze()
        self.assertEqual(result["holdMeasurementSource"],
                         "sendinput-keydown-keyup-bounded-midpoint")
        self.assertEqual(result["holdBoundsCandidate"],
                         {"minimumMillisecondsCandidate": 399,
                          "maximumMillisecondsCandidate": 401})
        self.assertEqual(400, result["observedHoldMilliseconds"])
        self.assertEqual(408.2, result["executorObservedMilliseconds"])
        self.assertAlmostEqual(result["dxPerMillisecondCandidate"], -2 / 400)
        self.assertAlmostEqual(result["dzPerMillisecondCandidate"], .5 / 400)
        self.assertEqual(result["calibrationHoldMillisecondsRounded"], 400)
        self.assertFalse(result["navigationEligible"] if "navigationEligible" in result
                         else result["movementEligible"])

    def test_timed_receipt_fails_closed_on_partial_or_contradictory_timings(self):
        cases = [
            (lambda r: r.pop("keySendEvents"), "timing-incomplete"),
            (lambda r: r["inputCallTiming"].update(wallClockConsistentWithMonotonic=False),
             "timing-invalid"),
            (lambda r: r["inputCallTiming"].update(executorObservedMilliseconds=100),
             "timing-invalid"),
            (lambda r: r["keySendEvents"][1].update(inserted=False), "event-invalid"),
            (lambda r: r["keySendEvents"][1].update(key="q"), "event-invalid"),
            (lambda r: r["keySendEvents"][1].update(phase="key-down"), "event-invalid"),
            (lambda r: r["keySendEvents"][1].update(
                callStartedAtUtc="2026-11-11T14:54:05.204Z",
                callCompletedAtUtc="2026-11-11T14:54:05.205Z"), "event-order-invalid"),
            (lambda r: r["keyHoldWindows"][0].update(
                status="unavailable-keyup-not-confirmed"), "window-invalid"),
            (lambda r: r["keyHoldWindows"][0].update(
                midpointMillisecondsCandidate=410), "window-invalid"),
            (lambda r: r["keyHoldWindows"][0].update(
                upCallCompletedAtUtc="2026-11-11T14:54:05.611Z"), "window-invalid"),
            (lambda r: r["keyHoldWindows"][0].update(
                maximumMillisecondsCandidate=900), "window-invalid"),
            (lambda r: r["inputCallTiming"].update(
                startedAtUtc="2026-11-11T14:54:05.109Z",
                monotonicElapsedMilliseconds=511), "capture-order-invalid"),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                report = timed_receipt()
                mutate(report)
                self.save(report)
                with self.assertRaisesRegex(ValueError, expected):
                    self.analyze()

    def test_previous_generation_envelope_only_receipt_remains_readable(self):
        report = timed_receipt()
        report.pop("keySendEvents")
        report.pop("keyHoldWindows")
        self.save(report)
        imported = self.analyze()
        self.assertEqual("executor-total-duration-with-call-envelope",
                         imported["holdMeasurementSource"])
        self.assertIsNone(imported["holdBoundsCandidate"])
        self.assertEqual(408.2, imported["observedHoldMilliseconds"])
        self.assertAlmostEqual(-2/408.2, imported["dxPerMillisecondCandidate"])
        self.assertFalse(imported["movementEligible"])

    def test_legacy_receipt_still_uses_executor_elapsed_with_explicit_label(self):
        result = self.analyze()
        self.assertEqual("executor-total-duration-legacy", result["holdMeasurementSource"])
        self.assertIsNone(result["holdBoundsCandidate"])
        self.assertEqual(408.2, result["observedHoldMilliseconds"])
        self.assertEqual(408.2, result["executorObservedMilliseconds"])

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

    def test_short_decimal_coordinates_recover_native_distance(self):
        report = receipt()
        feedback = report["xyzFeedback"]
        feedback["beforeXYZ"].update(x=7423.489, z=2944.0254)
        feedback["afterXYZ"].update(x=7424.4316, z=2945.3054)
        feedback["deltaXYZ"].update(x=0.94287109375, z=1.280029296875)
        feedback["planarDisplacementCandidate"] = 1.5898053026353975
        self.save(report)
        self.assertAlmostEqual(feedback["planarDisplacementCandidate"],
                               self.analyze()["horizontalDisplacementCandidate"], places=12)

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
