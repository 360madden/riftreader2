"""Offline validation of the conditional native selected-position candidate contract."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tests.test_physical_facing import optical_camera
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY
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


def burst_report():
    source = report()
    first = source["observation"]
    second = deepcopy(first)
    second.update(startedAtUtc="2026-11-17T19:00:00.0200000Z",
                  completedAtUtc="2026-11-17T19:00:00.0300000Z",
                  status="no-target", rawFallbackKey="0", targetKey=None,
                  targetUnitIdCandidate=None, targetEntityDecimal=None,
                  targetPositionCandidate=None, targetPositionRawBits=None)
    source.update(contractVersion="native-current-selected-position-candidate-burst/1",
                  identity=REPORT_IDENTITY, requestedSamples=2, completedSamples=2,
                  observation=second, observations=[first, second])
    return source


class PhysicalSelectedPositionTests(unittest.TestCase):
    def setUp(self):
        # Use the synthetic reader rather than this machine's registered bundle.
        self.enterContext(patch.dict("os.environ", {
            "RR2_PHYSICAL_TOOLS_ROOT": "debug", "RR2_NATIVE_READER": "",
        }))

    def test_bounded_burst_accepts_changed_target_and_rejects_forged_rows(self):
        for fault in ("valid", "missing", "identity", "self", "overlap"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                exe = Path(directory) / "reader.exe"
                output = Path(directory) / "target.json"
                exe.write_bytes(b"MZ")
                source = burst_report()
                if fault == "missing":
                    source["observations"].pop()
                elif fault == "identity":
                    source["observations"][0]["identity"] = {**REPORT_IDENTITY, "processId": 999}
                elif fault == "self":
                    source["observations"][0]["selfKey"] = "99"
                elif fault == "overlap":
                    source["observations"][1]["startedAtUtc"] = "2026-11-17T19:00:00.0050000Z"
                def run(command, **kwargs):
                    self.assertEqual("sample-current-selected-position", command[1])
                    self.assertEqual(["--samples", "2", "--interval-ms", "0"], command[-4:])
                    output.write_text(json.dumps(source), encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "recordType": "native-current-selected-position-summary/1",
                        "status": "complete", "selectionStatus": "no-target",
                        "completedSamples": 2, "output": str(output)}), "")
                with patch.object(physical_rift.socket, "gethostname", return_value="AMD-DESKTOP"), \
                     patch.object(physical_rift.observe_physical, "_identity", return_value=IDENTITY), \
                     patch.object(physical_rift, "NATIVE_EXE", exe), \
                     patch.object(physical_rift.subprocess, "run", side_effect=run), \
                     redirect_stdout(io.StringIO()) as stdout:
                    exit_code = physical_rift.main([
                        "--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                        "--read-native", "selected-position", "--samples", "2",
                        "--interval-ms", "0", "--output", str(output)])
                result = json.loads(stdout.getvalue())
                if fault == "valid":
                    self.assertEqual(0, exit_code)
                    self.assertEqual(["position-candidate", "no-target"],
                                     [v["status"] for v in result["nativeBurstValues"]])
                    self.assertEqual("no-target", result["nativeValues"]["status"])
                else:
                    self.assertEqual(2, exit_code)
                    self.assertEqual("invalid-native-reader-report", result["reason"])

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
