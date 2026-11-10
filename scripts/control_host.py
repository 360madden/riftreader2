#!/usr/bin/env python3
"""Repo-owned host hub for supervised RIFT-Lab controls.

The guest opens the control connection.  The operator surface is loopback-only.
This process records intent and transport results; it never labels them as game
response evidence.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import nullcontext, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import re
import select
import socket
import sqlite3
import struct
import sys
import threading
import time
from typing import Any
from urllib.parse import quote
import uuid


MAX_FRAME_BYTES = 16 * 1024 * 1024
MAX_HELLO_BYTES = 64 * 1024
MAX_HTTP_BODY_BYTES = 64 * 1024
REQUEST_TIMEOUT_SECONDS = 8.0
SEND_TIMEOUT_SECONDS = 2.0
TRANSPORT_POLL_SECONDS = .05
TRANSPORT_CHUNK_BYTES = 64 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UUID_HEX = re.compile(r"^[0-9a-f]{32}$")
CONTROL_KEYS = frozenset(("w", "a", "s", "d", "q", "e"))
REQUIRED_CONFIG = frozenset((
    "schemaVersion", "bindAddress", "agentPort", "uiPort", "guestAddress",
    "expectedMachineName", "token", "operatorToken", "outputDirectory",
))
OPTIONAL_CONFIG = frozenset((
    "bootstrapFile", "bootstrapPort", "vmx", "vmrun", "vncPort",
))


class ControlHostError(RuntimeError):
    """A fail-closed protocol, configuration, or control error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ControlHostError(f"duplicate JSON property: {key}")
        result[key] = value
    return result


def decode_json(data: bytes) -> Any:
    try:
        return json.loads(
            data,
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ControlHostError(f"non-finite JSON value: {value}")
            ),
        )
    except ControlHostError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlHostError("invalid JSON") from error


