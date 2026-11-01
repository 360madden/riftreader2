#!/usr/bin/env python3
"""Machine-readable client for the repo-owned supervised control host."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.request


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10.0


def _load_host_module():
    path = Path(__file__).with_name("control_host.py")
    spec = importlib.util.spec_from_file_location("rr2_control_host_client_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HOST = _load_host_module()


class ClientError(RuntimeError):
    def __init__(self, code: str, message: str, details: object | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _build_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n").encode("utf-8")


def _read_response(response) -> dict:
    length = response.headers.get("Content-Length")
    if length is not None:
        try:
            declared = int(length)
        except (TypeError, ValueError) as error:
            raise ClientError("invalid-response", "response Content-Length is invalid") from error
        if declared < 0 or declared > MAX_RESPONSE_BYTES:
            raise ClientError("response-too-large", "response exceeds 16 MiB")
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ClientError("response-too-large", "response exceeds 16 MiB")
    try:
        value = HOST.decode_json(data)
    except HOST.ControlHostError as error:
        raise ClientError("invalid-response", str(error)) from error
    if not isinstance(value, dict):
        raise ClientError("invalid-response", "response JSON must be an object")
    return value


class ControlClient:
    def __init__(self, config, opener=None, *, access=None):
        self.config = config
        self.base_url = f"http://127.0.0.1:{config.ui_port}"
        self.opener = opener or _build_opener()
        try:
            self.access = HOST.validate_control_access(access) if access is not None else None
        except HOST.ControlHostError:
            raise ClientError("input-error", "invalid private control lease") from None

    def request(self, path: str, *, method: str, payload: dict | None = None) -> dict:
        if (self.access is not None and method == "POST"
                and path in {"/api/" + name for name in HOST.PROTECTED_CONTROL_OPERATIONS}):
            payload = {"access": dict(self.access), "payload": payload}
        data = None if payload is None else _json_bytes(payload)
        headers = {
            "Authorization": f"Bearer {self.config.operator_token}",
            "Origin": self.base_url,
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method,
        )
        try:
            with self.opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return _read_response(response)
        except urllib.error.HTTPError as error:
            try:
                try:
                    details = _read_response(error)
                except ClientError:
                    details = None
            finally:
                error.close()
            message = details.get("error") if isinstance(details, dict) else None
            raise ClientError(
                "host-error", message or f"control host returned HTTP {error.code}", details
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ClientError("transport-error", str(error.reason if hasattr(error, "reason") else error)) from error


def _read_json(path: Path, description: str) -> dict:
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise ClientError("input-error", f"cannot read {description}: {error}") from error
    if len(data) > MAX_RESPONSE_BYTES:
        raise ClientError("input-error", f"{description} exceeds 16 MiB")
    try:
        value = HOST.decode_json(data)
    except HOST.ControlHostError as error:
        raise ClientError("input-error", f"invalid {description}: {error}") from error
    if not isinstance(value, dict):
        raise ClientError("input-error", f"{description} must contain one JSON object")
    return value


def _read_private_lease(path: Path) -> dict:
    """Read a bounded private pair or queue dispatch grant; never acquire or renew."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(8193)
        if len(data) > 8192:
            raise ValueError()
        value = HOST.decode_json(data)
        pair = {"request_id", "token"}
        grant = pair | {"owner", "track", "lease", "expires_ms", "deadline_ms"}
        if not isinstance(value, dict) or set(value) not in (pair, grant):
            raise ValueError()
        return HOST.validate_control_access({key: value[key] for key in pair})
    except (OSError, ValueError, HOST.ControlHostError):
        # Parse exceptions can include private property names or filesystem paths.
        raise ClientError("input-error", "private control lease must be valid JSON, at most 8 KiB") from None


