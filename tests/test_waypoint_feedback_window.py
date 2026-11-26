"""Offline tests for deterministic route feedback; no native or input adapters."""
import unittest

from scripts.waypoint_progress import RouteProgress
from scripts.waypoint_feedback_window import assess_leg_feedback


def cursor():
    route = {"waypoints": [["start", 0, 0], ["end", 4, 0], ["return", 0, .4]],
             "heights": [10, 10, 10]}
    value = RouteProgress(route, identity={"machine": "fixture", "gameBuildSha256": "fixture",
                                          "unitKey": "fixture"})
    value.begin({"x": 0, "y": 10, "z": 0})
    value.confirm_arrival(0, value.ordered_points[0])
    return value


def window(route, xyz, *, times=(0, .5, 1, 1.5)):
    return [{"routeHash": route.route_hash, "legIndex": route.next_index,
             "elapsedSeconds": t, "position": dict(zip("xyz", p))}
            for t, p in zip(times, xyz)]


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.route = cursor()

    def assess(self, points, *, expected=True, times=(0, .5, 1, 1.5)):
        result = assess_leg_feedback(self.route, window(self.route, points, times=times),
                                     translation_expected=expected)
        self.assertEqual(1, self.route.next_index)
        self.assertFalse(result["inputSent"])
        return result

    def test_forward_and_stationary_translation(self):
        moving = [(x, 10, 0) for x in (0, .2, .4, .6)]
        self.assertEqual("forward-progress-candidate", self.assess(moving)["status"])
        stopped = [(0, 10, 0)]*4
        result = self.assess(stopped)
        self.assertEqual("stalled-candidate", result["status"])
        self.assertTrue(result["replanSuggested"])
        self.assertEqual("translation-not-expected", self.assess(stopped, expected=False)["status"])

    def test_lateral_or_reversing_motion_is_not_stationary_stall(self):
        result = self.assess([(0, 10, 0), (.4, 10, 0), (.2, 10, 0), (0, 10, 0)])
        self.assertEqual("no-net-progress-candidate", result["status"])
        self.assertTrue(result["replanSuggested"])

    def test_near_waypoint_does_not_confirm_arrival(self):
        result = self.assess([(3.9, 10, 0)]*4)
        self.assertEqual("near-waypoint-candidate", result["status"])
        self.assertFalse(result["replanSuggested"])

    def test_off_corridor_and_wrong_floor_are_distinct(self):
        result = self.assess([(1, 10, .8)]*4)
        self.assertEqual("off-corridor-candidate", result["status"])
        self.assertTrue(result["replanSuggested"])
        result = self.assess([(1, 12, 0)]*4)
        self.assertEqual("height-context-mismatch", result["status"])
        self.assertFalse(result["replanSuggested"])

    def test_height_refusal_wins_over_earlier_off_corridor_sample(self):
        result = self.assess([(1, 10, .8), (1, 12, 0), (1, 10, 0), (1, 10, 0)])
        self.assertEqual("height-context-mismatch", result["status"])
        self.assertFalse(result["replanSuggested"])
        result = self.assess([(1, 10, .8)]*4, expected=False)
        self.assertFalse(result["replanSuggested"])

    def test_vertical_leg_cannot_be_a_planar_stall(self):
        self.route = RouteProgress(
            {"waypoints": [["a", 0, 0], ["b", 0, 0]], "heights": [10, 12]},
            identity={"machine": "fixture", "gameBuildSha256": "fixture", "unitKey": "fixture"})
        self.route.begin({"x": 0, "y": 10, "z": 0})
        self.route.confirm_arrival(0, self.route.ordered_points[0])
        result = self.assess([(0, 10, 0)]*4)
        self.assertEqual("degenerate-planar-leg", result["status"])
        self.assertFalse(result["replanSuggested"])

    def test_sparse_or_short_window_is_not_a_stall(self):
        for times in ((0, .1, .2, .3), (0, .1, 1.3, 1.5)):
            with self.subTest(times=times):
                self.assertEqual("insufficient-feedback",
                                 self.assess([(0, 10, 0)]*4, times=times)["status"])

    def test_wrong_leg_repeated_timestamp_and_missing_height_refuse(self):
        for key, value in (("legIndex", 2), ("routeHash", "foreign"), ("elapsedSeconds", 0),
                           ("position", {"x": 0, "z": 0})):
            samples = window(self.route, [(0, 10, 0)]*4)
            samples[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                assess_leg_feedback(self.route, samples, translation_expected=True)


if __name__ == "__main__":
    unittest.main()
