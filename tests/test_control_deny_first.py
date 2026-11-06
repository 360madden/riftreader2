"""Readiness tests with disposable loopback guests, not a real VM or desktop."""
import copy
from pathlib import Path
import tempfile
import unittest

from tests.test_control_host import host, config
from tests.test_control_lease_access import CallerGuest, ACCESS
from tests.test_nav_control_watchdog import VM
from scripts.nav_access_queue import AccessQueue
from scripts.nav_supervisor_bootstrap import OwnedSupervisor


class DenyFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(config(self.root), self.journal, require_supervisor=True)
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = CallerGuest(self.gateway)
        self.addCleanup(self.guest.close)
        self.session = self.gateway.session()
        self.session.vm_identity = copy.deepcopy(VM)
        self.queue = AccessQueue(self.root / "queue.sqlite3", create=True)

    def test_published_session_starts_suspended(self):
        self.assertTrue(self.gateway.local_status()["connected"])
        self.assertTrue(self.session._controls_suspended)
        for operation in ("capture", "arm", "action", "recover"):
            with self.subTest(operation=operation), self.assertRaises(host.ControlHostError):
                self.gateway.command(operation, {}, access=ACCESS)
        self.assertEqual(self.guest.commands, [])
        self.assertFalse(self.gateway.command("status")["busy"])
        self.assertTrue(self.gateway.command("stop")["stopped"])

    def test_explicit_supervisor_and_lease_allow_fake_capture(self):
        owner = OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal)
        try:
            epoch = owner.start()["epoch"]
            self.queue.submit("fixture", "test-owner", "A", {"vm:lab-1": epoch})
            grant = self.queue.dispatch()
            access = {"request_id": grant["request_id"], "token": grant["token"]}
            self.assertEqual(self.gateway.capture(access=access)["imageFormat"], "bmp")
        finally:
            self.assertFalse(owner.stop()["threadAlive"])
        self.assertTrue(self.session._controls_suspended)
        self.assertFalse(any(c["operation"] in ("arm", "action") for c in self.guest.commands))

    def test_reconnected_guest_gets_no_old_policy_or_capture_privilege(self):
        owner = OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal)
        try:
            epoch = owner.start()["epoch"]
            self.queue.submit("old", "test-owner", "A", {"vm:lab-1": epoch})
            grant = self.queue.dispatch()
        finally:
            self.assertFalse(owner.stop()["threadAlive"])
        self.session.close()
        other = CallerGuest(self.gateway)
        try:
            current = self.gateway.session()
            self.assertIsNot(current, self.session)
            self.assertIsNone(current.dispatch_policy)
            self.assertTrue(current._controls_suspended)
            with self.assertRaises(host.ControlHostError):
                self.gateway.capture(access={"request_id": "old", "token": grant["token"]})
            self.assertEqual(other.commands, [])
        finally:
            other.close()

    def test_releasing_local_latch_without_policy_does_not_enable_capture(self):
        with self.session.cleanup_boundary() as permit:
            permit()
        self.assertFalse(self.session._controls_suspended)
        with self.assertRaises(host.ControlHostError):
            self.gateway.capture()
        self.assertEqual(self.guest.commands, [])

    def test_invalid_flag_or_shared_policy_is_rejected_before_listening(self):
        for value in (None, 1, "yes"):
            with self.subTest(value=value), self.assertRaises(host.ControlHostError):
                host.AgentGateway(config(self.root), self.journal, require_supervisor=value)
        with self.assertRaises(host.ControlHostError):
            host.AgentGateway(config(self.root), self.journal,
                              require_supervisor=True, dispatch_policy=object())

    def test_existing_resource_cannot_be_reset_by_new_supervisor(self):
        self.queue.register("vm:lab-1", "original-epoch")
        owner = OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal)
        try:
            with self.assertRaises(ValueError):
                owner.start()
        finally:
            self.assertFalse(owner.stop()["threadAlive"])
        self.assertTrue(self.session._controls_suspended)
        self.assertEqual(self.queue.status()["resources"][0]["epoch"], "original-epoch")


if __name__ == "__main__":
    unittest.main()
