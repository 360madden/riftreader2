import base64
from contextlib import contextmanager, ExitStack
from io import BytesIO
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch


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




class CleanupOutputTests(unittest.TestCase):
    def assert_cleanup_request(self, opener, operation):
        self.assertEqual(len(opener.calls), 1)
        request, _ = opener.calls[0]
        self.assertEqual(request.full_url, f"http://127.0.0.1:49713/api/{operation}")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {})
        self.assertEqual(request.get_header("Authorization"), "Bearer operator-token-012345")
        self.assertEqual(request.get_header("Origin"), "http://127.0.0.1:49713")

    def assert_completed_error(self, error, operation, response, code):
        self.assertEqual(error.code, code)
        self.assertEqual(error.details, {
            "operation": operation, "requestCompleted": True, "result": response,
        })

    def test_existing_output_does_not_prevent_cleanup_or_overwrite(self):
        for operation in ("stop", "release"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = write_config(root)
                output = root / "result.json"
                output.write_bytes(b"existing receipt")
                response = {"released": True}
                opener = FakeOpener(FakeResponse(response))
                with self.assertRaises(client.ClientError) as caught:
                    client.run(parse(config, operation, "--output", str(output)), opener=opener)
                self.assert_cleanup_request(opener, operation)
                self.assert_completed_error(caught.exception, operation, response, "output-exists")
                self.assertEqual(output.read_bytes(), b"existing receipt")

    def test_cleanup_precedes_parent_and_reservation_failures(self):
        for operation in ("stop", "release"):
            for failure in ("missing-parent", "unwritable-parent", "reservation"):
                with self.subTest(operation=operation, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = write_config(root)
                    output = root / "missing" / "nested" / "result.json" if failure == "missing-parent" else root / "result.json"
                    response = {"released": True}
                    opener = FakeOpener(FakeResponse(response))
                    events = []
                    original_reserve = client._reserve_output

                    def reserve(path, **kwargs):
                        self.assert_cleanup_request(opener, operation)
                        events.append("reserve")
                        return original_reserve(path, **kwargs)

                    def denied(*args, **kwargs):
                        self.assert_cleanup_request(opener, operation)
                        events.append(failure)
                        raise PermissionError("injected reservation failure")

                    target = "mkdir" if failure == "unwritable-parent" else "open"
                    with patch.object(client, "_reserve_output", side_effect=reserve):
                        if failure == "missing-parent":
                            with self.assertRaises(client.ClientError) as caught:
                                client.run(parse(config, operation, "--output", str(output)), opener=opener)
                        else:
                            owner = Path if target == "mkdir" else client.os
                            with patch.object(owner, target, side_effect=denied):
                                with self.assertRaises(client.ClientError) as caught:
                                    client.run(parse(config, operation, "--output", str(output)), opener=opener)
                    self.assertEqual(events[0], "reserve")
                    self.assert_completed_error(caught.exception, operation, response, "output-error")
                    self.assertFalse(output.exists())

    def test_post_request_write_flush_fsync_and_fdopen_failures_clean_owned_output(self):
        for operation in ("stop", "release"):
            for failure in ("write", "flush", "fsync", "fdopen"):
                with self.subTest(operation=operation, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = write_config(root)
                    output = root / "result.json"
                    response = {"released": True}
                    opener = FakeOpener(FakeResponse(response))
                    original_fdopen = client.os.fdopen
                    descriptors = []
                    events = []

                    class FailingStream:
                        def __init__(self, stream):
                            self.stream = stream

                        def __enter__(self):
                            return self

                        def __exit__(self, *args):
                            self.stream.close()

                        def write(self, data):
                            events.append("write")
                            if failure == "write":
                                self.stream.write(data[:1])
                                raise OSError("injected write failure")
                            return self.stream.write(data)

                        def flush(self):
                            events.append("flush")
                            if failure == "flush":
                                raise OSError("injected flush failure")
                            return self.stream.flush()

                        def fileno(self):
                            return self.stream.fileno()

                    def fdopen(descriptor, *args, **kwargs):
                        self.assert_cleanup_request(opener, operation)
                        descriptors.append(descriptor)
                        events.append("fdopen")
                        if failure == "fdopen":
                            raise OSError("injected fdopen failure")
                        return FailingStream(original_fdopen(descriptor, *args, **kwargs))

                    def fsync(descriptor):
                        events.append("fsync")
                        if failure == "fsync":
                            raise OSError("injected fsync failure")

                    with patch.object(client.os, "fdopen", side_effect=fdopen), \
                         patch.object(client.os, "fsync", side_effect=fsync):
                        with self.assertRaises(client.ClientError) as caught:
                            client.run(parse(config, operation, "--output", str(output)), opener=opener)
                    self.assert_completed_error(caught.exception, operation, response, "output-error")
                    self.assertEqual(events, ["fdopen", "write", "flush", "fsync"][:("fdopen", "write", "flush", "fsync").index(failure) + 1])
                    self.assertFalse(output.exists())
                    self.assertEqual(len(descriptors), 1)
                    with self.assertRaises(OSError):
                        os.fstat(descriptors[0])

    def test_output_resolution_failure_is_reported_after_cleanup(self):
        for operation in ("stop", "release"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = write_config(root)
                output = root / "result.json"
                response = {"released": True}
                opener = FakeOpener(FakeResponse(response))
                original_resolve = Path.resolve

                def cannot_resolve(path, *args, **kwargs):
                    if path != output:
                        return original_resolve(path, *args, **kwargs)
                    self.assert_cleanup_request(opener, operation)
                    raise OSError("injected resolution failure")

                with patch.object(Path, "resolve", cannot_resolve), \
                     patch.object(client, "_reserve_output", side_effect=AssertionError("must not reserve")):
                    with self.assertRaises(client.ClientError) as caught:
                        client.run(parse(config, operation, "--output", str(output)), opener=opener)
                self.assert_completed_error(caught.exception, operation, response, "output-error")
                self.assertFalse(output.exists())

    def test_write_failure_has_one_cleanup_owner_and_preserves_replacement(self):
        for operation in ("stop", "release", "recover", "arm", "action"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = write_config(root)
                output = root / "result.json"
                capture = root / "capture.json"
                capture.write_text('{"captureId":"reviewed-capture"}', encoding="utf-8")
                arm = root / "arm.json"
                arm.write_text('{"armToken":"private-arm-token"}', encoding="utf-8")
                response = {"released": True, "armToken": "new-arm-token", "expiresInSeconds": 15}
                opener = FakeOpener(FakeResponse(response))
                original_unlink = Path.unlink
                unlinked = []

                def unlink_then_replace(path, *args, **kwargs):
                    result = original_unlink(path, *args, **kwargs)
                    if path == output:
                        unlinked.append(path)
                        path.write_bytes(b"replacement owned by another caller")
                    return result

                arguments = [operation, "--output", str(output)]
                if operation == "arm":
                    arguments.extend(["--capture", str(capture), "--review-note", "reviewed"])
                elif operation == "action":
                    arguments.extend(["--arm", str(arm), "--keys", "w"])
                with patch.object(client.os, "fsync", side_effect=OSError("injected fsync failure")), \
                     patch.object(Path, "unlink", unlink_then_replace), \
                     patch.object(client.os, "close", wraps=client.os.close) as close:
                    with self.assertRaises(client.ClientError) as caught:
                        client.run(parse(config, *arguments), opener=opener)
                self.assertEqual(caught.exception.code, "output-error")
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(unlinked, [output])
                close.assert_called_once()
                self.assertEqual(output.read_bytes(), b"replacement owned by another caller")

    def test_descriptor_close_failure_reports_ack_and_preserves_primary_failure(self):
        for operation in ("stop", "release"):
            for primary in (None, OSError("primary write failure"), KeyboardInterrupt("primary cancellation")):
                with self.subTest(operation=operation, primary=type(primary).__name__), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = write_config(root)
                    output = root / "result.json"
                    response = {"released": True}
                    opener = FakeOpener(FakeResponse(response))
                    original_close = client.os.close
                    descriptors = []

                    def close_then_fail(descriptor):
                        descriptors.append(descriptor)
                        original_close(descriptor)
                        raise OSError("secondary close failure")

                    with patch.object(client.os, "close", side_effect=close_then_fail), \
                         patch.object(client.os, "fsync", side_effect=primary):
                        if isinstance(primary, KeyboardInterrupt):
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                client.run(parse(config, operation, "--output", str(output)), opener=opener)
                            self.assertIs(caught.exception, primary)
                        else:
                            with self.assertRaises(client.ClientError) as caught:
                                client.run(parse(config, operation, "--output", str(output)), opener=opener)
                            self.assert_completed_error(caught.exception, operation, response, "output-error")
                            self.assertIn("primary write failure" if primary else "secondary close failure", str(caught.exception))
                    self.assert_cleanup_request(opener, operation)
                    self.assertEqual(len(descriptors), 1)
                    with self.assertRaises(OSError):
                        os.fstat(descriptors[0])
                    self.assertFalse(output.exists())

    def test_success_schemas_and_request_before_any_output_work(self):
        for operation in ("stop", "release"):
            for save in (False, True):
                with self.subTest(operation=operation, save=save), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = write_config(root)
                    output = root / "new-parent" / "result.json"
                    response = {"released": True}
                    opener = FakeOpener(FakeResponse(response))
                    original_reserve = client._reserve_output

                    def reserve(path, **kwargs):
                        self.assert_cleanup_request(opener, operation)
                        self.assertFalse(path.parent.exists())
                        return original_reserve(path, **kwargs)

                    with patch.object(client, "_reserve_output", side_effect=reserve) as reservation:
                        args = ("--output", str(output)) if save else ()
                        result = client.run(parse(config, operation, *args), opener=opener)
                    expected = {"operation": operation, "result": response}
                    if save:
                        expected["output"] = str(output.resolve())
                        self.assertEqual(json.loads(output.read_text()), response)
                        reservation.assert_called_once()
                    else:
                        reservation.assert_not_called()
                    self.assertEqual(result, expected)
                    self.assert_cleanup_request(opener, operation)

    def test_transport_and_host_errors_leave_output_untouched(self):
        for operation in ("stop", "release"):
            for kind in ("transport", "host"):
                for existing in (False, True):
                    with self.subTest(operation=operation, kind=kind, existing=existing), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        config = write_config(root)
                        output = root / "result.json" if existing else root / "absent" / "result.json"
                        if existing:
                            output.write_bytes(b"existing receipt")
                        details = {"error": "host refused cleanup"}
                        body = json.dumps(details).encode()
                        error = urllib.error.URLError("offline") if kind == "transport" else urllib.error.HTTPError(
                            "http://127.0.0.1:49713/api/stop", 409, "Conflict",
                            {"Content-Length": str(len(body))}, BytesIO(body))
                        opener = FakeOpener(error)
                        with patch.object(client, "_reserve_output", side_effect=AssertionError("must not reserve")):
                            with self.assertRaises(client.ClientError) as caught:
                                client.run(parse(config, operation, "--output", str(output)), opener=opener)
                        self.assert_cleanup_request(opener, operation)
                        self.assertEqual(caught.exception.code, "transport-error" if kind == "transport" else "host-error")
                        self.assertEqual(caught.exception.details, None if kind == "transport" else details)
                        if existing:
                            self.assertEqual(output.read_bytes(), b"existing receipt")
                        else:
                            self.assertFalse(output.parent.exists())

    def test_cli_receipt_error_reports_completed_result_with_redacted_tokens(self):
        for operation in ("stop", "release"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = write_config(root)
                output = root / "result.json"
                output.write_bytes(b"existing receipt")
                response = {"released": False, "recoveryRequired": True,
                            "nested": [{"armToken": "private-result-token",
                                                           "Authorization": "private-result-bearer"}]}
                opener = FakeOpener(FakeResponse(response))
                stdout = type("Console", (), {"buffer": BytesIO()})()
                stderr = type("Console", (), {"buffer": BytesIO()})()
                with patch.object(client.sys, "stdout", stdout), patch.object(client.sys, "stderr", stderr):
                    status = client.main(["--config", str(config), operation, "--output", str(output)], opener=opener)
                self.assertEqual(status, 1)
                self.assertEqual(stdout.buffer.getvalue(), b"")
                failure = json.loads(stderr.buffer.getvalue())
                self.assertFalse(failure["ok"])
                self.assertEqual(failure["error"]["code"], "output-exists")
                self.assertEqual(failure["error"]["details"], {
                    "operation": operation, "requestCompleted": True,
                    "result": {"released": False, "recoveryRequired": True,
                               "nested": [{"armToken": "[redacted]",
                                                               "Authorization": "[redacted]"}]},
                })
                self.assertNotIn(b"private-result-token", stderr.buffer.getvalue())
                self.assertNotIn(b"private-result-bearer", stderr.buffer.getvalue())
                self.assert_cleanup_request(opener, operation)

    def test_recover_keeps_reservation_before_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = write_config(root)
            output = root / "existing.json"
            output.write_bytes(b"existing receipt")
            opener = FakeOpener(FakeResponse({"recovered": True}))
            with self.assertRaises(client.ClientError) as caught:
                client.run(parse(config, "recover", "--output", str(output)), opener=opener)
            self.assertEqual(caught.exception.code, "output-exists")
            self.assertIsNone(caught.exception.details)
            self.assertEqual(opener.calls, [])
            self.assertEqual(output.read_bytes(), b"existing receipt")

    def test_arm_keeps_reservation_before_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = write_config(root)
            capture = root / "capture.json"
            capture.write_text('{"captureId":"reviewed-capture"}', encoding="utf-8")
            output = root / "existing.json"
            output.write_bytes(b"existing receipt")
            opener = FakeOpener(FakeResponse({"armToken": "unused"}))
            with self.assertRaises(client.ClientError) as caught:
                client.run(parse(config, "arm", "--capture", str(capture), "--review-note", "reviewed",
                                 "--output", str(output)), opener=opener)
            self.assertEqual(caught.exception.code, "output-exists")
            self.assertEqual(opener.calls, [])
            self.assertEqual(output.read_bytes(), b"existing receipt")

    def test_managed_cleanup_bypasses_admission_and_lease_with_failing_receipt(self):
        from scripts import ensure_controller
        for operation in ("stop", "release"):
            for prefix in ([], ["--no-auto-start"]):
                with self.subTest(operation=operation, prefix=prefix), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = write_config(root)
                    output = root / "existing.json"
                    output.write_bytes(b"existing receipt")
                    response = {"released": True}
                    opener = FakeOpener(FakeResponse(response))
                    with patch.dict(ensure_controller.CONFIGS, {"lab1": config}, clear=True), \
                         patch.object(ensure_controller, "ensure", side_effect=AssertionError("must not launch")), \
                         patch.object(ensure_controller, "ensure_existing", side_effect=AssertionError("must not inspect")), \
                         patch.object(client, "_read_private_lease", side_effect=AssertionError("must not read lease")), \
                         patch.object(client, "_build_opener", return_value=opener):
                        with self.assertRaises(client.ClientError) as caught:
                            client.run(parse(config, *prefix, "--lease", str(root / "absent-lease"),
                                             operation, "--output", str(output)))
                    self.assert_cleanup_request(opener, operation)
                    self.assert_completed_error(caught.exception, operation, response, "output-exists")


class ManagedAdmissionTests(unittest.TestCase):
    @contextmanager
    def action_admission(self, path, opener, *, lab="lab1", refusal=None, admitted=None):
        from scripts import ensure_controller, ensure_guest_agent
        from scripts.operation_dependencies import DependencyUnavailable
        from tests.test_ensure_guest_agent import _status
        if admitted is None:
            admitted = {"status": _status(armed=True)}
        with ExitStack() as stack:
            stack.enter_context(patch.dict(ensure_controller.CONFIGS, {lab: path}, clear=True))
            verify = stack.enter_context(patch.object(ensure_controller, "ensure_existing",
                                                      side_effect=refusal, return_value=admitted))
            stack.enter_context(patch.object(ensure_controller, "ensure", side_effect=AssertionError("must not recover controller")))
            stack.enter_context(patch.object(ensure_controller, "_launch", side_effect=AssertionError("must not launch")))
            stack.enter_context(patch.object(ensure_guest_agent, "ensure", side_effect=DependencyUnavailable(
                "guest-agent", "connected-but-not-idle")))
            stack.enter_context(patch.object(client, "_build_opener", return_value=opener))
            yield verify

    def test_armed_action_uses_existing_owner_and_preserves_private_envelope(self):
        for lab in ("lab1", "lab2"):
            for prefix in ([], ["--no-auto-start"]):
                with self.subTest(lab=lab, prefix=prefix), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = write_config(root)
                    arm = root / "arm.json"
                    arm.write_text('{"armToken":"private-arm-token"}', encoding="utf-8")
                    access = {"request_id": "reviewed-action", "token": "a" * 64}
                    lease = root / "lease.json"
                    lease.write_text(json.dumps(access), encoding="utf-8")
                    output = root / "result.json"
                    response = {"deliverySucceeded": True, "releaseSucceeded": True, "recoveryRequired": False}
                    opener = FakeOpener(FakeResponse(response))
                    with self.action_admission(path, opener, lab=lab) as verify:
                        result = client.run(parse(path, *prefix, "--lease", str(lease), "action",
                                                  "--arm", str(arm), "--keys", "w,a", "--dx", "10",
                                                  "--output", str(output)))
                        verify.assert_called_once_with(lab)
                    self.assertEqual(result, {"output": str(output.resolve()), "result": response})
                    self.assertEqual(json.loads(output.read_text()), response)
                    self.assertEqual(len(opener.calls), 1)
                    request, _ = opener.calls[0]
                    self.assertEqual(request.method, "POST")
                    self.assertTrue(request.full_url.endswith("/api/action"))
                    self.assertEqual(json.loads(request.data), {"access": access, "payload": {
                        "armToken": "private-arm-token", "action": {
                            "keys": ["w", "a"], "holdMilliseconds": 100, "mouseButton": None,
                            "deltaX": 10, "deltaY": 0, "wheelNotches": 0}}})
                    self.assertEqual(json.loads(lease.read_text()), access)
                    self.assertEqual(json.loads(arm.read_text()), {"armToken": "private-arm-token"})

    def test_default_action_owner_refusal_never_posts_or_starts(self):
        from scripts.operation_dependencies import DependencyUnavailable
        for reason in ("existing-endpoint-missing", "managed-owner-refused"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = write_config(root)
                opener = FakeOpener()
                with self.action_admission(path, opener, refusal=DependencyUnavailable("controller", reason)) as verify:
                    with self.assertRaisesRegex(client.ClientError, reason) as caught:
                        client.run(parse(path, "action", "--arm", str(root / "arm.json"),
                                         "--output", str(root / "out.json")))
                    verify.assert_called_once_with("lab1")
                self.assertEqual(caught.exception.code, "dependency-unavailable")
                self.assertEqual(opener.calls, [])

    def test_action_rejects_unsafe_or_missing_admitted_status_without_post(self):
        from tests.test_ensure_guest_agent import _status
        cases = [{}, {"status": None}, {"status": []}, {"status": {}},
                 {"status": _status(connected=False)}, {"status": _status(coordination="starting")}]
        for key, value in (("desktopInputsDown", ["w"]), ("desktopInputsDown", None),
                           ("busy", True), ("recoveryRequired", True), ("armed", None)):
            status = _status(armed=True)
            status["guest"][key] = value
            cases.append({"status": status})
        for prefix in ([], ["--no-auto-start"]):
            for admitted in cases:
                with self.subTest(prefix=prefix, admitted=admitted), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = write_config(root)
                    opener = FakeOpener()
                    with self.action_admission(path, opener, admitted=admitted) as verify:
                        with self.assertRaises(client.ClientError) as caught:
                            client.run(parse(path, *prefix, "action", "--arm", str(root / "arm.json"),
                                             "--output", str(root / "out.json")))
                        verify.assert_called_once_with("lab1")
                    self.assertEqual(caught.exception.code, "dependency-unavailable")
                    self.assertEqual(opener.calls, [])

    def test_default_action_keeps_local_gates_before_post_and_host_refusal_has_no_fallback(self):
        for gate in ("lease", "arm", "payload", "output", "host"):
            with self.subTest(gate=gate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = write_config(root)
                arm = root / "arm.json"
                arm.write_text(json.dumps({"armToken": "" if gate == "arm" else "private-arm-token"}), encoding="utf-8")
                output = root / "out.json"
                if gate == "output":
                    output.write_text("existing receipt", encoding="utf-8")
                extra = []
                if gate == "lease":
                    lease = root / "lease.json"
                    lease.write_text('{"request_id":"reviewed-action","token":"bad"}', encoding="utf-8")
                    extra = ["--lease", str(lease)]
                opener = FakeOpener()
                if gate == "host":
                    body = b'{"error":"armed action refused","recoveryRequired":true}'
                    opener.responses.append(urllib.error.HTTPError(
                        "http://127.0.0.1:49713/api/action", 409, "Conflict",
                        {"Content-Length": str(len(body))}, BytesIO(body)))
                with self.action_admission(path, opener) as verify:
                    with self.assertRaises(client.ClientError) as caught:
                        client.run(parse(path, *extra, "action", "--arm", str(arm),
                                         "--keys", "invalid-key" if gate == "payload" else "w",
                                         "--output", str(output)))
                    verify.assert_called_once_with("lab1")
                self.assertEqual(caught.exception.code, "host-error" if gate == "host" else
                                 "output-exists" if gate == "output" else "input-error")
                self.assertEqual(len(opener.calls), 1 if gate == "host" else 0)
                if gate == "output":
                    self.assertEqual(output.read_text(), "existing receipt")
                else:
                    self.assertFalse(output.exists())

    def test_default_capture_and_arm_keep_guest_recovery(self):
        from scripts import ensure_controller, ensure_guest_agent
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(Path(directory))
            with patch.dict(ensure_controller.CONFIGS, {"lab1": path}, clear=True), \
                 patch.object(ensure_controller, "ensure", side_effect=AssertionError("must not launch")), \
                 patch.object(ensure_controller, "ensure_existing", side_effect=AssertionError("must use guest preflight")), \
                 patch.object(ensure_guest_agent, "ensure") as guest, \
                 patch.object(client, "ControlClient"), \
                 patch.object(client, "_capture", return_value={}), patch.object(client, "_arm", return_value={}):
                client.run(parse(path, "capture", "--output", "capture"))
                client.run(parse(path, "arm", "--capture", "capture", "--review-note", "review", "--output", "arm"))
                self.assertEqual(guest.call_args_list, [unittest.mock.call("lab1"), unittest.mock.call("lab1")])

    def test_cleanup_bypasses_checks_and_never_launches(self):
        from unittest.mock import patch
        from scripts import ensure_controller
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(Path(directory))
            with patch.dict(ensure_controller.CONFIGS, {"lab1": path}, clear=True), \
                 patch.object(ensure_controller, "ensure", side_effect=AssertionError("must not start")), \
                 patch.object(ensure_controller, "ensure_existing", side_effect=AssertionError("must not inspect")), \
                 patch.object(client, "ControlClient") as control:
                control.return_value.request.return_value = {"ok": True}
                for operation in ("stop", "release"):
                    for prefix in ([], ["--no-auto-start"]):
                        client.run(parse(path, *prefix, operation))
                self.assertEqual(control.return_value.request.call_count, 4)

    def test_no_auto_start_protected_operations_verify_existing_owner(self):
        from unittest.mock import patch
        from scripts import ensure_controller
        from scripts.operation_dependencies import DependencyUnavailable
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(Path(directory))
            with patch.dict(ensure_controller.CONFIGS, {"lab1": path}, clear=True), \
                 patch.object(ensure_controller, "ensure") as launch, \
                 patch.object(ensure_controller, "ensure_existing", side_effect=DependencyUnavailable("controller", "managed-owner-refused")) as verify, \
                 patch.object(client, "ControlClient") as control:
                for args in (("recover",), ("capture", "--output", str(Path(directory) / "capture")),
                             ("arm", "--capture", "capture", "--review-note", "review", "--output", "arm"),
                             ("action", "--arm", "arm", "--output", "out")):
                    with self.assertRaisesRegex(client.ClientError, "managed-owner-refused"):
                        client.run(parse(path, "--no-auto-start", *args))
                self.assertEqual(verify.call_count, 4)
                launch.assert_not_called()
                control.assert_not_called()

    def test_status_defaults_to_ensure_but_no_auto_is_diagnostic(self):
        from unittest.mock import patch
        from scripts import ensure_controller
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(Path(directory))
            with patch.dict(ensure_controller.CONFIGS, {"lab1": path}, clear=True), \
                 patch.object(ensure_controller, "ensure") as ensure, \
                 patch.object(ensure_controller, "ensure_existing") as existing, \
                 patch.object(client, "ControlClient") as control:
                control.return_value.request.return_value = {"host": {}}
                client.run(parse(path, "status"))
                ensure.assert_called_once_with("lab1")
                client.run(parse(path, "--no-auto-start", "status"))
                ensure.assert_called_once_with("lab1")
                existing.assert_not_called()


if __name__ == "__main__":
    unittest.main()
