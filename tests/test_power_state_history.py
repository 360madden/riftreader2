"""Offline Power history tests independent of retained host-specific captures."""
from copy import deepcopy
import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from scripts import replay_physical_player_state as replay


def capture(index, currents=None, maxima=None):
    value = {
        "status": "candidate-only",
        "evidenceKind": "amd-physical-player-state-replay/1",
        "summarySha256": str(index), "target": {"processId": 42},
        "moduleBaseAddress": 1000, "moduleSize": 500,
        "selfKeyCandidate": "123", "sources": {},
        "firstStartedAtUtc": f"2026-11-26T08:00:{index*5:02d}Z",
        "lastCompletedAtUtc": f"2026-11-26T08:00:{index*5+4:02d}Z",
        "candidateValues": {"position": {"x": 0, "y": 0, "z": 0},
                            "vitals": {"health": {"status": "calculated-candidate", "current": 100}}},
    }
    if currents is not None:
        value["powerBracketCandidate"] = {
            "status": "matching-warrior-context-candidates",
            "selfKeyCandidate": "123", "nativePowerUnitKeyStatus": "unavailable",
        }
        maxima = maxima if maxima is not None else [100] * len(currents)
        value["candidateValues"]["power"] = {
            "status": "candidate", "recipe": "test-recipe",
            "samples": [{"current": c, "maximum": m} for c, m in zip(currents, maxima)],
        }
    return value


class PowerHistoryTests(unittest.TestCase):
    def history(self, *captures):
        with patch.object(replay, "verified_state", side_effect=captures):
            return replay.history(["unused"] * len(captures))

    def test_transient_drop_and_recovery_not_hidden_by_equal_endpoints(self):
        a, b = capture(0, [100, 20, 100]), capture(1, [100, 100])
        pair = replay._compare_states(a, b)["nativePowerComparison"]
        self.assertEqual(pair["status"], "comparable-candidate")
        self.assertEqual(pair["endpointCurrentDeltaCandidate"], 0)
        self.assertEqual(pair["before"]["minimumCurrentCandidate"], 20)
        self.assertEqual(pair["before"]["withinBurstChangedPairs"], 2)
        result = self.history(a, b)["nativePowerHistory"]
        self.assertEqual(result["minimumCurrentCandidate"], 20)
        self.assertEqual(result["sampleCount"], 5)
        self.assertEqual(result["withinBurstChangedPairs"], 2)
        self.assertEqual(result["netEndpointCurrentDeltaCandidate"], 0)

    def test_maximum_changes_and_boundary_differences_are_separate(self):
        a, b = capture(0, [70, 80]), capture(1, [60, 90], [120, 130])
        pair = replay._compare_states(a, b)["nativePowerComparison"]
        self.assertEqual(pair["boundaryCurrentDeltaCandidate"], -20)
        self.assertEqual(pair["endpointCurrentDeltaCandidate"], 10)
        self.assertEqual(pair["boundaryMaximumDeltaCandidate"], 20)
        self.assertEqual(pair["after"]["withinBurstMaximumChangedPairs"], 1)
        self.assertIn("cause", pair["qualification"])

    def test_missing_capture_is_not_bridged_or_counted_as_zero(self):
        result = self.history(capture(0, [50, 40]), capture(1), capture(2, [80, 100]))
        power = result["nativePowerHistory"]
        self.assertEqual(power["status"], "partial-candidate")
        self.assertEqual(power["capturesWithPower"], 2)
        self.assertEqual(power["capturesWithoutPower"], 1)
        self.assertEqual(power["sampleCount"], 4)
        self.assertEqual(power["comparableSegments"], 0)
        self.assertIsNone(power["netEndpointCurrentDeltaCandidate"])
        self.assertEqual([row["nativePowerComparison"]["status"] for row in result["segments"]],
                         ["partial-candidate", "partial-candidate"])

    def test_no_power_stays_explicitly_uncaptured(self):
        result = self.history(capture(0), capture(1))["nativePowerHistory"]
        self.assertEqual(result["status"], "not-captured")
        self.assertEqual(result["sampleCount"], 0)
        self.assertIsNone(result["minimumCurrentCandidate"])
        self.assertIsNone(result["netEndpointCurrentDeltaCandidate"])

    def test_incompatible_recipe_does_not_claim_numeric_continuity(self):
        a, b = capture(0, [20, 30]), capture(1, [40, 50])
        b["candidateValues"]["power"]["recipe"] = "different"
        pair = replay._compare_states(a, b)["nativePowerComparison"]
        self.assertEqual(pair["status"], "incompatible-recipe")
        self.assertNotIn("endpointCurrentDeltaCandidate", pair)

    def test_existing_epoch_guard_and_context_bracket_still_required(self):
        a, b = capture(0, [20, 30]), capture(1, [40, 50])
        changed = deepcopy(b)
        changed["target"]["processId"] = 43
        with self.assertRaisesRegex(ValueError, "owner-or-epoch-changed"):
            replay._compare_states(a, changed)
        b["powerBracketCandidate"]["selfKeyCandidate"] = "999"
        with self.assertRaisesRegex(ValueError, "power-context-bracket-unavailable"):
            replay._compare_states(a, b)

    def test_single_cli_summary_exposes_captured_power_without_extra_reads(self):
        value = capture(0, [80, 60])
        with patch.object(replay, "verified_state", return_value=value), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(replay.main(["--summary", "unused"]), 0)
        self.assertEqual(json.loads(out.getvalue())["nativePowerCandidate"]["lastCurrentCandidate"], 60)


if __name__ == "__main__":
    unittest.main()
