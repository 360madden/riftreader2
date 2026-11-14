"""Focused offline tests for continuous-route camera acceptance arithmetic."""
from __future__ import annotations

import contextlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import analyze_follow_camera as camera


BASE = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def stamp(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def key(name, phase, seconds, *, inserted=True):
    return {
        "key": name, "phase": phase,
        "callStartedAtUtc": stamp(seconds),
        "callCompletedAtUtc": stamp(seconds + .001),
        "inserted": inserted,
    }


def point(seconds, body, optical=None, pitch=None, status=None):
    return {
        "observedAtUtc": stamp(seconds), "bearing": body,
        "opticalCameraBearingDegreesCandidate": optical,
        "opticalCameraPitchDegreesCandidate": pitch,
        "opticalCameraStatus": status,
    }


def leg(path=None, events=None, name="P1"):
    return {"name": name, "nativeReceipt": {
        "status": "arrived", "path": path or [], "keySendEvents": events or []}}


class FollowCameraAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, value, name="route.json"):
        path = self.root / name
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
        return path

    def test_wrap_steering_alternations_reversal_and_gaps(self):
        route = {"legs": [leg(
            [point(1.01, 358, 358, -5, "available-candidate"),
             point(1.04, 359, 359, -4, "available-candidate"),
             point(1.08, 1, 1, -3, "available-candidate"),
             point(1.22, 4, 4, -2, "available-candidate"),
             point(1.27, 1, 1, -1, "available-candidate"),
             point(1.32, 3.5, 3.5, 0, "available-candidate")],
            [key("w", "key-down", 1), key("a", "key-down", 1.02),
             key("a", "key-up", 1.03), key("d", "key-down", 1.05),
             key("d", "key-up", 1.06), key("a", "key-down", 1.1),
             key("a", "key-up", 1.11), key("w", "key-up", 1.4)])]}
        output = camera.analyze(self.save(route))
        self.assertEqual("candidate-only", output["status"])
        self.assertFalse(output["opticalYawQualified"])
        interval = output["legs"][0]["forwardIntervals"][0]
        self.assertEqual(["a", "d", "a"], interval["travelSteeringSequence"])
        self.assertEqual(2, interval["travelSteeringAlternations"])
        self.assertAlmostEqual(6, interval["bodyYaw"]["unwrappedRangeDegreesCandidate"])
        self.assertEqual(2, interval["bodyYaw"]["significantReversalsCandidate"])
        self.assertGreater(interval["bodyYaw"]["totalVariationExcessDegreesCandidate"], 0)
        self.assertEqual(1, interval["opticalCameraYaw"]["gapsOverThreshold"])
        self.assertEqual(6, output["opticalCameraSampleCount"])

    def test_subthreshold_jitter_is_not_a_significant_reversal(self):
        values = camera._angle_metrics([0, 1, .1, 1.9, .2, 1.8], reversal_degrees=2)
        self.assertEqual(0, values["significantReversalsCandidate"])
        values = camera._angle_metrics([0, 3, .5, 3], reversal_degrees=2)
        self.assertEqual(2, values["significantReversalsCandidate"])

    def test_missing_camera_is_unavailable_not_pass(self):
        route = {"legs": [leg(
            [point(1.1, 10), point(1.2, 11)],
            [key("w", "key-down", 1), key("w", "key-up", 1.3)])]}
        output = camera.analyze(self.save(route))
        interval = output["legs"][0]["forwardIntervals"][0]
        self.assertEqual("unavailable", output["opticalCameraAvailability"])
        self.assertEqual("unavailable", interval["opticalCameraYaw"]["availability"])
        self.assertEqual(0, interval["opticalCameraYaw"]["sampleCount"])
        self.assertFalse(interval["opticalCameraYaw"]["opticalYawQualified"])

    def test_only_steering_during_forward_hold_is_counted(self):
        events = [key("a", "key-down", .5), key("a", "key-up", .6),
                  key("w", "key-down", 1), key("d", "key-down", 1.1),
                  key("d", "key-up", 1.2), key("w", "key-up", 1.3),
                  key("a", "key-down", 1.4), key("a", "key-up", 1.5)]
        output = camera.analyze(self.save({"legs": [leg([], events)]}))
        self.assertEqual(1, output["legs"][0]["travelSteeringKeyDownCount"])
        self.assertEqual(["d"], output["legs"][0]["forwardIntervals"][0]
                         ["travelSteeringSequence"])

    def test_multiple_legs_and_forward_intervals_remain_separate(self):
        events = [key("w", "key-down", 1), key("w", "key-up", 1.2),
                  key("w", "key-down", 2), key("w", "key-up", 2.2)]
        source = {"legs": [leg([], events, "A"), leg([], [], "B")]}
        output = camera.analyze(self.save(source))
        self.assertEqual(2, output["legCount"])
        self.assertEqual(2, output["forwardIntervalCount"])
        self.assertEqual(0, output["legs"][1]["forwardIntervalCount"])

    def test_partial_camera_sample_fails_closed(self):
        source = {"legs": [leg(
            [point(1.1, 10, 20, None, "available-candidate")],
            [key("w", "key-down", 1), key("w", "key-up", 1.2)])]}
        with self.assertRaisesRegex(ValueError, "partial-optical-camera-sample"):
            camera.analyze(self.save(source))

        source["legs"][0]["nativeReceipt"]["path"][0].update({
            "opticalCameraPitchDegreesCandidate": 2,
            "opticalCameraStatus": "unavailable",
        })
        with self.assertRaisesRegex(ValueError, "unavailable-optical-camera-values"):
            camera.analyze(self.save(source, "bad-status.json"))

    def test_unpaired_forward_key_and_duplicate_json_are_blocked(self):
        source = {"legs": [leg([], [key("w", "key-down", 1)])]}
        with self.assertRaisesRegex(ValueError, "forward-key-release-missing"):
            camera.analyze(self.save(source))
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"legs":[],"legs":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
            camera.analyze(duplicate)

    def test_cli_json_and_clean_missing_reason(self):
        route = self.save({"legs": [leg()]})
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            code = camera.main([str(route)])
        self.assertEqual(0, code)
        self.assertEqual("candidate-only", json.loads(buffer.getvalue())["status"])
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            code = camera.main([str(self.root / "missing.json")])
        self.assertEqual(2, code)
        self.assertEqual("camera-source-missing", json.loads(buffer.getvalue())["reason"])


if __name__ == "__main__":
    unittest.main()
