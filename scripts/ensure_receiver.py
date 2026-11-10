"""Idempotent on-demand host-only observation receiver for each RIFT lab.

The receiver is a read-only POST sink. Managed Task Scheduler ownership survives
a bounded Workbridge invocation without boot triggers or detached child processes.
No game input, VM start, reader binding, or credential prompting occurs here.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import ipaddress
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.operation_dependencies import DependencyUnavailable
from scripts.vm_console_native import (
    TCP_TABLE_OWNER_PID_LISTENER, parse_tcp_listener_rows,
)

CONFIGS = {
    lab: ROOT / ".local" / "two-lab-movement" / (lab + "-receiver.json")
    for lab in ("lab1", "lab2")
}
PORTS = {"lab1": 49813, "lab2": 49923}
BIND = "192.168.56.1"
SOURCE = ROOT / "scripts" / "observation_receiver.py"
SOURCE_SHA256 = "9D054B6A4EF183607EBCCAC8EF3662F28314214E9BD74B115724BD8AEDD95038"
MANAGER = ROOT / "scripts" / "Manage-RR2HelperTask.ps1"
LEGACY_INSPECTOR = ROOT / "scripts" / "Verify-RR2LegacyHelperTask.ps1"
ENTRY = ROOT / "scripts" / "receiver_task_entry.py"
TASKS = ROOT / "artifacts" / "receiver-tasks"
WINDOWS_TICKS_OFFSET = 504_911_232_000_000_000


def _blocked(code):
    raise DependencyUnavailable("receiver", code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _config(lab):
    if lab not in CONFIGS:
        _blocked("unknown-lab")
    path = CONFIGS[lab]
    if not path.is_file() or path.stat().st_size > 65_536:
        _blocked("private-config-unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        address = ipaddress.ip_address(value["bindAddress"])
        subnet = ipaddress.ip_network(value["guestSubnet"], strict=True)
        if (str(address) != BIND or value["port"] != PORTS[lab]
                or type(value["port"]) is not int or address not in subnet
                or subnet.prefixlen < 24
                or not isinstance(value["token"], str)
                or not 32 <= len(value["token"]) <= 512):
            _blocked("private-config-mismatch")
    except (OSError, ValueError, TypeError, KeyError):
        _blocked("private-config-invalid")
    if not SOURCE.is_file() or sha(SOURCE) != SOURCE_SHA256:
        _blocked("receiver-source-drift")
    if not ENTRY.is_file() or not MANAGER.is_file():
        _blocked("managed-helper-unavailable")
    return path


def _port_owners(port):
    """Read listener-filtered Windows TCP rows without making a dummy HTTP request."""
    if os.name != "nt":
        _blocked("windows-required")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET,
              TCP_TABLE_OWNER_PID_LISTENER, 0)
    if size.value < 4:
        _blocked("listener-query-unavailable")
    data = ctypes.create_string_buffer(size.value)
    if get_table(data, ctypes.byref(size), False, socket.AF_INET,
                 TCP_TABLE_OWNER_PID_LISTENER, 0):
        _blocked("listener-query-unavailable")
    return parse_tcp_listener_rows(bytes(data.raw[:size.value]), port, listener_table=True)


def _valid_instance_guid(value):
    from uuid import UUID
    try:
        return isinstance(value, str) and UUID(value).int != 0
    except (ValueError, AttributeError):
        return False


def _task_status(lab, expected_pid):
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "RemoteSigned", "-File", str(MANAGER), "-Action", "Status",
         "-HelperId", "rr2-receiver-" + lab],
        cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True,
        timeout=20, check=False,
    )
    if result.returncode:
        _blocked("managed-helper-ownership-refused")
    try:
        status = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        _blocked("managed-helper-status-invalid")
    if not isinstance(status, dict):
        _blocked("managed-helper-status-invalid")
    if (status.get("state") != "Running"
            or status.get("atLogon") is not False
            or status.get("runLevel") != "Limited"
            or type(status.get("enginePid")) is not int or status["enginePid"] != expected_pid
            or not _valid_instance_guid(status.get("instanceGuid"))):
        _blocked("managed-helper-not-running-or-not-on-demand")
    return status


def _legacy_task_status(lab, receiver):
    """Read-only verification for an already-running legacy task owner."""
    image = receiver.get("image")
    if not isinstance(image, str) or not image or not LEGACY_INSPECTOR.is_file():
        _blocked("receiver-legacy-ownership-unavailable")
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
             "RemoteSigned", "-File", str(LEGACY_INSPECTOR),
             "-HelperId", "rr2-receiver-" + lab, "-Executable", image],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True,
            timeout=20, check=False,
        )
        status = json.loads(result.stdout.decode("utf-8-sig")) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        _blocked("receiver-legacy-ownership-refused")
    if (not isinstance(status, dict) or status.get("helperId") != "rr2-receiver-" + lab
            or status.get("ownership") != "verified-legacy-read-only"
            or status.get("state") != "Running" or status.get("atLogon") is not False
            or status.get("runLevel") != "Limited"
            or type(status.get("enginePid")) is not int or status["enginePid"] != receiver.get("pid")
            or not _valid_instance_guid(status.get("instanceGuid"))):
        _blocked("receiver-legacy-ownership-refused")
    return status


def _matching_receipt(lab, receiver, config_path):
    base = TASKS / lab
    if not base.is_dir():
        return False
    candidates = sorted(base.glob("*/process.json"), key=lambda p: p.stat().st_mtime,
                        reverse=True)[:64]
    for file in candidates:
        try:
            if file.stat().st_size > 65_536:
                continue
            value = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                continue
            identity = value["processIdentity"]
            if (not isinstance(identity, dict)
                    or not isinstance(identity.get("image"), str)):
                continue
            if (value.get("lab") == lab
                    and value.get("pid") == receiver["pid"]
                    and value.get("configSha256") == sha(config_path)
                    and value.get("sourceSha256") == SOURCE_SHA256
                    and value.get("entrySha256") == sha(ENTRY)
                    and int(identity["startTicks"]) + WINDOWS_TICKS_OFFSET
                        == int(receiver["processStartUtcTicks"])
                    and identity["image"].casefold() == receiver["image"].casefold()):
                return True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return False


def _probe(lab, config_path):
    owners = _port_owners(PORTS[lab])
    if not owners:
        return None
    if len(owners) != 1 or owners[0][0] != BIND or owners[0][1] <= 0:
        _blocked("receiver-listener-collision")
    from scripts.launch_live_reader import receiver_preflight
    try:
        receiver, _token, _endpoint = receiver_preflight(config_path)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        _blocked("receiver-listener-unhealthy")
    if receiver["pid"] != owners[0][1]:
        _blocked("receiver-listener-owner-drift")
    if not _matching_receipt(lab, receiver, config_path):
        _blocked("receiver-listener-not-owned-by-task")
    try:
        _task_status(lab, receiver["pid"])
    except DependencyUnavailable:
        # Only a matching live process receipt may reach the read-only legacy
        # verifier. Startup itself never uses or starts the legacy task.
        _legacy_task_status(lab, receiver)
    return receiver


@contextmanager
def _launch_lock(lab, *, timeout_seconds=10):
    folder = ROOT / "artifacts" / "receiver-ensure"
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
                    _blocked("startup-already-in-progress")
                time.sleep(0.15)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def _receiver_pythonw() -> Path:
    # The managed task is registered against the stable base interpreter, not
    # whichever virtualenv happens to invoke this helper today.
    return Path(sys.base_prefix) / "pythonw.exe"


def _launch(lab):
    if _port_owners(PORTS[lab]):
        _blocked("receiver-port-already-owned")
    pythonw = _receiver_pythonw()
    if not pythonw.is_file():
        _blocked("pythonw-unavailable")
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    helper = "rr2-receiver-" + lab
    command = (
        "$ErrorActionPreference='Stop';"
        "$manager=" + quote(MANAGER) + ";"
        "& $manager -Action Register -HelperId " + quote(helper)
        + " -Executable " + quote(pythonw)
        + " -Argument @(" + ",".join(map(quote, (ENTRY, "--lab", lab))) + ")"
        + " -WorkingDirectory " + quote(ROOT) + " | Out-Null;"
        "& $manager -Action Start -HelperId " + quote(helper) + " | Out-Null;"
    )
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
             "RemoteSigned", "-EncodedCommand", encoded],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True,
            timeout=35, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _blocked("managed-helper-command-failed")
    if result.returncode:
        _blocked("managed-helper-registration-refused")
    return helper


def ensure(lab, *, timeout_seconds=40):
    """Recover only the exact receiver of this lab; freshness is checked later."""
    if not 1 <= timeout_seconds <= 60:
        _blocked("invalid-timeout")
    config_path = _config(lab)
    try:
        receiver = _probe(lab, config_path)
        if receiver is not None:
            return {"lab": lab, "state": "reused", "receiver": receiver}
        with _launch_lock(lab):
            receiver = _probe(lab, config_path)
            if receiver is not None:
                return {"lab": lab, "state": "reused", "receiver": receiver}
            helper = _launch(lab)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(0.35)
                receiver = _probe(lab, config_path)
                if receiver is not None:
                    return {"lab": lab, "state": "started", "helper": helper,
                            "receiver": receiver}
            _blocked("managed-helper-not-ready")
    except DependencyUnavailable:
        raise
    except (OSError, ValueError, subprocess.TimeoutExpired):
        _blocked("preflight-failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2", "all"), required=True)
    args = parser.parse_args()
    labs = list(PORTS) if args.lab == "all" else [args.lab]
    failed = False
    for lab in labs:
        try:
            result = ensure(lab)
            print(json.dumps({"lab": lab, "state": result["state"],
                              "receiverPid": result["receiver"]["pid"],
                              "address": BIND, "port": PORTS[lab],
                              "feedFreshness": "not-verified"}), flush=True)
        except DependencyUnavailable as error:
            print(json.dumps({"lab": lab, "state": "blocked",
                              "dependency": error.name, "reason": error.code}), flush=True)
            failed = True
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
