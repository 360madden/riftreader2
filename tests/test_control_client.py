import base64
from io import BytesIO
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error


SCRIPT = Path(__file__).parents[1] / "scripts" / "control_client.py"
SPEC = importlib.util.spec_from_file_location("control_client", SCRIPT)
client = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client
SPEC.loader.exec_module(client)


class FakeResponse:
    def __init__(self, value, *, headers=None):
        data = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
        self.stream = BytesIO(data)
        self.headers = {"Content-Length": str(len(data)), **(headers or {})}

    def read(self, count=-1):
        return self.stream.read(count)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def write_config(root: Path) -> Path:
    path = root / "host.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "bindAddress": "192.168.80.1",
        "agentPort": 49712,
        "uiPort": 49713,
        "guestAddress": "192.168.80.128",
        "expectedMachineName": "RIFT-LAB-1",
        "token": "guest-token-0123456789",
        "operatorToken": "operator-token-012345",
        "outputDirectory": "artifacts",
    }), encoding="utf-8")
    return path


def parse(config: Path, *arguments):
    return client.build_parser().parse_args(["--config", str(config), *arguments])


class RequestTests(unittest.TestCase):
    def test_status_uses_loopback_bearer_origin_and_one_request(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = write_config(Path(directory))
            opener = FakeOpener(FakeResponse({"host":{"connected":False}}))
            result = client.run(parse(config_path, "status"), opener=opener)
            self.assertFalse(result["host"]["connected"])
            self.assertEqual(len(opener.calls), 1)
            request, timeout = opener.calls[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:49713/api/status")
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer operator-token-012345")
            self.assertEqual(request.get_header("Origin"), "http://127.0.0.1:49713")
            self.assertEqual(timeout, 10.0)

    def test_nested_host_error_is_explicit(self):
        body = json.dumps({"error":"guest refused action","nested":{"error":"recovery-required"}}).encode()
        error = urllib.error.HTTPError(
            "http://127.0.0.1:49713/api/action", 409, "Conflict",
            {"Content-Length":str(len(body))}, BytesIO(body),
        )
        fake_config = type("Config", (), {"ui_port":49713, "operator_token":"secret"})()
        transport = client.ControlClient(fake_config, FakeOpener(error))
        with self.assertRaises(client.ClientError) as caught:
            transport.request("/api/action", method="POST", payload={})
        self.assertEqual(caught.exception.code, "host-error")
        self.assertEqual(str(caught.exception), "guest refused action")
        self.assertEqual(caught.exception.details["nested"]["error"], "recovery-required")

    def test_declared_oversize_response_is_rejected(self):
        response = FakeResponse(b"{}", headers={"Content-Length":str(client.MAX_RESPONSE_BYTES + 1)})
        with self.assertRaisesRegex(client.ClientError, "16 MiB"):
            client._read_response(response)


class ArtifactTests(unittest.TestCase):
    def test_capture_saves_verified_bmp_and_metadata_without_base64(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config_path = write_config(root)
            image = b"BM" + b"\0" * 64
            digest = hashlib.sha256(image).hexdigest().upper()
            response = {
                "captureId":"capture-one", "imageFormat":"bmp",
                "imageBase64":base64.b64encode(image).decode(),
                "target":{"pid":42},
                "artifact":{"path":"host.bmp","sha256":digest,"byteLength":len(image)},
            }
            opener = FakeOpener(FakeResponse(response))
            output = root / "capture"
            result = client.run(parse(config_path, "capture", "--output", str(output)), opener=opener)
            self.assertEqual((output / "image.bmp").read_bytes(), image)
            metadata_text = (output / "capture.json").read_text(encoding="utf-8")
            self.assertNotIn(response["imageBase64"], metadata_text)
            metadata = json.loads(metadata_text)
            self.assertEqual(metadata["savedImage"]["sha256"], digest)
            self.assertEqual(result["captureId"], "capture-one")

    def test_capture_hash_mismatch_removes_reserved_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config_path = write_config(root)
            image = b"BMbad"
            response = {
                "captureId":"capture-one", "imageFormat":"bmp",
                "imageBase64":base64.b64encode(image).decode(), "target":{"pid":42},
                "artifact":{"sha256":"0" * 64,"byteLength":len(image)},
            }
            output = root / "capture"
            with self.assertRaisesRegex(client.ClientError, "do not match"):
                client.run(parse(config_path, "capture", "--output", str(output)),
                           opener=FakeOpener(FakeResponse(response)))
            self.assertFalse(output.exists())

    def test_arm_token_is_private_artifact_and_console_redacts_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config_path = write_config(root)
            capture = root / "capture.json"
            capture.write_text('{"captureId":"capture-one"}', encoding="utf-8")
            output = root / "arm.json"
            result = client.run(parse(
                config_path, "arm", "--capture", str(capture),
                "--review-note", "RIFT in world and chat closed", "--output", str(output),
            ), opener=FakeOpener(FakeResponse({"armToken":"private-arm-token","expiresInSeconds":15})))
            self.assertEqual(json.loads(output.read_text())["armToken"], "private-arm-token")
            self.assertEqual(result["armToken"], "[redacted]")
            redacted = client._redact_for_console({
                "operatorToken":"operator-secret", "nested":{"armToken":"arm-secret"},
            })
            self.assertNotIn("secret", json.dumps(redacted))

    def test_arm_rejects_capture_id_changed_after_review_without_live_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            capture.write_text('{"captureId":"replaced-capture"}', encoding="utf-8")
            output = root / "arm.json"
            config = type("Config", (), {"ui_port":49713, "operator_token":"secret"})()
            opener = FakeOpener(FakeResponse({"armToken":"unused", "expiresInSeconds":15}))
            transport = client.ControlClient(config, opener)
            with self.assertRaisesRegex(client.ClientError,
                                        "capture ID differs from reviewed session"):
                client._arm(transport, capture, "RIFT in world and chat closed",
                            output, expected_capture_id="reviewed-capture")
            self.assertEqual(opener.calls, [])
            self.assertFalse(output.exists())

    def test_arm_accepts_the_exact_reviewed_capture_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "capture.json"
            capture.write_text('{"captureId":"reviewed-capture"}', encoding="utf-8")
            output = root / "arm.json"
            config = type("Config", (), {"ui_port":49713, "operator_token":"secret"})()
            opener = FakeOpener(FakeResponse({"armToken":"private-token", "expiresInSeconds":15}))
            transport = client.ControlClient(config, opener)
            result = client._arm(transport, capture, "RIFT in world and chat closed",
                                 output, expected_capture_id="reviewed-capture")
            self.assertTrue(result["armed"])
            self.assertEqual(len(opener.calls), 1)
            self.assertEqual(json.loads(opener.calls[0][0].data)["captureId"], "reviewed-capture")
            self.assertEqual(json.loads(output.read_text())["captureId"], "reviewed-capture")

    def test_existing_action_output_prevents_live_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config_path = write_config(root)
            arm = root / "arm.json"
            arm.write_text('{"armToken":"private-arm-token"}', encoding="utf-8")
            output = root / "result.json"; output.write_text("existing", encoding="utf-8")
            opener = FakeOpener(FakeResponse({"deliverySucceeded":True}))
            with self.assertRaisesRegex(client.ClientError, "already exists"):
                client.run(parse(
                    config_path, "action", "--arm", str(arm), "--keys", "w",
                    "--output", str(output),
                ), opener=opener)
            self.assertEqual(opener.calls, [])
            self.assertEqual(output.read_text(), "existing")

    def test_action_is_validated_once_and_result_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config_path = write_config(root)
            arm = root / "arm.json"
            arm.write_text('{"armToken":"private-arm-token"}', encoding="utf-8")
            output = root / "result.json"
            response = {"deliverySucceeded":True,"releaseSucceeded":True,"recoveryRequired":False}
            opener = FakeOpener(FakeResponse(response))
            result = client.run(parse(
                config_path, "action", "--arm", str(arm), "--keys", "w,a",
                "--dx", "10", "--output", str(output),
            ), opener=opener)
            self.assertEqual(json.loads(output.read_text()), response)
            self.assertEqual(result["result"], response)
            request = opener.calls[0][0]
            sent = json.loads(request.data)
            self.assertEqual(sent["action"]["keys"], ["w", "a"])
            self.assertEqual(sent["action"]["deltaX"], 10)


if __name__ == "__main__":
    unittest.main()
