"""Offline native-dispatch acceptance; all sockets/guests are disposable fakes."""

from contextlib import contextmanager, closing
import json
import http.client
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from tests.test_control_host import host, config, FakeGuest
from tests.test_nav_access_queue import nav, Clock


class RejectPolicy:
    @contextmanager
    def guard(self, operation, access):
        if operation not in ("status", "stop", "release"):
            raise ValueError("lease required")
        yield None


class RespondingGuest:
    def __init__(self, gateway):
        self.guest = FakeGuest(gateway.port)
        assert self.guest.receive() == {"type": "welcome"}
        self.guest.socket.settimeout(None)
        self.commands = []
        self.failures = []
        self.hold_actions = False
        self.pending = []
        self.action_seen = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 2
        while not gateway.local_status()["connected"]:
            if time.monotonic() >= deadline:
                raise AssertionError("fake guest failed to connect")
            time.sleep(.005)

    def _run(self):
        try:
            while True:
                command = self.guest.receive()
                self.commands.append(command)
                operation = command["operation"]
                if operation == "action":
                    self.action_seen.set()
                    if self.hold_actions:
                        self.pending.append(command)
                        continue
                if operation in ("stop", "release"):
                    self.guest.respond(command, {
                        "released": True, "armed": False,
                        "recoveryRequired": False, "busy": False,
                    })
                    for pending in self.pending:
                        self.guest.respond(pending, {"cancelled": True})
                    self.pending.clear()
                    continue
                if operation == "arm":
                    result = {"armToken": "fake-arm", "expiresInSeconds": 15}
                else:
                    result = {"fake": True, "operation": operation}
                self.guest.respond(command, result)
        except (EOFError, OSError, ValueError):
            pass
        except BaseException as error:
            self.failures.append(error)

    def close(self):
        try:
            self.guest.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.thread.join(2)
        self.guest.close()
        assert not self.thread.is_alive(), "fake reader did not stop"
        assert not self.failures, self.failures


class GatewayFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gateway = host.AgentGateway(config(self.root), host.EvidenceJournal(self.root))
        # Startup policy injection is the tested integration seam, not a live enable flag.
        self.gateway.dispatch_policy = RejectPolicy()
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = RespondingGuest(self.gateway)
        self.addCleanup(self.guest.close)

    def configured_queue(self, resources=None):
        self.clock = Clock()
        self.queue = nav.AccessQueue(self.root / "queue.sqlite3", create=True, clock=self.clock)
        self.resources = resources or {"vm:lab-1": "exact-epoch-1"}
        for name, epoch in self.resources.items():
            row = self.queue.register(name, epoch)
            self.queue.cleanup(name, epoch, row["generation"], self.clock.now,
                               "fake-stop-evidence", stopped=True, released=True, in_flight=False)
        self.queue.submit("request-a", "worker-a", "A", self.resources)
        self.grant = self.queue.dispatch()
        self.access = {"request_id": self.grant["request_id"], "token": self.grant["token"]}
        policy = nav.QueueDispatchPolicy(self.queue, self.resources)
        # A real production session must receive its immutable authority at construction.
        # Test replacement happens before any controlled command is issued.
        self.gateway.session().dispatch_policy = policy
        self.gateway.dispatch_policy = policy
        return self.queue

    def launch(self, operation="action", access=None):
        outcome = {}
        def invoke():
            try:
                outcome["result"] = self.gateway.command(operation, {}, access=access)
            except BaseException as error:
                outcome["error"] = error
        thread = threading.Thread(target=invoke)
        thread.start()
        return thread, outcome

    def test_missing_lease_is_rejected_before_wire_dispatch(self):
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {"armToken": "fake", "action": {}})
        self.assertFalse(self.guest.commands)
        self.assertTrue(self.gateway.command("status")["fake"])

    def test_valid_lease_sends_once_and_does_not_forward_or_log_private_token(self):
        self.configured_queue()
        result = self.gateway.command("action", {"armToken": "fake", "action": {}}, access=self.access)
        self.assertTrue(result["fake"])
        self.assertEqual([c["operation"] for c in self.guest.commands], ["action"])
        self.assertNotIn("access", self.guest.commands[0]["payload"])
        self.assertNotIn(self.grant["token"], json.dumps(self.guest.commands))
        self.assertNotIn(self.grant["token"], self.gateway.journal.path.read_text())

    def test_all_conflicting_operations_need_the_lease(self):
        self.configured_queue()
        for operation in ("capture", "arm", "action", "recover"):
            with self.subTest(operation=operation), self.assertRaises(host.ControlHostError):
                self.gateway.command(operation, {})
        self.assertFalse(self.guest.commands)

    def test_wrong_or_malformed_token_does_not_send_or_leak_it(self):
        self.configured_queue()
        for access in ({"request_id": "request-a", "token": "0" * 64},
                       {**self.access, "unexpected": True}, [], {"token": "private-secret"}):
            with self.subTest(kind=type(access).__name__), self.assertRaises(host.ControlHostError) as error:
                self.gateway.command("action", {}, access=access)
            self.assertNotIn("private-secret", str(error.exception))
            self.assertNotIn(self.grant["token"], str(error.exception))
        self.assertFalse(self.guest.commands)

    def test_expired_or_cancelled_lease_cannot_send(self):
        self.configured_queue()
        self.clock.now += 5000
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=self.access)
        self.assertFalse(self.guest.commands)
        self.assertEqual(self.queue.status()["requests"][0]["state"], "cleanup")

    def test_cancellation_before_dispatch_prevents_send(self):
        self.configured_queue()
        self.queue.cancel("request-a", "worker-a")
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=self.access)
        self.assertFalse(self.guest.commands)

    def test_trusted_resource_scope_cannot_be_replaced_by_caller_lease(self):
        self.configured_queue()
        self.gateway.session().dispatch_policy = nav.QueueDispatchPolicy(
            self.queue, {"vm:lab-2": "exact-epoch-1"})
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=self.access)
        self.assertFalse(self.guest.commands)

    def test_direct_session_request_has_same_guard(self):
        self.configured_queue()
        with self.assertRaises(host.ControlHostError):
            self.gateway.session().request("arm", {"captureId": "fake"})
        self.assertFalse(self.guest.commands)

    def test_queue_lock_is_not_held_while_waiting_for_guest_reply(self):
        self.configured_queue()
        self.guest.hold_actions = True
        action, outcome = self.launch(access=self.access)
        self.assertTrue(self.guest.action_seen.wait(2))
        # This would time out if request/response waiting held the fence or DB transaction.
        self.queue.cancel("request-a", "worker-a")
        stopped = self.gateway.command("stop", {})
        self.assertTrue(stopped["released"])
        action.join(2)
        self.assertFalse(action.is_alive())
        self.assertTrue(outcome["result"]["cancelled"])

    def test_stop_bypasses_queue_lock_and_invalidates_waiting_action(self):
        self.configured_queue()
        with self.queue.dispatch_fence():
            action, outcome = self.launch(access=self.access)
            # Wait until the session tracks the pending request, not a guessed sleep.
            deadline = time.monotonic() + 2
            while not self.gateway.session()._pending:
                if time.monotonic() > deadline:
                    self.fail("action did not reach admission")
                time.sleep(.005)
            self.assertTrue(self.gateway.command("stop", {})["released"])
            self.assertEqual([c["operation"] for c in self.guest.commands], ["stop"])
        action.join(2)
        self.assertFalse(action.is_alive())
        self.assertIsInstance(outcome.get("error"), host.ControlHostError)
        self.assertEqual([c["operation"] for c in self.guest.commands], ["stop"])

    def test_release_bypasses_invalid_lease(self):
        self.configured_queue()
        self.queue.cancel("request-a", "worker-a")
        self.assertTrue(self.gateway.command("release", {}, access={"invalid": True})["released"])
        self.assertEqual([c["operation"] for c in self.guest.commands], ["release"])

    def test_queued_action_is_checked_after_the_prior_action_finishes(self):
        self.configured_queue()
        self.guest.hold_actions = True
        first, first_result = self.launch(access=self.access)
        self.assertTrue(self.guest.action_seen.wait(2))
        second, second_result = self.launch(access=self.access)
        self.queue.cancel("request-a", "worker-a")
        self.gateway.command("release", {})
        first.join(2); second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertTrue(first_result["result"]["cancelled"])
        self.assertIsInstance(second_result.get("error"), host.ControlHostError)
        self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), 1)

    def test_lease_expiring_while_waiting_for_send_lock_is_rechecked(self):
        self.configured_queue()
        session = self.gateway.session()
        with session._send_lock:
            action, outcome = self.launch(access=self.access)
            deadline = time.monotonic() + 2
            while not session._pending:
                if time.monotonic() > deadline:
                    self.fail("action did not reach send wait")
                time.sleep(.005)
            self.clock.now += 5000
        action.join(2)
        self.assertFalse(action.is_alive())
        self.assertIsInstance(outcome.get("error"), host.ControlHostError)
        self.assertFalse(self.guest.commands)

    def test_lease_claim_on_uncoordinated_session_is_not_silently_accepted(self):
        self.configured_queue()
        self.gateway.session().dispatch_policy = None
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=self.access)
        self.assertFalse(self.guest.commands)

    def test_manual_http_route_cannot_bypass_policy_but_stop_remains_available(self):
        self.configured_queue()
        cfg = config(self.root)
        server = host.ControlHttpServer(("127.0.0.1", 0), self.gateway, cfg, b"<html>fake</html>")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        headers = {"Authorization": "Bearer " + cfg.operator_token,
                   "Origin": "http://127.0.0.1:" + str(server.server_address[1]),
                   "Content-Type": "application/json"}
        try:
            for route in ("capture", "recover"):
                connection.request("POST", "/api/" + route, b"{}", headers)
                response = connection.getresponse(); data = response.read()
                self.assertEqual(response.status, 409, data)
                self.assertIn("navigation", data.decode())
            self.assertFalse(self.guest.commands)
            connection.request("POST", "/api/stop", b"{}", headers)
            response = connection.getresponse(); data = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertTrue(data["released"])
            self.assertEqual([c["operation"] for c in self.guest.commands], ["stop"])
        finally:
            connection.close(); server.shutdown(); server.server_close(); thread.join(2)

    def test_changed_resource_generation_rejects_original_lease(self):
        self.configured_queue()
        self.queue.register("vm:lab-1", "replacement-epoch")
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("arm", {}, access=self.access)
        self.assertFalse(self.guest.commands)
        self.assertEqual(self.gateway.session().summary()["lastIssuedSequence"], 0)
        self.assertEqual(self.gateway.session()._pending, {})

    def test_exact_multiresource_lease_can_send(self):
        self.configured_queue({"vm:lab-1": "vm-epoch", "host:desktop-input": "desktop-epoch"})
        self.assertTrue(self.gateway.command("action", {}, access=self.access)["fake"])
        self.assertEqual(len(self.guest.commands), 1)

    def test_corrupt_authority_fails_closed_without_touching_transport(self):
        self.configured_queue()
        with closing(sqlite3.connect(self.queue.path)) as database:
            database.execute("PRAGMA user_version=999")
        with self.assertRaises(host.ControlHostError):
            self.gateway.command("action", {}, access=self.access)
        self.assertFalse(self.guest.commands)
        self.assertTrue(self.gateway.command("status")["fake"])



class QueueFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "authority.sqlite3"
        self.clock = Clock()
        self.queue = nav.AccessQueue(self.path, create=True, clock=self.clock)
        self.resource = {"vm:lab-1": "epoch-1"}
        row = self.queue.register("vm:lab-1", "epoch-1")
        self.queue.cleanup("vm:lab-1", "epoch-1", row["generation"], self.clock.now,
                           "fake-release", stopped=True, released=True, in_flight=False)
        self.queue.submit("a", "worker-a", "A", self.resource)
        self.grant = self.queue.dispatch()

    def test_fenced_admission_commits_db_before_transport_work(self):
        policy = nav.QueueDispatchPolicy(self.queue, self.resource)
        access = {"request_id": "a", "token": self.grant["token"]}
        with policy.guard("action", access) as admit:
            self.assertEqual(admit()["request_id"], "a")
            with closing(sqlite3.connect(self.path, timeout=0)) as database:
                database.execute("BEGIN IMMEDIATE")
                database.rollback()

    def test_second_queue_cancellation_waits_for_admitted_send_boundary(self):
        other = nav.AccessQueue(self.path, clock=self.clock)
        entered = threading.Event(); completed = threading.Event(); result = {}
        def cancel():
            entered.set()
            try:
                result["value"] = other.cancel("a", "worker-a")
            except BaseException as error:
                result["error"] = error
            finally:
                completed.set()
        with self.queue.dispatch_fence():
            self.queue.check("a", self.grant["token"])
            thread = threading.Thread(target=cancel)
            thread.start(); self.assertTrue(entered.wait(1))
            self.assertFalse(completed.wait(.1))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", result)
        self.assertEqual(result["value"]["state"], "cleanup")
        with self.assertRaises(nav.QueueError):
            self.queue.check("a", self.grant["token"])

    def test_cross_process_cancellation_uses_the_same_fence(self):
        marker = self.path.parent / "attempted.txt"
        script = "\n".join((
            "import sys,pathlib,json", "sys.path.insert(0,sys.argv[1])", "import nav_access_queue as nav",
            "q=nav.AccessQueue(pathlib.Path(sys.argv[2]),clock=lambda:1000000)",
            "pathlib.Path(sys.argv[3]).write_text('ready')", "print(json.dumps(q.cancel('a','worker-a')))"))
        with self.queue.dispatch_fence():
            child = subprocess.Popen([sys.executable, "-c", script,
                                      str(Path(nav.__file__).parent), str(self.path), str(marker)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 3
                while not marker.exists():
                    if time.monotonic() > deadline:
                        self.fail("child did not reach cancellation")
                    time.sleep(.01)
                self.assertIsNone(child.poll())
                self.assertEqual(self.queue.check("a", self.grant["token"])["state"], "active")
            except BaseException:
                child.kill(); child.communicate(timeout=3)
                raise
        output, error = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, error)
        self.assertEqual(json.loads(output)["state"], "cleanup")

    def test_different_authority_does_not_share_dispatch_fence(self):
        other = nav.AccessQueue(self.path.parent / "other.sqlite3", create=True, clock=self.clock)
        result = {}
        with self.queue.dispatch_fence():
            thread = threading.Thread(target=lambda: result.update(other.status()))
            thread.start(); thread.join(1)
            self.assertFalse(thread.is_alive())
        self.assertEqual(result["resources"], [])

    def test_resource_scope_is_copied_and_cannot_be_mutated_after_construction(self):
        resources = dict(self.resource)
        policy = nav.QueueDispatchPolicy(self.queue, resources)
        resources.clear()
        with policy.guard("action", {"request_id": "a", "token": self.grant["token"]}) as admit:
            self.assertEqual(admit()["request_id"], "a")

    def test_scope_must_match_all_declared_resources_not_a_subset(self):
        policy = nav.QueueDispatchPolicy(self.queue, {**self.resource, "host:desktop-input": "host-1"})
        with self.assertRaises(nav.QueueError):
            with policy.guard("arm", {"request_id": "a", "token": self.grant["token"]}) as admit:
                admit()

    def test_guard_does_not_reset_missing_database_or_authority(self):
        self.path.unlink()
        policy = nav.QueueDispatchPolicy(self.queue, self.resource)
        with self.assertRaises(nav.QueueError):
            with policy.guard("action", {"request_id": "a", "token": self.grant["token"]}) as admit:
                admit()
        self.assertFalse(self.path.exists())

    def test_fence_wait_is_bounded_and_does_not_change_owner(self):
        entered = threading.Event(); release = threading.Event()
        def hold():
            with self.queue.dispatch_fence():
                entered.set(); release.wait(2)
        thread = threading.Thread(target=hold); thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(nav.QueueError):
                with self.queue.dispatch_fence(timeout=0):
                    self.fail("contended fence was acquired")
        finally:
            release.set(); thread.join(2)
        self.assertEqual(self.queue.check("a", self.grant["token"])["state"], "active")

    def test_worker_death_releases_fence_but_does_not_replay_or_free_its_lease(self):
        marker = self.path.parent / "holding.txt"
        script = "\n".join((
            "import sys,pathlib,time", "sys.path.insert(0,sys.argv[1])", "import nav_access_queue as nav",
            "q=nav.AccessQueue(pathlib.Path(sys.argv[2]),clock=lambda:1000000)",
            "with q.dispatch_fence():", " pathlib.Path(sys.argv[3]).write_text('held')",
            " time.sleep(60)"))
        child = subprocess.Popen([sys.executable, "-c", script, str(Path(nav.__file__).parent),
                                  str(self.path), str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 3
            while not marker.exists():
                if time.monotonic() > deadline:
                    self.fail("private lock holder did not start")
                time.sleep(.01)
            child.kill(); child.communicate(timeout=3)
            self.assertEqual(self.queue.check("a", self.grant["token"])["state"], "active")
            self.assertIsNone(self.queue.dispatch())
            self.clock.now += 5000
            self.assertEqual(self.queue.status()["requests"][0]["state"], "cleanup")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)



if __name__ == "__main__":
    unittest.main()