def encode_frame(value: object) -> bytes:
    try:
        data = json.dumps(
            value, separators=(",", ":"), sort_keys=True, allow_nan=False
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as error:
        raise ControlHostError("response is not finite JSON") from error
    if len(data) > MAX_FRAME_BYTES + 1:
        raise ControlHostError("JSON frame exceeds 16 MiB")
    return data


def read_frame(stream, maximum: int = MAX_FRAME_BYTES) -> dict:
    data = stream.readline(maximum + 2)
    if not data:
        raise EOFError("connection closed")
    if len(data) > maximum + 1 or not data.endswith(b"\n"):
        raise ControlHostError(f"JSON frame exceeds {maximum} bytes or is unterminated")
    value = decode_json(data[:-1])
    if not isinstance(value, dict):
        raise ControlHostError("JSON frame must be an object")
    return value


def _bounded_text(value, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ControlHostError(f"{name} must be non-empty text up to {maximum} characters")
    return value


def _port(value, name: str, *, allow_zero: bool = False) -> int:
    lower = 0 if allow_zero else 1
    if type(value) is not int or not lower <= value <= 65535:
        raise ControlHostError(f"{name} must be an integer from {lower} through 65535")
    return value


def _is_rfc1918(address: str) -> bool:
    value = ipaddress.IPv4Address(address)
    return any(value in network for network in (
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
    ))


@dataclass(frozen=True)
class HostConfig:
    bind_address: str
    agent_port: int
    ui_port: int
    guest_address: str
    expected_machine_name: str
    token: str
    operator_token: str
    output_directory: Path
    bootstrap_file: Path | None = None
    bootstrap_port: int | None = None
    vmx: Path | None = None
    vmrun: Path | None = None
    vnc_port: int | None = None

    @staticmethod
    def load(path: Path) -> "HostConfig":
        path = Path(path).resolve()
        raw = path.read_bytes()
        if len(raw) > MAX_HTTP_BODY_BYTES:
            raise ControlHostError("configuration exceeds 64 KiB")
        value = decode_json(raw)
        if not isinstance(value, dict):
            raise ControlHostError("configuration must be an object")
        fields = frozenset(value)
        if not REQUIRED_CONFIG.issubset(fields) or fields - REQUIRED_CONFIG - OPTIONAL_CONFIG:
            raise ControlHostError("configuration fields do not match schema 1")
        if value["schemaVersion"] != 1 or type(value["schemaVersion"]) is not int:
            raise ControlHostError("only configuration schema 1 is supported")
        bind = str(ipaddress.IPv4Address(_bounded_text(value["bindAddress"], "bindAddress", 64)))
        guest = str(ipaddress.IPv4Address(_bounded_text(value["guestAddress"], "guestAddress", 64)))
        if not _is_rfc1918(bind) or not _is_rfc1918(guest):
            raise ControlHostError("bindAddress and guestAddress must be RFC 1918 IPv4 addresses")
        machine = _bounded_text(value["expectedMachineName"], "expectedMachineName", 64)
        token = _bounded_text(value["token"], "token", 512)
        operator = _bounded_text(value["operatorToken"], "operatorToken", 512)
        if len(token) < 16 or len(operator) < 16:
            raise ControlHostError("control tokens must contain at least 16 characters")
        output = Path(value["outputDirectory"])
        if not output.is_absolute():
            output = path.parent / output
        bootstrap_file = value.get("bootstrapFile")
        bootstrap_port = value.get("bootstrapPort")
        if (bootstrap_file is None) != (bootstrap_port is None):
            raise ControlHostError("bootstrapFile and bootstrapPort must be configured together")
        resolved_bootstrap = None
        if bootstrap_file is not None:
            resolved_bootstrap = Path(_bounded_text(bootstrap_file, "bootstrapFile", 32768))
            if not resolved_bootstrap.is_absolute():
                resolved_bootstrap = path.parent / resolved_bootstrap
            resolved_bootstrap = resolved_bootstrap.resolve(strict=True)
            if not resolved_bootstrap.is_file():
                raise ControlHostError("bootstrapFile must be one existing regular file")
            bootstrap_port = _port(bootstrap_port, "bootstrapPort")
        vm_values = (value.get("vmx"), value.get("vmrun"), value.get("vncPort"))
        if any(item is not None for item in vm_values) and not all(item is not None for item in vm_values):
            raise ControlHostError("vmx, vmrun, and vncPort must be configured together")
        vmx = vmrun = None
        vnc_port = None
        if all(item is not None for item in vm_values):
            vmx = Path(_bounded_text(vm_values[0], "vmx", 32768))
            vmrun = Path(_bounded_text(vm_values[1], "vmrun", 32768))
            if not vmx.is_absolute():
                vmx = path.parent / vmx
            if not vmrun.is_absolute():
                vmrun = path.parent / vmrun
            vnc_port = _port(vm_values[2], "vncPort")
        return HostConfig(
            bind, _port(value["agentPort"], "agentPort"),
            _port(value["uiPort"], "uiPort"), guest, machine, token, operator,
            output.resolve(), resolved_bootstrap, bootstrap_port,
            vmx.resolve() if vmx is not None else None,
            vmrun.resolve() if vmrun is not None else None,
            vnc_port,
        )


class VmEpochGuard:
    """Bind control authorization to the repo-owned VMware process epoch."""

    def __init__(self, config: HostConfig):
        self.module = None
        self.config = None
        self._console_condition = threading.Condition()
        self._console_mutex = None
        self._console_thread = None
        self._console_identity = None
        self._console_required = False
        self._console_acquiring = False
        self._console_closing = False
        self._console_faulted = False
        self._console_users = 0
        if config.vmx is None:
            return
        path = Path(__file__).with_name("vm_console_native.py")
        spec = importlib.util.spec_from_file_location("rr2_vm_console_native", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        try:
            native_config = module.validate_config(
                config.vmx, config.vnc_port, config.vmrun,
                config.output_directory / "vm-console", require_files=True,
            )
        except module.Blocked as error:
            raise ControlHostError(str(error)) from error
        self.module = module
        self.config = native_config

    @property
    def enabled(self):
        return self.module is not None

    def console_status(self):
        """Local exclusion state, not proof of guest release or supervisor readiness."""
        with self._console_condition:
            return {"required": self._console_required,
                    "held": self._console_mutex is not None,
                    "acquiring": self._console_acquiring,
                    "closing": self._console_closing, "faulted": self._console_faulted,
                    "inFlight": self._console_users}

    def reserve_console(self):
        """Reserve the established console mutex for this guard's lifetime.

        Call and release from the same owning thread. Other native request
        threads borrow this reservation; legacy console processes cannot. This
        grants no queue lease and does not make an authenticated guest ready.
        """
        if not self.enabled:
            raise ControlHostError("exclusive console requires an exact configured VM")
        with self._console_condition:
            if self._console_required or self._console_users:
                raise ControlHostError("console ownership cannot be acquired twice or during a request")
            self._console_required = True  # Never fall back silently after failure/release.
            self._console_acquiring = True
        mutex = self.module.ControlMutex(self.config.vmx)
        entered = False
        try:
            mutex.__enter__()
            entered = True
            identity = self.module.collect_identity(self.config)
            with self._console_condition:
                if self._console_closing:
                    raise ControlHostError("console reservation was closed during acquisition")
                self._console_identity = dict(identity)
                self._console_thread = threading.current_thread()
                self._console_mutex = mutex
                self._console_acquiring = False
            return {"identity": dict(identity), "held": True,
                    "previousOwnerAbandoned": getattr(mutex, "abandoned", False)}
        except BaseException as error:
            if entered:
                mutex.__exit__(None, None, None)
            with self._console_condition:
                self._console_faulted = True
                self._console_acquiring = False
                self._console_condition.notify_all()
            if isinstance(error, self.module.Blocked):
                raise ControlHostError(str(error)) from None
            raise

    def release_console(self, *, timeout_seconds=2.0):
        """Stop admission; release only after borrowed requests drain.

        A pending result retains the mutex until an explicit same-thread retry.
        Release is local ownership handoff, never a claim of guest key release.
        The owner must shut down supervisors and guest sessions first.
        """
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 <= timeout_seconds <= 5):
            raise ControlHostError("invalid console release timeout")
        deadline = time.monotonic() + timeout_seconds
        with self._console_condition:
            if self._console_acquiring:
                self._console_closing = True
                return {"released": False, "releasePending": True}
            if self._console_mutex is None:
                return {"released": True, "releasePending": False}
            if threading.current_thread() is not self._console_thread:
                raise ControlHostError("console reservation must be released by its owning thread")
            self._console_closing = True
            while self._console_users:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"released": False, "releasePending": True}
                self._console_condition.wait(remaining)
            self._console_mutex.__exit__(None, None, None)
            self._console_mutex = None
            return {"released": True, "releasePending": False}

    @contextmanager
    def _console_boundary(self):
        with self._console_condition:
            reserved = self._console_mutex is not None
            if self._console_required and (not reserved or self._console_closing
                    or self._console_faulted or not self._console_thread.is_alive()):
                raise ControlHostError("console reservation is unavailable or closing")
            self._console_users += 1
        try:
            with nullcontext() if reserved else self.module.ControlMutex(self.config.vmx):
                yield reserved
        finally:
            with self._console_condition:
                self._console_users -= 1
                self._console_condition.notify_all()

    def _observe(self, expected, fast, reserved):
        try:
            current = (self.module.verify_identity(self.config, expected) if fast
                       else self.module.collect_identity(self.config))
            if (expected is not None and current != expected) or (
                    reserved and current != self._console_identity):
                raise ControlHostError("VM process epoch changed during console ownership")
            return current
        except BaseException:
            if reserved:
                with self._console_condition:
                    self._console_faulted = True
            raise

    def collect(self) -> dict | None:
        if not self.enabled:
            return None
        try:
            with self._console_boundary() as reserved:
                return self._observe(None, False, reserved)
        except self.module.Blocked as error:
            raise ControlHostError(str(error)) from error

    def request(self, expected: dict | None, callback, *, fast: bool):
        if not self.enabled:
            return callback()
        if not isinstance(expected, dict):
            raise ControlHostError("a complete authenticated VM identity is required")
        try:
            with self._console_boundary() as reserved:
                before = self._observe(expected, fast, reserved)
                result = callback()
                self._observe(before, fast, reserved)
                return result
        except self.module.Blocked as error:
            raise ControlHostError(str(error)) from error


def sanitize_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            folded = key.casefold()
            if "token" in folded or folded in ("authorization",):
                result[key] = "[redacted]"
            elif key == "imageBase64" and isinstance(item, str):
                result[key] = {"omitted": True, "encodedLength": len(item)}
            else:
                result[key] = sanitize_evidence(item)
        return result
    if isinstance(value, list):
        return [sanitize_evidence(item) for item in value]
    return value


class EvidenceJournal:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.capture_root = self.root / "captures"
        self.capture_root.mkdir(exist_ok=True)
        self.path = self.root / "control-host.jsonl"
        self._lock = threading.Lock()

    def append(self, kind: str, value: object) -> None:
        record = {
            "schemaVersion": 1,
            "evidenceKind": kind,
            "recordedAtUtc": utc_now(),
            "value": sanitize_evidence(value),
        }
        data = json.dumps(record, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def retain_capture(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ControlHostError("capture response payload must be an object")
        capture_id = payload.get("captureId")
        if not isinstance(capture_id, str) or not SAFE_ID.fullmatch(capture_id):
            raise ControlHostError("captureId is invalid")
        if payload.get("imageFormat") != "bmp":
            raise ControlHostError("capture must use bmp imageFormat")
        if not isinstance(payload.get("target"), dict) or not payload["target"]:
            raise ControlHostError("capture target is required")
        encoded = payload.get("imageBase64")
        if not isinstance(encoded, str):
            raise ControlHostError("capture imageBase64 is required")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ControlHostError("capture imageBase64 is invalid") from error
        if not image.startswith(b"BM"):
            raise ControlHostError("capture bytes are not a BMP image")
        if len(image) < 26:
            raise ControlHostError("capture BMP header is truncated")
        width, height = struct.unpack_from("<ii", image, 18)
        if width <= 0 or height == 0 or width > 1920 or abs(height) > 1080:
            raise ControlHostError("capture BMP dimensions exceed 1920x1080 or are invalid")
        destination = self.capture_root / f"{capture_id}.bmp"
        try:
            with destination.open("xb") as stream:
                stream.write(image)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise ControlHostError("capture artifact already exists") from error
        retained = {
            "path": str(destination.resolve()),
            "sha256": hashlib.sha256(image).hexdigest().upper(),
            "byteLength": len(image),
        }
        result = dict(payload)
        result["artifact"] = retained
        self.append("control-capture/1", {**result, "imageBase64": encoded})
        return result


class AgentSession:
    def __init__(self, connection: socket.socket, source: str, hello: dict,
                 journal: EvidenceJournal, on_closed, vm_identity=None, dispatch_policy=None,
                 require_supervisor=False):
        self.connection = connection
        self.source = source
        self.hello = dict(hello)
        self.journal = journal
        self.on_closed = on_closed
        self.vm_identity = vm_identity
        self.dispatch_policy = dispatch_policy
        self.require_supervisor = require_supervisor
        self._control_lock = threading.Lock()
        self._control_generation = 0
        self._control_idle = threading.Condition(self._control_lock)
        self._protected_calls = 0
        self._controls_suspended = require_supervisor
        self._cleanup_lock = threading.Lock()
        # One fixed socket mode: per-request timeout changes would also affect the
        # concurrent reader. Authenticated framing uses explicit nonblocking I/O.
        self.connection.setblocking(False)
        self._receive_buffer = bytearray()
        self._send_lock = threading.Lock()
        self._action_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}
        self._sequence = 0
        self._closed = threading.Event()
        self._reader = threading.Thread(target=self._read_responses, daemon=True)

    def start(self):
        self._reader.start()

    @property
    def closed(self):
        return self._closed.is_set()

    def summary(self) -> dict:
        return {
            "connected": not self.closed,
            "sourceAddress": self.source,
            "instanceId": self.hello["instanceId"],
            "machineName": self.hello["machineName"],
            "lastIssuedSequence": self._sequence,
            "vmIdentity": self.vm_identity,
        }

    def request(self, operation: str, payload: dict | None = None, *, access=None) -> dict:
        access = dict(access) if isinstance(access, dict) else access
        protected = operation in ("capture", "arm", "action", "recover")
        with self._control_lock:
            if protected and self._controls_suspended:
                raise ControlHostError("control session suspended for verified cleanup")
            if operation in ("stop", "release"):
                self._control_generation += 1
            generation = self._control_generation
            if protected:
                self._protected_calls += 1
        try:
            lane = self._action_lock if operation == "action" else nullcontext()
            with lane:
                return self._request(operation, payload or {}, access=access, generation=generation)
        finally:
            if protected:
                with self._control_idle:
                    self._protected_calls -= 1
                    self._control_idle.notify_all()

    @contextmanager
    def preparation_boundary(self):
        """Claim one startup without suspending another already-installed owner.

        The cleanup owner lock also excludes a concurrent permit while startup
        validates identity/registers its authority. No send/control-state lock
        or database transaction spans the guest observations.
        """
        if not self._cleanup_lock.acquire(blocking=False):
            raise ControlHostError("another preparation or cleanup owns this session")
        try:
            with self._control_lock:
                if self.closed or self.dispatch_policy is not None:
                    raise ControlHostError("session cannot be prepared twice or after disconnect")
                self._controls_suspended = True
                self._control_generation += 1
            yield
        finally:
            self._cleanup_lock.release()

    def suspend_controls(self):
        """Local fail-closed latch; STOP/release/status remain available."""
        with self._control_lock:
            self._controls_suspended = True
            self._control_generation += 1

    def wait_controls_idle(self, timeout=2.0):
        if type(timeout) not in (int, float) or not 0 <= timeout <= 5:
            raise ControlHostError("cleanup drain timeout must be zero through five seconds")
        with self._control_idle:
            return self._control_idle.wait_for(lambda: self._protected_calls == 0, timeout)

    @contextmanager
    def cleanup_boundary(self):
        """Exclude new controls, invalidate queued work, and latch failure.

        The trusted caller must STOP, drain, verify fresh status and publish queue
        cleanup before invoking the yielded release function. Only the cleanup-owner
        mutex spans guest I/O, not send/control-state locks or a DB transaction.
        Failure leaves controls suspended.
        """
        if not self._cleanup_lock.acquire(blocking=False):
            raise ControlHostError("another cleanup owns this session")
        self.suspend_controls()
        permit_generation = None
        completed = False
        def permit():
            nonlocal permit_generation
            with self._control_lock:
                if self.closed or self._protected_calls:
                    raise ControlHostError("cannot release a closed or non-idle cleanup boundary")
                permit_generation = self._control_generation
        try:
            yield permit
            completed = True
        finally:
            with self._control_lock:
                if (completed and permit_generation is not None
                        and permit_generation == self._control_generation and not self.closed):
                    self._controls_suspended = False
            self._cleanup_lock.release()

    @contextmanager
    def _admission(self, operation, access):
        # Fresh identity reads grant no input authority and need no queue lease.
        if operation in ("identity", "native-vitals", "native-xyz", "native-orientation", "native-actor-pose"):
            if access is not None:
                raise ControlHostError("read-only requests do not accept a control lease")
            yield None
            return
        if self.dispatch_policy is None:
            if self.require_supervisor and operation in ("capture", "arm", "action", "recover"):
                raise ControlHostError("new session requires an owned supervisor")
            if access is not None and operation not in ("status", "stop", "release"):
                raise ControlHostError("navigation lease supplied to an uncoordinated session")
            yield None
            return
        try:
            with self.dispatch_policy.guard(operation, access) as admit:
                yield admit
        except ValueError as error:
            raise ControlHostError("navigation dispatch refused: " + str(error)) from error

    def _abort_transport(self, failure):
        """Fail local waiters; disconnection is never proof of guest-side release."""
        self._closed.set()
        self._fail_pending(failure)
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()

    @contextmanager
    def _send_boundary(self):
        # Bound lock contention too. No new frame may follow a partly sent frame.
        if not self._send_lock.acquire(timeout=SEND_TIMEOUT_SECONDS):
            failure = ControlHostError("guest send lock deadline; delivery uncertain; no retry")
            self._abort_transport(failure)
            raise failure
        try:
            yield
        finally:
            self._send_lock.release()

    def _send_frame(self, data):
        deadline = time.monotonic() + SEND_TIMEOUT_SECONDS
        view = memoryview(data)
        offset = 0
        try:
            while offset < len(view):
                if self.closed:
                    raise OSError("transport closed")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                try:
                    sent = self.connection.send(view[offset:offset + TRANSPORT_CHUNK_BYTES])
                except (BlockingIOError, InterruptedError):
                    # A ready indication is not a promise the whole frame fits.
                    select.select([], [self.connection], [], min(remaining, TRANSPORT_POLL_SECONDS))
                    continue
                if sent <= 0:
                    raise OSError("transport made no send progress")
                offset += sent
            if time.monotonic() > deadline:
                raise TimeoutError()
        except (OSError, ValueError) as error:
            reason = "deadline" if isinstance(error, TimeoutError) else "failed"
            failure = ControlHostError("guest send " + reason + "; delivery uncertain; no retry")
            self._abort_transport(failure)
            raise failure from None

    def _receive_frame(self):
        # The single reader retains coalesced frames and bounds incomplete input.
        search_from = 0
        while not self.closed:
            end = self._receive_buffer.find(b"\n", search_from)
            if end >= 0:
                if end > MAX_FRAME_BYTES:
                    raise ControlHostError("guest response frame exceeds size limit")
                data = bytes(self._receive_buffer[:end])
                del self._receive_buffer[:end + 1]
                value = decode_json(data)
                if not isinstance(value, dict):
                    raise ControlHostError("JSON frame must be an object")
                return value
            if len(self._receive_buffer) > MAX_FRAME_BYTES:
                raise ControlHostError("guest response frame is oversized or unterminated")
            search_from = len(self._receive_buffer)
            ready, _, _ = select.select([self.connection], [], [], TRANSPORT_POLL_SECONDS)
            if not ready:
                continue
            try:
                block = self.connection.recv(min(TRANSPORT_CHUNK_BYTES,
                                                MAX_FRAME_BYTES + 2 - len(self._receive_buffer)))
            except (BlockingIOError, InterruptedError):
                continue
            if not block:
                raise EOFError("guest control connection closed")
            self._receive_buffer.extend(block)
        raise EOFError("guest control connection closed")

    def _request(self, operation: str, payload: dict, *, access=None, generation=0) -> dict:
        if self.closed:
            raise ControlHostError("guest control connection is closed")
        if operation not in (
                "status", "identity", "native-vitals", "native-xyz", "native-orientation", "native-actor-pose", "capture", "arm", "action", "release", "stop", "recover"):
            raise ControlHostError("unsupported guest operation")
        if not isinstance(payload, dict):
            raise ControlHostError("command payload must be an object")
        if operation in ("identity", "native-vitals", "native-xyz", "native-orientation", "native-actor-pose"):
            validate_identity_payload(payload)
            if payload["machineName"] != self.hello["machineName"]:
                raise ControlHostError("identity machine does not match authenticated guest")
        if (operation == "action" and payload.get("action", {}).get("clickTarget") is not None
                and (type(self.hello.get("targetedClickVersion")) is not int
                     or self.hello["targetedClickVersion"] != 1)):
            raise ControlHostError("guest does not support targeted clicks; no action sent")
        command_id = uuid.uuid4().hex
        response_queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[command_id] = response_queue
        try:
            # Acquire the queue fence before the send lock: STOP/release must not
            # wait for an experiment merely waiting to acquire its queue authority.
            # Admission is rechecked after both waits; DB transactions end before send.
            with self._admission(operation, access) as admit:
                with self._send_boundary():
                    if self.closed:
                        raise ControlHostError("guest control connection is closed")
                    if admit is not None:
                        admit()
                    with self._control_lock:
                        if (operation in ("capture", "arm", "action", "recover")
                                and (self._controls_suspended or (self.dispatch_policy is not None
                                     and generation != self._control_generation))):
                            raise ControlHostError("control request invalidated by STOP/release")
                        self._sequence += 1
                        command = {
                            "type": "command", "id": command_id,
                            "sequence": self._sequence, "operation": operation,
                            "payload": payload,
                        }
                        frame = encode_frame(command)
                        self._send_frame(frame)
            self.journal.append("control-command-request/1", command)
            try:
                response = response_queue.get(timeout=REQUEST_TIMEOUT_SECONDS)
            except queue.Empty as error:
                self.close()
                raise ControlHostError("guest request exceeded the 8 second deadline") from error
            if isinstance(response, BaseException):
                raise ControlHostError(str(response)) from response
            response_payload = response["payload"]
            self.journal.append("control-command-response/1", {
                "id": command_id, "sequence": command["sequence"],
                "operation": operation, "payload": response_payload,
            })
            if isinstance(response_payload.get("error"), str):
                raise ControlHostError(response_payload["error"])
            return response_payload
        finally:
            with self._pending_lock:
                self._pending.pop(command_id, None)

    def _read_responses(self):
        failure: BaseException = ControlHostError("guest control connection closed")
        try:
            while not self.closed:
                response = self._receive_frame()
                if set(response) != {"type", "id", "payload"} or response.get("type") != "response":
                    raise ControlHostError("guest sent an invalid response envelope")
                response_id = response.get("id")
                if not isinstance(response_id, str) or not UUID_HEX.fullmatch(response_id):
                    raise ControlHostError("guest response id is invalid")
                if not isinstance(response.get("payload"), dict):
                    raise ControlHostError("guest response payload must be an object")
                with self._pending_lock:
                    destination = self._pending.get(response_id)
                if destination is None:
                    raise ControlHostError("guest sent an unsolicited or duplicate response")
                destination.put_nowait(response)
        except BaseException as error:
            failure = error
        finally:
            self._abort_transport(failure)
            self._receive_buffer.clear()
            self.on_closed(self)

    def _fail_pending(self, failure):
        with self._pending_lock:
            pending = list(self._pending.values())
        for destination in pending:
            try:
                destination.put_nowait(failure)
            except queue.Full:
                pass

    def close(self):
        self._abort_transport(ControlHostError("guest control connection closed"))
        if threading.current_thread() is not self._reader and self._reader.is_alive():
            self._reader.join(timeout=1)


class AgentGateway:
    def __init__(self, config: HostConfig, journal: EvidenceJournal, *, dispatch_policy=None,
                 require_supervisor=False, exclusive_console=False):
        if (type(exclusive_console) is not bool or (exclusive_console and not require_supervisor)):
            raise ControlHostError("exclusive console requires denied-first supervision")
        self.exclusive_console = exclusive_console
        self._start_attempted = False
        if type(require_supervisor) is not bool or (require_supervisor and dispatch_policy is not None):
            raise ControlHostError("deny-first startup requires a fresh per-session supervisor")
        self.require_supervisor = require_supervisor
        self.dispatch_policy = dispatch_policy
        self.config = config
        self.journal = journal
        self.vm_guard = VmEpochGuard(config)
        if exclusive_console and not self.vm_guard.enabled:
            raise ControlHostError("exclusive console requires an exact configured VM")
        self._listener = None
        self._accept_thread = None
        self._closed = threading.Event()
        self._session_lock = threading.Lock()
        self._session: AgentSession | None = None
        self._authentication_slots = threading.BoundedSemaphore(4)
        self.coordinator = None

    @property
    def port(self) -> int | None:
        return self._listener.getsockname()[1] if self._listener and self._listener.fileno() != -1 else None

    def start(self):
        with self._session_lock:
            if self._start_attempted or self._closed.is_set():
                raise ControlHostError("gateway start is single-use")
            self._start_attempted = True
        reserved = False
        listener = None
        try:
            with self._session_lock:
                if self._closed.is_set():
                    raise ControlHostError("gateway is closing")
                if self.exclusive_console:
                    self.vm_guard.reserve_console()
                    reserved = True
                    if self._closed.is_set():
                        raise ControlHostError("gateway closed during console acquisition")
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.config.bind_address, self.config.agent_port))
                listener.listen(4)
                listener.settimeout(0.25)
                self._listener = listener
                self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
                self._accept_thread.start()
        except BaseException:
            self._closed.set()
            if listener is not None:
                listener.close()
            self._listener = None
            if reserved:
                self.vm_guard.release_console()
            raise

    def _accept_loop(self):
        while not self._closed.is_set():
            try:
                connection, address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self._authentication_slots.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(
                target=self._authenticate, args=(connection, address), daemon=True
            ).start()

    def _authenticate(self, connection: socket.socket, address):
        source = address[0]
        stream = connection.makefile("rb")
        try:
            connection.settimeout(5)
            hello = read_frame(stream, MAX_HELLO_BYTES)
            hello_fields = {"type", "token", "instanceId", "machineName"}
            if (set(hello) not in (hello_fields, hello_fields | {"targetedClickVersion"})
                    or hello.get("type") != "hello"):
                raise ControlHostError("invalid hello envelope")
            if "targetedClickVersion" in hello and (type(hello["targetedClickVersion"]) is not int
                                                   or hello["targetedClickVersion"] != 1):
                raise ControlHostError("unsupported targeted click version")
            if source != self.config.guest_address:
                raise ControlHostError("guest source address mismatch")
            supplied = hello.get("token")
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied, self.config.token):
                raise ControlHostError("guest token mismatch")
            _bounded_text(hello.get("instanceId"), "instanceId", 128)
            machine = _bounded_text(hello.get("machineName"), "machineName", 64)
            if machine.casefold() != self.config.expected_machine_name.casefold():
                raise ControlHostError("guest machine name mismatch")
            with self._session_lock:
                if self._closed.is_set():
                    raise ControlHostError("gateway is closing")
                if self._session is not None and not self._session.closed:
                    raise ControlHostError("a guest is already connected")
                vm_identity = self.vm_guard.collect()
                # Keep the existing handshake timeout through the welcome write.
                connection.sendall(encode_frame({"type": "welcome"}))
                session = AgentSession(
                    connection, source, hello, self.journal,
                    self._session_closed, vm_identity, self.dispatch_policy,
                    require_supervisor=self.require_supervisor,
                )
                self._session = session
            self.journal.append("control-guest-connected/1", session.summary())
            session.start()
        except BaseException as error:
            try:
                connection.sendall(encode_frame({"type": "error", "error": str(error)}))
            except (OSError, ControlHostError):
                pass
            connection.close()
        finally:
            stream.close()
            self._authentication_slots.release()

    def _session_closed(self, session):
        self.journal.append("control-guest-disconnected/1", session.summary())
        with self._session_lock:
            if self._session is session:
                self._session = None

    def session(self) -> AgentSession:
        with self._session_lock:
            session = self._session
        if session is None or session.closed:
            raise ControlHostError("no authenticated guest is connected")
        return session

    def local_status(self) -> dict:
        try:
            result = self.session().summary()
        except ControlHostError:
            result = {"connected": False}
        if self.exclusive_console:
            result["consoleReservation"] = self.vm_guard.console_status()
        if self.coordinator is not None:
            result["coordination"] = self.coordinator.status()
        return result

    def command(self, operation: str, payload: dict | None = None, *, access=None) -> dict:
        session = self.session()
        if operation in ("native-vitals", "native-xyz", "native-orientation", "native-actor-pose") and (
                not self.vm_guard.enabled or not isinstance(session.vm_identity, dict)):
            raise ControlHostError(operation + " requires an authenticated VM identity guard")
        def invoke():
            if operation in ("native-vitals", "native-xyz", "native-orientation", "native-actor-pose"):
                # Bind capability admission to THIS authenticated transport. Never
                # silently reacquire another session between status and dispatch.
                instance = session.hello.get("instanceId")
                if not isinstance(instance, str) or not UUID_HEX.fullmatch(instance):
                    raise ControlHostError("native read authenticated instance is invalid")
                status = session.request("status", {}, access=None)
                if (not isinstance(status, dict)
                        or type(status.get("nativeReadLeaseVersion")) is not int
                        or status["nativeReadLeaseVersion"] != 1):
                    raise ControlHostError(
                        operation + " requires nativeReadLeaseVersion 1 from the current authenticated agent")
                if status.get("instanceId") != instance:
                    raise ControlHostError("native read status instance mismatch")
                if (session.closed or session.hello.get("instanceId") != instance
                        or self.session() is not session):
                    raise ControlHostError("native read session changed before dispatch")
                # This is a cooperative protocol claim, not deployed-binary
                # attestation or proof that nonparticipating readers are excluded.
            return session.request(operation, payload, access=access)

        if operation == "arm":
            result = self.vm_guard.request(session.vm_identity, invoke, fast=False)
        elif operation in ("action", "recover", "native-vitals", "native-xyz", "native-orientation", "native-actor-pose") or (self.exclusive_console and operation == "capture"):
            result = self.vm_guard.request(session.vm_identity, invoke, fast=True)
        else:
            result = invoke()
        if operation == "arm":
            arm_token = result.get("armToken")
            if (not isinstance(arm_token, str) or not arm_token
                    or len(arm_token) > 512 or result.get("expiresInSeconds") != 15):
                raise ControlHostError("guest returned an invalid 15 second arm result")
        return result

    def capture(self, *, access=None) -> dict:
        return self.journal.retain_capture(self.command("capture", {}, access=access))

    def close(self, *, reservation_timeout_seconds=2.0):
        self._closed.set()
        if self._listener:
            self._listener.close()
        with self._session_lock:
            session = self._session
        if session:
            session.close()
        if self._accept_thread and self._accept_thread.ident is not None:
            self._accept_thread.join(timeout=1)
        if self.exclusive_console:
            outcome = self.vm_guard.release_console(timeout_seconds=reservation_timeout_seconds)
            return {"closed": True, "consoleReleased": outcome["released"],
                    "releasePending": outcome["releasePending"]}


