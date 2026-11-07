import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import fresh_native_vitals as native
from tests import test_control_host as transport
from tests.test_sample_current_native_vitals import report, EXPECTED_VM, EXPECTED_GAME


class NativeVitalsClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name)
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962, expected_machine_name="RIFT-LAB-2")
        self.status = {"host": {"connected": True, "machineName": "RIFT-LAB-2", "vmIdentity": dict(EXPECTED_VM)},
                       "guest": {"nativeVitalsVersion": 1, "instanceId": "a" * 32}}
        value = report()
        now = datetime.now(timezone.utc).isoformat()
        value["observation"].update(startedAtUtc=now, completedAtUtc=now)
        self.response = {"nativeVitalsVersion": 1, "instanceId": "a" * 32,
                         "hashMode": "fresh-bytes", "observedAtUtc": now, "report": value}

    def query(self, *, client=None, verifier=None):
        client = client or Mock()
        client.request.side_effect = [self.status, self.response]
        verifier = verifier or Mock()
        with patch.object(native.HostConfig, "load", return_value=self.host), \
                patch.object(native, "verify_identity", verifier), \
                patch.object(native.vitals, "EVIDENCE", self.evidence):
            result = native.query(self.config, EXPECTED_VM, {"lab": "lab2", **EXPECTED_GAME}, Path("host.json"),
                                  client_factory=lambda _: client)
        return result, client, verifier

    def test_exact_response_persisted_with_candidate_contract_and_vm_brackets(self):
        result, client, verifier = self.query()
        self.assertEqual(2, verifier.call_count)
        self.assertEqual(result["transport"], "persistent-control-agent")
        self.assertEqual(result["activeAgentInstanceId"], "a" * 32)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["vmIdentity"], EXPECTED_VM)
        source = Path(result["sourceReport"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest().upper(), result["sourceReportSha256"])
        self.assertEqual(json.loads(source.read_bytes()), self.response["report"])
        self.assertEqual(result["metrics"]["health"]["current"], 100)
        self.assertEqual(client.request.call_args_list[1].args, ("/api/native-vitals",))
        self.assertEqual(client.request.call_args_list[1].kwargs["payload"],
                         {**EXPECTED_GAME, "executableSha256": EXPECTED_GAME["executableSha256"].lower(),
                          "machineName": "RIFT-LAB-2"})

    def test_status_identity_or_capability_mismatch_sends_no_native_command(self):
        for field, value in (("vmIdentity", {**EXPECTED_VM, "pid": 1}), ("machineName", "RIFT-LAB-1"),
                             ("connected", False), ("capability", True)):
            original = copy.deepcopy(self.status)
            if field == "capability": self.status["guest"]["nativeVitalsVersion"] = value
            else: self.status["host"][field] = value
            client, verifier = Mock(), Mock()
            with self.subTest(field=field), self.assertRaises(native.Blocked):
                self.query(client=client, verifier=verifier)
            client.request.assert_called_once_with("/api/status", method="GET")
            self.assertEqual(verifier.call_count, 2)
            self.status = original
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_wrong_native_identity_build_or_promoted_qualification_rejected(self):
        cases = [("processId", 1), ("processStartUtcTicks", EXPECTED_GAME["processStartUtcTicks"] + 1),
                 ("executableSha256", "0" * 64)]
        for field, bad in cases:
            original = copy.deepcopy(self.response)
            self.response["report"]["observation"]["identity"][field] = bad
            with self.subTest(field=field), self.assertRaises(native.Blocked): self.query()
            self.response = original
        self.response["report"]["qualification"] = "qualified"
        with self.assertRaises(native.Blocked): self.query()
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_stale_malformed_or_cached_response_rejected(self):
        for field, bad in (("hashMode", "cached"), ("nativeVitalsVersion", True),
                           ("observedAtUtc", (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),
                           ("report", {}), ("extra", "unexpected")):
            original = copy.deepcopy(self.response)
            self.response[field] = bad
            with self.subTest(field=field), self.assertRaises(native.Blocked): self.query()
            self.response = original
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_stale_sample_cannot_reuse_fresh_envelope(self):
        stale = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        self.response["report"]["observation"].update(startedAtUtc=stale, completedAtUtc=stale)
        with self.assertRaisesRegex(native.Blocked, "acquisition-stale"): self.query()

    def test_reconnected_response_instance_is_not_attributed_to_prestatus_agent(self):
        for instance in (None, "", "b" * 32, True):
            self.response["instanceId"] = instance
            with self.subTest(instance=instance), self.assertRaisesRegex(native.Blocked, "instance-changed"):
                self.query()
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_invalid_prestatus_instance_blocks_before_native_post(self):
        self.status["guest"]["instanceId"] = "not-guid-n"
        client = Mock()
        with self.assertRaisesRegex(native.Blocked, "instance-invalid"):
            self.query(client=client)
        client.request.assert_called_once_with("/api/status", method="GET")

    def test_vm_postcheck_failure_never_publishes(self):
        with self.assertRaisesRegex(native.Blocked, "target-drift"):
            self.query(verifier=Mock(side_effect=[None, native.Blocked("target-drift")]))
        self.assertEqual([], list(self.evidence.rglob("samples.json")))


class NativeHttpTests(unittest.TestCase):
    setUp = transport.HttpTests.setUp
    request = transport.HttpTests.request

    def test_endpoint_auth_and_strict_identity_body(self):
        payload = {**EXPECTED_GAME, "executableSha256": EXPECTED_GAME["executableSha256"].lower(),
                   "machineName": "RIFT-LAB-2"}
        self.assertEqual(self.request("POST", "/api/native-vitals", payload, token="wrong")[0], 401)
        self.assertEqual(self.request("POST", "/api/native-vitals", {**payload, "lease": "extra"})[0], 409)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.request("POST", "/api/native-vitals", payload)[0], 200)
        self.assertEqual(self.gateway.calls, [("native-vitals", payload)])


class NativeGatewayTests(unittest.TestCase):
    def test_gateway_uses_fast_vm_guard_and_no_arm_or_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            guard = Mock(enabled=True)
            guard.request.side_effect = lambda expected, invoke, fast: invoke()
            session = Mock(vm_identity=EXPECTED_VM)
            session.request.return_value = {"nativeVitalsVersion": 1}
            gateway = transport.host.AgentGateway(transport.config(folder), transport.host.EvidenceJournal(Path(folder)))
            gateway.vm_guard = guard
            with patch.object(gateway, "session", return_value=session):
                payload = {"machineName": "RIFT-LAB-2"}
                self.assertEqual(gateway.command("native-vitals", payload), {"nativeVitalsVersion": 1})
                guard.request.assert_called_once()
                self.assertEqual(guard.request.call_args.args[0], EXPECTED_VM)
                self.assertTrue(guard.request.call_args.kwargs["fast"])
                session.request.assert_called_once_with("native-vitals", payload, access=None)
                guard.enabled = False
                with self.assertRaisesRegex(transport.host.ControlHostError, "VM identity guard"):
                    gateway.command("native-vitals", payload)


if __name__ == "__main__": unittest.main()
