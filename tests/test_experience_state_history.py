"""Offline history tests for source-verified Experience projections.

Synthetic captures exercise comparison semantics; they are not live XP awards
or level-up evidence. Bundle integrity is tested by the composite replay suite.
"""
from copy import deepcopy
import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from scripts import replay_physical_player_state as replay
from scripts.sample_current_native_experience_values import project_values
from tests.test_native_experience_values_validation import updated_fixture
from tests.test_power_state_history import capture


def xp_capture(index, *, level=45, accumulated=300, needed=500, baseline=1200,
               limit=65, rested=0, unavailable=False):
    result = capture(index)
    report = updated_fixture()
    observation = report["observation"]
    observation["seed"]["unitKey"] = int(result["selfKeyCandidate"])
    selected = observation["seed"]["selected"]
    selected.update(rawDword24=level, rawInt64_18=baseline + accumulated - needed)
    observation.update(level=level, limit=limit, baseline=baseline,
                       valueStatus="raw-values-candidate", mode=2, needed=needed,
                       accumulatedCandidate=accumulated)
    if rested is None:
        observation.update(restedStatus="provider-uninitialized", restedFlag=None,
                           restedRawBits=None, restedCandidate=None)
    elif rested != 0:
        import struct
        bits = struct.unpack("<I", struct.pack("<f", rested))[0]
        observation.update(restedFlag=0, restedRawBits=bits, restedCandidate=rested)
    if unavailable:
        observation.update(valueStatus="provider-uninitialized", mode=None,
                           needed=None, accumulatedCandidate=None)
    result["candidateValues"]["experience-values"] = project_values(report)
    return result


class ExperienceHistoryTests(unittest.TestCase):
    def history(self, *captures):
        with patch.object(replay, "verified_state", side_effect=captures):
            return replay.history(["unused"] * len(captures))

    def compare(self, a, b):
        return replay._compare_states(a, b)["nativeExperienceComparison"]

    def test_same_level_numeric_gain_and_rested_difference(self):
        a = xp_capture(0, accumulated=100, rested=50)
        b = xp_capture(1, accumulated=300, rested=20)
        pair = self.compare(a, b)
        self.assertEqual("comparable-candidate", pair["status"])
        self.assertEqual(200, pair["withinLevelXpDeltaCandidate"])
        self.assertAlmostEqual(0.4, pair["progressFractionDeltaCandidate"])
        self.assertEqual(-30, pair["rawRestedDeltaCandidate"])
        self.assertEqual(0, pair["levelDeltaCandidate"])

    def test_level_transition_preserves_level_difference_not_xp_gain(self):
        a = xp_capture(0, accumulated=490)
        b = xp_capture(1, level=46, accumulated=10, baseline=1800, needed=600)
        pair = self.compare(a, b)
        self.assertEqual("level-transition-candidate", pair["status"])
        self.assertEqual(1, pair["levelDeltaCandidate"])
        self.assertIsNone(pair["withinLevelXpDeltaCandidate"])
        self.assertIsNone(pair["progressFractionDeltaCandidate"])
        history = self.history(a, b)["nativeExperienceHistory"]
        self.assertEqual(1, history["levelTransitionCandidates"])
        self.assertIsNone(history["netWithinLevelXpDeltaCandidate"])

    def test_parameter_change_invalidates_within_level_delta(self):
        for change in ({"needed": 600}, {"baseline": 1300}, {"limit": 66}):
            with self.subTest(change=change):
                pair = self.compare(xp_capture(0), xp_capture(1, **change))
                self.assertEqual("progression-parameters-changed", pair["status"])
                self.assertIsNone(pair["withinLevelXpDeltaCandidate"])

    def test_missing_or_partial_experience_does_not_bridge_gap(self):
        a, b, c = xp_capture(0, accumulated=100), capture(1), xp_capture(2, accumulated=300)
        history = self.history(a, b, c)["nativeExperienceHistory"]
        self.assertEqual("partial-candidate", history["status"])
        self.assertEqual(2, history["capturesWithExperience"])
        self.assertEqual(1, history["capturesWithoutExperience"])
        self.assertEqual(0, history["comparableSegments"])
        self.assertIsNone(history["sumComparableWithinLevelDeltasCandidate"])
        self.assertIsNone(history["netWithinLevelXpDeltaCandidate"])
        pair = self.compare(a, xp_capture(1, unavailable=True))
        self.assertEqual("partial-candidate", pair["status"])
        self.assertIsNone(pair["withinLevelXpDeltaCandidate"])

    def test_anomalous_fraction_remains_incomparable(self):
        pair = self.compare(xp_capture(0), xp_capture(1, accumulated=-1))
        self.assertEqual("partial-candidate", pair["status"])
        self.assertIsNone(pair["withinLevelXpDeltaCandidate"])

    def test_negative_and_zero_deltas_not_hidden_by_net_gain(self):
        history = self.history(xp_capture(0, accumulated=100),
                               xp_capture(1, accumulated=300),
                               xp_capture(2, accumulated=200),
                               xp_capture(3, accumulated=200))["nativeExperienceHistory"]
        self.assertEqual("comparable-candidate", history["status"])
        self.assertEqual(1, history["positiveDeltaSegments"])
        self.assertEqual(1, history["negativeDeltaSegments"])
        self.assertEqual(1, history["unchangedSegments"])
        self.assertEqual(100, history["netWithinLevelXpDeltaCandidate"])

    def test_no_experience_is_explicitly_not_captured(self):
        result = self.history(capture(0), capture(1))
        xp = result["nativeExperienceHistory"]
        self.assertEqual("not-captured", xp["status"])
        self.assertEqual(0, xp["capturesWithExperience"])
        self.assertIsNone(xp["netWithinLevelXpDeltaCandidate"])

    def test_rested_absence_and_existing_epoch_guard(self):
        a, b = xp_capture(0, rested=None), xp_capture(1)
        self.assertIsNone(self.compare(a, b)["rawRestedDeltaCandidate"])
        b["target"]["processId"] = 43
        with self.assertRaisesRegex(ValueError, "owner-or-epoch-changed"):
            self.compare(a, b)

    def test_cli_history_exposes_the_new_analysis(self):
        with patch.object(replay, "verified_state",
                          side_effect=[xp_capture(0), xp_capture(1)]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0, replay.main(["--summary", "old", "--history", "new"]))
        self.assertEqual(1, json.loads(out.getvalue())["nativeExperienceHistory"]["unchangedSegments"])


if __name__ == "__main__":
    unittest.main()
