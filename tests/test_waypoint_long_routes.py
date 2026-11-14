"""Exercise full route execution and durable Resume without real waits or input."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as app
from scripts.movement_controller import MovementHalted, Position
from scripts.waypoint_limits import (
    MAX_ROUTE_DISTANCE, MAX_WAYPOINTS, MAX_TRIP_SECONDS,
    MAX_TRIP_PULSES, MAX_TRIP_HOLD_MS,
)
from scripts.waypoint_playback import play_route
from scripts.waypoint_progress import ProgressError
from tests.test_waypoint_playback import BoundSim
from tests.test_waypoint_heading import TurningRift


class Clock:
    def __init__(self):
        self.now = 100.

    def monotonic(self):
        self.now += .001
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SimStop(threading.Event):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def wait(self, timeout=None):
        if not self.is_set() and timeout is not None:
            self.clock.sleep(timeout)
        return self.is_set()


class LongRouteTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.clock = Clock()
        self.stack.enter_context(patch.object(app.time, "monotonic", self.clock.monotonic))
        self.stack.enter_context(patch.object(app.time, "sleep", self.clock.sleep))
        self.stop = SimStop(self.clock)
        self.path = Path(self.stack.enter_context(tempfile.TemporaryDirectory())) / "progress.json"

    def run_playback(self, sim, document, **kwargs):
        return play_route(sim, document, self.stop, kwargs.pop("emit", lambda _: None),
                          runner=app.run_route, checkpoint=self.path,
                          face_waypoints=kwargs.pop("face_waypoints", False), **kwargs)

    def test_long_face_then_walk_route_turns_corners_and_reverses(self):
        class BoundTurningRift(TurningRift):
            binding = BoundSim.binding
        sim = BoundTurningRift()
        document = {"waypoints": [["Start", 0, 0], ["East", 30, 0],
                                   ["North", 30, 30], ["West", 0, 30]]}
        for direction, endpoint in (("forward", Position(0, 10, 30)), ("reverse", Position(0, 10, 0))):
            with self.subTest(direction=direction):
                first_call = len(sim.calls)
                legs, cursor = self.run_playback(sim, document, direction=direction, face_waypoints=True)
                self.assertEqual(4, cursor.next_index)
                self.assertLessEqual(app.planar_distance(sim.position, endpoint), .30)
                calls = sim.calls[first_call:]
                self.assertGreater(len(calls), 64)
                self.assertTrue(all(action.key in ("a", "d", "w") for action, _ in calls))
                self.assertTrue(calls[0][1])
                self.assertTrue(all(not focus for _, focus in calls[1:]))
                self.assertEqual(sum(leg["totalHoldMs"] for leg in legs),
                                 sum(action.hold_ms for action, _ in calls))

    def test_stale_pose_after_old_distance_limit_prevents_further_input(self):
        class StaleRift(BoundSim):
            def read(self):
                snapshot = super().read()
                if self.position.x >= 25:
                    return app.Snapshot(snapshot.position, snapshot.bearing, snapshot.acquired - 3, snapshot.source)
                return snapshot
        sim = StaleRift()
        with self.assertRaisesRegex(app.WaypointError, "expired"):
            app.run_route(sim, [("Far", 100, 0)], self.stop)
        self.assertGreaterEqual(sim.position.x, 25)
        self.assertLess(sim.position.x, 26)

    def test_thousand_unit_route_and_five_hundred_points_keep_local_guards(self):
        document = {"waypoints": [[f"Point {i}", i * 1000 / (MAX_WAYPOINTS - 1), 0]
                                  for i in range(MAX_WAYPOINTS)]}
        sim = BoundSim()
        legs, cursor = self.run_playback(sim, document)
        self.assertEqual(MAX_WAYPOINTS, cursor.next_index)
        self.assertLessEqual(abs(sim.position.x - MAX_ROUTE_DISTANCE), .30)
        self.assertGreater(len(sim.calls), 64)
        self.assertTrue(sim.calls[0][1])
        self.assertTrue(all(not focus for _, focus in sim.calls[1:]))
        for leg in legs:
            for segment in leg["segments"]:
                self.assertLessEqual(segment["movementPulses"], 6)
                self.assertLessEqual(segment["totalHoldMs"], 900)
                self.assertLessEqual(segment["elapsedSeconds"], 12)
                self.assertTrue(segment["allPulsesReleased"])
        self.assertEqual(MAX_WAYPOINTS, json.loads(self.path.read_text())["nextIndex"])
        calls = len(sim.calls)
        with self.assertRaisesRegex(ProgressError, "already complete"):
            self.run_playback(sim, document, resume=True)
        self.assertEqual(calls, len(sim.calls))

    def test_stop_past_old_limit_and_resume_forward_and_reverse(self):
        document = {"waypoints": [[f"Point {i}", i * 2, 0] for i in range(31)]}
        for direction in ("forward", "reverse"):
            with self.subTest(direction=direction):
                sim = BoundSim()
                if direction == "reverse":
                    sim.position = Position(60, 10, 0)
                self.stop.clear()
                def stop_midway(event):
                    if event["status"] == "arrived" and event["nextWaypoint"] == 16:
                        self.stop.set()
                with self.assertRaises(app.Stopped):
                    self.run_playback(sim, document, direction=direction, emit=stop_midway)
                payload = json.loads(self.path.read_text())
                self.assertEqual(16, payload["nextIndex"])
                self.assertEqual(direction, payload["direction"])
                calls = len(sim.calls)
                with self.assertRaises(app.Stopped):
                    self.run_playback(sim, document, direction=direction, resume=True)
                self.assertEqual(calls, len(sim.calls))
                self.stop.clear()
                _, cursor = self.run_playback(sim, document, direction=direction, resume=True)
                self.assertEqual(31, cursor.next_index)
                self.assertLessEqual(abs(sim.position.x - (60 if direction == "forward" else 0)), .30)

    def test_stop_in_long_unfinished_leg_then_resume_and_reject_foreign_cursor(self):
        sim = BoundSim(stop_after=self.stop)
        document = {"waypoints": [["Start", 0, 0], ["Far endpoint", 80, 0]]}
        with self.assertRaises(app.Stopped):
            self.run_playback(sim, document)
        self.assertEqual(1, len(sim.calls))
        self.assertEqual(1, json.loads(self.path.read_text())["nextIndex"])
        self.stop.clear()
        sim.stop_after = None
        calls = len(sim.calls)
        changed = {"waypoints": [["Start", 0, 0], ["Far endpoint", 81, 0]]}
        with self.assertRaisesRegex(ProgressError, "route"):
            self.run_playback(sim, changed, resume=True)
        self.assertEqual(calls, len(sim.calls))
        _, cursor = self.run_playback(sim, document, resume=True)
        self.assertEqual(2, cursor.next_index)
        self.assertLessEqual(abs(sim.position.x - 80), .30)

    def test_blocked_long_route_stops_after_two_pulses(self):
        sim = BoundSim(stuck=True)
        with self.assertRaisesRegex(MovementHalted, "no-progress"):
            app.run_route(sim, [("Far", 100, 0)], self.stop)
        self.assertEqual(2, len(sim.calls))

    def test_route_distance_includes_entry_leg_before_input(self):
        sim = BoundSim()
        with self.assertRaisesRegex(app.WaypointError, "1000 world units"):
            app.run_route(sim, [("Near", 1, 0), ("Far", 1001, 0)], self.stop)
        self.assertFalse(sim.calls)

    def test_trip_budget_remains_shared_across_segments_and_waypoints(self):
        sim = BoundSim()
        created = []
        class TinyBudget(app.TripBudget):
            def check(self, action=None):
                if action is not None and self.pulses >= 7:
                    raise app.WaypointError("test trip budget reached")
                super().check(action)
        def factory(started):
            budget = TinyBudget(started)
            created.append(budget)
            return budget
        with patch.object(app, "TripBudget", side_effect=factory):
            with self.assertRaisesRegex(app.WaypointError, "test trip budget"):
                app.run_route(sim, [("First", 2, 0), ("Second", 40, 0)], self.stop)
        self.assertEqual(1, len(created))
        self.assertEqual(7, len(sim.calls))

    def test_trip_time_pulse_and_hold_limits_stop_before_next_action(self):
        action = SimpleNamespace(hold_ms=150)
        for values in (
            dict(started=self.clock.now - MAX_TRIP_SECONDS - 1),
            dict(started=self.clock.now, pulses=MAX_TRIP_PULSES),
            dict(started=self.clock.now, hold_ms=MAX_TRIP_HOLD_MS - 149),
        ):
            with self.subTest(values=values), self.assertRaises(app.WaypointError):
                app.TripBudget(**values).check(action)
        app.TripBudget(self.clock.now, MAX_TRIP_PULSES - 1, MAX_TRIP_HOLD_MS - 150).check(action)


if __name__ == "__main__":
    unittest.main()
