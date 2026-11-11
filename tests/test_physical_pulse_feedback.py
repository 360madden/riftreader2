"""Offline physical native position before/after pulse feedback."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import physical_pulse_feedback as feedback
from tests.test_physical_route_preview import native, catalog


class PhysicalPulseFeedbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"
        self.catalog = self.root / "anchors.json"
        self.store()

    def store(self, *, first_x=1, later_x=3, first_z=0, later_z=0,
              before=None, after=None, anchor=None):
        prior = native() if before is None else before
        current = deepcopy(prior) if after is None else after
        for row in prior["observations"]:
            row.update(x=first_x, y=0, z=first_z)
        for row in current["observations"]:
            row.update(x=later_x, y=0, z=later_z)
            row["startedAtUtc"] = row["startedAtUtc"].replace("07:06:42", "07:06:43")
            row["completedAtUtc"] = row["completedAtUtc"].replace("07:06:42", "07:06:43")
        saved = catalog() if anchor is None else anchor
        saved["anchors"][0]["position"] = {"x": 10, "y": 0, "z": 0}
        self.before.write_text(json.dumps(prior, allow_nan=True), encoding="utf-8")
        self.after.write_text(json.dumps(current, allow_nan=True), encoding="utf-8")
        self.catalog.write_text(json.dumps(saved), encoding="utf-8")

    def test_two_unit_progress_toward_anchor(self):
        result = feedback.compare(self.before, self.after, self.catalog, "north_gate")
        self.assertEqual(result["status"], "offline-physical-pulse-feedback-candidate")
        self.assertEqual(result["direction"], "toward-anchor-candidate")
        self.assertAlmostEqual(result["planarDistanceBeforeCandidate"], 9)
        self.assertAlmostEqual(result["planarDistanceAfterCandidate"], 7)
        self.assertAlmostEqual(result["planarProgressCandidate"], 2)
        self.assertAlmostEqual(result["horizontalDisplacementCandidate"], 2)
        self.assertEqual(result["deltaXYZ"], {"x": 2, "y": 0, "z": 0})
        self.assertFalse(result["actionVerified"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["arrivalQualified"])
        self.assertFalse(result["worldInstanceMatched"])

    def test_stalled_and_regression_candidates(self):
        self.store(later_x=1)
        result = feedback.compare(self.before, self.after, self.catalog, "North_Gate")
        self.assertEqual(result["direction"], "no-distance-change-candidate")
        self.assertAlmostEqual(result["planarProgressCandidate"], 0)
        self.store(later_x=0)
        result = feedback.compare(self.before, self.after, self.catalog, "North_Gate")
        self.assertEqual(result["direction"], "away-from-anchor-candidate")
        self.assertAlmostEqual(result["planarProgressCandidate"], -1)

    def test_same_evidence_and_epoch_or_player_change_block(self):
        self.after.write_bytes(self.before.read_bytes())
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "independent"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")
        later = native()
        later["identity"]["processStartUtcTicks"] += 1
        self.store(after=later)
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "process/build epoch"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")
        later = native()
        for row in later["observations"]:
            row["unitKey"] = "2"
        self.store(after=later)
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "player key"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")

    def test_capture_overlap_gap_and_anchor_build_block(self):
        self.store()
        after = json.loads(self.after.read_text(encoding="utf-8"))
        for row in after["observations"]:
            row["startedAtUtc"] = row["startedAtUtc"].replace("07:06:43", "07:06:42")
            row["completedAtUtc"] = row["completedAtUtc"].replace("07:06:43", "07:06:42")
        self.after.write_text(json.dumps(after), encoding="utf-8")
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "overlap"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")
        self.store()
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "gap exceeded"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate",
                             max_gap_seconds=.1)
        saved = catalog()
        saved["anchors"][0]["source"]["gameBuildSha256"] = "F" * 64
        self.store(anchor=saved)
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "different game builds"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")

    def test_overflow_metrics_block(self):
        self.store(first_x=1e308, later_x=-1e308)
        with self.assertRaisesRegex(feedback.PhysicalPulseFeedbackError, "nonfinite"):
            feedback.compare(self.before, self.after, self.catalog, "North_Gate")

    def test_cli_success_and_blocked_are_structured(self):
        args = ["--before", str(self.before), "--after", str(self.after),
                "--catalog", str(self.catalog), "--anchor-id", "North_Gate"]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(feedback.main(args), 0)
        self.assertEqual(json.loads(output.getvalue())["direction"], "toward-anchor-candidate")
        self.after.write_bytes(self.before.read_bytes())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(feedback.main(args), 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
