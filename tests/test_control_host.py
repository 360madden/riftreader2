import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "control_host.py"
SPEC = importlib.util.spec_from_file_location("control_host", SCRIPT)
host = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = host
SPEC.loader.exec_module(host)


def config(root, agent_port=0, ui_port=0):
    return host.HostConfig(
        "127.0.0.1", agent_port, ui_port, "127.0.0.1", "RIFT-LAB-1",
        "guest-token-0123456789", "operator-token-012345", Path(root),
    )


def bmp_bytes():
    image = bytearray(b"BM" + b"\0" * 64)
    image[18:26] = (800).to_bytes(4, "little", signed=True) + (600).to_bytes(4, "little", signed=True)
    return bytes(image)


class FakeGuest:
    def __init__(self, port, token="guest-token-0123456789", machine="RIFT-LAB-1"):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.stream = self.socket.makefile("rb")
        self.send({"type":"hello", "token":token, "instanceId":"guest-one", "machineName":machine})

    def send(self, value):
        self.socket.sendall(host.encode_frame(value))

    def receive(self):
        return host.read_frame(self.stream)

    def respond(self, command, payload):
        self.send({"type":"response", "id":command["id"], "payload":payload})

    def close(self):
        self.stream.close()
        self.socket.close()


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.journal = host.EvidenceJournal(Path(self.temporary.name))
        self.gateway = host.AgentGateway(config(self.temporary.name), self.journal)
        self.gateway.start()
        self.addCleanup(self.gateway.close)

    def wait_connected(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.gateway.local_status()["connected"]:
                return
            time.sleep(.01)
        self.fail("guest did not connect")

    def test_authentication_and_command_response_correlation(self):
        bad = FakeGuest(self.gateway.port, token="wrong-token-but-long")
        self.assertEqual(bad.receive()["type"], "error")
        bad.close()

        guest = FakeGuest(self.gateway.port)
        self.addCleanup(guest.close)
        self.assertEqual(guest.receive(), {"type":"welcome"})
        self.wait_connected()
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.gateway.command("status", {})))
        thread.start()
        command = guest.receive()
        self.assertEqual(command["sequence"], 1)
        self.assertEqual(command["operation"], "status")
        guest.respond(command, {"ready": True})
        thread.join(2)
        self.assertEqual(result, {"ready": True})

    def test_release_can_pass_an_outstanding_action_and_sequences_stay_ordered(self):
        guest = FakeGuest(self.gateway.port)
        self.addCleanup(guest.close)
        guest.receive(); self.wait_connected()
        results = {}
        action = threading.Thread(target=lambda: results.update(action=self.gateway.command("action", {
            "armToken":"a", "action":{}
        })))
        action.start()
        first = guest.receive()
        self.assertEqual(first["operation"], "action")
        release = threading.Thread(target=lambda: results.update(release=self.gateway.command("release", {})))
        release.start()
        second = guest.receive()
        self.assertEqual(second["operation"], "release")
        self.assertEqual((first["sequence"], second["sequence"]), (1, 2))
        guest.respond(second, {"released":True, "armed":True, "recoveryRequired":False})
        guest.respond(first, {"cancelled":True})
        action.join(2); release.join(2)
        self.assertTrue(results["release"]["released"])
        self.assertTrue(results["action"]["cancelled"])

    def test_capture_is_retained_and_image_and_tokens_are_not_journaled(self):
        guest = FakeGuest(self.gateway.port)
        self.addCleanup(guest.close)
        guest.receive(); self.wait_connected()
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.gateway.capture()))
        thread.start()
        command = guest.receive()
        guest.respond(command, {
            "captureId":"capture-1", "imageFormat":"bmp",
            "imageBase64":base64.b64encode(bmp_bytes()).decode(),
            "target":{"pid":42}, "armToken":"must-not-be-logged"
        })
        thread.join(2)
        self.assertTrue(Path(result["artifact"]["path"]).exists())
        journal = self.journal.path.read_text(encoding="utf-8")
        self.assertNotIn(base64.b64encode(bmp_bytes()).decode(), journal)
        self.assertNotIn("must-not-be-logged", journal)
        self.assertIn(result["artifact"]["sha256"], journal)

    def test_request_timeout_closes_transport_without_retry(self):
        guest = FakeGuest(self.gateway.port)
        self.addCleanup(guest.close)
        guest.receive(); self.wait_connected()
        failure = {}
        previous_timeout = host.REQUEST_TIMEOUT_SECONDS
        host.REQUEST_TIMEOUT_SECONDS = .05
        try:
            def request():
                try:
                    self.gateway.command("status", {})
                except BaseException as error:
                    failure["error"] = error
            thread = threading.Thread(target=request)
            thread.start()
            command = guest.receive()
            self.assertEqual(command["sequence"], 1)
            thread.join(2)
        finally:
            host.REQUEST_TIMEOUT_SECONDS = previous_timeout
        self.assertIsInstance(failure.get("error"), host.ControlHostError)
        self.assertIn("deadline", str(failure["error"]))
        with self.assertRaises(EOFError):
            guest.receive()
        self.assertFalse(self.gateway.local_status()["connected"])


