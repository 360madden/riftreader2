from contextlib import nullcontext
import threading
import time
import unittest

from scripts.movement_controller import Calibration, MovementHalted, Position
from scripts.physical_waypoints import Snapshot, Stopped, run_leg, run_route
from scripts.waypoint_limits import MAX_ROUTE_DISTANCE


class SimulatedRift:
    def __init__(self, *, stuck=False, stop_after=None):
        self.position = Position(0, 10, 0)
        self.stuck = stuck
        self.stop_after = stop_after
        self.calls = []

    def reserve(self):
        class Lease:
            def check(self):
                pass
        return nullcontext(Lease())

    def read(self):
        return Snapshot(self.position, 0, time.monotonic(), "simulation")

    def calibrations(self, _):
        return {key: Calibration(key, x, z, 100, .6, 0) for key, x, z in
                (("w", 0, .006), ("s", 0, -.003), ("q", .006, 0), ("e", -.006, 0))}

    def pulse(self, action, *, focus):
        self.calls.append((action, focus))
        if not self.stuck:
            calibration = self.calibrations(None)[action.key]
            self.position = Position(self.position.x + calibration.dx_per_ms * action.hold_ms,
                                     10, self.position.z + calibration.dz_per_ms * action.hold_ms)
        if self.stop_after:
            self.stop_after.set()
        return {"releaseSucceeded": True}


class WaypointRunnerTests(unittest.TestCase):
    def test_arrives_using_feedback_and_only_first_pulse_can_focus(self):
        adapter = SimulatedRift()
        result = run_leg(adapter, -2, 0, threading.Event())
        self.assertEqual(result["status"], "arrived")
        self.assertLessEqual(result["distance"], .30)
        self.assertGreater(len(adapter.calls), 1)
        self.assertTrue(adapter.calls[0][1])
        self.assertTrue(all(not focus for _, focus in adapter.calls[1:]))
        self.assertLessEqual(result["totalHoldMs"], 900)

    def test_pending_stop_never_sends_input(self):
        adapter, stop = SimulatedRift(), threading.Event()
        stop.set()
        with self.assertRaises(Stopped):
            run_leg(adapter, 1, 0, stop)
        self.assertFalse(adapter.calls)

    def test_stop_after_one_released_pulse_prevents_next(self):
        stop = threading.Event()
        adapter = SimulatedRift(stop_after=stop)
        with self.assertRaises(Stopped):
            run_leg(adapter, 2, 0, stop)
        self.assertEqual(len(adapter.calls), 1)

    def test_blocked_movement_halts_instead_of_repeating_route(self):
        adapter = SimulatedRift(stuck=True)
        with self.assertRaisesRegex(MovementHalted, "no-progress"):
            run_leg(adapter, 2, 0, threading.Event())
        self.assertEqual(len(adapter.calls), 2)

    def test_out_of_range_goal_sends_nothing(self):
        adapter = SimulatedRift()
        with self.assertRaisesRegex(ValueError, "radius"):
            run_leg(adapter, 20, 0, threading.Event())
        self.assertFalse(adapter.calls)

    def test_already_there_requires_two_read_observations_and_no_input(self):
        adapter = SimulatedRift()
        result = run_leg(adapter, 0, 0, threading.Event())
        self.assertEqual(result["status"], "arrived")
        self.assertFalse(adapter.calls)

    def test_route_can_focus_first_actual_pulse_after_an_already_reached_point(self):
        adapter = SimulatedRift()
        result = run_route(adapter, [("Here", 0, 0), ("Next", 1, 0), ("Return", 0, 0)], threading.Event())
        self.assertEqual(len(result), 3)
        self.assertTrue(adapter.calls[0][1])
        self.assertTrue(all(not focus for _, focus in adapter.calls[1:]))

    def test_route_stop_does_not_start_next_leg(self):
        adapter, stop = SimulatedRift(), threading.Event()
        def emit(event):
            if event["status"] == "arrived":
                stop.set()
        with self.assertRaises(Stopped):
            run_route(adapter, [("Here", 0, 0), ("Next", 2, 0)], stop, emit)
        self.assertFalse(adapter.calls)

    def test_long_waypoint_uses_multiple_controllers_but_keeps_one_focus_request(self):
        adapter = SimulatedRift()
        result = run_route(adapter, [("Long", 8, 0)], threading.Event())[0]
        self.assertEqual(result["status"], "arrived")
        self.assertLessEqual(result["distance"], .30)
        self.assertGreater(len(result["segments"]), 1)
        self.assertGreater(result["pulses"], 6)
        self.assertTrue(adapter.calls[0][1])
        self.assertTrue(all(not focus for _, focus in adapter.calls[1:]))

    def test_route_total_length_is_checked_before_any_input(self):
        adapter = SimulatedRift()
        with self.assertRaisesRegex(ValueError, "1000 world units"):
            run_route(adapter, [("Out", MAX_ROUTE_DISTANCE / 2 + 1, 0), ("Return", 0, 0)], threading.Event())
        self.assertFalse(adapter.calls)

    def test_stop_at_intermediate_arrival_does_not_start_the_next_segment(self):
        adapter, stop = SimulatedRift(), threading.Event()
        def emit(event):
            if event["status"] == "segment-arrived":
                stop.set()
        with self.assertRaises(Stopped):
            run_route(adapter, [("Long", 8, 0)], stop, emit)
        self.assertLess(adapter.position.x, 5)
        self.assertLessEqual(len(adapter.calls), 6)


if __name__ == "__main__":
    unittest.main()
