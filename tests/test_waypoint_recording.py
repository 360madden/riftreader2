import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from scripts.waypoint_recording import RecordingError, RouteRecorder


def pose(x, z, at, y=0, source="native.json"):
    return NS(position=NS(x=x, y=y, z=z), bearing=0, acquired=at, source=source)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch("scripts.waypoint_recording.time.monotonic", return_value=100)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.identity = {"machine": "AMD-DESKTOP", "build": "abc", "player": "123",
                         "runtimeIdentity": {"processId": 20}}
        self.rec = RouteRecorder(self.identity, max_age_seconds=10)

    def test_progress_tracks_observations_and_is_independent(self):
        self.assertEqual(self.rec.progress, {"sampleCount": 0, "observedPathLength": 0})
        self.rec.observe(pose(0, 0, 98))
        self.assertEqual(self.rec.progress, {"sampleCount": 1, "observedPathLength": 0})
        self.rec.observe(pose(3, 4, 99))
        progress = self.rec.progress
        self.assertEqual(progress, {"sampleCount": 2, "observedPathLength": 5})
        progress["sampleCount"] = 999
        progress["observedPathLength"] = -1
        self.assertEqual(self.rec.progress, {"sampleCount": 2, "observedPathLength": 5})
        self.rec.observe(pose(3, 5, 100))
        self.assertEqual(self.rec.progress, {"sampleCount": 3, "observedPathLength": 6})
        finished = self.rec.finish()["recording"]
        self.assertEqual(self.rec.progress["sampleCount"], finished["sampleCount"])
        self.assertEqual(self.rec.progress["observedPathLength"], finished["observedPathLength"])

    def test_corners_start_end_and_identity_copied(self):
        for p in (pose(0, 0, 95), pose(1, .01, 96), pose(2, 0, 97),
                  pose(2, 1, 98), pose(2, 2, 99), pose(3, 2, 100)):
            self.rec.observe(p)
        self.identity["runtimeIdentity"]["processId"] = 999
        route = self.rec.finish()
        self.assertEqual([(r[1], r[2]) for r in route["waypoints"]], [(0, 0), (2, 0), (2, 2), (3, 2)])
        self.assertEqual(route["recording"]["identity"]["runtimeIdentity"]["processId"], 20)
        self.assertTrue(route["recording"]["complete"])

    def test_boundary_preserved_and_stationary_deduplicated(self):
        a, b, c = pose(0, 0, 97), pose(1, 0, 98), pose(2, 0, 100)
        self.rec.observe(a); self.rec.observe(b); self.rec.observe(b, boundary=True)
        self.rec.observe(pose(1, 0, 99)); self.rec.observe(c)
        self.assertEqual([p[1] for p in self.rec.finish()["waypoints"]], [0, 1, 2])

    def test_out_of_order_gap_teleport_and_stale_poison_recording(self):
        for bad in (pose(1, 0, 97), pose(1, 0, 96), pose(1, 0, 100.2),
                    pose(19, 0, 98.1)):
            with self.subTest(at=bad.acquired, x=bad.position.x):
                rec = RouteRecorder(self.identity, max_age_seconds=10)
                rec.observe(pose(0, 0, 97))
                with self.assertRaises(RecordingError): rec.observe(bad)
                with self.assertRaises(RecordingError): rec.finish()
        rec = RouteRecorder(self.identity)
        with self.assertRaises(RecordingError): rec.observe(pose(0, 0, 97))

    def test_gap_and_too_many_corners_fail_without_truncating(self):
        rec = RouteRecorder(self.identity, max_age_seconds=10)
        rec.observe(pose(0, 0, 95))
        with self.assertRaises(RecordingError): rec.observe(pose(1, 0, 99))
        rec = RouteRecorder(self.identity, max_age_seconds=100, max_gap_seconds=3)
        for i in range(21): rec.observe(pose(i * .1, 0, 80 + i), boundary=True)
        with self.assertRaisesRegex(RecordingError, "2–20"): rec.finish()

    def test_long_path_and_no_movement_refused(self):
        rec = RouteRecorder(self.identity, max_age_seconds=100)
        for i in range(11): rec.observe(pose(i * 2, 0, 89 + i))
        with self.assertRaises(RecordingError): rec.observe(pose(20.1, 0, 100))
        self.rec.observe(pose(0, 0, 99)); self.rec.observe(pose(0, 0, 100))
        with self.assertRaises(RecordingError): self.rec.finish()

    def test_retained_corner_heights_align_with_waypoints(self):
        for sample in (pose(0, 0, 97, y=10.1234567), pose(1, 0, 98, y=11),
                       pose(2, 0, 99, y=12.1234567), pose(2, 1, 100, y=13)):
            self.rec.observe(sample)
        route = self.rec.finish()
        self.assertEqual([(p[1], p[2]) for p in route["waypoints"]], [(0, 0), (2, 0), (2, 1)])
        self.assertEqual(route["heights"], [10.123457, 12.123457, 13])

    def test_waypoints_use_stable_six_decimal_coordinates(self):
        self.rec.observe(pose(1.123456789, 2.123456789, 99))
        self.rec.observe(pose(2.123456789, 2.987654321, 100))
        points = self.rec.finish()["waypoints"]
        self.assertEqual(points[0][1:], [1.123457, 2.123457])
        self.assertEqual(points[1][1:], [2.123457, 2.987654])
        self.assertEqual(points, [[name, float(f"{x:.6f}"), float(f"{z:.6f}")] for name, x, z in points])

    def test_collinear_reversal_preserves_turn(self):
        for i, x in enumerate((0, 1, 2, 1, 3)):
            self.rec.observe(pose(x, 0, 96 + i))
        self.assertEqual([p[1] for p in self.rec.finish()["waypoints"]], [0, 2, 1, 3])

    def test_out_and_back_preserves_turn(self):
        for i, x in enumerate((0, 1, 2, 1, 0)):
            self.rec.observe(pose(x, 0, 96 + i))
        self.assertEqual([p[1] for p in self.rec.finish()["waypoints"]], [0, 2, 0])


if __name__ == "__main__": unittest.main()
