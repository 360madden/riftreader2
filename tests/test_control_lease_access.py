"""Disposable HTTP/CLI ownership acceptance, never live VM input."""
import base64
import copy
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from tests.test_control_host import host, config, FakeGuest, bmp_bytes
from tests.test_control_client import client, FakeOpener, FakeResponse, write_config, parse
from tests.test_nav_control_watchdog import VM, TARGET
from scripts.nav_access_queue import AccessQueue
from scripts.nav_supervisor_bootstrap import OwnedSupervisor

ACCESS = {"request_id": "worker:test-1", "token": "a" * 64}
ACTION = {"armToken": "fake-arm", "action": {"keys": ["w"], "holdMilliseconds": 20,
          "mouseButton": None, "deltaX": 0, "deltaY": 0, "wheelNotches": 0}}


class CallerGuest:
    def __init__(self, gateway):
        self.guest = FakeGuest(gateway.port)
        assert self.guest.receive() == {"type": "welcome"}
        self.guest.socket.settimeout(None)
        self.commands = []
        self.errors = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 2
        while not gateway.local_status()["connected"]:
            if time.monotonic() >= deadline:
                raise AssertionError("fake guest was not published")
            time.sleep(.005)

    def _run(self):
        try:
            while True:
                command = self.guest.receive()
                self.commands.append(command)
                operation = command["operation"]
                if operation == "status":
                    value = {"instanceId": "guest-one", "target": copy.deepcopy(TARGET),
                             "armed": False, "busy": False, "recoveryRequired": False,
                             "desktopInputsDown": []}
                elif operation == "capture":
                    value = {"captureId": "capture-" + str(len(self.commands)),
                             "imageBase64": base64.b64encode(bmp_bytes()).decode(),
                             "imageFormat": "bmp", "target": copy.deepcopy(TARGET),
                             "reviewExpiresInSeconds": 45}
                elif operation == "arm":
                    value = {"armToken": "fake-arm", "expiresInSeconds": 15}
                elif operation == "stop":
                    value = {"stopped": True, "recoveryRequired": False}
                else:
                    value = {"released": True, "fake": True, "recoveryRequired": False}
                self.guest.respond(command, value)
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
        assert not self.thread.is_alive()
        assert not self.errors, self.errors


class HttpLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = config(self.root)
        self.journal = host.EvidenceJournal(self.root)
        self.gateway = host.AgentGateway(self.cfg, self.journal)
        self.gateway.start()
        self.addCleanup(self.gateway.close)
        self.guest = CallerGuest(self.gateway)
        self.addCleanup(self.guest.close)
        self.session = self.gateway.session()
        self.session.vm_identity = copy.deepcopy(VM)
        self.queue = AccessQueue(self.root / "queue.sqlite3", create=True)
        self.owner = OwnedSupervisor(self.session, self.queue, "vm:lab-1", self.journal)
        self.addCleanup(lambda: self.assertFalse(self.owner.stop(timeout_seconds=5)["threadAlive"]))
        epoch = self.owner.start()["epoch"]
        self.queue.submit("worker:test-1", "worker-one", "A", {"vm:lab-1": epoch},
                          ttl_ms=30000, max_ms=30000)
        grant = self.queue.dispatch()
        self.access = {"request_id": grant["request_id"], "token": grant["token"]}
        self.server = host.ControlHttpServer(("127.0.0.1", 0), self.gateway, self.cfg, b"fixture")
        self.http_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.http_thread.start()
        self.addCleanup(self.close_http)

    def close_http(self):
        self.server.shutdown(); self.server.server_close(); self.http_thread.join(2)

    def post(self, operation, payload, access=None, *, raw=None, authorized=True):
        value = {"payload": payload, "access": access} if access is not None else payload
        data = raw if raw is not None else json.dumps(value)
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=4)
        try:
            conn.request("POST", "/api/" + operation, data, {
                "Authorization": "Bearer " + (self.cfg.operator_token if authorized else "wrong"),
                "Origin": self.server.expected_origin, "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_valid_owned_action_reaches_guest_without_lease_credentials(self):
        before = len(self.guest.commands)
        status, value = self.post("action", ACTION, self.access)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["fake"])
        self.assertEqual(len(self.guest.commands), before + 1)
        self.assertEqual(self.guest.commands[-1]["payload"], ACTION)
        self.assertNotIn(self.access["token"], self.journal.path.read_text())
        self.assertNotIn(self.access["token"], json.dumps(value))

    def test_capture_arm_and_recover_share_owned_http_path(self):
        cases = [("capture", {}), ("arm", {"captureId": "fresh", "reviewNote": "reviewed fresh fake frame"}),
                 ("recover", {})]
        for operation, payload in cases:
            with self.subTest(operation=operation):
                status, result = self.post(operation, payload, self.access)
                self.assertEqual(status, 200, result)
                self.assertEqual(self.guest.commands[-1]["operation"], operation)
                self.assertEqual(self.guest.commands[-1]["payload"], payload)
        self.assertNotIn(self.access["token"], self.journal.path.read_text())

    def test_missing_wrong_and_malformed_access_cannot_send(self):
        for access in (None, {**self.access, "token": "b" * 64}, {}, [],
                       {**self.access, "extra": "private"}, {**self.access, "request_id": "wrong"}):
            with self.subTest(accessType=type(access).__name__):
                before = sum(c["operation"] == "action" for c in self.guest.commands)
                status, value = self.post("action", ACTION, access)
                self.assertEqual(status, 409)
                self.assertEqual(sum(c["operation"] == "action" for c in self.guest.commands), before)
                self.assertNotIn(self.access["token"], json.dumps(value))

    def test_cancelled_lease_cannot_be_reused(self):
        self.queue.cancel(self.access["request_id"], "worker-one")
        status, _ = self.post("action", ACTION, self.access)
        self.assertEqual(status, 409)
        self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))

    def test_payload_validation_still_applies_inside_envelope(self):
        for operation, payload in (("capture", {"extra": True}), ("arm", {}), ("action", {}),
                                   ("action", {**ACTION, "extra": True}), ("recover", [])):
            with self.subTest(operation=operation):
                before = len(self.guest.commands)
                status, _ = self.post(operation, payload, self.access)
                self.assertEqual(status, 409)
                self.assertEqual(len(self.guest.commands), before)

    def test_operator_authentication_is_required_before_lease_parsing(self):
        status, _ = self.post("action", ACTION, self.access, authorized=False)
        self.assertEqual(status, 401)
        self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))

    def test_unknown_envelope_fields_and_duplicate_tokens_rejected(self):
        values = [{"access": self.access}, {"payload": ACTION},
                  {"payload": ACTION, "access": self.access, "extra": 1}]
        for value in values:
            status, _ = self.post("action", None, raw=json.dumps(value))
            self.assertEqual(status, 409)
        raw = json.dumps({"payload": ACTION, "access": self.access})
        raw = raw.replace('"token":', '"token":"duplicate", "token":', 1)
        self.assertEqual(self.post("action", None, raw=raw)[0], 409)
        self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))

    def test_stop_release_and_status_need_no_lease(self):
        self.queue.cancel(self.access["request_id"], "worker-one")
        for operation in ("stop", "release"):
            status, value = self.post(operation, {})
            self.assertEqual(status, 200, value)
        self.assertEqual(self.gateway.command("status")["desktopInputsDown"], [])

    def test_valid_lease_is_refused_if_session_has_no_installed_policy(self):
        self.owner.stop()
        self.session.dispatch_policy = None
        with self.session.cleanup_boundary() as permit:
            permit()
        status, _ = self.post("action", ACTION, self.access)
        self.assertEqual(status, 409)
        self.assertFalse(any(c["operation"] == "action" for c in self.guest.commands))

    def test_real_cli_transport_can_carry_owned_request(self):
        cfg = type("Config", (), {"ui_port": self.server.server_address[1],
                                  "operator_token": self.cfg.operator_token})()
        transport = client.ControlClient(cfg, access=self.access)
        result = transport.request("/api/action", method="POST", payload=ACTION)
        self.assertTrue(result["fake"])
        self.assertEqual(self.guest.commands[-1]["payload"], ACTION)


class LeaseClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = write_config(self.root)
        self.lease = self.root / "lease.private.json"
        self.lease.write_text(json.dumps(ACCESS))

    def run_command(self, name, *args, responses=None):
        opener = FakeOpener(*(responses or [FakeResponse({"recoveryRequired": False})]))
        parsed = client.build_parser().parse_args(["--config", str(self.config), "--lease", str(self.lease), name, *args])
        return client.run(parsed, opener=opener), opener

    def test_recover_wraps_minimal_private_credential(self):
        _, opener = self.run_command("recover")
        sent = json.loads(opener.calls[0][0].data)
        self.assertEqual(sent, {"access": ACCESS, "payload": {}})
        self.assertEqual(len(opener.calls), 1)

    def test_native_dispatch_grant_can_be_loaded_without_forwarding_metadata(self):
        self.lease.write_text(json.dumps({**ACCESS, "owner": "worker-one", "track": "A",
            "lease": {"vm:lab-1": {"epoch": "opaque", "generation": 1}},
            "expires_ms": 1000, "deadline_ms": 2000}))
        _, opener = self.run_command("recover")
        self.assertEqual(json.loads(opener.calls[0][0].data), {"access": ACCESS, "payload": {}})

    def test_stop_release_and_status_ignore_even_an_unreadable_lease_file(self):
        self.lease.unlink()
        for command in ("stop", "release", "status"):
            with self.subTest(command=command):
                _, opener = self.run_command(command)
                sent = opener.calls[0][0].data
                self.assertIsNone(sent) if command == "status" else self.assertEqual(json.loads(sent), {})

    def test_invalid_and_oversized_credential_files_send_nothing(self):
        for data in (b"x" * 8193, b'[]', b'{"request_id":"ok","token":"PRIVATE"}',
                     b'{"request_id":"ok","token":"a","token":"b"}', b'\xff',
                     json.dumps({**ACCESS, "unknown": 1}).encode()):
            self.lease.write_bytes(data)
            opener = FakeOpener()
            args = client.build_parser().parse_args(["--config", str(self.config), "--lease", str(self.lease), "recover"])
            with self.subTest(length=len(data)), self.assertRaises(client.ClientError) as error:
                client.run(args, opener=opener)
            self.assertNotIn("PRIVATE", str(error.exception))
            self.assertEqual(opener.calls, [])

    def test_remote_rejection_never_falls_back_to_unleased_request(self):
        from io import BytesIO
        import urllib.error
        body = b'{"error":"recover request body must be an empty object"}'
        failure = urllib.error.HTTPError("http://127.0.0.1", 409, "Conflict",
                                         {"Content-Length": str(len(body))}, BytesIO(body))
        opener = FakeOpener(failure, FakeResponse({"recoveryRequired": False}))
        transport = client.ControlClient(type("C", (), {"ui_port": 99, "operator_token": "fake"})(),
                                         opener=opener, access=ACCESS)
        with self.assertRaises(client.ClientError):
            transport.request("/api/recover", method="POST", payload={})
        self.assertEqual(len(opener.calls), 1)

    def test_credentials_are_copied_and_not_attached_to_other_routes(self):
        access = dict(ACCESS); opener = FakeOpener(FakeResponse({}), FakeResponse({}))
        transport = client.ControlClient(type("C", (), {"ui_port": 99, "operator_token": "fake"})(),
                                         opener=opener, access=access)
        access["token"] = "changed"
        transport.request("/api/recover", method="POST", payload={})
        transport.request("/api/stop", method="POST", payload={})
        self.assertEqual(json.loads(opener.calls[0][0].data)["access"], ACCESS)
        self.assertEqual(json.loads(opener.calls[1][0].data), {})


if __name__ == "__main__":
    unittest.main()
