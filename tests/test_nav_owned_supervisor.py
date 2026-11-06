"""Disposable queue/guest proof for the owned supervisor, never a live VM."""
import copy
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from scripts import nav_supervisor_bootstrap as bootstrap
from scripts.nav_access_queue import AccessQueue, QueueError
from tests.test_control_host import host, config
from tests.test_nav_control_watchdog import WatchGuest, VM
from tests.test_nav_access_queue import Clock


class OwnedSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.queue = AccessQueue(self.root / "authority.sqlite3", create=True, clock=self.clock)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(config(self.root), self.journal)
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = WatchGuest(self.gateway)
        self.addCleanup(self.guest.close)
        self.session = self.gateway.session()
        self.session.vm_identity = copy.deepcopy(VM)

    def owner(self):
        owner = bootstrap.OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal,
                                          interval_seconds=.05)
        self.addCleanup(lambda: self.assertFalse(owner.stop(timeout_seconds=5)["threadAlive"]))
        return owner

    def row(self):
        return self.queue.status()["resources"][0]

    def grant(self, name, epoch):
        self.queue.submit(name, "worker-" + name, "A", {"vm:lab-1": epoch})
        grant = self.queue.dispatch()
        self.assertEqual(grant["request_id"], name)
        return {"request_id": name, "token": grant["token"]}

    def wait_state(self, owner, state, seconds=3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            result = owner.status()
            if result["state"] == state:
                return result
            time.sleep(.005)
        self.fail((state, owner.status()))

    def test_competing_registration_cannot_replace_an_unobserved_owner(self):
        other = AccessQueue(self.queue.path, clock=self.clock)
        original = self.queue.register
        def inserted_before_register(resource, epoch, **kwargs):
            other.register(resource, "racing-epoch")
            return original(resource, epoch, **kwargs)
        self.queue.register = inserted_before_register
        with self.assertRaises((QueueError, bootstrap.CompositionError)):
            bootstrap.prepare_authority(self.session, self.queue, "vm:lab-1", self.journal)
        self.assertEqual(self.row()["epoch"], "racing-epoch")
        self.assertTrue(self.row()["blocked"])
        self.assertIsNone(self.session.dispatch_policy)
        self.assertTrue(self.session._controls_suspended)

    def test_constructor_is_inert_and_stop_before_start_is_inert(self):
        owner = self.owner()
        self.assertEqual(owner.status()["state"], "new")
        self.assertEqual(self.guest.commands, [])
        self.assertEqual(self.queue.status()["resources"], [])
        self.assertEqual(owner.stop()["state"], "stopped")
        self.assertEqual(self.guest.commands, [])
        self.assertIsNone(self.session.dispatch_policy)
        with self.assertRaises(bootstrap.CompositionError):
            owner.start()

    def test_start_readiness_requires_saved_cleanup_and_a_running_thread(self):
        owner = self.owner()
        status = owner.start()
        self.assertEqual(status["state"], "running")
        self.assertTrue(status["threadAlive"])
        self.assertTrue(status["initialCleanupVerified"])
        self.assertFalse(self.row()["blocked"])
        self.assertTrue(self.row()["cleanup_receipt"].startswith("nav-cleanup:"))
        self.assertEqual([c["operation"] for c in self.guest.commands],
                         ["status", "status", "status", "stop", "status"])
        self.assertFalse(self.session._controls_suspended)
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {})

    def test_stop_drains_thread_blocks_resource_and_cannot_be_restarted(self):
        owner = self.owner(); owner.start()
        result = owner.stop()
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["threadAlive"])
        self.assertFalse(result["terminationPending"])
        self.assertTrue(result["shutdownStopVerified"])
        self.assertTrue(self.row()["blocked"])
        self.assertTrue(self.session._controls_suspended)
        count = len(self.guest.commands)
        self.assertEqual(owner.stop(), result)
        self.assertEqual(len(self.guest.commands), count)
        with self.assertRaises(bootstrap.CompositionError):
            owner.start()

    def test_two_workers_handoff_after_expiry_without_replaying_original_action(self):
        owner = self.owner(); epoch = owner.start()["epoch"]
        access = self.grant("first", epoch)
        self.queue.submit("second", "worker-second", "B", {"vm:lab-1": epoch})
        self.guest.hold = True
        result = {}
        def action():
            try:
                result["value"] = self.gateway.command("action", {}, access=access)
            except Exception as error:
                result["error"] = type(error).__name__
        thread = threading.Thread(target=action); thread.start()
        self.assertTrue(self.guest.action_seen.wait(2))
        self.clock.now += 5000
        thread.join(3); self.assertFalse(thread.is_alive())
        self.assertTrue(result["value"]["cancelled"])
        end = time.monotonic() + 3
        while self.row()["blocked"] and time.monotonic() < end:
            time.sleep(.005)
        second = self.queue.dispatch()
        self.assertEqual(second["request_id"], "second")
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=access)
        self.guest.hold = False
        self.assertTrue(self.gateway.command("action", {}, access={
            "request_id": "second", "token": second["token"]})["fake"])
        self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), 2)
        self.assertNotIn(access["token"], self.journal.path.read_text())
        self.assertNotIn(second["token"], json.dumps(owner.status()))

    def test_failed_initial_stop_never_becomes_ready_or_silently_retries(self):
        self.guest.stop_reply["stopped"] = False
        owner = self.owner()
        with self.assertRaises(bootstrap.CompositionError):
            owner.start()
        result = owner.stop()
        self.assertEqual(result["state"], "blocked")
        self.assertFalse(result["initialCleanupVerified"])
        self.assertTrue(self.row()["blocked"])
        count = len(self.guest.commands)
        self.guest.stop_reply["stopped"] = True
        owner.stop()
        self.assertEqual(len(self.guest.commands), count)

    def test_disconnect_quarantines_ownership_and_never_rebinds_session(self):
        owner = self.owner(); owner.start()
        self.session.close()
        self.wait_state(owner, "blocked")
        self.assertTrue(self.row()["blocked"])
        self.assertFalse(owner.stop()["threadAlive"])
        self.assertFalse(owner.status()["shutdownStopVerified"])

    def test_queue_failure_suspends_even_when_quarantine_cannot_be_saved(self):
        owner = self.owner(); epoch = owner.start()["epoch"]
        access = self.grant("a", epoch)
        original = self.queue.status
        self.queue.status = lambda: (_ for _ in ()).throw(OSError("PRIVATE_FAILURE"))
        self.wait_state(owner, "blocked")
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=access)
        owner.stop()
        self.queue.status = original
        self.assertNotIn("PRIVATE_FAILURE", json.dumps(owner.status()))
        self.assertTrue(self.session._controls_suspended)

    def test_journal_failure_before_ready_does_not_publish_running(self):
        owner = self.owner()
        original = self.journal.append
        def reject(kind, value):
            if kind == "nav-supervisor-readiness/1":
                raise OSError("PRIVATE_CREDENTIAL")
            return original(kind, value)
        self.journal.append = reject
        with self.assertRaises(bootstrap.CompositionError) as error:
            owner.start()
        owner.stop()
        self.assertNotIn("PRIVATE_CREDENTIAL", str(error.exception))
        self.assertTrue(self.row()["blocked"])
        self.assertTrue(self.session._controls_suspended)

    def test_start_timeout_cannot_later_enable_commands(self):
        entered = threading.Event(); release = threading.Event()
        def delayed_status():
            entered.set(); release.wait(3)
        self.guest.on_status = delayed_status
        owner = self.owner()
        try:
            with self.assertRaises(bootstrap.CompositionError):
                owner.start(timeout_seconds=.1)
            self.assertTrue(entered.wait(2))
            self.assertFalse(owner.status()["initialCleanupVerified"])
            with self.assertRaises(host.ControlHostError):
                self.gateway.command("action", {})
        finally:
            release.set()
            result = owner.stop(timeout_seconds=5)
        self.assertFalse(result["threadAlive"])
        self.assertNotEqual(result["state"], "running")
        self.assertTrue(self.session._controls_suspended)
        self.assertTrue(all(row["blocked"] for row in self.queue.status()["resources"]))

    def test_stop_timeout_reports_pending_until_cleanup_really_finishes(self):
        owner = self.owner(); owner.start()
        entered = threading.Event(); release = threading.Event()
        def delayed_stop():
            entered.set(); release.wait(3)
        self.guest.on_stop = delayed_stop
        try:
            result = owner.stop(timeout_seconds=.1)
            self.assertTrue(entered.wait(2))
            self.assertEqual(result["state"], "stopping")
            self.assertTrue(result["terminationPending"])
            self.assertFalse(result["shutdownStopVerified"])
            self.assertTrue(self.row()["blocked"])
        finally:
            release.set()
            result = owner.stop(timeout_seconds=5)
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(result["shutdownStopVerified"])

    def test_second_supervisor_cannot_disrupt_existing_running_owner(self):
        first = self.owner(); first.start()
        second = self.owner()
        with self.assertRaises(bootstrap.CompositionError):
            second.start()
        second.stop()
        self.assertEqual(first.status()["state"], "running")
        self.assertFalse(self.session._controls_suspended)
        self.assertFalse(self.row()["blocked"])

    def test_thread_launch_failure_does_not_register_or_send(self):
        owner = self.owner()
        with patch.object(threading.Thread, "start", side_effect=RuntimeError("PRIVATE")):
            with self.assertRaises(bootstrap.CompositionError):
                owner.start()
        self.assertEqual(owner.status()["state"], "blocked")
        self.assertFalse(owner.status()["threadAlive"])
        self.assertEqual(self.queue.status()["resources"], [])
        self.assertEqual(self.guest.commands, [])

    def test_old_registered_epoch_requires_explicit_reconciliation(self):
        self.queue.register("vm:lab-1", "old")
        owner = self.owner()
        with self.assertRaises(bootstrap.CompositionError):
            owner.start()
        owner.stop()
        self.assertEqual(self.row()["epoch"], "old")
        self.assertTrue(self.row()["blocked"])

    def test_same_session_preparation_is_exclusive_before_identity_reads(self):
        entered = threading.Event(); release = threading.Event(); outcome = {}
        self.guest.on_status = lambda: (entered.set(), release.wait(3))
        def prepare():
            try:
                outcome["prepared"] = bootstrap.prepare_authority(
                    self.session, self.queue, "vm:lab-1", self.journal)
            except BaseException as error:
                outcome["error"] = error
        thread = threading.Thread(target=prepare); thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(bootstrap.CompositionError):
                bootstrap.prepare_authority(self.session, self.queue, "vm:lab-2", self.journal)
        finally:
            release.set(); thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertIn("prepared", outcome, outcome)
        self.assertEqual(len(self.queue.status()["resources"]), 1)

    def test_invalid_timing_values_have_no_side_effects(self):
        for value in (True, float("nan"), float("inf"), 0, -1, 10):
            with self.subTest(value=value), self.assertRaises(bootstrap.CompositionError):
                bootstrap.OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal,
                                          interval_seconds=value)
        owner = self.owner()
        for value in (True, float("nan"), float("inf"), 0, -1, 100):
            with self.subTest(timeout=value), self.assertRaises(bootstrap.CompositionError):
                owner.start(timeout_seconds=value)
        self.assertEqual(owner.status()["state"], "new")
        self.assertEqual(self.guest.commands, [])

    def test_saved_cleanup_alone_does_not_admit_before_runner_ready(self):
        owner = self.owner()
        entered = threading.Event(); release = threading.Event(); result = {}
        original = self.journal.append
        def delayed_journal(kind, value):
            if kind == "nav-supervisor-readiness/1":
                entered.set(); release.wait(3)
            return original(kind, value)
        self.journal.append = delayed_journal
        def start():
            try:
                result["value"] = owner.start(timeout_seconds=5)
            except BaseException as error:
                result["error"] = error
        thread = threading.Thread(target=start); thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(owner.status()["state"], "starting")
            self.assertFalse(self.row()["blocked"])
            access = self.grant("early", owner.status()["epoch"])
            with self.assertRaises(host.ControlHostError):
                self.gateway.command("action", {}, access=access)
            self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))
        finally:
            release.set(); thread.join(5)
        self.assertIn("value", result, result)
        self.assertTrue(self.gateway.command("action", {}, access=access)["fake"])

    def test_multiple_stop_callers_share_one_shutdown(self):
        owner = self.owner(); owner.start()
        before = sum(c["operation"] == "stop" for c in self.guest.commands)
        barrier = threading.Barrier(4); results = []; errors = []
        def stop():
            try:
                barrier.wait(timeout=2)
                results.append(owner.stop(timeout_seconds=5))
            except BaseException as error:
                errors.append(error)
        threads = [threading.Thread(target=stop) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(6)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r["state"] == "stopped" and not r["threadAlive"] for r in results))
        self.assertEqual(sum(c["operation"] == "stop" for c in self.guest.commands), before + 1)

    def test_stop_cancels_original_inflight_action_before_verified_exit(self):
        owner = self.owner(); access = self.grant("a", owner.start()["epoch"])
        self.guest.hold = True; result = {}
        def action():
            try:
                result["value"] = self.gateway.command("action", {}, access=access)
            except BaseException as error:
                result["error"] = error
        thread = threading.Thread(target=action); thread.start()
        self.assertTrue(self.guest.action_seen.wait(2))
        stopped = owner.stop(timeout_seconds=5)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result["value"]["cancelled"])
        self.assertEqual(stopped["state"], "stopped")
        self.assertTrue(stopped["shutdownStopVerified"])
        self.assertTrue(self.row()["blocked"])
        self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), 1)

    def test_unexpected_runner_exit_closes_admission_without_automatic_restart(self):
        owner = self.owner(); access = self.grant("a", owner.start()["epoch"])
        def fail(*args, **kwargs):
            raise RuntimeError("PRIVATE_RUNTIME_DATA")
        owner._prepared.watchdog.tick = fail
        self.wait_state(owner, "blocked")
        result = owner.stop()
        self.assertFalse(result["threadAlive"])
        self.assertEqual(result["errorCode"], "supervisor-operation-failed")
        self.assertTrue(self.row()["blocked"])
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=access)
        self.assertNotIn("PRIVATE_RUNTIME_DATA", json.dumps(result))

    def test_existing_watchdog_runner_contract_rejects_second_loop(self):
        owner = self.owner(); owner.start()
        with self.assertRaises(ValueError):
            with owner._prepared.watchdog.runner_boundary():
                self.fail("second runner was admitted")
        self.assertEqual(owner.status()["state"], "running")

    def test_six_competing_processes_register_exactly_one_startup_owner(self):
        gate = self.root / "go"
        script = "\n".join([
            "import sys,pathlib,time,json",
            "sys.path.insert(0,sys.argv[1]);import nav_access_queue as nav",
            "q=nav.AccessQueue(pathlib.Path(sys.argv[2]),clock=lambda:1000000)",
            "gate=pathlib.Path(sys.argv[3]);end=time.monotonic()+5",
            "while not gate.exists() and time.monotonic()<end: time.sleep(.005)",
            "assert gate.exists()",
            "try:",
            " r=q.register('vm:lab-1',sys.argv[4],require_absent=True)",
            " print(json.dumps({'won':True,'epoch':r['epoch']}))",
            "except nav.QueueError:",
            " print(json.dumps({'won':False}))",
        ])
        children = []
        try:
            for index in range(6):
                children.append(subprocess.Popen([
                    sys.executable, "-c", script,
                    str(Path(bootstrap.__file__).parent), str(self.queue.path), str(gate),
                    "epoch-" + str(index)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            gate.write_text("go")
            results = []
            for child in children:
                out, error = child.communicate(timeout=8)
                self.assertEqual(child.returncode, 0, error)
                results.append(json.loads(out))
            winners = [row for row in results if row["won"]]
            self.assertEqual(len(winners), 1, results)
            self.assertEqual(self.row()["epoch"], winners[0]["epoch"])
            self.assertTrue(self.row()["blocked"])
        finally:
            for child in children:
                if child.poll() is None: child.kill()
                child.communicate(timeout=3)

    def test_atomic_registration_same_epoch_refuses_without_mutating_row(self):
        before = self.queue.register("vm:lab-1", "known", require_absent=True)
        with self.assertRaises(QueueError):
            self.queue.register("vm:lab-1", "known", require_absent=True)
        self.assertEqual(self.row(), before)
        for value in (0, 1, None, "true"):
            with self.subTest(value=value), self.assertRaises(QueueError):
                self.queue.register("vm:other", "other", require_absent=value)
        self.assertEqual(len(self.queue.status()["resources"]), 1)

    def test_worker_readiness_does_not_open_admission_until_start_caller_accepts(self):
        owner = self.owner(); original_wait = owner._ready.wait
        arrived = threading.Event(); release = threading.Event(); outcome = {}
        def wait(timeout):
            result = original_wait(timeout)
            arrived.set(); release.wait(3)
            return result
        owner._ready.wait = wait
        def start():
            try:
                outcome["value"] = owner.start(timeout_seconds=5)
            except BaseException as error:
                outcome["error"] = error
        thread = threading.Thread(target=start); thread.start()
        try:
            self.assertTrue(arrived.wait(2))
            status = owner.status()
            self.assertEqual(status["state"], "starting")
            self.assertTrue(status["initialCleanupVerified"])
            access = self.grant("before-accept", status["epoch"])
            with self.assertRaises(host.ControlHostError):
                self.gateway.command("action", {}, access=access)
        finally:
            release.set(); thread.join(5)
        self.assertIn("value", outcome, outcome)
        self.assertTrue(self.gateway.command("action", {}, access=access)["fake"])

    def test_timeout_decision_after_cleanup_cannot_publish_late_running(self):
        owner = self.owner(); original_wait = owner._ready.wait
        def timeout_after_observation(timeout):
            self.assertTrue(original_wait(timeout))
            return False
        owner._ready.wait = timeout_after_observation
        with self.assertRaises(bootstrap.CompositionError):
            owner.start()
        stopped = owner.stop(timeout_seconds=5)
        self.assertEqual(stopped["state"], "blocked")
        self.assertEqual(stopped["errorCode"], "startup-timeout")
        self.assertFalse(stopped["threadAlive"])
        self.assertTrue(self.row()["blocked"])
        self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))


if __name__ == "__main__":
    unittest.main()
