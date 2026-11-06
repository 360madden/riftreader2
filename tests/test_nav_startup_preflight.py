"""Offline checks for startup preflight; no live guest or queue creation."""
import copy
import tempfile
import unittest
from pathlib import Path
from scripts.nav_startup_preflight import qualify_startup, StartupPreflightError
from tests.test_nav_control_watchdog import VM, TARGET, WatchGuest
from tests.test_control_host import host, config


class FakeSession:
    def __init__(self):
        self.closed = False
        self.dispatch_policy = None
        self.identity = {"connected": True, "instanceId": "guest-one",
                         "machineName": TARGET["machineName"], "vmIdentity": copy.deepcopy(VM)}
        self.statuses = [self.status(), self.status()]
        self.calls = []
        self.sequence = 0

    def status(self):
        return {"instanceId": "guest-one", "target": copy.deepcopy(TARGET),
                "armed": False, "busy": False, "recoveryRequired": False,
                "desktopInputsDown": []}

    def summary(self):
        result = copy.deepcopy(self.identity)
        result["lastIssuedSequence"] = self.sequence
        return result

    def request(self, operation, payload):
        self.calls.append((operation, payload))
        self.sequence += 1
        return copy.deepcopy(self.statuses[len(self.calls)-1])


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()

    def test_two_matching_reads_qualify_without_activation(self):
        result = qualify_startup(self.session, "vm:lab-1")
        self.assertEqual(result.resource, "vm:lab-1")
        self.assertEqual(len(result.fingerprint), 64)
        self.assertTrue(result.epoch.startswith("nav-"))
        self.assertEqual(self.session.calls, [("status", {}), ("status", {})])
        self.assertIsNone(self.session.dispatch_policy)

    def test_changed_guest_target_rejected(self):
        self.session.statuses[1]["target"]["processStartUtcTicks"] += 1
        with self.assertRaises(StartupPreflightError):
            qualify_startup(self.session, "vm:lab-1")

    def test_vm_identity_change_rejected(self):
        original = self.session.summary
        counter = [0]
        def evolving():
            counter[0] += 1
            result = original()
            if counter[0] >= 2:
                result["vmIdentity"]["pid"] += 1
            return result
        self.session.summary = evolving
        with self.assertRaises(StartupPreflightError):
            qualify_startup(self.session, "vm:lab-1")

    def test_recovery_or_input_not_released_rejected(self):
        for field, value in (("armed", True), ("busy", True),
                             ("recoveryRequired", True), ("desktopInputsDown", ["w"])):
            with self.subTest(field=field):
                self.session.calls = []
                self.session.statuses = [self.session.status(), self.session.status()]
                self.session.statuses[1][field] = value
                with self.assertRaises(StartupPreflightError):
                    qualify_startup(self.session, "vm:lab-1")

    def test_existing_policy_refused(self):
        self.session.dispatch_policy = object()
        with self.assertRaises(StartupPreflightError):
            qualify_startup(self.session, "vm:lab-1")
        self.assertEqual(self.session.calls, [])

    def test_disconnect_refused(self):
        self.session.closed = True
        with self.assertRaises(StartupPreflightError):
            qualify_startup(self.session, "vm:lab-1")

    def test_absent_status_is_not_promoted(self):
        self.session.statuses[1] = {"error": "connection lost"}
        with self.assertRaises(StartupPreflightError):
            qualify_startup(self.session, "vm:lab-1")

    def test_transport_failure_rejected_without_leaking_message(self):
        def fail(operation, payload):
            raise RuntimeError("PRIVATE_HOST_TOKEN")
        self.session.request = fail
        with self.assertRaises(StartupPreflightError) as outcome:
            qualify_startup(self.session, "vm:lab-1")
        self.assertNotIn("PRIVATE_HOST_TOKEN", str(outcome.exception))

    def test_invalid_resource_name_rejected_before_requests(self):
        for value in ("vm:../bad space", "vm:", "VM:lab-1", "vm:bad?", None):
            with self.subTest(value=value), self.assertRaises(StartupPreflightError):
                qualify_startup(self.session, value)
        self.assertEqual(self.session.calls, [])

    def test_foreground_not_assumed_from_idle_status(self):
        self.session.statuses[0]["target"]["isForeground"] = False
        self.session.statuses[1]["target"]["isForeground"] = False
        # Safe qualification of identity, not permission for foreground actions.
        result = qualify_startup(self.session, "vm:lab-1")
        self.assertNotIn("isForeground", result.identity["target"])


class LiveProtocolFixtureTests(unittest.TestCase):
    def test_real_session_framing_returns_stable_startup_binding_without_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gateway = host.AgentGateway(config(root), host.EvidenceJournal(root))
            gateway.start()
            try:
                guest = WatchGuest(gateway)
                try:
                    session = gateway.session()
                    session.vm_identity = copy.deepcopy(VM)
                    qualified = qualify_startup(session, "vm:lab-1")
                    self.assertEqual(qualified.identity["instanceId"], "guest-one")
                    self.assertEqual([item["operation"] for item in guest.commands], ["status", "status"])
                    self.assertEqual(session.summary()["lastIssuedSequence"], 2)
                    self.assertIsNone(session.dispatch_policy)
                finally:
                    guest.close()
            finally:
                gateway.close()


if __name__ == "__main__":
    unittest.main()
