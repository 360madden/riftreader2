#!/usr/bin/env python3
"""Guarded continuous movement to one physical-RIFT destination.

The native helper owns every key transition and release. Python owns the exact
process reservation, fresh stationary admission, parent lifetime and STOP file.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import ctypes
from ctypes import wintypes
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
import math
import os
import queue
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.physical_waypoints import Stopped
from scripts.waypoint_limits import MAX_ROUTE_DISTANCE, MAX_TRIP_SECONDS, MAX_WAYPOINTS

_DOTNET_FILETIME_OFFSET = 504911232000000000
_RELEASE_GRACE_SECONDS = 10.0
_FORCED_EXIT_GRACE_SECONDS = 15.0
_UNTRUSTED_OUTPUT_CHARACTERS = 16_384


class ContinuousStopped(Stopped):
    """STOP with the current release-validated movement result attached."""
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


class EncounterInterrupted(RuntimeError):
    """A verified, released native movement interruption, distinct from STOP."""

    def __init__(self, receipt):
        self.receipt = receipt
        self.position = receipt.get("position")
        super().__init__(receipt.get("reason") or "Encounter interrupted travel")


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _owner_start_ticks(pid=None):
    """Return the current process creation time as .NET UTC ticks."""
    pid = os.getpid() if pid is None else pid
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Cannot inspect movement owner process")
    try:
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise OSError(ctypes.get_last_error(), "Cannot read movement owner process time")
        return ((created.dwHighDateTime << 32) | created.dwLowDateTime) + _DOTNET_FILETIME_OFFSET
    finally:
        kernel.CloseHandle(handle)


def _create_stop(path):
    """Publish this invocation's stop request once; never pre-create the file."""
    try:
        with path.open("xb") as stream:
            stream.write(b"stop\n")
    except FileExistsError:
        pass


def _drain(stream, output):
    try:
        output.append(stream.read())
    except (OSError, ValueError) as exc:
        output.append(exc)


def _drain_lines(stream, output, progress):
    try:
        for line in stream:
            output.append(line)
            try:
                value = json.loads(line)
                if isinstance(value, dict) and value.get("status") == "waypoint-passed":
                    progress.put(value)
            except (ValueError, TypeError):
                pass
    except (OSError, ValueError) as exc:
        output.append(exc)


def _validate_passes(receipt, guides, started):
    if not guides:
        return []
    passes = receipt.get("passedWaypoints")
    if not isinstance(passes, list) or len(passes) > len(guides):
        raise ValueError("Native waypoint passage evidence is unavailable")
    if receipt["status"] == "arrived" and len(passes) != len(guides):
        raise ValueError("Native arrival omitted waypoint passages")
    previous = started - timedelta(seconds=1)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    for index, item in enumerate(passes):
        guide = guides[index]
        if not isinstance(item, dict) or type(item.get("index")) is not int or item["index"] != index or item.get("name") != guide["name"]:
            raise ValueError("Native waypoint passage order or name changed")
        position = item.get("position")
        if not isinstance(position, dict):
            raise ValueError("Native waypoint passage position is unavailable")
        px, py, pz = (_finite(position.get(axis), "passage " + axis) for axis in ("x", "y", "z"))
        if math.hypot(px - guide["x"], pz - guide["z"]) > .5 + 1e-9 or ("y" in guide and abs(py - guide["y"]) > .5 + 1e-9):
            raise ValueError("Native waypoint passage is outside the guide")
        try:
            observed = datetime.fromisoformat(item["observedAtUtc"].replace("Z", "+00:00"))
            if observed.tzinfo is None or not previous <= observed <= now:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ValueError("Native waypoint passage timestamp is stale or unordered")
        previous = observed
    return passes


def _parse_final(stdout):
    if not isinstance(stdout, str):
        raise ValueError("Native movement result is unavailable")
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("Native movement must return one final JSON object")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(lines[0], object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"nonfinite {value}")))


def _same_window(value, expected):
    try:
        return int(value, 0) == expected if isinstance(value, str) else value == expected
    except ValueError:
        return False


def _held_input_milliseconds(events):
    """Derive bounded held time from native send-call windows, or return None."""
    if not isinstance(events, list):
        return None
    if not events:
        return 0.0
    pending, total = {}, 0.0
    try:
        for event in events:
            if not isinstance(event, dict) or event.get("inserted") is not True:
                return None
            key, phase = event.get("key"), event.get("phase")
            if not isinstance(key, str) or phase not in ("key-down", "key-up"):
                return None
            if phase == "key-down":
                pending[key] = datetime.fromisoformat(
                    event["callCompletedAtUtc"].replace("Z", "+00:00"))
            else:
                down = pending.pop(key)
                up = datetime.fromisoformat(event["callStartedAtUtc"].replace("Z", "+00:00"))
                milliseconds = (up - down).total_seconds() * 1000
                if milliseconds < 0:
                    return None
                total += milliseconds
    except (KeyError, TypeError, ValueError):
        return None
    return total if not pending else None