class ValidationTests(unittest.TestCase):
    def test_action_contract_accepts_bounds_and_rejects_invalid_values(self):
        valid = {"armToken":"arm", "action":{
            "keys":["w","a"], "holdMilliseconds":20, "mouseButton":"right",
            "deltaX":-200, "deltaY":200, "wheelNotches":0,
        }}
        self.assertEqual(host.validate_action_payload(valid)["action"]["keys"], ["w","a"])
        for mutate in (
            lambda value: value["action"].update(holdMilliseconds=251),
            lambda value: value["action"].update(deltaX=201),
            lambda value: value["action"].update(keys=["w","w"]),
            lambda value: value["action"].update(wheelNotches=2),
        ):
            value = json.loads(json.dumps(valid)); mutate(value)
            with self.subTest(value=value), self.assertRaises(host.ControlHostError):
                host.validate_action_payload(value)
        for keys in (["w", "s"], ["a", "d"], ["q", "e"]):
            conflict = json.loads(json.dumps(valid))
            conflict["action"]["keys"] = keys
            with self.subTest(keys=keys), self.assertRaisesRegex(
                    host.ControlHostError, "opposing movement"):
                host.validate_action_payload(conflict)

        wheel = {"armToken":"arm", "action":{
            "keys":[], "holdMilliseconds":0, "mouseButton":None,
            "deltaX":0, "deltaY":0, "wheelNotches":-1,
        }}
        self.assertEqual(host.validate_action_payload(wheel), wheel)
        for field, value in (("keys", ["w"]), ("holdMilliseconds", 20),
                             ("mouseButton", "right"), ("deltaX", 1)):
            conflicting = json.loads(json.dumps(wheel))
            conflicting["action"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    host.ControlHostError, "wheel input must be standalone"):
                host.validate_action_payload(conflicting)

    def test_frame_rejects_duplicate_properties_and_oversize(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close); self.addCleanup(right.close)
        stream = left.makefile("rb")
        self.addCleanup(stream.close)
        right.sendall(b'{"type":"x","type":"y"}\n')
        with self.assertRaisesRegex(host.ControlHostError, "duplicate"):
            host.read_frame(stream)
        left2, right2 = socket.socketpair()
        self.addCleanup(left2.close); self.addCleanup(right2.close)
        stream2 = left2.makefile("rb")
        self.addCleanup(stream2.close)
        right2.sendall(b"x" * (host.MAX_FRAME_BYTES + 2))
        with self.assertRaisesRegex(host.ControlHostError, str(host.MAX_FRAME_BYTES)):
            host.read_frame(stream2)

        left3, right3 = socket.socketpair()
        self.addCleanup(left3.close); self.addCleanup(right3.close)
        stream3 = left3.makefile("rb")
        self.addCleanup(stream3.close)
        right3.sendall(b"x" * (host.MAX_HELLO_BYTES + 2))
        with self.assertRaisesRegex(host.ControlHostError, str(host.MAX_HELLO_BYTES)):
            host.read_frame(stream3, host.MAX_HELLO_BYTES)

    def test_loaded_config_requires_rfc1918_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            value = {
                "schemaVersion":1, "bindAddress":"192.168.80.1",
                "agentPort":49712, "uiPort":49713,
                "guestAddress":"192.168.80.128", "expectedMachineName":"RIFT-LAB-1",
                "token":"guest-token-0123456789", "operatorToken":"operator-token-012345",
                "outputDirectory":"artifacts",
            }
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(host.HostConfig.load(path).bind_address, "192.168.80.1")
            value["bindAddress"] = "127.0.0.1"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(host.ControlHostError, "RFC 1918"):
                host.HostConfig.load(path)


