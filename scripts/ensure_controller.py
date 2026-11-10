"""On-demand, owned per-lab RIFT controller lifecycle through RR2 helpers.

The RR2 helper manager provides a Limited/Interactive, no-logon-
trigger, unlimited-lifetime, IgnoreNew Windows task; its source and owner
registration are checked on every call. No VM/game startup or game input.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

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
ENTRY = ROOT / "scripts/controller_task_entry.py"
MANAGER = ROOT / "scripts" / "Manage-RR2HelperTask.ps1"
RUNTIME_FILES = (
    "scripts/control_host.py", "scripts/vm_console_native.py",
    "scripts/nav_host_runtime.py", "scripts/nav_access_queue.py",
    "scripts/nav_supervisor_bootstrap.py", "scripts/nav_control_watchdog.py",
    "scripts/nav_startup_preflight.py", "scripts/control_panel.html",
    "scripts/controller_task_entry.py",
)


def _session_id():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    current = wintypes.DWORD()
    if not api.ProcessIdToSessionId(os.getpid(), ctypes.byref(current)) or current.value == 0:
        raise DependencyUnavailable("controller", "interactive-windows-session-required")
    return current.value


def _listening(port):
    # Windows timeout-mode connect_ex can return 10035 for a closed loopback port.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            code = connection.connect_ex(("127.0.0.1", port))
    except OSError:
        raise DependencyUnavailable("controller", "listener-state-uncertain") from None
    if code == 0:
        return True
    if code in (10061, 111):
        return False
    if code == 10035:
        # Windows can report WSAEWOULDBLOCK for a *closed* loopback port.
        # Only a successfully queried, exact-port LISTEN table can clear that
        # ambiguity; never infer absence from a failed or nonloopback query.
        from scripts.vm_console_native import Blocked, tcp_listener_rows
        try:
            rows = tcp_listener_rows(port)
        except (Blocked, OSError, ValueError):
            raise DependencyUnavailable("controller", "listener-state-uncertain") from None
        if (type(rows) is not list or len(rows) > 1
                or any(address != "127.0.0.1" or type(pid) is not int or pid <= 0
                       for address, pid in rows)):
            raise DependencyUnavailable("controller", "listener-state-uncertain")
        return bool(rows)
    raise DependencyUnavailable("controller", "listener-state-uncertain")


@contextmanager
def _launch_lock(lab, *, timeout_seconds=10):
    import msvcrt
    folder = ROOT / "artifacts/controller-ensure"
    folder.mkdir(parents=True, exist_ok=True)
    handle = (folder / (lab + ".lock")).open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
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
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def _probe(config):
    import scripts.control_client as cli
    try:
        response = cli.ControlClient(config).request("/api/status", method="GET")
    except cli.ClientError:
        if _listening(config.ui_port):
            raise DependencyUnavailable("controller", "existing-endpoint-unhealthy") from None
        return None
    if not isinstance(response, dict) or not isinstance(response.get("host"), dict):
        raise DependencyUnavailable("controller", "invalid-status-response")
    # An authenticated HTTP listener can outlive its safety supervisor. Never
    # report such an endpoint as healthy or replace its still-held owner.
    coordination = response["host"].get("coordination")
    if not isinstance(coordination, dict):
        raise DependencyUnavailable("controller", "coordination-status-missing")
    supervisor = coordination.get("supervisor")
    if (coordination.get("state") == "blocked"
            or coordination.get("errorCode") is not None
            or isinstance(supervisor, dict) and supervisor.get("state") == "blocked"):
        raise DependencyUnavailable("controller", "supervision-blocked")
    return response


def _controller_pythonw() -> Path:
    # Scheduled task registration must be stable across system and venv callers.
    return Path(sys.base_prefix) / "pythonw.exe"


def _launch(lab, config):
    if os.name != "nt":
        raise DependencyUnavailable("controller", "windows-required")
    if not QUEUE.is_file() or not ENTRY.is_file() or not MANAGER.is_file():
        raise DependencyUnavailable("controller", "helper-or-queue-unavailable")
    if _listening(config.ui_port):
        raise DependencyUnavailable("controller", "endpoint-owned-by-another-process")
    if config.vmx is None or config.vmrun is None or config.vnc_port is None:
        raise DependencyUnavailable("controller", "vm-identity-config-missing")
    try:
        # Preflight now; the persistent helper independently reacquires VM identity.
        VmEpochGuard(config).collect()
        _session_id()
    except DependencyUnavailable:
        raise
    except Exception:
        raise DependencyUnavailable("controller", "vm-preflight-failed") from None
    pythonw = _controller_pythonw()
    if not pythonw.is_file():
        raise DependencyUnavailable("controller", "pythonw-unavailable")
    helper = "rr2-controller-" + lab
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    script = (
        "$ErrorActionPreference='Stop';"
        "$manager=" + quote(MANAGER) + ";"
        "& $manager -Action Register -HelperId " + quote(helper)
        + " -Executable " + quote(pythonw)
        + " -Argument @(" + ",".join(map(quote, (ENTRY, "--lab", lab))) + ")"
        + " -WorkingDirectory " + quote(ROOT) + " | Out-Null;"
        "& $manager -Action Start -HelperId " + quote(helper) + " | Out-Null;"
    )
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    import base64
    try:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "RemoteSigned", "-EncodedCommand", encoded],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True,
            timeout=35, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DependencyUnavailable("controller", "managed-helper-command-failed") from None
    if result.returncode:
        raise DependencyUnavailable("controller", "managed-helper-registration-refused") from None
    return helper


def _verify_existing_owner(lab, config):
    """Bind the authenticated listener to one exact managed generation."""
    from scripts.managed_controller_receipt import (
        ManagedReceiptError, resolve_current_managed_controller,
    )
    from scripts.vm_console_native import listener_owner
    try:
        _, receipt, _ = resolve_current_managed_controller(lab)
        if listener_owner(config.ui_port) != receipt["pid"]:
            raise ValueError("listener PID differs")
    except ManagedReceiptError as error:
        # Preserve only fixed lifecycle diagnostics, never arbitrary exception
        # text. This does not retry, replace a controller, or relax admission.
        reason = str(error)
        if reason not in {
            "managed-live-generation-absent", "managed-live-generation-not-unique",
            "managed-live-generation-exiting", "managed-process-identity-uncertain",
            "managed-runtime-changed",
        }:
            reason = "managed-owner-refused"
        raise DependencyUnavailable("controller", reason) from None
    except Exception:
        raise DependencyUnavailable("controller", "managed-owner-refused") from None


def ensure_existing(lab):
    """Verify an existing managed endpoint without starting a controller."""
    if lab not in CONFIGS:
        raise DependencyUnavailable("controller", "unknown-lab")
    try:
        config = HostConfig.load(CONFIGS[lab])
        status = _probe(config)
        if status is None:
            raise DependencyUnavailable("controller", "existing-endpoint-missing")
        _verify_existing_owner(lab, config)
        return {"lab": lab, "state": "reused", "status": status}
    except DependencyUnavailable:
        raise
    except (OSError, ValueError):
        raise DependencyUnavailable("controller", "preflight-failed") from None


def ensure(lab, *, timeout_seconds=40):
    """Use/recover a controller endpoint; guest telemetry is a separate dependency."""
    if lab not in CONFIGS:
        raise DependencyUnavailable("controller", "unknown-lab")
    if not 1 <= timeout_seconds <= 60:
        raise DependencyUnavailable("controller", "invalid-timeout")
    try:
        config = HostConfig.load(CONFIGS[lab])
        status = _probe(config)
        if status is not None:
            _verify_existing_owner(lab, config)
            return {"lab": lab, "state": "reused", "status": status}
        with _launch_lock(lab):
            status = _probe(config)
            if status is not None:
                _verify_existing_owner(lab, config)
                return {"lab": lab, "state": "reused", "status": status}
            helper = _launch(lab, config)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(0.35)
                try:
                    status = _probe(config)
                except DependencyUnavailable as error:
                    # A newly listening API can briefly refuse a request while
                    # completing initialization. Never start another owner;
                    # wait for authenticated health or expire this one deadline.
                    if error.code != "existing-endpoint-unhealthy":
                        raise
                    continue
                if status is not None:
                    _verify_existing_owner(lab, config)
                    return {"lab": lab, "state": "started", "helper": helper, "status": status}
            raise DependencyUnavailable("controller", "managed-helper-not-ready")
    except DependencyUnavailable:
        raise
    except (OSError, ValueError):
        raise DependencyUnavailable("controller", "preflight-failed") from None
