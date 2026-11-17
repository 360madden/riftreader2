"""Offline regression checks for selected-target / loaded-unit cross-reader agreement."""
from copy import deepcopy
import math
import unittest

from scripts.compare_selected_unit_positions import compare
from tests.test_physical_selected_position import report as selected_report, burst_report
from tests.test_physical_unit_positions import report as units_report, bits


def fixtures():
    selected = deepcopy(selected_report())
    units = deepcopy(units_report())
    obs = units["observation"]
    obs["startedAtUtc"] = "2026-11-17T19:00:00.0110000Z"
    obs["completedAtUtc"] = "2026-11-17T19:00:00.0600000Z"
    for index, row in enumerate(obs["rows"]):
        row["startedAtUtc"] = f"2026-11-17T19:00:00.0{index + 2}00000Z"
        row["completedAtUtc"] = f"2026-11-17T19:00:00.0{index + 3}00000Z"
    chosen = obs["rows"][1]
    xyz = selected["observation"]["targetPositionCandidate"]
    chosen["unitKey"] = "43"
    chosen["unitIdCandidate"] = "u000000000000002B"
    chosen["positionCandidate"] = deepcopy(xyz)
    chosen["rawBits"] = bits(xyz)
    origin = obs["selfPositionCandidate"]
    chosen["horizontalDistanceCandidate"] = math.hypot(xyz["x"]-origin["x"], xyz["z"]-origin["z"])
    return selected, units


class SelectedUnitAgreementTests(unittest.TestCase):
    def test_exact_match_with_same_process_and_close_times(self):
        selected, units = fixtures()
        result = compare(selected, units)
        self.assertEqual("exact-position-agreement-candidate", result["status"])
        self.assertEqual(0, result["positionDifference"])
        self.assertEqual("43", result["selectedTargetKeyCandidate"])
        self.assertEqual(2, result["unitsWithPosition"])
        self.assertEqual(1, result["selectedSamples"])

    def test_burst_brackets_scan_with_no_claim_of_atomicity(self):
        selected, units = fixtures()
        first = selected["observation"]
        second = deepcopy(first)
        second["startedAtUtc"] = "2026-11-17T19:00:00.0700000Z"
        second["completedAtUtc"] = "2026-11-17T19:00:00.0800000Z"
        selected.update(contractVersion="native-current-selected-position-candidate-burst/1",
                        identity=first["identity"], requestedSamples=2, completedSamples=2,
                        observations=[first, second], observation=second)
        result = compare(selected, units)
        self.assertEqual("exact-position-agreement-candidate", result["status"])
        self.assertEqual(2, result["selectedSamples"])
        self.assertIn("not atomic", result["qualification"])

        second["rawFallbackKey"] = "44"
        second["targetKey"] = "44"
        second["targetUnitIdCandidate"] = "u000000000000002C"
        result = compare(selected, units)
        self.assertEqual("selected-candidate-changed-or-unavailable", result["status"])

    def test_positions_disagree_even_when_target_key_matches(self):
        selected, units = fixtures()
        row = units["observation"]["rows"][1]
        xyz = row["positionCandidate"]
        xyz["x"] += 1
        row["rawBits"] = bits(xyz)
        origin = units["observation"]["selfPositionCandidate"]
        row["horizontalDistanceCandidate"] = math.hypot(xyz["x"]-origin["x"], xyz["z"]-origin["z"])
        result = compare(selected, units)
        self.assertEqual("position-disagreement-candidate", result["status"])
        self.assertGreater(result["positionDifference"], 0)

    def test_unseen_target_is_not_called_absent_from_world(self):
        selected, units = fixtures()
        units["observation"]["rows"].pop()
        units["observation"]["examined"] -= 1
        result = compare(selected, units)
        self.assertEqual("target-not-in-bounded-unit-scan", result["status"])

    def test_stale_separation_withholds_agreement(self):
        selected, units = fixtures()
        selected["observation"]["startedAtUtc"] = "2026-11-17T19:04:00.0000000Z"
        selected["observation"]["completedAtUtc"] = "2026-11-17T19:04:00.0100000Z"
        self.assertEqual("source-times-too-far-apart", compare(selected, units)["status"])

    def test_wrong_process_and_owner_rejected(self):
        for change in ("process", "player", "overlap", "invalid-gap"):
            selected, units = fixtures()
            if change == "process":
                selected["observation"]["identity"]["processId"] = 444
            elif change == "player":
                selected["observation"]["selfKey"] = "99"
            elif change == "overlap":
                selected["observation"]["startedAtUtc"] = "2026-11-17T20:00:00.0200000Z"
                selected["observation"]["completedAtUtc"] = "2026-11-17T20:00:00.0100000Z"
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare(selected, units, max_gap_seconds=float("inf") if change == "invalid-gap" else 120)


if __name__ == "__main__":
    unittest.main()
