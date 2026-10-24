"""V2-owned, bounded VMware console capture and bootstrap helper.

This module intentionally has no runtime dependency on RiftReader V1 source.
It does retain one compatibility decision: the VNC password is derived from the
existing Windows Credential Manager entry named ``VMware Encrypted VM: `` plus
the normalized VMX path, using the HMAC label ``RIFT-Lab local console v1``.
That preserves access to the already-configured local console without storing,
printing, or copying either credential material or VMX contents.

Bootstrap input is limited to Windows Run setup. It cannot express game
movement keys, held keys, arbitrary chords, or relative mouse movement.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time
import threading
from typing import NamedTuple
import uuid


DEFAULT_VMRUN = Path(r"C:\Program Files\VMware\VMware Workstation\vmrun.exe")
DEFAULT_PORT = 5905
MAX_ACTIONS = 32
MAX_TEXT_LENGTH = 2048
MAX_SCREEN_DIMENSION = 16384
HMAC_LABEL = b"RIFT-Lab local console v1"
MUTEX_PREFIX = "Local\\RiftReader.VMConsole."
LOG_PATTERN = re.compile(
    r"(?m)^(?P<epoch>\S+) .*Log for VMware Workstation pid=(?P<pid>\d+) "
)
SHIFTED_ASCII_BASE = {
    "~": "`",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "minus",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
}


class Blocked(RuntimeError):
    """A stable, non-secret reason that an operation cannot continue."""


class Config(NamedTuple):
    vmx: Path
    port: int
    vmrun: Path
    output: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_path(path: Path, *, strict: bool = False) -> Path:
    """Return one absolute, normalized path without reading file contents."""
    try:
        return Path(path).expanduser().resolve(strict=strict)
    except OSError as exc:
        raise Blocked("path-unavailable") from exc


def path_key(path: Path) -> str:
    """Return a stable case-insensitive key for a normalized Windows path."""
    return str(normalized_path(path)).replace("/", "\\").casefold()


def validate_config(
    vmx: Path,
    port: int,
    vmrun: Path,
    output: Path,
    *,
    require_files: bool = False,
) -> Config:
    if type(port) is not int or not 1 <= port <= 65535:
        raise Blocked("invalid-console-port")
    resolved_vmx = normalized_path(vmx, strict=require_files)
    resolved_vmrun = normalized_path(vmrun, strict=require_files)
    resolved_output = normalized_path(output)
    if resolved_vmx.suffix.casefold() != ".vmx":
        raise Blocked("invalid-vmx-path")
    if resolved_vmrun.name.casefold() != "vmrun.exe":
        raise Blocked("invalid-vmrun-path")
    if require_files and (not resolved_vmx.is_file() or not resolved_vmrun.is_file()):
        raise Blocked("required-file-unavailable")
    return Config(resolved_vmx, port, resolved_vmrun, resolved_output)


def parse_vmrun_list(stdout: str) -> list[Path]:
    """Parse only VMX entries from ``vmrun list`` output."""
    if not isinstance(stdout, str):
        raise Blocked("vmrun-list-invalid")
    entries: list[Path] = []
    for line in stdout.splitlines():
        candidate = line.strip()
        if candidate.casefold().endswith(".vmx"):
            entries.append(normalized_path(Path(candidate)))
    return entries


def parse_vmware_log_identity(header: str) -> tuple[str, int]:
    """Extract launch epoch and PID from the bounded vmware.log header."""
    if not isinstance(header, str):
        raise Blocked("vm-log-identity-unavailable")
    match = LOG_PATTERN.search(header)
    if not match:
        raise Blocked("vm-log-identity-unavailable")
    pid = int(match.group("pid"))
    if pid <= 0:
        raise Blocked("vm-log-identity-unavailable")
    epoch = match.group("epoch")
    try:
        parsed = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Blocked("vm-log-identity-unavailable") from exc
    if parsed.tzinfo is None:
        raise Blocked("vm-log-identity-unavailable")
    return epoch, pid


def parse_tcp_listener_rows(table: bytes, port: int) -> list[tuple[str, int]]:
    """Parse matching LISTEN rows from a MIB_TCPTABLE_OWNER_PID byte buffer."""
    if len(table) < 4:
        raise Blocked("listener-query-invalid")
    count = struct.unpack_from("<I", table)[0]
    expected = 4 + count * 24
    if expected > len(table):
        raise Blocked("listener-query-invalid")
    matches: list[tuple[str, int]] = []
    for index in range(count):
        state, address, local_port, _, _, pid = struct.unpack_from(
            "<6I", table, 4 + index * 24
        )
        if state != 2 or socket.ntohs(local_port & 0xFFFF) != port:
            continue
        ip = socket.inet_ntoa(struct.pack("<I", address))
        matches.append((ip, pid))
    return matches


def _kernel32():
    if os.name != "nt":
        raise Blocked("windows-required")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    return api


def process_identity(pid: int) -> dict:
    api = _kernel32()
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        raise Blocked("process-unavailable")
    try:
        api.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            raise Blocked("process-image-unavailable")
        times = [wintypes.FILETIME() for _ in range(4)]
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)
        ] * 4
        if not api.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise Blocked("process-start-unavailable")
        return {
            "pid": pid,
            "image": str(normalized_path(Path(buffer.value))),
            "startTicks": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
        }
    finally:
        api.CloseHandle(handle)


def listener_owner(port: int) -> int:
    if os.name != "nt":
        raise Blocked("windows-required")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if not size.value:
        raise Blocked("listener-query-failed")
    data = ctypes.create_string_buffer(size.value)
    if get_table(data, ctypes.byref(size), False, socket.AF_INET, 3, 0):
        raise Blocked("listener-query-failed")
    matches = parse_tcp_listener_rows(bytes(data.raw[: size.value]), port)
    if any(ip != "127.0.0.1" for ip, _ in matches):
        raise Blocked("console-not-loopback-only")
    owners = [pid for ip, pid in matches if ip == "127.0.0.1"]
    if len(owners) != 1:
        raise Blocked("console-listener-not-unique")
    return owners[0]


def _log_identity(vmx: Path) -> tuple[str, int]:
    try:
        with vmx.with_name("vmware.log").open(
            encoding="utf-8", errors="replace"
        ) as stream:
            header = stream.read(8192)
    except OSError as exc:
        raise Blocked("vm-log-identity-unavailable") from exc
    return parse_vmware_log_identity(header)


def _binding_files(vmx: Path) -> tuple:
    try:
        vmx_stat = vmx.stat()
        log = vmx.with_name("vmware.log").resolve(strict=True)
        log_stat = log.stat()
    except OSError as exc:
        raise Blocked("vm-binding-file-identity-unavailable") from exc
    if not vmx_stat.st_ino or not log_stat.st_ino:
        raise Blocked("vm-binding-file-identity-unavailable")
    return (
        path_key(vmx),
        vmx_stat.st_dev,
        vmx_stat.st_ino,
        path_key(log),
        log_stat.st_dev,
        log_stat.st_ino,
        _log_identity(vmx),
    )


def _direct_identity(config: Config) -> dict:
    """Read the current pinned epoch without invoking ``vmrun``."""
    files_before = _binding_files(config.vmx)
    epoch, pid = _log_identity(config.vmx)
    process = process_identity(pid)
    expected_image = normalized_path(config.vmrun.parent / "x64" / "vmware-vmx.exe")
    if path_key(Path(process["image"])) != path_key(expected_image):
        raise Blocked("unexpected-console-process")
    owner = listener_owner(config.port)
    if owner != pid:
        raise Blocked("listener-vm-mismatch")
    process_after = process_identity(pid)
    if process_after != process or _log_identity(config.vmx) != (epoch, pid):
        raise Blocked("vm-process-identity-drift")
    launched = datetime.fromisoformat(epoch.replace("Z", "+00:00")).timestamp()
    created = process["startTicks"] / 10_000_000 - 11_644_473_600
    if not 0 <= launched - created < 10:
        raise Blocked("vm-log-process-epoch-mismatch")
    if _binding_files(config.vmx) != files_before:
        raise Blocked("vm-binding-files-drift")
    return {
        "vmx": path_key(config.vmx),
        "port": config.port,
        "logEpoch": epoch,
        "listenerPid": owner,
        **process,
    }


def collect_identity(config: Config) -> dict:
    """Initially bind vmrun membership, then return the exact direct identity."""
    files_before = _binding_files(config.vmx)
    try:
        result = subprocess.run(
            [str(config.vmrun), "list"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=0x08000000,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Blocked("vmrun-list-failed") from exc
    if result.returncode:
        raise Blocked("vmrun-list-failed")
    running = parse_vmrun_list(result.stdout)
    target = path_key(config.vmx)
    matches = [item for item in running if path_key(item) == target]
    if len(matches) != 1:
        raise Blocked("target-vm-not-running")
    target_parent = path_key(config.vmx.parent)
    if any(
        path_key(item) != target and path_key(item.parent) == target_parent
        for item in running
    ):
        raise Blocked("target-vm-shared-log-ambiguous")
    identity = _direct_identity(config)
    if _binding_files(config.vmx) != files_before:
        raise Blocked("vm-binding-files-drift")
    return identity


def verify_identity(config: Config, expected: dict) -> dict:
    """Revalidate one pinned VM epoch without launching ``vmrun``.

    ``expected`` must be the complete dictionary returned by an earlier
    :func:`collect_identity` call in the same control session.
    """
    if not isinstance(expected, dict):
        raise Blocked("invalid-expected-identity")
    current = _direct_identity(config)
    if current != expected:
        raise Blocked("target-drift")
    return dict(current)


def mutex_name(vmx: Path) -> str:
    digest = hashlib.sha256(path_key(vmx).encode("utf-8")).hexdigest()[:24]
    return MUTEX_PREFIX + digest


class ControlMutex:
    """Cross-process Windows mutex shared with the established console tools."""

    def __init__(self, vmx: Path):
        self.name = mutex_name(vmx)
        self.handle = None
        self.api = None
        self.owner_thread = None
        self.abandoned = False

    def __enter__(self):
        if self.handle is not None:
            raise Blocked("controller-lock-already-owned")
        self.api = _kernel32()
        self.api.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise Blocked("controller-lock-unavailable")
        outcome = self.api.WaitForSingleObject(self.handle, 0)
        if outcome not in (0, 0x80):
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise Blocked("controller-busy")
        self.owner_thread = threading.current_thread()
        self.abandoned = outcome == 0x80
        return self

    def __exit__(self, *_):
        if self.handle:
            if threading.current_thread() is not self.owner_thread:
                raise Blocked("controller-lock-wrong-thread")
            if not self.api.ReleaseMutex(self.handle):
                raise Blocked("controller-lock-release-failed")
            self.api.CloseHandle(self.handle)
            self.handle = None


def console_password(vmx: Path) -> str:
    """Derive the compatible VNC secret in memory; never persist or report it."""
    if os.name != "nt":
        raise Blocked("windows-required")

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("BlobSize", wintypes.DWORD),
            ("Blob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    api.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.POINTER(Credential)()
    target = "VMware Encrypted VM: " + str(normalized_path(vmx, strict=True))
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        raise Blocked("saved-vm-credential-unavailable")
    try:
        item = pointer.contents
        raw = ctypes.string_at(item.Blob, item.BlobSize)
        encoding = "utf-16-le" if len(raw) % 2 == 0 and raw[1:2] == b"\x00" else "utf-8"
        secret = raw.decode(encoding).rstrip("\x00").encode("utf-8")
        digest = hmac.new(secret, HMAC_LABEL, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")[:8]
    except (UnicodeError, ValueError) as exc:
        raise Blocked("saved-vm-credential-invalid") from exc
    finally:
        api.CredFree(pointer)


def connect(config: Config):
    try:
        import warnings

        warnings.filterwarnings("ignore", message="TripleDES has been moved.*")
        from vncdotool import api

        return api.connect(
            f"127.0.0.1::{config.port}",
            password=console_password(config.vmx),
            timeout=3,
        )
    except Blocked:
        raise
    except BaseException as exc:
        # Transport exception text is deliberately discarded because dependencies
        # may include authentication material in diagnostic strings.
        raise Blocked("console-connect-failed") from exc


def _require_exact_fields(action: dict, allowed: set[str]) -> None:
    if set(action) != allowed:
        raise Blocked("invalid-bootstrap-action-fields")


def _validate_text(value) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_TEXT_LENGTH:
        raise Blocked("invalid-bootstrap-text")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise Blocked("invalid-bootstrap-text")
    return value


def validate_actions(payload, screen_size: tuple[int, int] | None = None) -> list[dict]:
    """Validate the complete bounded bootstrap plan before sending any input."""
    if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "actions"}:
        raise Blocked("invalid-bootstrap-plan")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise Blocked("unsupported-bootstrap-schema")
    actions = payload["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise Blocked("invalid-bootstrap-actions")
    width, height = screen_size or (MAX_SCREEN_DIMENSION, MAX_SCREEN_DIMENSION)
    if (
        type(width) is not int
        or type(height) is not int
        or not 1 <= width <= MAX_SCREEN_DIMENSION
        or not 1 <= height <= MAX_SCREEN_DIMENSION
    ):
        raise Blocked("invalid-screen-size")
    run_open = False
    text_used = False
    total_text = 0
    validated: list[dict] = []
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("type"), str):
            raise Blocked("invalid-bootstrap-action")
        kind = action["type"]
        if kind == "windowsRunText":
            _require_exact_fields(action, {"type", "text"})
            text = _validate_text(action["text"])
            total_text += len(text)
            run_open = False
            text_used = False
        elif kind == "keyChord":
            _require_exact_fields(action, {"type", "keys"})
            keys = action["keys"]
            if keys == ["super", "r"]:
                run_open = True
                text_used = False
            elif keys == ["alt", "tab"]:
                run_open = False
                text_used = False
            else:
                raise Blocked("unsupported-bootstrap-key-chord")
        elif kind == "keyPress":
            _require_exact_fields(action, {"type", "key"})
            if action["key"] not in ("enter", "esc"):
                raise Blocked("unsupported-bootstrap-key")
            run_open = False
            text_used = False
        elif kind == "text":
            _require_exact_fields(action, {"type", "text"})
            if not run_open or text_used:
                raise Blocked("bootstrap-text-requires-windows-run")
            text = _validate_text(action["text"])
            total_text += len(text)
            text_used = True
        elif kind == "click":
            _require_exact_fields(action, {"type", "x", "y", "button"})
            x, y, button = action["x"], action["y"], action["button"]
            if (
                type(x) is not int
                or type(y) is not int
                or type(button) is not int
                or button != 1
                or not 0 <= x < width
                or not 0 <= y < height
            ):
                raise Blocked("invalid-bootstrap-click")
            run_open = False
            text_used = False
        else:
            raise Blocked("unsupported-bootstrap-action")
        if total_text > MAX_TEXT_LENGTH:
            raise Blocked("invalid-bootstrap-text")
        validated.append(dict(action))
    return validated


def load_actions(path: Path) -> list[dict]:
    try:
        payload = json.loads(normalized_path(path, strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Blocked("bootstrap-plan-unavailable") from exc
    return validate_actions(payload)


def text_keypress(character: str) -> str:
    """Map one validated ASCII character to a US-keyboard VNC key chord."""
    if not isinstance(character, str) or len(character) != 1:
        raise Blocked("invalid-bootstrap-text-character")
    if "A" <= character <= "Z":
        return "shift-" + character.casefold()
    if character in SHIFTED_ASCII_BASE:
        return "shift-" + SHIFTED_ASCII_BASE[character]
    if character == "-":
        return "minus"
    return character


def _type_text(client, value: str) -> None:
    for character in value:
        client.keyPress(text_keypress(character))


def execute_actions(client, actions: list[dict]) -> None:
    for action in actions:
        kind = action["type"]
        if kind == "windowsRunText":
            client.keyPress("super-r")
            time.sleep(0.25)
            _type_text(client, action["text"])
            client.keyPress("enter")
        elif kind == "keyChord":
            client.keyPress("-".join(action["keys"]))
        elif kind == "keyPress":
            client.keyPress(action["key"])
        elif kind == "text":
            _type_text(client, action["text"])
        elif kind == "click":
            client.mouseMove(action["x"], action["y"])
            client.mousePress(action["button"])
        time.sleep(0.25)


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_output(output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    screen = output / "screen.png"
    identity = output / "identity.json"
    if screen.exists() or identity.exists():
        raise Blocked("output-already-exists")
    return screen, identity


def _capture(client, destination: Path) -> tuple[int, int]:
    temporary = destination.with_name("." + destination.name + "." + uuid.uuid4().hex)
    try:
        client.captureScreen(str(temporary), format="PNG")
        from PIL import Image

        with Image.open(temporary) as image:
            image.verify()
        with Image.open(temporary) as image:
            size = image.size
        if not all(type(item) is int and 1 <= item <= MAX_SCREEN_DIMENSION for item in size):
            raise Blocked("invalid-screen-size")
        os.replace(temporary, destination)
        return size
    except Blocked:
        raise
    except BaseException as exc:
        raise Blocked("screen-capture-failed") from exc
    finally:
        temporary.unlink(missing_ok=True)


def run(config: Config, command: str, actions: list[dict] | None = None) -> dict:
    screen_path, identity_path = _prepare_output(config.output)
    report = {
        "schemaVersion": 1,
        "command": command,
        "startedAtUtc": utc_now(),
        "status": "failed",
        "inputSent": False,
        "inputMayHaveBeenSent": False,
        "before": None,
        "after": None,
        "screen": str(screen_path),
    }
    with ControlMutex(config.vmx):
        report["before"] = collect_identity(config)
        operation_error: Blocked | None = None
        client = None
        try:
            client = connect(config)
            if command == "bootstrap":
                preflight = config.output / (".preflight." + uuid.uuid4().hex + ".png")
                try:
                    size = _capture(client, preflight)
                    validated = validate_actions(
                        {"schemaVersion": 1, "actions": actions}, size
                    )
                    report["inputMayHaveBeenSent"] = True
                    execute_actions(client, validated)
                    report["inputSent"] = True
                    report["actionCount"] = len(validated)
                finally:
                    preflight.unlink(missing_ok=True)
            _capture(client, screen_path)
        except Blocked as exc:
            operation_error = exc
        except BaseException as exc:
            operation_error = Blocked("console-operation-failed")
            operation_error.__cause__ = exc
        finally:
            if client is not None:
                if not screen_path.exists():
                    try:
                        _capture(client, screen_path)
                    except Blocked as exc:
                        if operation_error is None:
                            operation_error = exc
                try:
                    client.disconnect()
                except BaseException:
                    pass
        after_error: Blocked | None = None
        try:
            report["after"] = collect_identity(config)
        except Blocked as exc:
            after_error = exc
        report["completedAtUtc"] = utc_now()
        if operation_error is not None:
            report["status"] = "blocked"
            report["reason"] = str(operation_error)
            _atomic_json(identity_path, report)
            raise operation_error
        if after_error is not None:
            report["status"] = "blocked"
            report["reason"] = str(after_error)
            _atomic_json(identity_path, report)
            raise after_error
        if report["after"] != report["before"]:
            report["status"] = "target-drift"
            _atomic_json(identity_path, report)
            raise Blocked("target-drift")
        report["status"] = "completed"
        _atomic_json(identity_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vmx", required=True, type=Path)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--vmrun", type=Path, default=DEFAULT_VMRUN)
    parser.add_argument("--output", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capture")
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--actions", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = validate_config(
            args.vmx, args.port, args.vmrun, args.output, require_files=True
        )
        actions = load_actions(args.actions) if args.command == "bootstrap" else None
        report = run(config, args.command, actions)
        print(json.dumps({"status": report["status"], "output": str(config.output)}))
        return 0
    except Blocked as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2
    except BaseException:
        print(json.dumps({"status": "failed", "reason": "unexpected-error"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
