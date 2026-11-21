"""Offline target-series tests: no RIFT process or keyboard input."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import replay_physical_telemetry_target_series as series

A = "u00000000000000A1"
B = "u00000000000000B2"
SELF = "u035400012FA2D207"
BUILD = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"


def report(seq, target=None, number=1, *, first=None, source_status=None):
    return {
        "qualificationStatus": "candidate-only",
        "status": source_status or ("no-target-baseline-candidate" if target is None
                                    else "selected-target-observations-candidate"),
        "processId": 37676, "processStartUtcTicks": "639308565554559088",
        "executableSha256": BUILD, "playerUnitId": SELF,
        "zoneIdCandidate": "z0000000CB7B53FD7",
        "sourceEpoch": 52, "sourceSessionId": "a" * 32,
        "evidenceSummarySha256": f"{number:064X}",
        "firstSequence": seq - 3 if first is None else first,
        "lastSequence": seq, "observedFrameCount": 4,
        "runs": [{"targetUnitIdCandidate": target,
                  "firstSequence": seq - 3 if first is None else first,
                  "lastSequence": seq}],
        "nativeTargetComparison": {"status": "matching-endpoint-candidates"},
    }


class TargetSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for i in range(1, 5):
            path = Path(self.tmp.name) / f"capture-{i}.json"
            path.write_text("{}", encoding="utf-8")
            self.paths.append(path)

    def call(self, rows):
        calls = []

        def replay(path):
            calls.append(path)
            return deepcopy(rows[len(calls) - 1])

        result = series.combine(self.paths[:len(rows)], replay=replay)
        self.assertEqual(calls, self.paths[:len(rows)])
        return result

    def test_actual_a_b_a_endpoints_are_explicitly_candidate_only(self):
        outcome = self.call([report(10, A, 1), report(20, B, 2),
                             report(30, A, 3)])
        self.assertEqual(outcome["status"], "a-b-a-across-captures-candidate")
        self.assertEqual(outcome["aBaAcrossCaptures"], [{
            "targetACandidate": A, "targetBCandidate": B,
            "firstCapture": 1, "secondCapture": 2, "returnCapture": 3}])
        self.assertEqual(outcome["captureCount"], 3)
        self.assertFalse(outcome["inputSent"])
        self.assertEqual(outcome["qualificationStatus"], "candidate-only")
        self.assertIn("Intermediate target changes are unknown", outcome["qualification"])

    def test_no_target_baseline_across_two_verified_windows(self):
        result = self.call([report(10, None, 1), report(20, None, 2)])
        self.assertEqual(result["status"], "no-target-continuity-candidate")
        self.assertEqual(result["aBaAcrossCaptures"], [])
        self.assertEqual(result["lastObservedTargetRuns"], [{
            "targetUnitIdCandidate": None, "firstCapture": 1, "lastCapture": 2}])

    def test_unobserved_gaps_are_reported_not_fabricated_as_continuity(self):
        result = self.call([report(10, A, 1, first=7),
                            report(30, B, 2, first=26)])
        self.assertEqual(result["unobservedSequenceGapCount"], 1)
        self.assertEqual(result["captures"][1]["unobservedSequenceGapFromPrior"], 15)
        self.assertEqual(result["aBaAcrossCaptures"], [])

    def test_source_epoch_player_build_zone_session_and_pid_mismatches(self):
        baseline = report(10, A, 1)
        for field, value in [
            ("processId", 3), ("processStartUtcTicks", "456"),
            ("executableSha256", "B" * 64),
            ("playerUnitId", B), ("zoneIdCandidate", "z" + "0"*16),
            ("sourceEpoch", 53), ("sourceSessionId", "f" * 32),
        ]:
            with self.subTest(field=field):
                changed = report(20, B, 2)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, "process-player-zone-or-publisher-changed"):
                    self.call([baseline, changed])

    def test_replayed_source_hash_cannot_be_reused(self):
        a, b = report(10, A, 1), report(20, B, 1)
        with self.assertRaisesRegex(ValueError, "source-hash-missing-or-reused"):
            self.call([a, b])

    def test_static_or_reversed_source_sequence_is_rejected(self):
        for seq in (10, 9):
            with self.subTest(seq=seq):
                with self.assertRaisesRegex(ValueError, "no-new-advancing-source-sequence"):
                    self.call([report(10, A, 1), report(seq, B, 2)])

    def test_unqualified_forged_or_malformed_replay_refused(self):
        failures = [
            ("qualificationStatus", "unqualified"),
            ("status", "unqualified"),
            ("lastSequence", "20"),
            ("runs", []),
            ("evidenceSummarySha256", "not-a-hash"),
        ]
        for field, value in failures:
            with self.subTest(field=field):
                bad = report(20, B, 2)
                bad[field] = value
                with self.assertRaises(ValueError):
                    self.call([report(10, A, 1), bad])

    def test_bad_summary_list_and_missing_source_refused(self):
        with self.assertRaisesRegex(ValueError, "requires-2-to-16-captures"):
            series.combine(self.paths[:1], replay=lambda _: None)
        with self.assertRaisesRegex(ValueError, "requires-2-to-16-captures"):
            series.combine(self.paths * 5, replay=lambda _: None)
        with self.assertRaisesRegex(ValueError, "source-file-unavailable"):
            series.combine([self.paths[0], self.paths[0].parent / "missing.json"],
                           replay=lambda path: report(10, A, 1))

    def test_current_physical_saved_bundles_replay_when_present(self):
        root = Path(__file__).resolve().parents[1]
        old = root / "artifacts/physical-telemetry-target-20261121-0835-p37676/summary.json"
        new = root / "artifacts/physical-telemetry-target-autolocate-20261121-p37676-01/summary.json"
        if not old.is_file() or not new.is_file():
            self.skipTest("Original ignored same-machine physical evidence unavailable")
        result = series.combine([old, new])
        self.assertEqual(result["captureCount"], 2)
        self.assertEqual(result["status"], "no-target-continuity-candidate")
        self.assertEqual(result["runtimeIdentity"]["processId"], 37676)
        self.assertEqual(result["aBaAcrossCaptures"], [])


if __name__ == "__main__":
    unittest.main()
