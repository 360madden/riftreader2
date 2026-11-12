import math
import threading
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from scripts.movement_controller import Calibration, Position
from scripts.physical_waypoints import PhysicalAdapter, Snapshot, Stopped, WaypointError, pose_drift, run_facing, run_route
from scripts.waypoint_heading import choose_turn, heading_error
from tests.test_physical_waypoints import SimulatedRift


class ImmediateStop(threading.Event):
    def wait(self, timeout=None):
        return self.is_set()


class TurningRift(SimulatedRift):
    def __init__(self, *, no_turn=False, move_during_turn=False, stop_after=None):
        super().__init__()
        self.bearing = 0
        self.no_turn, self.move_during_turn, self.stop_after = no_turn, move_during_turn, stop_after

    def read(self):
        return Snapshot(self.position, self.bearing, time.monotonic(), "simulation")

    def turn_rates(self):
        return {"a": .17, "d": -.17}

    def calibrations(self, _):
        result = {}
        for key, offset in (("w", 0), ("s", 180), ("q", 90), ("e", -90)):
            angle = math.radians(self.bearing + offset)
            result[key] = Calibration(key, .006*math.sin(angle), .006*math.cos(angle), 100, .6, 0)
        return result

    def pulse(self, action, *, focus):
        self.calls.append((action, focus))
        if action.key in ("a", "d"):
            if not self.no_turn:
                self.bearing = heading_error(self.bearing+self.turn_rates()[action.key]*action.hold_ms, 0)
            if self.move_during_turn:
                self.position = Position(self.position.x+.2, 10, self.position.z)
        else:
            speed = self.calibrations(None)[action.key]
            self.position = Position(self.position.x+speed.dx_per_ms*action.hold_ms,
                                     10, self.position.z+speed.dz_per_ms*action.hold_ms)
        if self.stop_after:
            self.stop_after.set()
        return {"releaseSucceeded": True, "holdMilliseconds": action.hold_ms, "keys": [action.key]}


class HeadingTests(unittest.TestCase):
    def test_shortest_angle_wrap_and_key_direction(self):
        self.assertEqual(heading_error(-170, 170), 20)
        self.assertEqual(heading_error(170, -170), -20)
        self.assertEqual(choose_turn(170, -170, {"a": .17, "d": -.17}).key, "a")
        self.assertEqual(choose_turn(-170, 170, {"a": .17, "d": -.17}).key, "d")

    def test_face_then_walk_reaches_sideways_goal_using_turns_and_w_only(self):
        adapter = TurningRift()
        result = run_route(adapter, [("Left", 2, 0)], ImmediateStop(), face_waypoints=True)[0]
        self.assertEqual(result["status"], "arrived")
        self.assertLessEqual(result["distance"], .3)
        self.assertGreater(result["turnPulses"], 0)
        self.assertEqual(set(a.key for a, _ in adapter.calls), {"a", "w"})
        self.assertTrue(adapter.calls[0][1])
        self.assertTrue(all(not focus for _, focus in adapter.calls[1:]))
        self.assertEqual(result["totalHoldMs"], sum(a.hold_ms for a, _ in adapter.calls))

    def test_facing_changes_yaw_without_translation(self):
        adapter = TurningRift()
        result = run_facing(adapter, ImmediateStop(), bearing=-90)
        self.assertLessEqual(abs(result["headingError"]), 4)
        self.assertEqual(adapter.position, Position(0, 10, 0))
        self.assertEqual(set(a.key for a, _ in adapter.calls), {"d"})

    def test_no_turn_response_never_starts_forward_motion(self):
        adapter = TurningRift(no_turn=True)
        with self.assertRaisesRegex(WaypointError, "Turn response"):
            run_route(adapter, [("Left", 2, 0)], ImmediateStop(), face_waypoints=True)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.position, Position(0, 10, 0))

    def test_unexpected_translation_during_turn_halts_before_w(self):
        adapter = TurningRift(move_during_turn=True)
        with self.assertRaisesRegex(WaypointError, "Turning moved"):
            run_route(adapter, [("Left", 2, 0)], ImmediateStop(), face_waypoints=True)
        self.assertEqual([a.key for a, _ in adapter.calls], ["a"])

    def test_stop_during_turn_prevents_any_forward_pulse(self):
        stop = ImmediateStop()
        adapter = TurningRift(stop_after=stop)
        with self.assertRaises(Stopped):
            run_route(adapter, [("Left", 2, 0)], stop, face_waypoints=True)
        self.assertEqual([a.key for a, _ in adapter.calls], ["a"])
        self.assertEqual(adapter.position, Position(0, 10, 0))

    def test_stop_drift_detects_yaw_only_motion_and_vertical_motion(self):
        first = Snapshot(Position(0, 10, 0), 179.9, 0, "simulation")
        second = Snapshot(Position(0, 10.2, 0), -179.9, 0, "simulation")
        distance, yaw = pose_drift(first, second)
        self.assertAlmostEqual(distance, .2)
        self.assertAlmostEqual(yaw, .2)
        self.assertGreater(pose_drift(first, Snapshot(first.position, 90, 0, "simulation"))[1], .5)

    def test_snapshot_age_includes_time_since_native_acquisition(self):
        adapter = object.__new__(PhysicalAdapter)
        adapter.selection, adapter.unit_key = {}, "123"
        captured = {"status": "complete", "nativeOutput": "simulation", "nativeValues": {
            "sampledAtUtc": (datetime.now(timezone.utc)-timedelta(seconds=1.5)).isoformat(),
            "playerKey": "123", "positionSource": "entity-owned-position-component+0x48",
            "bodyBearingDegreesCandidate": 0, "positionXYZCandidate": {"x": 0, "y": 10, "z": 0}}}
        with patch("scripts.physical_rift.read_native", return_value=captured):
            snapshot = adapter.read()
        self.assertGreaterEqual(time.monotonic()-snapshot.acquired, 1.49)

    def test_moving_player_preflight_sends_no_input(self):
        class MovingRift(TurningRift):
            def read(self):
                self.position = Position(self.position.x+.1, 10, self.position.z)
                return super().read()
        adapter = MovingRift()
        with self.assertRaisesRegex(WaypointError, "moving or turning"):
            run_route(adapter, [("Near", 2, 0)], ImmediateStop(), face_waypoints=True)
        self.assertFalse(adapter.calls)


if __name__ == "__main__":
    unittest.main()
