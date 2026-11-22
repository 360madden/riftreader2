"""No-game-input tests for bounded physical target continuity acquisition."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import capture_physical_telemetry_target_series as capture

PID = 37676
ORIGIN = "0x8000000"


class SeriesCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "output"
        self.calls = []
        self.sleeps = []

    def collect(self, pid, destination, **options):
        index = len(self.calls) + 1
        self.calls.append((pid, destination, options))
        destination.mkdir()
        path = destination / "summary.json"
        path.write_text('{"fixture":true}', encoding="utf-8")
        return path, {"status": "matching-candidates",
                      "target": {"processId": PID},
                      "scopeSurvey": {"selectedStartAddress": ORIGIN}}

    def replay(self, path):
        index = int(path.parent.name.split("-")[1])
        return {"qualificationStatus": "candidate-only",
                "status": "no-target-baseline-candidate",
                "lastSequence": 10 * index}

    def combine(self, paths):
        self.assertEqual([p.parent.name for p in paths],
                         ["capture-01", "capture-02", "capture-03"])
        return {"captureCount": 3, "qualificationStatus": "candidate-only",
                "status": "no-target-continuity-candidate",
                "aBaAcrossCaptures": []}

    def execute_capture(self, **changes):
        kwargs = dict(count=3, interval_ms=50, scope_count=4,
                      collect=self.collect, replay_target=self.replay,
                      combine=self.combine, sleep=self.sleeps.append)
        kwargs.update(changes)
        return capture.run(PID, self.output, **kwargs)

    def test_first_window_discovers_and_later_windows_reuse_verified_scope(self):
        path, result = self.execute_capture()
        self.assertTrue(path.is_file())
        self.assertEqual(result["status"], "no-target-continuity-candidate")
        self.assertFalse(result["inputSent"])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.sleeps, [0.05, 0.05])
        first = self.calls[0][2]
        self.assertEqual(first["discover_scope"], True)
        self.assertEqual(first["scope_count"], 4)
        self.assertNotIn("start_address", first)
        for _, _, later in self.calls[1:]:
            self.assertEqual(later["discover_scope"], False)
            self.assertEqual(later["scope_count"], 1)
            self.assertEqual(later["start_address"], ORIGIN)
            self.assertEqual(later["include_native_target"], True)
        self.assertEqual(json.loads(path.read_text())["continuity"],
                         result["continuity"])
        self.assertFalse((self.output / "failure.json").exists())

    def test_unqualified_window_aborts_without_claiming_freshness(self):
        def failed(pid, destination, **options):
            path, result = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                result["status"] = "unqualified"
            return path, result

        with self.assertRaisesRegex(ValueError, "capture-02-unqualified"):
            self.execute_capture(collect=failed)
        self.assertEqual(len(self.calls), 2)
        saved = json.loads((self.output / "failure.json").read_text())
        self.assertEqual(saved["status"], "unqualified")
        self.assertEqual(saved["completedCaptures"], 1)
        self.assertFalse(saved["inputSent"])
        self.assertFalse((self.output / "result.json").exists())

    def test_changed_process_is_refused_without_a_third_read(self):
        def wrong_pid(pid, destination, **options):
            path, result = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                result["target"]["processId"] = PID + 1
            return path, result

        with self.assertRaisesRegex(ValueError, "capture-02-process-mismatch"):
            self.execute_capture(collect=wrong_pid)
        self.assertEqual(len(self.calls), 2)

    def test_continuity_replay_failure_keeps_original_capture_files(self):
        def invalid(paths):
            raise ValueError("target-continuity-no-new-advancing-source-sequence")

        with self.assertRaisesRegex(ValueError, "no-new-advancing"):
            self.execute_capture(combine=invalid)
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertEqual(len(list(self.output.glob("capture-*/summary.json"))), 3)

    def test_invalid_bounds_and_existing_directory_are_rejected_before_reads(self):
        cases = [{"count": 1}, {"count": 7}, {"interval_ms": -1},
                 {"interval_ms": 3000}, {"scope_count": 9},
                 {"recover_stale_scope": 1}, {"stop_on_aba": 1}]
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "invalid-bounds"):
                    self.execute_capture(**invalid)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.calls, [])
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "output-must-be-new"):
            self.execute_capture()
        self.assertEqual(self.calls, [])

    def test_bounded_watcher_stops_at_first_source_verified_aba(self):
        calls = []

        def verified_source_merge(paths):
            calls.append(len(paths))
            if len(paths) == 2:
                return {"captureCount": 2,
                        "qualificationStatus": "candidate-only",
                        "status": "a-b-a-in-source-frames-candidate",
                        "observedSourceABACycles": [{
                            "firstSequence": 12, "otherSequence": 13,
                            "returnedSequence": 14}],
                        "aBaAcrossCaptures": []}
            self.fail("Observer must not acquire a third window after candidate")

        path, result = self.execute_capture(
            count=6, stop_on_aba=True, combine=verified_source_merge)
        self.assertTrue(path.is_file())
        self.assertEqual(calls, [2])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["requestedCaptureCount"], 6)
        self.assertEqual(result["completedCaptureCount"], 2)
        self.assertEqual(result["earlyStopReason"],
                         "observed-source-a-b-a-candidate")
        self.assertEqual(result["continuity"]["observedSourceABACycles"][0]
                         ["returnedSequence"], 14)
        self.assertEqual(self.sleeps, [0.05])
        self.assertFalse((self.output / "capture-03").exists())
        self.assertFalse(result["inputSent"])

    def test_no_aba_observations_run_entire_bounded_schedule(self):
        checked = []
        def no_cycle(paths):
            checked.append(len(paths))
            return {"captureCount": len(paths),
                    "qualificationStatus": "candidate-only",
                    "status": "no-target-continuity-candidate",
                    "observedSourceABACycles": [],
                    "aBaAcrossCaptures": []}

        path, result = self.execute_capture(
            count=4, stop_on_aba=True, combine=no_cycle)
        self.assertTrue(path.is_file())
        self.assertEqual(checked, [2, 3, 4])
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(result["completedCaptureCount"], 4)
        self.assertIsNone(result["earlyStopReason"])
        self.assertEqual(self.sleeps, [0.05, 0.05, 0.05])
        self.assertFalse(result["inputSent"])

    def test_last_state_only_pattern_never_ends_watcher_early(self):
        def last_state_only(paths):
            return {"captureCount": len(paths),
                    "qualificationStatus": "candidate-only",
                    "status": "a-b-a-across-captures-candidate",
                    "observedSourceABACycles": [],
                    "aBaAcrossCaptures": [{"firstCapture": 1}]}

        _, result = self.execute_capture(
            count=3, stop_on_aba=True, combine=last_state_only)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(result["requestedCaptureCount"], 3)
        self.assertIsNone(result["earlyStopReason"])

    def test_invalid_incremental_replay_fails_closed_without_more_captures(self):
        def fake_success(paths):
            return {"captureCount": len(paths),
                    "qualificationStatus": "candidate-only",
                    "status": "a-b-a-in-source-frames-candidate",
                    "observedSourceABACycles": None,
                    "aBaAcrossCaptures": []}

        with self.assertRaisesRegex(ValueError, "early-stop-replay-invalid"):
            self.execute_capture(count=5, stop_on_aba=True,
                                 combine=fake_success)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "capture-03").exists())

    def test_cli_opt_in_stop_on_aba_is_forwarded(self):
        fake = {
            "status": "a-b-a-in-source-frames-candidate",
            "individualCaptures": [{"capture": 1}, {"capture": 2}],
            "earlyStopReason": "observed-source-a-b-a-candidate",
            "continuity": {
                "observedSourceABACycles": [{"firstSequence": 12,
                                              "otherSequence": 13,
                                              "returnedSequence": 14}],
                "aBaAcrossCaptures": []},
        }
        with patch.object(capture, "run", return_value=(
                self.output / "result.json", fake)) as launched, \
                redirect_stdout(StringIO()) as stdout:
            code = capture.main(["--physical-pid", str(PID),
                                 "--output-dir", str(self.output),
                                 "--count", "6", "--stop-on-aba"])
        self.assertEqual(code, 0)
        self.assertTrue(launched.call_args.kwargs["stop_on_aba"])
        printed = json.loads(stdout.getvalue())
        self.assertEqual(printed["earlyStopReason"],
                         "observed-source-a-b-a-candidate")
        self.assertEqual(printed["aBaCandidates"], 1)

    def test_cli_reports_frame_level_aba_not_only_final_target_states(self):
        fake = {
            "status": "a-b-a-in-source-frames-candidate",
            "individualCaptures": [{"capture": 1}, {"capture": 2}],
            "continuity": {
                "observedSourceABACycles": [{"firstSequence": 7,
                                              "otherSequence": 8,
                                              "returnedSequence": 9}],
                "aBaAcrossCaptures": [],
            },
        }
        with patch.object(capture, "run",
                          return_value=(self.output / "result.json", fake)) as run, \
                redirect_stdout(StringIO()) as output:
            code = capture.main(["--physical-pid", str(PID),
                                 "--output-dir", str(self.output),
                                 "--count", "2"])
        self.assertEqual(code, 0)
        self.assertFalse(self.output.exists())
        printed = json.loads(output.getvalue())
        self.assertEqual(printed["aBaCandidates"], 1)
        self.assertEqual(printed["lastStateABACandidates"], 0)
        self.assertEqual(printed["status"], "a-b-a-in-source-frames-candidate")
        run.assert_called_once()

    def test_opt_in_relocates_one_stale_scope_and_preserves_failed_evidence(self):
        moved = "0xC000000"

        def relocation(pid, destination, **options):
            path, report = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                report.update(status="unqualified", sameProcessEpoch=True,
                              sourceClockProgression="unqualified")
                report["scopeSurvey"]["status"] = "scoped-candidate"
            if len(self.calls) >= 3:
                report["scopeSurvey"]["selectedStartAddress"] = moved
            return path, report

        def merged(paths):
            self.assertEqual([p.parent.name for p in paths],
                             ["capture-01", "capture-02-rediscovery", "capture-03"])
            return {"captureCount": 3, "qualificationStatus": "candidate-only",
                    "status": "no-target-continuity-candidate",
                    "aBaAcrossCaptures": [], "observedSourceABACycles": []}

        path, result = self.execute_capture(
            collect=relocation, combine=merged, recover_stale_scope=True,
            expected_host="RIFT-STATION")
        self.assertTrue(path.is_file())
        self.assertEqual(len(self.calls), 4)
        self.assertTrue(all(options["expected_host"] == "RIFT-STATION"
                            for _, _, options in self.calls))
        self.assertTrue((self.output / "capture-02" / "summary.json").is_file())
        self.assertTrue((self.output / "capture-02-rediscovery" / "summary.json").is_file())
        self.assertEqual(self.calls[2][2]["discover_scope"], True)
        self.assertEqual(self.calls[2][2]["scope_count"], 4)
        self.assertNotIn("start_address", self.calls[2][2])
        self.assertEqual(self.calls[3][2]["start_address"], moved)
        self.assertEqual(result["scopeRediscoveryAttempts"][0]["outcome"],
                         "completed-candidate")
        self.assertEqual(result["scopeRediscoveryAttempts"][0]["reason"],
                         "cached-scope-source-not-advancing")
        self.assertFalse(result["inputSent"])

    def test_opt_in_recovers_only_exact_cached_scope_not_found_error(self):
        def missing(pid, destination, **options):
            path, report = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                raise ValueError(
                    "telemetry-zone-capture-no-current-player-zone-scope-in-survey")
            return path, report

        def merged(paths):
            self.assertEqual(paths[1].parent.name, "capture-02-rediscovery")
            return {"captureCount": 3, "qualificationStatus": "candidate-only",
                    "status": "no-target-continuity-candidate",
                    "aBaAcrossCaptures": [], "observedSourceABACycles": []}

        path, result = self.execute_capture(
            collect=missing, combine=merged, recover_stale_scope=True)
        self.assertTrue(path.is_file())
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(result["scopeRediscoveryAttempts"][0]["reason"],
                         "cached-scope-not-found")
        self.assertFalse((self.output / "failure.json").exists())

    def test_recovery_failure_keeps_attempt_and_never_commits_result(self):
        def unqualified_then_failed(pid, destination, **options):
            path, report = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                report.update(status="unqualified", sameProcessEpoch=True,
                              sourceClockProgression="unqualified")
                report["scopeSurvey"]["status"] = "scoped-candidate"
            if len(self.calls) == 3:
                raise ValueError("telemetry-zone-capture-recovery-incomplete")
            return path, report

        with self.assertRaisesRegex(ValueError, "recovery-incomplete"):
            self.execute_capture(
                collect=unqualified_then_failed, recover_stale_scope=True)
        self.assertEqual(len(self.calls), 3)
        failure = json.loads((self.output / "failure.json").read_text())
        self.assertEqual(failure["completedCaptures"], 1)
        self.assertEqual(failure["scopeRediscoveryAttempts"][0]["outcome"],
                         "attempted")
        self.assertFalse((self.output / "result.json").exists())
        self.assertTrue((self.output / "capture-02" / "summary.json").is_file())

    def test_process_identity_change_blocks_rediscovery(self):
        def changed_epoch(pid, destination, **options):
            path, report = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                report.update(status="unqualified", sameProcessEpoch=True,
                              sourceClockProgression="unqualified")
                report["scopeSurvey"]["status"] = "scoped-candidate"
                report["target"]["processStartUtcTicks"] = "other"
            return path, report

        with self.assertRaisesRegex(ValueError, "target-identity-changed"):
            self.execute_capture(collect=changed_epoch,
                                 recover_stale_scope=True)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse((self.output / "capture-02-rediscovery").exists())

    def test_recovery_never_retries_unrelated_unqualified_capture(self):
        def stale_but_wrong_reason(pid, destination, **options):
            path, report = self.collect(pid, destination, **options)
            if len(self.calls) == 2:
                report.update(status="unqualified", sameProcessEpoch=True,
                              sourceClockProgression="advancing")
                report["scopeSurvey"]["status"] = "scoped-candidate"
            return path, report

        with self.assertRaisesRegex(ValueError, "capture-02-unqualified"):
            self.execute_capture(collect=stale_but_wrong_reason,
                                 recover_stale_scope=True)
        self.assertEqual(len(self.calls), 2)

    def test_cli_recovery_is_opt_in_and_forwarded(self):
        sample = {"status": "no-target-continuity-candidate",
                  "individualCaptures": [{"capture": 1}, {"capture": 2}],
                  "continuity": {"observedSourceABACycles": [],
                                 "aBaAcrossCaptures": []}}
        with patch.object(capture, "run",
                          return_value=(self.output / "result.json", sample)) as run, \
                redirect_stdout(StringIO()):
            self.assertEqual(capture.main([
                "--physical-pid", str(PID), "--output-dir", str(self.output),
                "--count", "2", "--recover-stale-scope"]), 0)
        self.assertTrue(run.call_args.kwargs["recover_stale_scope"])

    def test_unavailable_scope_aborts_before_followup(self):
        def no_scope(pid, destination, **options):
            path, result = self.collect(pid, destination, **options)
            result["scopeSurvey"]["selectedStartAddress"] = None
            return path, result

        with self.assertRaisesRegex(ValueError, "scope-unavailable"):
            self.execute_capture(collect=no_scope)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
