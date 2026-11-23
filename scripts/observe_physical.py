"""Explicit physical RIFT screenshot through the deployed Workbridge desktop turn."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(r"C:\work\workbridge-mcp")
NODE = Path(r"C:\Program Files\nodejs\node.exe")
MIN_WORKBRIDGE_NODE_MAJOR = 24
WORKBRIDGE_WINAPP_REASONS = ("WINAPP_NOT_INSTALLED", "UNSUPPORTED_WINAPP_VERSION", "WINAPP_VERSION_CHECK_FAILED")
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
MAX_OUTPUT = 12 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def valid_host_name(value):
    return (isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", value) is not None)


def _plain_path(path):
    """Reject links/reparse points, including ancestors; do not resolve them away."""
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            _require(not item.is_symlink() and not getattr(info, "st_file_attributes", 0) & 1024,
                     "reparse-path")


def _local_absolute_path(value, reason):
    path = Path(value)
    _require(path.is_absolute() and not path.drive.startswith(("\\", "/"))
             and ".." not in path.parts, reason)
    _plain_path(path)
    return path


def published_physical_tool(relative_path):
    """Resolve one executable in the bundle produced by publish-physical-tools.ps1."""
    root = os.environ.get("RR2_PHYSICAL_TOOLS_ROOT")
    if root == "debug":
        return None
    if not root:
        registration = ROOT / ".local" / "physical-tools.json"
        if not registration.exists() and not registration.is_symlink():
            return None
        _plain_path(registration)
        _require(registration.is_file(), "invalid-physical-tools-registration")
        with registration.open("rb") as stream:
            raw = stream.read(16385)
        _require(0 < len(raw) <= 16384, "invalid-physical-tools-registration")
        try:
            settings = json.loads(raw)
        except ValueError as error:
            raise ValueError("invalid-physical-tools-registration") from error
        _require(isinstance(settings, dict) and settings.get("schema") == "rr2-physical-tools/1"
                 and valid_host_name(settings.get("host")) and isinstance(settings.get("root"), str),
                 "invalid-physical-tools-registration")
        _require(settings["host"].casefold() == socket.gethostname().casefold(),
                 "physical-tools-registration-host-mismatch")
        root = settings["root"]
    return _local_absolute_path(Path(root) / relative_path, "invalid-physical-tools-root")


def _registered_workbridge():
    path = ROOT / ".local" / "workbridge-client.json"
    if not path.exists() and not path.is_symlink():
        return {}
    reason = "invalid-workbridge-client-registration"
    _plain_path(path)
    _require(path.is_file(), reason)
    with path.open("rb") as stream:
        raw = stream.read(16385)
    _require(0 < len(raw) <= 16384, reason)
    try:
        settings = json.loads(raw)
    except ValueError as error:
        raise ValueError(reason) from error
    _require(isinstance(settings, dict) and settings.get("schema") == "rr2.workbridge-client/1"
             and valid_host_name(settings.get("host"))
             and all(isinstance(settings.get(key), str) for key in ("deployment", "cliRoot", "node")), reason)
    _require(settings["host"].casefold() == socket.gethostname().casefold(), "workbridge-registration-host-mismatch")
    return settings


def workbridge_root(*, use_registered=True):
    """Resolve one local deployment for service state and desktop turn ownership."""
    configured = os.environ.get("RR2_WORKBRIDGE_ROOT")
    if configured is None and use_registered:
        configured = _registered_workbridge().get("deployment")
    return _local_absolute_path(BRIDGE if configured is None else configured, "invalid-workbridge-root")


def require_clear_desktop_turn(*, bridge=None):
    """Check Workbridge admission without creating or releasing a lock."""
    bridge = workbridge_root() if bridge is None else bridge
    evidence = bridge / ".tools" / "desktop-evidence"
    _plain_path(evidence)
    _require(evidence.is_dir(), "shared-gui-evidence-directory-missing")
    for path in evidence.iterdir():
        name = path.name.casefold()
        _require(name not in ("desktop-input-turn.lock", "desktop-turn-admission.lock")
                 and not (name.startswith("desktop-turn-quarantine-") and name.endswith(".json")),
                 "desktop-turn-recovery-required")


def _run(args, timeout=120, *, env=None):
    # File-backed bounded output avoids buffering base64 screenshots without a limit.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen([str(arg) for arg in args], cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=stdout, stderr=stderr, env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + timeout
        try:
            while proc.poll() is None:
                _require(time.monotonic() < deadline, "backend-timeout")
                _require(os.fstat(stdout.fileno()).st_size <= MAX_OUTPUT and
                         os.fstat(stderr.fileno()).st_size <= MAX_OUTPUT, "backend-output-limit")
                time.sleep(.05)
            _require(os.fstat(stdout.fileno()).st_size <= MAX_OUTPUT and
                     os.fstat(stderr.fileno()).st_size <= MAX_OUTPUT, "backend-output-limit")
            stdout.seek(0)
            raw = stdout.read(MAX_OUTPUT + 1).decode("utf-8-sig")
            return proc.returncode, raw
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


def _rift_addons_registration():
    return ROOT / ".local" / "rift-addons.json"


def register_local_rift_addons_root(root, expected_host):
    """Save an explicit AddOns directory for this checkout on the verified host."""
    from scripts.waypoint_progress import write_json_atomic

    host = socket.gethostname()
    _require(valid_host_name(expected_host) and host.casefold() == expected_host.casefold(),
             "physical-host-mismatch")
    addons = _local_absolute_path(root, "invalid-rift-addons-root")
    _require(addons.is_dir(), "rift-addons-directory-unavailable")
    registration = _rift_addons_registration()
    _plain_path(registration)
    registration.parent.mkdir(exist_ok=True)
    write_json_atomic(registration, {"schema": "rr2.rift-addons/1", "host": host, "root": str(addons)})
    return {"addonsRoot": str(addons), "registration": str(registration)}


def local_rift_addons_root():
    """Resolve the selected AddOns root or the Windows Documents known folder."""
    configured = os.environ.get("RR2_RIFT_ADDONS_ROOT")
    if configured:
        return _local_absolute_path(configured, "invalid-rift-addons-root")
    registration = _rift_addons_registration()
    if registration.exists() or registration.is_symlink():
        _plain_path(registration)
        error = "invalid-rift-addons-registration"
        _require(registration.is_file(), error)
        with registration.open("rb") as stream:
            raw = stream.read(16385)
        _require(0 < len(raw) <= 16384, error)
        try:
            settings = json.loads(raw)
        except ValueError as exc:
            raise ValueError(error) from exc
        _require(isinstance(settings, dict) and settings.get("schema") == "rr2.rift-addons/1"
                 and valid_host_name(settings.get("host")) and isinstance(settings.get("root"), str), error)
        _require(settings["host"].casefold() == socket.gethostname().casefold(), "rift-addons-registration-host-mismatch")
        addons = _local_absolute_path(settings["root"], error)
        _require(addons.is_dir(), "rift-addons-directory-unavailable")
        return addons
    code, text = _run([
        POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "[Environment]::GetFolderPath('MyDocuments')",
    ], timeout=10)
    documents = Path(text.strip())
    _require(code == 0 and documents.is_absolute() and not documents.drive.startswith(("\\", "/")),
             "local-documents-directory-unavailable")
    return documents / "RIFT" / "Interface" / "AddOns"


def _identity(physical_pid=None, *, require_window=True):
    _require(physical_pid is None or
             (type(physical_pid) is int and 1 <= physical_pid <= 4294967295),
             "invalid-physical-pid")
    selection = (f"$p=@($p | Where-Object {{$_.Id -eq {physical_pid}}});"
                 if physical_pid is not None else "")
    script = (
        "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$p=@(Get-Process -Name rift_x64 -ErrorAction SilentlyContinue);"
        + selection +
        "if($p.Count -eq 0){@{status='not-running'}|ConvertTo-Json -Compress;exit};"
        "if($p.Count -ne 1){@{status='ambiguous-process'}|ConvertTo-Json -Compress;exit};"
        "$p=$p[0];$path=$p.MainModule.FileName;"
        # The local PowerShell host may not expose the Get-FileHash cmdlet.
        # Hash the actual executable stream with the .NET framework instead.
        "$sha=[Security.Cryptography.SHA256]::Create();"
        "try{$stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);"
        "try{$exeHash=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}"
        "finally{$stream.Dispose()}}finally{$sha.Dispose()};"
        "[ordered]@{hostName=[Environment]::MachineName;processId=[int]$p.Id;"
        "processStartUtcTicks=$p.StartTime.ToUniversalTime().Ticks.ToString();"
        "executablePath=$path;executableSha256=$exeHash;"
        "hwnd=$p.MainWindowHandle.ToInt64()}|ConvertTo-Json -Compress"
    )
    code, text = _run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script], 20)
    _require(code == 0, "game-identity-unavailable")
    value = json.loads(text)
    _require(isinstance(value, dict), "invalid-game-identity")
    _require("status" not in value, value.get("status", "invalid-game-identity"))
    _require(type(value.get("processId")) is int and value["processId"] > 0 and
             isinstance(value.get("processStartUtcTicks"), str) and
             value["processStartUtcTicks"].isdigit() and int(value["processStartUtcTicks"]) > 0 and
             isinstance(value.get("executableSha256"), str) and
             re.fullmatch("[a-f0-9]{64}", value["executableSha256"]) and
             isinstance(value.get("executablePath"), str) and bool(value["executablePath"]) and
             type(value.get("hwnd")) is int and
             (value["hwnd"] > 0 if require_window else value["hwnd"] >= 0),
             "no-window-or-invalid-identity")
    return value


def _workbridge_command(bridge, *, use_registered=True):
    settings = _registered_workbridge() if use_registered else {}
    if settings and Path(settings["deployment"]) != bridge:
        settings = {}
    override = os.environ.get("RR2_WORKBRIDGE_CLI_ROOT", settings.get("cliRoot"))
    cli_root = bridge if override is None else _local_absolute_path(override, "invalid-workbridge-cli-root")
    cli = cli_root / "scripts" / "workbridge-cli.mjs"
    state = bridge / ".local"
    _plain_path(cli)
    _plain_path(state)
    configured_node = os.environ.get("RR2_WORKBRIDGE_NODE", settings.get("node"))
    if configured_node is not None:
        node = _local_absolute_path(configured_node, "invalid-workbridge-node-path")
        _require(node.suffix.casefold() == ".exe", "invalid-workbridge-node-path")
        _require(node.is_file(), "desktop-node-runtime-unavailable")
    else:
        node = NODE if NODE.is_file() else shutil.which("node")
    _require(node is not None, "desktop-node-runtime-unavailable")
    _require(cli.is_file(), "desktop-workbridge-cli-unavailable")
    _require(state.is_dir(), "desktop-workbridge-service-state-unavailable")
    # The running owner keeps service state and desktop evidence in its deployment.
    # The CLI may come from a separate, compatible local build.
    return [node, cli, "--service-state", state]


def _workbridge_response(text):
    lines = text.splitlines()
    _require(len(lines) == 1, "invalid-backend-response")
    entry = json.loads(lines[0])
    _require(isinstance(entry, dict), "invalid-backend-response")
    return entry


def _missing_workbridge_capture_runners(bridge):
    # Include the shared admission module imported by the capture runner and service.
    missing = []
    for relative in ("dist/desktop-ui.mjs", "dist/desktop-capture.mjs", "dist/desktop-turn-admission.mjs"):
        path = bridge / relative
        _plain_path(path)
        if not path.is_file():
            missing.append(relative)
    return missing


def _check_workbridge_winapp(command):
    failure = {"status": "blocked", "reason": "desktop-workbridge-winapp-probe-failed"}
    try:
        with tempfile.TemporaryDirectory(prefix="rr2-winapp-") as request_dir:
            result = _call(command, "desktop_windows", {"checkDependencies": True}, Path(request_dir), timeout=23)
    except (OSError, ValueError, subprocess.SubprocessError):
        return failure
    if (result.get("ok") is not True or result.get("readOnly") is not True
            or type(result.get("schemaVersion")) is not int or result["schemaVersion"] != 1
            or result.get("operation") != "check-dependencies" or result.get("backend") != "Microsoft.WinAppCli"):
        return failure
    status = result.get("status")
    version = result.get("version")
    if status == "available" and isinstance(version, str) and re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){2}", version):
        return {"status": "available", "version": version}
    reason = result.get("reason")
    if status == "blocked" and reason in WORKBRIDGE_WINAPP_REASONS:
        return {"status": "blocked", "reason": reason}
    return failure


def _check_workbridge_catalog(command):
    code, text = _run([*command, "--list-tools", "--timeout", "6", "--json"], 10)
    entry = _workbridge_response(text)
    if code != 0 or entry.get("ok") is not True:
        error = entry.get("error")
        _require(isinstance(error, dict), "workbridge-discovery-failed")
        reason = error.get("code")
        _require(isinstance(reason, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", reason),
                 "workbridge-discovery-failed")
        result = {"status": "blocked", "reason": reason}
        for field in ("expectedVersion", "runtimeVersion"):
            version = error.get(field)
            if isinstance(version, str) and re.fullmatch(r"[0-9][A-Za-z0-9.+-]{0,63}", version):
                result[field] = version
        return result, None
    tools = entry.get("tools")
    version = entry.get("serverVersion")
    _require(entry.get("discovery") == "tools" and isinstance(tools, list) and len(tools) <= 1000
             and all(isinstance(tool, dict) and isinstance(tool.get("name"), str) for tool in tools)
             and isinstance(version, str) and re.fullmatch(r"[0-9][A-Za-z0-9.+-]{0,63}", version),
             "invalid-backend-response")
    names = [tool["name"] for tool in tools]
    _require(len(names) == len(set(names)), "invalid-backend-response")
    missing = [name for name in ("desktop_windows", "desktop_capture_window") if name not in names]
    if missing:
        return {"status": "blocked", "reason": "TOOL_NOT_FOUND", "runtimeVersion": version,
                "missingTools": missing}, None
    return {"status": "available", "runtimeVersion": version}, tools[names.index("desktop_windows")]


def _check_workbridge_node(command):
    details = {"nodeExecutable": str(command[0]), "cliPath": str(command[1])}
    try:
        node_code, node_text = _run([command[0], "--version"], 5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {**details, "status": "blocked", "reason": "desktop-node-version-unavailable"}
    version_match = re.fullmatch(r"v([0-9]{1,3})\.[0-9]{1,6}\.[0-9]{1,6}(?:-[A-Za-z0-9.-]{1,32})?",
                                 node_text.strip())
    if node_code != 0 or version_match is None:
        return {**details, "status": "blocked", "reason": "desktop-node-version-unavailable"}
    details["nodeVersion"] = version_match[0]
    if int(version_match[1]) < MIN_WORKBRIDGE_NODE_MAJOR:
        return {**details, "status": "blocked", "reason": "desktop-node-version-unsupported",
                "minimumNodeMajor": MIN_WORKBRIDGE_NODE_MAJOR}
    return details


def register_workbridge_client(expected_host):
    """Remember a client verified by read-only discovery against its local service."""
    from scripts.waypoint_progress import write_json_atomic

    host = socket.gethostname()
    _require(valid_host_name(expected_host) and host.casefold() == expected_host.casefold(), "host-mismatch")
    bridge = workbridge_root(use_registered=False)
    evidence = bridge / ".tools" / "desktop-evidence"
    _plain_path(evidence)
    _require(evidence.is_dir(), "shared-gui-evidence-directory-missing")
    command = _workbridge_command(bridge, use_registered=False)
    node = _local_absolute_path(command[0], "invalid-workbridge-node-path")
    result = {"workbridgeRoot": str(bridge), "captureAttempted": False, "inputSent": False,
              **_check_workbridge_node(command)}
    if result.get("status") == "blocked":
        return result
    catalog, _ = _check_workbridge_catalog(command)
    result["toolCatalog"] = catalog
    if catalog["status"] != "available":
        return {**result, "status": "blocked", "reason": catalog["reason"]}
    _require(socket.gethostname().casefold() == host.casefold(), "host-changed")
    path = ROOT / ".local" / "workbridge-client.json"
    _plain_path(path)
    path.parent.mkdir(exist_ok=True)
    settings = {"schema": "rr2.workbridge-client/1", "host": host, "deployment": str(bridge),
                "cliRoot": str(command[1].parents[1]), "node": str(node)}
    write_json_atomic(path, settings)
    return {**result, "status": "workbridge-client-registered", "registration": str(path)}


def check_workbridge_capture_service(bridge):
    """Check deployed desktop files, catalog, and the service's WinApp when supported."""
    missing_files = _missing_workbridge_capture_runners(bridge)
    details = {"missingFiles": missing_files} if missing_files else {}
    try:
        command = _workbridge_command(bridge)
    except ValueError as error:
        return {**details, "status": "blocked", "reason": str(error)}
    details.update(_check_workbridge_node(command))
    if details.get("status") == "blocked":
        return details

    try:
        catalog, desktop = _check_workbridge_catalog(command)
    except (OSError, ValueError, subprocess.SubprocessError):
        if not missing_files:
            raise
        catalog, desktop = {"status": "blocked", "reason": "workbridge-discovery-unavailable"}, None
    if missing_files:
        return {**details, "status": "blocked", "reason": "desktop-workbridge-runner-files-missing",
                "toolCatalog": catalog}

    details.update(catalog)
    if catalog["status"] == "blocked":
        return details
    schema = desktop.get("inputSchema")
    properties = schema.get("properties") if isinstance(schema, dict) else None
    capability = properties.get("checkDependencies") if isinstance(properties, dict) else None
    if isinstance(capability, dict) and capability.get("type") == "boolean":
        winapp = _check_workbridge_winapp(command)
        if winapp["status"] == "blocked":
            return {**details, "status": "blocked", "reason": winapp["reason"], "winapp": winapp}
    else:
        winapp = {"status": "not-checked", "reason": "desktop-workbridge-winapp-probe-unsupported"}
    return {**details, "status": "available", "winapp": winapp}


