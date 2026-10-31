"""Ensure the existing per-lab control host is available on demand.

Starts only a new, identity-pinned, detached and disarmed host when the local
API is absent. Reuses an existing endpoint without attempting takeover.
No VM/game startup, addon commands, gameplay input or queue reset.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_host import HostConfig, VmEpochGuard
from scripts.operation_dependencies import DependencyUnavailable

CONFIGS = {
    "lab1": ROOT / "artifacts/control-fleet-live/lab1/host.json",
    "lab2": ROOT / "artifacts/control-fleet-live/lab2/host.json",
}
QUEUE = ROOT / "artifacts/native-coordination-live/queue.sqlite3"
ENTRY = ROOT / "scripts/controller_host_entry.py"
RUNTIME_FILES = (
    "scripts/control_host.py", "scripts/vm_console_native.py",
    "scripts/nav_host_runtime.py", "scripts/nav_access_queue.py",
    "scripts/nav_supervisor_bootstrap.py", "scripts/nav_control_watchdog.py",
    "scripts/nav_startup_preflight.py", "scripts/control_panel.html",
    "scripts/controller_host_entry.py",
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _session_id():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    current = wintypes.DWORD()
    if not api.ProcessIdToSessionId(os.getpid(), ctypes.byref(current)) or current.value == 0:
        raise DependencyUnavailable("controller", "interactive-windows-session-required")
    return current.value


def _require_uncontained():
    # Never launch a long-lived control host inside a bounded job.
    try:
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetCurrentProcess.restype = wintypes.HANDLE
        api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.BOOL)]
        contained = wintypes.BOOL()
        if not api.IsProcessInJob(api.GetCurrentProcess(), None, ctypes.byref(contained)):
            raise OSError("containment-query-failed")
    except OSError:
        raise DependencyUnavailable("controller", "containment-query-failed") from None
    if contained.value:
        raise DependencyUnavailable("controller", "persistent-launcher-unavailable-in-bounded-job")


def _listening(port):
    # On this Windows host timeout-mode connect_ex can report WSAEWOULDBLOCK
    # (10035) even for a closed loopback port. Blocking loopback returns the
    # definitive WSAECONNREFUSED (10061), without a false startup decision.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            code = connection.connect_ex(("127.0.0.1", port))
    except OSError:
        raise DependencyUnavailable("controller", "listener-state-uncertain") from None
    if code == 0:
        return True
    if code in (10061, 111):
        return False
    raise DependencyUnavailable("controller", "listener-state-uncertain")


@contextmanager
def _launch_lock(lab):
    import msvcrt
    folder = ROOT / "artifacts/controller-ensure"
    folder.mkdir(parents=True, exist_ok=True)
    handle = (folder / (lab + ".lock")).open("a+b")
    try:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        deadline = time.monotonic() + 10
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise DependencyUnavailable("controller", "startup-already-in-progress")
                time.sleep(0.15)
        try:
            yield folder
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def _probe(config):
    # The local API must return an authenticated status, not merely open a port.
    import scripts.control_client as cli
    try:
        response = cli.ControlClient(config).request("/api/status", method="GET")
    except cli.ClientError:
        if _listening(config.ui_port):
            raise DependencyUnavailable("controller", "existing-endpoint-unhealthy") from None
        return None
    if not isinstance(response, dict) or not isinstance(response.get("host"), dict):
        raise DependencyUnavailable("controller", "invalid-status-response")
    return response


def _launch(lab, config, folder):
    if os.name != "nt":
        raise DependencyUnavailable("controller", "windows-required")
    _require_uncontained()
    if not QUEUE.is_file() or not ENTRY.is_file():
        raise DependencyUnavailable("controller", "required-queue-or-launcher-missing")
    if _listening(config.ui_port):
        raise DependencyUnavailable("controller", "endpoint-owned-by-another-process")
    if config.vmx is None or config.vmrun is None or config.vnc_port is None:
        raise DependencyUnavailable("controller", "vm-identity-config-missing")
    try:
        identity = VmEpochGuard(config).collect()
        hashes = {name: _sha(ROOT / name) for name in RUNTIME_FILES}
        session = _session_id()
    except DependencyUnavailable:
        raise
    except Exception:
        raise DependencyUnavailable("controller", "vm-or-source-preflight-failed") from None
    path = folder / (lab + "-" + uuid4().hex)
    path.mkdir(mode=0o700)
    plan = {
        "schemaVersion": 1, "configPath": str(CONFIGS[lab].resolve()),
        "configSha256": _sha(CONFIGS[lab]), "database": str(QUEUE.resolve()),
        "resource": "vm:rift-lab-" + lab[-1],
        "shutdownFile": str(path / "stop.request"),
        "vmIdentity": identity, "runtimeHashes": hashes,
        "expectedWindowsSession": session,
        "createdUtc": datetime.now(timezone.utc).isoformat(),
    }
    plan_path = path / "plan.json"
    with plan_path.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise DependencyUnavailable("controller", "pythonw-unavailable")
    try:
        with (path / "bootstrap.stderr.log").open("x", encoding="utf-8") as diagnostic:
            process = subprocess.Popen([str(pythonw), str(ENTRY), str(plan_path)],
                                       cwd=str(ROOT),
                                       creationflags=(subprocess.DETACHED_PROCESS
                                                      | subprocess.CREATE_NEW_PROCESS_GROUP),
                                       stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=diagnostic,
                                       close_fds=True)
    except OSError:
        raise DependencyUnavailable("controller", "detached-startup-refused") from None
    return process.pid


def ensure(lab, *, timeout_seconds=20):
    """Reuse or start one controller; never infer guest readiness from host startup."""
    if lab not in CONFIGS:
        raise DependencyUnavailable("controller", "unknown-lab")
    if not 1 <= timeout_seconds <= 60:
        raise DependencyUnavailable("controller", "invalid-timeout")
    try:
        config = HostConfig.load(CONFIGS[lab])
        status = _probe(config)
        if status is not None:
            return {"lab": lab, "state": "reused", "status": status}
        with _launch_lock(lab) as folder:
            status = _probe(config)  # Recheck under the launch lock.
            if status is not None:
                return {"lab": lab, "state": "reused", "status": status}
            pid = _launch(lab, config, folder)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(0.3)
                status = _probe(config)
                if status is not None:
                    return {"lab": lab, "state": "started", "pid": pid, "status": status}
            raise DependencyUnavailable("controller", "startup-timeout-or-exited")
    except DependencyUnavailable:
        raise
    except (OSError, ValueError):
        raise DependencyUnavailable("controller", "preflight-failed") from None
