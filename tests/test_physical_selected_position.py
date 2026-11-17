"""Offline validation of the conditional native selected-position candidate contract."""
from copy import deepcopy
import unittest
from tests.test_physical_facing import optical_camera
from tests.test_physical_only_selection import REPORT_IDENTITY
from tests.test_physical_unit_positions import bits
from scripts import physical_rift


def report():
    xyz = {"x": 7181.0, "y": 821.0, "z": 3135.0}
    camera = optical_camera()
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-selected-position-candidate-sample/1",
        "status": "complete",
        "observation": {
            "identity": REPORT_IDENTITY,
            "startedAtUtc": "2026-11-17T19:00:00.0000000Z",
            "completedAtUtc": "2026-11-17T19:00:00.0100000Z",
            "selfKey": "42",
            "status": "position-candidate",
            "selectionBranch": "selection-component-missing-fallback",
            "rawFallbackKey": "43",
            "targetKey": "43",
            "targetUnitIdCandidate": "u000000000000002B",
            "targetEntityDecimal": "536870912",
            "targetPositionCandidate": xyz,
            "targetPositionRawBits": bits(xyz),
            "opticalCameraCandidate": camera,
            "opticalCameraAfterCandidate": deepcopy(camera),
            "cameraStableCandidate": True,
            "qualification": ("conditional raw selection and cached position candidate; "
                              "selected-target semantics, freshness and restart unverified"),
        },
    }


class PhysicalSelectedPositionTests(unittest.TestCase):
    def test_position_candidate_projects_and_retains_raw_key(self):
        value = physical_rift._native_values("selected-position", report())
        self.assertEqual("position-candidate", value["status"])
        self.assertEqual("43", value["targetKey"])
        self.assertEqual("43", value["rawFallbackKey"])
        self.assertEqual("42", value["selfKey"])
        self.assertTrue(value["cameraStableCandidate"])
        self.assertEqual(7181, value["targetPositionXYZCandidate"]["x"])

    def test_no_target_is_unavailable_without_making_up_coordinates(self):
        source = report()
        observation = source["observation"]
        observation.update(status="no-target", rawFallbackKey="0", targetKey=None,
                           targetUnitIdCandidate=None, targetEntityDecimal=None,
                           targetPositionCandidate=None, targetPositionRawBits=None)
        value = physical_rift._native_values("selected-position", source)
        self.assertEqual("no-target", value["status"])
        self.assertIsNone(value["targetKey"])
        self.assertEqual("unavailable", value["targetScreenPointCandidate"]["status"])

    def test_active_override_does_not_publish_fallback_as_selected_key(self):
        source = report()
        row = source["observation"]
        row.update(status="selection-override-unresolved", selectionBranch="selection-override-active",
                   targetKey=None, targetUnitIdCandidate=None, targetEntityDecimal=None,
                   targetPositionCandidate=None, targetPositionRawBits=None)
        value = physical_rift._native_values("selected-position", source)
        self.assertIsNone(value["targetKey"])
        row["targetKey"] = "43"
        with self.assertRaises(ValueError):
            physical_rift._native_values("selected-position", source)

    def test_forged_payload_or_stability_is_rejected(self):
        for mode in ("bits", "entity", "key", "camera", "branch", "time"):
            source = report()
            row = source["observation"]
            if mode == "bits":
                row["targetPositionRawBits"] = [0, 0, 0]
            if mode == "entity":
                row["targetEntityDecimal"] = "0"
            if mode == "key":
                row["targetUnitIdCandidate"] = "u0000000000000001"
            if mode == "camera":
                row["cameraStableCandidate"] = False
            if mode == "branch":
                row["selectionBranch"] = "made-up-branch"
            if mode == "time":
                row["completedAtUtc"] = "2026-11-17T18:00:00.0000000Z"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                physical_rift._native_values("selected-position", source)


if __name__ == "__main__":
    unittest.main()