def _validate_receipt(receipt, adapter, goal, stop_path, owner, returncode):
    if not isinstance(receipt, dict) or receipt.get("status") not in {
            "arrived", "stopped", "halted", "blocked"}:
        raise ValueError("Invalid native movement status")
    status = receipt["status"]
    expected_code = 0 if status in ("arrived", "stopped") else 2 if status == "blocked" else 3
    if returncode != expected_code:
        raise ValueError("Native movement exit code does not match its status")
    if (type(receipt.get("inputSent")) is not bool
            or receipt.get("releaseSucceeded") is not True
            or not isinstance(receipt.get("desktopInputsDown"), list)
            or receipt["desktopInputsDown"]):
        raise ValueError("Native movement release is not verified")
    observed_owner = receipt.get("owner")
    if (not isinstance(observed_owner, dict)
            or observed_owner.get("processId") != owner[0]
            or str(observed_owner.get("processStartUtcTicks")) != str(owner[1])):
        raise ValueError("Native movement owner identity changed")
    returned_goal = receipt.get("goal")
    if (not isinstance(returned_goal, dict)
            or _finite(returned_goal.get("x"), "goal X") != goal[0]
            or _finite(returned_goal.get("z"), "goal Z") != goal[1]
            or Path(str(receipt.get("stopFile", ""))).absolute() != stop_path):
        raise ValueError("Native movement goal or STOP ownership changed")
    expected_goal_y = goal[2]
    if expected_goal_y is None:
        if "y" in returned_goal:
            raise ValueError("Native movement returned an unrequested goal height")
    elif _finite(returned_goal.get("y"), "goal Y") != expected_goal_y:
        raise ValueError("Native movement goal height changed")
    target = receipt.get("target")
    expected = adapter.target
    if target is not None:
        if (not isinstance(target, dict)
                or str(target.get("machineName", "")).casefold() != adapter.host.casefold()
                or target.get("processId") != adapter.pid
                or str(target.get("processStartUtcTicks")) != str(expected["processStartUtcTicks"])
                or str(target.get("executableSha256", "")).casefold()
                   != expected["executableSha256"].casefold()
                or not _same_window(target.get("windowHandle"), expected["hwnd"])
                or str(receipt.get("playerKey")) != str(adapter.unit_key)):
            raise ValueError("Native movement target or player identity changed")
    elif status != "blocked" or receipt.get("playerKey") is not None:
        raise ValueError("Native movement target or player identity changed")
    position = receipt.get("position")
    metrics = (receipt.get("bodyBearingDegreesCandidate"), receipt.get("initialDistance"),
               receipt.get("finalDistance"))
    if position is None and status == "blocked":
        if any(value is not None for value in metrics):
            raise ValueError("Blocked native movement has partial pose evidence")
    else:
        if not isinstance(position, dict):
            raise ValueError("Native movement final position is unavailable")
        for axis in ("x", "y", "z"):
            _finite(position.get(axis), f"position {axis}")
        _finite(metrics[0], "body bearing")
        _finite(metrics[1], "initial distance")
        _finite(metrics[2], "final distance")
    path = receipt.get("path")
    if not isinstance(path, list):
        raise ValueError("Native movement path evidence is unavailable")
    if status != "blocked" and (not path or not isinstance(path[-1], dict)
            or not isinstance(path[-1].get("observedAtUtc"), str)
            or not path[-1]["observedAtUtc"]):
        raise ValueError("Native movement final observation time is unavailable")
    if not isinstance(receipt.get("keySendEvents"), list):
        raise ValueError("Native movement key-send evidence is unavailable")
    return receipt


def _retain(adapter, receipt):
    receipt = dict(receipt, version=1, kind="native-continuous-move")
    adapter.last_input_receipt = receipt
    path = Path(adapter.input_receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, separators=(",", ":"), allow_nan=False) + "\n")
    return path


def _bounded_text(value):
    if isinstance(value, Exception):
        value = f"{type(value).__name__}: {value}"
    elif not isinstance(value, str):
        value = "" if value is None else str(value)
    size = len(value)
    if size <= _UNTRUSTED_OUTPUT_CHARACTERS:
        return {"text": value, "originalCharacters": size, "truncated": False}
    half = _UNTRUSTED_OUTPUT_CHARACTERS // 2
    return {"text": value[:half] + "\n...[bounded untrusted output]...\n" + value[-half:],
            "originalCharacters": size, "truncated": True}


