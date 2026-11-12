"""Slow-direction segmentation regression using the real route controller."""
import threading
import unittest

from scripts.physical_waypoints import run_route
from tests.test_physical_waypoints import SimulatedRift


class SlowSegmentsTests(unittest.TestCase):
    def test_backward_route_arrives_without_exceeding_segment_budgets(self):
        sim = SimulatedRift()  # S is half the W speed, .003 vs .006 units/ms.
        result = run_route(sim, [("Back", 0, -3.3)], threading.Event())[0]
        self.assertEqual(result["status"], "arrived")
        self.assertLessEqual(result["distance"], .30)
        self.assertGreater(len(result["segments"]), 1)
        for segment in result["segments"]:
            self.assertLessEqual(segment["movementPulses"], 6)
            self.assertLessEqual(segment["totalHoldMs"], 900)
            self.assertLessEqual(segment["elapsedSeconds"], 12)
        self.assertLessEqual(result["pulses"], 64)
        self.assertLessEqual(result["totalHoldMs"], 9000)
        self.assertTrue(all(action.key == "s" for action, _ in sim.calls))


if __name__ == "__main__": unittest.main()
