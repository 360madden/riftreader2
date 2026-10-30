import math
import unittest

from scripts.movement_controller import (
    MovementError,
    MovementHalted,
    Position,
    WaypointController,
    calibrate_displacement,
    validate_noncollinear,
)


def basis():
    origin = Position(0, 10, 0)
    return {
        "w": calibrate_displacement("w", origin, Position(1, 10, 0), 100),
        "q": calibrate_displacement("q", origin, Position(0, 10, 1), 100),
    }


class CalibrationTests(unittest.TestCase):
    def test_measures_only_the_requested_empirical_key(self):
        value = calibrate_displacement("s", Position(3, 4, 5), Position(2.5, 4.1, 5), 100)
        self.assertEqual("s", value.key)
        self.assertAlmostEqual(-0.005, value.dx_per_ms)
        self.assertEqual(0, value.dz_per_ms)

    def test_rejects_invalid_nonfinite_small_large_and_vertical_samples(self):
        cases = [
            ("x", Position(0, 0, 0), Position(1, 0, 0), 100),
            ("w", Position(math.nan, 0, 0), Position(1, 0, 0), 100),
            ("w", Position(0, 0, 0), Position(.01, 0, 0), 100),
            ("w", Position(0, 0, 0), Position(3, 0, 0), 100),
            ("w", Position(0, 0, 0), Position(1, 1, 0), 100),
            ("w", Position(0, 0, 0), Position(1, 0, 0), 151),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(MovementError):
                calibrate_displacement(*args)

    def test_requires_independent_basis(self):
        self.assertAlmostEqual(1, validate_noncollinear(basis()))
        values = basis()
        values["q"] = calibrate_displacement("q", Position(0, 0, 0), Position(1, 0, .01), 100)
        with self.assertRaisesRegex(MovementError, "collinear"):
            validate_noncollinear(values)


class WaypointControllerTests(unittest.TestCase):
    def test_greedy_recomputes_from_feedback_and_confirms_arrival_twice(self):
        ctl = WaypointController(basis(), Position(0, 10, 0), Position(1, 10, 1))
        first = ctl.decide(Position(0, 10, 0), 0)
        self.assertEqual(("q", 70), (first.key, first.hold_ms))
        feedback = ctl.record_feedback(Position(0, 10, .7), 1)
        self.assertGreater(feedback.progress, 0)
        self.assertEqual("active", feedback.status)
        second = ctl.decide(Position(0, 10, .7), 1.1)
        self.assertEqual(("w", 100), (second.key, second.hold_ms))
        ctl.record_feedback(Position(1, 10, .7), 2)
        third = ctl.decide(Position(1, 10, .7), 2.1)
        self.assertEqual(("q", 30), (third.key, third.hold_ms))
        ctl.record_feedback(Position(1, 10, 1), 2.5)
        self.assertEqual("confirming-arrival", ctl.status)
        self.assertIsNone(ctl.decide(Position(1, 10, 1), 2.6))
        self.assertEqual("confirming-arrival", ctl.status)
        ctl.observe(Position(1, 10, 1), 2.7)
        self.assertEqual("arrived", ctl.status)
        self.assertEqual(3, ctl.feedback_iterations)
        self.assertIsNone(ctl.decide(Position(1, 10, 1), 2.8))

    def test_does_not_assume_inverse_key(self):
        ctl = WaypointController({"w": basis()["w"]}, Position(0, 0, 0), Position(-1, 0, 0))
        with self.assertRaisesRegex(MovementHalted, "no-useful"):
            ctl.decide(Position(0, 0, 0), 0)

    def test_uses_explicitly_calibrated_inverse(self):
        values = basis()
        values["s"] = calibrate_displacement("s", Position(0, 0, 0), Position(-1, 0, 0), 100)
        ctl = WaypointController(values, Position(0, 0, 0), Position(-1, 0, 0))
        self.assertEqual("s", ctl.decide(Position(0, 0, 0), 0).key)

    def test_clamps_pulses_to_bounds(self):
        short = WaypointController(basis(), Position(0, 0, 0), Position(.4, 0, 0), tolerance=.25)
        self.assertEqual(40, short.decide(Position(0, 0, 0), 0).hold_ms)
        long = WaypointController(basis(), Position(0, 0, 0), Position(3, 0, 0))
        self.assertEqual(150, long.decide(Position(0, 0, 0), 0).hold_ms)

    def test_requires_feedback_before_another_action(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 1))
        ctl.decide(Position(0, 0, 0), 0)
        with self.assertRaisesRegex(MovementError, "no fresh feedback"):
            ctl.decide(Position(0, 0, 0), .1)

    def test_halts_on_two_no_progress_feedbacks(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(2, 0, 2))
        ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(0, 0, 0), 1)
        ctl.decide(Position(0, 0, 0), 1.1)
        with self.assertRaisesRegex(MovementHalted, "no-progress"):
            ctl.record_feedback(Position(0, 0, 0), 2)

    def test_halts_on_two_divergent_feedbacks(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(2, 0, 2), max_radius=6)
        ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(-.1, 0, 0), 1)
        ctl.decide(Position(-.1, 0, 0), 1.1)
        with self.assertRaisesRegex(MovementHalted, "divergence"):
            ctl.record_feedback(Position(-.2, 0, 0), 2)

    def test_enforces_time_radius_vertical_action_and_hold_budgets(self):
        for name, ctl, position, elapsed in [
            ("elapsed", WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 1)), Position(0, 0, 0), 12.1),
            ("radius", WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 1)), Position(6.1, 0, 0), 1),
            ("vertical", WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 1)), Position(0, 1.6, 0), 1),
        ]:
            with self.subTest(name=name), self.assertRaises(MovementHalted):
                ctl.decide(position, elapsed)
        with self.assertRaises(MovementError):
            WaypointController(basis(), Position(0, 0, 0), Position(6.1, 0, 0))

    def test_halts_on_cross_track_departure(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(2, 0, 0))
        with self.assertRaisesRegex(MovementHalted, "cross-track"):
            ctl.observe(Position(0, 0, .51), 1)

    def test_action_and_hold_budgets_have_direct_coverage(self):
        actions = WaypointController(
            basis(), Position(0, 0, 0), Position(3, 0, 0), max_goal_actions=1
        )
        first = actions.decide(Position(0, 0, 0), 0)
        actions.record_feedback(Position(first.hold_ms / 100, 0, 0), 1)
        with self.assertRaisesRegex(MovementHalted, "action-budget"):
            actions.decide(actions.current, 1.1)

        holds = WaypointController(
            basis(), Position(0, 0, 0), Position(3, 0, 0), max_total_hold_ms=20
        )
        first = holds.decide(Position(0, 0, 0), 0)
        holds.record_feedback(Position(first.hold_ms / 100, 0, 0), 1)
        with self.assertRaisesRegex(MovementHalted, "hold-budget"):
            holds.decide(holds.current, 1.1)

    def test_arrival_never_emits_an_action(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(.3, 0, 0), tolerance=.3)
        self.assertIsNone(ctl.decide(Position(0, 0, 0), 0))
        self.assertIsNone(ctl.decide(Position(0, 0, 0), .1))
        self.assertEqual(0, ctl.arrival_confirmations)
        ctl.observe(Position(0, 0, 0), .2)
        ctl.observe(Position(0, 0, 0), .3)
        self.assertEqual("arrived", ctl.status)
        ctl.observe(Position(0, 0, .4), .4)
        self.assertEqual("active", ctl.status)
        self.assertEqual(0, ctl.arrival_confirmations)

    def test_released_settle_confirms_without_extending_movement_time(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        action = ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(1, 0, 0), 11.9)
        self.assertEqual("confirming-arrival", ctl.status)
        ctl.confirm_released_settle(Position(1, 0, 0), Position(1, 0, 0))
        self.assertEqual("arrived", ctl.status)

    def test_released_settle_requires_no_pending_and_one_action_arrival(self):
        pending = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        pending.decide(Position(0, 0, 0), 0)
        with self.assertRaisesRegex(MovementError, "pending action"):
            pending.confirm_released_settle(Position(1, 0, 0), Position(1, 0, 0))

        active = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        with self.assertRaisesRegex(MovementError, "one in-tolerance"):
            active.confirm_released_settle(Position(1, 0, 0), Position(1, 0, 0))

    def test_released_settle_still_enforces_geometry_and_can_revoke_arrival(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(1, 0, 0), 11.9)
        with self.assertRaisesRegex(MovementError, "not planar-stationary"):
            ctl.confirm_released_settle(Position(.6, 0, 0), Position(1, 0, 0))
        self.assertEqual("confirming-arrival", ctl.status)
        self.assertEqual(1, ctl.arrival_confirmations)

        ctl.confirm_released_settle(Position(.96, 0, 0), Position(1, 0, 0))
        self.assertEqual("arrived", ctl.status)

    def test_released_settle_inside_tolerance_still_requires_stationarity(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(.8, 0, 0), 1)
        with self.assertRaisesRegex(MovementError, "not planar-stationary"):
            ctl.confirm_released_settle(Position(.9, 0, 0), Position(.8, 0, 0))
        ctl.confirm_released_settle(Position(.84, 0, 0), Position(.8, 0, 0))
        self.assertEqual("arrived", ctl.status)

    def test_released_settle_rejects_out_of_geometry_and_halted_controller(self):
        ctl = WaypointController(basis(), Position(0, 0, 0), Position(1, 0, 0))
        ctl.decide(Position(0, 0, 0), 0)
        ctl.record_feedback(Position(1, 0, 0), 11.9)
        with self.assertRaisesRegex(MovementHalted, "cross-track"):
            ctl.confirm_released_settle(Position(1, 0, .51), Position(1, 0, 0))
        with self.assertRaisesRegex(MovementHalted, "cross-track"):
            ctl.confirm_released_settle(Position(1, 0, 0), Position(1, 0, 0))


if __name__ == "__main__":
    unittest.main()
