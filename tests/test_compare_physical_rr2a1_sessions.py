"""Offline longitudinal RR2A1 source/coordinate qualification regressions."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import compare_physical_rr2a1_sessions as longitudinal


def session(*, x=0., z=0., sequence=100, clock=10.,
            beginning="2026-11-14T22:00:00Z",
            ending="2026-11-14T22:00:08Z", source="A"):
    xyz = {"x": x, "y": 870., "z": z}
    return {
        "summarySha256": source * 64,
        "identity": {
            "host": "AMD-DESKTOP", "processId": 21672,
            "processStartUtcTicks": "639302305454629980",
            "executableSha256": "B" * 64,
        },
        "readerSha256": "C" * 64,
        "firstStartedAtUtc": beginning,
        "lastCompletedAtUtc": ending,
        "comparison": {
            "luaPlayerIdCandidate": "u035400012FA2D207",
            "luaEpochCandidate": 1,
            "sequenceWindows": [[sequence, sequence + 1],
                                [sequence + 2, sequence + 3]],
            "clockWindows": [[clock, clock + 1.], [clock + 2., clock + 3.]],
            "positionCandidates": {"lastLua": xyz, "nativeAfter": dict(xyz)},
        },
    }


class LongitudinalCandidateTests(unittest.TestCase):
    def setUp(self):
        self.old = session()
        self.new = session(x=4., z=3., sequence=50, clock=1000.,
                           beginning="2026-11-14T23:00:00Z",
                           ending="2026-11-14T23:00:08Z", source="D")

    def test_changed_native_and_lua_coordinates_with_regressed_sequence(self):
        result = longitudinal.compare_sessions(self.old, self.new)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["producerSequenceContinuity"], "not-increasing")
        self.assertEqual(result["producerClockContinuity"], "increasing")
        self.assertEqual(result["luaEpochCandidates"], [1, 1])
        self.assertEqual(result["nativePlanarDifference"], 5.)
        self.assertEqual(result["luaPlanarDifference"], 5.)
        self.assertEqual(result["changedCoordinateScreen"],
                         "consistent-candidate-change")
        self.assertIn("No nonce-authenticated", result["qualification"])

    def test_counter_gate_rejects_sequence_rollback_even_with_advancing_clock(self):
        with patch.object(longitudinal, "replay_session",
                          side_effect=[self.old, self.new]), \
             patch("builtins.print") as printed:
            code = longitudinal.main([
                "--older", "old.json", "--newer", "new.json",
                "--require-increasing-counters"])
        self.assertEqual(code, 2)
        self.assertIn("producer-counters-not-increasing", printed.call_args.args[0])

    def test_counter_gate_accepts_only_same_epoch_increasing_counters(self):
        self.new["comparison"]["sequenceWindows"] = [[200, 201], [202, 203]]
        with patch.object(longitudinal, "replay_session",
                          side_effect=[self.old, self.new]), \
             patch("builtins.print") as printed:
            code = longitudinal.main([
                "--older", "old.json", "--newer", "new.json",
                "--require-increasing-counters"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(printed.call_args.args[0])[
            "producerCountersIncreasingCandidate"])

    def test_counter_gate_rejects_epoch_change_despite_increasing_counters(self):
        self.new["comparison"]["sequenceWindows"] = [[200, 201], [202, 203]]
        self.new["comparison"]["luaEpochCandidate"] = 2
        with patch.object(longitudinal, "replay_session",
                          side_effect=[self.old, self.new]), \
             patch("builtins.print") as printed:
            code = longitudinal.main([
                "--older", "old.json", "--newer", "new.json",
                "--require-increasing-counters"])
        self.assertEqual(code, 2)
        self.assertIn("producer-counters-not-increasing", printed.call_args.args[0])

    def test_stationary_pair_does_not_claim_change(self):
        self.new["comparison"]["positionCandidates"] = copy.deepcopy(
            self.old["comparison"]["positionCandidates"])
        result = longitudinal.compare_sessions(self.old, self.new)
        self.assertEqual(result["changedCoordinateScreen"], "not-established")

    def test_opposing_or_inconsistent_modalities_return_disagreement(self):
        self.new["comparison"]["positionCandidates"]["lastLua"]["x"] = 99.
        result = longitudinal.compare_sessions(self.old, self.new)
        self.assertEqual(result["status"], "candidate-disagreement")
        self.assertEqual(result["changedCoordinateScreen"], "disagreement")

    def test_changed_process_or_reader_never_accepted(self):
        for changed in ({"processId": 20}, {"executableSha256": "E" * 64}):
            candidate = copy.deepcopy(self.new)
            candidate["identity"].update(changed)
            with self.subTest(changed=changed), self.assertRaisesRegex(
                ValueError, "process-player-or-reader-changed"
            ):
                longitudinal.compare_sessions(self.old, candidate)
        candidate = copy.deepcopy(self.new)
        candidate["readerSha256"] = "E" * 64
        with self.assertRaisesRegex(ValueError, "process-player-or-reader-changed"):
            longitudinal.compare_sessions(self.old, candidate)

    def test_changed_player_identity_rejected(self):
        self.new["comparison"]["luaPlayerIdCandidate"] = "u0000000000000001"
        with self.assertRaisesRegex(ValueError, "process-player-or-reader-changed"):
            longitudinal.compare_sessions(self.old, self.new)

    def test_reverse_or_overlapping_observations_rejected(self):
        self.new["firstStartedAtUtc"] = self.old["lastCompletedAtUtc"]
        with self.assertRaisesRegex(ValueError, "overlap-or-reversed-captures"):
            longitudinal.compare_sessions(self.old, self.new)

    def test_same_summary_cannot_self_correlate(self):
        self.new["summarySha256"] = self.old["summarySha256"]
        with self.assertRaisesRegex(ValueError, "same-source"):
            longitudinal.compare_sessions(self.old, self.new)

    def test_nonfinite_coordinates_rejected(self):
        self.new["comparison"]["positionCandidates"]["nativeAfter"]["x"] = math.nan
        with self.assertRaisesRegex(ValueError, "nonfinite-difference"):
            longitudinal.compare_sessions(self.old, self.new)

    def test_replay_checks_original_receipts_and_fallback_native_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [root / "pass-01/scan/index.json",
                     root / "pass-02-broad/scan/index.json",
                     root / "native-before/summary.json",
                     root / "native-after/summary.json"]
            hashes = []
            for index, path in enumerate(paths):
                path.parent.mkdir(parents=True, exist_ok=True)
                data = json.dumps({"source": index}).encode()
                path.write_bytes(data)
                hashes.append(hashlib.sha256(data).hexdigest().upper())
            # A retry may only replace the second Lua pass, not the native-after
            # bracket. The replay must select that bracket by its actual SHA.
            (root / "native-after-broad").mkdir()
            (root / "native-after-broad/summary.json").write_text('{"bad":true}')
            evidence = {
                "schemaVersion": 1,
                "evidenceKind": "amd-physical-rr2a1-bracketed-two-pass/1",
                "status": "candidate-only", "ownerHost": "AMD-DESKTOP",
                "target": {"hostName": "AMD-DESKTOP", "processId": 21672,
                           "processStartUtcTicks": "639302305454629980",
                           "executableSha256": "B" * 64},
                "readerSha256": "C" * 64,
                "scanIndexSha256": {"first": hashes[0], "second": hashes[1]},
                "nativeBracketSha256": {"before": hashes[2], "after": hashes[3]},
                "secondPassFocus": {"fallbackUsed": True},
            }
            checked = {
                "status": "candidate-only",
                "coordinateAgreementScreen": {"withinTolerance": True},
                "identity": self.old["identity"],
            }
            ordering = {"status": "source-verified-order"}
            evidence["comparison"] = dict(checked, captureOrder=ordering)
            summary = root / "summary.json"
            summary.write_text(json.dumps(evidence), encoding="utf-8")
            with patch.object(longitudinal.pair, "compare",
                              return_value=checked) as paired, \
                 patch.object(longitudinal.pair, "verify_capture_order",
                              return_value=ordering), \
                 patch.object(longitudinal.native, "verified_bracket",
                              side_effect=[
                                  (None, None, "2026-11-14T22:00:00Z",
                                   "2026-11-14T22:00:01Z"),
                                  (None, None, "2026-11-14T22:00:07Z",
                                   "2026-11-14T22:00:08Z"),
                              ]):
                result = longitudinal.replay_session(summary)
            self.assertEqual(result["comparison"], evidence["comparison"])
            self.assertEqual(result["lastCompletedAtUtc"],
                             "2026-11-14T22:00:08Z")
            self.assertEqual(paired.call_args.args[-1], paths[3])

            evidence["comparison"]["status"] = "live-qualified"
            summary.write_text(json.dumps(evidence), encoding="utf-8")
            with patch.object(longitudinal.pair, "compare",
                              return_value=checked), \
                 patch.object(longitudinal.pair, "verify_capture_order",
                              return_value=ordering):
                with self.assertRaisesRegex(ValueError, "saved-comparison-mismatch"):
                    longitudinal.replay_session(summary)

            evidence["comparison"]["status"] = "candidate-only"
            summary.write_text(json.dumps(evidence), encoding="utf-8")
            paths[1].write_text('{"modified":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                longitudinal.replay_session(summary)


if __name__ == "__main__":
    unittest.main()