PROTECTED_CONTROL_OPERATIONS = frozenset(("capture", "arm", "action", "recover"))


def validate_control_access(value: object) -> dict:
    """Copy only the private capability pair; authoritative lease checks happen at send."""
    if not isinstance(value, dict) or set(value) != {"request_id", "token"}:
        raise ControlHostError("control access must contain request_id and token")
    request_id, token = value["request_id"], value["token"]
    if (not isinstance(request_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id)
            or not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token)):
        raise ControlHostError("invalid control access identifiers")
    return {"request_id": request_id, "token": token}


def split_control_envelope(operation: str, body: object):
    """Explicit envelope, never a header that an older host could silently ignore.

    Unwrapped legacy requests retain existing behavior; an installed policy still
    refuses them at dispatch. STOP/release remain empty-body and credential-free.
    """
    if (operation in PROTECTED_CONTROL_OPERATIONS and isinstance(body, dict)
            and ("access" in body or "payload" in body)):
        if set(body) != {"access", "payload"} or not isinstance(body["payload"], dict):
            raise ControlHostError("invalid owned control envelope")
        return body["payload"], validate_control_access(body["access"])
    return body, None


def validate_arm_payload(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"captureId", "reviewNote"}:
        raise ControlHostError("arm payload must contain captureId and reviewNote")
    capture_id = payload.get("captureId")
    if not isinstance(capture_id, str) or not SAFE_ID.fullmatch(capture_id):
        raise ControlHostError("arm captureId is invalid")
    note = payload.get("reviewNote")
    if not isinstance(note, str) or not 12 <= len(note.strip()) <= 512:
        raise ControlHostError("reviewNote must contain 12 through 512 characters")
    return {"captureId": capture_id, "reviewNote": note.strip()}


