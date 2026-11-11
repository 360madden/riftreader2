"""Offline feedback-gated native waypoint step."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_nav_step as nav
from tests.test_physical_waypoint_decision import position, catalog, empirical


class PhysicalNavStepTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"
        self.catalog = self.root / "catalog.json"
        self.w = self.root / "w.json"
        self.q = self.root / "q.json"
        self.save(self.catalog, catalog(x=2))
        self.save(self.w, empirical("w"))
        self.save(self.q, empirical("q"))
        self.positions(.2)

    def save(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def positions(self, x):
        before = position()
        after = deepcopy(before)
        for row in after["observations"]:
            row["x"] = x
            row["startedAtUtc"] = row["startedAtUtc"].replace("07:06:42", "07:06:43")
            row["completedAtUtc"] = row["completedAtUtc"].replace("07:06:42", "07:06:43")
        self.save(self.before, before)
        self.save(self.after, after)

    def step(self):
        return nav.next_step(self.before, self.after, self.catalog, "Near_Gate", self.w, self.q)

    def test_progress_yields_bounded_candidate_from_after_position(self):
        result = self.step()
        self.assertEqual(result["decision"], "suggested-one-pulse")
        self.assertEqual(result["candidateAction"]["key"], "w")
        self.assertTrue(20 <= result["candidateAction"]["holdMilliseconds"] <= 150)
        self.assertEqual(result["waypointDecision"]["candidateCurrentXYZ"]["x"], .2)
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["actionVerified"])

    def test_no_progress_and_regression_stop(self):
        for x in (0, -.1, .01):
            with self.subTest(x=x):
                self.positions(x)
                result = self.step()
                self.assertEqual(result["decision"], "stop")
                self.assertIsNone(result["candidateAction"])

    def test_candidate_within_tolerance_is_not_arrival(self):
        self.positions(1.8)
        result = self.step()
        self.assertEqual(result["decision"], "within-tolerance-candidate")
        self.assertIsNone(result["candidateAction"])
        self.assertFalse(result["arrivalQualified"])

    def test_mismatched_feedback_and_decision_evidence_blocks(self):
        original = nav.waypoint.decide
        def changed(*args):
            result = original(*args)
            result["nativeReportSha256"] = "F" * 64
            return result
        with patch.object(nav.waypoint, "decide", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                self.step()

    def test_missing_or_invalid_q_retains_feedback_but_stops(self):
        no_calibrations = nav.next_step(self.before, self.after, self.catalog, "Near_Gate", None, None)
        self.assertEqual(no_calibrations["reason"], "w-calibration-required-for-steering")
        self.assertAlmostEqual(no_calibrations["feedback"]["planarProgressCandidate"], .2)
        result = nav.next_step(self.before, self.after, self.catalog, "Near_Gate", self.w, None)
        self.assertEqual(result["reason"], "q-calibration-required-for-steering")
        self.assertAlmostEqual(result["feedback"]["planarProgressCandidate"], .2)
        self.assertIsNone(result["candidateAction"])
        self.save(self.q, {})
        result = self.step()
        self.assertEqual(result["reason"], "waypoint-decision-unavailable")
        self.assertAlmostEqual(result["feedback"]["planarProgressCandidate"], .2)
        self.assertIsNone(result["candidateAction"])

    def test_cli_reports_invalid_feedback(self):
        self.after.write_bytes(self.before.read_bytes())
        args = ["--before", str(self.before), "--after", str(self.after),
                "--catalog", str(self.catalog), "--anchor-id", "Near_Gate",
                "--w-calibration", str(self.w), "--q-calibration", str(self.q)]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(nav.main(args), 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
