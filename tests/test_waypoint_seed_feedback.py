import unittest
from types import SimpleNamespace as NS

from scripts.waypoint_seed_feedback import SeedFeedbackError, verify_translation, verify_turn


def pose(x=0, y=0, z=0, bearing=0):
    return NS(position=NS(x=x, y=y, z=z), bearing=bearing)


def receipt(key="w", hold=100):
    return {"keys": [key], "holdMilliseconds": hold, "observedMilliseconds": hold + 8,
            "inputCallTiming": {"utcOrderValid": True, "wallClockConsistentWithMonotonic": True},
            "keyHoldWindows": [{"key": key, "status": "candidate-sendinput-hold-bounds",
                "minimumMillisecondsCandidate": hold - 1, "maximumMillisecondsCandidate": hold + 1,
                "midpointMillisecondsCandidate": hold, "exactKeyDownUpTimesKnown": False,
                "gameResponseVerified": False}]}


class SeedFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.cal = NS(key="w", dx_per_ms=.002, dz_per_ms=0)

    def test_translation_valid_and_bounded_midpoint(self):
        result = verify_translation(pose(), pose(x=.2, z=.01), self.cal, receipt())
        self.assertEqual(result["holdMilliseconds"], 100)
        self.assertEqual(result["holdSource"], "sendinput-window-midpoint")

    def test_translation_wrong_or_no_response(self):
        for end in (pose(), pose(x=-.2), pose(z=.2), pose(x=.5), pose(x=.2, bearing=10)):
            with self.subTest(end=end), self.assertRaises(SeedFeedbackError):
                verify_translation(pose(), end, self.cal, receipt())

    def test_translation_rejects_receipt_for_another_key(self):
        with self.assertRaises(SeedFeedbackError):
            verify_translation(pose(), pose(x=.2), self.cal, receipt("q"))

    def test_short_translation_and_bad_timing(self):
        self.assertGreater(verify_translation(pose(), pose(x=.035), self.cal, receipt(hold=20))["alongDistance"], 0)
        bad = receipt()
        bad["keyHoldWindows"][0]["midpointMillisecondsCandidate"] = 150
        with self.assertRaises(SeedFeedbackError):
            verify_translation(pose(), pose(x=.2), self.cal, bad)
        bad = receipt()
        bad["inputCallTiming"]["utcOrderValid"] = False
        with self.assertRaises(SeedFeedbackError):
            verify_translation(pose(), pose(x=.2), self.cal, bad)

    def test_turn_good_wrap_and_short(self):
        result = verify_turn(pose(bearing=175), pose(bearing=-165), "a", .2, receipt("a"))
        self.assertEqual(result["observedDegrees"], 20)
        verify_turn(pose(), pose(bearing=-4), "d", -.2, receipt("d", 20))

    def test_turn_wrong_no_response_or_drift(self):
        for end in (pose(), pose(bearing=-20), pose(bearing=50), pose(x=.2, bearing=20)):
            with self.subTest(end=end), self.assertRaises(SeedFeedbackError):
                verify_turn(pose(), end, "a", .2, receipt("a"))

    def test_legacy_timing_and_key_mismatch(self):
        r = receipt()
        del r["keyHoldWindows"]
        self.assertEqual(verify_translation(pose(), pose(x=.2), self.cal, r)["holdSource"], "executor-observed")
        with self.assertRaises(SeedFeedbackError):
            verify_turn(pose(), pose(bearing=20), "a", .2, r)


if __name__ == "__main__":
    unittest.main()
