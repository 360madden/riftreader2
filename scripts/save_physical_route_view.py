"""Save one guarded physical route view and optional offline RRD.

The caller owns desktop access. Explicit desktop capture requests pinned focus
without keys; the separate WGC path is focus-neutral. Neither rebinds a target,
installs packages or opens a viewer.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess

from scripts import observe_target, physical_rift, plot_physical_waypoints
from scripts.live_physical_waypoints import load_route
from scripts.waypoint_progress import write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_PYTHON = ROOT / ".local/visualization-venv/Scripts/python.exe"
CAPTURE_PYTHON = ROOT / ".local/overlay-venv/Scripts/python.exe"
TARGET_FIELDS = {"hostName", "processId", "processStartUtcTicks", "executablePath", "executableSha256", "hwnd"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _retain_native_sources(observation, directory, sources):
    bracket = observation.get("nativeFacing")
    if not isinstance(bracket, dict):
        return
    for field, filename in (("beforeOutput", "native-before.json"), ("afterOutput", "native-after.json")):
        original = bracket.get(field)
        if original is None:
            continue
        require(isinstance(original, str) and original, "invalid-native-source-path")
        source, retained = Path(original), directory / filename
        sources[field] = {"source": original}
        require(source.is_absolute(), "absolute-native-source-required")
        raw = source.read_bytes()
        sources[field]["sha256"] = hashlib.sha256(raw).hexdigest()
        with retained.open("xb") as stream:
            stream.write(raw)
        sources[field]["retained"] = str(retained)
        bracket[field] = str(retained)


def _optional_rerun(route_path, observation_path, directory, enabled, *, desktop=False):
    if not enabled:
        return {"status": "unavailable", "reason": "not-requested"}
    if not VISUALIZATION_PYTHON.is_file():
        return {"status": "unavailable", "reason": "visualization-environment-unavailable"}
    output = directory / "view.rrd"
    environment = dict(os.environ, CI="1")
    environment.pop("FORCE_RERUN_ANALYTICS", None)
    try:
        completed = subprocess.run([str(VISUALIZATION_PYTHON), str(ROOT / "scripts/export_physical_rerun.py"),
            "--route", str(route_path), "--desktop-pair" if desktop else "--observation", str(observation_path),
            "--output", str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lines = completed.stdout.splitlines()
        summary = json.loads(lines[-1]) if lines else {}
        require(completed.returncode == 0 and summary.get("status") == "offline-rerun-evidence-export"
                and summary.get("output") == str(output) and output.is_file() and output.stat().st_size > 0,
                summary.get("reason") or "rerun-export-failed")
        return {"status": "saved", "path": str(output)}
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        return {"status": "failed", "reason": str(error)}


def _monitor_name(hwnd):
    """Get the current Windows display name; never assume its origin or index."""
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT),
                    ("dwFlags", W.DWORD), ("szDevice", W.WCHAR * 32)]
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.MonitorFromWindow.argtypes, user.MonitorFromWindow.restype = [W.HWND, W.DWORD], W.HANDLE
    user.GetMonitorInfoW.argtypes, user.GetMonitorInfoW.restype = [W.HANDLE, ctypes.POINTER(MonitorInfo)], W.BOOL
    monitor = user.MonitorFromWindow(hwnd, 0)
    info = MonitorInfo(); info.cbSize = ctypes.sizeof(info)
    require(monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)), "target-display-unavailable")
    return info.szDevice


def _desktop_capture(host, pid, pinned, directory, result):
    require(CAPTURE_PYTHON.is_file(), "desktop-capture-environment-unavailable")
    result.update(focusRequested=True, focusMayChange=True, focusChanged=None)
    command = [str(physical_rift.NATIVE_EXE), "move-key", "--focus-only", "--pid", str(pid),
               "--expect-start-ticks", pinned["processStartUtcTicks"], "--expect-sha256", pinned["executableSha256"],
               "--expect-hwnd", hex(pinned["hwnd"]), "--json"]
    focused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    focus = json.loads(focused.stdout)
    write_json_atomic(directory / "focus.json", focus)
    result["focusReceipt"] = str(directory / "focus.json")
    require(focused.returncode == 0 and focus.get("status") == "focused-target"
            and focus.get("inputSent") is False and focus.get("desktopInputsDown") == [],
            focus.get("reason", "focus-only-unavailable"))
    target = focus.get("target", {})
    require(target.get("machineName", "").casefold() == host.casefold()
            and target.get("processId") == pid
            and str(target.get("processStartUtcTicks")) == pinned["processStartUtcTicks"]
            and target.get("executablePath", "").casefold() == pinned["executablePath"].casefold()
            and target.get("executableSha256", "").casefold() == pinned["executableSha256"].casefold()
            and int(target.get("windowHandle", "0"), 16) == pinned["hwnd"]
            and target.get("isForeground") is True, "focus-target-identity-mismatch")
    result["focusChanged"] = focus.get("focusAttempt") is not None
    display = _monitor_name(pinned["hwnd"])
    capture = directory / "capture"
    command = [str(CAPTURE_PYTHON), str(ROOT / "scripts/probe_dxcam_native_pair.py"),
               "--expected-host", host, "--physical-pid", str(pid), "--display", display,
               "--output", str(capture), "--timeout", "10",
               "--expect-start-ticks", pinned["processStartUtcTicks"],
               "--expect-sha256", pinned["executableSha256"], "--expect-hwnd", hex(pinned["hwnd"])]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    pair_path = capture / "pair.json"
    require(pair_path.is_file(), "desktop-pair-unavailable: " + completed.stdout[-1024:])
    pair = plot_physical_waypoints._read(pair_path)
    require(completed.returncode == 0 and pair.get("status") == "stable-native-composite-event-candidate",
            pair.get("reason", "desktop-pair-withheld"))
    require(pair.get("targetBefore") == pinned and pair.get("targetAfter") == pinned,
            "captured-target-identity-mismatch")
    sources = {}
    for number, (field, filename) in enumerate((("nativeBeforeOutput", "native-before.json"),
                                               ("nativeAfterOutput", "native-after.json"))):
        source = pair["nativeSources"][number]
        require(source["path"] == pair[field], "desktop-native-source-mismatch")
        raw = Path(source["path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == source["sha256"], "desktop-native-source-hash-mismatch")
        retained = directory / filename
        with retained.open("xb") as stream:
            stream.write(raw)
        sources[field] = dict(source=source["path"], sha256=source["sha256"], retained=str(retained))
        source["path"] = pair[field] = str(retained)
    pair["retainedNativeSources"] = sources
    # The pair's PNG already resides inside this new bundle.
    write_json_atomic(directory / "desktop-pair.json", pair)
    result.update(nativeSources=sources, requestedDisplay=display, sourceKind="desktop-composite-event-candidate")
    return directory / "desktop-pair.json"


def save_route_view(expected_host, physical_pid, document, output, *, expected_target, export_rerun=True,
                    capture_backend="wgc"):
    """Return saved-route-view-candidate or blocked, retaining acquired evidence.

    Output is a fresh absolute directory. Full recorded heights and exact caller
    process/window identity are mandatory. Optional Rerun failure is nonfatal.
    """
    result = {"status": "blocked", "inputSent": False, "focusChanged": False,
              "rerun": {"status": "unavailable", "reason": "core-view-unavailable"}}
    directory = None
    created = False
    try:
        directory = Path(output)
        result["directory"] = str(directory)
        require(directory.is_absolute() and not directory.exists() and directory.parent.is_dir(),
                "fresh-absolute-output-directory-required")
        require(isinstance(expected_host, str) and expected_host.casefold() == socket.gethostname().casefold()
                and expected_host.upper() in ("AMD-DESKTOP", "LEGION"), "host-mismatch")
        require(type(physical_pid) is int and 1 <= physical_pid <= 4294967295, "explicit-physical-pid-required")
        require(type(export_rerun) is bool, "invalid-export-rerun-option")
        require(capture_backend in ("wgc", "desktop"), "explicit-capture-backend-required")
        pinned = deepcopy(expected_target)
        require(isinstance(pinned, dict) and set(pinned) == TARGET_FIELDS
                and isinstance(pinned["hostName"], str) and pinned["hostName"].casefold() == expected_host.casefold()
                and type(pinned["processId"]) is int and pinned["processId"] == physical_pid
                and isinstance(pinned["processStartUtcTicks"], str) and pinned["processStartUtcTicks"].isdecimal()
                and int(pinned["processStartUtcTicks"]) > 0
                and isinstance(pinned["executableSha256"], str)
                and re.fullmatch(r"[a-fA-F0-9]{64}", pinned["executableSha256"]) is not None
                and isinstance(pinned["executablePath"], str) and pinned["executablePath"]
                and type(pinned["hwnd"]) is int and pinned["hwnd"] > 0, "complete-expected-target-required")
        selection = physical_rift.select_physical(expected_host, physical_pid)
        require(selection.get("status") == "ready", selection.get("reason", "physical-selection-unavailable"))
        require(selection.get("target") == pinned, "expected-target-identity-mismatch")
        directory.mkdir()
        created = True
        route_path, observation_path = directory / "route.json", directory / "observation.json"
        write_json_atomic(route_path, deepcopy(document))
        route = load_route(route_path)
        require(route["identity"]["machine"].casefold() == expected_host.casefold()
                and route["identity"]["gameBuildSha256"].casefold() == pinned["executableSha256"].casefold(),
                "route-host-build-mismatch")
        result["target"] = pinned
        result["route"] = str(route_path)
        result["recordingIdentity"] = route["recordingIdentity"]
        result["captureBackend"] = capture_backend
        if capture_backend == "desktop":
            observation_path = _desktop_capture(expected_host, physical_pid, pinned, directory, result)
            result["observation"] = str(observation_path)
            projection = plot_physical_waypoints.render_desktop_pair(observation_path, route_path, directory / "projection")
            result.update(status="saved-route-view-candidate", image=projection["annotatedImage"],
                          projection=projection["report"])
            result["rerun"] = _optional_rerun(route_path, observation_path, directory, export_rerun, desktop=True)
            write_json_atomic(directory / "view.json", result)
            return result
        observation = deepcopy(observe_target.observe("physical-" + expected_host.lower(), expected_host,
            output=directory / "capture", physical_pid=physical_pid,
            native_facing=True, physical_capture_backend="wgc"))
        result["nativeSources"] = {}
        try:
            _retain_native_sources(observation, directory, result["nativeSources"])
        finally:
            observation["retainedNativeSources"] = result["nativeSources"]
            write_json_atomic(observation_path, observation)
            result["observation"] = str(observation_path)
        require(observation.get("status") == "verified-awaiting-visual-review",
                observation.get("reason", "physical-observation-unavailable"))
        require(observation.get("target") == pinned, "captured-target-identity-mismatch")
        projection = plot_physical_waypoints.render(observation_path, route_path, directory / "projection")
        result.update(status="saved-route-view-candidate", image=projection["annotatedImage"],
                      projection=projection["report"])
        result["rerun"] = _optional_rerun(route_path, observation_path, directory, export_rerun)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        result.update(status="blocked", reason=str(error))
    if created:
        try:
            write_json_atomic(directory / "view.json", result)
        except (OSError, ValueError, TypeError) as error:
            result.update(status="blocked", reason="view-summary-write-failed", summaryWriteError=str(error))
    return result
