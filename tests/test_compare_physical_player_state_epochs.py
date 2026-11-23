"""Offline cross-restart comparison regressions."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from scripts import compare_physical_player_state_epochs as mod


def sample(pid, sha, when, hp=100):
    return {
        "summarySha256": sha,
        "target": {"hostName": "RIFT-STATION", "processId": pid, "processStartUtcTicks": str(pid*100),
                   "executableSha256": mod.replay.state.BUILD_SHA},
        "firstStartedAtUtc": f"2026-11-12T12:00:{when:02d}+00:00",
        "lastCompletedAtUtc": f"2026-11-12T12:00:{when+1:02d}+00:00",
        "selfKeyCandidate": "123",
        "candidateValues": {
            "position": {"x": float(pid), "y": 3., "z": float(pid+5)},
            "vitals": {"health": {"status": "calculated-candidate", "current": hp}},
        },
    }


def add_armor_stats(state, *, ordinary=100, mapped_index=0):
    state["candidateValues"]["stats"] = {
        "status": "candidate-only", "selectorCount": 1,
        "stats": [{"name": "armor", "selector": 37, "mappedIndex": mapped_index,
                   "ordinary": {"status": "raw-candidate", "rawSigned64": ordinary},
                   "unbuffed": {"status": "raw-candidate", "rawSigned64": 100}}],
    }


class CrossEpochTests(unittest.TestCase):
    def run_pair(self, mutate=None):
        a, b = sample(100, "A", 0), sample(200, "B", 4, 95)
        if mutate:
            mutate(a, b)
        with patch.object(mod.replay, "verified_state", side_effect=[a, b]):
            return mod.compare("a", "b")

    def test_uncorrelated_math_and_source_provenance(self):
        result = self.run_pair()
        self.assertEqual(result["uncorrelatedNumericXYZDifference"],
                         {"x": 100., "y": 0., "z": 100.})
        self.assertEqual(result["uncorrelatedNumericHealthDifference"], -5)
        self.assertEqual(result["beforeSummarySha256"], "A")
        self.assertEqual(result["afterEpoch"]["processId"], 200)
        self.assertIn("NOT verified movement", result["qualification"])

    def test_no_zone_brackets_preserves_explicit_unavailability(self):
        self.assertEqual(self.run_pair()["crossEpochZoneCandidateComparison"],
                         {"status": "not-comparable", "reason": "one-or-both-zone-brackets-not-captured"})

    def test_changed_zone_candidates_across_epochs_are_not_world_proof(self):
        def mutate(a, b):
            a["zoneBracketCandidate"] = {"status": "matching-candidates",
                                          "zoneIdCandidate": "z0000000CB7B53FD7", "rawZoneKey": 12}
            b["zoneBracketCandidate"] = {"status": "matching-candidates",
                                          "zoneIdCandidate": "z487C9102D2EA79BE", "rawZoneKey": 1216123138}
        value = self.run_pair(mutate)["crossEpochZoneCandidateComparison"]
        self.assertEqual(value["status"], "different-id-candidates")
        self.assertEqual(value["beforeRawZoneKey"], 12)
        self.assertEqual(value["afterZoneIdCandidate"], "z487C9102D2EA79BE")
        self.assertEqual(value["worldInstanceStatus"], "unavailable")
        self.assertIn("not a continuous world identity", value["qualification"])

    def test_matching_zone_strings_across_epochs_remain_candidate_only(self):
        def mutate(a, b):
            for item in (a, b):
                item["zoneBracketCandidate"] = {"status": "matching-candidates",
                                                "zoneIdCandidate": "z0000000CB7B53FD7", "rawZoneKey": 12}
        result = self.run_pair(mutate)["crossEpochZoneCandidateComparison"]
        self.assertEqual(result["status"], "matching-id-candidates")
        self.assertEqual(result["worldInstanceStatus"], "unavailable")

    def test_invalid_zone_bracket_refused(self):
        def mutate(a, b):
            a["zoneBracketCandidate"] = {"status": "claimed-world-proof", "zoneIdCandidate": "zBAD"}
            b["zoneBracketCandidate"] = {"status": "matching-candidates", "zoneIdCandidate": "zOK"}
        with self.assertRaisesRegex(ValueError, "invalid-zone-bracket"):
            self.run_pair(mutate)

    def test_different_self_keys_not_mistaken_for_continuity(self):
        self.assertFalse(self.run_pair(
            lambda a,b: b.update(selfKeyCandidate="999"))["selfKeysNumericallyEqual"])

    def test_stats_compare_matching_raw_slots_as_numeric_differences(self):
        def mutate(a, b):
            add_armor_stats(a)
            add_armor_stats(b, ordinary=106)

        value = self.run_pair(mutate)["crossEpochNativeStatsComparison"]
        self.assertEqual(value["status"], "comparable-candidate")
        self.assertEqual(value["rawValuesCompared"], 2)
        self.assertEqual(value["rawValuesDiffering"], 1)
        self.assertEqual(value["differences"], [
            {"name": "armor", "variant": "ordinary", "beforeRawSigned64": 100,
             "afterRawSigned64": 106, "rawNumericDifference": 6},
        ])

    def test_stats_with_different_owner_or_layout_are_not_compared(self):
        def different_player(a, b):
            add_armor_stats(a)
            add_armor_stats(b, ordinary=106)
            b["selfKeyCandidate"] = "456"

        def different_layout(a, b):
            add_armor_stats(a)
            add_armor_stats(b, mapped_index=5)

        self.assertEqual(self.run_pair(different_player)["crossEpochNativeStatsComparison"],
                         {"status": "not-comparable", "reason": "different-self-key-candidates"})
        self.assertEqual(self.run_pair(different_layout)["crossEpochNativeStatsComparison"],
                         {"status": "incompatible-selector-layout"})

    def test_stats_report_missing_and_unavailable_sources(self):
        def unavailable_slot(a, b):
            add_armor_stats(a)
            add_armor_stats(b)
            b["candidateValues"]["stats"]["stats"][0]["unbuffed"] = {"status": "index-unavailable"}

        self.assertEqual(self.run_pair(lambda a, b: add_armor_stats(a))["crossEpochNativeStatsComparison"],
                         {"status": "not-captured"})
        value = self.run_pair(unavailable_slot)["crossEpochNativeStatsComparison"]
        self.assertEqual(value["rawValuesCompared"], 1)
        self.assertEqual(value["rawValuesUnavailable"], 1)
        self.assertEqual(value["rawValuesDiffering"], 0)

    def test_reject_same_epoch(self):
        with self.assertRaisesRegex(ValueError, "same-epoch-use-history"):
            self.run_pair(lambda a,b: b.update(target=copy.deepcopy(a["target"])))

    def test_reject_changed_build(self):
        with self.assertRaisesRegex(ValueError, "different-build"):
            self.run_pair(lambda a,b: b["target"].update(executableSha256="F"*64))

    def test_reject_cross_host_restart_comparison(self):
        with self.assertRaisesRegex(ValueError, "different-host"):
            self.run_pair(lambda a,b: b["target"].update(hostName="OTHER-PC"))

    def test_reject_overlap(self):
        with self.assertRaisesRegex(ValueError, "captures-overlap-or-reversed"):
            self.run_pair(lambda a,b: b.update(firstStartedAtUtc=a["lastCompletedAtUtc"]))

    def test_reject_same_source(self):
        with self.assertRaisesRegex(ValueError, "same-source"):
            self.run_pair(lambda a,b: b.update(summarySha256="A"))

    def test_unknown_health_is_null(self):
        result = self.run_pair(lambda a,b: b["candidateValues"]["vitals"].update(
            health={"status": "unavailable", "current": None}))
        self.assertIsNone(result["uncorrelatedNumericHealthDifference"])

    def test_reject_nonfinite_difference(self):
        with self.assertRaisesRegex(ValueError, "nonfinite-difference"):
            self.run_pair(lambda a,b: (
                a["candidateValues"]["position"].update(x=-1e308),
                b["candidateValues"]["position"].update(x=1e308)))

    def test_never_selects_running_process(self):
        with patch.object(mod.replay, "verified_state", side_effect=[
            sample(100,"A",0), sample(200,"B",4)]), patch.object(
                mod.replay.state.physical_rift,"select_physical") as live:
            mod.compare("a","b")
            live.assert_not_called()

    def test_cli_nonoverwriting_output(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)/"result.json"
            with patch.object(mod.replay, "verified_state", side_effect=[
                sample(100,"A",0), sample(200,"B",4)]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(mod.main(["--before","old","--after","new",
                                               "--output",str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["status"], "candidate-only")
            with redirect_stdout(io.StringIO()) as result:
                self.assertEqual(mod.main(["--before","old","--after","new",
                                           "--output",str(output)]), 2)
            self.assertIn("output-exists",result.getvalue())


if __name__=="__main__":
    unittest.main()