def _retain_untrusted(adapter, *, returncode, stdout, stderr, parsed, failure):
    """Retain bounded diagnostics without admitting an untrusted move receipt."""
    def scalar(value):
        if value is None or type(value) in (bool, int, float):
            return value
        return value[:128] if isinstance(value, str) else None

    release = None
    if isinstance(parsed, dict):
        down = parsed.get("desktopInputsDown")
        release = {
            "status": parsed.get("status") if isinstance(parsed.get("status"), str) else None,
            "reason": (parsed.get("reason")[:512]
                       if isinstance(parsed.get("reason"), str) else None),
            "inputSent": scalar(parsed.get("inputSent")),
            "inputSentType": type(parsed.get("inputSent")).__name__,
            "releaseSucceeded": scalar(parsed.get("releaseSucceeded")),
            "releaseSucceededType": type(parsed.get("releaseSucceeded")).__name__,
            "desktopInputsDown": ([str(value)[:128] for value in down[:32]]
                                  if isinstance(down, list) else None),
            "desktopInputsDownType": type(down).__name__,
            "desktopInputsDownTruncated": isinstance(down, list) and len(down) > 32,
        }
    record = {
        "version": 1, "kind": "native-continuous-move-untrusted",
        "trusted": False, "status": "rejected", "childExitCode": returncode,
        "validationError": str(failure)[:1024], "parsedReleaseFields": release,
        "rawStdout": _bounded_text(stdout), "rawStderr": _bounded_text(stderr),
    }
    adapter._continuous_move_untrusted = record
    try:
        path = Path(adapter.input_receipt_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        record["receiptWriteError"] = str(exc)
    return record


def _validate_recovery(receipt, adapter, key, returncode):
    """Validate one exact-target move-key --release-only receipt."""
    if not isinstance(receipt, dict):
        raise ValueError(f"Native {key} key-up recovery is not an object")
    expected = adapter.target
    events = receipt.get("keySendEvents")
    if (returncode != 0
            or receipt.get("status") != "windows-keyup-inserted-game-state-unverified"
            or receipt.get("releaseOnly") is not True
            or receipt.get("keyDownAttempts") != 0
            or str(receipt.get("machine", "")).casefold() != adapter.host.casefold()
            or receipt.get("processId") != adapter.pid
            or str(receipt.get("processStartUtcTicks")) != str(expected["processStartUtcTicks"])
            or str(receipt.get("executableSha256", "")).casefold()
               != expected["executableSha256"].casefold()
            or receipt.get("keys") != [key]
            or not isinstance(events, list) or len(events) != 1
            or not isinstance(events[0], dict)
            or events[0].get("key") != key
            or events[0].get("phase") != "key-up"
            or events[0].get("inserted") is not True
            or not isinstance(receipt.get("desktopInputsDown"), list)
            or receipt["desktopInputsDown"]):
        raise ValueError(f"Native {key} key-up recovery is not verified")
    return receipt


def _recover_after_untrusted_exit(adapter, executable, failure, run=subprocess.run):
    """Try exact-target W/A/D key-up recovery after the mover has exited.

    The crashed mover no longer owns the native semaphore, while the caller
    still owns the Python reservation. Recovery never turns an untrusted move
    into an arrived/stopped result; it records only independently checked key-up
    calls.
    """
    attempts = []
    for key in ("w", "a", "d"):
        command = [str(executable), "move-key", "--pid", str(adapter.pid),
                   "--expect-start-ticks", str(adapter.target["processStartUtcTicks"]),
                   "--expect-sha256", adapter.target["executableSha256"],
                   "--expect-hwnd", hex(adapter.target["hwnd"]), "--key", key,
                   "--release-only", "--no-focus", "--execute", "--json"]
        try:
            completed = run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=5,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            recovered = _validate_recovery(_parse_final(completed.stdout), adapter, key,
                                           completed.returncode)
            attempts.append({"key": key, "verified": True, "receipt": recovered})
        except (OSError, subprocess.SubprocessError, TypeError, ValueError,
                json.JSONDecodeError) as exc:
            attempts.append({"key": key, "verified": False, "reason": str(exc)})
    record = {"version": 1, "kind": "native-continuous-move-recovery",
              "status": "halted", "reason": str(failure), "inputSent": None,
              "releaseSucceeded": all(item["verified"] for item in attempts),
              "keys": attempts}
    adapter._continuous_move_recovery = record
    adapter._continuous_input_release_fault = not record["releaseSucceeded"]
    try:
        path = Path(adapter.input_receipt_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
    except OSError as exc:
        record["receiptWriteError"] = str(exc)
    return record


def retry_release(adapter, *, native_exe=None, run=subprocess.run):
    """Explicitly retry exact-target, no-focus W/A/D release after a fault."""
    from scripts.physical_waypoints import WaypointError
    if not getattr(adapter, "_continuous_input_release_fault", False):
        raise WaypointError("No unresolved continuous-input release fault")
    executable = Path(native_exe or physical_rift.NATIVE_EXE).absolute()
    with adapter.reserve() as lease:
        lease.check()
        recovery = _recover_after_untrusted_exit(
            adapter, executable, "Explicit release retry", run)
        lease.check()
    if not recovery["releaseSucceeded"]:
        raise WaypointError("Explicit W/A/D key-up recovery remains unverified")
    return recovery


def preview_move(adapter, x, z, stop):
    """Fresh input-free admission for the standalone CLI."""
    from scripts.physical_waypoints import read_stationary, Stopped, WaypointError
    x, z = _finite(x, "goal X"), _finite(z, "goal Z")
    if stop.is_set():
        raise Stopped("Stopped; no movement helper launched")
    with adapter.reserve() as lease:
        start = read_stationary(adapter, stop)
        lease.check()
        distance = math.hypot(x - start.position.x, z - start.position.z)
        if distance > MAX_ROUTE_DISTANCE:
            raise WaypointError(f"Destination exceeds {MAX_ROUTE_DISTANCE:g} world units")
        return {"status": "preview-only", "name": "CLI destination",
                "goal": {"x": x, "z": z}, "start": asdict(start.position),
                "position": asdict(start.position), "bearing": start.bearing,
                "distance": distance, "acquired": start.acquired, "inputSent": False,
                "qualification": "Fresh stationary native pose; no terrain or clearance proof"}


def move_to(adapter, x, z, stop, emit=lambda event: None, *, popen=subprocess.Popen,
            native_exe=None, owner_identity=None, max_seconds=MAX_TRIP_SECONDS,
            stop_path=None, expected_origin=None, reservation=None,
            recovery_run=subprocess.run, survival_guard=False, goal_y=None, path_points=None):
    """Run one native continuous destination movement under Python ownership."""
    from scripts.physical_waypoints import read_stationary, Stopped, WaypointError
    adapter._continuous_move_launched = False
    adapter._continuous_move_receipt_trusted = False
    if getattr(adapter, "_continuous_input_release_fault", False):
        raise WaypointError(
            "Previous continuous movement cleanup remains unverified; recreate the exact-target adapter")
    adapter._continuous_move_recovery = None
    adapter._continuous_move_untrusted = None
    x, z = _finite(x, "goal X"), _finite(z, "goal Z")
    goal_y = None if goal_y is None else _finite(goal_y, "goal Y")
    guides = []
    for point in path_points or []:
        if not isinstance(point, dict) or not isinstance(point.get("name"), str) or not point["name"]:
            raise ValueError("Guide requires a name and coordinates")
        guide = {"name": point["name"], "x": _finite(point.get("x"), "guide X"),
                 "z": _finite(point.get("z"), "guide Z")}
        if point.get("y") is not None:
            guide["y"] = _finite(point["y"], "guide Y")
        guides.append(guide)
    if (type(max_seconds) is not int or not 1 <= max_seconds <= MAX_TRIP_SECONDS):
        raise WaypointError(f"Movement time must be 1-{MAX_TRIP_SECONDS} seconds")
    if stop.is_set():
        raise Stopped("Stopped; no movement helper launched")
    executable = Path(native_exe or physical_rift.NATIVE_EXE).absolute()
    stop_path = Path(stop_path or (ROOT / "artifacts" /
                     ("continuous-move-stop-" + uuid.uuid4().hex + ".flag"))).absolute()
    if not stop_path.is_absolute() or stop_path.exists():
        raise WaypointError("A new absolute STOP path is required")
    owner = owner_identity or (os.getpid(), _owner_start_ticks())
    if (not isinstance(owner, tuple) or len(owner) != 2 or type(owner[0]) is not int
            or type(owner[1]) is not int or owner[0] <= 0 or owner[1] <= 0):
        raise WaypointError("Movement owner identity is unavailable")
    origin = None
    if expected_origin is not None:
        if not isinstance(expected_origin, dict):
            raise WaypointError("Expected movement origin must contain X, Z and bearing")
        try:
            origin = tuple(_finite(expected_origin[key], f"expected origin {key}")
                           for key in ("x", "z", "bearing"))
        except KeyError as exc:
            raise WaypointError("Expected movement origin must contain X, Z and bearing") from exc

    with (adapter.reserve() if reservation is None else nullcontext(reservation)) as lease:
        start = read_stationary(adapter, stop)
        lease.check()
        if origin is not None:
            origin_distance = math.hypot(start.position.x - origin[0], start.position.z - origin[1])
            origin_bearing_error = abs((start.bearing - origin[2] + 180) % 360 - 180)
            if origin_distance > .05 or origin_bearing_error > .5:
                raise WaypointError("Fresh pose no longer matches the reviewed movement origin")
        initial_distance = math.hypot(x - start.position.x, z - start.position.z)
        if initial_distance > MAX_ROUTE_DISTANCE:
            raise WaypointError(f"Destination exceeds {MAX_ROUTE_DISTANCE:g} world units")
        if stop.is_set():
            raise Stopped("Stopped; no movement helper launched")
        command = [str(executable), "follow-route", "--expected-host", adapter.host,
                   "--pid", str(adapter.pid), "--expect-start-ticks",
                   str(adapter.target["processStartUtcTicks"]), "--expect-sha256",
                   adapter.target["executableSha256"], "--expect-hwnd", hex(adapter.target["hwnd"]),
                   "--expect-player-key", str(adapter.unit_key), "--owner-pid", str(owner[0]),
                   "--owner-start-ticks", str(owner[1]), "--x", repr(x), "--z", repr(z),
                   "--stop-file", str(stop_path), "--max-seconds", str(max_seconds),
                   "--execute", "--json"]
        if guides:
            path_file = (ROOT / "artifacts" / ("continuous-route-" + uuid.uuid4().hex + ".json")).absolute()
            path_file.parent.mkdir(parents=True, exist_ok=True)
            with path_file.open("x", encoding="utf-8") as stream:
                json.dump({"waypoints": guides}, stream, allow_nan=False, separators=(",", ":"))
            command[command.index("--stop-file"):command.index("--stop-file")] = ["--path-file", str(path_file)]
        if goal_y is not None:
            insertion = command.index("--stop-file")
            command[insertion:insertion] = ["--goal-y", repr(goal_y)]
        if survival_guard:
            command.insert(command.index("--execute"), "--survival-interrupt")
            if survival_guard == "retreat":
                command.insert(command.index("--execute"), "--survival-retreat")
        if origin is not None:
            insertion = command.index("--execute")
            command[insertion:insertion] = ["--expect-x", repr(origin[0]),
                "--expect-z", repr(origin[1]), "--expect-bearing", repr(origin[2])]
        event_goal = {"x": x, "z": z}
        if goal_y is not None:
            event_goal["y"] = goal_y
        emit({"status": "moving", "name": "CLI destination", "goal": event_goal,
              "start": asdict(start.position), "position": asdict(start.position),
              "bearing": start.bearing, "distance": initial_distance, "acquired": start.acquired})
        started_utc = datetime.now(timezone.utc)
        child = popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, text=True,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        adapter._continuous_move_launched = True
        stdout, stderr = [], []
        progress = queue.Queue()
        readers = [threading.Thread(target=_drain_lines, args=(child.stdout, stdout, progress), daemon=True),
                   threading.Thread(target=_drain, args=(child.stderr, stderr), daemon=True)]
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + max_seconds + 5
        stop_requested_at = None
        last_wait_report = 0.0
        forced_exit_reason = None
        while child.poll() is None:
            try:
                while not progress.empty():
                    emit(dict(progress.get_nowait(), status="route-progress", trusted=False))
                now = time.monotonic()
                if (stop.is_set() or now >= deadline) and stop_requested_at is None:
                    stop_requested_at = now
                    try:
                        _create_stop(stop_path)
                    except OSError as exc:
                        forced_exit_reason = f"Could not publish native STOP: {exc}"
                if (stop_requested_at is not None and now - stop_requested_at >= _RELEASE_GRACE_SECONDS
                        and now - last_wait_report >= 5):
                    emit({"status": "stopping", "name": "CLI destination",
                          "reason": "Waiting for the native watchdog to publish release evidence"})
                    last_wait_report = now
                if (stop_requested_at is not None
                        and now - stop_requested_at >= _FORCED_EXIT_GRACE_SECONDS):
                    forced_exit_reason = forced_exit_reason or (
                        "Native movement did not exit after STOP/watchdog grace")
                    # The native watchdog has had its independent release grace.
                    # End a wedged controller, keep the Python reservation, then
                    # use no-focus exact-target key-up-only recovery after it
                    # relinquishes the native semaphore. Never accept a partial
                    # movement receipt after this path.
                    try:
                        child.kill()
                    except OSError as exc:
                        forced_exit_reason = f"{forced_exit_reason}; process kill failed: {exc}"
                time.sleep(.025)
            except KeyboardInterrupt:
                stop_requested_at = stop_requested_at or time.monotonic()
                try:
                    _create_stop(stop_path)
                except OSError as exc:
                    forced_exit_reason = f"Could not publish native STOP: {exc}"
        parsed_receipt = None
        try:
            for reader in readers:
                reader.join(timeout=5)
            while not progress.empty():
                emit(dict(progress.get_nowait(), status="route-progress", trusted=False))
            if any(reader.is_alive() for reader in readers):
                raise ValueError("Native movement output did not close after process exit")
            if forced_exit_reason is not None:
                raise ValueError(forced_exit_reason)
            if not stdout or isinstance(stdout[0], Exception):
                raise ValueError(f"Native movement result unavailable (exit code {child.returncode})")
            if not all(isinstance(part, str) for part in stdout) or not "".join(stdout).strip():
                detail = stderr[0].strip()[:4000] if stderr and isinstance(stderr[0], str) else ""
                raise ValueError(f"Native movement result unavailable (exit code {child.returncode})"
                                 + (": " + detail if detail else ""))
            raw_output = "".join(stdout)
            lines = [line for line in raw_output.splitlines() if line.strip()]
            for line in lines[:-1]:
                progress_record = _parse_final(line)
                if not isinstance(progress_record, dict) or progress_record.get("status") != "waypoint-passed":
                    raise ValueError("Unexpected native movement output")
            parsed_receipt = _parse_final(lines[-1])
            receipt = _validate_receipt(parsed_receipt, adapter, (x, z, goal_y), stop_path,
                                        owner, child.returncode)
            passes = _validate_passes(receipt, guides, started_utc)
            receipt_path = _retain(adapter, receipt)
            adapter._continuous_move_receipt_trusted = True
            adapter._continuous_input_release_fault = False
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raw_stdout = "".join(value for value in stdout if isinstance(value, str)) if stdout else None
            raw_stderr = stderr[0] if stderr else None
            _retain_untrusted(adapter, returncode=child.returncode,
                              stdout=raw_stdout, stderr=raw_stderr,
                              parsed=parsed_receipt, failure=exc)
            recovery = _recover_after_untrusted_exit(adapter, executable, exc, recovery_run)
            release = ("explicit W/A/D key-up recovery verified"
                       if recovery["releaseSucceeded"]
                       else "explicit W/A/D key-up recovery is unverified")
            raise WaypointError(f"Invalid native movement receipt: {exc}; {release}; no retry") from exc
        position = ({axis: float(receipt["position"][axis]) for axis in ("x", "y", "z")}
                    if receipt.get("position") is not None else None)
        events = receipt.get("keySendEvents")
        pulses = sum(event.get("phase") == "key-down" for event in events)
        held_ms = _held_input_milliseconds(events)
        observed_at = receipt["path"][-1]["observedAtUtc"] if receipt.get("path") else None
        result = dict(receipt, name="CLI destination", start=asdict(start.position),
                      goal={"x": x, "y": goal_y if goal_y is not None else start.position.y,
                            "z": z}, position=position,
                      bearing=(float(receipt["bodyBearingDegreesCandidate"])
                               if receipt.get("bodyBearingDegreesCandidate") is not None else None),
                      distance=(float(receipt["finalDistance"])
                                if receipt.get("finalDistance") is not None else None),
                      pulses=pulses, observedAtUtc=observed_at, inputReceiptPath=str(receipt_path),
                      heldInputMilliseconds=held_ms,
                      motionMode="held-forward",
                      autorunQualification="Game autorun is not started, detected, or cancelled by this operation")
        for item in passes:
            guide = guides[item["index"]]
            emit({"status": "passed", "index": item["index"], "name": guide["name"],
                  "goal": dict(guide), "position": item["position"],
                  "observedAtUtc": item["observedAtUtc"], "releaseSucceeded": True,
                  "source": item.get("source", "pose"),
                  "desktopInputsDown": [], "passageVerified": True,
                  "inputReceiptPath": str(receipt_path)})
        def stopped_with_receipt(message):
            # This is the current identity-bound, release-validated native result,
            # never a cached adapter receipt. Callers may validate its path.
            return ContinuousStopped(message, result)

        if receipt["status"] == "arrived":
            if stop.is_set():
                raise stopped_with_receipt("Stopped after native arrival; native release verified")
            try:
                settled = read_stationary(adapter, stop)
            except Stopped as exc:
                raise stopped_with_receipt(str(exc)) from exc
            if stop.is_set():
                raise stopped_with_receipt("Stopped during post-arrival verification; native release verified")
            settled_distance = math.hypot(x - settled.position.x, z - settled.position.z)
            if settled_distance > .30 + 1e-9:
                raise WaypointError("Fresh post-release pose no longer confirms destination arrival")
            if goal_y is not None and abs(settled.position.y - goal_y) > .5 + 1e-9:
                raise WaypointError(
                    "Fresh post-release pose no longer confirms destination height")
            result.update(position=asdict(settled.position), bearing=settled.bearing,
                          distance=settled_distance, acquired=settled.acquired)
        final_event = {key: result[key] for key in
            ("status", "name", "goal", "start", "position", "bearing", "distance", "pulses",
             "observedAtUtc", "releaseSucceeded", "desktopInputsDown")}
        if "acquired" in result:
            final_event["acquired"] = result["acquired"]
        emit(final_event)
        # Operator STOP always wins, including a race with an encounter receipt.
        if stop.is_set():
            raise stopped_with_receipt((receipt.get("reason") if receipt["status"] == "stopped" else None)
                                       or "operator STOP; native movement release verified")
        if receipt["status"] == "stopped":
            raise stopped_with_receipt(receipt.get("reason") or "Stopped; native release verified")
        if (survival_guard and receipt["status"] == "halted"
                and receipt.get("reason") in {"survival-hp-drop", "survival-combat"}):
            raise EncounterInterrupted(result)
        if receipt["status"] != "arrived":
            reason = receipt.get("reason") or (str(stderr[0]) if stderr and stderr[0] else None)
            raise WaypointError(reason or "Native continuous movement failed")
        return result


def route_motion_seed(adapter, snapshot):
    """Bound calibration candidates against the conservative bootstrap seed."""
    speed, turn_rate = 6.25, 175.0
    if callable(getattr(adapter, "calibrations", None)):
        try:
            calibration = adapter.calibrations(snapshot)["w"]
            candidate = math.hypot(calibration.dx_per_ms, calibration.dz_per_ms) * 1000
            if math.isfinite(candidate) and 0.1 <= candidate <= 30:
                speed = max(speed, candidate)
        except (KeyError, TypeError, ValueError, AttributeError):
            pass  # Optional candidate is unavailable; keep the bootstrap seed.
    if callable(getattr(adapter, "turn_rates", None)):
        try:
            rates = adapter.turn_rates()
            candidate = min(abs(rates["a"]), abs(rates["d"])) * 1000
            if math.isfinite(candidate) and 1 <= candidate <= 1000:
                turn_rate = min(turn_rate, candidate)
        except (KeyError, TypeError, ValueError, AttributeError):
            pass  # Native follower also estimates turns independently.
    return speed, turn_rate


def _receipt_speed_seed(receipt, speed):
    """Raise the next span's speed seed from validated in-hold path samples."""
    try:
        intervals, down = [], None
        for event in receipt.get("keySendEvents", []):
            if event.get("key", "").upper() != "W":
                continue
            if event.get("phase") == "key-down":
                down = datetime.fromisoformat(event["callCompletedAtUtc"].replace("Z", "+00:00"))
            elif event.get("phase") == "key-up" and down is not None:
                up = datetime.fromisoformat(event["callStartedAtUtc"].replace("Z", "+00:00"))
                intervals.append((down, up))
                down = None
        samples = []
        for item in receipt.get("path", []):
            t = datetime.fromisoformat(item["observedAtUtc"].replace("Z", "+00:00"))
            samples.append((t, float(item["x"]), float(item["z"])))
        rates = []
        for a, b in zip(samples, samples[1:]):
            dt = (b[0] - a[0]).total_seconds()
            if .05 <= dt <= 1 and any(start <= a[0] < b[0] <= end for start, end in intervals):
                candidate = math.hypot(b[1] - a[1], b[2] - a[2]) / dt
                if math.isfinite(candidate) and .1 <= candidate <= 30:
                    rates.append(candidate)
        if rates:
            rates.sort()
            speed = max(speed, rates[math.floor((len(rates) - 1) * .9)])
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return speed


def response_estimate(receipt):
    """Summarize observed response intervals, not guaranteed response limits.

    Requires a current trusted, release-validated receipt supplied by caller.
    Onset includes sampling latency; coast uses sampled positions and may be
    censored by sparse samples or prior settling.
    """
    result = {"onsetIntervalsSeconds": [], "coastObservations": [],
              "turnRatesDegreesPerSecond": [], "limitations":
              "Onset includes sampling latency; coast is sampled and may be censored."}
    try:
        raw_path, raw_events = receipt["path"], receipt["keySendEvents"]
        if len(raw_path) < 3 or len(raw_path) >= 500:
            return result
        def stamp(value):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("timestamp missing timezone")
            return dt.timestamp()
        poses = [(stamp(p["observedAtUtc"]), float(p["x"]), float(p["z"]),
                  float(p["bearing"])) for p in raw_path]
        if any(not all(math.isfinite(v) for v in p) for p in poses):
            return result
        if any(a[0] >= b[0] or b[0] - a[0] > .5 for a, b in zip(poses, poses[1:])):
            return result
        events = []
        for e in raw_events:
            key, phase = e["key"].upper(), e["phase"]
            if key not in ("W", "A", "D") or phase not in ("key-down", "key-up"):
                continue
            if e.get("inserted") is not True:
                return result
            start, end = stamp(e["callStartedAtUtc"]), stamp(e["callCompletedAtUtc"])
            if end < start:
                return result
            events.append((start, end, key, phase))
        if any(a[0] > b[0] for a, b in zip(events, events[1:])):
            return result
        active, holds = {}, []
        for start, end, key, phase in events:
            if phase == "key-down":
                if key in active:
                    return result
                active[key] = (start, end)
            else:
                if key not in active:
                    return result
                down = active.pop(key)
                holds.append((key, down[0], down[1], start, end))
        if active:
            return result
        def planar(a, b):
            return math.hypot(b[1]-a[1], b[2]-a[2])
        def angular(a, b):
            return (b[3]-a[3]+180) % 360 - 180
        for key, ds, de, us, ue in holds:
            # A simultaneous key can produce the motion under examination.
            if any(other != key and ods < ue and ous > ds
                   for other, ods, _, ous, _ in holds):
                continue
            before = [p for p in poses if p[0] <= ds]
            if not before or ds - before[-1][0] > .2:
                continue
            baseline = before[-1]
            if len(before) < 2 or before[-1][0]-before[-2][0] > .2:
                continue
            if planar(before[-2], baseline) > .02 or abs(angular(before[-2], baseline)) > 1:
                continue
            current = [p for p in poses if ds < p[0] <= us]
            previous = baseline
            for pose in current:
                if key == "W":
                    heading = math.radians(baseline[3])
                    delta = ((pose[1]-baseline[1])*math.sin(heading) +
                             (pose[2]-baseline[2])*math.cos(heading))
                else:
                    delta = angular(baseline, pose) * (1 if key == "A" else -1)
                if delta > (.04 if key == "W" else 1.0):
                    result["onsetIntervalsSeconds"].append({"key": key,
                        "lower": 0.0, "upper": max(0.0, pose[0]-ds),
                        "thresholdLower": max(0.0, previous[0]-de)})
                    break
                previous = pose
            if key in ("A", "D"):
                for a, b in zip(current, current[1:]):
                    dt = b[0]-a[0]
                    if .05 <= dt <= .2 and planar(a, b) <= .02:
                        rate = angular(a, b) * (1 if key == "A" else -1) / dt
                        if 20 <= rate <= 1000:
                            result["turnRatesDegreesPerSecond"].append(rate)
            # Pre-up to settled displacement is sampled and is not a stop guarantee.
            # Require prior correct-axis movement and inspect successive post-up
            # pairs until settled or another input makes attribution ambiguous.
            pre = [p for p in poses if p[0] <= us]
            next_action = min((e[0] for e in events if e[0] > us), default=float("inf"))
            post = [p for p in poses if ue <= p[0] < min(next_action, ue + 1)]
            if (receipt.get("status") == "arrived" and len(pre) >= 2 and
                    us-pre[-1][0] <= .2 and pre[-1][0]-pre[-2][0] <= .2):
                if key == "W":
                    heading = math.radians(baseline[3])
                    prior = ((pre[-1][1]-pre[-2][1])*math.sin(heading) +
                             (pre[-1][2]-pre[-2][2])*math.cos(heading))
                else:
                    prior = angular(pre[-2], pre[-1]) * (1 if key == "A" else -1)
                if prior > (.02 if key == "W" else 1.0):
                    for p, q in zip(post, post[1:]):
                        if q[0]-p[0] > .2:
                            break
                        stable = planar(p, q) <= .02 and abs(angular(p, q)) <= 1
                        if stable:
                            result["coastObservations"].append({"key": key,
                                "sampledDistance": planar(pre[-1], q) if key == "W" else abs(angular(pre[-1], q)),
                                "firstPostUpDistance": planar(post[0], q) if key == "W" else abs(angular(post[0], q)),
                                "immediate": p is post[0], "censored": True})
                            break
        return result
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return {"onsetIntervalsSeconds": [], "coastObservations": [],
                "turnRatesDegreesPerSecond": [], "limitations": result["limitations"]}


def merge_response_seed(receipt, delay, turn_rate):
    """Keep conservative seeds; qualified observations can only tighten them."""
    estimate = response_estimate(receipt)
    intervals = [v["upper"] for v in estimate["onsetIntervalsSeconds"]
                 if v["key"] in ("W", "A", "D") and 0 <= v["upper"] <= .5]
    if intervals:
        delay = max(delay, max(intervals))
    rates = sorted(estimate["turnRatesDegreesPerSecond"])
    if len(rates) >= 2:
        turn_rate = min(turn_rate, max(20.0, rates[math.floor((len(rates)-1)*.1)]))
    return delay, turn_rate, estimate


def route_spans(rows, heights, kinds, *, origin=None, speed=6.25, turn_rate=175.0,
                response_delay=.10, observed_coast=0.0):
    """Plan inclusive guide spans; automatic boundaries retain pass semantics.

    The default 6.25 units/s and 175 degrees/s are bootstrap estimates, not
    measurements of the current run. Feasibility is geometric,
    not a guarantee of physical passage or obstacle clearance.
    """
    count = len(rows)
    if count == 0 or len(heights) != count or len(kinds) != count:
        raise ValueError("Route span inputs must have matching nonempty lengths")
    speed = _finite(speed, "route speed")
    turn_rate = _finite(turn_rate, "route turn rate")
    if not 0.1 <= speed <= 30 or not 1 <= turn_rate <= 1000:
        raise ValueError("Route motion seed outside supported bounds")
    response_delay = _finite(response_delay, "response delay")
    if not 0 <= response_delay <= .5:
        raise ValueError("Response delay outside supported bounds")
    observed_coast = _finite(observed_coast, "observed coast")
    if not 0 <= observed_coast <= 5:
        raise ValueError("Observed coast outside supported bounds")
    radius = speed / math.radians(turn_rate)
    runout = [0.0] * count
    turns = [0.0] * count
    automatic = set()
    for i in range(0 if origin is not None else 1, count - 1):
        if kinds[i] != "pass":
            continue
        previous = origin if i == 0 else (rows[i-1][1], rows[i-1][2])
        ax, az = rows[i][1] - previous[0], rows[i][2] - previous[1]
        bx, bz = rows[i+1][1] - rows[i][1], rows[i+1][2] - rows[i][2]
        a, b = math.hypot(ax, az), math.hypot(bx, bz)
        if a < 1e-9 or b < 1e-9:
            # A duplicate cannot conceal a reversal. A guide at the fresh
            # origin needs no incoming tangent; native admission handles it.
            if not (i == 0 and a < 1e-9 and b >= 1e-9):
                automatic.add(i)
            continue
        angle = math.acos(max(-1.0, min(1.0, (ax*bx + az*bz)/(a*b))))
        if angle < 1e-6:
            continue
        turns[i] = math.copysign(angle, ax*bz - az*bx)
        cosine = math.cos(angle / 2)
        if cosine < 1e-6:
            automatic.add(i)
            continue
        tangent = radius * math.tan(angle / 2)
        # Allow for bounded input response and release travel, without assuming
        # a walk toggle or a verified instantaneous turn rate.
        needed = tangent + max(speed * response_delay * math.sin(angle / 2), observed_coast)
        if radius * (1 / cosine - 1) > .5 or needed > min(a, b):
            automatic.add(i)
        else:
            runout[i] = needed
    # Adjacent corners cannot both consume the same short segment.
    for i in range(0, count - 2):
        if runout[i] and runout[i+1]:
            length = math.hypot(rows[i+1][1] - rows[i][1], rows[i+1][2] - rows[i][2])
            if runout[i] + runout[i+1] > length:
                # Samples along one smooth arc share steering rather than
                # executing two independent fillets. Require consistent turn
                # direction and sufficient radius for the shared segment.
                shared_angle = (abs(turns[i]) + abs(turns[i+1])) / 2
                smooth_arc = (turns[i] * turns[i+1] > 0 and shared_angle > 0
                              and max(abs(turns[i]), abs(turns[i+1]))
                                  <= 1.5 * min(abs(turns[i]), abs(turns[i+1]))
                              and length / shared_angle >= radius * 1.15)
                if not smooth_arc:
                    automatic.add(i)
                    automatic.add(i+1)
    spans, start = [], 0
    for i, kind in enumerate(kinds):
        if kind == "stop" or i in automatic or i == count - 1:
            spans.append((start, i, i in automatic and kind != "stop" and i != count - 1))
            start = i + 1
    return spans


def run_continuous_route(adapter, points, stop, emit=lambda event: None, *,
                         face_waypoints=True, entry_check=None, survival_guard=False,
                         goal_heights=None, point_kinds=None, reservation=None, deadline=None):
    """Follow real route waypoints with one reservation and one shared deadline.

    Ordinary guides share one native forward run. Explicit stops and the final
    destination end a span with settled arrival. Live observations are separate
    from passage events validated after release for durable checkpoints.
    """
    from scripts.physical_waypoints import read_stationary, route_points, Stopped, WaypointError
    if getattr(adapter, "_continuous_input_release_fault", False):
        raise WaypointError("Previous continuous movement cleanup remains unverified")
    if stop.is_set():
        raise Stopped("Stopped; no movement helper launched")
    rows = route_points(points)
    if not 1 <= len(rows) <= MAX_WAYPOINTS:
        raise WaypointError(f"Route must have 1-{MAX_WAYPOINTS} waypoints")
    if goal_heights is None:
        heights = [None] * len(rows)
    elif not isinstance(goal_heights, (list, tuple)) or len(goal_heights) != len(rows):
        raise WaypointError("Route goal heights must match its waypoints")
    else:
        heights = [None if value is None else _finite(value, "route goal height")
                   for value in goal_heights]
    if point_kinds is None:
        kinds = ["pass"] * len(rows)
    elif (not isinstance(point_kinds, (list, tuple)) or len(point_kinds) != len(rows)
          or any(kind not in ("pass", "stop") for kind in point_kinds)):
        raise WaypointError("Route point kinds must match its waypoints and be pass or stop")
    else:
        kinds = list(point_kinds)
    kinds[-1] = "stop"
    started = time.monotonic()
    if deadline is not None:
        deadline = _finite(deadline, "route deadline")
    deadline = min(started + MAX_TRIP_SECONDS, deadline) if deadline is not None else started + MAX_TRIP_SECONDS
    with (adapter.reserve() if reservation is None else nullcontext(reservation)) as lease:
        initial = read_stationary(adapter, stop)
        lease.check()
        if entry_check is not None:
            entry_check(initial.position)
        planned = math.hypot(rows[0][1] - initial.position.x, rows[0][2] - initial.position.z)
        planned += sum(math.hypot(later[1] - earlier[1], later[2] - earlier[2])
                       for earlier, later in zip(rows, rows[1:]))
        if planned > MAX_ROUTE_DISTANCE:
            raise WaypointError(f"Route exceeds {MAX_ROUTE_DISTANCE:g} world units")
        legs = []
        speed, turn_rate = route_motion_seed(adapter, initial)
        response_delay, observed_coast = .10, 0.0
        batch_start = 0
        origin = (initial.position.x, initial.position.z)
        while batch_start < len(rows):
            _, relative_end, automatic_corner = route_spans(
                rows[batch_start:], heights[batch_start:], kinds[batch_start:],
                origin=origin, speed=speed, turn_rate=turn_rate, response_delay=response_delay,
                observed_coast=observed_coast)[0]
            end = batch_start + relative_end
            label, x, z = rows[end]
            goal_y = heights[end]
            guides = []
            for index in range(batch_start, end):
                guide = {"name": rows[index][0], "x": rows[index][1], "z": rows[index][2]}
                if heights[index] is not None:
                    guide["y"] = heights[index]
                guides.append(guide)
            if stop.is_set():
                raise Stopped("Stopped; no further input")
            remaining = math.floor(deadline - time.monotonic())
            if remaining < 1:
                raise WaypointError(f"Trip exceeded {MAX_TRIP_SECONDS} seconds")

            def named(event):
                if event.get("status") == "passed":
                    legs.append(dict(event, elapsedSeconds=None, totalHoldMs=None,
                                     nativeReceipt=adapter.last_input_receipt))
                    emit(event)
                elif event.get("status") == "route-progress":
                    index = event.get("index")
                    position = event.get("position")
                    if (type(index) is not int or not 0 <= index < len(guides)
                            or event.get("name") != guides[index]["name"]
                            or not isinstance(position, dict)):
                        return
                    try:
                        for axis in ("x", "y", "z"):
                            _finite(position.get(axis), "progress " + axis)
                    except ValueError:
                        return
                    emit(dict(event, batchIndex=index, index=batch_start + index,
                              waypointCount=len(rows), observedPointNumber=batch_start + index + 1,
                              source=event.get("source", "pose")))
                elif not (automatic_corner and event.get("status") == "arrived"):
                    emit(dict(event, name=label))

            leg = move_to(adapter, x, z, stop, named, reservation=lease,
                          max_seconds=remaining, survival_guard=survival_guard,
                          goal_y=goal_y, path_points=guides)
            leg = dict(leg, name=label,
                       elapsedSeconds=round(float(leg.get("elapsedMilliseconds", 0)) / 1000, 3),
                       totalHoldMs=(float(leg["heldInputMilliseconds"])
                                    if (type(leg.get("heldInputMilliseconds")) in (int, float)
                                        and math.isfinite(leg["heldInputMilliseconds"])) else None),
                       nativeReceipt=adapter.last_input_receipt)
            if automatic_corner:
                leg.update(status="passed", passageVerified=True)
                emit(dict(leg, index=end, source="settled-corner"))
            trusted_receipt = adapter.last_input_receipt or {}
            speed = _receipt_speed_seed(trusted_receipt, speed)
            response_delay, turn_rate, response = merge_response_seed(
                trusted_receipt, response_delay, turn_rate)
            for coast in response["coastObservations"]:
                if coast["key"] == "W" and 0 <= coast["sampledDistance"] <= 5:
                    observed_coast = max(observed_coast, coast["sampledDistance"])
            leg["responseEstimate"] = response
            legs.append(leg)
            origin = (float(leg["position"]["x"]), float(leg["position"]["z"])) if (
                isinstance(leg.get("position"), dict) and
                all(type(leg["position"].get(k)) in (int, float) and
                    math.isfinite(leg["position"][k]) for k in ("x", "z"))) else (x, z)
            batch_start = end + 1
        return legs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--z", required=True, type=float)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    from scripts.physical_waypoints import (DEFAULT_BASIS, PhysicalAdapter, Stopped,
                                             WaypointError, cli_stop_controls)
    stop = threading.Event()
    adapter = None
    try:
        adapter = PhysicalAdapter(args.expected_host, args.physical_pid, DEFAULT_BASIS)
        if args.execute:
            # Install the SIGINT latch before F8 registration and before the
            # native child can launch. Ctrl+C/F8 set the shared STOP event; the
            # movement wrapper remains alive until native release evidence (or
            # exact-target recovery) is complete.
            with cli_stop_controls(stop):
                result = move_to(adapter, args.x, args.z, stop)
        else:
            result = preview_move(adapter, args.x, args.z, stop)
        if args.json:
            print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        else:
            print(f"{result['status']}: {result['distance']:.3f} units")
        return 0
    except Stopped as exc:
        trusted = (getattr(adapter, "last_input_receipt", None)
                   if getattr(adapter, "_continuous_move_receipt_trusted", False) else None)
        launched = bool(getattr(adapter, "_continuous_move_launched", False))
        result = {"status": "stopped", "reason": str(exc),
                  "inputSent": trusted.get("inputSent") if isinstance(trusted, dict) else None if launched else False,
                  "receipt": trusted,
                  "recovery": getattr(adapter, "_continuous_move_recovery", None)}
        print(json.dumps(result, separators=(",", ":"), allow_nan=False) if args.json else str(exc))
        return 2
    except (WaypointError, ValueError, OSError) as exc:
        trusted = (getattr(adapter, "last_input_receipt", None)
                   if getattr(adapter, "_continuous_move_receipt_trusted", False) else None)
        launched = bool(getattr(adapter, "_continuous_move_launched", False))
        status = ("halted" if isinstance(trusted, dict) and trusted.get("status") == "arrived"
                  else trusted.get("status") if isinstance(trusted, dict)
                  else "halted" if launched else "blocked")
        result = {"status": status, "reason": str(exc),
                  "inputSent": trusted.get("inputSent") if isinstance(trusted, dict) else None if launched else False,
                  "receipt": trusted,
                  "recovery": getattr(adapter, "_continuous_move_recovery", None)}
        print(json.dumps(result, separators=(",", ":"), allow_nan=False) if args.json else str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
