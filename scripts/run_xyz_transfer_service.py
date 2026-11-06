"""Guarded one-use XYZ ZIP claim/upload service; preview is the default.

Preview validates only files, hashes, schemas, and phase order.  ``--serve`` is
the sole live entry point.  It does not launch a process, open a VM console,
read credentials, issue game input, or change VM settings.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
from http.server import HTTPServer
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_host import HostConfig
from scripts.prepare_native_host_handover import authority_snapshot
from scripts.receive_guest_inline_zip_claim import handler_for as claim_handler
from scripts.receive_guest_memory_report import create_handler as upload_handler
from scripts.receive_guest_memory_report import POINTER_ROUTE
from scripts.run_guest_inline_service import require_independent_windows_user
from scripts.vm_console_native import (
    Blocked, ControlMutex, collect_identity, normalized_path, process_identity, validate_config,
)

ARTIFACTS = ROOT / "artifacts"
BIND = "192.168.56.1"
GUEST = "192.168.56.128"
PORT = 8765
MAX_SECONDS = 600
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
RESERVED_RUN_IDS = {"con", "prn", "aux", "nul",
                    *(f"com{i}" for i in range(1, 10)),
                    *(f"lpt{i}" for i in range(1, 10))}
CLAIM_SOURCE = ROOT / "scripts/receive_guest_inline_zip_claim.py"
UPLOAD_SOURCE = ROOT / "scripts/receive_guest_memory_report.py"
CLAIM_SOURCE_SHA = "0C2443EA12427CD346B167DDC26704C2B1E75C7B584FF712BAA3E4BA4FFDDF4A"
UPLOAD_SOURCE_SHA = "C3BB17580C83B8B2BBC9D862148B7B897551707B1E47DA92771633D62C377B3F"
SHA = re.compile(r"[0-9A-F]{64}\Z")
SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?\Z")
PLAN_KEYS = {"schemaVersion", "contractVersion", "runId", "target",
             "readerSha256", "maintenancePlan", "priorProcess", "priorExit"}
TARGET_KEYS = {"processId", "processStartUtcTicks", "executableSha256"}
PIN_KEYS = {"path", "sha256"}
MAINTENANCE_KEYS = {"schemaVersion", "configPath", "configSha256", "database",
                    "resource", "shutdownFile", "vmIdentity", "runtimeHashes",
                    "expectedWindowsSession"}


class TransferBlocked(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TransferBlocked(message)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode(raw: bytes, label: str) -> dict:
    _require(len(raw) <= 1024 * 1024, f"{label} exceeds 1 MiB")
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda x: (_ for _ in ()).throw(
                               TransferBlocked(f"nonfinite JSON in {label}: {x}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransferBlocked(f"invalid JSON: {label}") from error
    _require(isinstance(value, dict), f"JSON object required: {label}")
    return value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _regular(path: Path, label: str) -> bytes:
    _require(path.is_absolute() and path.is_file() and not path.is_symlink() and
             not _reparse(path),
             f"{label} must be an absolute regular file")
    lexical = path.absolute()
    artifact_root = ARTIFACTS.resolve(strict=True)
    for ancestor in (lexical, *lexical.parents):
        if ancestor == artifact_root.parent:
            break
        if ancestor.exists():
            _require(not ancestor.is_symlink() and not _reparse(ancestor),
                     f"linked path refused: {label}")
    resolved = path.resolve(strict=True)
    _require(resolved.is_relative_to(artifact_root), f"{label} is outside artifacts")
    size = resolved.stat().st_size
    _require(0 <= size <= 1024 * 1024, f"{label} exceeds 1 MiB")
    with resolved.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    _require(len(raw) == size and len(raw) <= 1024 * 1024,
             f"{label} changed or exceeds 1 MiB")
    return raw


def _pin(value: object, label: str) -> tuple[Path, bytes]:
    _require(isinstance(value, dict) and set(value) == PIN_KEYS,
             f"invalid {label} pin")
    _require(isinstance(value["path"], str), f"invalid {label} path")
    _require(isinstance(value["sha256"], str) and SHA.fullmatch(value["sha256"]),
             f"invalid {label} SHA-256")
    path = Path(value["path"])
    raw = _regular(path, label)
    _require(_sha(raw) == value["sha256"], f"{label} hash differs")
    return path.resolve(strict=True), raw


def _target(value: object) -> dict:
    _require(isinstance(value, dict) and set(value) == TARGET_KEYS,
             "invalid exact target")
    _require(type(value["processId"]) is int and value["processId"] > 0 and
             type(value["processStartUtcTicks"]) is int and
             value["processStartUtcTicks"] > 0 and
             isinstance(value["executableSha256"], str) and
             SHA.fullmatch(value["executableSha256"]), "invalid exact target")
    return dict(value)


def _identity(value: object, label: str) -> dict:
    _require(isinstance(value, dict) and set(value) == {"pid", "image", "startTicks"} and
             type(value["pid"]) is int and value["pid"] > 0 and
             isinstance(value["image"], str) and value["image"] and
             type(value["startTicks"]) is int and value["startTicks"] > 0,
             f"invalid {label} identity")
    return value


def _vm_identity(value: object) -> dict:
    keys = {"vmx", "port", "logEpoch", "listenerPid", "pid", "image", "startTicks"}
    _require(isinstance(value, dict) and set(value) == keys and
             isinstance(value["vmx"], str) and value["vmx"] and
             type(value["port"]) is int and 1 <= value["port"] <= 65535 and
             isinstance(value["logEpoch"], str) and value["logEpoch"] and
             type(value["listenerPid"]) is int and value["listenerPid"] > 0 and
             type(value["pid"]) is int and value["pid"] == value["listenerPid"] and
             isinstance(value["image"], str) and value["image"] and
             type(value["startTicks"]) is int and value["startTicks"] > 0,
             "invalid maintenance VM identity")
    return value


def _json_file(path: Path, label: str) -> dict:
    return _decode(_regular(path, label), label)


def _claim_value(value: dict, target: dict, reader_sha: str) -> dict:
    required = {"schemaVersion", "evidenceKind", "source", "guest", "zipSha256",
                "zipBytes", "target", "bundleSha256"}
    _require(required.issubset(value) and
             type(value["schemaVersion"]) is int and value["schemaVersion"] == 1 and
             value["evidenceKind"] == "guest-native-pointer-zip-claim/1" and
             value["source"] == "guest-declared-only" and value["guest"] == GUEST and
             value["target"] == target and value["bundleSha256"] == reader_sha and
             isinstance(value["zipSha256"], str) and SHA.fullmatch(value["zipSha256"]) and
             type(value["zipBytes"]) is int and 1 <= value["zipBytes"] <= MAX_ARCHIVE_BYTES,
             "claim phase provenance differs")
    return value


def _maintenance(path: Path, raw: bytes) -> tuple[dict, str]:
    value = _decode(raw, "maintenance plan")
    allowed = MAINTENANCE_KEYS | {"createdUtc"}
    _require(set(value) in (MAINTENANCE_KEYS, allowed), "maintenance plan fields differ")
    _require(type(value["schemaVersion"]) is int and value["schemaVersion"] == 1 and
             value["expectedWindowsSession"] == 2, "maintenance plan version differs")
    _vm_identity(value["vmIdentity"])
    _require(isinstance(value["resource"], str) and value["resource"],
             "maintenance resource missing")
    match = re.fullmatch(r"coordinated-host-plan-(v[1-9][0-9]*)\.json", path.name)
    _require(match is not None, "maintenance plan filename lacks successor version")
    version = match.group(1)
    for name in ("configPath", "database", "shutdownFile"):
        candidate = Path(value[name])
        _require(candidate.is_absolute() and candidate.resolve(strict=False).is_relative_to(
            ARTIFACTS.resolve(strict=True)), f"maintenance {name} is outside artifacts")
    _require(isinstance(value["configSha256"], str) and
             re.fullmatch(r"[0-9a-f]{64}", value["configSha256"]),
             "maintenance config hash differs")
    _require(isinstance(value["runtimeHashes"], dict) and value["runtimeHashes"],
             "maintenance runtime hashes missing")
    for relative, expected in value["runtimeHashes"].items():
        _require(isinstance(relative, str) and not Path(relative).is_absolute() and
                 isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
                 "invalid maintenance runtime pin")
        source = (ROOT / relative).resolve(strict=True)
        _require(source.is_relative_to(ROOT) and source.is_file() and
                 not (ROOT / relative).is_symlink() and not _reparse(ROOT / relative) and
                 hashlib.sha256(source.read_bytes()).hexdigest() == expected,
                 f"maintenance runtime differs: {relative}")
    config = Path(value["configPath"])
    _require(_sha(_regular(config, "host configuration")).lower() == value["configSha256"],
             "host configuration hash differs")
    return value, version


def _paths(plan_path: Path, run_id: str) -> dict[str, Path]:
    return {
        "claim": plan_path.parent / f"{run_id}-claim.json",
        "upload": plan_path.parent / f"{run_id}-upload.zip",
        "claimProcess": plan_path.parent / f"{run_id}-claim-process.json",
        "claimExit": plan_path.parent / f"{run_id}-claim-exited.json",
        "uploadProcess": plan_path.parent / f"{run_id}-upload-process.json",
        "uploadExit": plan_path.parent / f"{run_id}-upload-exited.json",
    }


def load_plan(plan_path: Path, phase: str) -> dict:
    plan_path = Path(plan_path)
    plan_raw = _regular(plan_path, "transfer plan")
    plan = _decode(plan_raw, "transfer plan")
    _require(set(plan) == PLAN_KEYS and type(plan["schemaVersion"]) is int and
             plan["schemaVersion"] == 1 and
             plan["contractVersion"] == "xyz-transfer-plan/1",
             "unsupported transfer plan")
    run_id = plan["runId"]
    _require(isinstance(run_id, str) and len(run_id) <= 48 and SLUG.fullmatch(run_id),
             "invalid runId")
    _require(run_id not in RESERVED_RUN_IDS, "reserved runId")
    target = _target(plan["target"])
    _require(isinstance(plan["readerSha256"], str) and SHA.fullmatch(plan["readerSha256"]),
             "invalid reader SHA-256")
    maintenance_path, maintenance_raw = _pin(plan["maintenancePlan"], "maintenance plan")
    prior_path, prior_raw = _pin(plan["priorProcess"], "prior process")
    exit_path, exit_raw = _pin(plan["priorExit"], "prior exit")
    maintenance, successor = _maintenance(maintenance_path, maintenance_raw)
    prior = _decode(prior_raw, "prior process")
    exited = _decode(exit_raw, "prior exit")
    _require(type(prior.get("pid")) is int and prior["pid"] > 0 and
             _identity(prior.get("processIdentity"), "prior process")["pid"] == prior["pid"] and
             prior.get("windowsSessionId") == 2 and prior.get("inJob") is False and
             prior.get("vmIdentity") == maintenance["vmIdentity"] and
             prior.get("shutdownMarker"), "prior process evidence differs")
    prior_stop = Path(prior["shutdownMarker"])
    _require(prior_stop.is_absolute() and
             prior_stop.resolve(strict=False).is_relative_to(ARTIFACTS.resolve(strict=True)),
             "prior STOP marker is outside artifacts")
    _require(set(exited) == {"pid", "utc"} and exited.get("pid") == prior["pid"] and
             isinstance(exited.get("utc"), str) and exited["utc"],
             "prior exit evidence differs")
    paths = _paths(plan_path.resolve(strict=True), run_id)
    for path in paths.values():
        _require(path.resolve(strict=False).parent == plan_path.resolve(strict=True).parent,
                 "derived output escaped plan directory")
    successor_process = maintenance_path.parent / f"coordinated-host-{successor}-process.json"
    successor_exit = maintenance_path.parent / f"coordinated-host-{successor}-exited.json"
    plan_sha = _sha(plan_raw)
    if phase == "claim":
        _require(not any(path.exists() for path in paths.values()),
                 "claim phase output already exists")
    else:
        _require(paths["claim"].is_file() and paths["claimProcess"].is_file() and
                 paths["claimExit"].is_file(), "completed claim phase required")
        claim = _json_file(paths["claim"], "claim receipt")
        process = _json_file(paths["claimProcess"], "claim process receipt")
        outcome = _json_file(paths["claimExit"], "claim exit receipt")
        _claim_value(claim, target, plan["readerSha256"])
        process_identity_value = _identity(process.get("processIdentity"), "claim process")
        _require(type(process.get("schemaVersion")) is int and
                 process.get("schemaVersion") == 1 and
                 process.get("contractVersion") == "xyz-transfer-process/1" and
                 process.get("planSha256") == plan_sha and process.get("phase") == "claim" and
                 process.get("windowsSessionId") == 2 and process.get("inJob") is False and
                 process.get("bind") == BIND and process.get("guest") == GUEST and
                 process.get("port") == PORT and
                 process_identity_value["pid"] == process.get("pid") and
                 process.get("vmIdentity") == maintenance["vmIdentity"] and
                 type(outcome.get("schemaVersion")) is int and
                 outcome.get("schemaVersion") == 1 and
                 outcome.get("contractVersion") == "xyz-transfer-exit/1" and
                 outcome.get("planSha256") == plan_sha and outcome.get("phase") == "claim" and
                 outcome.get("state") == "claim-received" and
                 outcome.get("listenerClosed") is True and
                 outcome.get("mutexReleased") is True and
                 outcome.get("vmIdentity") == maintenance["vmIdentity"] and
                 outcome.get("pid") == process.get("pid"), "claim phase provenance differs")
        _require(not any(paths[name].exists() for name in ("upload", "uploadProcess", "uploadExit")),
                 "upload phase output already exists")
    return {"path": plan_path.resolve(strict=True), "raw": plan_raw,
            "sha256": plan_sha, "value": plan, "target": target,
            "maintenance": maintenance, "maintenancePath": maintenance_path,
            "prior": prior, "priorExit": exited, "successorProcess": successor_process,
            "successorExit": successor_exit, "paths": paths, "phase": phase}


def _refresh_inputs(context: dict) -> None:
    """Require all caller and maintenance pins to remain the original bytes."""
    current_plan = _regular(context["path"], "transfer plan")
    _require(current_plan == context["raw"] and _sha(current_plan) == context["sha256"],
             "transfer plan changed after validation")
    plan = _decode(current_plan, "transfer plan")
    maintenance_path, maintenance_raw = _pin(plan["maintenancePlan"], "maintenance plan")
    prior_path, prior_raw = _pin(plan["priorProcess"], "prior process")
    exit_path, exit_raw = _pin(plan["priorExit"], "prior exit")
    maintenance, _successor = _maintenance(maintenance_path, maintenance_raw)
    _require(maintenance_path == context["maintenancePath"] and
             maintenance == context["maintenance"] and
             _decode(prior_raw, "prior process") == context["prior"] and
             _decode(exit_raw, "prior exit") == context["priorExit"],
             "pinned maintenance context changed")
    source = CLAIM_SOURCE if context["phase"] == "claim" else UPLOAD_SOURCE
    expected = CLAIM_SOURCE_SHA if context["phase"] == "claim" else UPLOAD_SOURCE_SHA
    _require(_sha(source.read_bytes()) == expected, "pinned receiver source changed")


def _descriptor(context: dict, seconds: int) -> dict:
    phase = context["phase"]
    source = CLAIM_SOURCE if phase == "claim" else UPLOAD_SOURCE
    expected = CLAIM_SOURCE_SHA if phase == "claim" else UPLOAD_SOURCE_SHA
    _require(_sha(source.read_bytes()) == expected, "pinned receiver source changed")
    return {"schemaVersion": 1, "contractVersion": "xyz-transfer-preview/1",
            "state": "verified-not-serving", "phase": phase,
            "runId": context["value"]["runId"], "planSha256": context["sha256"],
            "bind": BIND, "guest": GUEST, "port": PORT, "lifetimeSeconds": seconds,
            "route": ("/rr2-native-pointer-zip-claim-oct24-01" if phase == "claim"
                      else POINTER_ROUTE), "maximumArchiveBytes": MAX_ARCHIVE_BYTES,
            "liveNotChecked": True, "listenerStarted": False, "gameInput": False,
            "credentialsRead": False, "vmConsoleOpened": False,
            "limitation": ("The target is a caller-pinned identity. Preview does not prove "
                           "that this process is current in the guest or that live guards pass.")}


def preview(plan_path: Path, phase: str, seconds: int) -> dict:
    _require(phase in ("claim", "upload") and type(seconds) is int and
             30 <= seconds <= MAX_SECONDS, "invalid phase or lifetime")
    return _descriptor(load_plan(plan_path, phase), seconds)


def _write_new(path: Path, value: dict) -> None:
    raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        _require(stream.write(raw) == len(raw), "short receipt write")
        stream.flush()
        os.fsync(stream.fileno())
    _require(path.read_bytes() == raw, "receipt readback differs")


def _prior_process_identity(pid: int) -> dict | None:
    """Return current identity, None only for Win32 ERROR_INVALID_PARAMETER."""
    _require(os.name == "nt", "process exit proof requires Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        _require(error == 87, f"prior process open failed with Win32 error {error}")
        return None
    try:
        api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                   wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        _require(api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)) != 0,
                 f"prior process image query failed with Win32 error {ctypes.get_last_error()}")
        times = [wintypes.FILETIME() for _ in range(4)]
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)] * 4
        _require(api.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)) != 0,
                 f"prior process time query failed with Win32 error {ctypes.get_last_error()}")
        return {"pid": pid, "image": str(normalized_path(Path(buffer.value))),
                "startTicks": ((times[0].dwHighDateTime << 32) |
                               times[0].dwLowDateTime)}
    finally:
        api.CloseHandle(handle)


def _prior_epoch_exited(prior: dict) -> None:
    """Fail closed on access errors; PID absence or a different epoch proves exit."""
    current = _prior_process_identity(prior["pid"])
    if current is None:
        return
    _require(current["pid"] == prior["pid"], "prior process query returned another PID")
    _require(current["startTicks"] != prior["processIdentity"]["startTicks"],
             "prior process epoch is still alive")


def _live_gate(context: dict):
    require_independent_windows_user()
    _refresh_inputs(context)
    maintenance = context["maintenance"]
    prior = context["prior"]
    _require(Path(prior["shutdownMarker"]).is_file(), "prior normal STOP marker absent")
    _prior_epoch_exited(prior)
    _require(not context["successorProcess"].exists() and not context["successorExit"].exists(),
             "successor already started")
    _require(not Path(maintenance["shutdownFile"]).exists(), "successor STOP marker exists")
    _require(authority_snapshot(Path(maintenance["database"]), maintenance["resource"]) ==
             (1, None, None), "canonical authority is not quarantined")
    if context["phase"] == "upload":
        _prior_epoch_exited(_json_file(context["paths"]["claimProcess"],
                                       "claim process receipt"))
    _require(_listener_rows() == [], "port 8765 already has a listener")
    config = HostConfig.load(Path(maintenance["configPath"]))
    _require(config.vmx is not None and config.vmrun is not None and config.vnc_port is not None,
             "host configuration lacks VMware identity")
    native = validate_config(config.vmx, config.vnc_port, config.vmrun,
                             config.output_directory / "vm-console", require_files=True)
    mutex = ControlMutex(native.vmx)
    mutex.__enter__()
    try:
        _require(not mutex.abandoned, "controller mutex was abandoned")
        _require(collect_identity(native) == maintenance["vmIdentity"], "VM identity drift")
        # Repeat mutable gates under sole ownership immediately before binding.
        _prior_epoch_exited(prior)
        _require(not context["successorProcess"].exists() and
                 not context["successorExit"].exists(), "successor appeared")
        _require(authority_snapshot(Path(maintenance["database"]), maintenance["resource"]) ==
                 (1, None, None), "canonical authority changed")
        _require(not Path(maintenance["shutdownFile"]).exists(), "successor STOP marker appeared")
        _require(_listener_rows() == [], "port 8765 listener appeared")
        _refresh_inputs(context)
        return mutex, native
    except BaseException:
        mutex.__exit__(None, None, None)
        raise


class _DeadlineServer(HTTPServer):
    """Close accepted sockets at one absolute deadline, including partial headers."""
    allow_reuse_address = False
    request_queue_size = 2

    def __init__(self, address, handler, deadline):
        self.deadline = deadline
        self._active = set()
        self._active_lock = threading.Lock()
        self._expired = False
        super().__init__(address, handler)

    def get_request(self):
        request, address = super().get_request()
        with self._active_lock:
            if self._expired or time.monotonic() >= self.deadline:
                try:
                    request.close()
                finally:
                    raise OSError("transfer deadline expired")
            self._active.add(request)
        return request, address

    def close_request(self, request):
        with self._active_lock:
            self._active.discard(request)
        super().close_request(request)

    def expire(self):
        with self._active_lock:
            self._expired = True
            active = list(self._active)
        for connection in active:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass

    def handle_error(self, *_args):
        # Deadline-triggered disconnects are expected and contain no useful evidence.
        pass


def _serve_once(handler, seconds: float, *, upload: bool, ready=None):
    deadline = time.monotonic() + seconds
    with _DeadlineServer((BIND, PORT), handler, deadline) as server:
        server.timeout = min(1, max(.01, seconds))
        server.delivered = False
        server.result = None
        server.upload_info = None
        if ready is not None:
            ready(server.server_address)
        stop = threading.Event()
        watchdog = threading.Thread(
            target=lambda: (None if stop.wait(max(0, deadline - time.monotonic()))
                            else server.expire()), daemon=True)
        watchdog.start()
        try:
            while time.monotonic() < deadline and not server.delivered:
                server.handle_request()
            return server.upload_info if upload else server.result
        finally:
            stop.set()
            server.expire()
            watchdog.join(timeout=2)


def _listener_rows(port: int = PORT) -> list[tuple[str, int]]:
    """Read-only Windows TCP ownership, including non-loopback listeners."""
    _require(os.name == "nt", "listener verification requires Windows")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    _require(size.value > 0, "listener table unavailable")
    data = ctypes.create_string_buffer(size.value)
    _require(get_table(data, ctypes.byref(size), False, socket.AF_INET, 3, 0) == 0,
             "listener table unavailable")
    from scripts.vm_console_native import parse_tcp_listener_rows
    return parse_tcp_listener_rows(bytes(data.raw[:size.value]), port)


def serve(plan_path: Path, phase: str, seconds: int) -> tuple[int, dict]:
    _require(phase in ("claim", "upload") and type(seconds) is int and
             30 <= seconds <= MAX_SECONDS, "invalid phase or lifetime")
    context = load_plan(plan_path, phase)
    descriptor = _descriptor(context, seconds)
    paths = context["paths"]
    process_path = paths[phase + "Process"]
    exit_path = paths[phase + "Exit"]
    mutex = native = None
    process_receipt = None
    process_published = False
    state = "blocked"
    listener_closed = False
    try:
        mutex, native = _live_gate(context)
        session, in_job = require_independent_windows_user()
        process_receipt = {"schemaVersion": 1, "contractVersion": "xyz-transfer-process/1",
            "phase": phase, "pid": os.getpid(), "processIdentity": process_identity(os.getpid()),
            "windowsSessionId": session, "inJob": in_job, "planSha256": context["sha256"],
            "vmIdentity": context["maintenance"]["vmIdentity"], "bind": BIND,
            "guest": GUEST, "port": PORT, "startedAtUtc": datetime.now(timezone.utc).isoformat()}
        _write_new(process_path, process_receipt)
        process_published = True
        if phase == "claim":
            handler = claim_handler(paths["claim"], GUEST, pid=context["target"]["processId"],
                ticks=context["target"]["processStartUtcTicks"],
                game_sha=context["target"]["executableSha256"],
                bundle_sha=context["value"]["readerSha256"], kind="pointer")
            result = _serve_once(handler, seconds, upload=False)
            if result is not None:
                published = _claim_value(_json_file(paths["claim"], "claim receipt"),
                                         context["target"],
                                         context["value"]["readerSha256"])
                _require(published == result, "published claim differs from receiver result")
            candidate_state = "claim-received" if result is not None else "expired-no-claim"
        else:
            claim = _claim_value(_json_file(paths["claim"], "claim receipt"),
                                 context["target"], context["value"]["readerSha256"])
            handler = upload_handler(paths["upload"], claim["zipSha256"], GUEST,
                                     MAX_ARCHIVE_BYTES, route=POINTER_ROUTE)
            result = _serve_once(handler, seconds, upload=True)
            if result is not None:
                claim = _json_file(paths["claim"], "claim receipt")
                _require(result.get("bytes") == claim["zipBytes"] and
                         result.get("sha256", "").upper() == claim["zipSha256"] and
                         paths["upload"].stat().st_size == claim["zipBytes"] and
                         _sha(paths["upload"].read_bytes()) == claim["zipSha256"],
                         "uploaded ZIP length differs from declaration")
            candidate_state = "upload-received" if result is not None else "expired-no-upload"
        _require(_listener_rows() == [], "transfer listener remains open")
        listener_closed = True
        _refresh_inputs(context)
        _require(collect_identity(native) == context["maintenance"]["vmIdentity"],
                 "VM identity changed during listener")
        _require(process_identity(process_receipt["pid"]) ==
                 process_receipt["processIdentity"], "service process identity changed")
        state = candidate_state
        code = 0 if result is not None else 3
        return code, {**descriptor, "state": state, "liveNotChecked": False,
                      "listenerStarted": True, "result": result}
    finally:
        if process_receipt is not None and not listener_closed:
            try:
                listener_closed = _listener_rows() == []
            except (TransferBlocked, OSError):
                listener_closed = False
        release_error = None
        if mutex is not None:
            try:
                mutex.__exit__(None, None, None)
            except BaseException as error:
                release_error = error
                state = "blocked"
        if process_published:
            _write_new(exit_path, {"schemaVersion": 1,
                "contractVersion": "xyz-transfer-exit/1", "phase": phase,
                "pid": process_receipt["pid"], "planSha256": context["sha256"],
                "state": state, "completedAtUtc": datetime.now(timezone.utc).isoformat(),
                "listenerClosed": listener_closed, "mutexReleased": release_error is None,
                "vmIdentity": context["maintenance"]["vmIdentity"]})
        if release_error is not None:
            raise release_error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--phase", choices=("claim", "upload"), required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.serve:
            code, result = serve(args.plan, args.phase, args.seconds)
        else:
            code, result = 0, preview(args.plan, args.phase, args.seconds)
        print(json.dumps(result, sort_keys=True), flush=True)
        return code
    except (TransferBlocked, Blocked, OSError, ValueError, KeyError, TypeError,
            OverflowError, socket.error) as error:
        print(json.dumps({"state": "blocked", "reason": str(error)}),
              file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
