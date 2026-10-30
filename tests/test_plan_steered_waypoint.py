import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts.plan_steered_waypoint import (
    SteeringPlanError, measure_turn, next_step, signed_angle,
)


TARGET = {"processId": 11, "processStartUtcTicks": 22,
          "executableSha256": "A" * 64}


def sample(x, y, z, sequence, *, nonce="nonce"):
    return {"xyz": {"x": x, "y": y, "z": z}, "outerSequence": sequence,
            "addonSequence": sequence, "addonClock": float(sequence), "lab": "lab1",
            "player": "player", "addonEpoch": 1, "sourceAddress": "192.168.56.128",
            "readerProcessId": 33, "readerProcessStartUtcTicks": 44,
            "readerExecutableSha256": "B" * 64, "readerInstance": "reader",
            "readerNonce": nonce, "receiverInstance": "receiver", "target": TARGET}


def calibration(start, end, first_sequence, step, *, nonce="nonce"):
    first = sample(*start, first_sequence, nonce=nonce)
    last = sample(*end, first_sequence + 1, nonce=nonce)
    return {"success": True, "mode": "calibration", "status": "calibrated",
            "movementDimension": "1d", "calibrationKeys": ["w"],
            "calibrationIdentity": {key: first[key] for key in (
                "lab", "player", "addonEpoch", "sourceAddress", "readerProcessId",
                "readerProcessStartUtcTicks", "readerExecutableSha256", "readerInstance",
                "readerNonce", "receiverInstance", "target")},
            "calibrationEnd": last, "normalizedCross": None,
            "calibrations": {"w": {"key": "w", "dx_per_ms": step[0] / 100,
                "dz_per_ms": step[1] / 100, "calibration_hold_ms": 100,
                "horizontal_displacement": math.hypot(*step), "vertical_displacement": 0}},
            "samples": [first, last]}


def turn(position, first_sequence, key="d", hold=50, *, shift=(0, 0)):
    return {"success": True, "mode": "turn", "status": "turn-input-completed",
            "headingClaimed": False, "turnKey": key, "holdMs": hold,
            "samples": [sample(*position, first_sequence),
                        sample(position[0] + shift[0], position[1], position[2] + shift[1],
                               first_sequence + 1)]}


class SteeringPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_signed_angle_preserves_direction_and_wraparound(self):
        self.assertAlmostEqual(signed_angle((1, 0), (0, 1)), math.pi / 2)
        self.assertAlmostEqual(signed_angle((1, 0), (0, -1)), -math.pi / 2)
        value = signed_angle((-1, .001), (-1, -.001))
        self.assertAlmostEqual(value, .002, places=5)

    def test_measure_turn_derives_signed_rate_from_w_vectors(self):
        before = self.write("before.json", calibration((0, 0, 0), (1, 0, 0), 1, (1, 0)))
        turning = self.write("turn.json", turn((1, 0, 0), 3, "d", 50))
        after = self.write("after.json", calibration((1, 0, 0), (1, 0, 1), 5, (0, 1)))
        result = measure_turn(before, turning, after)
        self.assertEqual(result["key"], "d")
        self.assertAlmostEqual(result["signedRadians"], math.pi / 2)
        self.assertAlmostEqual(result["signedRadiansPerMillisecond"], math.pi / 100)

    def test_measure_turn_rejects_translation_or_stale_producer(self):
        before_value = calibration((0, 0, 0), (1, 0, 0), 1, (1, 0))
        before = self.write("before.json", before_value)
        turning_value = turn((1, 0, 0), 3, shift=(.051, 0))
        turning = self.write("turn.json", turning_value)
        after = self.write("after.json", calibration((1.051, 0, 0), (1.051, 0, 1), 5, (0, 1)))
        with self.assertRaisesRegex(SteeringPlanError, "translated too far"):
            measure_turn(before, turning, after)
        turning_value = turn((1, 0, 0), 3)
        turning_value["samples"][0]["addonClock"] = 2.0
        turning = self.write("turn-stale.json", turning_value)
        with self.assertRaisesRegex(SteeringPlanError, "addonClock"):
            measure_turn(before, turning, after)

    def test_measure_turn_rejects_mixed_identity_and_tiny_angle(self):
        before = self.write("before.json", calibration((0, 0, 0), (1, 0, 0), 1, (1, 0)))
        turning = self.write("turn.json", turn((1, 0, 0), 3))
        foreign = calibration((1, 0, 0), (2, 0, 0), 5, (1, 0), nonce="other")
        after = self.write("foreign.json", foreign)
        with self.assertRaisesRegex(SteeringPlanError, "identities differ"):
            measure_turn(before, turning, after)
        tiny = self.write("tiny.json", calibration((1, 0, 0), (2, 0, .001), 5, (1, .001)))
        with self.assertRaisesRegex(SteeringPlanError, "measurable threshold"):
            measure_turn(before, turning, tiny)

    def test_calibration_vector_must_match_observed_sample_delta(self):
        value = calibration((0, 0, 0), (1, 0, 0), 1, (1, 0))
        value["calibrations"]["w"]["dx_per_ms"] = .009
        current = self.write("mismatch.json", value)
        with self.assertRaisesRegex(SteeringPlanError, "differs from its sample"):
            next_step(current, (3, 0), [])

    def turn_measurement(self, name, key, rate, identity):
        return self.write(name, {"schemaVersion": 1,
            "evidenceKind": "provisional-session-turn-calibration/1", "status": "provisional",
            "key": key, "signedRadiansPerMillisecond": rate, "identity": identity})

    def test_next_emits_exact_chosen_coordinate_forward_step(self):
        current = self.write("current.json", calibration((0, 4, 0), (1, 4, 0), 1, (1, 0)))
        result = next_step(current, (3, .03), [])
        self.assertEqual(result["decision"], "forward")
        self.assertEqual(result["targetKind"], "chosen-planar-coordinate")
        self.assertEqual(result["target"], {"x": 3.0, "y": 4.0, "z": .03})
        self.assertEqual(result["planarGoal"], {"x": 3.0, "z": .03})
        self.assertEqual(result["arrivalKind"], "planar-xz")
        self.assertEqual(result["runnerArgumentFragment"][-4:],
                         ["--goal", "3.0", "4.0", "0.03"])

    def test_next_splits_distant_aligned_goal_into_forward_segment(self):
        current = self.write("current.json", calibration((0, 0, 0), (1, 0, 0), 1, (1, 0)))
        result = next_step(current, (6, 0), [])
        self.assertEqual(result["decision"], "forward")
        self.assertEqual(result["targetKind"], "intermediate-forward-segment")
        self.assertEqual(result["target"], {"x": 3.0, "y": 0.0, "z": 0.0})

    def test_post_turn_forward_pins_turn_result_in_runner_fragment(self):
        turning = self.write("turn.json", turn((1, 0, 0), 3, "d", 40))
        current = self.write("current.json", calibration((1, 0, 0), (2, 0, 0), 5, (1, 0)))
        result = next_step(current, (4, 0), [], turning)
        self.assertEqual(result["decision"], "forward")
        self.assertIn("afterTurnResult", result)
        index = result["runnerArgumentFragment"].index("--after-turn-result")
        self.assertEqual(result["runnerArgumentFragment"][index + 1],
                         str(turning.resolve()))
        self.assertEqual(len(result["afterTurnResult"]["sha256"]), 64)

    def test_post_turn_pin_rejects_stale_or_foreign_result(self):
        current = self.write("current.json", calibration((1, 0, 0), (2, 0, 0), 5, (1, 0)))
        stale = turn((1, 0, 0), 3)
        stale["samples"][-1]["addonClock"] = 5.0
        stale_path = self.write("stale.json", stale)
        with self.assertRaisesRegex(SteeringPlanError, "addonClock"):
            next_step(current, (4, 0), [], stale_path)
        foreign = turn((1, 0, 0), 3)
        foreign["samples"][-1]["readerNonce"] = "other"
        foreign_path = self.write("foreign-turn.json", foreign)
        with self.assertRaisesRegex(SteeringPlanError, "another identity"):
            next_step(current, (4, 0), [], foreign_path)

    def test_next_selects_only_measured_turn_direction_and_clamps_hold(self):
        value = calibration((0, 0, 0), (1, 0, 0), 1, (1, 0))
        current = self.write("current.json", value)
        clockwise = self.turn_measurement("d.json", "d", .005, value["calibrationIdentity"])
        result = next_step(current, (1, 5), [clockwise])
        self.assertEqual(result["decision"], "turn")
        self.assertEqual(result["key"], "d")
        self.assertEqual(result["holdMilliseconds"], 100)
        self.assertEqual(result["runnerArgumentFragment"],
                         ["prepare", "--mode", "turn", "--keys", "d",
                          "--turn-hold-ms", "100"])
        result = next_step(current, (1, -5), [clockwise])
        self.assertEqual(result["decision"], "blocked")
        self.assertEqual(result["reason"], "no-measured-turn-direction-reduces-error")

    def test_next_rejects_foreign_turn_measurement(self):
        value = calibration((0, 0, 0), (1, 0, 0), 1, (1, 0))
        current = self.write("current.json", value)
        foreign_identity = dict(value["calibrationIdentity"], readerNonce="other")
        measured = self.turn_measurement("foreign.json", "d", .01, foreign_identity)
        with self.assertRaisesRegex(SteeringPlanError, "another identity"):
            next_step(current, (1, 5), [measured])

    def test_next_blocks_short_or_cross_track_goal_without_turn_evidence(self):
        current = self.write("current.json", calibration((0, 0, 0), (1, 0, 0), 1, (1, 0)))
        short = next_step(current, (1.5, 0), [])
        self.assertEqual(short["reason"], "remaining-forward-distance-outside-1d-contract")
        off_axis = next_step(current, (3, .06), [])
        self.assertEqual(off_axis["reason"], "no-measured-turn-direction-reduces-error")

    def test_next_reports_planar_arrival_despite_y_difference(self):
        current = self.write("current.json", calibration((0, 5, 0), (1, 5, 0), 1, (1, 0)))
        result = next_step(current, (1.2, .1), [])
        self.assertEqual(result["decision"], "arrived")
        self.assertEqual(result["arrivalKind"], "planar-xz")


if __name__ == "__main__":
    unittest.main()
