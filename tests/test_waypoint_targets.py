from datetime import datetime, timedelta, timezone
import time
import unittest

from scripts.movement_controller import Position
from scripts.physical_waypoints import Snapshot, WaypointError, target_waypoint


class TargetWaypointTests(unittest.TestCase):
    def snapshot(self, *, age=0, target_y=10, status="candidate"):
        return Snapshot(Position(0, 10, 0), 0, time.monotonic(), "test", {
            "status": status,
            "sampledAtUtc": (datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),
            "positionXYZCandidate": {"x": 3, "y": target_y, "z": 4}})

    def test_fresh_ground_target_becomes_a_fixed_point(self):
        snapshot = self.snapshot()
        self.assertEqual(("Selected target", 3, 4), target_waypoint(snapshot))
        self.assertEqual(Position(0, 10, 0), snapshot.position)

    def test_absent_expired_future_or_different_floor_target_is_refused(self):
        for snapshot in (Snapshot(Position(0, 10, 0), 0, time.monotonic(), "test"),
                         self.snapshot(status="unavailable"), self.snapshot(age=5),
                         self.snapshot(age=-5), self.snapshot(target_y=12)):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(WaypointError):
                    target_waypoint(snapshot)

    def test_invalid_coordinate_or_expired_player_pose_is_refused(self):
        snapshot = self.snapshot()
        snapshot.selected_target["positionXYZCandidate"]["x"] = float("nan")
        with self.assertRaises(WaypointError):
            target_waypoint(snapshot)
        snapshot = self.snapshot()
        old = Snapshot(snapshot.position, snapshot.bearing, time.monotonic()-5,
                       snapshot.source, snapshot.selected_target)
        with self.assertRaises(WaypointError):
            target_waypoint(old)


if __name__ == "__main__":
    unittest.main()
