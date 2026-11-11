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


if __name__ == "__main__":
    unittest.main()
