"""Offline contract tests for C# orientation candidate read-through."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import fresh_native_orientation as native
from tests.test_sample_current_native_vitals import EXPECTED_VM, EXPECTED_GAME


class OrientationClientTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.evidence = Path(temp.name)
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962, expected_machine_name="RIFT-LAB-2")
        now = datetime.now(timezone.utc).isoformat()
        self.status = {
            "host": {"connected": True, "machineName": "RIFT-LAB-2",
                     "vmIdentity": dict(EXPECTED_VM), "instanceId": "a" * 32},
            "guest": {"nativeOrientationVersion": 1, "nativeReadLeaseVersion": 1, "instanceId": "a" * 32}}
        row = {"sourceOffset": 0x60, "rawBits": [0] * 9, "rowMajorF32": [0.0] * 9,
               "status": "structural-y-planar-matrix-candidate", "orthonormalError": 0,
               "determinant": 1, "yPlanarError": 0,
               "planarAngleRadiansCandidate": 1.5, "planarAngleDegreesCandidate": 85.943669}
        self.report = {
            "identity": {**EXPECTED_GAME, "executablePath": r"C:\RIFT\rift_x64.exe",
                         "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
            "startedAtUtc": now, "completedAtUtc": now,
            "unitKey": "123", "refreshHandleRaw": "0x0000000000000000", "refreshFlagRaw": 0,
            "primary": row, "secondary": {**row, "sourceOffset": 0x94},
            "qualification": native.QUALIFICATION}
        self.response = {"nativeOrientationVersion": 1, "instanceId": "a" * 32,
                         "hashMode": "fresh-bytes", "observedAtUtc": now, "report": self.report}

    def run_query(self, client=None):
        client = client or Mock()
        client.request.side_effect = [self.status, self.response]
        with patch.object(native.HostConfig, "load", return_value=self.host), \
                patch.object(native, "verify_identity"), \
                patch.object(native, "EVIDENCE", self.evidence):
            result = native.query(self.config, EXPECTED_VM, {"lab": "lab2", **EXPECTED_GAME},
                                  Path("host.json"), client_factory=lambda _: client)
        return result, client

    def assert_no_publication(self):
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_one_fresh_authenticated_candidate_is_recorded(self):
        result, client = self.run_query()
        self.assertEqual("candidate-only", result["status"])
        self.assertEqual(self.report["unitKey"], result["metrics"]["unitKey"])
        self.assertAlmostEqual(85.943669, result["metrics"]["candidateAnglesDegrees"]["primary"])
        self.assertEqual(self.report, json.loads(Path(result["sourceReport"]).read_text(encoding="utf-8")))
        self.assertEqual("/api/native-orientation", client.request.call_args_list[1].args[0])
        self.assertEqual("persistent-control-agent", result["transport"])

    def test_missing_capability_blocks_before_post(self):
        original = copy.deepcopy(self.status)
        for field, value in (("nativeOrientationVersion", None), ("nativeReadLeaseVersion", False),
                             ("instanceId", "invalid")):
            self.status = copy.deepcopy(original)
            if value is None:
                self.status["guest"].pop(field)
            else:
                self.status["guest"][field] = value
            client = Mock()
            with self.subTest(field=field), self.assertRaises(native.Blocked):
                self.run_query(client)
            client.request.assert_called_once_with("/api/status", method="GET")
        self.assert_no_publication()

    def test_stale_epoch_and_unqualified_angle_never_publish(self):
        self.report["identity"]["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(native.Blocked, "identity-mismatch"):
            self.run_query()
        self.report["identity"]["processStartUtcTicks"] -= 1
        self.report["primary"]["status"] = "unqualified-matrix-shape"
        with self.assertRaisesRegex(native.Blocked, "angle-unqualified"):
            self.run_query()
        self.assert_no_publication()

    def test_stale_response_and_nonfinite_angle_never_publish(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.report.update(startedAtUtc=old, completedAtUtc=old)
        with self.assertRaisesRegex(native.Blocked, "acquisition-stale"):
            self.run_query()
        self.report["startedAtUtc"] = self.response["observedAtUtc"]
        self.report["completedAtUtc"] = self.response["observedAtUtc"]
        self.report["primary"]["planarAngleDegreesCandidate"] = float("nan")
        with self.assertRaisesRegex(native.Blocked, "matrix-values-invalid"):
            self.run_query()
        self.assert_no_publication()


if __name__ == "__main__":
    unittest.main()