def _reserve_output(path: Path, *, private: bool = False):
    path = Path(path)
    try:
        path.parent.mkdir(parents=False, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
    except FileExistsError as error:
        raise ClientError("output-exists", f"output already exists: {path}") from error
    except OSError as error:
        raise ClientError("output-error", f"cannot create output: {error}") from error
    return path, descriptor


def _write_reserved_json(path: Path, descriptor: int, value: object, *, private: bool = False):
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        if private:
            os.chmod(path, 0o600)
    except OSError as error:
        try:
            path.unlink()
        except OSError:
            pass
        raise ClientError("output-error", f"cannot write output: {error}") from error
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _write_new_json(path: Path, value: object, *, private: bool = False):
    path, descriptor = _reserve_output(path, private=private)
    _write_reserved_json(path, descriptor, value, private=private)


def _redact_for_console(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if "token" in key.casefold()
            else _redact_for_console(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_for_console(item) for item in value]
    return value


def _print(value: object):
    sys.stdout.buffer.write(_json_bytes(_redact_for_console(value)))
    sys.stdout.buffer.flush()


def _capture(client: ControlClient, output: Path) -> dict:
    output = Path(output)
    if output.exists():
        raise ClientError("output-exists", f"output directory already exists: {output}")
    try:
        output.mkdir(parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ClientError("output-exists", f"output directory already exists: {output}") from error
    except OSError as error:
        raise ClientError("output-error", f"cannot create output directory: {error}") from error
    image_path = None
    capture_path = None
    try:
        response = client.request("/api/capture", method="POST", payload={})
        required = {"captureId", "imageFormat", "imageBase64", "target", "artifact"}
        if not required.issubset(response) or response.get("imageFormat") != "bmp":
            raise ClientError("invalid-response", "capture response is incomplete or is not BMP")
        if not isinstance(response["captureId"], str) or not isinstance(response["target"], dict):
            raise ClientError("invalid-response", "capture identity or target is invalid")
        artifact = response["artifact"]
        if not isinstance(artifact, dict):
            raise ClientError("invalid-response", "capture artifact metadata is invalid")
        try:
            image = base64.b64decode(response["imageBase64"], validate=True)
        except (TypeError, ValueError, binascii.Error) as error:
            raise ClientError("invalid-response", "capture imageBase64 is invalid") from error
        digest = hashlib.sha256(image).hexdigest().upper()
        if (not image.startswith(b"BM") or artifact.get("sha256") != digest
                or artifact.get("byteLength") != len(image)):
            raise ClientError("invalid-response", "capture bytes do not match host artifact metadata")
        image_path = output / "image.bmp"
        with image_path.open("xb") as stream:
            stream.write(image)
            stream.flush()
            os.fsync(stream.fileno())
        metadata = {key: value for key, value in response.items() if key != "imageBase64"}
        metadata["savedImage"] = {
            "path": "image.bmp", "sha256": digest, "byteLength": len(image),
        }
        capture_path = output / "capture.json"
        _write_new_json(capture_path, metadata)
    except BaseException:
        for created in (capture_path, image_path):
            if created is not None:
                try:
                    created.unlink()
                except OSError:
                    pass
        if output.exists():
            try:
                output.rmdir()
            except OSError:
                pass
        raise
    return {
        "captureId": response["captureId"],
        "capture": str(capture_path.resolve()),
        "image": str(image_path.resolve()),
    }


def _arm(client: ControlClient, capture_path: Path, review_note: str, output: Path,
         *, expected_capture_id: str | None = None) -> dict:
    capture = _read_json(capture_path, "capture artifact")
    capture_id = capture.get("captureId")
    if not isinstance(capture_id, str):
        raise ClientError("input-error", "capture artifact has no captureId")
    if expected_capture_id is not None and (
            not isinstance(expected_capture_id, str) or capture_id != expected_capture_id):
        raise ClientError("input-error", "capture ID differs from reviewed session")
    output, descriptor = _reserve_output(Path(output), private=True)
    try:
        response = client.request("/api/arm", method="POST", payload={
            "captureId": capture_id, "reviewNote": review_note,
        })
        token = response.get("armToken")
        if not isinstance(token, str) or not token or response.get("expiresInSeconds") != 15:
            raise ClientError("invalid-response", "host returned an invalid arm result")
        artifact = {
            "schemaVersion": 1, "captureId": capture_id, "armToken": token,
            "expiresInSeconds": 15,
            "savedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _write_reserved_json(output, descriptor, artifact, private=True)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return {
        "armed": True, "expiresInSeconds": 15,
        "output": str(Path(output).resolve()), "armToken": "[redacted]",
    }


def _parse_keys(text: str) -> list[str]:
    if text == "":
        return []
    return [item.strip().lower() for item in text.split(",")]


def _action(client: ControlClient, args) -> dict:
    arm = _read_json(args.arm, "arm artifact")
    token = arm.get("armToken")
    if not isinstance(token, str) or not token:
        raise ClientError("input-error", "arm artifact has no armToken")
    payload = {
        "armToken": token,
        "action": {
            "keys": _parse_keys(args.keys), "holdMilliseconds": args.hold_ms,
            "mouseButton": args.mouse_button, "deltaX": args.dx,
            "deltaY": args.dy, "wheelNotches": args.wheel,
        },
    }
    if getattr(args, "click_target", None) is not None:
        payload["action"]["clickTarget"] = dict(zip(("x", "y", "width", "height"), args.click_target))
    try:
        payload = HOST.validate_action_payload(payload)
    except HOST.ControlHostError as error:
        raise ClientError("input-error", str(error)) from error
    output, descriptor = _reserve_output(Path(args.output))
    try:
        response = client.request("/api/action", method="POST", payload=payload)
        _write_reserved_json(output, descriptor, response)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return {"output": str(output.resolve()), "result": response}


def _simple(client: ControlClient, operation: str, output: Path | None) -> dict:
    if output is not None:
        output, descriptor = _reserve_output(Path(output))
        try:
            response = client.request(f"/api/{operation}", method="POST", payload={})
            _write_reserved_json(output, descriptor, response)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                output.unlink()
            except OSError:
                pass
            raise
        return {"operation": operation, "output": str(output.resolve()), "result": response}
    response = client.request(f"/api/{operation}", method="POST", payload={})
    return {"operation": operation, "result": response}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--no-auto-start", action="store_true",
                        help="diagnostic mode: never start a missing controller")
    parser.add_argument("--lease", type=Path, help="private access pair or queue grant JSON; no automatic acquisition or renewal")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    capture = commands.add_parser("capture")
    capture.add_argument("--output", required=True, type=Path)
    arm = commands.add_parser("arm")
    arm.add_argument("--capture", required=True, type=Path)
    arm.add_argument("--review-note", required=True)
    arm.add_argument("--output", required=True, type=Path)
    action = commands.add_parser("action")
    action.add_argument("--arm", required=True, type=Path)
    action.add_argument("--keys", default="")
    action.add_argument("--hold-ms", default=100, type=int)
    action.add_argument("--mouse-button", choices=("left", "right"))
    action.add_argument("--dx", default=0, type=int)
    action.add_argument("--dy", default=0, type=int)
    action.add_argument("--wheel", default=0, type=int)
    action.add_argument("--click-target", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"),
                        help="reviewed client-pixel button rectangle; standalone left click only")
    action.add_argument("--output", required=True, type=Path)
    for name in ("stop", "release", "recover"):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path)
    return parser


def run(args, *, opener=None) -> dict:
    try:
        config = HOST.HostConfig.load(args.config)
    except (OSError, ValueError, HOST.ControlHostError) as error:
        raise ClientError("config-error", str(error)) from error
    # Operational calls own their controller prerequisite. Test/openers and
    # non-fleet configurations stay inert; never launch an unrecognized target.
    if opener is None and not getattr(args, "no_auto_start", False):
        repo_root = str(Path(__file__).resolve().parents[1])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from scripts.ensure_controller import CONFIGS, ensure
        from scripts.operation_dependencies import DependencyUnavailable
        target = next((lab for lab, path in CONFIGS.items()
                       if path.resolve() == args.config.resolve()), None)
        if target is not None:
            try:
                ensure(target)
                # Live capture and reviewed actions need an authenticated guest,
                # not merely a listening main-PC controller. Status and
                # cleanup-only operations remain independently inspectable.
                if args.command in ("capture", "arm", "action"):
                    from scripts.ensure_guest_agent import ensure as ensure_guest_agent
                    ensure_guest_agent(target)
            except DependencyUnavailable as error:
                raise ClientError("dependency-unavailable", str(error)) from None
    access = None
    if args.command in HOST.PROTECTED_CONTROL_OPERATIONS and getattr(args, "lease", None) is not None:
        access = _read_private_lease(args.lease)
    client = ControlClient(config, opener=opener, access=access)
    if args.command == "status":
        return client.request("/api/status", method="GET")
    if args.command == "capture":
        return _capture(client, args.output)
    if args.command == "arm":
        return _arm(client, args.capture, args.review_note, args.output)
    if args.command == "action":
        return _action(client, args)
    return _simple(client, args.command, args.output)


def main(argv=None, *, opener=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        _print({"ok": True, "value": run(args, opener=opener)})
        return 0
    except ClientError as error:
        failure: dict[str, Any] = {
            "ok": False, "error": {"code": error.code, "message": str(error)},
        }
        if error.details is not None:
            failure["error"]["details"] = error.details
        sys.stderr.buffer.write(_json_bytes(_redact_for_console(failure)))
        sys.stderr.buffer.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
