"""Passive guidance never borrows playback progress or skips route points."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from scripts.waypoint_manual_guidance import ManualGuidance


OWNER = dict(target=dict(hostName="AMD-DESKTOP", executablePath="C:/rift.exe",
    executableSha256="a" * 64, processId=42, processStartUtcTicks="100", hwnd=123),
    playerKey="player", sessionId="beacons-1")
POINTS = [["A", 0., 0.], ["B", 5., 0.], ["C", 10., 0.]]


def pose(seq, seconds, x=0., z=0.):
    return dict(deepcopy(OWNER), status="fresh", sequence=seq,
                acquiredMonotonic=100 + seconds,
                sampledAtUtc=(datetime(2026, 11, 13, tzinfo=timezone.utc)
                              + timedelta(seconds=seconds)).isoformat(),
                position=dict(x=x, y=0., z=z))


class ManualGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.guide = ManualGuidance()
        self.guide.begin(POINTS, "forward", 0, OWNER)

    def test_two_distinct_sustained_samples_advance_only_current_point(self):
        self.assertEqual(self.guide.observe(pose(1, 0))["activeIndex"], 0)
        self.assertEqual(self.guide.observe(pose(2, .1))["completedIndices"], [])
        result = self.guide.observe(pose(3, .2))
        self.assertEqual(result["activeIndex"], 1)
        self.assertEqual(result["activeName"], "B")
        self.assertEqual(result["completedIndices"], [0])
        self.assertEqual(result["distance"], 5.)

    def test_near_later_point_never_skips_current_point(self):
        for seq in range(1, 5):
            result = self.guide.observe(pose(seq, seq * .25, x=10))
        self.assertEqual(result["completedIndices"], [])
        self.assertEqual(result["activeIndex"], 0)

    def test_reverse_explicit_start_preserves_original_indices(self):
        self.guide.begin(POINTS, "reverse", 1, OWNER)
        self.guide.observe(pose(1, 0, x=5))
        result = self.guide.observe(pose(2, .2, x=5))
        self.assertEqual(result["order"], [1, 0])
        self.assertEqual(result["completedIndices"], [1])
        self.assertEqual(result["activeIndex"], 0)
        self.guide.observe(pose(3, .4))
        result = self.guide.observe(pose(4, .6))
        self.assertTrue(result["complete"])
        self.assertIsNone(result["activeIndex"])
        self.assertEqual(result["completedIndices"], [1, 0])

    def test_repeated_and_regressed_samples_reset_confirmation(self):
        self.guide.observe(pose(2, .2))
        for packet in (pose(2, .4), pose(3, .2), pose(1, .1)):
            self.assertEqual(self.guide.observe(packet)["status"], "unavailable")
        self.assertEqual(self.guide.observe(pose(4, .5))["completedIndices"], [])
        self.assertEqual(self.guide.observe(pose(5, .7))["completedIndices"], [0])

    def test_polling_exact_same_packet_never_confirms_or_resets_arrival(self):
        first = pose(1, 0)
        self.guide.observe(first)
        for _ in range(10):
            self.assertEqual(self.guide.observe(first)["completedIndices"], [])
        self.assertEqual(self.guide.observe(pose(2, .2))["completedIndices"], [0])

    def test_unavailable_and_long_gap_require_new_confirmation(self):
        for gap in ("explicit", "time"):
            with self.subTest(gap=gap):
                self.guide.begin(POINTS, "forward", 0, OWNER)
                self.guide.observe(pose(1, 0))
                if gap == "explicit":
                    self.guide.unavailable("stale-pose")
                result = self.guide.observe(pose(2, 2))
                self.assertEqual(result["completedIndices"], [])
                self.assertEqual(self.guide.observe(pose(3, 2.2))["completedIndices"], [0])

    def test_leaving_arrival_radius_resets_confirmation(self):
        self.guide.observe(pose(1, 0))
        self.guide.observe(pose(2, .2, x=.61))
        self.assertEqual(self.guide.observe(pose(3, .4))["completedIndices"], [])
        self.assertEqual(self.guide.observe(pose(4, .6))["completedIndices"], [0])

    def test_owner_epoch_or_beacon_session_change_stops_until_begin(self):
        for change in (lambda p: p.update(sessionId="new-path"),
                       lambda p: p.update(playerKey="other"),
                       lambda p: p["target"].update(processId=43),
                       lambda p: p["target"].update(processStartUtcTicks="101")):
            self.guide.begin(POINTS, "forward", 0, OWNER)
            packet = pose(1, 0)
            change(packet)
            self.assertEqual(self.guide.observe(packet)["status"], "stopped")
            self.assertEqual(self.guide.observe(pose(2, .3))["status"], "stopped")

    def test_nonfresh_or_invalid_sample_clears_distance_and_confirmation(self):
        for packet in (dict(pose(2, .2), status="unavailable"),
                       dict(pose(2, .2), acquiredMonotonic=float("nan"))):
            self.guide.observe(pose(1, 0))
            result = self.guide.observe(packet)
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["distance"])

    def test_snapshots_and_status_copies_cannot_mutate_route_or_progress(self):
        points, owner = deepcopy(POINTS), deepcopy(OWNER)
        self.guide.begin(points, "forward", 1, owner)
        points[1][1] = 500
        owner["playerKey"] = "other"
        result = self.guide.observe(pose(1, 0, x=5))
        result["order"].clear()
        result["completedIndices"].append(2)
        self.assertEqual(self.guide.as_dict()["order"], [1, 2])
        self.assertEqual(self.guide.as_dict()["completedIndices"], [])
        self.assertEqual(self.guide.as_dict()["distance"], 0)

    def test_coincident_points_need_separate_arrival_confirmations(self):
        self.guide.begin([["A", 0, 0], ["B", 0, 0]], "forward", 0, OWNER)
        self.guide.observe(pose(1, 0))
        self.guide.observe(pose(2, .2))
        self.assertEqual(self.guide.observe(pose(3, .4))["completedIndices"], [0])
        self.assertTrue(self.guide.observe(pose(4, .6))["complete"])

    def test_stop_does_not_resume_and_begin_resets_passive_progress(self):
        self.guide.observe(pose(1, 0))
        self.guide.stop()
        self.assertEqual(self.guide.observe(pose(2, .2))["status"], "stopped")
        self.assertEqual(self.guide.begin(POINTS, "forward", 2, OWNER)["order"], [2])
        self.assertEqual(self.guide.as_dict()["completedIndices"], [])


if __name__ == "__main__":
    unittest.main()
