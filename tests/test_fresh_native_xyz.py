"""Offline host admission and persistent-agent XYZ response checks."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import fresh_native_xyz as native
from tests import test_control_host as transport
from tests.test_sample_current_native_vitals import EXPECTED_VM, EXPECTED_GAME


class NativeXyzClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name)
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962, expected_machine_name="RIFT-LAB-2")
        self.status = {
            "host": {"connected": True, "machineName": "RIFT-LAB-2",
                     "vmIdentity": dict(EXPECTED_VM), "instanceId": "a" * 32},
            "guest": {"nativeXyzVersion": 1, "nativeReadLeaseVersion": 1, "instanceId": "a" * 32}}
        now = datetime.now(timezone.utc).isoformat()
        self.report = {
            "schemaVersion": 1, "contractVersion": "native-current-position-candidate-sample/1",
            "qualification": native.QUALIFICATION,
            "identity": {**EXPECTED_GAME, "executablePath": r"C:\RIFT\rift_x64.exe",
                         "moduleBaseAddress": 0x140000000, "moduleSize": 0x4000000},
            "startedAtUtc": now, "completedAtUtc": now, "unitKey": "18446744073709551615",
            "unitIdCandidate": "uFFFFFFFFFFFFFFFF",
            "ownerIdentityStatus": "player-component-chain-anchored", "x": 1.5, "y": -2, "z": 3}
        self.response = {"nativeXyzVersion": 1, "instanceId": "a" * 32,
                         "hashMode": "fresh-bytes", "observedAtUtc": now, "report": self.report}

    def query(self, *, client=None, verifier=None, **kwargs):
        client = client or Mock()
        client.request.side_effect = [self.status, self.response]
        verifier = verifier or Mock()
        with patch.object(native.HostConfig, "load", return_value=self.host), \
                patch.object(native, "verify_identity", verifier), \
                patch.object(native, "EVIDENCE", self.evidence):
            result = native.query(self.config, EXPECTED_VM, {"lab": "lab2", **EXPECTED_GAME},
                                  Path("host.json"), client_factory=lambda _: client, **kwargs)
        return result, client, verifier

    def assert_unpublished(self):
        self.assertEqual([], list(self.evidence.rglob("samples.json")))

    def test_exact_pinned_response_published_and_no_zone_inferred(self):
        result, client, verifier = self.query()
        self.assertEqual(2, verifier.call_count)
        self.assertEqual("candidate-only", result["status"])
        self.assertEqual("persistent-control-agent", result["transport"])
        self.assertEqual("unavailable-in-source-report", result["metrics"]["zoneStatus"])
        self.assertEqual(self.report["unitKey"], result["metrics"]["unitKey"])
        source = Path(result["sourceReport"])
        self.assertEqual(self.report, json.loads(source.read_bytes()))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest().upper(), result["sourceReportSha256"])
        self.assertEqual("/api/native-xyz", client.request.call_args_list[1].args[0])
        self.assertEqual({"machineName": "RIFT-LAB-2", **EXPECTED_GAME,
                          "executableSha256": EXPECTED_GAME["executableSha256"].lower()},
                         client.request.call_args_list[1].kwargs["payload"])

    def test_status_target_capability_and_instance_mismatch_send_no_xyz(self):
        for section, key, value in (
                ("host", "connected", False), ("host", "vmIdentity", {}),
                ("host", "machineName", "RIFT-LAB-1"), ("host", "instanceId", "b" * 32),
                ("guest", "nativeXyzVersion", True), ("guest", "instanceId", "invalid")):
            original = copy.deepcopy(self.status)
            self.status[section][key] = value
            client = Mock()
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                self.query(client=client)
            client.request.assert_called_once_with("/api/status", method="GET")
            self.status = original
        self.assert_unpublished()

    def test_missing_wrong_or_changed_lease_capability_sends_no_xyz(self):
        for value in (None, True, False, 0, 2, "1", 1.0):
            original = copy.deepcopy(self.status)
            if value is None:
                self.status["guest"].pop("nativeReadLeaseVersion")
            else:
                self.status["guest"]["nativeReadLeaseVersion"] = value
            client = Mock()
            with self.subTest(value=value), self.assertRaisesRegex(native.Blocked, "lease-unsupported"):
                self.query(client=client)
            client.request.assert_called_once_with("/api/status", method="GET")
            self.status = original
        self.assert_unpublished()

    def test_response_cache_instance_version_or_extra_fields_rejected(self):
        for key, value in (("hashMode", "cached"), ("instanceId", "b" * 32),
                           ("nativeXyzVersion", True), ("extra", 1), ("report", {})):
            original = copy.deepcopy(self.response)
            self.response[key] = value
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                self.query()
            self.response = original
        self.assert_unpublished()

    def test_report_identity_and_qualification_mismatch_rejected(self):
        for key, value in (("processId", 0), ("processStartUtcTicks", EXPECTED_GAME["processStartUtcTicks"] + 1),
                           ("executableSha256", "0" * 64), ("moduleBaseAddress", True), ("moduleSize", 4)):
            original = copy.deepcopy(self.response)
            self.response["report"]["identity"][key] = value
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                self.query()
            self.response = original
        self.response["report"]["qualification"] = "qualified"
        with self.assertRaises(native.Blocked): self.query()
        self.assert_unpublished()

    def test_noncanonical_unit_keys_and_wrong_ids_rejected(self):
        for key in ("0", "01", "+1", "-1", "18446744073709551616", 123, True):
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                native.validate_report({**self.report, "unitKey": key},
                    pid=EXPECTED_GAME["processId"], ticks=EXPECTED_GAME["processStartUtcTicks"])
        with self.assertRaises(native.Blocked):
            native.validate_report({**self.report, "unitIdCandidate": "u0000000000000001"},
                pid=EXPECTED_GAME["processId"], ticks=EXPECTED_GAME["processStartUtcTicks"])

    def test_nonfinite_bool_coordinates_and_wrong_owner_rejected(self):
        for key, value in (("x", float("nan")), ("y", float("inf")), ("z", True),
                           ("ownerIdentityStatus", "unanchored"), ("schemaVersion", True)):
            original = copy.deepcopy(self.response)
            self.response["report"][key] = value
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                self.query()
            self.response = original
        self.assert_unpublished()

    def test_stale_sample_and_one_tick_response_reversal_rejected(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.response["report"].update(startedAtUtc=stale, completedAtUtc=stale)
        with self.assertRaisesRegex(native.Blocked, "acquisition-stale"): self.query()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.report.update(startedAtUtc="2026-01-01T00:00:00.0000000Z",
                           completedAtUtc="2026-01-01T00:00:00.0000009Z")
        with self.assertRaisesRegex(native.Blocked, "response-before-sample"):
            native.validate_response_time(self.report, "2026-01-01T00:00:00.0000008Z", base, base)
        self.assert_unpublished()

    def test_slow_response_is_unavailable_without_retry_or_publication(self):
        client = Mock()
        with patch.object(native.time, "perf_counter", side_effect=[0, 0, 3]):
            with self.assertRaisesRegex(native.Blocked, "response-too-slow"):
                self.query(client=client)
        self.assertEqual(2, client.request.call_count)
        self.assert_unpublished()

    def test_zone_requirement_fails_before_network(self):
        client = Mock()
        with self.assertRaisesRegex(native.Blocked, "zone-unavailable"):
            self.query(client=client, expected_zone="z0000000000000001")
        client.request.assert_not_called()
        self.assert_unpublished()

    def test_final_vm_drift_or_oversized_report_never_publishes(self):
        with self.assertRaisesRegex(native.Blocked, "drift"):
            self.query(verifier=Mock(side_effect=[None, native.Blocked("drift")]))
        self.report["identity"]["executablePath"] = "x" * (native.REPORT_MAX_BYTES + 1)
        with self.assertRaisesRegex(native.Blocked, "report-too-large"): self.query()
        self.assert_unpublished()


class NativeXyzHttpTests(unittest.TestCase):
    setUp = transport.HttpTests.setUp
    request = transport.HttpTests.request

    def test_route_auth_and_strict_no_lease_identity(self):
        payload = {**EXPECTED_GAME, "executableSha256": EXPECTED_GAME["executableSha256"].lower(),
                   "machineName": "RIFT-LAB-2"}
        for operation in ("native-xyz", "native-orientation", "native-actor-pose"):
            with self.subTest(operation=operation):
                route = "/api/" + operation
                self.assertEqual(401, self.request("POST", route, payload, token="wrong")[0])
                self.assertEqual(409, self.request("POST", route, {**payload, "lease": "extra"})[0])
                before = len(self.gateway.calls)
                self.assertEqual(200, self.request("POST", route, payload)[0])
                self.assertEqual(before + 1, len(self.gateway.calls))
                self.assertEqual((operation, payload), self.gateway.calls[-1])


class NativeXyzGatewayTests(unittest.TestCase):
    def test_fast_vm_guard_is_required_and_original_endpoint_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            guard = Mock(enabled=True)
            guard.request.side_effect = lambda expected, invoke, fast: invoke()
            session = Mock(vm_identity=EXPECTED_VM, closed=False,
                           hello={"instanceId": "a" * 32})
            session.request.side_effect = [{"nativeReadLeaseVersion": 1, "instanceId": "a" * 32},
                                           {"nativeXyzVersion": 1}]
            gateway = transport.host.AgentGateway(transport.config(folder), transport.host.EvidenceJournal(Path(folder)))
            gateway.vm_guard = guard
            with patch.object(gateway, "session", return_value=session):
                gateway.command("native-xyz", {})
                self.assertTrue(guard.request.call_args.kwargs["fast"])
                self.assertEqual([(("status", {}), {"access": None}),
                                  (("native-xyz", {}), {"access": None})],
                                 [(c.args, c.kwargs) for c in session.request.call_args_list])
                guard.enabled = False
                with self.assertRaisesRegex(transport.host.ControlHostError, "VM identity guard"):
                    gateway.command("native-xyz", {})
                with self.assertRaisesRegex(transport.host.ControlHostError, "VM identity guard"):
                    gateway.command("native-vitals", {})

    def test_native_lease_capability_is_checked_on_same_session_for_both_operations(self):
        for operation in ("native-xyz", "native-vitals", "native-orientation", "native-actor-pose"):
            for value in (None, True, False, 0, 2, "1", 1.0):
                with self.subTest(operation=operation, value=value), tempfile.TemporaryDirectory() as folder:
                    session = Mock(vm_identity=EXPECTED_VM, closed=False,
                                   hello={"instanceId": "a" * 32})
                    status = {"instanceId": "a" * 32}
                    if value is not None:
                        status["nativeReadLeaseVersion"] = value
                    session.request.return_value = status
                    gateway = transport.host.AgentGateway(transport.config(folder),
                        transport.host.EvidenceJournal(Path(folder)))
                    gateway.vm_guard = Mock(enabled=True)
                    gateway.vm_guard.request.side_effect = lambda expected, invoke, fast: invoke()
                    with patch.object(gateway, "session", return_value=session):
                        with self.assertRaisesRegex(transport.host.ControlHostError, "nativeReadLeaseVersion"):
                            gateway.command(operation, {})
                    session.request.assert_called_once_with("status", {}, access=None)

    def test_native_instance_or_session_change_blocks_without_reconnect(self):
        for operation in ("native-xyz", "native-vitals", "native-orientation", "native-actor-pose"):
            for kind in ("wrong-instance", "missing-instance", "replaced", "closed", "hello-changed"):
                with self.subTest(operation=operation, kind=kind), tempfile.TemporaryDirectory() as folder:
                    session = Mock(vm_identity=EXPECTED_VM, closed=False,
                                   hello={"instanceId": "a" * 32})
                    status = {"nativeReadLeaseVersion": 1, "instanceId": "a" * 32}
                    if kind == "wrong-instance":
                        status["instanceId"] = "b" * 32
                    if kind == "missing-instance":
                        status.pop("instanceId")
                    def status_read(*args, **kwargs):
                        if kind == "closed":
                            session.closed = True
                        if kind == "hello-changed":
                            session.hello["instanceId"] = "b" * 32
                        return status
                    session.request.side_effect = status_read
                    gateway = transport.host.AgentGateway(transport.config(folder),
                        transport.host.EvidenceJournal(Path(folder)))
                    gateway.vm_guard = Mock(enabled=True)
                    gateway.vm_guard.request.side_effect = lambda expected, invoke, fast: invoke()
                    successor = Mock()
                    provider = Mock(side_effect=[session, successor]) if kind == "replaced" else Mock(return_value=session)
                    with patch.object(gateway, "session", provider):
                        with self.assertRaises(transport.host.ControlHostError):
                            gateway.command(operation, {})
                    session.request.assert_called_once_with("status", {}, access=None)
                    successor.request.assert_not_called()

    def test_changed_capability_is_not_cached_and_non_native_call_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Mock(vm_identity=EXPECTED_VM, closed=False,
                           hello={"instanceId": "a" * 32})
            session.request.side_effect = [
                {"nativeReadLeaseVersion": 1, "instanceId": "a" * 32},
                {"sample": "candidate"},
                {"nativeReadLeaseVersion": 2, "instanceId": "a" * 32},
                {"ordinary": "status"}]
            gateway = transport.host.AgentGateway(transport.config(folder),
                transport.host.EvidenceJournal(Path(folder)))
            gateway.vm_guard = Mock(enabled=True)
            gateway.vm_guard.request.side_effect = lambda expected, invoke, fast: invoke()
            with patch.object(gateway, "session", return_value=session):
                self.assertEqual({"sample": "candidate"}, gateway.command("native-xyz", {}))
                with self.assertRaisesRegex(transport.host.ControlHostError, "nativeReadLeaseVersion"):
                    gateway.command("native-vitals", {})
                self.assertEqual({"ordinary": "status"}, gateway.command("status", {}))
            self.assertEqual(["status", "native-xyz", "status", "status"],
                             [c.args[0] for c in session.request.call_args_list])

    def test_read_only_admission_rejects_lease_without_control_authority(self):
        local, remote = socket.socketpair()
        self.addCleanup(remote.close)
        with tempfile.TemporaryDirectory() as folder:
            session = transport.host.AgentSession(local, "test",
                {"instanceId": "a" * 32, "machineName": "RIFT-LAB-2"},
                transport.host.EvidenceJournal(Path(folder)), lambda _: None)
            self.addCleanup(session.close)
            for operation in ("native-xyz", "native-actor-pose"):
                with self.subTest(operation=operation):
                    with session._admission(operation, None) as admit:
                        self.assertIsNone(admit)
                    with self.assertRaisesRegex(transport.host.ControlHostError, "do not accept a control lease"):
                        with session._admission(operation, {"request_id": "r", "token": "a" * 64}): pass
            self.assertEqual(0, session.summary()["lastIssuedSequence"])


if __name__ == "__main__": unittest.main()
