"""Offline tests for inert prepared navigation authority; no live VM access."""
import copy
import tempfile
import unittest
from pathlib import Path

from scripts.nav_supervisor_bootstrap import prepare_authority, CompositionError
from scripts.nav_access_queue import AccessQueue
from tests.test_control_host import host, config
from tests.test_nav_control_watchdog import WatchGuest, VM


class PreparedAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(config(self.root), self.journal)
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = WatchGuest(self.gateway)
        self.addCleanup(self.guest.close)
        self.session = self.gateway.session()
        self.session.vm_identity = copy.deepcopy(VM)
        self.queue = AccessQueue(self.root / "authority.sqlite3", create=True)

    def test_prepare_registers_blocked_authority_without_starting_watchdog(self):
        prepared = prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertTrue(self.session._controls_suspended)
        self.assertIsNotNone(self.session.dispatch_policy)
        self.assertFalse(prepared.watchdog._shutdown)
        snapshot = self.queue.status()
        self.assertTrue(snapshot["resources"][0]["blocked"])
        self.assertIsNone(snapshot["resources"][0]["holder"])
        self.assertEqual([command["operation"] for command in self.guest.commands],
                         ["status", "status"])
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("arm", {})
        self.assertEqual(len(self.guest.commands), 2)

    def test_explicit_watchdog_cleanup_only_then_releases_local_latch(self):
        prepared = prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertEqual(prepared.watchdog.tick()["state"], "cleaned")
        self.assertFalse(self.session._controls_suspended)
        self.assertEqual([command["operation"] for command in self.guest.commands],
                         ["status", "status", "status", "stop", "status"])
        self.assertFalse(self.queue.status()["resources"][0]["blocked"])
        self.assertIsNotNone(self.session.dispatch_policy)

    def test_existing_resource_does_not_get_registered_twice(self):
        self.queue.register("vm:lab-1", "old-epoch")
        with self.assertRaises(CompositionError):
            prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        rows = self.queue.status()["resources"]
        self.assertEqual(rows[0]["epoch"], "old-epoch")
        self.assertTrue(rows[0]["blocked"])
        self.assertTrue(self.session._controls_suspended)
        self.assertIsNone(self.session.dispatch_policy)

    def test_changed_game_identity_denies_and_does_not_register(self):
        def change():
            self.guest.target["processStartUtcTicks"] += 1
        self.guest.on_status = change
        with self.assertRaises(ValueError):
            prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertEqual(self.queue.status()["resources"], [])
        self.assertTrue(self.session._controls_suspended)

    def test_disconnected_session_does_not_create_resource(self):
        self.session.close()
        with self.assertRaises(CompositionError):
            prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertEqual(self.queue.status()["resources"], [])

    def test_duplicate_preparation_is_rejected_without_second_cleanup(self):
        prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        with self.assertRaises(CompositionError):
            prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertEqual([c["operation"] for c in self.guest.commands],
                         ["status", "status"])


if __name__ == "__main__":
    unittest.main()
