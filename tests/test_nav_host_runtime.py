"""Production composition tests with disposable queues, sockets and VM identities."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts.nav_access_queue import AccessQueue, QueueError
from scripts.nav_host_runtime import HostCoordinator
from scripts.nav_supervisor_bootstrap import CompositionError
from tests.test_control_host import host, config
from tests.test_nav_control_watchdog import VM, WatchGuest
from tests.test_nav_access_queue import Clock


class ReconcileQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.q = AccessQueue(Path(self.tmp.name) / "queue.sqlite3", create=True, clock=self.clock)
        self.q.register("vm:one", "epoch-1")
        self.clean("vm:one")

    def row(self, name="vm:one"):
        return next(r for r in self.q.status()["resources"] if r["name"] == name)

    def clean(self, name="vm:one"):
        row = self.row(name)
        return self.q.cleanup(name, row["epoch"], row["generation"], self.clock.now,
                              "fixture-release", stopped=True, released=True, in_flight=False)

    def grant(self, resources=None):
        self.q.submit("old", "worker", "A", resources or {"vm:one": "epoch-1"})
        return self.q.dispatch()

    def test_same_epoch_rebind_invalidates_active_and_queued_work(self):
        grant = self.grant()
        self.q.submit("queued", "worker-2", "A", {"vm:one": "epoch-1"})
        before = self.row()
        result = self.q.reconcile_resource("vm:one", "epoch-1", before, "fresh-owner-receipt")
        self.assertTrue(result["blocked"]); self.assertGreater(result["generation"], before["generation"])
        with self.assertRaises(QueueError): self.q.check("old", grant["token"])
        self.assertIsNone(self.q.dispatch())
        self.clean()
        rows = {r["request_id"]: r["state"] for r in self.q.status()["requests"]}
        self.assertEqual(rows, {"old": "stale", "queued": "stale"})

    def test_consumed_snapshot_cannot_be_replayed(self):
        before = self.row()
        self.q.reconcile_resource("vm:one", "epoch-2", before, "receipt")
        changed = self.row()
        with self.assertRaises(QueueError): self.q.reconcile_resource("vm:one", "epoch-2", before, "receipt")
        self.assertEqual(self.row(), changed)

    def test_two_competing_reconcilers_have_one_winner(self):
        before = self.row(); barrier = threading.Barrier(3); results = []
        def reconcile():
            other = AccessQueue(self.q.path, clock=self.clock)
            barrier.wait()
            try: other.reconcile_resource("vm:one", "epoch-2", before, "receipt"); results.append("won")
            except QueueError: results.append("refused")
        threads = [threading.Thread(target=reconcile) for _ in range(2)]
        for t in threads: t.start()
        barrier.wait()
        for t in threads: t.join(4); self.assertFalse(t.is_alive())
        self.assertCountEqual(results, ["won", "refused"])

    def test_multiresource_owner_keeps_other_resource_quarantined(self):
        self.q.register("host:desktop", "h1"); self.clean("host:desktop")
        grant = self.grant({"vm:one": "epoch-1", "host:desktop": "h1"})
        self.q.reconcile_resource("vm:one", "epoch-2", self.row(), "receipt")
        self.clean()
        other = self.row("host:desktop")
        self.assertTrue(other["blocked"]); self.assertEqual(other["holder"], "old")
        self.assertEqual(self.q.status()["requests"][0]["state"], "cleanup")
        self.clean("host:desktop")
        self.assertEqual(self.q.status()["requests"][0]["state"], "stale")
        with self.assertRaises(QueueError): self.q.check("old", grant["token"])

    def test_unrelated_resources_and_queued_work_are_not_invalidated(self):
        self.q.register("vm:two", "e2"); self.clean("vm:two")
        self.q.submit("unrelated", "worker-2", "A", {"vm:two": "e2"})
        other = self.row("vm:two")
        self.q.reconcile_resource("vm:one", "epoch-2", self.row(), "receipt")
        self.assertEqual(self.row("vm:two"), other)
        self.assertEqual(self.q.dispatch()["request_id"], "unrelated")

    def test_reconciliation_does_not_publish_or_reuse_cleanup_receipt(self):
        before = self.row()
        row = self.q.reconcile_resource("vm:one", "epoch-2", before, "receipt-not-cleanup")
        self.assertIsNone(row["cleanup_receipt"]); self.assertTrue(row["blocked"])
        self.q.submit("new", "worker", "A", {"vm:one": "epoch-2"})
        self.assertIsNone(self.q.dispatch())
        self.clean()
        self.assertEqual(self.q.dispatch()["request_id"], "new")

    def test_expiry_maintenance_survives_rejected_snapshot(self):
        grant = self.grant(); before = self.row(); self.clock.now += 5000
        with self.assertRaises(QueueError): self.q.reconcile_resource("vm:one", "epoch-2", before, "receipt")
        self.assertTrue(self.row()["blocked"])
        self.assertEqual(self.q.status()["requests"][0]["state"], "cleanup")
        with self.assertRaises(QueueError): self.q.check("old", grant["token"])

    def test_bad_snapshot_and_receipt_cannot_change_authority(self):
        before = self.row()
        for expected, receipt in (({}, "x"), ({**before, "generation": True}, "x"),
                                   ({**before, "holder": "unknown"}, "x"), (before, "")):
            with self.subTest(expected=expected), self.assertRaises(QueueError):
                self.q.reconcile_resource("vm:one", "epoch-2", expected, receipt)
        self.assertEqual(self.row(), before)


@unittest.skipUnless(os.name == "nt", "Windows console reservation required")
class HostRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        vmx = self.root / "lab.vmx"; vmx.touch()
        vmrun = self.root / "vmrun.exe"; vmrun.touch()
        self.cfg = replace(config(self.root), vmx=vmx, vmrun=vmrun, vnc_port=5905)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(self.cfg, self.journal, require_supervisor=True, exclusive_console=True)
        self.identity = {**deepcopy(VM), "vmx": self.gateway.vm_guard.module.path_key(vmx)}
        self.collect = patch.object(self.gateway.vm_guard.module, "collect_identity", side_effect=lambda _: dict(self.identity))
        self.verify = patch.object(self.gateway.vm_guard.module, "verify_identity", side_effect=lambda *_: dict(self.identity))
        self.collect.start(); self.verify.start()
        self.addCleanup(self.collect.stop); self.addCleanup(self.verify.stop)
        self.gateway.start(); self.addCleanup(self.gateway.close)
        self.q = AccessQueue(self.root / "queue.sqlite3", create=True)
        self.co = HostCoordinator(self.gateway, self.q, "vm:lab-1", self.journal)
        self.gateway.coordinator = self.co
        self.guests = []
        self.addCleanup(self.close_guests)
        self.addCleanup(lambda: self.co.stop(timeout_seconds=5))

    def close_guests(self):
        for guest in self.guests: guest.close()

    def guest(self):
        guest = WatchGuest(self.gateway); self.guests.append(guest); return guest

    def ready(self):
        end = time.monotonic() + 4
        while time.monotonic() < end:
            value = self.co.poll()
            if value["state"] in ("ready", "blocked"): return value
            time.sleep(.01)
        self.fail("coordinator did not settle")

    def grant(self, name="work"):
        epoch = self.co.status()["supervisor"]["epoch"]
        self.q.submit(name, "worker", "A", {"vm:lab-1": epoch}, ttl_ms=30000, max_ms=30000)
        grant = self.q.dispatch()
        return {"request_id": name, "token": grant["token"]}

    def reconnect(self):
        old = self.gateway.session(); old.close()
        end = time.monotonic() + 2
        while self.gateway.local_status()["connected"]:
            self.assertLess(time.monotonic(), end); time.sleep(.005)
        return self.guest()

    def test_empty_host_waits_without_creating_resource_or_watchdog(self):
        self.assertEqual(self.co.poll()["state"], "waiting")
        self.assertEqual(self.q.status()["resources"], [])
        self.assertTrue(self.co.stop()["safeToClose"])

    def test_first_session_gets_verified_supervisor_but_no_automatic_grant(self):
        guest = self.guest(); status = self.ready()
        self.assertEqual(status["state"], "ready", status)
        self.assertEqual([c["operation"] for c in guest.commands], ["status", "status", "status", "stop", "status"])
        self.assertEqual(self.q.status()["requests"], [])
        with self.assertRaises(host.ControlHostError): self.gateway.command("action", {})
        self.assertTrue(self.gateway.command("action", {}, access=self.grant())["fake"])

    def test_reconnect_same_target_revokes_old_token_and_queued_request(self):
        first = self.guest(); self.assertEqual(self.ready()["state"], "ready")
        token = self.grant(); epoch = self.co.status()["supervisor"]["epoch"]
        self.q.submit("waiting", "worker-2", "A", {"vm:lab-1": epoch})
        old_owner = self.co._owner
        second = self.reconnect(); result = self.ready()
        self.assertEqual(result["state"], "ready", result)
        self.assertEqual(result["supervisor"]["epoch"], epoch)
        self.assertFalse(old_owner.status()["threadAlive"])
        with self.assertRaises(host.ControlHostError): self.gateway.command("action", {}, access=token)
        self.assertEqual({r["request_id"]: r["state"] for r in self.q.status()["requests"]},
                         {"work": "stale", "waiting": "stale"})
        self.assertTrue(self.gateway.command("action", {}, access=self.grant("new"))["fake"])
        self.assertEqual(sum(c["operation"] == "action" for c in first.commands), 0)
        self.assertEqual(sum(c["operation"] == "action" for c in second.commands), 1)

    def test_new_game_identity_creates_new_epoch_without_replaying_work(self):
        self.guest(); self.ready(); old_epoch = self.co.status()["supervisor"]["epoch"]
        second = self.reconnect(); second.target["processStartUtcTicks"] += 100
        result = self.ready(); self.assertEqual(result["state"], "ready")
        self.assertNotEqual(result["supervisor"]["epoch"], old_epoch)
        self.assertFalse(any(c["operation"] == "action" for c in second.commands))

    def test_existing_authority_requires_explicit_startup_choice(self):
        self.q.register("vm:lab-1", "prior-epoch"); before = self.q.status()["resources"]
        guest = self.guest(); result = self.ready()
        self.assertEqual(result["state"], "blocked"); self.assertEqual(self.q.status()["resources"], before)
        self.assertEqual(guest.commands, [])
        for _ in range(5): self.co.poll()
        self.assertEqual(guest.commands, [])

    def test_explicit_existing_reconciliation_does_not_delete_history(self):
        self.q.register("vm:lab-1", "prior-epoch")
        self.q.submit("old-queued", "other", "A", {"vm:lab-1": "prior-epoch"})
        self.co = HostCoordinator(self.gateway, self.q, "vm:lab-1", self.journal, reconcile_existing=True)
        self.gateway.coordinator = self.co; self.guest()
        result = self.ready(); self.assertEqual(result["state"], "ready", result)
        self.assertEqual(self.q.status()["requests"][0]["state"], "stale")

    def test_failed_cleanup_is_blocked_and_not_retried_each_poll(self):
        guest = self.guest(); guest.stop_reply = {"stopped": False, "recoveryRequired": True}
        result = self.ready(); self.assertEqual(result["state"], "blocked")
        self.co._owner.stop(timeout_seconds=5)
        count = len(guest.commands)
        for _ in range(5): self.co.poll()
        self.assertEqual(len(guest.commands), count)
        self.assertFalse(self.co.stop()["safeToClose"])
        self.assertTrue(self.gateway.vm_guard.console_status()["held"])

    def test_shutdown_joins_supervisor_before_reporting_safe_release(self):
        self.guest(); self.ready(); self.grant()
        result = self.co.stop()
        self.assertTrue(result["safeToClose"]); self.assertTrue(result["shutdownVerified"])
        self.assertFalse(result["supervisor"]["threadAlive"])
        self.assertTrue(self.gateway.vm_guard.console_status()["held"])
        self.assertTrue(self.q.status()["resources"][0]["blocked"])
        self.assertEqual(self.co.poll()["state"], "stopped")

    def test_lost_guest_during_shutdown_never_claims_release(self):
        self.guest(); self.ready(); self.gateway.session().close()
        result = self.co.stop()
        self.assertFalse(result["safeToClose"]); self.assertFalse(result["shutdownVerified"])
        self.assertTrue(self.gateway.vm_guard.console_status()["held"])

    def test_vm_drift_before_start_blocks_guest_access(self):
        guest = self.guest(); self.identity["startTicks"] += 1
        self.assertEqual(self.ready()["state"], "blocked")
        self.assertEqual(guest.commands, [])
        self.assertEqual(self.q.status()["resources"], [])

    def test_journal_failure_prevents_reconciliation(self):
        self.guest(); self.ready(); self.reconnect()
        # Finish the previous owner before testing only the next transition journal.
        self.co._owner.stop(timeout_seconds=5)
        before = deepcopy(self.q.status()["resources"])
        with patch.object(self.journal, "append", side_effect=OSError("PRIVATE")):
            result = self.ready()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.q.status()["resources"], before)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_status_is_visible_without_mutation_and_contains_no_grant_secret(self):
        self.guest(); self.ready(); access = self.grant()
        view = self.gateway.local_status()["coordination"]
        self.assertEqual(view["state"], "ready"); self.assertNotIn(access["token"], json.dumps(view))
        self.assertNotIn(access["token"], self.journal.path.read_text())

    def test_lifecycle_from_wrong_thread_is_rejected(self):
        errors = []
        def run():
            try: self.co.poll()
            except CompositionError: errors.append(True)
        thread = threading.Thread(target=run); thread.start(); thread.join(2)
        self.assertEqual(errors, [True]); self.assertEqual(self.q.status()["resources"], [])

    def test_pending_old_supervisor_is_joined_before_new_guest_is_probed(self):
        self.guest(); self.ready(); old = self.co._owner
        entered = threading.Event(); release = threading.Event()
        shutdown = old._prepared.watchdog.shutdown
        def gated():
            entered.set(); release.wait(4); return shutdown()
        with patch.object(old._prepared.watchdog, "shutdown", side_effect=gated):
            other = self.reconnect()
            try:
                value = self.co.poll()
                self.assertTrue(entered.wait(2))
                self.assertEqual(value["state"], "draining")
                self.assertTrue(old.status()["threadAlive"])
                self.assertEqual(other.commands, [])
            finally:
                release.set()
            self.assertEqual(self.ready()["state"], "ready")
        self.assertFalse(old.status()["threadAlive"])

    def test_stop_timeout_retains_exclusion_and_finishes_on_explicit_retry(self):
        guest = self.guest(); self.ready()
        entered = threading.Event(); release = threading.Event()
        def held_stop(): entered.set(); release.wait(3)
        guest.on_stop = held_stop
        try:
            value = self.co.stop(timeout_seconds=.01)
            self.assertTrue(entered.wait(2))
            self.assertFalse(value["safeToClose"])
            self.assertTrue(value["supervisor"]["threadAlive"])
            self.assertTrue(self.gateway.vm_guard.console_status()["held"])
        finally:
            release.set()
        self.assertTrue(self.co.stop()["safeToClose"])

    def test_status_does_not_advertise_ready_after_disconnect(self):
        self.guest(); self.ready(); self.gateway.session().close()
        self.assertNotEqual(self.co.status()["state"], "ready")

    def test_uncoordinated_or_unreserved_gateway_is_rejected(self):
        with patch.object(self.gateway, "exclusive_console", False), self.assertRaises(CompositionError):
            HostCoordinator(self.gateway, self.q, "vm:lab-1", self.journal)
        with patch.object(self.gateway.vm_guard, "console_status", return_value={"held":False}), self.assertRaises(CompositionError):
            HostCoordinator(self.gateway, self.q, "vm:lab-1", self.journal)

    def test_cleanup_changed_row_between_snapshot_and_start_is_not_overwritten(self):
        self.q.register("vm:lab-1", "prior-epoch")
        self.co = HostCoordinator(self.gateway, self.q, "vm:lab-1", self.journal, reconcile_existing=True)
        guest = self.guest()
        guest.on_status = lambda: self.q.register("vm:lab-1", "changed-by-other")
        result = self.ready(); self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.q.status()["resources"][0]["epoch"], "changed-by-other")


class HostOptionTests(unittest.TestCase):
    def test_opt_in_parser_does_not_change_legacy_defaults(self):
        args = host.build_parser().parse_args(["--config", "fixture.json"])
        self.assertIsNone(args.coordination_db); self.assertFalse(args.reconcile_existing)

    def test_incomplete_or_relative_coordination_options_refused_before_config_access(self):
        for extra in (["--coordination-db", "relative"], ["--reconcile-existing"],
                      ["--coordination-db", "relative", "--coordination-resource", "vm:lab-1"]):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                host.main(["--config", "nonexistent", *extra])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
