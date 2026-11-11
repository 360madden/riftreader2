"""Cross-check two candidate native matrix sources with physical ownership pins."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import compare_physical_orientation_actor_matrix as alias
from tests.test_analyze_physical_turn_pair import report, POS_COMPONENT


class MatrixSourceAliasTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.orientation_path = self.root / "orientation.json"
        self.pose_path = self.root / "pose.json"
        self.save()

    def save(self, orientation=None, pose=None):
        ori = report("orientation", [1, 2], [10, 10]) if orientation is None else orientation
        actor = report("actor-pose", [4, 5], [10, 10]) if pose is None else pose
        self.orientation_path.write_text(json.dumps(ori, allow_nan=False), encoding="utf-8")
        self.pose_path.write_text(json.dumps(actor, allow_nan=False), encoding="utf-8")

    def compare(self):
        return alias.compare(self.orientation_path, self.pose_path)

    def test_exact_raw_bit_equality_is_candidate_only(self):
        r = self.compare()
        self.assertEqual("stable-separate-captures-same-matrix-bits-candidate", r["status"])
        self.assertEqual(0, r["rawBitElementMismatchCount"])
        self.assertTrue(r["rawBitsEqualBetweenBursts"])
        self.assertTrue(r["positionSecondaryStableWithinBurst"])
        self.assertTrue(r["actorMatrixStableWithinBurst"])
        self.assertEqual("0x94", r["positionSecondaryOffset"])
        self.assertEqual("0x398", r["actorMatrixOffset"])
        self.assertEqual(str(POS_COMPONENT), r["positionComponent"])
        self.assertFalse(r["actorHeadingQualified"])
        self.assertFalse(r["independentGameResponseVerified"])
        self.assertFalse(r["navigationEligible"])
        self.assertEqual(len(set([r["orientationSourceSha256"], r["actorPoseSourceSha256"]])),2)

    def test_changed_actor_matrix_does_not_invent_alias_failure(self):
        pose = report("actor-pose", [4, 5], [20, 20])
        self.save(pose=pose)
        r = self.compare()
        self.assertEqual("matrix-copy-not-established-from-captures", r["status"])
        self.assertFalse(r["rawBitsEqualBetweenBursts"])
        self.assertGreater(r["rawBitElementMismatchCount"], 0)
        self.assertFalse(r["navigationEligible"])
        self.assertFalse(r["actorHeadingQualified"])

    def test_burst_changed_state_disqualifies_stationary_match(self):
        pose = report("actor-pose", [4, 5], [10, 20])
        self.save(pose=pose)
        r = self.compare()
        self.assertFalse(r["actorMatrixStableWithinBurst"])
        self.assertFalse(r["rawBitsEqualBetweenBursts"])
        orientation = report("orientation", [1, 2], [10, 20])
        self.save(orientation=orientation)
        r = self.compare()
        self.assertFalse(r["positionSecondaryStableWithinBurst"])

    def test_process_player_component_and_time_identity(self):
        pose = report("actor-pose", [4, 5], [10, 10])
        pose["observations"][0]["positionComponentDecimal"] = "777"
        pose["observations"][1]["positionComponentDecimal"] = "777"
        pose["observation"]["positionComponentDecimal"] = "777"
        self.save(pose=pose)
        with self.assertRaisesRegex(ValueError, "alias-position-component-mismatch"):
            self.compare()

        pose = report("actor-pose", [4, 5], [10, 10])
        pose["identity"]["processStartUtcTicks"] += 1
        pose["observation"]["identity"]["processStartUtcTicks"] += 1
        for row in pose["observations"]:
            row["identity"]["processStartUtcTicks"] += 1
        self.save(pose=pose)
        with self.assertRaisesRegex(ValueError, "alias-process-build-epoch-mismatch"):
            self.compare()

        self.save(pose=report("actor-pose", [50, 51], [10, 10]))
        with self.assertRaisesRegex(ValueError, "alias-bursts-not-contemporaneous"):
            self.compare()

        self.save(pose=report("actor-pose", [1, 2], [10, 10]))
        with self.assertRaisesRegex(ValueError, "alias-bursts-not-contemporaneous"):
            self.compare()

    def test_cli_and_saved_report_new_only(self):
        dest = self.root / "result.json"
        args = ["--orientation", str(self.orientation_path),
                "--actor-pose", str(self.pose_path), "--out", str(dest)]
        with contextlib.redirect_stdout(StringIO()) as output:
            self.assertEqual(0, alias.main(args))
        self.assertEqual(json.loads(output.getvalue()),
                         json.loads(dest.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as output:
            self.assertEqual(2, alias.main(args))
        self.assertEqual("blocked", json.loads(output.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
