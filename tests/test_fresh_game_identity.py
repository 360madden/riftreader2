import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import fresh_game_identity as identity
from tests import test_control_host as host_tests
from tests.test_control_host import host, FakeGuest


class FreshIdentityTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(vmx=Path("lab2.vmx"), vmrun=Path("vmrun.exe"), port=5962)
        self.host = SimpleNamespace(**vars(self.config), vnc_port=5962,
                                    expected_machine_name="RIFT-LAB-2")
        self.game = {"lab": "lab2", "processId": 12, "processStartUtcTicks": 1234,
                     "executableSha256": "ab" * 32}
        self.expected = {key: value for key, value in self.game.items() if key != "lab"}
        self.target = {**self.expected, "machineName": "RIFT-LAB-2", "isForeground": True}
        self.response = {"identityVersion": 1, "hashMode": "fresh-bytes",
                         "observedAtUtc": datetime.now(timezone.utc).isoformat(),
                         "target": self.target}
        self.vm = {"epoch": 1}
        self.status = {"host": {"connected": True, "machineName": "RIFT-LAB-2",
                                "vmIdentity": self.vm},
                       "guest": {"freshIdentityVersion": 1, "target": self.target}}

    def run_query(self, response=None, *, status=None, verify=None, client=None):
        client = client or Mock()
        client.request.side_effect = [self.status if status is None else status,
                                      self.response if response is None else response]
        verifier = verify or Mock()
        with patch.object(identity.HostConfig, "load", return_value=self.host), \
                patch.object(identity, "verify_identity", verifier):
            result = identity.query(self.config, self.vm, self.game, Path("host.json"),
                                    client_factory=lambda _: client)
        return result, client, verifier

    def test_fresh_hash_exact_target_and_both_vm_checks(self):
        self.target["executableSha256"] = self.target["executableSha256"].upper()
        result, client, verify = self.run_query()
        self.assertEqual(result, self.expected)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(client.request.call_args_list[1].args, ("/api/identity",))
        self.assertEqual(client.request.call_args_list[1].kwargs["payload"],
                         {**self.expected, "machineName": "RIFT-LAB-2"})

    def use_lab1(self):
        self.config.vmx = self.host.vmx = Path("lab1.vmx")
        self.config.port = self.host.vnc_port = 5961
        self.host.expected_machine_name = "RIFT-LAB-1"
        self.game["lab"] = "lab1"
        self.target["machineName"] = "RIFT-LAB-1"
        self.status["host"]["machineName"] = "RIFT-LAB-1"

    def test_lab1_fresh_hash_keeps_exact_payload_and_vm_bracket(self):
        self.use_lab1()
        result, client, verify = self.run_query()
        self.assertEqual(result, self.expected)
        self.assertEqual(verify.call_args_list, [
            unittest.mock.call(self.config, self.vm),
            unittest.mock.call(self.config, self.vm)])
        self.assertEqual(client.request.call_args_list[1].kwargs["payload"],
                         {**self.expected, "machineName": "RIFT-LAB-1"})

    def test_lab_machine_mismatch_and_unknown_lab_fail_before_client(self):
        for lab, machine in (("lab1", "RIFT-LAB-2"), ("lab2", "RIFT-LAB-1"),
                             ("lab3", "RIFT-LAB-3"), (None, "RIFT-LAB-2"),
                             ("LAB1", "RIFT-LAB-1")):
            self.game["lab"] = lab
            self.host.expected_machine_name = machine
            client, verify = Mock(), Mock()
            with self.subTest(lab=lab, machine=machine), \
                    self.assertRaisesRegex(identity.Blocked, "identity-host-lab-mismatch"):
                self.run_query(client=client, verify=verify)
            client.request.assert_not_called()
            verify.assert_not_called()

    def test_lab1_host_config_binding_is_not_relaxed(self):
        self.use_lab1()
        for field, bad in (("vmx", Path("lab2.vmx")), ("vmrun", Path("other.exe")),
                           ("vnc_port", 5962)):
            original = getattr(self.host, field)
            setattr(self.host, field, bad)
            client, verify = Mock(), Mock()
            with self.subTest(field=field), \
                    self.assertRaisesRegex(identity.Blocked, "identity-host-vm-mismatch"):
                self.run_query(client=client, verify=verify)
            client.request.assert_not_called()
            verify.assert_not_called()
            setattr(self.host, field, original)

    def test_lab1_retains_exact_identity_freshness_and_vm_rejection(self):
        self.use_lab1()
        self.test_wrong_or_stale_host_vm_refused_before_identity_post()
        self.test_stale_and_malformed_receipts_fail_closed()
        self.test_vm_drift_before_or_after_is_rejected()
        for field, bad in (("machineName", "RIFT-LAB-2"), ("processId", 13),
                           ("processStartUtcTicks", 1235), ("executableSha256", "cd" * 32)):
            response = copy.deepcopy(self.response)
            response["target"][field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(identity.Blocked, "game-identity-drift"):
                self.run_query(response)

    def test_supplied_status_is_freshly_called_inside_vm_bracket(self):
        events = []
        client = Mock()
        client.request.side_effect = lambda *a, **kw: (events.append("hash") or self.response)
        def supplier(host_config):
            self.assertIs(host_config, self.host)
            events.append("status")
            return self.status
        with patch.object(identity.HostConfig, "load", return_value=self.host), \
                patch.object(identity, "verify_identity", side_effect=lambda *a: events.append("vm")):
            identity.query(self.config, self.vm, self.game, Path("host.json"),
                           client_factory=lambda _: client, _status_supplier=supplier)
        self.assertEqual(events, ["vm", "status", "hash", "vm"])
        client.request.assert_called_once()
        self.assertEqual(client.request.call_args.args, ("/api/identity",))

    def test_supplier_failure_still_checks_final_vm_and_never_hashes(self):
        client, verifier = Mock(), Mock()
        with patch.object(identity.HostConfig, "load", return_value=self.host), \
                patch.object(identity, "verify_identity", verifier), \
                self.assertRaisesRegex(identity.Blocked, "status-refused"):
            identity.query(self.config, self.vm, self.game, Path("host.json"),
                           client_factory=lambda _: client,
                           _status_supplier=Mock(side_effect=identity.Blocked("status-refused")))
        self.assertEqual(verifier.call_count, 2)
        client.request.assert_not_called()

    def test_supplied_status_still_enforces_identity_predicates(self):
        for change in ("vm", "connected", "capability"):
            status = copy.deepcopy(self.status)
            if change == "vm":
                status["host"]["vmIdentity"] = {}
            elif change == "connected":
                status["host"]["connected"] = False
            else:
                status["guest"]["freshIdentityVersion"] = True
            client = Mock()
            with self.subTest(change=change), patch.object(identity.HostConfig, "load", return_value=self.host), \
                    patch.object(identity, "verify_identity"), self.assertRaises(identity.Blocked):
                identity.query(self.config, self.vm, self.game, Path("host.json"),
                               client_factory=lambda _: client, _status_supplier=lambda _: status)
            client.request.assert_not_called()

    def test_wrong_exact_identity_is_rejected(self):
        for field, bad in (("machineName", "RIFT-LAB-1"), ("processId", 13),
                           ("processStartUtcTicks", 1235), ("executableSha256", "cd" * 32)):
            response = copy.deepcopy(self.response)
            response["target"][field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(identity.Blocked, "game-identity-drift"):
                self.run_query(response)

    def test_status_cached_identity_is_never_accepted(self):
        # Status advertises the exact expected identity but the fresh read disagrees.
        self.response["target"] = {**self.target, "processId": 14}
        with self.assertRaisesRegex(identity.Blocked, "game-identity-drift"):
            self.run_query()

    def test_wrong_or_stale_host_vm_refused_before_identity_post(self):
        for vm in (None, {}, {"epoch": 2}, {"epoch": 1, "unexpected": "value"}):
            status = copy.deepcopy(self.status)
            status["host"]["vmIdentity"] = vm
            client = Mock()
            verifier = Mock()
            with self.subTest(vm=vm), self.assertRaisesRegex(identity.Blocked, "identity-host-vm-mismatch"):
                self.run_query(status=status, verify=verifier, client=client)
            client.request.assert_called_once_with("/api/status", method="GET")
            self.assertEqual(verifier.call_count, 2)

    def test_unsupported_capability_sends_no_identity_or_input(self):
        for version in (None, 0, True, "1"):
            status = copy.deepcopy(self.status)
            status["guest"]["freshIdentityVersion"] = version
            verifier = Mock()
            with self.subTest(version=version), self.assertRaisesRegex(identity.Blocked, "unsupported"):
                self.run_query(status=status, verify=verifier)
            self.assertEqual(verifier.call_count, 2)

    def test_stale_and_malformed_receipts_fail_closed(self):
        cases = [{**self.response, "hashMode": "cached"},
                 {**self.response, "identityVersion": True},
                 {**self.response, "nonce": "unexpected"},
                 {**self.response, "target": {}},
                 {**self.response, "observedAtUtc": "invalid"},
                 {**self.response, "observedAtUtc": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(identity.Blocked):
                self.run_query(response)

    def test_vm_drift_before_or_after_is_rejected(self):
        for sequence in ([identity.Blocked("target-drift")], [None, identity.Blocked("target-drift")]):
            with self.subTest(sequence=sequence), self.assertRaisesRegex(identity.Blocked, "target-drift"):
                self.run_query(verify=Mock(side_effect=sequence))

    def test_strict_host_payload_bounds(self):
        valid = {**self.expected, "machineName": "RIFT-LAB-2"}
        self.assertEqual(host.validate_identity_payload(valid), valid)
        for bad in ({**valid, "processId": True}, {**valid, "processStartUtcTicks": 0},
                    {**valid, "executableSha256": "bad"}, {**valid, "nonce": "extra"}):
            with self.subTest(bad=bad), self.assertRaises(host.ControlHostError):
                host.validate_identity_payload(bad)


class IdentityCliTests(unittest.TestCase):
    def test_each_machine_derives_its_canonical_lab(self):
        for lab, machine in (("lab1", "RIFT-LAB-1"), ("lab2", "RIFT-LAB-2")):
            config = SimpleNamespace(vmx=Path(lab + ".vmx"), vmrun=Path("vmrun.exe"),
                                     vnc_port=5961, expected_machine_name=machine,
                                     output_directory=Path("output"))
            with self.subTest(lab=lab), \
                    patch.object(identity.HostConfig, "load", return_value=config), \
                    patch.object(identity, "validate_config", return_value="config") as validate, \
                    patch.object(identity, "collect_identity", return_value={"epoch": 1}), \
                    patch.object(identity, "query", return_value={}) as query, \
                    patch("builtins.print"):
                result = identity.main([
                    "--host-config", "host.json", "--expected-machine", machine,
                    "--expected-game-pid", "12", "--expected-game-start-ticks", "1234",
                    "--expected-game-sha256", "AB" * 32])
            self.assertEqual(result, 0)
            validate.assert_called_once_with(config.vmx, config.vnc_port, config.vmrun,
                                             config.output_directory, require_files=True)
            self.assertEqual(query.call_args.args, ("config", {"epoch": 1}, {
                "lab": lab, "processId": 12, "processStartUtcTicks": 1234,
                "executableSha256": "ab" * 32}, Path("host.json")))

    def test_machine_config_mismatch_fails_before_vm_collection(self):
        config = SimpleNamespace(expected_machine_name="RIFT-LAB-2")
        with patch.object(identity.HostConfig, "load", return_value=config), \
                patch.object(identity, "collect_identity") as collect, \
                patch.object(identity, "query") as query, patch("builtins.print"):
            result = identity.main([
                "--host-config", "host.json", "--expected-machine", "RIFT-LAB-1",
                "--expected-game-pid", "12", "--expected-game-start-ticks", "1234",
                "--expected-game-sha256", "ab" * 32])
        self.assertEqual(result, 2)
        collect.assert_not_called()
        query.assert_not_called()


class IdentityGatewayTests(unittest.TestCase):
    setUp = host_tests.GatewayTests.setUp
    wait_connected = host_tests.GatewayTests.wait_connected

    def test_identity_is_readonly_correlated_and_does_not_change_control_generation(self):
        import threading
        guest = FakeGuest(self.gateway.port)
        self.addCleanup(guest.close)
        guest.receive()
        self.wait_connected()
        session = self.gateway.session()
        session.dispatch_policy = Mock()
        session.dispatch_policy.guard.side_effect = AssertionError("read-only query requested input admission")
        before = session._control_generation
        payload = {"machineName": "RIFT-LAB-1", "processId": 12,
                   "processStartUtcTicks": 1234, "executableSha256": "ab" * 32}
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.gateway.command("identity", payload)))
        thread.start()
        command = guest.receive()
        self.assertEqual(command["operation"], "identity")
        self.assertEqual(command["payload"], payload)
        self.assertEqual(len(command["id"]), 32)
        guest.respond(command, {"identityVersion": 1})
        thread.join(2)
        self.assertEqual(result, {"identityVersion": 1})
        self.assertEqual(session._control_generation, before)
        session.dispatch_policy.guard.assert_not_called()

    def test_identity_refuses_lease_and_wrong_machine_before_send(self):
        import socket
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            local, remote = socket.socketpair()
            self.addCleanup(remote.close)
            session = host.AgentSession(local, "test", {"instanceId": "test", "machineName": "RIFT-LAB-2"},
                                        host.EvidenceJournal(Path(folder)), lambda _: None,
                                        require_supervisor=True)
            self.addCleanup(session.close)
            payload = {"machineName": "RIFT-LAB-2", "processId": 12,
                       "processStartUtcTicks": 1234, "executableSha256": "ab" * 32}
            with self.assertRaisesRegex(host.ControlHostError, "do not accept"):
                session.request("identity", payload, access={"request_id": "test", "token": "test"})
            with self.assertRaisesRegex(host.ControlHostError, "machine"):
                session.request("identity", {**payload, "machineName": "RIFT-LAB-1"})
            self.assertEqual(session.summary()["lastIssuedSequence"], 0)


class IdentityHttpTests(unittest.TestCase):
    setUp = host_tests.HttpTests.setUp
    request = host_tests.HttpTests.request

    def test_identity_requires_authentication_and_exact_bounded_payload(self):
        payload = {"machineName": "RIFT-LAB-2", "processId": 12,
                   "processStartUtcTicks": 1234, "executableSha256": "ab" * 32}
        self.assertEqual(self.request("POST", "/api/identity", payload, token="wrong")[0], 401)
        self.assertEqual(self.request("POST", "/api/identity", payload, origin="http://wrong")[0], 403)
        self.assertEqual(self.request("POST", "/api/identity", {**payload, "armToken": "extra"})[0], 409)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.request("POST", "/api/identity", payload)[0], 200)
        self.assertEqual(self.gateway.calls, [("identity", payload)])


if __name__ == "__main__":
    unittest.main()
