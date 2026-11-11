"""Offline empirical four-direction movement basis from already completed helper receipts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import contextlib
from io import StringIO
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_move_basis as basis
from tests.test_physical_move_key_calibration import receipt


class PhysicalMoveBasisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = {}
        for index, (key, dx, dz) in enumerate(
                (("w", -2, 0), ("s", 1, 0), ("q", 0, 1), ("e", 0, -1))):
            self.paths[key] = self.save(key, index, dx, dz)

    def save(self, key, index, dx, dz):
        base = receipt()
        base["keys"] = [key]
        before, after = (base["xyzFeedback"]["beforeXYZ"],
                         base["xyzFeedback"]["afterXYZ"])
        t = datetime(2026, 11, 11, 14, 50, 0, tzinfo=timezone.utc) + timedelta(seconds=2*index)
        def iso(ms):
            return (t + timedelta(milliseconds=ms)).isoformat()
        before.update(startedAtUtc=iso(0), completedAtUtc=iso(10))
        after.update(startedAtUtc=iso(700), completedAtUtc=iso(710),
                     x=before["x"]+dx, z=before["z"]+dz)
        base["xyzFeedback"].update(
            deltaXYZ={"x": dx, "y": 0, "z": dz},
            planarDisplacementCandidate=math.hypot(dx, dz),
            captureGapSeconds=.690)
        path = self.root / f"{key}-{index}.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        return path

    def analyze(self, *, later_forward=None):
        return basis.analyze(self.paths, later_forward=later_forward)

    def test_four_vectors_generate_cardinal_candidate_without_navigation_authority(self):
        result = self.analyze()
        self.assertEqual("offline-physical-key-basis-candidate", result["status"])
        self.assertTrue(result["cardinalGeometryCandidate"])
        self.assertFalse(result["navigationEligible"])
        self.assertFalse(result["sameFacingConfirmed"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertEqual(set(result["samples"]), {"w", "s", "q", "e"})
        self.assertEqual(len(set(result["sourceReceiptsSha256"].values())), 4)
        self.assertAlmostEqual(result["geometry"]["forwardVsBackward"]
                               ["unsignedAngleDegreesCandidate"], 180)
        self.assertAlmostEqual(result["geometry"]["forwardVsLeftStrafe"]
                               ["unsignedAngleDegreesCandidate"], 90)
        self.assertAlmostEqual(result["geometry"]["leftVsRightStrafe"]
                               ["unsignedAngleDegreesCandidate"], 180)
        self.assertAlmostEqual(result["geometry"]["forwardVsBackward"]
                               ["firstSpeedOverSecondCandidate"], 2)

    def test_later_forward_reports_direction_change_but_not_heading(self):
        later = self.save("w", 4, -.5, 1)
        result = self.analyze(later_forward=later)
        self.assertIn("earlyVsLaterForward", result["geometry"])
        self.assertTrue(result["cardinalGeometryCandidate"])
        self.assertFalse(result["sameFacingConfirmed"])
        self.assertFalse(result["navigationEligible"])
        self.assertGreater(
            result["geometry"]["earlyVsLaterForward"]["unsignedAngleDegreesCandidate"], 10)
        self.assertEqual(len(result["samples"]), 5)
        # A large unverified direction change does not produce a strafe forecast.
        self.assertIsNone(result["laterFacingReprojectionCandidate"])

    def test_small_later_direction_change_reprojects_keys_without_authorizing_input(self):
        later = self.save("w", 4, -2, -.5)
        result = self.analyze(later_forward=later)
        model = result["laterFacingReprojectionCandidate"]
        self.assertEqual("unverified-rigid-rotation-model", model["status"])
        self.assertFalse(model["sameFacingConfirmed"])
        self.assertFalse(model["navigationEligible"])
        self.assertGreater(model["relativeDirectionChangeDegreesCandidate"], 10)
        self.assertLess(model["relativeDirectionChangeDegreesCandidate"], 20)
        self.assertLess(model["modeledVectors"]["q"]["vxPerMillisecondCandidate"], 0)
        self.assertGreater(model["modeledVectors"]["q"]["vzPerMillisecondCandidate"], 0)
        self.assertFalse(result["headingQualified"])
        later = self.save("w", 5, -3, -.5)
        # This test remains chronological because its timestamp follows E.
        result = self.analyze(later_forward=later)
        self.assertIsNone(result["laterFacingReprojectionCandidate"])

    def test_rejects_identity_conflict_duplicate_source_and_key_swap(self):
        original = json.loads(self.paths["e"].read_text(encoding="utf-8"))
        changed = deepcopy(original)
        changed["processStartUtcTicks"] += 1
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "basis-player-process-build-mismatch"):
            self.analyze()
        self.paths["e"].write_text(json.dumps(original), encoding="utf-8")
        self.paths["e"] = self.paths["q"]
        with self.assertRaisesRegex(ValueError, "basis-key-mismatch"):
            self.analyze()
        self.paths["e"] = self.save("e", 3, 0, -1)
        self.assertEqual("offline-physical-key-basis-candidate", self.analyze()["status"])
        self.paths["e"] = self.paths["w"]
        with self.assertRaisesRegex(ValueError, "basis-key-mismatch"):
            self.analyze()

    def test_rejects_out_of_order_timestamps_and_malformed_input(self):
        original = json.loads(self.paths["e"].read_text(encoding="utf-8"))
        changed = deepcopy(original)
        changed["xyzFeedback"]["beforeXYZ"]["startedAtUtc"] = "2026-11-11T14:49:59+00:00"
        changed["xyzFeedback"]["beforeXYZ"]["completedAtUtc"] = "2026-11-11T14:49:59.010+00:00"
        changed["xyzFeedback"]["afterXYZ"]["startedAtUtc"] = "2026-11-11T14:49:59.700+00:00"
        changed["xyzFeedback"]["afterXYZ"]["completedAtUtc"] = "2026-11-11T14:49:59.710+00:00"
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "basis-chronology-invalid"):
            self.analyze()
        self.paths["e"].write_text(json.dumps(original), encoding="utf-8")
        changed = deepcopy(original)
        changed["xyzFeedback"]["deltaXYZ"]["x"] = 100
        self.paths["e"].write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "helper-native-delta-mismatch"):
            self.analyze()

    def test_cli_file_new_only(self):
        args = []
        for key, flag in (("w", "--forward"), ("s", "--backward"),
                          ("q", "--left"), ("e", "--right")):
            args.extend([flag, str(self.paths[key])])
        out = self.root / "comparison.json"
        with contextlib.redirect_stdout(StringIO()) as capture:
            self.assertEqual(basis.main(args+["--out",str(out)]),0)
        self.assertEqual(json.loads(capture.getvalue()),
                         json.loads(out.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as capture:
            self.assertEqual(basis.main(args+["--out",str(out)]),2)
        self.assertEqual(json.loads(capture.getvalue())["status"],"blocked")


if __name__ == "__main__":
    unittest.main()
