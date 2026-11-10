"""Offline contract tests for authenticated actor/model pose read-through (no game input)."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import fresh_native_actor_pose as pose
from tests.test_sample_current_native_vitals import EXPECTED_VM, EXPECTED_GAME


def matrix(offset, values, angle=0):
    bits = [struct.unpack("<I", struct.pack("<f", value))[0] for value in values]
    return {"sourceOffset": offset, "rawBits": bits, "rowMajorF32": values,
            "status": "structural-y-planar-matrix-candidate",
            "orthonormalError": 0.0, "determinant": 1.0, "yPlanarError": 0.0,
            "planarAngleRadiansCandidate": angle * 3.141592653589793 / 180,
            "planarAngleDegreesCandidate": angle}


class ActorPoseClientTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.evidence = Path(temp.name)
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962,
                                    expected_machine_name="RIFT-LAB-2")
        now = datetime.now(timezone.utc).isoformat()
        self.status = {
            "host": {"connected": True, "machineName": "RIFT-LAB-2",
                     "vmIdentity": dict(EXPECTED_VM), "instanceId": "a" * 32},
            "guest": {"nativeActorPoseVersion": 1, "nativeReadLeaseVersion": 1,
                      "instanceId": "a" * 32}}
        identity = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
        self.report = {
            "identity": {**EXPECTED_GAME, "executablePath": r"C:\RIFT\rift_x64.exe",
                         "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
            "startedAtUtc": now, "completedAtUtc": now,
            "playerKeyDecimal": "123", "playerEntityDecimal": "2097152",
            "actorComponentDecimal": "4194304", "positionComponentDecimal": "3145728",
            "actorFlags": 0, "actorMatrix": matrix(0x398, identity),
            "modelMatrix": matrix(0x3EC, identity),
            "renderMatrix": matrix(0xA0, identity),
            "renderStatus": "normal-render-matrix-candidate",
            "renderCompositionMaxAbsDelta": 0.0, "normalRenderBranch": True,
            "actorHeadingQualified": False, "qualification": pose.QUALIFICATION}
        self.response = {"nativeActorPoseVersion": 1, "instanceId": "a" * 32,
                         "hashMode": "fresh-bytes", "observedAtUtc": now,
                         "report": self.report}

    def query(self, client=None):
        client = client or Mock()
        client.request.side_effect = [self.status, self.response]
        with patch.object(pose.HostConfig, "load", return_value=self.host), \
                patch.object(pose, "verify_identity") as verification, \
                patch.object(pose, "EVIDENCE", self.evidence):
            result = pose.query(self.config, EXPECTED_VM, {"lab": "lab2", **EXPECTED_GAME},
                                Path("host.json"), client_factory=lambda _: client)
        self.assertEqual(2, verification.call_count)
        return result, client

    def assert_not_published(self):
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_fresh_authenticated_sample_preserves_lossless_addresses_and_raw_hash(self):
        summary, client = self.query()
        self.assertEqual("candidate-only", summary["status"])
        self.assertFalse(summary["metrics"]["actorHeadingQualified"])
        self.assertEqual("123", summary["metrics"]["unitKey"])
        self.assertEqual("123", summary["metrics"]["playerKeyDecimal"])
        self.assertEqual("4194304", summary["metrics"]["actorComponentDecimal"])
        self.assertEqual("3145728", summary["metrics"]["positionComponentDecimal"])
        self.assertEqual("normal-render-matrix-candidate", summary["metrics"]["renderStatus"])
        self.assertEqual("/api/native-actor-pose", client.request.call_args_list[1].args[0])
        sent = client.request.call_args_list[1].kwargs["payload"]
        self.assertEqual(EXPECTED_GAME["processId"], sent["processId"])
        raw = Path(summary["sourceReport"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest().upper(), summary["sourceReportSha256"])
        self.assertEqual(self.report, json.loads(raw))
        saved = json.loads((Path(summary["sourceReport"]).parent / "summary.json").read_text())
        self.assertEqual(summary["sourceReportSha256"], saved["sourceReportSha256"])

    def test_capability_must_be_ready_before_post(self):
        original = copy.deepcopy(self.status)
        for field, value in (("nativeActorPoseVersion", None), ("nativeReadLeaseVersion", False),
                             ("instanceId", "incorrect")):
            self.status = copy.deepcopy(original)
            if value is None:
                del self.status["guest"][field]
            else:
                self.status["guest"][field] = value
            client = Mock()
            with self.subTest(field=field), self.assertRaisesRegex(pose.Blocked, "endpoint-not-ready"):
                self.query(client)
            client.request.assert_called_once_with("/api/status", method="GET")
        self.assert_not_published()

    def test_lossless_owner_and_process_epoch_required(self):
        original = copy.deepcopy(self.report)
        for value in (4194304, "0x400000", "4194305", "0", "-1", None):
            self.report = copy.deepcopy(original)
            self.response["report"] = self.report
            self.report["actorComponentDecimal"] = value
            with self.subTest(value=value), self.assertRaisesRegex(pose.Blocked, "owner-invalid"):
                self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["identity"]["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(pose.Blocked, "identity-mismatch"):
            self.query()
        self.assert_not_published()

    def test_matrix_float32_bits_and_composition_must_match(self):
        original = copy.deepcopy(self.report)
        self.report["actorMatrix"]["rawBits"][0] ^= 1
        with self.assertRaisesRegex(pose.Blocked, "raw-mismatch"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["renderMatrix"]["planarAngleDegreesCandidate"] = 10
        with self.assertRaisesRegex(pose.Blocked, "angle-invalid"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["renderCompositionMaxAbsDelta"] = 0.2
        with self.assertRaisesRegex(pose.Blocked, "composition-invalid"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["modelMatrix"]["rowMajorF32"][1] = float("nan")
        with self.assertRaisesRegex(pose.Blocked, "matrix-values-invalid"):
            self.query()
        self.assert_not_published()

    def test_alternate_branch_is_candidate_without_render(self):
        self.report.update(actorFlags=1, normalRenderBranch=False, renderMatrix=None,
                           renderStatus="alternate-reference-branch-not-followed",
                           renderCompositionMaxAbsDelta=None)
        summary, _ = self.query()
        self.assertIsNone(summary["metrics"]["renderAngleDegreesCandidate"])
        self.assertFalse(summary["metrics"]["actorHeadingQualified"])

    def test_stale_report_does_not_publish(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.report.update(startedAtUtc=old, completedAtUtc=old)
        with self.assertRaisesRegex(pose.Blocked, "acquisition-stale"):
            self.query()
        self.assert_not_published()


if __name__ == "__main__":
    unittest.main()