class FakeGateway:
    def __init__(self):
        self.calls = []
    def local_status(self): return {"connected":False}
    def command(self, operation, payload):
        self.calls.append((operation,payload))
        return {"armToken":"arm","expiresInSeconds":15} if operation == "arm" else {"ok":True}
    def capture(self): self.calls.append(("capture",{})); return {"captureId":"c","imageFormat":"bmp","imageBase64":"Qk0=","target":{"pid":1}}


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.gateway = FakeGateway()
        self.server = host.ControlHttpServer(("127.0.0.1", 0), self.gateway, config(self.temporary.name), b"<html></html>")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"

    def request(self, method, path, body=None, token="operator-token-012345", origin="default", host_header=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        headers = {"Authorization":f"Bearer {token}"}
        if host_header is not None:
            headers["Host"] = host_header
        if origin is not None:
            headers["Origin"] = self.origin if origin == "default" else origin
        data = None if body is None else json.dumps(body)
        if data is not None: headers["Content-Type"] = "application/json"
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse(); value = json.loads(response.read())
        connection.close(); return response.status, value

    def test_api_requires_exact_origin_and_bearer(self):
        self.assertEqual(self.request("GET", "/api/status", origin="http://localhost:1")[0], 403)
        self.assertEqual(self.request("GET", "/api/status", host_header=f"localhost:{self.port}")[0], 403)
        self.assertEqual(self.request("GET", "/api/status", token="wrong")[0], 401)
        self.assertEqual(self.request("GET", "/api/status", origin=None)[0], 200)
        self.assertEqual(self.request("GET", "/api/status")[0], 200)

    def test_arm_action_and_stop_validation(self):
        status, _ = self.request("POST", "/api/arm", {"captureId":"c1","reviewNote":"In world, chat closed."})
        self.assertEqual(status, 200)
        self.assertEqual(self.gateway.calls[-1][0], "arm")
        invalid, _ = self.request("POST", "/api/action", {"armToken":"x","action":{
            "keys":["x"], "holdMilliseconds":100, "mouseButton":None,
            "deltaX":0,"deltaY":0,"wheelNotches":0}})
        self.assertEqual(invalid, 409)
        stopped, _ = self.request("POST", "/api/stop", {})
        self.assertEqual(stopped, 200)
        released, _ = self.request("POST", "/api/release", {})
        self.assertEqual(released, 200)
        self.assertEqual(self.gateway.calls[-1][0], "release")
        recovered, _ = self.request("POST", "/api/recover", {})
        self.assertEqual(recovered, 200)
        self.assertEqual(self.gateway.calls[-1][0], "recover")


class BootstrapTests(unittest.TestCase):
    def test_only_authenticated_exact_bundle_is_served_with_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "agent.exe"; bundle.write_bytes(b"published-agent")
            cfg = host.HostConfig(
                "127.0.0.1", 1, 1, "127.0.0.1", "RIFT-LAB-1",
                "guest-token-0123456789", "operator-token-012345", Path(directory), bundle, 0)
            server = host.BootstrapHttpServer(("127.0.0.1", 0), cfg)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
            connection.request("GET", "/bundle", headers={"Authorization":"Bearer guest-token-0123456789"})
            response = connection.getresponse(); data = response.read(); connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(data, b"published-agent")
            self.assertEqual(response.getheader("X-Content-SHA256"), hashlib.sha256(data).hexdigest().upper())


class PanelContractTests(unittest.TestCase):
    def test_control_result_and_late_response_guards_are_explicit(self):
        panel = (Path(__file__).parents[1] / "scripts" / "control_panel.html").read_text(
            encoding="utf-8")
        self.assertIn("function show(value, state='neutral')", panel)
        self.assertIn("typeof value.result === 'object' ? value.result : null", panel)
        self.assertIn("outcome.deliverySucceeded === true", panel)
        self.assertIn("outcome.releaseSucceeded === true", panel)
        self.assertIn("value.recoveryRequired === false", panel)
        self.assertIn("outcome && outcome.cancelled === true", panel)
        self.assertGreaterEqual(panel.count("generation === controlGeneration"), 8)

    def test_browser_diagnostics_mark_unsafe_integers_and_capture_state(self):
        panel = (Path(__file__).parents[1] / "scripts" / "control_panel.html").read_text(
            encoding="utf-8")
        self.assertIn("Number.isInteger(value) && !Number.isSafeInteger(value)", panel)
        self.assertIn("[unsafe integer in browser; use retained JSON evidence]", panel)
        self.assertIn("JSON.stringify(printableDiagnostic(value), null, 2)", panel)
        self.assertIn("screen.removeAttribute('src')", panel)
        self.assertIn("screen.alt = 'No current reviewed capture'", panel)
        self.assertIn("screen.alt = 'Fresh control capture awaiting operator review'", panel)


if __name__ == "__main__":
    unittest.main()
