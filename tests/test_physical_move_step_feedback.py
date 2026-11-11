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

    def assess(self, x=-.6, z=-.075):
        return feedback.compare(self.basis_file, self.position_file, x, z, self.receipt_file)

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

    def test_divergent_direction_means_stop_and_review(self):
        r = completed_w()
        r["xyzFeedback"]["afterXYZ"]["x"] = -.10
        r["xyzFeedback"]["deltaXYZ"]["x"] = -.10
        r["xyzFeedback"]["planarDisplacementCandidate"] = (.10**2 + .0825**2)**.5
        self.write(r=r)
        result = self.assess()
        self.assertEqual(result["comparison"], "candidate-divergent")
        self.assertEqual(result["decision"], "stop-and-review")
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