def _call(command, tool, arguments, output, *, timeout=100):
    request = output / (tool + "-request.json")
    with request.open("x", encoding="utf-8") as stream:
        json.dump([{"tool": tool, "arguments": arguments}], stream)
    code, text = _run([*command, "--input", request, "--timeout", str(timeout), "--json"], timeout + 20)
    entry = _workbridge_response(text)
    result = entry.get("result", {})
    _require(isinstance(result, dict), "invalid-backend-response")
    if code != 0 or entry.get("ok") is not True:
        error = result.get("error", entry.get("error", {}))
        raise ValueError(error.get("code", "backend-failed") if isinstance(error, dict) else "backend-failed")
    _require(entry.get("tool") == tool and entry.get("index") == 0, "invalid-backend-response")
    return result


def capture_physical(expected_host, output, *, allow_foreground_change=False,
                     physical_pid=None):
    """No fallback, guest authentication, input injection, service startup, or retry."""
    target_id = "physical-" + str(expected_host).lower()
    try:
        _require(valid_host_name(expected_host), "invalid-host")
        _require(socket.gethostname().casefold() == expected_host.casefold(), "host-mismatch")
        _require(allow_foreground_change is True, "desktop-ownership-required")
        _require(physical_pid is None or
                 (type(physical_pid) is int and 1 <= physical_pid <= 4294967295),
                 "invalid-physical-pid")
        output = Path(output)
        _require(output.is_absolute(), "absolute-output-required")
        output = Path(os.path.abspath(output))
        _plain_path(output)
        _require(not output.exists() and output.parent.is_dir(), "fresh-output-required")
        bridge = workbridge_root()
        command = _workbridge_command(bridge)
        _require(not _missing_workbridge_capture_runners(bridge), "desktop-workbridge-runner-files-missing")
        output.mkdir()
        before = _identity(physical_pid)
        _require(physical_pid is None or before.get("processId") == physical_pid,
                 "physical-pid-mismatch")
        _require(before.get("hostName", "").casefold() == expected_host.casefold(), "host-mismatch")
        windows = _call(command, "desktop_windows", {"app": str(before["processId"])}, output)
        _require(windows.get("truncated") is False, "window-list-truncated")
        matches = [w for w in windows.get("windows", [])
                   if w.get("pid") == before["processId"] and w.get("hwnd") == before["hwnd"]
                   and str(w.get("process", "")).casefold() == "rift_x64"]
        _require(len(matches) == 1, "no-exact-window")
        window = matches[0]
        _require(window.get("width", 0) >= 256 and window.get("height", 0) >= 40,
                 "window-not-visible")
        _require(isinstance(window.get("title"), str) and bool(window["title"]) and
                 isinstance(window.get("className"), str) and bool(window["className"]),
                 "invalid-window-identity")
        _require(_identity(physical_pid) == before, "stale-identity")
        request_id = "rr2_physical_" + uuid.uuid4().hex
        started = datetime.now(timezone.utc)
        started = started.replace(microsecond=(started.microsecond // 1000) * 1000)
        receipt = _call(command, "desktop_capture_window", {
            "pid": before["processId"], "hwnd": before["hwnd"], "process": "rift_x64",
            "requestId": request_id, "title": window["title"], "className": window["className"],
        }, output)
        _require(_identity(physical_pid) == before, "stale-identity")
        ended = datetime.now(timezone.utc)
        _require(receipt.get("ok") is True and receipt.get("replayed") is False and
                 receipt.get("requestId") == request_id and receipt.get("pid") == before["processId"] and
                 receipt.get("hwnd") == before["hwnd"] and receipt.get("process") == "rift_x64" and
                 receipt.get("title") == window["title"] and receipt.get("expectedClass") == window["className"] and
                 receipt.get("inputInjected") is False and receipt.get("foregroundMayChange") is True,
                 "capture-receipt-mismatch")
        captured = datetime.fromisoformat(receipt["capturedUtc"].replace("Z", "+00:00"))
        _require(captured.tzinfo is not None and started <= captured <= ended, "stale-capture")
        source = Path(receipt["imagePath"])
        _require(source == bridge / ".tools/desktop-evidence" / ("capture-" + request_id + ".png"),
                 "unexpected-image-path")
        _plain_path(source)
        _require(source.is_file() and 45 <= source.stat().st_size <= MAX_IMAGE, "image-unavailable")
        with source.open("rb") as stream:
            raw = stream.read(MAX_IMAGE + 1)
        digest = sha256(raw).hexdigest()
        _require(len(raw) <= MAX_IMAGE and raw[:8] == bytes.fromhex("89504e470d0a1a0a") and
                 raw[12:16] == b"IHDR" and b"IEND" in raw[29:], "invalid-image")
        width, height = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
        _require(1 <= width <= 10000 and 1 <= height <= 10000 and
                 digest == receipt.get("sha256") == receipt.get("imageSha256Verified") and
                 len(raw) == receipt.get("sizeBytes") == receipt.get("imageBytesVerified") and
                 receipt.get("width") == width and receipt.get("height") == height and
                 receipt.get("imageDimensionsVerified") == {"width": width, "height": height} and
                 receipt.get("mimeType") == "image/png", "image-evidence-mismatch")
        _plain_path(output)
        image = output / "image.png"
        with image.open("xb") as stream:
            stream.write(raw)
        return {"status": "verified-awaiting-visual-review", "targetId": target_id,
                "workflow": "physical", "captureBackend": "Microsoft.WinAppCli-host-window",
                "image": str(image), "imageSha256": digest.upper(),
                "capturedAtUtc": receipt["capturedUtc"], "target": before,
                "foregroundMayChange": True}
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        return {"status": "blocked", "targetId": target_id, "workflow": "physical",
                "reason": str(error), "captureBackend": "Microsoft.WinAppCli-host-window",
                "foregroundMayChange": True}
