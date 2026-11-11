"""Read-only predicted versus observed single-pulse feedback from retained reports."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_move_step_feedback as feedback
from tests.test_physical_move_basis_waypoint import basis
from tests.test_physical_waypoint_decision import BUILD, UNIT, START_TICKS, position
from tests.test_physical_move_key_calibration import receipt


def completed_w():
    r = receipt()
    r.update(executableSha256=BUILD, processId=44888,
             processStartUtcTicks=START_TICKS, keys=["w"],
             holdMilliseconds=100, observedMilliseconds=110)
    xyz = r["xyzFeedback"]
    xyz["beforeXYZ"].update(unitKey=UNIT, x=0.0, y=0.0, z=0.0,
                            startedAtUtc="2026-11-11T07:06:42.500Z",
                            completedAtUtc="2026-11-11T07:06:42.510Z")
    xyz["afterXYZ"].update(unitKey=UNIT, x=-.66, y=0.0, z=-.0825,
                           startedAtUtc="2026-11-11T07:06:42.730Z",
                           completedAtUtc="2026-11-11T07:06:42.740Z")
    xyz.update(deltaXYZ={"x": -.66, "y": 0, "z": -.0825},
               planarDisplacementCandidate=(.66**2 + .0825**2)**.5,
               captureGapSeconds=.22)
    return r


class PhysicalStepFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.basis_file = self.root / "basis.json"
        self.position_file = self.root / "position.json"
        self.receipt_file = self.root / "receipt.json"
        self.write()

    def write(self, b=None, p=None, r=None):
        self.basis_file.write_text(json.dumps(basis() if b is None else b), encoding="utf-8")
        self.position_file.write_text(json.dumps(position() if p is None else p), encoding="utf-8")
        self.receipt_file.write_text(json.dumps(completed_w() if r is None else r), encoding="utf-8")

    def assess(self, x=-.6, z=-.075, post=False):
        extra = {"post_position_path": self.root / "post.json"} if post else {}
        return feedback.compare(self.basis_file, self.position_file, x, z,
                                self.receipt_file, **extra)

    def save_post(self, x=-.66, z=-.0825, start_second="42"):
        report = position()
        for index, row in enumerate(report["observations"]):
            ms = 850 + index * 100
            row["startedAtUtc"] = f"2026-11-11T07:06:{start_second}.{ms:03d}Z"
            row["completedAtUtc"] = f"2026-11-11T07:06:{start_second}.{ms+10:03d}Z"
            row.update(x=x, y=0, z=z)
        (self.root / "post.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    def test_matching_pulse_produces_candidate_feedback_not_control_authority(self):
        result = self.assess()
        self.assertEqual(result["status"], "offline-physical-waypoint-feedback-candidate")
        self.assertEqual(result["comparison"], "candidate-consistent")
        self.assertEqual(result["decision"], "observation-only")
        self.assertEqual(result["key"], "w")
        self.assertEqual(result["requestedHoldMilliseconds"], 100)
        self.assertEqual(result["observedHoldMilliseconds"], 110)
        self.assertAlmostEqual(result["predictedDeltaForObservedHoldCandidate"]["x"], -.66)
        self.assertAlmostEqual(result["observedDeltaCandidate"]["x"], -.66)
        self.assertAlmostEqual(result["planarPredictionErrorCandidate"], 0, places=6)
        self.assertGreater(result["progressTowardTargetCandidate"], 0)
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertFalse(result["navigationEligible"])
        self.assertFalse(result["arrivalQualified"])
        self.assertEqual(result["controllerFeedbackStatus"], "confirming-arrival")
        self.assertEqual(result["nextCandidateStatus"], "requires-independent-arrival-settle")
        self.assertIsNone(result["nextCandidateAction"])

    def test_replans_one_revised_candidate_without_resetting_controller(self):
        r = completed_w()
        r.update(holdMilliseconds=150, observedMilliseconds=155)
        r["xyzFeedback"]["afterXYZ"].update(x=-.93, z=-.11625)
        r["xyzFeedback"]["deltaXYZ"] = {"x": -.93, "y": 0, "z": -.11625}
        r["xyzFeedback"]["planarDisplacementCandidate"] = (.93**2 + .11625**2)**.5
        self.write(r=r)
        result = self.assess(-1.2, .5)
        self.assertEqual(result["comparison"], "candidate-consistent")
        self.assertEqual(result["nextCandidateStatus"], "one-revised-offline-candidate")
        self.assertEqual(result["controllerFeedbackStatus"], "active")
        next_action = result["nextCandidateAction"]
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action["key"], "q")
        self.assertLessEqual(next_action["holdMilliseconds"], 150)
        self.assertGreaterEqual(next_action["holdMilliseconds"], 20)
        self.assertFalse(next_action["navigationEligible"])
        self.assertFalse(next_action["inputSent"])
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["navigationEligible"])

    def test_consistent_displacement_that_breaks_corridor_stops(self):
        r = completed_w()
        r.update(holdMilliseconds=150, observedMilliseconds=155)
        r["xyzFeedback"]["afterXYZ"].update(x=-.93, z=-.33)
        r["xyzFeedback"]["deltaXYZ"] = {"x": -.93, "y": 0, "z": -.33}
        r["xyzFeedback"]["planarDisplacementCandidate"] = (.93**2 + .33**2)**.5
        self.write(r=r)
        result = self.assess(-1.2, .5)
        self.assertEqual(result["comparison"], "candidate-consistent")
        self.assertEqual(result["decision"], "stop-and-review")
        self.assertEqual(result["nextCandidateStatus"], "stop-controller-cross-track")
        self.assertIsNone(result["nextCandidateAction"])

    def test_separate_stationary_post_capture_matches_helper_candidate(self):
        self.save_post(x=-.661, z=-.082)
        result = self.assess(post=True)
        self.assertTrue(result["postPositionMatchesReceiptCandidate"])
        self.assertRegex(result["postPositionReportSha256"], "^[0-9A-F]{64}$")
        self.assertGreater(result["postCaptureGapSeconds"], 0)
        self.assertEqual(result["nextCandidateStatus"], "requires-independent-arrival-settle")
        self.assertFalse(result["arrivalQualified"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertIsNone(result["nextCandidateAction"])

    def test_separate_post_capture_can_support_revised_offline_candidate(self):
        r = completed_w()
        r.update(holdMilliseconds=150, observedMilliseconds=155)
        r["xyzFeedback"]["afterXYZ"].update(x=-.93, z=-.11625)
        r["xyzFeedback"]["deltaXYZ"] = {"x": -.93, "y": 0, "z": -.11625}
        r["xyzFeedback"]["planarDisplacementCandidate"] = (.93**2 + .11625**2)**.5
        self.write(r=r)
        self.save_post(x=-.931, z=-.116)
        result = self.assess(-1.2, .5, post=True)
        self.assertEqual(result["nextCandidateStatus"], "one-revised-offline-candidate")
        self.assertEqual(result["nextCandidateAction"]["key"], "q")
        self.assertAlmostEqual(result["postPositionXYZCandidate"]["x"], -.931)
        self.assertFalse(result["navigationEligible"])

    def test_post_capture_wrong_owner_stale_unstable_or_disagreeing_blocks(self):
        p = self.save_post()
        p["identity"]["processId"] += 1
        (self.root / "post.json").write_text(json.dumps(p), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feedback-post-owner-changed"):
            self.assess(post=True)
        self.save_post(start_second="49")
        with self.assertRaisesRegex(ValueError, "feedback-post-capture-gap-invalid"):
            self.assess(post=True)
        self.save_post(x=-.4)
        with self.assertRaisesRegex(ValueError, "feedback-post-disagrees-with-helper"):
            self.assess(post=True)
        p = self.save_post()
        p["observations"][0]["x"] = -.50
        (self.root / "post.json").write_text(json.dumps(p), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feedback-post-capture-not-stationary"):
            self.assess(post=True)
        p = self.save_post()
        p["observations"][1].update(
            startedAtUtc="2026-11-11T07:06:45.950Z",
            completedAtUtc="2026-11-11T07:06:45.960Z")
        (self.root / "post.json").write_text(json.dumps(p), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feedback-post-burst-too-long"):
            self.assess(post=True)
        p = self.save_post()
        middle = deepcopy(p["observations"][0])
        middle.update(index=2, x=-.4,
                      startedAtUtc="2026-11-11T07:06:42.910Z",
                      completedAtUtc="2026-11-11T07:06:42.920Z")
        p["observations"].insert(1, middle)
        p["observations"][2]["index"] = 3
        p["requestedSamples"] = p["completedSamples"] = 3
        (self.root / "post.json").write_text(json.dumps(p), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feedback-post-capture-not-stationary"):
            self.assess(post=True)

    def test_cli_optional_post_position_reuses_later_native_capture(self):
        self.save_post()
        args = ["--basis", str(self.basis_file), "--position", str(self.position_file),
                "--receipt", str(self.receipt_file),
                "--post-position", str(self.root / "post.json"),
                "--target-x", "-.6", "--target-z", "-.075"]
        with contextlib.redirect_stdout(StringIO()) as printed:
            self.assertEqual(feedback.main(args), 0)
        report = json.loads(printed.getvalue())
        self.assertTrue(report["postPositionMatchesReceiptCandidate"])
        self.assertFalse(report["gameResponseVerified"])
        self.assertFalse(report["inputSent"])

    def test_divergent_direction_means_stop_and_review(self):
        r = completed_w()
        r["xyzFeedback"]["afterXYZ"]["x"] = -.10
        r["xyzFeedback"]["deltaXYZ"]["x"] = -.10
        r["xyzFeedback"]["planarDisplacementCandidate"] = (.10**2 + .0825**2)**.5
        self.write(r=r)
        result = self.assess()
        self.assertEqual(result["comparison"], "candidate-divergent")
        self.assertEqual(result["decision"], "stop-and-review")
        self.assertEqual(result["nextCandidateStatus"], "stop-divergent-feedback")
        self.assertIsNone(result["nextCandidateAction"])
        self.assertGreater(result["planarPredictionErrorCandidate"],
                           result["planarErrorToleranceCandidate"])

    def test_rejects_mismatched_key_and_hold(self):
        r = completed_w()
        r.update(keys=["q"])
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-command-mismatch"):
            self.assess()
        r = completed_w()
        r.update(holdMilliseconds=120, observedMilliseconds=121)
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-command-mismatch"):
            self.assess()

    def test_rejects_different_owner_and_start_position(self):
        r = completed_w()
        r["xyzFeedback"]["beforeXYZ"]["unitKey"] = "42"
        r["xyzFeedback"]["afterXYZ"]["unitKey"] = "42"
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-target-mismatch"):
            self.assess()
        r = completed_w()
        r["xyzFeedback"]["beforeXYZ"]["x"] = 1
        r["xyzFeedback"]["afterXYZ"]["x"] = .34
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-unexpected-start-position"):
            self.assess()

    def test_rejects_stale_or_reversed_receipt(self):
        r = completed_w()
        r["xyzFeedback"]["beforeXYZ"].update(
            startedAtUtc="2026-11-11T07:07:02.500Z",
            completedAtUtc="2026-11-11T07:07:02.510Z")
        r["xyzFeedback"]["afterXYZ"].update(
            startedAtUtc="2026-11-11T07:07:02.730Z",
            completedAtUtc="2026-11-11T07:07:02.740Z")
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-stale-or-overlapping-position"):
            self.assess()
        r = completed_w()
        r["xyzFeedback"]["beforeXYZ"].update(
            startedAtUtc="2026-11-11T07:06:42.200Z",
            completedAtUtc="2026-11-11T07:06:42.210Z")
        r["xyzFeedback"]["afterXYZ"].update(
            startedAtUtc="2026-11-11T07:06:42.430Z",
            completedAtUtc="2026-11-11T07:06:42.440Z")
        self.write(r=r)
        with self.assertRaisesRegex(ValueError, "feedback-stale-or-overlapping-position"):
            self.assess()

    def test_no_proposed_action_blocks_and_cli_output_does_not_overwrite(self):
        with self.assertRaisesRegex(ValueError, "feedback-no-proposed-action"):
            self.assess(-.05,0)
        args=["--basis",str(self.basis_file),"--position",str(self.position_file),
              "--receipt",str(self.receipt_file),"--target-x","-.6","--target-z","-.075"]
        output=self.root/"assessment.json"
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(feedback.main(args+["--out",str(output)]),0)
        self.assertEqual(json.loads(stream.getvalue()),
                         json.loads(output.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(feedback.main(args+["--out",str(output)]),2)
        self.assertEqual(json.loads(stream.getvalue())["status"],"blocked")


if __name__=="__main__":
    unittest.main()
