"""Offline watchdog acceptance. No VM, real input or production queue is used."""
from copy import deepcopy
from contextlib import closing
import sqlite3
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tests.test_control_host import host, config, FakeGuest
from tests.test_nav_access_queue import nav, Clock
from scripts.nav_control_watchdog import LeaseWatchdog, WatchdogError, bind_identity, resource_epoch

VM = {"image": "C:/fake/vmware-vmx.exe", "vmx": "C:/fake/lab.vmx", "pid": 55,
      "listenerPid": 55, "startTicks": 1234, "port": 5905, "logEpoch": "2026-10-21T00:00:00Z"}
TARGET = {"machineName": "RIFT-LAB-1", "executablePath": "C:/fake/rift_x64.exe",
          "executableSha256": "a" * 64, "windowHandle": "0x123", "processId": 44,
          "processStartUtcTicks": 123456, "clientX": 0, "clientY": 23,
          "clientWidth": 800, "clientHeight": 600, "isForeground": True}


class WatchGuest:
    def __init__(self, gateway):
        self.guest = FakeGuest(gateway.port)
        assert self.guest.receive() == {"type": "welcome"}
        self.guest.socket.settimeout(None)
        self.commands = []
        self.errors = []
        self.target = deepcopy(TARGET)
        self.instance = "guest-one"
        self.overrides = {}
        self.stop_reply = {"stopped": True, "recoveryRequired": False}
        self.pending = []
        self.hold = False
        self.ack_actions = True
        self.on_stop = lambda: None
        self.on_status = lambda: None
        self.stopped = threading.Event()
        self.action_seen = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        end = time.monotonic() + 2
        while not gateway.local_status()["connected"]:
            if time.monotonic() > end:
                raise AssertionError("fake guest did not connect")
            time.sleep(.005)

    def _read(self):
        try:
            while True:
                command = self.guest.receive()
                self.commands.append(command)
                operation = command["operation"]
                if operation == "action":
                    self.action_seen.set()
                    if self.hold:
                        self.pending.append(command)
                        continue
                    result = {"fake": True}
                elif operation == "stop":
                    self.stopped.set()
                    self.on_stop()
                    self.guest.respond(command, deepcopy(self.stop_reply))
                    if self.ack_actions:
                        for previous in self.pending:
                            self.guest.respond(previous, {"cancelled": True})
                        self.pending.clear()
                    continue
                elif operation == "status":
                    self.on_status()
                    result = {"instanceId": self.instance, "target": deepcopy(self.target),
                              "armed": False, "busy": bool(self.pending),
                              "recoveryRequired": False, "desktopInputsDown": [], **self.overrides}
                else:
                    result = {"fake": True}
                self.guest.respond(command, result)
        except (EOFError, OSError):
            pass
        except BaseException as error:
            self.errors.append(error)

    def close(self):
        try:
            self.guest.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.thread.join(2)
        self.guest.close()
        assert not self.thread.is_alive(), "fake reader leaked"
        assert not self.errors, self.errors


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.queue = nav.AccessQueue(self.root / "authority.sqlite3", create=True, clock=self.clock)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(config(self.root), self.journal)
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = WatchGuest(self.gateway)
        self.addCleanup(self.guest.close)
        self.session = self.gateway.session()
        self.session.vm_identity = deepcopy(VM)
        self.identity = bind_identity(self.session.summary(), {"instanceId": "guest-one", "target": TARGET})
        self.epoch = resource_epoch(self.identity)
        self.resource = "vm:lab-1"
        self.queue.register(self.resource, self.epoch)
        self.session.dispatch_policy = nav.QueueDispatchPolicy(self.queue, {self.resource: self.epoch})
        self.watch = LeaseWatchdog(self.queue, self.session, self.resource, self.identity, self.journal)

    def row(self):
        return next(r for r in self.queue.status()["resources"] if r["name"] == self.resource)

    def clean(self):
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        self.guest.commands.clear()
        self.guest.stopped.clear()

    def grant(self, name="a", resources=None):
        self.queue.submit(name, "worker-" + name, "A", resources or {self.resource: self.epoch})
        grant = self.queue.dispatch()
        self.assertEqual(grant["request_id"], name)
        return {"request_id": name, "token": grant["token"]}

    def action(self, access):
        result = {}
        def perform():
            try:
                result["value"] = self.gateway.command("action", {}, access=access)
            except Exception as error:
                result["error"] = error
        thread = threading.Thread(target=perform)
        thread.start()
        return thread, result

    def assert_blocked(self, result):
        self.assertEqual(result["state"], "blocked", result)
        self.assertFalse(result["cleanupPublished"])
        self.assertTrue(self.row()["blocked"])
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {})

    def test_construction_has_no_commands_or_automatic_thread(self):
        self.assertEqual(self.guest.commands, [])
        self.assertTrue(self.row()["blocked"])

    def test_initial_cleanup_sends_stop_then_fresh_status_and_saves_receipt(self):
        result = self.watch.tick()
        self.assertEqual(result["state"], "cleaned")
        self.assertEqual([c["operation"] for c in self.guest.commands], ["status", "stop", "status"])
        self.assertEqual(self.row()["cleanup_receipt"], result["receipt"])
        records = [json.loads(line) for line in self.journal.path.read_text().splitlines()]
        receipt = next(r["value"] for r in records if r["evidenceKind"] == "nav-control-cleanup/1")
        self.assertEqual(receipt["receipt"], result["receipt"])
        self.assertEqual(receipt["identity"], self.identity)

    def test_unexpired_lease_tick_sends_nothing(self):
        self.clean(); self.grant()
        self.assertEqual(self.watch.tick()["state"], "idle")
        self.assertEqual(self.guest.commands, [])

    def test_expiry_stops_original_action_drains_it_and_never_replays(self):
        self.clean(); access = self.grant()
        self.queue.submit("b", "worker-b", "B", {self.resource: self.epoch})
        self.guest.hold = True
        action, result = self.action(access)
        self.assertTrue(self.guest.action_seen.wait(2))
        self.clock.now += 5000
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        action.join(2)
        self.assertFalse(action.is_alive()); self.assertTrue(result["value"]["cancelled"])
        self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), 1)
        self.assertEqual(self.queue.status()["requests"][0]["state"], "expired")
        self.assertEqual(self.queue.dispatch()["request_id"], "b")
        self.assertNotIn(access["token"], self.journal.path.read_text())

    def test_finished_experiment_keeps_success_after_verified_cleanup(self):
        self.clean(); access = self.grant()
        self.queue.finish("a", access["token"], "succeeded", ["synthetic-trial"])
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        self.assertEqual(self.queue.status()["requests"][0]["state"], "succeeded")

    def test_cancelled_experiment_is_not_reported_as_success(self):
        self.clean(); self.grant(); self.queue.cancel("a", "worker-a")
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        self.assertEqual(self.queue.status()["requests"][0]["state"], "cancelled")

    def test_negative_stop_latches_and_needs_explicit_retry(self):
        self.guest.stop_reply["stopped"] = False
        self.assert_blocked(self.watch.tick())
        count = len(self.guest.commands)
        self.guest.stop_reply["stopped"] = True
        self.assertEqual(self.watch.tick()["state"], "blocked")
        self.assertEqual(len(self.guest.commands), count)
        self.assertEqual(self.watch.tick(retry=True)["state"], "cleaned")

    def test_stop_recovery_requirement_blocks_without_automatic_recover(self):
        self.guest.stop_reply["recoveryRequired"] = True
        self.assert_blocked(self.watch.tick())
        self.assertNotIn("recover", [c["operation"] for c in self.guest.commands])

    def test_identity_changed_before_stop_does_not_send_to_new_target(self):
        self.guest.target["processStartUtcTicks"] += 1
        self.assert_blocked(self.watch.tick())
        self.assertNotIn("stop", [c["operation"] for c in self.guest.commands])

    def test_identity_changed_after_stop_cannot_publish_cleanup(self):
        self.guest.on_stop = lambda: self.guest.target.update(processId=999)
        self.assert_blocked(self.watch.tick())
        self.assertIsNone(self.row()["cleanup_receipt"])

    def test_reconnected_guest_identity_is_not_silently_rebound(self):
        self.session.hello["instanceId"] = "new-guest"
        self.assert_blocked(self.watch.tick())
        self.assertEqual(self.guest.commands, [])

    def test_foreground_loss_does_not_block_release_only_cleanup(self):
        self.guest.target["isForeground"] = False
        self.assertEqual(self.watch.tick()["state"], "cleaned")

    def test_changed_queue_epoch_during_stop_invalidates_positive_observation(self):
        self.guest.on_stop = lambda: self.queue.register(self.resource, "replacement-epoch")
        result = self.watch.tick()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.row()["epoch"], "replacement-epoch")
        self.assertTrue(self.row()["blocked"])

    def test_journal_failure_does_not_free_resource(self):
        append = self.journal.append
        def fail(kind, value):
            if kind == "nav-control-cleanup/1":
                raise OSError("PRIVATE_TOKEN_OR_PATH")
            append(kind, value)
        with patch.object(self.journal, "append", fail):
            result = self.watch.tick()
        self.assert_blocked(result)
        self.assertNotIn("PRIVATE_TOKEN_OR_PATH", json.dumps(result))
        self.assertNotIn("PRIVATE_TOKEN_OR_PATH", self.journal.path.read_text())

    def test_receipt_that_becomes_old_during_storage_is_rejected(self):
        append = self.journal.append
        def delay(kind, value):
            append(kind, value)
            if kind == "nav-control-cleanup/1":
                self.clock.now += 6000
        with patch.object(self.journal, "append", delay):
            self.assert_blocked(self.watch.tick())

    def test_wall_clock_rollback_stops_but_cannot_publish_until_explicit_reconciliation(self):
        self.clean(); self.grant(); self.clock.now -= 10
        result = self.watch.tick()
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(result["emergencyStopVerified"])
        self.clock.now += 10
        self.assert_blocked(self.watch.tick())
        self.assertEqual(self.watch.tick(retry=True)["state"], "cleaned")

    def test_database_failure_stops_and_latches_local_controls(self):
        self.clean(); self.grant()
        with patch.object(self.queue, "status", side_effect=OSError("private-database-path")):
            result = self.watch.tick()
        self.assert_blocked(result)
        self.assertTrue(result["emergencyStopVerified"])
        self.assertNotIn("private-database-path", json.dumps(result))
        self.assertEqual(self.watch.tick(retry=True)["state"], "cleaned")

    def test_elapsed_observation_bound_prevents_publication(self):
        times = iter([100.0, 106.0])
        self.watch.monotonic = lambda: next(times)
        self.assert_blocked(self.watch.tick())

    def test_in_flight_request_must_drain_even_when_stop_reports_success(self):
        self.clean(); access = self.grant()
        self.guest.hold = True; self.guest.ack_actions = False
        action, result = self.action(access)
        self.assertTrue(self.guest.action_seen.wait(2))
        self.clock.now += 5000; self.watch.drain_timeout = .02
        self.assert_blocked(self.watch.tick())
        self.session.close(); action.join(2)
        self.assertFalse(action.is_alive())
        self.assertIn("error", result)

    def test_new_control_is_refused_while_cleanup_waits_for_guest(self):
        entered = threading.Event(); release = threading.Event(); result = {}
        def hold():
            entered.set(); release.wait(2)
        self.guest.on_stop = hold
        thread = threading.Thread(target=lambda: result.update(self.watch.tick()))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(host.ControlHostError):
                self.gateway.command("capture", {})
            self.assertEqual(self.watch.tick()["state"], "busy")
        finally:
            release.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["state"], "cleaned")
        self.assertEqual(sum(c["operation"] == "stop" for c in self.guest.commands), 1)

    def test_shutdown_stops_active_owner_and_keeps_resource_blocked(self):
        self.clean(); self.grant()
        result = self.watch.shutdown()
        self.assertTrue(result["stopVerified"])
        self.assert_blocked(result)
        self.assertIsNone(self.queue.dispatch())
        count = len(self.guest.commands)
        self.assertEqual(self.watch.shutdown()["reason"], "watchdog-shutdown")
        self.assertEqual(len(self.guest.commands), count)
        self.assertEqual(self.watch.tick(retry=True)["reason"], "watchdog-shutdown")

    def test_explicit_owned_loop_observes_expiry_and_shutdown_leaves_no_worker(self):
        self.clean(); self.grant()
        stop = threading.Event(); thread = threading.Thread(target=self.watch.run, args=(stop,))
        thread.start()
        try:
            self.clock.now += 5000
            self.assertTrue(self.guest.stopped.wait(2))
        finally:
            stop.set(); thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertTrue(self.row()["blocked"])
        self.assertTrue(self.watch._shutdown)

    def test_other_resource_is_not_cleaned_from_this_guest_evidence(self):
        self.clean()
        row = self.queue.register("host:desktop-input", "host-epoch")
        self.queue.cleanup("host:desktop-input", "host-epoch", row["generation"], self.clock.now,
                           "synthetic-other-owner", stopped=True, released=True, in_flight=False)
        self.grant(resources={self.resource: self.epoch, "host:desktop-input": "host-epoch"})
        self.clock.now += 5000
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        snapshot = self.queue.status()
        other = next(r for r in snapshot["resources"] if r["name"] == "host:desktop-input")
        self.assertTrue(other["blocked"])
        self.assertEqual(snapshot["requests"][0]["state"], "cleanup")

    def test_shared_host_or_mismatched_policy_construction_is_refused(self):
        with self.assertRaises(WatchdogError):
            LeaseWatchdog(self.queue, self.session, "host:desktop-input", self.identity, self.journal)
        self.session.dispatch_policy = nav.QueueDispatchPolicy(self.queue, {self.resource: "wrong-epoch"})
        with self.assertRaises(WatchdogError):
            LeaseWatchdog(self.queue, self.session, self.resource, self.identity, self.journal)
        self.assertEqual(self.guest.commands, [])

    def test_binding_is_copied_and_epoch_changes_with_process_identity(self):
        old = deepcopy(self.watch.identity)
        self.identity["target"]["processId"] = 999
        self.assertEqual(self.watch.identity, old)
        self.assertNotEqual(resource_epoch(self.identity), self.epoch)
        other = bind_identity(self.session.summary(), {"instanceId": "guest-one", "target": {**TARGET, "isForeground": False}})
        self.assertEqual(resource_epoch(other), self.epoch)

    def test_invalid_binding_and_runner_arguments_are_rejected(self):
        for value in (True, -1, float("nan"), 6):
            with self.subTest(value=value), self.assertRaises(WatchdogError):
                LeaseWatchdog(self.queue, self.session, self.resource, self.identity, self.journal, drain_timeout=value)
        for interval in (0, True, 2, float("nan")):
            with self.subTest(interval=interval), self.assertRaises(WatchdogError):
                self.watch.run(threading.Event(), interval_seconds=interval)
        with self.assertRaises(WatchdogError):
            self.watch.tick(retry=1)
        self.assertEqual(self.guest.commands, [])


    def test_stop_and_status_do_not_hold_a_queue_transaction(self):
        checked = []
        def inspect():
            with closing(sqlite3.connect(self.queue.path, timeout=0)) as database:
                database.execute("BEGIN IMMEDIATE")
                database.rollback()
            checked.append(self.queue.status()["resources"][0]["blocked"])
        self.guest.on_stop = inspect
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        self.assertEqual(checked, [1])

    def test_reconstructed_coordinator_preserves_original_expiry_and_owner(self):
        self.clean(); self.grant()
        reopened = nav.AccessQueue(self.queue.path, clock=self.clock)
        replacement = LeaseWatchdog(reopened, self.session, self.resource,
                                    self.identity, self.journal)
        self.clock.now += 5000
        self.assertEqual(replacement.tick()["state"], "cleaned")
        self.assertEqual(self.queue.status()["requests"][0]["state"], "expired")
        self.assertNotIn("action", [c["operation"] for c in self.guest.commands])

    def test_queued_second_action_is_invalidated_and_drained_before_cleanup(self):
        self.clean(); access = self.grant(); self.guest.hold = True
        first, first_result = self.action(access)
        self.assertTrue(self.guest.action_seen.wait(2))
        second, second_result = self.action(access)
        end = time.monotonic() + 2
        while self.session._protected_calls != 2:
            if time.monotonic() > end:
                self.fail("second action did not enter the owned queue")
            time.sleep(.005)
        self.clock.now += 5000
        self.assertEqual(self.watch.tick()["state"], "cleaned")
        first.join(2); second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertTrue(first_result["value"]["cancelled"])
        self.assertIn("error", second_result)
        self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), 1)

    def test_disconnection_during_receipt_storage_prevents_queue_cleanup(self):
        append = self.journal.append
        def close_after_record(kind, value):
            append(kind, value)
            if kind == "nav-control-cleanup/1":
                self.session.close()
        with patch.object(self.journal, "append", close_after_record), patch.object(self.queue, "cleanup", wraps=self.queue.cleanup) as cleanup:
            result = self.watch.tick()
            self.assertEqual(cleanup.call_count, 0)
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(self.row()["blocked"])

    def test_policy_replacement_is_not_silently_accepted(self):
        self.session.dispatch_policy = nav.QueueDispatchPolicy(self.queue, {self.resource: "other-epoch"})
        self.assert_blocked(self.watch.tick())
        self.assertEqual(self.guest.commands, [])

    def test_deleted_authority_is_not_recreated_and_session_is_stopped(self):
        self.queue.path.unlink()
        result = self.watch.tick()
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(result["emergencyStopVerified"])
        self.assertFalse(self.queue.path.exists())
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("arm", {})

    def test_nonboolean_stop_is_not_accepted(self):
        self.guest.stop_reply["stopped"] = 1
        self.assert_blocked(self.watch.tick())

    def test_nonfinite_elapsed_time_is_not_accepted(self):
        times = iter([100.0, float("nan")])
        self.watch.monotonic = lambda: next(times)
        self.assert_blocked(self.watch.tick())

    def test_receipt_is_present_before_cleanup_transaction(self):
        cleanup = self.queue.cleanup
        observed = []
        def verify(*args, **kwargs):
            receipt = args[4]
            records = [json.loads(line) for line in self.journal.path.read_text().splitlines()]
            self.assertTrue(any(r["evidenceKind"] == "nav-control-cleanup/1"
                                and r["value"]["receipt"] == receipt for r in records))
            observed.append(receipt)
            return cleanup(*args, **kwargs)
        with patch.object(self.queue, "cleanup", verify):
            result = self.watch.tick()
        self.assertEqual(result["state"], "cleaned")
        self.assertEqual(observed, [result["receipt"]])


# Each release condition is its own regression case, not just subtest accounting.
def status_case(field, bad):
    def test(self):
        self.guest.overrides[field] = bad
        self.assert_blocked(self.watch.tick())
        self.assertIsNone(self.row()["cleanup_receipt"])
    return test


for _field, _bad in (("armed", True), ("busy", True), ("recoveryRequired", True),
                     ("desktopInputsDown", ["w"]), ("armed", 0), ("busy", None)):
    setattr(WatchdogTests, "test_bad_status_" + _field + "_" + str(_bad).replace(" ", "_"), status_case(_field, _bad))


if __name__ == "__main__":
    unittest.main()
