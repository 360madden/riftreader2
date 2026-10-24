"""Disposable Windows mutex/guest integration. No actual VM or desktop access."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.test_control_host import host, config
from tests.test_control_lease_access import CallerGuest
from tests.test_nav_control_watchdog import VM
from scripts.nav_access_queue import AccessQueue
from scripts.nav_supervisor_bootstrap import OwnedSupervisor


@unittest.skipUnless(os.name == "nt", "Windows shared-console contract")
class ConsoleReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        vmx = self.root / "lab.vmx"; vmx.touch()
        vmrun = self.root / "vmrun.exe"; vmrun.touch()
        self.cfg = replace(config(self.root), vmx=vmx, vmrun=vmrun, vnc_port=5905)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(self.cfg, self.journal, require_supervisor=True,
                                         exclusive_console=True)
        self.guard = self.gateway.vm_guard
        self.identity = {**copy.deepcopy(VM), "vmx": self.guard.module.path_key(vmx)}
        self.addCleanup(self.gateway.close)
        self.collect = patch.object(self.guard.module, "collect_identity", side_effect=lambda _: dict(self.identity))
        self.verify = patch.object(self.guard.module, "verify_identity", side_effect=lambda *_: dict(self.identity))
        self.collect.start(); self.verify.start()
        self.addCleanup(self.collect.stop); self.addCleanup(self.verify.stop)

    def contender(self, vmx=None):
        code = "\n".join([
            "import sys,json,pathlib;sys.path.insert(0,sys.argv[1]);import vm_console_native as c",
            "try:", " with c.ControlMutex(pathlib.Path(sys.argv[2])): print(json.dumps({'acquired':True}))",
            "except c.Blocked as e: print(json.dumps({'acquired':False,'reason':str(e)}))"])
        result = subprocess.run([sys.executable, "-c", code, str(Path(host.__file__).parent),
                                 str(vmx or self.cfg.vmx)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def guest(self):
        self.gateway.start()
        guest = CallerGuest(self.gateway); self.addCleanup(guest.close)
        return guest

    def test_idle_gateway_excludes_console_until_explicit_close(self):
        self.gateway.start()
        self.assertEqual(self.contender(), {"acquired": False, "reason": "controller-busy"})
        self.assertTrue(self.guard.console_status()["held"])
        self.assertFalse(self.gateway.local_status()["connected"])
        self.assertTrue(self.gateway.local_status()["consoleReservation"]["held"])
        self.assertTrue(self.gateway.close()["consoleReleased"])
        self.assertTrue(self.contender()["acquired"])

    def test_different_vm_path_is_not_blocked(self):
        self.gateway.start()
        self.assertTrue(self.contender(self.root / "other.vmx")["acquired"])

    def test_authorized_native_request_from_another_thread_borrows_reservation(self):
        guest = self.guest()
        queue = AccessQueue(self.root / "queue.sqlite3", create=True)
        owner = OwnedSupervisor(self.gateway.session(), queue, "vm:lab-1", self.journal)
        try:
            epoch = owner.start()["epoch"]
            queue.submit("a", "worker", "A", {"vm:lab-1": epoch}, ttl_ms=30000, max_ms=30000)
            grant = queue.dispatch(); access = {"request_id": "a", "token": grant["token"]}
            outcome = {}
            def action():
                try: outcome["value"] = self.gateway.command("action", {}, access=access)
                except BaseException as error: outcome["error"] = repr(error)
            thread = threading.Thread(target=action); thread.start(); thread.join(3)
            self.assertFalse(thread.is_alive()); self.assertIn("value", outcome, outcome)
            self.assertTrue(outcome["value"]["fake"])
            self.assertFalse(self.contender()["acquired"])
            self.assertNotIn(grant["token"], self.journal.path.read_text())
        finally:
            self.assertFalse(owner.stop()["threadAlive"])
        # Losing supervisor readiness does not release the host's console fence.
        self.assertFalse(self.contender()["acquired"])
        self.assertTrue(self.gateway.command("stop")["stopped"])
        self.assertEqual(sum(c["operation"] == "action" for c in guest.commands), 1)

    def test_missing_lease_still_denied_under_host_reservation(self):
        guest = self.guest()
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {})
        self.assertEqual(guest.commands, [])
        self.assertTrue(self.gateway.command("stop")["stopped"])

    def test_collect_on_authentication_thread_does_not_reacquire_mutex(self):
        self.gateway.start(); result = {}
        thread = threading.Thread(target=lambda: result.update(self.guard.collect()))
        thread.start(); thread.join(2)
        self.assertEqual(result, self.identity)
        self.assertEqual(self.guard.console_status()["inFlight"], 0)
        self.assertFalse(self.contender()["acquired"])

    def test_vm_drift_closes_new_admission_but_retains_console_exclusion(self):
        guest = self.guest()
        expected = dict(self.identity)
        self.identity["startTicks"] += 1
        called = []
        with self.assertRaises(host.ControlHostError):
            self.guard.request(expected, lambda: called.append(True), fast=True)
        self.assertEqual(called, [])
        self.assertTrue(self.guard.console_status()["faulted"])
        self.assertFalse(self.contender()["acquired"])
        self.assertTrue(self.gateway.command("stop")["stopped"])
        self.assertEqual([c["operation"] for c in guest.commands], ["stop"])

    def test_post_request_identity_drift_is_not_reported_as_success(self):
        self.gateway.start(); expected = dict(self.identity); calls = []
        def action():
            calls.append(1); self.identity["pid"] += 1
            return {"fake": True}
        with self.assertRaises(host.ControlHostError):
            self.guard.request(expected, action, fast=True)
        self.assertEqual(calls, [1]); self.assertTrue(self.guard.console_status()["faulted"])
        self.assertFalse(self.contender()["acquired"])

    def test_callback_error_does_not_falsely_claim_identity_drift(self):
        self.gateway.start()
        def fail(): raise host.ControlHostError("fixture operation rejected")
        with self.assertRaises(host.ControlHostError): self.guard.request(self.identity, fail, fast=True)
        self.assertFalse(self.guard.console_status()["faulted"])
        self.assertEqual(self.guard.collect(), self.identity)

    def test_release_timeout_retains_lock_and_requires_explicit_retry(self):
        self.gateway.start(); entered = threading.Event(); release = threading.Event(); result = {}
        def callback(): entered.set(); release.wait(4); return "done"
        def invoke():
            try: result["value"] = self.guard.request(self.identity, callback, fast=True)
            except BaseException as error: result["error"] = type(error).__name__
        thread = threading.Thread(target=invoke); thread.start()
        try:
            self.assertTrue(entered.wait(2))
            result_close = self.guard.release_console(timeout_seconds=0)
            self.assertFalse(result_close["released"])
            self.assertTrue(result_close["releasePending"])
            self.assertFalse(self.contender()["acquired"])
            with self.assertRaises(host.ControlHostError): self.guard.collect()
        finally:
            release.set(); thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertFalse(self.contender()["acquired"])
        self.assertTrue(self.guard.release_console()["released"])
        self.assertTrue(self.contender()["acquired"])
        # The same guard must not silently fall back to uncoordinated operation.
        with self.assertRaises(host.ControlHostError): self.guard.collect()

    def test_wrong_thread_release_refuses_without_unlocking(self):
        self.gateway.start(); errors = []
        def close():
            try: self.guard.release_console()
            except host.ControlHostError as error: errors.append(str(error))
        thread = threading.Thread(target=close); thread.start(); thread.join(2)
        self.assertEqual(len(errors), 1); self.assertFalse(self.contender()["acquired"])
        self.assertTrue(self.guard.release_console()["released"])

    def test_duplicate_start_does_not_release_original_reservation(self):
        self.gateway.start()
        with self.assertRaises(host.ControlHostError): self.gateway.start()
        self.assertFalse(self.contender()["acquired"])
        self.assertTrue(self.guard.console_status()["held"])

    def test_listener_failure_releases_its_new_reservation(self):
        with patch.object(host.socket.socket, "bind", side_effect=OSError("fixture port busy")):
            with self.assertRaises(OSError): self.gateway.start()
        self.assertTrue(self.contender()["acquired"])
        self.assertFalse(self.guard.console_status()["held"])

    def test_identity_failure_before_start_opens_no_listener_or_console(self):
        with patch.object(self.guard.module, "collect_identity", side_effect=self.guard.module.Blocked("target-drift")):
            with self.assertRaises(host.ControlHostError): self.gateway.start()
        self.assertIsNone(self.gateway.port)
        self.assertTrue(self.contender()["acquired"])

    def test_conflicting_controller_blocks_start_before_identity_or_listener(self):
        ready = self.root / "holder-ready"; release = self.root / "holder-release"
        code = "\n".join([
            "import sys,pathlib,time;sys.path.insert(0,sys.argv[1]);import vm_console_native as c",
            "with c.ControlMutex(pathlib.Path(sys.argv[2])):",
            " pathlib.Path(sys.argv[3]).write_text('ready')",
            " end=time.monotonic()+8",
            " while not pathlib.Path(sys.argv[4]).exists() and time.monotonic()<end: time.sleep(.01)"])
        child = subprocess.Popen([sys.executable, "-c", code, str(Path(host.__file__).parent),
            str(self.cfg.vmx), str(ready), str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        import time
        try:
            end = time.monotonic() + 4
            while not ready.exists() and time.monotonic() < end: time.sleep(.01)
            self.assertTrue(ready.exists())
            with patch.object(self.guard.module, "collect_identity") as collect:
                with self.assertRaisesRegex(host.ControlHostError, "controller-busy"):
                    self.gateway.start()
                collect.assert_not_called()
            self.assertIsNone(self.gateway.port)
        finally:
            release.write_text('release'); child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0)

    def test_closing_does_not_lose_reservation_while_callback_remains(self):
        self.gateway.start(); entered = threading.Event(); release = threading.Event()
        def work(): self.guard.request(self.identity, lambda: (entered.set(), release.wait(3)), fast=True)
        thread = threading.Thread(target=work); thread.start()
        try:
            self.assertTrue(entered.wait(2))
            result = self.gateway.close(reservation_timeout_seconds=0)
            self.assertFalse(result["consoleReleased"])
            self.assertFalse(self.contender()["acquired"])
        finally:
            release.set(); thread.join(3)
        self.assertTrue(self.gateway.close()["consoleReleased"])

    def test_exclusive_gateway_rejects_missing_identity_or_legacy_mode(self):
        with self.assertRaises(host.ControlHostError):
            host.AgentGateway(config(self.root), self.journal, require_supervisor=True, exclusive_console=True)
        with self.assertRaises(host.ControlHostError):
            host.AgentGateway(self.cfg, self.journal, exclusive_console=True)
        for value in (None, 1, "yes"):
            with self.assertRaises(host.ControlHostError):
                host.AgentGateway(self.cfg, self.journal, require_supervisor=True, exclusive_console=value)

    def test_real_console_cli_capture_and_bootstrap_refuse_before_target_access(self):
        self.gateway.start()
        actions = self.root / "actions.json"
        actions.write_text(json.dumps({"schemaVersion": 1, "actions": [{"type": "keyPress", "key": "esc"}]}))
        for command in ("capture", "bootstrap"):
            output = self.root / ("cli-" + command)
            arguments = [sys.executable, str(Path(host.__file__).with_name("vm_console_native.py")),
                "--vmx", str(self.cfg.vmx), "--vmrun", str(self.cfg.vmrun), "--output", str(output), command]
            if command == "bootstrap": arguments += ["--actions", str(actions)]
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stderr)["reason"], "controller-busy")
            self.assertFalse((output / "screen.png").exists())
            self.assertFalse((output / "identity.json").exists())

    def test_invalid_release_timeout_cannot_unlock_a_live_owner(self):
        self.gateway.start()
        for value in (True, float("inf"), float("nan"), -1, 6):
            with self.subTest(value=value), self.assertRaises(host.ControlHostError):
                self.guard.release_console(timeout_seconds=value)
        self.assertFalse(self.contender()["acquired"])
        self.assertFalse(self.guard.console_status()["closing"])

    def test_slow_identity_check_also_remains_pinned(self):
        self.gateway.start(); calls = []
        self.assertEqual(self.guard.request(self.identity, lambda: calls.append(1), fast=False), None)
        self.assertEqual(calls, [1]); self.assertFalse(self.contender()["acquired"])

    def test_native_capture_rechecks_vm_identity_before_guest_request(self):
        guest = self.guest()
        self.identity["startTicks"] += 1
        with self.assertRaises(host.ControlHostError): self.gateway.capture()
        self.assertEqual(guest.commands, [])
        self.assertTrue(self.guard.console_status()["faulted"])

    def test_stopped_gateway_cannot_restart_in_legacy_mode(self):
        self.gateway.start(); self.gateway.close()
        with self.assertRaises(host.ControlHostError): self.gateway.start()
        with self.assertRaises(host.ControlHostError): self.guard.collect()
        self.assertTrue(self.contender()["acquired"])

    def test_raw_mutex_wrong_thread_cannot_drop_the_owning_handle(self):
        mutex = self.guard.module.ControlMutex(self.cfg.vmx)
        mutex.__enter__(); errors = []
        try:
            def release():
                try: mutex.__exit__(None, None, None)
                except self.guard.module.Blocked as error: errors.append(str(error))
            thread = threading.Thread(target=release); thread.start(); thread.join(2)
            self.assertEqual(errors, ["controller-lock-wrong-thread"])
            self.assertFalse(self.contender()["acquired"])
            with self.assertRaises(self.guard.module.Blocked): mutex.__enter__()
        finally:
            mutex.__exit__(None, None, None)
        self.assertTrue(self.contender()["acquired"])

    def test_reconnect_does_not_drop_gateway_reservation(self):
        guest = self.guest(); previous = self.gateway.session(); previous.close()
        other = CallerGuest(self.gateway)
        try:
            self.assertIsNot(self.gateway.session(), previous)
            self.assertTrue(self.gateway.session()._controls_suspended)
            self.assertFalse(self.contender()["acquired"])
            with self.assertRaises(host.ControlHostError): self.gateway.command("action", {})
            self.assertEqual(other.commands, [])
        finally: other.close()

    def test_missing_authenticated_identity_never_invokes_callback(self):
        self.gateway.start(); calls = []
        for expected in (None, [], "not-an-identity"):
            with self.subTest(expected=expected), self.assertRaises(host.ControlHostError):
                self.guard.request(expected, lambda: calls.append(1), fast=False)
        self.assertEqual(calls, [])

    def test_closing_during_acquisition_cannot_publish_late_reservation(self):
        entered = threading.Event(); release = threading.Event(); outcome = {}
        def observe(_):
            entered.set(); release.wait(3); return dict(self.identity)
        def acquire():
            try: outcome["value"] = self.guard.reserve_console()
            except BaseException as error: outcome["error"] = type(error).__name__
        with patch.object(self.guard.module, "collect_identity", side_effect=observe):
            thread = threading.Thread(target=acquire); thread.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.guard.release_console(timeout_seconds=0),
                                 {"released": False, "releasePending": True})
                self.assertFalse(self.contender()["acquired"])
            finally:
                release.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome.get("error"), "ControlHostError")
        self.assertTrue(self.guard.release_console()["released"])
        self.assertFalse(self.guard.console_status()["held"])
        self.assertTrue(self.contender()["acquired"])

    def test_reserved_guard_refuses_duplicate_ownership_without_release(self):
        self.gateway.start()
        with self.assertRaises(host.ControlHostError): self.guard.reserve_console()
        self.assertFalse(self.contender()["acquired"])

    def test_legacy_per_request_guard_behavior_is_preserved(self):
        guard = host.VmEpochGuard(self.cfg)
        with patch.object(guard.module, "collect_identity", return_value=self.identity):
            self.assertEqual(guard.collect(), self.identity)
        self.assertTrue(self.contender()["acquired"])


if __name__ == "__main__":
    unittest.main()