def validate_action_payload(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"armToken", "action"}:
        raise ControlHostError("action payload must contain armToken and action")
    token = _bounded_text(payload.get("armToken"), "armToken", 512)
    action = payload.get("action")
    expected = {"keys", "holdMilliseconds", "mouseButton", "deltaX", "deltaY", "wheelNotches"}
    if not isinstance(action, dict) or set(action) not in (expected, expected | {"clickTarget"}):
        raise ControlHostError("action fields do not match the control contract")
    keys = action.get("keys")
    if (not isinstance(keys, list) or len(keys) > len(CONTROL_KEYS)
            or any(not isinstance(key, str) or key not in CONTROL_KEYS for key in keys)
            or len(set(keys)) != len(keys)):
        raise ControlHostError("keys must be a unique list containing only w/a/s/d/q/e")
    conflicts = ({"w", "s"}, {"a", "d"}, {"q", "e"})
    if any(pair.issubset(keys) for pair in conflicts):
        raise ControlHostError("keys cannot contain opposing movement controls")
    hold = action.get("holdMilliseconds")
    if type(hold) is not int:
        raise ControlHostError("holdMilliseconds must be an integer")
    mouse = action.get("mouseButton")
    if mouse not in (None, "left", "right"):
        raise ControlHostError("mouseButton must be null, left, or right")
    deltas = []
    for name in ("deltaX", "deltaY"):
        value = action.get(name)
        if type(value) is not int or not -200 <= value <= 200:
            raise ControlHostError(f"{name} must be an integer from -200 through 200")
        deltas.append(value)
    wheel = action.get("wheelNotches")
    if type(wheel) is not int or not -1 <= wheel <= 1:
        raise ControlHostError("wheelNotches must be -1, 0, or 1")
    if wheel:
        if keys or hold != 0 or mouse is not None or deltas != [0, 0]:
            raise ControlHostError(
                "wheel input must be standalone with holdMilliseconds 0")
    elif not 20 <= hold <= 250:
        raise ControlHostError("holdMilliseconds must be an integer from 20 through 250")
    if not keys and mouse is None and deltas == [0, 0] and wheel == 0:
        raise ControlHostError("action must contain a bounded operator input")
    result = {"armToken": token, "action": {
        "keys": keys, "holdMilliseconds": hold, "mouseButton": mouse,
        "deltaX": deltas[0], "deltaY": deltas[1], "wheelNotches": wheel,
    }}
    if "clickTarget" in action:
        click = action["clickTarget"]
        if (not isinstance(click, dict) or set(click) != {"x", "y", "width", "height"}
                or any(type(v) is not int for v in click.values())
                or not 0 <= click["x"] <= 4095 or not 0 <= click["y"] <= 2159
                or not 4 <= click["width"] <= 128 or not 4 <= click["height"] <= 128):
            raise ControlHostError("invalid targeted button rectangle")
        if keys or mouse != "left" or deltas != [0, 0] or wheel:
            raise ControlHostError("a targeted click must be a standalone left click")
        result["action"]["clickTarget"] = dict(click)
    return result


