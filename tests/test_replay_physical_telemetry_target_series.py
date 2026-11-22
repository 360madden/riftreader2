"""Offline target-series tests: no RIFT process or keyboard input."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
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


def report(seq, target=None, number=1, *, first=None, source_status=None,
           source_frames=None):
    start = seq - 3 if first is None else first
    if source_frames is None:
        keys = sorted({start, start + 1, seq - 1, seq})
        source_frames = [(key, target) for key in keys]
    else:
        source_frames = list(source_frames)
    observed = [{"sequence": key, "sourceEpoch": 52,
                 "sourceClockCandidate": float(key),
                 "targetUnitIdCandidate": selected,
                 "sourceSha256": f"{key:064X}"}
                for key, selected in source_frames]
    runs = []
    for key, selected in source_frames:
        if not runs or runs[-1]["targetUnitIdCandidate"] != selected:
            runs.append({"targetUnitIdCandidate": selected,
                         "firstSequence": key, "lastSequence": key})
        else:
            runs[-1]["lastSequence"] = key
    all_none = all(item["targetUnitIdCandidate"] is None for item in observed)
    return {
        "qualificationStatus": "candidate-only",
        "status": source_status or ("no-target-baseline-candidate" if all_none
                                    else "selected-target-observations-candidate"),
        "hostName": "RIFT-STATION", "processId": 37676, "processStartUtcTicks": "639308565554559088",
        "executableSha256": BUILD, "playerUnitId": SELF,
        "zoneIdCandidate": "z0000000CB7B53FD7",
        "sourceEpoch": 52, "sourceSessionId": "a" * 32,
        "evidenceSummarySha256": f"{number:064X}",
        "firstSequence": source_frames[0][0],
        "lastSequence": source_frames[-1][0],
        "observedFrameCount": len(source_frames),
        "observedTargetFrames": observed,
        "runs": runs,
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

        def replay(path, *, include_frames=False):
            self.assertTrue(include_frames)
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

    def test_overlapping_windows_do_not_imply_complete_source_sequence_coverage(self):
        result = self.call([
            report(10, A, 1, first=7),
            report(30, A, 2, first=8),
            report(50, A, 3, first=20),
        ])
        self.assertEqual(result["unobservedSequenceGapCount"], 0)
        self.assertEqual(result["capturesWithInternalSequenceGaps"], 2)
        self.assertEqual([
            row["minimumUnobservedSequencesWithinCapture"]
            for row in result["captures"]], [0, 19, 27])
        self.assertEqual(result["status"], "target-continuity-observations-candidate")
        self.assertEqual(result["qualificationStatus"], "candidate-only")
        self.assertEqual(result["missingSequencesInMergedSourceRange"], 34)
        self.assertIn("merged source range reports unique missing sequences",
                      result["qualification"])

    def test_impossible_observation_count_is_refused(self):
        bad = report(20, B, 2)
        bad["observedFrameCount"] = 100
        with self.assertRaisesRegex(ValueError, "source-sequences-invalid"):
            self.call([report(10, A, 1), bad])

    def test_mid_capture_a_b_a_is_found_even_when_last_targets_are_none(self):
        first = report(10, None, 1, source_frames=[
            (6, None), (7, A), (8, B), (9, A), (10, None)])
        later = report(20, None, 2)
        outcome = self.call([first, later])
        self.assertEqual(outcome["status"], "a-b-a-in-source-frames-candidate")
        self.assertEqual(outcome["aBaAcrossCaptures"], [])
        self.assertEqual(outcome["observedSourceABACycles"], [{
            "targetACandidate": A, "targetBCandidate": B,
            "firstSequence": 7, "otherSequence": 8, "returnedSequence": 9}])
        self.assertEqual(outcome["uniqueObservedSourceFrameCount"], 9)
        self.assertFalse(outcome["inputSent"])

    def test_cli_counts_frame_verified_cycle_even_when_last_state_has_none(self):
        first = report(10, None, 1, source_frames=[
            (6, None), (7, A), (8, B), (9, A), (10, None)])
        result = self.call([first, report(20, None, 2)])
        with patch.object(series, "combine", return_value=result), \
                redirect_stdout(StringIO()) as out:
            code = series.main(["--summary", str(self.paths[0]),
                                "--summary", str(self.paths[1])])
        self.assertEqual(code, 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["status"], "a-b-a-in-source-frames-candidate")
        self.assertEqual(printed["aBaCandidates"], 1)
        self.assertEqual(printed["lastStateABACandidates"], 0)

    def test_transient_selected_state_cannot_be_reported_as_all_none(self):
        first = report(10, None, 1, source_frames=[
            (6, None), (7, B), (8, None), (10, None)])
        result = self.call([first, report(20, None, 2)])
        self.assertEqual(result["lastObservedTargetRuns"][0]["targetUnitIdCandidate"],
                         None)
        self.assertEqual(result["status"], "target-continuity-observations-candidate")
        self.assertTrue(any(r["targetUnitIdCandidate"] == B
                            for r in result["observedSourceRuns"]))

    def test_conflicting_same_sequence_across_captures_is_refused(self):
        with self.assertRaisesRegex(ValueError, "overlapping-source-frame-conflict"):
            self.call([report(10, A, 1),
                       report(20, B, 2, first=9)])
        changed = report(20, A, 2, first=9)
        changed["observedTargetFrames"][0]["sourceSha256"] = "F" * 64
        with self.assertRaisesRegex(ValueError, "overlapping-source-frame-conflict"):
            self.call([report(10, A, 1), changed])

    def test_bad_per_frame_source_projection_is_refused(self):
        cases = [
            ("observedFrameCount", 200),
            ("observedTargetFrames", []),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                bad = report(20, B, 2)
                bad[field] = value
                with self.assertRaisesRegex(ValueError,
                                             "source-sequences-invalid|source-frame"):
                    self.call([report(10, A, 1), bad])
        altered = report(20, B, 2)
        altered["observedTargetFrames"][0]["targetUnitIdCandidate"] = A
        with self.assertRaisesRegex(ValueError, "source-frame-run-mismatch"):
            self.call([report(10, A, 1), altered])

    def test_source_epoch_player_build_zone_session_and_pid_mismatches(self):
        baseline = report(10, A, 1)
        for field, value in [
            ("hostName", "OTHER-PC"), ("processId", 3), ("processStartUtcTicks", "456"),
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
                    self.call([report(10, A, 1), report(seq, A, 2)])

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
                           replay=lambda path, **kwargs: report(10, A, 1))

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
