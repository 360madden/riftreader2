"""Offline basis-derived waypoint recommendation reuses RR2's bounded controller."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_move_basis_waypoint as waypoint
from tests.test_physical_waypoint_decision import BUILD, UNIT, START_TICKS, position
from tests.test_analyze_physical_turn_pair import IDENTITY, report


def basis():
    return {
        "schemaVersion": 1,
        "status": "offline-physical-key-basis-candidate",
        "navigationEligible": False,
        "movementEligible": False,
        "headingQualified": False,
        "sameFacingConfirmed": False,
        "gameResponseVerified": False,
        "cardinalGeometryCandidate": True,
        "identity": {
            "machine": "AMD-DESKTOP", "processId": 44888,
            "processStartUtcTicks": str(START_TICKS),
            "gameBuildSha256": BUILD, "unitKey": UNIT,
        },
        "samples": {
            "w": {}, "s": {}, "q": {}, "e": {},
            "laterW": {
                "vxCandidate": -.006, "vzCandidate": -.00075,
                "afterSampleUtc": "2026-11-11T07:06:41.500Z",
            },
        },
        "sourceReceiptsSha256": dict(zip(("w","s","q","e","laterW"),
                                         (("A"*64,"B"*64,"C"*64,"D"*64,"E"*64)))),
        "laterFacingReprojectionCandidate": {
            "status": "unverified-rigid-rotation-model",
            "sameFacingConfirmed": False,
            "navigationEligible": False,
            "modeledVectors": {
                "s": {"vxPerMillisecondCandidate": .003, "vzPerMillisecondCandidate": .000375},
                "q": {"vxPerMillisecondCandidate": -.00075, "vzPerMillisecondCandidate": .006},
                "e": {"vxPerMillisecondCandidate": .00075, "vzPerMillisecondCandidate": -.006},
            },
        },
    }


class PhysicalBasisWaypointTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.basis_path = self.root / "basis.json"
        self.native_path = self.root / "native.json"
        self.store()

    def store(self, *, basis_value=None, native_value=None):
        self.basis_path.write_text(json.dumps(basis() if basis_value is None else basis_value),
                                   encoding="utf-8")
        self.native_path.write_text(json.dumps(position() if native_value is None else native_value),
                                    encoding="utf-8")

    def preview(self, x=-.6, z=-.075, y=None):
        return waypoint.preview(self.basis_path, self.native_path, x, z, y)

    def test_real_controller_suggests_single_bounded_w_from_offline_basis(self):
        result = self.preview()
        self.assertEqual("offline-physical-waypoint-candidate", result["status"])
        self.assertEqual("suggested-one-pulse", result["decision"])
        self.assertEqual("w", result["candidateAction"]["key"])
        self.assertEqual(100, result["candidateAction"]["holdMilliseconds"])
        expected = result["candidateAction"]["predictedAfterXYZCandidate"]
        delta = result["candidateAction"]["predictedDeltaXYZCandidate"]
        self.assertAlmostEqual(-.6, expected["x"])
        self.assertAlmostEqual(-.075, expected["z"])
        self.assertAlmostEqual(0, expected["y"])
        self.assertAlmostEqual(-.6, delta["x"])
        self.assertAlmostEqual(-.075, delta["z"])
        self.assertAlmostEqual(0, delta["y"])
        self.assertFalse(result["navigationEligible"])
        self.assertFalse(result["arrivalQualified"])
        self.assertFalse(result["worldInstanceMatched"])
        self.assertFalse(result["gameResponseVerified"])
        self.assertFalse(result["inputSent"])
        self.assertRegex(result["basisReportSha256"], "^[0-9A-F]{64}$")
        self.assertRegex(result["nativePositionReportSha256"], "^[0-9A-F]{64}$")

    def test_goal_within_tolerance_yields_no_action_not_arrival(self):
        result = self.preview(x=-.08,z=0)
        self.assertEqual("within-tolerance-candidate", result["decision"])
        self.assertIsNone(result["candidateAction"])
        self.assertFalse(result["arrivalQualified"])

    def test_far_and_vertical_goals_refused(self):
        with self.assertRaisesRegex(ValueError, "goal exceeds"):
            self.preview(-8, 0)
        with self.assertRaisesRegex(ValueError, "waypoint-vertical-target-unqualified"):
            self.preview(-.6, -.075, 5)

    def test_wrong_process_or_unit_refused(self):
        value = basis()
        value["identity"]["processId"] += 1
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-native-basis-identity-mismatch"):
            self.preview()
        value = basis()
        value["identity"]["unitKey"] = "42"
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-native-basis-identity-mismatch"):
            self.preview()

    def test_four_measured_vectors_require_position_after_last_sample(self):
        value = basis()
        value["samples"].pop("laterW")
        value["sourceReceiptsSha256"].pop("laterW")
        value["laterFacingReprojectionCandidate"] = None
        for key, (x, z) in {"w": (-.006, 0), "s": (.003, 0),
                            "q": (0, .006), "e": (0, -.006)}.items():
            value["samples"][key] = {
                "vxCandidate": x, "vzCandidate": z,
                "afterSampleUtc": "2026-11-11T07:06:41.500Z",
            }
        self.store(basis_value=value)
        result = self.preview(x=0, z=.6)
        self.assertEqual("q", result["candidateAction"]["key"])
        self.assertEqual(100, result["candidateAction"]["holdMilliseconds"])

        value["samples"]["e"]["afterSampleUtc"] = "2026-11-11T07:06:43Z"
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-position-precedes-calibration"):
            self.preview()

    def test_current_position_must_follow_basis_and_model_must_be_available(self):
        value = basis()
        value["samples"]["laterW"]["afterSampleUtc"] = "2026-11-11T07:06:43Z"
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-position-precedes-calibration"):
            self.preview()
        value = basis()
        value["laterFacingReprojectionCandidate"] = None
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-later-facing-model-unavailable"):
            self.preview()
        value = basis()
        value["cardinalGeometryCandidate"] = False
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-basis-unqualified"):
            self.preview()

    def test_source_hashes_and_model_numbers_fail_closed(self):
        value = basis()
        value["sourceReceiptsSha256"]["q"] = value["sourceReceiptsSha256"]["e"]
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-basis-source-hashes-invalid"):
            self.preview()
        value = basis()
        value["laterFacingReprojectionCandidate"]["modeledVectors"]["q"]["vxPerMillisecondCandidate"] = 0
        value["laterFacingReprojectionCandidate"]["modeledVectors"]["q"]["vzPerMillisecondCandidate"] = 0
        self.store(basis_value=value)
        with self.assertRaisesRegex(ValueError, "waypoint-basis-vector-zero"):
            self.preview()

    def test_cli_does_not_overwrite_or_send_input(self):
        args = ["--basis", str(self.basis_path), "--position", str(self.native_path),
                "--target-x", "-.6", "--target-z", "-.075"]
        output = self.root / "candidate.json"
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(waypoint.main(args + ["--out", str(output)]), 0)
        self.assertEqual(json.loads(stream.getvalue()),
                         json.loads(output.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(StringIO()) as stream:
            self.assertEqual(waypoint.main(args + ["--out", str(output)]), 2)
        self.assertEqual("blocked", json.loads(stream.getvalue())["status"])

    def pose(self, angles):
        identity = dict(IDENTITY, executableSha256=BUILD)
        value = report("actor-pose", [1, 2, 3], angles, identity=identity)
        for row, fraction in zip(value["observations"], (400, 600, 800)):
            row["startedAtUtc"] = f"2026-11-11T07:06:41.{fraction}Z"
            row["completedAtUtc"] = f"2026-11-11T07:06:41.{fraction + 1}Z"
        value["observation"] = deepcopy(value["observations"][-1])
        path = self.root / "pose.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_actor_pose_reorients_all_keys_across_quadrants(self):
        # Existing calibration points W southwest. Current yaw 90 puts W west,
        # Q north, E south and S east while keeping each measured key speed.
        pose = self.pose([90, 90, 90])
        for key, x, z in (("w", -.6, 0), ("q", 0, .6),
                          ("e", 0, -.6), ("s", .4, 0)):
            with self.subTest(key=key):
                result = waypoint.preview(self.basis_path, self.native_path, x, z,
                                          actor_pose_path=pose)
                self.assertEqual(key, result["candidateAction"]["key"])
                self.assertAlmostEqual(0, result["candidateAction"]
                                       ["predictedAfterDistanceCandidate"], places=2)
                self.assertFalse(result["inputSent"])
                self.assertFalse(result["headingQualified"])
        pose = self.pose([-179.999, 180, 179.999])
        result = waypoint.preview(self.basis_path, self.native_path, 0, -.6,
                                  actor_pose_path=pose)
        self.assertEqual("w", result["candidateAction"]["key"])
        self.assertTrue(result["directionModelCandidate"]["stability"]
                        ["sampledPoseStableCandidate"])

    def test_actor_model_refuses_motion_wrong_epoch_or_old_pose(self):
        pose = self.pose([90, 91, 92])
        with self.assertRaisesRegex(ValueError, "waypoint-pose-not-stable"):
            waypoint.preview(self.basis_path, self.native_path, -.6, 0,
                             actor_pose_path=pose)
        pose = self.pose([90, 90, 90])
        wrong_epoch = json.loads(pose.read_text(encoding="utf-8"))
        wrong_epoch["identity"]["processStartUtcTicks"] += 1
        for row in wrong_epoch["observations"]:
            row["identity"]["processStartUtcTicks"] += 1
        wrong_epoch["observation"] = deepcopy(wrong_epoch["observations"][-1])
        pose.write_text(json.dumps(wrong_epoch), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "waypoint-pose-identity-mismatch"):
            waypoint.preview(self.basis_path, self.native_path, -.6, 0,
                             actor_pose_path=pose)
        pose = self.pose([90, 90, 90])
        for first, second in (("45.000", "45.200"), ("41.600", "41.700")):
            native = position()
            for row, stamp in zip(native["observations"], (first, second)):
                row["startedAtUtc"] = f"2026-11-11T07:06:{stamp}Z"
                row["completedAtUtc"] = f"2026-11-11T07:06:{stamp[:-1]}1Z"
            self.native_path.write_text(json.dumps(native), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "waypoint-pose-position-gap-invalid"):
                waypoint.preview(self.basis_path, self.native_path, -.6, 0,
                                 actor_pose_path=pose)


if __name__ == "__main__":
    unittest.main()
