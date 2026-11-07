import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import summarize_workflow_timeline as timeline


def trace():
    return {"schemaVersion": 1, "clockScope": "orchestrator-a", "requiredPhases": ["run"],
            "calls": [
                {"phase": "run", "tool": "terminal_run", "jobId": "a", "status": "running",
                 "exitCode": None, "completionPending": True, "roundTripMs": 100,
                 "dispatchUtc": "2026-11-07T01:00:00Z", "resultReturnUtc": "2026-11-07T01:00:00.100Z"},
                {"phase": "run", "tool": "command_output", "jobId": "a", "status": "passed",
                 "exitCode": 0, "completionPending": False, "roundTripMs": 150,
                 "dispatchUtc": "2026-11-07T01:00:01Z", "resultReturnUtc": "2026-11-07T01:00:01.150Z"}],
            "childStages": [{"phase": "capture", "wallMs": 75}]}


class WorkflowTimelineTests(unittest.TestCase):
    def test_completed_job_counts_gap_and_independent_child_duration(self):
        result = timeline.summarize(trace())
        self.assertTrue(result["success"])
        self.assertEqual(result["workflowElapsedMs"], 1150)
        self.assertEqual(result["toolRoundTripTotalMs"], 250)
        self.assertEqual(result["observedOrchestrationGapTotalMs"], 900)
        self.assertEqual(result["callCounts"], {"terminal_run": 1, "command_output": 1})
        self.assertEqual(result["childStages"], [{"phase": "capture", "wallMs": 75}])
        self.assertEqual(result["phaseTransitionGapTotalMs"], 0)
        self.assertEqual(result["withinPhaseGapTotalMs"], 900)
        self.assertTrue(result["phases"][0]["completionObserved"])

    def test_phase_labels_split_observed_gaps_without_inventing_their_cause(self):
        data = trace()
        data["requiredPhases"] = ["preflight", "capture"]
        data["calls"][0]["phase"] = "preflight"
        data["calls"][1]["phase"] = "capture"
        data["calls"][0].update({"class": "within-phase", "observedGapMs": 123456})
        result = timeline.summarize(data)
        self.assertEqual(result["phaseTransitionGapTotalMs"], 900)
        self.assertEqual(result["withinPhaseGapTotalMs"], 0)
        gap = result["observedOrchestrationGaps"][0]
        self.assertEqual((gap["afterPhase"], gap["beforePhase"], gap["class"]),
                         ("preflight", "capture", "phase-transition"))
        self.assertEqual([row["callCount"] for row in result["phases"]], [1, 1])
        self.assertFalse(result["phases"][0]["completionObserved"])
        self.assertTrue(result["phases"][1]["completionObserved"])

    def test_revisited_phase_has_no_contiguous_observation_span(self):
        data = trace()
        final = copy.deepcopy(data["calls"][-1])
        data["calls"][-1]["phase"] = "capture"
        final.update(dispatchUtc="2026-11-07T01:00:02Z", resultReturnUtc="2026-11-07T01:00:02.150Z")
        data["calls"].append(final)
        result = timeline.summarize(data)
        self.assertFalse(result["phases"][0]["contiguous"])
        self.assertIsNone(result["phases"][0]["observedSpanMs"])
        self.assertEqual(result["phaseTransitionGapTotalMs"], 1750)
        self.assertEqual(result["withinPhaseGapTotalMs"], 0)

    def test_unsettled_nonzero_failed_and_missing_phase_are_non_success(self):
        for changes in ({"status": "running"}, {"completionPending": True}, {"exitCode": 2},
                        {"status": "failed"}, {"error": "transport error"}):
            data = trace()
            data["calls"][-1].update(changes)
            with self.subTest(changes=changes):
                result = timeline.summarize(data)
                self.assertFalse(result["success"])
                self.assertIsNone(result["workflowElapsedMs"])
        data = trace()
        data["requiredPhases"].append("verify")
        self.assertEqual(timeline.summarize(data)["missingPhases"], ["verify"])

    def test_failed_job_not_hidden_by_other_completed_job(self):
        data = trace()
        data["calls"][0].update(status="failed", completionPending=False, jobId="failed-job")
        self.assertFalse(timeline.summarize(data)["success"])

    def test_invalid_order_scope_bounds_and_numbers_rejected(self):
        cases = []
        for changes in ({"dispatchUtc": "2026-11-07T00:59:59Z"},
                        {"resultReturnUtc": "2026-11-07T00:00:00Z"},
                        {"resultReturnUtc": "2026-11-07T04:00:00Z"},
                        {"dispatchUtc": "2026-11-07T01:00:01"},
                        {"clockScope": "other-clock"}, {"roundTripMs": -1},
                        {"roundTripMs": float("nan")}, {"roundTripMs": True},
                        {"completionPending": 0}, {"exitCode": False}):
            data = trace()
            data["calls"][-1].update(changes)
            cases.append(data)
        for field, value in (("calls", []), ("calls", trace()["calls"] * 501),
                             ("requiredPhases", []), ("clockScope", ""), ("schemaVersion", True),
                             ("childStages", [{"phase": "run", "wallMs": -1}])):
            data = trace()
            data[field] = value
            cases.append(data)
        for data in cases:
            with self.subTest(data=str(data)[:200]), self.assertRaises(ValueError):
                timeline.summarize(data)

    def test_cli_compares_separate_clocks_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, output = root / "first.json", root / "second.json", root / "out.json"
            first.write_text(json.dumps(trace()), encoding="utf-8")
            other = copy.deepcopy(trace())
            other["clockScope"] = "different-session"
            second.write_text(json.dumps(other), encoding="utf-8")
            args = ["--trace", str(first), "--compare", str(second), "--output", str(output)]
            self.assertEqual(timeline.main(args), 0)
            content = output.read_bytes()
            self.assertEqual(json.loads(content)["comparison"]["workflowElapsedDeltaMs"], 0)
            self.assertEqual(timeline.main(args), 2)
            self.assertEqual(output.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
