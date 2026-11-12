"""Offline tests for two-pass RR2A1 Lua/native replay. No live process reads."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_physical_rr2a1_passes as pair


def pass_report(start, end, *, epoch=1, scan="A", clock_start=10.0,
                player="u035400012FA2D207"):
    return {
        "status": "candidate-only",
        "luaProtocol": "RR2A1-unbound",
        "identity": {"host": "AMD-DESKTOP", "processId": 123,
                     "processStartUtcTicks": "638000000000000001",
                     "executableSha256": "B" * 64},
        "luaPlayerIdCandidate": player,
        "luaEpochCandidate": epoch,
        "luaFrameCount": 2,
        "firstSequence": start,
        "lastSequence": end,
        "firstClockCandidate": clock_start,
        "lastClockCandidate": clock_start + 1.0,
        "luaPositionCandidates": [{"x": 10., "y": 20., "z": 30.},
                                  {"x": 10.002, "y": 20., "z": 30.}],
        "nativePositionCandidate": {"x": 10., "y": 20., "z": 30.},
        "maxAbsCoordinateDifferenceCandidate": {"x": .002, "y": 0., "z": 0.},
        "frameEvidence": [{"frameSha256": f"{scan}{start}"},
                          {"frameSha256": f"{scan}{end}"}],
        "sourceSha256": {"scanIndex": scan * 64, "scanRequest": "C" * 64,
                         "nativeBracketSummary": "D" * 64},
    }


class TwoPassTests(unittest.TestCase):
    def sample(self):
        return pass_report(1, 2, scan="A"), pass_report(3, 4, scan="B",
                                                          clock_start=20.0)

    def test_independent_advancing_passes_stay_candidate_only(self):
        a, b = self.sample()
        with patch.object(pair.lua, "replay", side_effect=[a, b]) as replay:
            output = pair.compare("first-index", "second-index", "native")
        self.assertEqual(replay.call_count, 2)
        self.assertEqual(output["frameCounts"], [2, 2])
        self.assertEqual(output["sequenceWindows"], [[1, 2], [3, 4]])
        self.assertEqual(output["luaEpochCandidate"], 1)
        self.assertAlmostEqual(output["betweenPassLuaXYZDifferenceCandidate"]["x"], -.002)
        self.assertEqual(output["coordinateAgreementScreen"]["result"], "consistent")
        self.assertTrue(output["coordinateAgreementScreen"]["withinTolerance"])
        self.assertEqual(output["status"], "candidate-only")
        self.assertIn("remains unbound", output["qualification"])

    def test_rejects_changed_epoch_and_identity(self):
        for mutation, error in (
            ({"luaEpochCandidate": 2}, "lua-epoch-changed"),
            ({"luaPlayerIdCandidate": "u0000000000000001"},
             "process-or-player-identity-changed"),
        ):
            a, b = self.sample()
            b.update(mutation)
            with self.subTest(mutation=mutation), patch.object(
                    pair.lua, "replay", side_effect=[a, b]):
                with self.assertRaisesRegex(ValueError, error):
                    pair.compare("a", "b", "native")

    def test_rejects_nonadvancing_passes_or_duplicate_sources(self):
        a, b = self.sample()
        for mutation, error in (
            ({"firstSequence": 2}, "nonadvancing-or-overlapping"),
            ({"firstClockCandidate": 11.0}, "nonadvancing-or-overlapping"),
            ({"sourceSha256": deepcopy(a["sourceSha256"])}, "same-scan-source"),
            ({"frameEvidence": deepcopy(a["frameEvidence"])}, "reused-frame"),
        ):
            left, right = deepcopy(a), deepcopy(b)
            right.update(mutation)
            with self.subTest(mutation=mutation), patch.object(
                    pair.lua, "replay", side_effect=[left, right]):
                with self.assertRaisesRegex(ValueError, error):
                    pair.compare("a", "b", "native")

    def test_large_coordinate_gap_does_not_claim_correspondence(self):
        a, b = self.sample()
        b["luaPositionCandidates"][0]["x"] += .5
        b["maxAbsCoordinateDifferenceCandidate"]["x"] = .5
        with patch.object(pair.lua, "replay", side_effect=[a, b]):
            output = pair.compare("a", "b", "native")
        self.assertEqual(output["status"], "candidate-disagreement")
        self.assertFalse(output["coordinateAgreementScreen"]["withinTolerance"])
        self.assertIn("not demonstrated", output["qualification"])
        self.assertNotIn("matching native player ID and XYZ", output["qualification"])

    def test_disagreement_cli_returns_nonzero_with_preserved_evidence(self):
        a, b = self.sample()
        b["maxAbsCoordinateDifferenceCandidate"]["z"] = .051
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                pair.lua, "replay", side_effect=[a, b]):
            receipt = Path(tmp) / "disagreement.json"
            rc = pair.main(["--first-index", "first",
                            "--second-index", "second",
                            "--first-native-bracket", "native",
                            "--output", str(receipt)])
            self.assertEqual(rc, 2)
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "candidate-disagreement")
            self.assertEqual(saved["coordinateAgreementScreen"]["result"],
                             "disagreement")

    def test_nonfinite_or_negative_coordinate_gaps_rejected(self):
        for gap in (float("nan"), float("inf"), -.01):
            a, b = self.sample()
            b["maxAbsCoordinateDifferenceCandidate"]["x"] = gap
            with self.subTest(gap=gap), patch.object(
                    pair.lua, "replay", side_effect=[a, b]):
                with self.assertRaisesRegex(ValueError, "invalid-coordinate-gap"):
                    pair.compare("a", "b", "native")

    def test_bracketed_order_accepts_independent_sequential_receipts(self):
        times = [f"2026-11-12T03:33:{sec:02d}.0000000Z"
                 for sec in (32, 33, 34, 35, 36, 38)]
        first = {"startedAtUtc": times[1], "completedAtUtc": times[2]}
        second = {"startedAtUtc": times[3], "completedAtUtc": times[4]}
        with patch.object(pair.native, "verified_bracket", side_effect=[
                ({}, "a", times[0], times[0]),
                ({}, "b", times[5], times[5])]), \
             patch.object(pair.context, "load", side_effect=[(first, "c"),
                                                              (second, "d")]):
            result = pair.verify_capture_order("index1", "index2", "native1", "native2")
        self.assertEqual(result["status"], "source-verified-order")
        self.assertEqual(result["observedUtc"]["nativeBeforeCompleted"], times[0])
        self.assertIn("not atomic", result["qualification"])

    def test_bracketed_order_rejects_overlap_missing_and_reversed_times(self):
        base = [f"2026-11-12T03:33:{sec:02d}.0000000Z"
                for sec in (32, 33, 34, 35, 36, 38)]
        for index, value, reason in (
                (1, base[0], "overlapping-or-reordered"),
                (2, base[3], "overlapping-or-reordered"),
                (4, base[3], "overlapping-or-reordered"),
                (5, base[4], "overlapping-or-reordered"),
                (1, None, "missing-capture-timestamps"),
                (3, "not-a-date", "invalid-capture-timestamps")):
            times = base.copy()
            times[index] = value
            first = {"startedAtUtc": times[1], "completedAtUtc": times[2]}
            second = {"startedAtUtc": times[3], "completedAtUtc": times[4]}
            with self.subTest(index=index, value=value), \
                 patch.object(pair.native, "verified_bracket", side_effect=[
                     ({}, "a", times[0], times[0]),
                     ({}, "b", times[5], times[5])]), \
                 patch.object(pair.context, "load", side_effect=[(first, "c"),
                                                                  (second, "d")]):
                with self.assertRaisesRegex(ValueError, reason):
                    pair.verify_capture_order("index1", "index2", "native1", "native2")

    def test_replay_failure_propagates_and_existing_output_preserved(self):
        a, b = self.sample()
        with patch.object(pair.lua, "replay",
                          side_effect=ValueError("source-sha-mismatch")):
            with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                pair.compare("a", "b", "native")
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "exists.json"
            existing.write_text("preserve", encoding="utf-8")
            self.assertEqual(pair.main([
                "--first-index", "a", "--second-index", "b",
                "--first-native-bracket", "native",
                "--output", str(existing)]), 2)
            self.assertEqual(existing.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