def validate_identity_payload(payload):
    fields = {"machineName", "processId", "processStartUtcTicks", "executableSha256"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ControlHostError("identity payload fields do not match schema 1")
    machine = payload["machineName"]
    if (not isinstance(machine, str) or not 1 <= len(machine) <= 64
            or re.fullmatch(r"[A-Za-z0-9_.-]+", machine) is None):
        raise ControlHostError("invalid identity machineName")
    for field, maximum in (("processId", 2147483647),
                           ("processStartUtcTicks", 3155378975999999999)):
        if type(payload[field]) is not int or not 1 <= payload[field] <= maximum:
            raise ControlHostError("invalid identity " + field)
    if (not isinstance(payload["executableSha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", payload["executableSha256"]) is None):
        raise ControlHostError("invalid identity executableSha256")
    return payload


class ControlHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, gateway: AgentGateway, config: HostConfig, html: bytes):
        super().__init__(address, ControlRequestHandler)
        self.gateway = gateway
        self.config = config
        self.html = html
        self.expected_origin = f"http://127.0.0.1:{self.server_address[1]}"


class ControlRequestHandler(BaseHTTPRequestHandler):
    server_version = "RiftReader2Control/1"

    def log_message(self, *_):
        return

    def _headers(self, status: int, content_type: str, length: int):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self, status: int, value: object):
        data = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def _api_authorized(self) -> bool:
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_address[1]}":
            self._json(403, {"error": "host rejected"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.expected_origin:
            self._json(403, {"error": "origin rejected"})
            return False
        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied = authorization[len(prefix):] if authorization.startswith(prefix) else ""
        if not hmac.compare_digest(supplied, self.server.config.operator_token):
            self._json(401, {"error": "bearer token rejected"})
            return False
        return True

    def _body(self) -> object:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as error:
            raise ControlHostError("Content-Length is required") from error
        if not 0 <= length <= MAX_HTTP_BODY_BYTES:
            raise ControlHostError("request body exceeds 64 KiB")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ControlHostError("request body is incomplete")
        return decode_json(data) if data else {}

    def do_GET(self):
        if self.path == "/":
            data = self.server.html
            self._headers(200, "text/html; charset=utf-8", len(data))
            self.wfile.write(data)
            return
        if self.path != "/api/status":
            self._json(404, {"error": "not found"})
            return
        if not self._api_authorized():
            return
        try:
            result = {"host": self.server.gateway.local_status()}
            if result["host"]["connected"]:
                result["guest"] = self.server.gateway.command("status", {})
            self._json(200, result)
        except ControlHostError as error:
            self._json(409, {"error": str(error)})

    def do_POST(self):
        routes = {
            "/api/capture": "capture", "/api/arm": "arm",
            "/api/action": "action", "/api/release": "release",
            "/api/stop": "stop",
            "/api/recover": "recover",
            "/api/identity": "identity",
            "/api/native-vitals": "native-vitals",
            "/api/native-xyz": "native-xyz",
            "/api/native-orientation": "native-orientation",
            "/api/native-actor-pose": "native-actor-pose",
        }
        operation = routes.get(self.path)
        if operation is None:
            self._json(404, {"error": "not found"})
            return
        if not self._api_authorized():
            return
        try:
            payload, access = split_control_envelope(operation, self._body())
            access_kwargs = {"access": access} if access is not None else {}
            if operation in ("capture", "release", "stop", "recover") and payload != {}:
                raise ControlHostError(f"{operation} request body must be an empty object")
            if operation in ("identity", "native-vitals", "native-xyz", "native-orientation", "native-actor-pose"):
                result = self.server.gateway.command(operation, validate_identity_payload(payload))
            elif operation == "capture":
                result = self.server.gateway.capture(**access_kwargs)
            elif operation == "arm":
                result = self.server.gateway.command("arm", validate_arm_payload(payload), **access_kwargs)
            elif operation == "action":
                result = self.server.gateway.command("action", validate_action_payload(payload), **access_kwargs)
            elif operation in ("release", "stop", "recover"):
                result = self.server.gateway.command(operation, {}, **access_kwargs)
            self._json(200, result)
        except ControlHostError as error:
            self._json(409, {"error": str(error)})


class BootstrapHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config: HostConfig):
        super().__init__(address, BootstrapRequestHandler)
        self.config = config
        self.bundle = config.bootstrap_file
        self.bundle_sha256 = hashlib.sha256(self.bundle.read_bytes()).hexdigest().upper()


class BootstrapRequestHandler(BaseHTTPRequestHandler):
    server_version = "RiftReader2Bootstrap/1"

    def log_message(self, *_):
        return

    def do_GET(self):
        if self.path != "/bundle":
            self.send_error(404)
            return
        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied = authorization[len(prefix):] if authorization.startswith(prefix) else ""
        if not hmac.compare_digest(supplied, self.server.config.token):
            self.send_error(401)
            return
        size = self.server.bundle.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-SHA256", self.server.bundle_sha256)
        self.send_header("Content-Disposition", f'attachment; filename="{self.server.bundle.name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with self.server.bundle.open("rb") as stream:
            while block := stream.read(64 * 1024):
                self.wfile.write(block)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--coordination-db", type=Path,
                        help="existing absolute queue database; opt-in coordinated host")
    parser.add_argument("--coordination-resource", help="exact VM resource, for example vm:lab-1")
    parser.add_argument("--reconcile-existing", action="store_true",
                        help="explicitly revoke existing grants and verify fresh cleanup on startup")
    parser.add_argument("--shutdown-file", type=Path,
                        help="absent absolute marker path; creating it requests verified shutdown")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    coordinated = args.coordination_db is not None
    if coordinated != (args.coordination_resource is not None):
        parser.error("coordination database and resource must be supplied together")
    if (args.reconcile_existing or args.shutdown_file is not None) and not coordinated:
        parser.error("reconciliation and shutdown marker require coordinated mode")
    if coordinated and (not args.coordination_db.is_absolute()
            or not re.fullmatch(r"vm:[a-z0-9][a-z0-9._/-]{0,120}", args.coordination_resource)):
        parser.error("coordinated mode requires an absolute database and exact VM resource")
    if args.shutdown_file is not None and (not args.shutdown_file.is_absolute() or args.shutdown_file.exists()):
        parser.error("shutdown marker must be an absent absolute path")
    gateway = None
    ui = None
    bootstrap = None
    threads = []
    coordinator = None
    try:
        config = HostConfig.load(args.config)
        journal = EvidenceJournal(config.output_directory)
        authority = None
        if coordinated:
            # Direct script execution must resolve the same repository package.
            root = str(Path(__file__).resolve().parents[1])
            if root not in sys.path:
                sys.path.insert(0, root)
            from scripts.nav_access_queue import AccessQueue
            from scripts.nav_host_runtime import HostCoordinator
            authority = AccessQueue(args.coordination_db)  # Refuse missing/corrupt DB.
        gateway = AgentGateway(config, journal, require_supervisor=coordinated,
                               exclusive_console=coordinated)
        gateway.start()
        if coordinated:
            coordinator = HostCoordinator(gateway, authority, args.coordination_resource, journal,
                                          reconcile_existing=args.reconcile_existing)
            gateway.coordinator = coordinator
        html_path = Path(__file__).with_name("control_panel.html")
        html = html_path.read_bytes()
        ui = ControlHttpServer(("127.0.0.1", config.ui_port), gateway, config, html)
        threads.append(threading.Thread(target=ui.serve_forever, daemon=True))
        if config.bootstrap_file is not None:
            bootstrap = BootstrapHttpServer((config.bind_address, config.bootstrap_port), config)
            threads.append(threading.Thread(target=bootstrap.serve_forever, daemon=True))
        for thread in threads:
            thread.start()
        print(json.dumps({
            "status": "running",
            "agentEndpoint": f"{config.bind_address}:{gateway.port}",
            "operatorUrl": f"http://127.0.0.1:{ui.server_address[1]}/#{quote(config.operator_token, safe='')}",
            "bootstrapEndpoint": (
                f"http://{config.bind_address}:{bootstrap.server_address[1]}/bundle"
                if bootstrap else None
            ),
            "evidence": str(journal.path.resolve()),
        }, indent=2))
        while True:
            if args.shutdown_file is not None and args.shutdown_file.exists():
                break
            if coordinator is not None:
                coordinator.poll()
            time.sleep(0.1)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ControlHostError, OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}))
        return 2
    finally:
        if coordinator is not None:
            # Do not unlock console maintenance while a supervisor is running or
            # release is unverified. A second Ctrl+C is an explicit forced exit,
            # never a successful cleanup claim. Native STOP/status remain served.
            outcome = coordinator.stop()
            announced = False
            while not outcome["safeToClose"]:
                if not announced:
                    # Diagnostic storage/output failure must not release ownership.
                    try:
                        journal.append("nav-host-shutdown-pending/1", outcome)
                    except Exception:
                        pass
                    try:
                        print(json.dumps({"status": "shutdown-blocked", "coordination": outcome}), flush=True)
                    except (OSError, ValueError):
                        pass
                    announced = True
                time.sleep(.25)
                outcome = coordinator.stop(timeout_seconds=.1)
        if ui:
            if threads and threads[0].is_alive():
                ui.shutdown()
            ui.server_close()
        if bootstrap:
            if len(threads) > 1 and threads[1].is_alive():
                bootstrap.shutdown()
            bootstrap.server_close()
        if gateway:
            gateway.close()


if __name__ == "__main__":
    raise SystemExit(main())
