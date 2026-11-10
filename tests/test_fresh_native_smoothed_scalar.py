"""Offline pinned scalar client tests; never starts a VM or sends game input."""
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

from scripts import fresh_native_smoothed_scalar as scalar
from tests.test_sample_current_native_vitals import EXPECTED_VM, EXPECTED_GAME


class SmoothedScalarClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.evidence = Path(temporary.name)
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962,
                                    expected_machine_name="RIFT-LAB-2")
        now = datetime.now(timezone.utc).isoformat()
        self.status = {
            "host": {"connected": True, "machineName": "RIFT-LAB-2",
                     "vmIdentity": dict(EXPECTED_VM), "instanceId": "a" * 32},
            "guest": {"nativeSmoothedScalarVersion": 1, "nativeReadLeaseVersion": 1,
                      "instanceId": "a" * 32}}
        values = (0.5, 1.5, 2.5, 0.25)
        self.report = {
            "identity": {**EXPECTED_GAME, "executablePath": r"C:\RIFT\rift_x64.exe",
                         "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
            "startedAtUtc": now, "completedAtUtc": now,
            "playerKeyDecimal": "123", "playerEntityDecimal": "2097152",
            "componentAddressDecimal": "4194304",
            "rawBits": [struct.unpack("<I", struct.pack("<f", x))[0] for x in values],
            "currentCandidate": values[0], "sourceCandidate": values[1],
            "targetCandidate": values[2], "factorCandidate": values[3],
            "headingQualified": False, "qualification": scalar.QUALIFICATION}
        self.response = {"nativeSmoothedScalarVersion": 1, "instanceId": "a" * 32,
                         "hashMode": "fresh-bytes", "observedAtUtc": now,
                         "report": self.report}

    def query(self, client=None):
        client = client or Mock()
        client.request.side_effect = [self.status, self.response]
        with patch.object(scalar.HostConfig, "load", return_value=self.host), \
                patch.object(scalar, "verify_identity") as verify, \
                patch.object(scalar, "EVIDENCE", self.evidence):
            result = scalar.query(self.config, EXPECTED_VM, {"lab": "lab2", **EXPECTED_GAME},
                                  Path("host.json"), client_factory=lambda _: client)
        self.assertEqual(2, verify.call_count)
        return result, client

    def assert_unpublished(self):
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_exact_bits_and_pin_are_saved_with_source_hash(self):
        summary, client = self.query()
        self.assertEqual("candidate-only", summary["status"])
        self.assertFalse(summary["metrics"]["headingQualified"])
        self.assertEqual(2.5, summary["metrics"]["targetCandidate"])
        self.assertEqual("4194304", summary["metrics"]["componentAddressDecimal"])
        self.assertEqual("/api/native-smoothed-scalar", client.request.call_args_list[1].args[0])
        self.assertEqual(EXPECTED_GAME["processId"],
                         client.request.call_args_list[1].kwargs["payload"]["processId"])
        raw = Path(summary["sourceReport"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest().upper(), summary["sourceReportSha256"])
        self.assertEqual(self.report, json.loads(raw))

    def test_wrong_capability_blocks_before_post(self):
        original = copy.deepcopy(self.status)
        for field, value in (("nativeSmoothedScalarVersion", None),
                             ("nativeReadLeaseVersion", False), ("instanceId", "incorrect")):
            self.status = copy.deepcopy(original)
            if value is None:
                del self.status["guest"][field]
            else:
                self.status["guest"][field] = value
            client = Mock()
            with self.subTest(field=field), self.assertRaisesRegex(scalar.Blocked, "endpoint-not-ready"):
                self.query(client)
            client.request.assert_called_once_with("/api/status", method="GET")
        self.assert_unpublished()

    def test_wrong_owner_epoch_or_float_bits_do_not_publish(self):
        original = copy.deepcopy(self.report)
        for value in (4194304, "0x400000", "4194305", "0", None):
            self.report = copy.deepcopy(original)
            self.response["report"] = self.report
            self.report["componentAddressDecimal"] = value
            with self.subTest(value=value), self.assertRaisesRegex(scalar.Blocked, "owner-invalid"):
                self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["identity"]["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(scalar.Blocked, "identity-mismatch"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["rawBits"][0] ^= 1
        with self.assertRaisesRegex(scalar.Blocked, "raw-mismatch"):
            self.query()
        self.assert_unpublished()

    def test_nonfinite_extra_key_or_false_claim_does_not_publish(self):
        original = copy.deepcopy(self.report)
        self.report["factorCandidate"] = float("nan")
        with self.assertRaisesRegex(scalar.Blocked, "value-invalid"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["headingQualified"] = True
        with self.assertRaisesRegex(scalar.Blocked, "contract-invalid"):
            self.query()
        self.report = copy.deepcopy(original)
        self.response["report"] = self.report
        self.report["invented"] = 42
        with self.assertRaisesRegex(scalar.Blocked, "contract-invalid"):
            self.query()
        self.assert_unpublished()

    def test_oversized_integer_is_a_blocked_candidate_not_an_uncaught_exception(self):
        self.report["currentCandidate"] = 10 ** 400
        with self.assertRaisesRegex(scalar.Blocked, "value-invalid"):
            self.query()
        self.assert_unpublished()

    def test_stale_sample_does_not_publish(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.report.update(startedAtUtc=past, completedAtUtc=past)
        with self.assertRaisesRegex(scalar.Blocked, "acquisition-stale"):
            self.query()
        self.assert_unpublished()


if __name__ == "__main__":
    unittest.main()
