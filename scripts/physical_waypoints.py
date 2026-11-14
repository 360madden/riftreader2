#!/usr/bin/env python3
"""Small physical-RIFT waypoint prototype, using the existing RR2 controller.

Run without a CLI action for the waypoint window. CLI movement actions require
--execute and are bounded. No memory writes, addon, service, Workbridge or mesh
required.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, nullcontext
from dataclasses import asdict, dataclass
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Direct execution names this module ``__main__``.  Movement and survival
# helpers import the canonical package name, so publish that alias before any
# helper can define an exception boundary against a second copy of this module.
if __name__ == "__main__":
    sys.modules["scripts.physical_waypoints"] = sys.modules[__name__]

from scripts import physical_rift
from scripts.movement_controller import Position, WaypointController, planar_distance
from scripts.nav_physical_reservation import PhysicalClientIdentity, PhysicalClientReservation
from scripts.physical_move_basis_waypoint import read_basis, candidate_calibrations
from scripts.waypoint_map import LocalMap, ZOOM_RADII, draw_route, fit_route_radius, route_length
from scripts.waypoint_heading import choose_turn, heading_error
from scripts.waypoint_seed_feedback import verify_translation, verify_turn
from scripts.waypoint_limits import (
    MAX_ROUTE_DISTANCE, MAX_WAYPOINTS, MAX_TRIP_SECONDS,
    MAX_TRIP_PULSES, MAX_TRIP_HOLD_MS,
)

DEFAULT_BASIS = ROOT / "config/physical-movement-basis.amd-desktop.json"


class WaypointError(ValueError):
    pass


class Stopped(WaypointError):
    pass


class OwnedWaypointMarkers:
    """One owned read-only marker child, stopped only through its unique file."""
    def __init__(self, root=ROOT, *, popen=None):
        self.root = Path(root)
        self.popen = popen or subprocess.Popen
        self.child = None
        self.stop_path = None
        self.output = None
        self.appearance_path = (self.root / "artifacts" / "waypoint-marker-style.json").absolute()
        self.route_updates_path = None
        self.pose_path = None
        self.exploration_path = None
        self.radar_path = (self.root / "artifacts" / "waypoint-radar-style.json").absolute()
        self.status_path = None
        self.identity = None
        self.stop_requested = False
        self.exit_code = None

    def running(self):
        if self.child is not None:
            result = self.child.poll()
            if result is not None:
                self.exit_code = result
                self.child = None
        return self.child is not None

    def start(self, document, adapter, *, target_beacon=False, landmark_number=None, companion=None):
        if companion is not None:
            from scripts.physical_waypoint_overlay import validate_companion
            companion = validate_companion(companion)
        if type(target_beacon) is not bool:
            raise WaypointError("Invalid target beacon option")
        if landmark_number is not None and (type(landmark_number) is not int
                or not 1 <= landmark_number <= len(document.get("waypoints", []))):
            raise WaypointError("Select one saved marker to guide to")
        if self.running():
            raise WaypointError("Markers are already open or closing")
        from scripts.live_physical_waypoints import load_route
        from scripts.waypoint_progress import write_json_atomic
        identity = adapter.binding["runtimeIdentity"]
        token = uuid.uuid4().hex
        directory = self.root / "artifacts"
        route_path = directory / ("waypoint-markers-route-" + token + ".json")
        self.output = directory / ("waypoint-markers-summary-" + token + ".json")
        self.stop_path = directory / ("waypoint-markers-stop-" + token + ".signal")
        self.route_updates_path = (directory / ("waypoint-markers-updates-" + token + ".json")).absolute()
        self.pose_path = (directory / ("waypoint-markers-pose-" + token + ".json")).absolute()
        self.status_path = (directory / ("waypoint-markers-status-" + token + ".json")).absolute()
        self.exploration_path = (directory / ("waypoint-exploration-" + token + ".json")).absolute()
        write_json_atomic(self.exploration_path, {"version": 1, "owner": None,
                                                "acquiredMonotonic": None, "guidance": None, "trail": []})
        write_json_atomic(route_path, document)
        qt_executable = self.root / ".local" / "overlay-venv" / "Scripts" / "pythonw.exe"
        presenter = "qt" if qt_executable.is_file() else "native"
        recorded = load_route(route_path, expected_identity=identity, allow_empty=presenter == "qt")
        if any(str(recorded["identity"].get(key, "")).casefold() != str(identity[key]).casefold()
               for key in ("machine", "gameBuildSha256", "unitKey")):
            raise WaypointError("Recorded route belongs to another host, build or player")
        target = adapter.target
        if (identity["processId"] != adapter.pid or identity["processId"] != target["processId"]
                or str(identity["processStartUtcTicks"]) != str(target["processStartUtcTicks"])
                or identity["gameBuildSha256"].casefold() != target["executableSha256"].casefold()
                or type(target["hwnd"]) is not int or target["hwnd"] <= 0):
            raise WaypointError("Current RIFT identity is unavailable")
        self.identity = deepcopy(identity)
        write_json_atomic(self.route_updates_path, {"route": document, "landmarkNumber": landmark_number})
        executable = qt_executable if presenter == "qt" else Path(sys.executable).with_name("pythonw.exe")
        if presenter == "qt" and not self.radar_path.exists():
            from scripts.waypoint_explore_ui import RADAR_DEFAULTS
            write_json_atomic(self.radar_path, RADAR_DEFAULTS)
        command = [str(executable), str(self.root / "scripts" / "live_physical_waypoints.py"),
                   "--expected-host", identity["machine"], "--physical-pid", str(adapter.pid),
                   "--expected-unit-key", identity["unitKey"],
                   "--expect-start-ticks", str(target["processStartUtcTicks"]),
                   "--expect-sha256", target["executableSha256"], "--expect-hwnd", hex(target["hwnd"]),
                   "--route", str(route_path), "--duration", "0", "--max-age", ".35", "--presenter", presenter,
                   "--output", str(self.output), "--stop-file", str(self.stop_path),
                   "--status-file", str(self.status_path),
                   "--appearance-file", str(self.appearance_path),
                   "--route-updates-file", str(self.route_updates_path),
                   "--pose-file", str(self.pose_path),
                   "--progress-file", str(self.root / "artifacts" / "waypoint-current-progress.json")]
        if target_beacon:
            command.append("--target-beacon")
        if presenter == "qt":
            command.extend(["--radar-file", str(self.radar_path)])
            command.extend(["--exploration-file", str(self.exploration_path)])
        if landmark_number is not None:
            command.extend(["--landmark-number", str(landmark_number)])
        if companion is not None:
            command.extend(["--companion-window", json.dumps(companion, separators=(",", ":"))])
        self.child = self.popen(command, cwd=self.root,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.stop_requested = False
        self.exit_code = None

    def update(self, document, *, landmark_number=None):
        if not self.running() or self.stop_requested or self.identity is None:
            raise WaypointError("Markers are not active")
        if landmark_number is not None and (type(landmark_number) is not int
                or not 1 <= landmark_number <= len(document.get("waypoints", []))):
            raise WaypointError("Select one saved marker to guide to")
        from scripts.waypoint_measurements import parse_marker_projection_route
        parse_marker_projection_route(document, self.identity, allow_empty=True)
        from scripts.waypoint_progress import write_json_atomic
        write_json_atomic(self.route_updates_path, {"route": document, "landmarkNumber": landmark_number})

    def stop(self):
        if self.running() and not self.stop_requested:
            self.stop_path.touch(exist_ok=False)
            self.stop_requested = True


def beacon_display_status(running, closing, display):
    """Explain fresh presenter feedback without equating a reader with visibility."""
    def state(value, reason, visible=None):
        return dict(state=value, reason=reason, visible=visible)
    if closing: return state("stopping", "Waiting for the shared overlay reader to exit")
    if not running: return state("stopped", "Overlay reader stopped", False)
    if not isinstance(display, dict): return state("unknown", "Reader running; display feedback unavailable")
    snapshot = display.get("presenterSnapshot") or display.get("snapshot") or {}
    if snapshot.get("displayAllowed") is False:
        return state("hidden", "Switch to RIFT or this Waypoints window", False)
    if display.get("overlayHasFrame") is False:
        return state("waiting", "Waiting for a fresh camera frame", False)
    if display.get("nativeWindowVisible") is False or display.get("qtWidgetVisible") is False:
        return state("hidden", "Overlay window is hidden; awaiting a valid frame", False)
    age, maximum = display.get("frameAgeSeconds"), display.get("maxAgeSeconds", .35)
    if (display.get("nativeWindowVisible") is True and display.get("overlayHasFrame") is True
            and snapshot.get("displayAllowed") is True and type(age) in (int,float)
            and type(maximum) in (int,float) and 0 <= age <= maximum):
        return state("visible", "Overlay visible · fresh camera frame", True)
    return state("unknown", "Reader running; fresh visible overlay not confirmed")


@dataclass(frozen=True)
class Snapshot:
    position: Position
    bearing: float
    acquired: float
    source: str
    selected_target: dict | None = None


def target_waypoint(snapshot):
    """Save a fresh selected-target location, never a moving follow command."""
    target = snapshot.selected_target
    if not isinstance(target, dict) or target.get("status") != "candidate":
        raise WaypointError("Select a target with an available position first.")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(target["sampledAtUtc"])).total_seconds()
        point = target["positionXYZCandidate"]
        px, py, pz = (finite(point[axis]) for axis in ("x", "y", "z"))
    except (KeyError, TypeError, ValueError) as exc:
        raise WaypointError("Selected target position is unavailable.") from exc
    if not -.1 <= age <= 2 or time.monotonic() - snapshot.acquired > 2:
        raise WaypointError("Selected target position expired; try Add Target again.")
    # A planar waypoint cannot represent a different floor. Keep target
    # selection useful without offering travel to elevated/flying entities.
    if abs(py - snapshot.position.y) > 1:
        raise WaypointError("Selected target is on a different height; choose a ground point.")
    return "Selected target", px, pz


def _target_name_candidate(report, target, observer, first, last):
    if (not isinstance(report, dict) or report.get("status") != "complete"
            or report.get("workflow") != "physical"
            or str(report.get("ownerHost", "")).casefold() != str(target.get("hostName", "")).casefold()
            or report.get("nativeRead") != "target-name" or report.get("target") != target):
        return None
    try:
        values = report["nativeValues"]
        key, text = last["targetKey"], values["selectedBaseNameCandidate"]
        source, digest = report["nativeOutput"], report["nativeSourceSha256"]
        if (values["status"] != "available-candidate" or values["selfKey"] != observer["unitKey"]
                or values["targetKey"] != key or any(not isinstance(k, str)
                    or re.fullmatch(r"[1-9][0-9]{0,19}", k) is None or int(k) >= 2**64
                    for k in (key, values["selfKey"]))
                or observer["processId"] != target["processId"]
                or str(observer["processStartUtcTicks"]) != str(target["processStartUtcTicks"])
                or observer["gameBuildSha256"].casefold() != target["executableSha256"].casefold()
                or observer["machine"].casefold() != target["hostName"].casefold()
                or not isinstance(text, str) or not text.strip() or not text.isprintable() or len(text) > 80
                or not isinstance(source, str) or not source.strip()
                or re.fullmatch(r"[A-Fa-f0-9]{64}", digest) is None
                or not isinstance(values["qualification"], str) or not values["qualification"].strip()):
            return None
        first_time, started, sampled, last_time = map(physical_rift._utc_tick_order_key, (
            first["sampledAtUtc"], values["startedAtUtc"], values["sampledAtUtc"], last["sampledAtUtc"]))
        if (not first_time <= started <= sampled <= last_time
                or not -.1 <= (datetime.now(timezone.utc) - started[0]).total_seconds() <= 2):
            return None
        return {"text": text.strip(), "source": source, "sourceSha256": digest,
                "startedAtUtc": values["startedAtUtc"], "sampledAtUtc": values["sampledAtUtc"],
                "qualification": values["qualification"], "targetKey": key, "observerKey": values["selfKey"],
                "processIdentity": deepcopy(target)}
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _read_target_waypoint(adapter, pose):
    waypoint = target_waypoint(pose)
    read_name = getattr(adapter, "read_target_name", None)
    if read_name is None:
        return pose, waypoint, None
    target = deepcopy(adapter.target)
    observer = deepcopy(adapter.binding["runtimeIdentity"])
    try:
        report = read_name()
    except (OSError, ValueError, subprocess.SubprocessError):
        report = None
    current = adapter.read(include_target=True)
    waypoint = target_waypoint(current)
    if (adapter.target != target or adapter.binding["runtimeIdentity"] != observer
            or not pose.selected_target.get("targetKey")
            or pose.selected_target["targetKey"] != current.selected_target.get("targetKey")):
        raise WaypointError("Selected target or player changed; try Add Target again.")
    candidate = _target_name_candidate(report, target, observer, pose.selected_target, current.selected_target)
    return current, waypoint, candidate


@dataclass
class TripBudget:
    """A single budget shared by every controller and waypoint in a trip."""
    started: float
    pulses: int = 0
    hold_ms: int = 0

    def check(self, action=None):
        if time.monotonic() - self.started > MAX_TRIP_SECONDS:
            raise WaypointError(f"Trip exceeded {MAX_TRIP_SECONDS // 60} minutes")
        if action is not None and (self.pulses >= MAX_TRIP_PULSES or self.hold_ms + action.hold_ms > MAX_TRIP_HOLD_MS):
            raise WaypointError("Trip input budget reached; stopped before the next pulse")


class ForegroundStop:
    """Temporary F8 STOP; optionally preserve focus for the GUI's STOP button."""

    def __init__(self, window, stop, events):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.types = ctypes, wintypes
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.api.GetAncestor.restype = wintypes.HWND
        self.api.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.api.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.api.GetMessageW.restype = ctypes.c_int
        self.api.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.kernel.GetCurrentThreadId.restype = wintypes.DWORD
        self.handle = None
        if window is not None:
            window.update_idletasks()
            self.handle = self.api.GetAncestor(window.winfo_id(), 2)
            self.original_style = self.api.GetWindowLongPtrW(self.handle, -20)
            ctypes.set_last_error(0)
            self.api.SetWindowLongPtrW(self.handle, -20, self.original_style | 0x08000000)
            if ctypes.get_last_error():
                raise WaypointError("Could not enable a STOP window that preserves RIFT focus")
        self.thread_id = None
        self.registered = False
        self.ready = threading.Event()
        self.cancelled = threading.Event()

        def listen():
            self.thread_id = self.kernel.GetCurrentThreadId()
            registered = False
            try:
                registered = bool(self.api.RegisterHotKey(None, 1, 0x4000, 0x77))
                self.registered = registered
                self.ready.set()
                if self.cancelled.is_set():
                    return
                if not registered:
                    events.put({"status": "notice", "reason": "F8 unavailable; use the STOP button."})
                    return
                message = wintypes.MSG()
                while self.api.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    if message.message == 0x0312:
                        stop.set()
                        events.put({"status": "stopping", "reason": "F8 STOP requested; waiting for owned movement to release."})
            except Exception:
                stop.set()
                events.put({"status": "notice", "reason": "F8 listener failed; STOP requested."})
            finally:
                if registered:
                    self.api.UnregisterHotKey(None, 1)
                    if not self.cancelled.is_set():
                        stop.set()
                        events.put({"status": "notice", "reason": "F8 listener exited; STOP requested."})
                self.registered = False
                self.ready.set()

        self.thread = threading.Thread(target=listen, daemon=True)
        self.thread.start()
        try:
            if not self.ready.wait(1):
                raise WaypointError("F8 listener startup did not complete; no movement started")
            if window is None and not self.registered:
                raise WaypointError("F8 is unavailable; CLI input was not started")
        except BaseException:
            self.close()
            raise

    def close(self):
        self.cancelled.set()
        try:
            if self.thread.is_alive() and self.thread_id:
                posted = self.api.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
                if not posted and self.thread.is_alive():
                    raise WaypointError("Waiting for F8 listener shutdown")
                self.thread.join(timeout=1)
                if self.thread.is_alive():
                    raise WaypointError("Waiting for F8 listener shutdown")
        finally:
            if self.handle is not None:
                self.api.SetWindowLongPtrW(self.handle, -20, self.original_style)


@contextmanager
def cli_stop_controls(stop):
    # Raising KeyboardInterrupt inside subprocess.run can kill the child before
    # its unconditional key-up. Let it finish; the shared latch blocks the next
    # action just as GUI STOP does. Install before listener construction, too.
    previous = signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        with closing(ForegroundStop(None, stop, queue.Queue())):
            yield
    finally:
        signal.signal(signal.SIGINT, previous)


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise WaypointError("Coordinates must be finite numbers")
    return result


def capture_reason(capture):
    reason = capture.get("reason", "Native pose unavailable")
    detail = capture.get("detail")
    if detail:
        try:
            decoded = json.loads(detail)
            detail = decoded.get("error", detail) if isinstance(decoded, dict) else detail
        except (TypeError, ValueError):
            pass
        reason += ": " + " ".join(str(detail).split())
    return reason


def spatial_distance(a, b):
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def pose_drift(first, second):
    return (spatial_distance(first.position, second.position),
            abs(heading_error(second.bearing, first.bearing)))


def verify_stopped_pose(adapter, *, after="STOP"):
    """Measure two post-action poses; native key-release evidence stays separate."""
    evidence = {"status": "unavailable", "samples": [], "xyzDrift": None,
                "yawDriftDegrees": None, "maxXyzDrift": .05, "maxYawDriftDegrees": .5,
                "qualification": f"Two native candidate poses after {after}; separate from per-pulse key-release evidence"}
    try:
        time.sleep(.35)
        first = adapter.read()
        evidence["samples"].append({"source": first.source, "position": asdict(first.position),
                                    "bearing": first.bearing, "acquired": first.acquired})
        time.sleep(.25)
        second = adapter.read()
        evidence["samples"].append({"source": second.source, "position": asdict(second.position),
                                    "bearing": second.bearing, "acquired": second.acquired})
        drift, yaw = pose_drift(first, second)
        evidence.update(xyzDrift=drift, yawDriftDegrees=yaw,
                        status="movement-detected" if drift > .05 or yaw > .5 else "pass")
        if drift > .05:
            evidence["reason"] = f"Movement still detected after {after} ({drift:.3f} units); recovery required"
        elif yaw > .5:
            evidence["reason"] = f"Facing still changing after {after} ({yaw:.2f}°); recovery required"
    except Exception as exc:
        evidence.update(status="unavailable", reason=str(exc))
    return evidence


def read_stationary(adapter, stop):
    if stop.is_set():
        raise Stopped("Stopped; no further input")
    first = adapter.read()
    if stop.wait(.15):
        raise Stopped("Stopped; no further input")
    second = adapter.read()
    distance, yaw = pose_drift(first, second)
    if distance > .05 or yaw > .5:
        raise WaypointError("Player is moving or turning; let it settle before starting")
    return second


class PhysicalAdapter:
    """Fresh epoch-pinned input, with reusable numerical calibration seeds."""

    def __init__(self, host, pid, basis_path):
        self.host, self.pid = host, pid
        self.selection = physical_rift.select_physical(host, pid)
        if self.selection.get("status") != "ready":
            raise WaypointError(self.selection.get("reason", "RIFT unavailable"))
        self.target = self.selection["target"]
        # An unbound single-client launch may wait for RIFT; selection still
        # refuses ambiguity and resolves an explicit live PID before any reads.
        self.pid = pid = self.target["processId"]
        if type(self.target.get("hwnd")) is not int or self.target["hwnd"] <= 0:
            raise WaypointError("RIFT window is not ready; wait for the game window")
        self.basis, self.basis_sha = read_basis(basis_path)
        ident = self.basis["identity"]
        if (ident["machine"].casefold() != host.casefold()
                or ident["gameBuildSha256"].casefold() != self.target["executableSha256"].casefold()):
            raise WaypointError("Movement seed belongs to another host/build; current build calibration required")
        self.unit_key = ident["unitKey"]
        self.basis_reused = (ident["processId"] != pid
                             or ident["processStartUtcTicks"] != self.target["processStartUtcTicks"])
        self.input_receipt_path = ROOT / "artifacts" / ("waypoint-input-" + uuid.uuid4().hex + ".jsonl")
        self.last_input_receipt = None
        # A basis stores measured speeds, not reusable process addresses. Keep its
        # provenance intact; acquire current owners/facing and prove player identity
        # before publishing the new binding. Every input still pins self.target.
        self.initial_pose = self.read()
        self.binding = {"mode": "reused-seed" if self.basis_reused else "measured-epoch",
                        "basisSha256": self.basis_sha, "calibrationIdentity": dict(ident),
                        "runtimeIdentity": {"machine": host, "processId": pid,
                            "processStartUtcTicks": self.target["processStartUtcTicks"],
                            "gameBuildSha256": self.target["executableSha256"],
                            "unitKey": self.unit_key}}

    def identity(self):
        completed = subprocess.run([str(physical_rift.NATIVE_EXE), "move-key", "--inspect",
                                    "--pid", str(self.pid), "--expect-start-ticks",
                                    self.target["processStartUtcTicks"], "--expect-sha256",
                                    self.target["executableSha256"], "--expect-hwnd",
                                    hex(self.target["hwnd"]), "--json"], cwd=ROOT,
                                   capture_output=True, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            result = json.loads(completed.stdout.splitlines()[-1])
            target = result["target"]
            same = (completed.returncode == 0 and result["status"] == "inspected-target"
                    and result["inputSent"] is False and result["focusRequested"] is False
                    and target["machineName"].casefold() == self.host.casefold()
                    and target["processId"] == self.pid
                    and str(target["processStartUtcTicks"]) == self.target["processStartUtcTicks"]
                    and target["executableSha256"].casefold() == self.target["executableSha256"].casefold()
                    and target["executablePath"].casefold() == self.target["executablePath"].casefold()
                    and int(target["windowHandle"], 16) == self.target["hwnd"])
        except (ValueError, IndexError, KeyError, TypeError):
            same = False
        if not same:
            raise WaypointError("RIFT process or window identity changed")
        return self.pinned_identity()

    def pinned_identity(self):
        return PhysicalClientIdentity(self.host, self.pid,
                                      int(self.target["processStartUtcTicks"]),
                                      self.target["executableSha256"].lower())

    def reserve(self):
        return PhysicalClientReservation(self.pinned_identity(), self.identity)

    def read(self, *, include_target=False):
        capture = physical_rift.read_native(self.selection, "facing", samples=1,
                                            include_target=include_target)
        if capture.get("status") != "complete":
            raise WaypointError(capture_reason(capture))
        values = capture["nativeValues"]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(values["sampledAtUtc"])).total_seconds()
        if not -0.1 <= age <= 2 or values["playerKey"] != self.unit_key:
            raise WaypointError("Stale pose or player identity changed")
        if values.get("positionSource") != "entity-owned-position-component+0x48":
            raise WaypointError("Entity-owned position unavailable")
        bearing = finite(values["bodyBearingDegreesCandidate"])
        point = values["positionXYZCandidate"]
        return Snapshot(Position(*(finite(point[k]) for k in ("x", "y", "z"))),
                        bearing, time.monotonic() - max(0, age), capture["nativeOutput"],
                        values.get("selectedTargetProjectionCandidate"))

    def calibrations(self, snapshot):
        # The empirical actor angle is the negative of our +Z -> +X bearing.
        return candidate_calibrations(self.basis, -snapshot.bearing)[0]

    def read_target_name(self):
        return physical_rift.read_native(self.selection, "target-name")

    def turn_rates(self):
        candidate = self.basis.get("turnCalibrationCandidate", {})
        try:
            rates = {key: finite(candidate["rates"][key]["degreesPerMillisecondCandidate"])
                     for key in ("a", "d")}
        except (KeyError, TypeError, ValueError) as exc:
            raise WaypointError("Turn calibration unavailable for this process") from exc
        if not .05 <= rates["a"] <= .5 or not -.5 <= rates["d"] <= -.05:
            raise WaypointError("Turn calibration direction or speed invalid")
        return rates

    def pulse(self, action, *, focus):
        command = [str(physical_rift.NATIVE_EXE), "move-key", "--pid", str(self.pid),
                   "--expect-start-ticks", self.target["processStartUtcTicks"],
                   "--expect-sha256", self.target["executableSha256"],
                   "--expect-hwnd", hex(self.target["hwnd"]),
                   "--key", action.key, "--hold-ms", str(action.hold_ms),
                   "--execute", "--json"]
        if not focus:
            command.append("--no-focus")
        # Do not kill the helper to implement STOP: its bounded executor owns
        # unconditional key release. STOP latches and prevents the next pulse.
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            receipt = json.loads(completed.stdout.splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise WaypointError("Input receipt unavailable; no retry") from exc
        # Retain failed/interrupted GUI receipts as well as successful pulses.
        # This is the evidence needed to distinguish a rejected input from a
        # released target-loss abort; a generic process exit code cannot do so.
        self.last_input_receipt = receipt
        with self.input_receipt_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, separators=(",", ":")) + "\n")
        same_identity = (receipt.get("processId") == self.pid
                         and str(receipt.get("processStartUtcTicks")) == self.target["processStartUtcTicks"]
                         and str(receipt.get("executableSha256", "")).casefold()
                             == self.target["executableSha256"].casefold())
        if (same_identity and receipt.get("releaseSucceeded") is True
                and (receipt.get("targetLost") is True or receipt.get("cancelled") is True)):
            raise Stopped("Target changed or lost foreground; Windows release accepted, game stop unverified")
        if (completed.returncode != 0 or receipt.get("boundedActionCompleted") is not True
                or receipt.get("keys") != [action.key]
                or receipt.get("holdMilliseconds") != action.hold_ms
                or receipt.get("releaseSucceeded") is not True
                or receipt.get("allRequestedKeyDownsInserted") is not True
                or receipt.get("insertionUncertain") is not False
                or receipt.get("targetLost") is not False or receipt.get("cancelled") is not False
                or receipt.get("processId") != self.pid
                or str(receipt.get("processStartUtcTicks")) != self.target["processStartUtcTicks"]
                or str(receipt.get("executableSha256", "")).casefold()
                    != self.target["executableSha256"].casefold()):
            raise WaypointError(receipt.get("reason") or receipt.get("error")
                                or "Input stopped or release unconfirmed; no retry")
        return receipt


def align_heading(adapter, target, current, stop, lease, budget, emit, *, focus=True):
    """Use measured A/D speeds as seeds; each released turn needs actual feedback."""
    rates = adapter.turn_rates()
    started = time.monotonic()
    anchor = current.position
    actions = []
    for _ in range(8):
        if stop.is_set():
            raise Stopped("Stopped; no further input")
        if time.monotonic() - started > 20:
            raise WaypointError("Facing exceeded its 20-second budget")
        if budget is not None:
            budget.check()
        lease.check()
        if time.monotonic() - current.acquired > 2:
            current = adapter.read()
        if time.monotonic() - current.acquired > 2:
            raise WaypointError("Pose expired before turn input")
        if spatial_distance(anchor, current.position) > .10:
            raise WaypointError("Player moved during facing; stopped")
        if time.monotonic() - started > 20:
            raise WaypointError("Facing exceeded its 20-second budget")
        if budget is not None:
            budget.check()
        action = choose_turn(current.bearing, target, rates)
        if action is None:
            return current, actions
        if stop.is_set():
            raise Stopped("Stopped; no further input")
        if budget is not None:
            budget.check(action)
        if time.monotonic() - current.acquired > 2 or time.monotonic() - started > 20:
            raise WaypointError("Pose or facing time budget expired before turn input")
        receipt = adapter.pulse(action, focus=focus and not actions)
        actions.append(receipt)
        if budget is not None:
            budget.pulses += 1
            budget.hold_ms += action.hold_ms
        if stop.wait(.5):
            raise Stopped("Stopped; turn key-up accepted")
        after = adapter.read()
        if spatial_distance(anchor, after.position) > .10:
            raise WaypointError("Turning moved the player; stopped")
        if getattr(adapter, "basis_reused", False):
            receipt["seedFeedback"] = dict(
                verify_turn(current, after, action.key, rates[action.key], receipt),
                beforeSource=current.source, afterSource=after.source)
        actual = heading_error(after.bearing, current.bearing)
        error = heading_error(target, after.bearing)
        if actual * rates[action.key] <= 0 or abs(actual) < .25:
            raise WaypointError("Turn response disagrees with the measured direction; stopped")
        if abs(error) > 4 and abs(error) >= abs(action.error_degrees) - .5:
            raise WaypointError("Turn did not improve facing; stopped")
        current = after
        emit({"status": "turning", "position": asdict(current.position), "bearing": current.bearing,
              "acquired":current.acquired,"headingError": error, "key": action.key, "holdMs": action.hold_ms})
    if time.monotonic() - started <= 20 and abs(heading_error(target, current.bearing)) <= 4:
        return current, actions
    raise WaypointError("Facing reached its eight-pulse budget")


def run_facing(adapter, stop, emit=lambda event: None, *, bearing=None, point=None):
    if (bearing is None) == (point is None):
        raise WaypointError("Choose one facing angle or waypoint")
    with adapter.reserve() as lease:
        current = read_stationary(adapter, stop)
        if point is not None:
            px, pz = (finite(value) for value in point)
            distance = math.hypot(px-current.position.x, pz-current.position.z)
            if distance > MAX_ROUTE_DISTANCE:
                raise WaypointError(f"Facing waypoint exceeds {MAX_ROUTE_DISTANCE:g} units")
            bearing = (math.degrees(math.atan2(px-current.position.x, pz-current.position.z))
                       if distance > .3 else current.bearing)
        target = heading_error(finite(bearing), 0)
        started = time.monotonic()
        current, actions = align_heading(adapter, target, current, stop, lease,
                                        TripBudget(started), emit)
        result = {"status": "facing", "position": asdict(current.position),
                  "bearing": current.bearing, "acquired":current.acquired,"targetBearing": target,
                  "headingError": heading_error(target, current.bearing),
                  "pulses": len(actions), "totalHoldMs": sum(row["holdMilliseconds"] for row in actions),
                  "elapsedSeconds": round(time.monotonic()-started, 3),
                  "allPulsesReleased": True, "actions": actions,
                  "calibrationBinding": getattr(adapter, "binding", None),
                  "qualification": "Candidate body facing; fresh runtime identity and post-release feedback"}
        emit(result)
        return result


def run_leg(adapter, goal_x, goal_z, stop, emit=lambda event: None, *, focus=True,
            reservation=None, budget=None, face_waypoints=False):
    """One existing bounded controller, with a fresh feedback read per pulse."""
    def check_stop():
        if stop.is_set():
            raise Stopped("Stopped; no further input")
        if budget is not None:
            budget.check()

    actions = []
    check_stop()
    with (adapter.reserve() if reservation is None else nullcontext(reservation)) as lease:
        start = current = (read_stationary(adapter, stop) if reservation is None else adapter.read())
        goal = Position(finite(goal_x), start.position.y, finite(goal_z))
        # Validate the original translation bounds before any optional turn.
        controller = WaypointController(adapter.calibrations(start), start.position, goal)
        leg_started = time.monotonic()
        turns = []
        if face_waypoints and planar_distance(current.position, goal) > .30:
            target = math.degrees(math.atan2(goal.x-current.position.x, goal.z-current.position.z))
            current, turns = align_heading(adapter, target, current, stop, lease, budget, emit, focus=focus)
        calibrations = adapter.calibrations(current)
        if face_waypoints:
            calibrations = {"w": calibrations["w"]}
        controller.calibrations = calibrations
        started = time.monotonic()
        emit({"status": "moving", "position": asdict(current.position), "bearing": current.bearing,
              "acquired":current.acquired,"distance": planar_distance(current.position, goal)})
        while True:
            check_stop()
            lease.check()
            if time.monotonic() - current.acquired > 2:
                current = adapter.read()
            controller.calibrations = adapter.calibrations(current)
            if face_waypoints:
                controller.calibrations = {"w": controller.calibrations["w"]}
            action = controller.decide(current.position, time.monotonic() - started)
            if action is None:
                # Two independent, released stationary observations confirm arrival.
                if controller.arrival_confirmations == 0:
                    controller.observe(current.position, time.monotonic() - started)
                check_stop()
                time.sleep(.15)
                settled = adapter.read()
                controller.confirm_released_settle(settled.position, current.position)
                if controller.status != "arrived":
                    raise WaypointError("Player left the arrival radius while settling")
                result = {"status": "arrived", "start": asdict(start.position),
                          "goal": asdict(goal), "position": asdict(settled.position),
                          "acquired":settled.acquired,
                          "distance": planar_distance(settled.position, goal), "bearing": settled.bearing,
                          "pulses": len(turns) + len(actions), "turnPulses": len(turns),
                          "movementPulses": len(actions),
                          "totalHoldMs": controller.total_hold_ms + sum(row["holdMilliseconds"] for row in turns),
                          "elapsedSeconds": round(time.monotonic() - leg_started, 3),
                          "allPulsesReleased": True, "actions": turns + actions,
                          "calibrationBinding": getattr(adapter, "binding", None),
                          "qualification": "Supervised open-ground prototype; candidate native pose, no obstacle routing"}
                emit(result)
                return result
            check_stop()
            if time.monotonic() - current.acquired > 2:
                raise WaypointError("Pose expired before input")
            if budget is not None:
                budget.check(action)
            receipt = adapter.pulse(action, focus=focus and not turns and not actions)
            actions.append(receipt)
            if budget is not None:
                budget.pulses += 1
                budget.hold_ms += action.hold_ms
            # Wait with all keys released for the observed motion to settle.
            if stop.wait(.15):
                raise Stopped("Stopped; current pulse released")
            before = current
            current = adapter.read()
            if getattr(adapter, "basis_reused", False):
                receipt["seedFeedback"] = dict(
                    verify_translation(before, current, adapter.calibrations(before)[action.key], receipt),
                    beforeSource=before.source, afterSource=current.source)
            feedback = controller.record_feedback(current.position, time.monotonic() - started)
            emit({"status": feedback.status, "position": asdict(current.position),
                  "acquired":current.acquired,"distance": feedback.distance_after, "pulse": len(actions), "bearing": current.bearing,
                  "key": action.key, "holdMs": action.hold_ms})


def route_points(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_WAYPOINTS:
        raise WaypointError(f"Route must have 1–{MAX_WAYPOINTS} points")
    if any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in rows):
        raise WaypointError("Each point needs name, X and Z")
    return [(str(row[0])[:80], finite(row[1]), finite(row[2])) for row in rows]


def run_route(adapter, points, stop, emit=lambda event: None, *, face_waypoints=False,
              entry_check=None):
    """Follow a bounded route using <=4-unit intermediate targets.

    The original controller's six-action, 900-ms, 12-second and corridor limits
    remain in force for each intermediate target. Ownership, STOP and the trip
    budget span the entire route, including arrivals and intermediate targets.
    """
    points = route_points(points)
    if stop.is_set():
        raise Stopped("Stopped; no further input")
    with adapter.reserve() as lease:
        current = read_stationary(adapter, stop)
        if entry_check is not None:
            entry_check(current.position)
        planned = route_length(current.position.x, current.position.z, points)
        if planned > MAX_ROUTE_DISTANCE:
            raise WaypointError(f"Route exceeds {MAX_ROUTE_DISTANCE:g} world units; choose a shorter route")
        budget = TripBudget(time.monotonic())
        results = []
        movement_started = False
        for label, px, pz in points:
            if stop.is_set():
                raise Stopped("Stopped; no further input")
            budget.check()
            current = adapter.read()
            start = current.position
            goal = Position(px, start.y, pz)
            distance = planar_distance(start, goal)
            span = 3.5
            if not face_waypoints:
                speeds = [math.hypot(finite(row.dx_per_ms), finite(row.dz_per_ms))
                          for row in adapter.calibrations(current).values()]
                if not speeds or min(speeds) <= 0:
                    raise WaypointError("Movement seed has no usable planar speed")
                # Backward travel can be slower than W. Size each intermediate
                # leg for about 600 ms at the slowest measured speed, leaving
                # room inside the unchanged six-pulse / 900-ms controller guard.
                span = min(4, 600 * min(speeds))
            count = max(1, math.ceil(distance / span))
            segments = []
            emit({"status": "leg", "name": label, "segmentCount": count})
            for index in range(1, count + 1):
                sx = start.x + (px - start.x) * index / count
                sz = start.z + (pz - start.z) * index / count

                def progress(event):
                    event = dict(event, segment=index, segmentCount=count)
                    if "position" in event:
                        point = Position(**event["position"])
                        event["distance"] = planar_distance(point, goal)
                    if event["status"] == "arrived":
                        event["status"] = "segment-arrived"
                    emit(event)

                segment = run_leg(adapter, sx, sz, stop, progress,
                                  focus=not movement_started, reservation=lease, budget=budget,
                                  face_waypoints=face_waypoints)
                segments.append(segment)
                movement_started = movement_started or segment["pulses"] > 0
            result = dict(segments[-1], name=label, start=asdict(start), goal=asdict(goal),
                          pulses=sum(row["pulses"] for row in segments),
                          totalHoldMs=sum(row["totalHoldMs"] for row in segments),
                          turnPulses=sum(row["turnPulses"] for row in segments),
                          movementPulses=sum(row["movementPulses"] for row in segments),
                          elapsedSeconds=round(sum(row["elapsedSeconds"] for row in segments), 3),
                          segments=segments, actions=[action for row in segments for action in row["actions"]])
            results.append(result)
            emit(result)
        return results


def run_map_move(adapter, payload, stop, emit=lambda event: None, *, mover=None):
    """Admit one owned-map destination without clicking the game or editing a route."""
    from scripts.waypoint_click_move import validate_map_origin
    if not isinstance(payload, dict) or not payload.get("owner"):
        raise WaypointError("Map owner unavailable; refresh before choosing a destination")
    if adapter.binding["runtimeIdentity"] != payload["owner"]:
        raise WaypointError("Map player/process changed; refresh before choosing a destination")
    view = payload["view"]
    pose = read_stationary(adapter, stop)
    validate_map_origin(view, pose.position, pose.bearing)
    if mover is None:
        from scripts.continuous_move import move_to
        mover = move_to
    return mover(adapter, payload["x"], payload["z"], stop, emit,
                 expected_origin={"x": view.x, "z": view.z, "bearing": view.bearing})


def validate_route_document(document):
    """Validate route/provenance without requiring measured heights for map points."""
    from scripts.waypoint_progress import _route
    from scripts.waypoint_measurements import document_measurements, parse_projection_route
    _route(document)
    from scripts.waypoint_route_library import normalize_context
    normalize_context(document.get("routeContext"))
    if "recording" in document:
        parse_projection_route(document)
    elif "pointMeasurements" in document:
        raw = document["pointMeasurements"]
        if not isinstance(raw, list) or len(raw) != len(document["waypoints"]):
            raise WaypointError("Point measurements must align with waypoints")
        parsed = document_measurements(document)
        if any(receipt is not None and valid is None for receipt, valid in zip(raw, parsed)):
            raise WaypointError("Invalid waypoint measurement provenance")
    return document


def read_route_context(adapter):
    """One pinned zone-candidate acquisition; no instance/name inference."""
    from scripts.save_physical_route_view import _zone_context
    from scripts.waypoint_route_library import normalize_context
    path = ROOT / "artifacts" / ("waypoint-zone-" + uuid.uuid4().hex + ".json")
    entry = _zone_context(adapter.selection, {"identity": adapter.binding["runtimeIdentity"]}, path)
    if entry.get("status") != "available-candidate" or entry.get("routePlayerMatches") is not True:
        raise WaypointError("Zone candidate unavailable: " + str(entry.get("reason", "player mismatch")))
    values = entry["values"]
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(values["sampledAtUtc"].replace("Z", "+00:00"))).total_seconds()
    if not -.1 <= age <= 3:
        raise WaypointError("Zone observation expired")
    return normalize_context(dict(version=1, zoneIdCandidate=values["zoneIdCandidate"],
        rawZoneKey=values["rawZoneKey"], source=str(path), observedAtUtc=values["sampledAtUtc"],
        target=deepcopy(adapter.target), playerKey=values["selfKey"]))


def launch_window(args):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from scripts.waypoint_diagnostics import Diagnostics
    from scripts.waypoint_brand import APP_NAME, APP_VERSION, APP_TITLE
    owns_diagnostics = getattr(args, "diagnostics", None) is None
    diagnostics = getattr(args, "diagnostics", None) or Diagnostics(ROOT)
    diagnostics.set_context(appName=APP_NAME, appVersion=APP_VERSION, host=args.expected_host,
                            guiPid=os.getpid(), phase="window")
    diagnostics.install_hooks()
    try:
        window = tk.Tk()
    except Exception as exc:
        diagnostics.exception("GUI initialization failed", exc=exc)
        if owns_diagnostics: diagnostics.close()
        raise
    def diagnostic_window_destroyed(event):
        if event.widget is window:
            diagnostics.info("Waypoint window closed")
            if owns_diagnostics: diagnostics.close()
    window.bind("<Destroy>", diagnostic_window_destroyed, add="+")
    if getattr(args, "background", False):
        window.withdraw()
    from scripts.waypoint_ui_theme import PALETTE, apply_theme, summarize_status
    from scripts.waypoint_marker_style import DEFAULT_STYLE, load_style, save_style
    apply_theme(window)
    from scripts.waypoint_connection import idle_read
    from scripts.waypoint_observation import observe_batch
    from scripts.waypoint_recording import RouteRecorder
    from scripts.waypoint_playback import play_route
    from scripts.waypoint_progress import _route as progress_route, write_json_atomic

    window.title(f"{APP_TITLE} — {args.expected_host} / "
                 + (f"PID {args.physical_pid}" if args.physical_pid is not None else "waiting for RIFT"))
    screen_height = window.winfo_screenheight()
    window.geometry(f"1120x{min(850, max(640, screen_height - 90))}")
    window.minsize(980, min(740, max(620, screen_height - 90)))
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    frame = ttk.Frame(window, padding=(22, 12))
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)
    header = ttk.Frame(frame)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    header.columnconfigure(0, weight=1)
    brand = ttk.Frame(header)
    brand.grid(row=0, column=0, sticky="w")
    try:
        mascot = tk.PhotoImage(file=str(ROOT / "assets/waypoints/red-panda.png"))
        mascot = mascot.subsample(max(1, math.ceil(max(mascot.width(), mascot.height()) / 68)))
        window._waypoint_mascot = mascot
        ttk.Label(brand, image=mascot).pack(side="left", padx=(0, 12))
        window.iconphoto(True, mascot)
    except (tk.TclError, OSError):
        pass  # Text branding remains usable without the optional artwork.
    brand_words = ttk.Frame(brand)
    brand_words.pack(side="left")
    brand_context = ttk.Frame(brand_words)
    brand_context.pack(anchor="w")
    ttk.Label(brand_context, text="RIFT / READER 2", style="Base.Micro.TLabel").pack(side="left")
    connection_text = tk.StringVar(value=f"{args.expected_host}  /  "
        + (f"PID {args.physical_pid}" if args.physical_pid is not None else "Waiting for RIFT"))
    connection_label=ttk.Label(brand_context, textvariable=connection_text, style="Base.Muted.TLabel")
    connection_label.pack(side="left", padx=(12, 0))
    title_row = ttk.Frame(brand_words)
    title_row.pack(anchor="w", pady=(3, 0))
    ttk.Label(title_row, text=APP_NAME, style="Brand.TLabel").pack(side="left")
    ttk.Label(title_row, text=f"v{APP_VERSION}", style="Base.Micro.TLabel").pack(side="left", padx=(10, 0), pady=(7, 0))
    header_actions = ttk.Frame(header)
    header_actions.grid(row=0, column=1, sticky="e", padx=(12, 16))
    stop_slot = ttk.Frame(header)
    stop_slot.grid(row=0, column=2, sticky="e")
    state = tk.StringVar(value=("Waiting for RIFT: " + args.initial_reason
                                if getattr(args, "initial_reason", None) else
                                "Ready — save a point, click the map, or enter X / Z."))
    status_brief = tk.StringVar(value=summarize_status(state.get()))
    state.trace_add("write", lambda *_: status_brief.set(summarize_status(state.get())))
    last_logged_state = [None]
    def log_state_change(*_):
        text = state.get()
        if text != last_logged_state[0]:
            last_logged_state[0] = text
            diagnostics.info("Activity", status=text)
    state.trace_add("write", log_state_change)
    status_strip = ttk.Frame(frame, style="Card.TFrame", padding=(14, 6))
    status_strip.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    status_label = ttk.Label(status_strip, textvariable=status_brief, style="Gold.TLabel", wraplength=900)
    ttk.Style(window).configure("Header.Ghost.TButton",padding=(8,0),font=("Segoe UI",9,"bold"))
    status_details = ttk.Button(status_strip, text="Details", style="Header.Ghost.TButton",
                                command=lambda: workflow.select(activity_tab))
    status_details.pack(side="right", padx=(10,0))
    draft_notice_text=tk.StringVar(value="")
    draft_notice=ttk.Button(status_strip,textvariable=draft_notice_text,style="Header.Ghost.TButton",
                            command=lambda: workflow.select(edit_tab))
    status_label.pack(side="left", fill="x", expand=True)
    def size_status(_=None):
        draft_width=draft_notice.winfo_reqwidth()+8 if draft_notice.winfo_manager() else 0
        status_label.configure(wraplength=max(200,status_strip.winfo_width()-status_details.winfo_reqwidth()-draft_width-42))
    status_strip.bind("<Configure>",size_status)
    pose_text = tk.StringVar(value="Position is loading…")
    telemetry = ttk.Frame(frame)
    telemetry.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    pose_row = ttk.Frame(telemetry)
    pose_row.pack(fill="x")
    pose_label = ttk.Label(pose_row, textvariable=pose_text, style="Telemetry.TLabel")
    pose_badge = tk.StringVar(value="Waiting for pose")
    pose_badge_label = ttk.Label(pose_row, textvariable=pose_badge, style="Base.Muted.TLabel")
    pose_badge_label.pack(side="right", padx=(12,0))
    pose_label.pack(side="left", fill="x", expand=True)
    pose_row.bind("<Configure>", lambda event: pose_label.configure(
        wraplength=max(200,event.width-pose_badge_label.winfo_reqwidth()-12)))
    route_status = tk.StringVar(value="New route — Unsaved")
    editable = []
    workflow = ttk.Notebook(frame, height=184)
    workflow.grid(row=4, column=0, sticky="ew", pady=(10, 6))
    replay_tab, edit_tab, scene_tab, explore_tab, library_tab, activity_tab = [ttk.Frame(workflow, style="Surface.TFrame", padding=(14, 8)) for _ in range(6)]
    for tab, title in ((replay_tab, "Replay"), (edit_tab, "Edit waypoint"),
                       (scene_tab, "Scene & beacons"), (explore_tab, "Explore"), (library_tab, "Library"), (activity_tab, "Activity")):
        workflow.add(tab, text=title)
    coordinates = ttk.Frame(edit_tab, style="Surface.TFrame")
    coordinates.pack(fill="x", pady=(0, 8))
    name, x, z = tk.StringVar(value="Point 1"), tk.StringVar(), tk.StringVar()
    form_item, form_baseline, form_loading = None, None, False
    edit_hint = tk.StringVar(value="Select a waypoint to edit, or enter X / Z to add one.")
    edit_buttons = {}
    last_edit_change = None
    walk_facing = tk.BooleanVar(value=args.face_waypoints)
    continuous_travel = tk.BooleanVar(value=getattr(args, "movement_engine", "pulse") == "continuous")
    survival_enabled = tk.BooleanVar(value=False)
    survival_summary = tk.StringVar(value="Survival: choose a verified ability profile")
    from scripts.waypoint_survival_runtime import WaypointSurvivalRuntime
    survival_runtime = WaypointSurvivalRuntime()
    target_beacon = tk.BooleanVar(value=False)
    landmark_guide = tk.BooleanVar(value=False)
    appearance_path = (ROOT / "artifacts" / "waypoint-marker-style.json").absolute()
    appearance = load_style(appearance_path)
    beacon_size = tk.DoubleVar(value=appearance["beaconScale"] * 100)
    beacon_opacity = tk.DoubleVar(value=appearance["opacity"] * 100)
    beacon_labels = tk.BooleanVar(value=appearance["labelsVisible"])
    size_percent = tk.StringVar(value=f"{round(beacon_size.get())}%")
    opacity_percent = tk.StringVar(value=f"{round(beacon_opacity.get())}%")
    appearance_after = None
    live_pose = tk.BooleanVar(value=True)
    view_bring_forward = tk.BooleanVar(value=False)
    view_include_units = tk.BooleanVar(value=False)
    point_entries = []
    for column, (label, variable, width) in enumerate((("Name", name, 26), ("World X", x, 18), ("World Z", z, 18))):
        coordinates.columnconfigure(column, weight=2 if column == 0 else 1)
        ttk.Label(coordinates, text=label, style="Surface.TLabel").grid(row=0, column=column, sticky="w", pady=(0, 3))
        entry = ttk.Entry(coordinates, textvariable=variable, width=width)
        entry.grid(row=1, column=column, sticky="ew", padx=(0, 10))
        editable.append(entry)
        point_entries.append(entry)
    live_pose_option = ttk.Checkbutton(header_actions, text="Live pose (1 s)", variable=live_pose)
    live_pose_option.pack(anchor="e", pady=(7, 0))
    summary = tk.StringVar(value="Refresh position to preview the route.")
    summary_label = ttk.Label(telemetry, textvariable=summary, style="Base.Muted.TLabel", wraplength=900)
    summary_label.pack(anchor="w", pady=(3, 0))
    context_text = tk.StringVar(value="Zone context loading; legacy routes remain untagged.")
    context_label = ttk.Label(telemetry, textvariable=context_text, style="Base.Muted.TLabel", wraplength=900)
    context_label.pack(anchor="w", pady=(2, 0))
    def size_telemetry(event):
        for label in (summary_label,context_label): label.configure(wraplength=max(200,event.width))
    telemetry.bind("<Configure>", size_telemetry)
    middle = ttk.Frame(frame)
    middle.grid(row=3, column=0, sticky="nsew")
    middle.columnconfigure(0, weight=3)
    middle.columnconfigure(1, weight=2)
    middle.rowconfigure(0, weight=1)
    middle.rowconfigure(0, minsize=200)
    route_card = ttk.Frame(middle, style="Card.TFrame", padding=(10,7))
    route_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    route_card.columnconfigure(0, weight=1)
    route_card.rowconfigure(3, weight=1)
    route_heading = ttk.Frame(route_card, style="Surface.TFrame")
    route_heading.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    ttk.Label(route_heading, text="YOUR ROUTE", style="Eyebrow.TLabel").pack(side="left", padx=(0, 12))
    route_status_label = ttk.Label(route_heading, textvariable=route_status, style="Gold.TLabel", wraplength=360)
    route_status_label.pack(side="left")
    route_heading.bind("<Configure>", lambda event: route_status_label.configure(wraplength=max(140, event.width - 100)))
    file_toolbar = ttk.Frame(route_card, style="Surface.TFrame")
    file_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 3))
    recent_controls = ttk.Frame(route_card, style="Surface.TFrame")
    recent_controls.grid(row=2, column=0, sticky="ew", pady=(0, 5))
    recent_controls.columnconfigure(1, weight=1)
    tree_frame = ttk.Frame(route_card, style="Surface.TFrame")
    tree_frame.grid(row=3, column=0, sticky="nsew")
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)
    ttk.Style(window).configure("Route.Treeview",rowheight=24)
    ttk.Style(window).configure("Route.Treeview.Heading",padding=(7,3))
    table = ttk.Treeview(tree_frame, columns=("name", "x", "z"), show="tree headings", height=4, style="Route.Treeview")
    table.heading("#0",text="#")
    table.column("#0",width=44,minwidth=44,stretch=False,anchor="center")
    for col, label, width in (("name", "Waypoint", 214), ("x", "X", 107), ("z", "Z", 107)):
        table.heading(col, text=label)
        table.column(col, width=width)
    table.grid(row=0, column=0, sticky="nsew")
    tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=table.yview)
    tree_scroll.grid(row=0, column=1, sticky="ns")
    table.configure(yscrollcommand=tree_scroll.set)
    map_frame = ttk.Frame(middle, style="Card.TFrame", padding=12)
    map_frame.grid(row=0, column=1, sticky="nsew")
    map_title = tk.StringVar(value="LOCAL PREVIEW")
    ttk.Label(map_frame, textvariable=map_title, style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 10))
    click_move = tk.BooleanVar(value=False)
    click_move_button = ttk.Checkbutton(map_frame, text="Click to move · clear path only",
        variable=click_move, command=lambda: update_preview_hint())
    click_move_button.pack(anchor="w", pady=(0, 4))
    editable.append(click_move_button)
    canvas = tk.Canvas(map_frame, width=330, height=220, bg="#0b1723", highlightthickness=0)
    map_hint = ttk.Frame(map_frame, style="Surface.TFrame")
    # Reserve the toolbar before the expandable canvas consumes compact height.
    map_hint.pack(side="bottom", fill="x", pady=(4, 0))
    canvas.pack(fill="both", expand=True)
    map_hint_text = tk.StringVar(value="No pose")
    ttk.Label(map_hint, textvariable=map_hint_text, style="Surface.Micro.TLabel").pack(side="left", padx=(0, 6))
    map_radius = 10
    radius_text = tk.StringVar(value="10 units")
    zoom_in = ttk.Button(map_hint, text="+", width=2, command=lambda: zoom(-1))
    zoom_in.pack(side="left")
    zoom_out = ttk.Button(map_hint, text="-", width=2, command=lambda: zoom(1))
    zoom_out.pack(side="left", padx=3)
    fit_button = ttk.Button(map_hint, text="Fit", width=3, command=lambda: fit_zoom())
    fit_button.pack(side="left")
    ttk.Label(map_hint, textvariable=radius_text, style="Surface.TLabel").pack(side="left", padx=6)
    events, stop = queue.Queue(), threading.Event()
    busy = False
    recording = False
    recording_restore = None
    recording_progress = None
    pending_recorded = None
    closing = False
    adapter = getattr(args, "initial_adapter", None)
    diagnostics.set_context(riftTarget=deepcopy(getattr(adapter, "target", None)))
    published_adapter = adapter
    foreground_stop = None
    last_pose = None
    last_y = None
    verified_adapter = None
    verified_at = None
    displayed_acquired = None
    displayed_stamp = None
    displayed_source = "existing-idle-reader"
    pose_unavailable_reason = None
    stop_context = {"hadOwnedAction": False, "activeRequestIdAtStop": None,
                    "result": None, "keyReleaseEvidence": "not-measured", "stationaryEvidence": "not-measured"}
    stop_waiting_operation = False
    identity_unavailable = False
    saved_view = None
    saved_unit_sample = None
    nearby_picker = None
    saved_rerun = None
    last_capture_state, last_capture_error = "none", None
    capture_hint = tk.StringVar(value="No capture yet · Save view or Open saved…")
    beacon_hint = tk.StringVar(value="Overlay reader stopped")
    next_scene_at = 0
    rerun_viewer = None
    markers = OwnedWaypointMarkers(ROOT)
    marker_identity = None
    marker_restart_pending = False
    marker_running_target = False
    marker_update_after = None
    marker_pending_signature = None
    marker_published = None
    beacon_pose_token = None
    beacon_pose_available = False
    beacon_pose_stamp = None
    beacon_display_active = False
    next_beacon_pose_at = 0
    explore_controls = None
    exploration_sample = None
    exploration_trail = []
    beacon_latest_error = None
    map_view = None
    map_render = {"nodes": [], "offscreen": [], "visible_count": 0, "offscreen_count": 0, "total_count": 0}
    map_hover = [None]
    observing = False
    next_live_at = time.monotonic() + 1
    operation_gate = threading.Lock()
    record_stop, record_cancel = threading.Event(), threading.Event()
    checkpoint = ROOT / "artifacts" / "waypoint-current-progress.json"
    progress_archive = ROOT / "artifacts" / "waypoint-progress"
    last_route = ROOT / "artifacts" / "waypoint-last-route.json"
    route_metadata = {}
    point_receipts = {}
    route_path = None
    route_dirty = False
    route_recovered = False
    playback_view = None
    playback_active = False
    pending_progress_selection = False
    loading_route = False
    added_selection = None
    edit_history = []
    recent_paths = []
    route_revision = 0
    cli_server = None
    cli_waiters = {}
    cli_action = None
    cli_recent = []
    cli_record_output = None
    cli_close_id = None
    cli_stop_at = 0
    cli_last_operation = None
    cli_last_record_file = None
    cli_destroyed = False
    cli_cancelled_requests = set()
    current_zone_context = None
    zone_error = None
    zone_observing = False
    next_zone_at = time.monotonic() + 1
    marker_anchor_y = None
    from scripts.waypoint_recent_display import route_labels, attach_path_tooltip
    from scripts.waypoint_activity_ui import ActivityControls
    activity_controls = ActivityControls(activity_tab, diagnostics,
        open_logs=lambda: open_logs(), copy_diagnostics=lambda: copy_diagnostics(),
        attach_path_tooltip=attach_path_tooltip)

    def update_route_status():
        friendly = route_metadata.get("routeName")
        title = friendly if isinstance(friendly,str) and friendly.strip() else route_path.name if route_path is not None else "Recovered route" if route_recovered else "New route"
        status = "Unsaved changes" if route_dirty else "Saved" if route_path is not None else "Unsaved"
        route_status.set(f"{title} — {status}")

    def mark_saved(path):
        nonlocal route_path, route_dirty, route_recovered
        route_path, route_dirty, route_recovered = Path(path).absolute(), False, False
        update_route_status()
        remember_recent(route_path)

    def local_source_path(value):
        # Inspect drive type before opening any remembered path; never probe a
        # UNC path or a mapped network drive during automatic recovery.
        import ctypes
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        if not path.is_absolute() or not path.drive or path.drive.startswith("\\\\"):
            return None
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) not in (2, 3):
            return None
        return path

    def remember_recent(path):
        try:
            progress_route(route_document())
        except (ValueError, KeyError, TypeError):
            return
        source = local_source_path(str(path))
        if source is None:
            return
        value = str(source)
        recent_paths[:] = [value] + [old for old in recent_paths if old.casefold() != value.casefold()]
        del recent_paths[8:]
        recent_dropdown.configure(values=route_labels(recent_paths))
        recent_dropdown.current(0)
        recent_load_button.configure(state="normal" if not busy and not closing else "disabled")

    def invalidate_progress(*, clear_metadata=True):
        nonlocal route_metadata, playback_view, route_dirty, route_revision
        if not loading_route:
            route_revision += 1
            if table.get_children():
                from scripts.waypoint_progress import invalidate_route_progress
                # Editing the local route invalidates only the cursor belonging to
                # its known player, even when the last pose is too old for Resume.
                invalidate_route_progress(checkpoint, progress_archive, route_document(),
                                          current_identity() or last_verified_owner)
            if clear_metadata:
                route_metadata = {key:value for key,value in route_metadata.items()
                                  if key in ("routeContext", "routeName")}
            playback_view = None
            route_dirty = True
            update_route_status()
            progress_text.set("No saved progress; choose Play Forward or Play Reverse.")

    def add_point(label, px, pz):
        nonlocal added_selection
        if len(table.get_children()) >= MAX_WAYPOINTS:
            state.set("Waypoint list is full; remove a point before adding another.")
            return
        px, pz = finite(px), finite(pz)
        remember_edit()
        invalidate_progress()
        item = table.insert("", "end", values=(label, f"{finite(px):.6f}", f"{finite(pz):.6f}"))
        added_selection = item
        table.selection_set(item)
        fill_fields(item)
        redraw()
        return item

    def selected_points(all_points=False):
        return [table.item(item, "values") for item in (table.get_children() if all_points else table.selection())]

    def route_document():
        document = {**route_metadata, "waypoints": [list(row) for row in route_points(selected_points(True))]}
        if "recording" not in route_metadata:
            receipts = [deepcopy(point_receipts.get(item)) for item in table.get_children()]
            if any(receipt is not None for receipt in receipts):
                document["pointMeasurements"] = receipts
                document["heights"] = [receipt["position"]["y"] if receipt is not None else None for receipt in receipts]
        return document

    def remember_edit():
        if loading_route:
            return
        rows = selected_points(True)
        edit_history.append((deepcopy(route_document() if rows else {"waypoints": []}),
                             [table.index(item) for item in table.selection()]))
        del edit_history[:-20]

    def undo_edit(_=None):
        nonlocal route_metadata, added_selection
        if busy or closing or not edit_history or draft_pending():
            return "break"
        document, indices = edit_history[-1]
        invalidate_progress(clear_metadata=False)
        edit_history.pop()
        if document["waypoints"]:
            show_document(document)
        else:
            table.delete(*table.get_children())
            point_receipts.clear()
            route_metadata = {k: v for k, v in document.items() if k != "waypoints"}
            name.set("Point 1")
        added_selection = None
        items = table.get_children()
        table.selection_set([items[index] for index in indices if index < len(items)])
        selection = table.selection()
        fill_fields(selection[0] if len(selection) == 1 else None)
        redraw()
        state.set("Route edit undone; save the route to keep these changes.")
        return "break"

    def cache_route(document, success):
        try:
            source = local_source_path(str(route_path)) if route_path is not None else None
            write_json_atomic(last_route, {"version": 1, "route": document,
                                           "sourcePath": str(source) if source else None,
                                           "recentPaths": list(recent_paths)})
            text = success
        except (OSError, ValueError, TypeError) as exc:
            diagnostics.exception("Unable to cache route", exc=exc)
            text = success + "; last-route snapshot could not be saved: " + str(exc)
        state.set(text)

    def show_document(document):
        nonlocal loading_route, route_metadata, route_revision
        from scripts.waypoint_measurements import document_measurements
        parsed = route_points(document["waypoints"])
        receipts = document_measurements(document)
        loading_route = True
        try:
            table.delete(*table.get_children())
            point_receipts.clear()
            for row, receipt in zip(parsed, receipts):
                item = add_point(*row)
                if receipt is not None:
                    point_receipts[item] = deepcopy(receipt)
            route_metadata = {k: v for k, v in document.items() if k != "waypoints"}
            fill_fields(table.selection()[0] if len(table.selection()) == 1 else None)
        finally:
            loading_route = False
        route_revision += 1
        redraw()

    def current_identity():
        if identity_unavailable:
            return None
        pose = getattr(adapter, "initial_pose", None)
        acquired = verified_at if adapter is verified_adapter else getattr(pose, "acquired", None)
        if type(acquired) not in (int, float) or not -.1 <= time.monotonic() - acquired <= 2:
            return None
        binding = getattr(adapter, "binding", None)
        identity = binding.get("runtimeIdentity") if isinstance(binding, dict) else None
        return deepcopy(identity) if isinstance(identity, dict) and all(
            isinstance(identity.get(key), str) and identity[key]
            for key in ("machine", "gameBuildSha256", "unitKey")) else None

    last_verified_owner = current_identity()

    def display_progress(progress):
        nonlocal playback_view
        count, index = len(progress.ordered_points), progress.next_index
        playback_view = {"direction": progress.direction, "nextIndex": index}
        hint = "choose Play Forward or Play Reverse." if index == count else "choose Resume."
        progress_text.set(f"{progress.direction.title()} progress: {index} / {count}; {hint}")
        redraw()

    def restore_progress():
        from scripts.waypoint_progress import RouteProgress
        identity = current_identity()
        if identity is None:
            raise ValueError("Waiting for a verified player identity")
        display_progress(RouteProgress.load(checkpoint, route_document(), identity))

    def select_progress(document):
        from scripts.waypoint_progress import select_route_progress
        return select_route_progress(checkpoint, progress_archive, document, current_identity())

    def select_pending_progress():
        nonlocal pending_progress_selection, playback_view
        if not pending_progress_selection or busy or current_identity() is None or not table.get_children():
            return
        try:
            progress = select_progress(route_document())
            pending_progress_selection = False
            playback_view = None
            if progress is not None:
                display_progress(progress)
            else:
                progress_text.set("No saved progress; choose Play Forward or Play Reverse.")
                redraw()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to restore saved progress", exc=exc)
            state.set("Cannot restore saved progress: " + str(exc))

    def prepared_document(document):
        validate_route_document(document)
        prepared = deepcopy(document)
        prepared["waypoints"] = [[label, float(f"{x:.6f}"), float(f"{z:.6f}")]
                                 for label, x, z in route_points(document["waypoints"])]
        progress_route(prepared)
        from scripts.waypoint_measurements import document_measurements
        document_measurements(prepared)
        return prepared

    def zoom(direction):
        nonlocal map_radius
        index = ZOOM_RADII.index(map_radius)
        map_radius = ZOOM_RADII[max(0, min(len(ZOOM_RADII) - 1, index + direction))]
        redraw()

    def fit_zoom():
        nonlocal map_radius
        if last_pose is None or not table.get_children():
            state.set("A cached position and at least one waypoint are needed to fit the preview.")
            return False
        map_radius = fit_route_radius(*last_pose[:2], selected_points(True))
        redraw()
        return True

    def redraw(*_):
        nonlocal map_view, map_render
        if cli_server is not None:
            update_context_text()
            update_replay_status()
            update_edit_state()
            update_library_readiness()
        if explore_controls is not None:
            explore_controls.route_changed()
            explore_controls.refresh_context()
        schedule_marker_update()
        radius_text.set(f"{map_radius:g} units")
        zoom_in.configure(state="disabled" if map_radius == ZOOM_RADII[0] else "normal")
        zoom_out.configure(state="disabled" if map_radius == ZOOM_RADII[-1] else "normal")
        fit_button.configure(state="normal" if last_pose is not None and table.get_children() else "disabled")
        undo_button.configure(state="normal" if edit_history and not busy and not closing and not draft_pending() else "disabled")
        points = [(item, *table.item(item, "values")) for item in table.get_children()]
        original_points = points[:]
        for number,row in enumerate(original_points,1):
            table.item(row[0],text=str(number))
        completed, active = None, None
        if playback_view is not None:
            if playback_view["direction"] == "reverse":
                points.reverse()
            index = max(0, min(len(points), playback_view["nextIndex"]))
            completed = {row[0] for row in points[:index]}
            active = points[index][0] if index < len(points) else None
        elif explore_controls is not None:
            guidance = explore_controls.navigation_state()
            if guidance["status"] in ("active", "complete"):
                completed = {row[0] for i, row in enumerate(points) if i in guidance["completedIndices"]}
                active = next((row[0] for i, row in enumerate(points) if i == guidance["activeIndex"]), None)
        for row in points:
            table.item(row[0], tags=("next",) if row[0] == active else
                       ("completed",) if completed is not None and row[0] in completed else ())
        if last_pose is None:
            map_view = None
            map_render = draw_route(canvas, None, [], set())
            map_title.set("LOCAL PREVIEW · no position")
            map_hint_text.set("No pose · Refresh")
            summary.set("Position unavailable; refresh to preview the route.")
            if not busy:
                for button in (go_button, route_button, face_button, record_button,
                               forward_button, reverse_button, resume_button, teach_button):
                    button.configure(state="disabled")
            return
        map_view = LocalMap(*last_pose, max(100, canvas.winfo_width()), max(100, canvas.winfo_height()), map_radius)
        map_render = draw_route(canvas, map_view, points, set(table.selection()), completed=completed, active=active,
                   trail=exploration_trail,numbers=[table.index(row[0])+1 for row in points])
        visible=map_render["visible_count"]
        hidden=map_render["offscreen_count"]
        map_title.set((f"LOCAL PREVIEW · {visible}/{len(points)} visible"+(f" · {hidden} off-screen" if hidden else ""))
                      if points else "LOCAL PREVIEW · no waypoints")
        update_preview_hint()
        remaining = points[index:] if playback_view is not None else points
        distance = route_length(*last_pose[:2], [row[1:] for row in remaining])
        planned_distance = route_length(*last_pose[:2], selected_points(True))
        selected = selected_points()
        chosen = route_length(*last_pose[:2], selected) if selected else None
        if recording_progress is not None:
            summary.set(f"Recording: {recording_progress['observedPathLength']:.2f} / {MAX_ROUTE_DISTANCE:g} units"
                        f"   •   {recording_progress['sampleCount']} samples"
                        + ("   •   Stop Recording saves" if recording else "   •   STOP cancels"))
        else:
            endpoints = ""
            if not busy and not recording and original_points:
                distances = [math.hypot(finite(row[2]) - last_pose[0], finite(row[3]) - last_pose[1])
                             for row in (original_points[0], original_points[-1])]
                endpoints = f"   •   Start: {distances[0]:.2f} • End: {distances[1]:.2f} units"
            summary.set(f"{'Remaining' if playback_view is not None else 'Route'}: {distance:.2f} / {MAX_ROUTE_DISTANCE:g} units"
                        + (f"   •   Selected: {chosen:.2f} units" if chosen is not None else "")
                        + endpoints
                        + (f"   •   Beacons: {sum(1 for row in original_points if point_receipts.get(row[0]) is not None)} measured"
                           f" · {sum(1 for row in original_points if point_receipts.get(row[0]) is None)} estimated"
                           if original_points else "")
                        + ("   •   Shorten the route to run it" if distance > MAX_ROUTE_DISTANCE else ""))
        if not busy:
            update_direct_state()
            if cli_server is not None:
                update_replay_status()

    def map_click(event):
        if busy or closing or cli_action is not None:
            state.set("Wait for the active action before changing preview selection or adding points.")
            return
        if draft_pending():
            state.set("Apply or Reset fields before selecting or adding a waypoint.")
            return
        if click_move.get():
            try:
                payload = map_destination(event.x, event.y)
            except (ValueError, TypeError) as exc:
                state.set(str(exc))
                return
            start("map-go", payload, check_route_zone=False)
            return
        from scripts.waypoint_map import hit_test_route
        hit=hit_test_route(map_render,event.x,event.y)
        if hit is not None:
            item=hit["identifier"]
            table.selection_set(item)
            table.focus(item)
            select_point(None)
            return
        if map_view is None:
            state.set("Refresh position before adding a point from the preview.")
            return
        if not (12<=event.x<=map_view.width-12 and 12<=event.y<=map_view.height-12):
            state.set("Click inside the preview to add a waypoint.")
            return
        if len(table.get_children())>=MAX_WAYPOINTS:
            state.set("Waypoint list is full; remove a point before adding another.")
            return
        px, pz = map_view.canvas_to_world(event.x, event.y)
        label=(name.get() or f"Point {len(table.get_children())+1}") if form_item is None else f"Point {len(table.get_children())+1}"
        start("map", (map_view, px, pz, label))

    diagnostic_failures = {}

    def project_destination(canvas_x, canvas_y):
        from scripts.waypoint_click_move import project_map_click
        if map_view is None:
            raise WaypointError("Refresh position before choosing a map destination")
        projected = project_map_click(map_view, canvas_x, canvas_y)
        from scripts.waypoint_map import hit_test_route
        hit = hit_test_route(map_render, canvas_x, canvas_y)
        if hit is not None:
            # Displaced number badges are UI annotations: choose their actual
            # waypoint, not the different ground underneath the badge pixels.
            values = table.item(hit["identifier"], "values")
            projected.update(x=finite(values[1]), z=finite(values[2]),
                             waypointNumber=hit["number"], selectedFrom=hit["part"])
        return projected

    def map_destination(canvas_x, canvas_y):
        owner = current_identity()
        if owner is None:
            raise WaypointError("Refresh position before choosing a map destination")
        projected = project_destination(canvas_x, canvas_y)
        return dict(projected, view=map_view, owner=owner)

    def worker(operation, points=None, face_walk=False, route_context=None, request_id=None, engine="pulse"):
        with operation_gate:
            if operation == "live" and closing:
                events.put({"status": "live-idle"})
                return
            perform_operation(operation, points, face_walk, route_context, request_id, engine)

    def perform_operation(operation, points=None, face_walk=False, route_context=None, request_id=None, engine="pulse"):
        nonlocal adapter, published_adapter
        retain = operation in ("go", "face", "face-bearing", "play", "resume", "teach", "map-go", "release")
        history, outcome, failure = [], None, None
        stop_verification = None
        receipt_path = None
        observed_context = None
        if operation not in ("live", "zone-live"):
            diagnostics.info("Operation started", operation=operation, requestId=request_id)

        def emit(event):
            if retain:
                history.append(dict(event))
            events.put(event)

        try:
            runner = run_route
            if engine == "survival" and operation in ("go", "play", "resume"):
                runner = survival_runtime.route_runner
            elif engine == "continuous" and operation in ("go", "play", "resume"):
                from scripts.continuous_move import run_continuous_route
                runner = run_continuous_route
            if adapter is None:
                if operation not in ("refresh", "save", "map", "live", "target"):
                    raise WaypointError("RIFT is not connected; wait for a fresh pose")
                adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
            if retain:
                adapter.input_receipt_path = ROOT / "artifacts" / ("waypoint-input-" + uuid.uuid4().hex + ".jsonl")
                adapter.last_input_receipt = None
            if route_context is not None or operation in ("zone", "zone-live", "record"):
                try:
                    observed_context = read_route_context(adapter)
                    events.put({"status": "zone", "context": observed_context})
                except Exception as exc:
                    events.put({"status": "zone-unavailable", "reason": str(exc)})
                    if route_context is not None or operation in ("zone", "zone-live"):
                        raise
                if route_context is not None:
                    from scripts.waypoint_route_library import compare_context
                    if compare_context(route_context, observed_context) != "matching":
                        raise WaypointError("Route zone candidate does not match the current zone; no movement sent")
            if operation == "survival-preflight":
                outcome = survival_runtime.preflight(adapter, stop)
                emit({"status": "survival-state", "survival": outcome})
            elif operation in ("zone", "zone-live"):
                outcome = observed_context
            elif operation in ("refresh", "save", "map", "live", "target"):
                adapter, pose, reconnected = idle_read(
                    adapter, args.expected_host, args.basis, physical_rift.select_physical,
                    PhysicalAdapter, include_target=operation == "target",
                    auto_reconnect=getattr(args, "auto_reconnect", False))
                if reconnected or adapter is not published_adapter:
                    events.put({"status": "reconnected", "pid": adapter.pid})
                    published_adapter = adapter
                if operation == "target":
                    pose, waypoint, name_candidate = _read_target_waypoint(adapter, pose)
                result = {"status": operation, "position": asdict(pose.position), "bearing": pose.bearing,
                          "acquired": pose.acquired}
                if operation in ("save","target") and isinstance(points,str): result["newLabel"]=points
                if operation == "save" and isinstance(getattr(adapter, "binding", None), dict):
                    try:
                        from scripts.waypoint_measurements import measurement
                        result["measurement"] = measurement(pose.position, adapter.binding, pose.source,
                                                            datetime.now(timezone.utc).isoformat())
                    except (ValueError, KeyError, TypeError, AttributeError):
                        result["measurementReason"] = "Position provenance unavailable; point saved without height."
                if operation == "save" and isinstance(points, dict):
                    if result.get("measurement") is None:
                        raise WaypointError("Cannot replace waypoint without a fresh measured position.")
                    result["replacement"] = deepcopy(points)
                    result["captureTarget"] = deepcopy(getattr(adapter, "target", None))
                if operation == "target":
                    result["waypoint"] = waypoint
                    try:
                        from scripts.waypoint_measurements import measurement
                        result["measurement"] = measurement(
                            pose.selected_target["positionXYZCandidate"], adapter.binding, pose.source,
                            pose.selected_target["sampledAtUtc"], kind="native-selected-target-position",
                            target_key=pose.selected_target["targetKey"])
                        if name_candidate is not None:
                            result["measurement"]["nameCandidate"] = name_candidate
                            result["waypoint"] = (name_candidate["text"], waypoint[1], waypoint[2])
                    except (ValueError, KeyError, TypeError, AttributeError):
                        result["measurementReason"] = "Target position saved without verified height provenance."
                if operation == "map":
                    view, px, pz, label = points
                    moved = math.hypot(view.x - pose.position.x, view.z - pose.position.z) > .05
                    turned = abs((view.bearing - pose.bearing + 180) % 360 - 180) > .5
                    if moved or turned:
                        result.update(status="notice", reason="Player moved; map refreshed. Click again to choose a waypoint.")
                    else:
                        result["waypoint"] = (label, px, pz)
                if operation=="target" and result.get("newLabel") and result.get("waypoint"):
                    result["waypoint"]=(result["newLabel"],*result["waypoint"][1:])
                events.put(result)
            elif operation == "release":
                from scripts.continuous_move import retry_release
                outcome = retry_release(adapter)
                stop_verification = verify_stopped_pose(adapter, after="release retry")
                emit({"status": "notice", "reason": "Owned key release verified. STOP remains latched; choose an explicit new run or Resume."})
            elif operation == "map-go":
                outcome = run_map_move(adapter, points, stop, emit)
                events.put(dict(outcome, status="route-complete", waypointCount=1))
            elif operation == "face":
                outcome = run_facing(adapter, stop, emit, point=points[0][1:])
            elif operation == "face-bearing":
                outcome = run_facing(adapter, stop, emit, bearing=points)
            elif operation == "view":
                from scripts.save_physical_route_view import save_route_view
                document, pid, target, capture_backend, include_units, *destination = points
                if adapter.pid != pid or adapter.target != target:
                    raise WaypointError("RIFT connection changed; refresh before saving a view")
                output = ROOT / "artifacts" / ("waypoint-view-" + uuid.uuid4().hex)
                result = save_route_view(args.expected_host, pid, document, output,
                                         expected_target=target, export_rerun=True, capture_backend=capture_backend,
                                         **({"include_units": True} if include_units else {}))
                if (result.get("status") != "saved-route-view-candidate" or not result.get("image")
                        or result.get("inputSent") is not False or type(result.get("focusChanged")) is not bool
                        or (capture_backend == "wgc" and result.get("focusChanged") is not False)):
                    raise WaypointError(str(result.get("reason", "View capture unavailable"))
                                        + "; details: " + str(result.get("directory", output)))
                if destination:
                    write_json_atomic(destination[0], result)
                events.put({"status": "view-saved", "image": str(result["image"]),
                            "rerun": result.get("rerun", {}), "unitSample": result.get("unitSample")})
            elif operation == "record":
                recorder = RouteRecorder(adapter.binding)
                next_record_zone = time.monotonic()+3
                while not record_stop.is_set() and not record_cancel.is_set():
                    # The batch revalidates process/build/player/owners itself.
                    # A read-only recorder must not contend for move-key's input
                    # semaphore merely to inspect the window between captures.
                    # The native lease spans the entire paced burst. Leave a
                    # real handoff window for other guarded one-pose readers.
                    for pose in observe_batch(adapter, samples=6):
                        recorder.observe(pose)
                    if observed_context is not None and time.monotonic() >= next_record_zone:
                        from scripts.waypoint_route_library import compare_context
                        if compare_context(observed_context, read_route_context(adapter)) != "matching":
                            raise WaypointError("Zone candidate changed while recording; no mixed-zone route saved")
                        next_record_zone = time.monotonic()+3
                    events.put({"status": "recording", "preview": recorder.preview(), "position": asdict(pose.position),
                                "bearing": pose.bearing, **recorder.progress})
                    record_stop.wait(.15)
                if record_cancel.is_set():
                    raise WaypointError("Recording cancelled; no route saved")
                document = recorder.finish()
                if observed_context is not None:
                    document["routeContext"] = observed_context
                events.put({"status": "recorded-pending", "document": document})
            elif operation == "teach":
                from scripts.waypoint_playback import teach_route
                results, document = teach_route(adapter, points, stop, emit, runner=run_route,
                                                face_waypoints=face_walk)
                outcome = results
                events.put({"status": "recorded-pending", "document": document, "operation": "teach"})
            elif operation in ("play", "resume"):
                document, direction = points
                results, cursor = play_route(adapter, document, stop, emit, runner=runner,
                                             checkpoint=checkpoint, direction=direction,
                                             resume=operation == "resume", face_waypoints=face_walk, approach_start=True)
                outcome = results
                events.put({"status": "route-complete", "waypointCount": len(results),
                            "nextWaypoint": cursor.next_index, "totalWaypoints": len(cursor.ordered_points),
                            "position": results[-1]["position"], "bearing": results[-1]["bearing"],
                            "distance": results[-1]["distance"]})
            else:
                results = runner(adapter, points, stop, emit, face_waypoints=face_walk)
                outcome = results
                events.put({"status": "route-complete", "waypointCount": len(results),
                            "position": results[-1]["position"], "bearing": results[-1]["bearing"],
                            "distance": results[-1]["distance"]})
        except Exception as exc:
            signature = (type(exc).__name__, str(exc))
            if isinstance(exc, Stopped):
                diagnostics.warning("Operation stopped", operation=operation, requestId=request_id, reason=str(exc))
            elif operation not in ("live", "zone-live") or diagnostic_failures.get(operation) != signature:
                diagnostics.exception("Operation failed", exc=exc, operation=operation, requestId=request_id)
            diagnostic_failures[operation] = signature
            original_reason = str(exc)
            stopped_position = stopped_bearing = stopped_acquired = None
            if retain and adapter is not None:
                is_stop = isinstance(exc, Stopped)
                stop_verification = verify_stopped_pose(adapter, after="STOP" if is_stop else "halt")
                if is_stop and stop_verification["status"] == "pass":
                    stopped_position = stop_verification["samples"][-1]["position"]
                    stopped_bearing = stop_verification["samples"][-1]["bearing"]
                    stopped_acquired = stop_verification["samples"][-1].get("acquired")
                elif is_stop and stop_verification["status"] == "unavailable":
                    exc = WaypointError("STOP requested; stationary check unavailable: " + stop_verification["reason"])
                elif is_stop and stop_verification["status"] != "pass":
                    exc = WaypointError(stop_verification["reason"])
            failure = {"status": "zone-unavailable" if operation == "zone-live" else "live-unavailable" if operation == "live" else "view-failed" if operation == "view" else
                       "stopped" if isinstance(exc, Stopped) else "halted", "reason": str(exc),
                       "originalReason": original_reason,
                       "inputReleaseFault": bool(getattr(adapter, "_continuous_input_release_fault", False)),
                       "inputRecovery": deepcopy(getattr(adapter, "_continuous_move_recovery", None)),
                       **({"position": stopped_position, "bearing": stopped_bearing,"acquired":stopped_acquired} if stopped_position else {}),
                       "inputReceiptPath": str(getattr(adapter, "input_receipt_path", None)) if getattr(adapter, "input_receipt_path", None) else None}
            emit(failure)
        else:
            diagnostic_failures.pop(operation, None)
        finally:
            if retain:
                receipt = {"operation": operation,
                           "direction": points[1] if operation in ("play", "resume") and points else None,
                           "status": failure["status"] if failure else "completed",
                           "failure": failure, "result": outcome, "events": history,
                           "movementEngine": "continuous" if operation == "map-go" else "pulse" if operation == "teach" else engine,
                           "inputReleaseFault": bool(getattr(adapter, "_continuous_input_release_fault", False)),
                           "inputRecovery": deepcopy(getattr(adapter, "_continuous_move_recovery", None)),
                           "completedLegs": [event for event in history if event.get("status") == "arrived"],
                           "calibrationBinding": getattr(adapter, "binding", None),
                           "inputReceiptPath": str(getattr(adapter, "input_receipt_path", None)) if getattr(adapter, "input_receipt_path", None) else None,
                           "inputReceiptPresent": bool(getattr(adapter, "input_receipt_path", None) and adapter.input_receipt_path.exists()),
                           "stopVerification": stop_verification,
                           "releaseVerification": ("see individual native input receipts for key release; measured stationary evidence is separate in stopVerification"
                                                   if failure else "see completed result and pulse receipts")}
                receipt_path = ROOT / "artifacts" / ("waypoint-run-" + uuid.uuid4().hex + ".json")
                try:
                    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                    events.put({"status": "run-receipt", "path": str(receipt_path), "failure": failure})
                except (OSError, TypeError, ValueError) as exc:
                    diagnostics.exception("Unable to save operation receipt", exc=exc, operation=operation,
                                          requestId=request_id, receipt=str(receipt_path))
                    events.put({"status": "receipt-error", "reason": str(exc), "failure": failure})
            if operation not in ("live", "zone-live"):
                diagnostics.info("Operation finished", operation=operation, requestId=request_id,
                                 failed=failure is not None, receipt=str(receipt_path) if receipt_path else None)
            events.put({"status": "zone-idle" if operation == "zone-live" else "live-idle" if operation == "live" else "idle"})
            if operation not in ("live", "zone-live"):
                events.put({"status": "operation-finished", "operation": operation,
                            "failure": failure, "result": outcome,
                            "inputReleaseFault": bool(getattr(adapter, "_continuous_input_release_fault", False)),
                            "inputRecovery": deepcopy(getattr(adapter, "_continuous_move_recovery", None)),
                            "stopVerification":stop_verification,
                            "inputReceiptPath":str(adapter.input_receipt_path) if retain and getattr(adapter,"input_receipt_path",None) and adapter.input_receipt_path.exists() else None,
                            "receipt": str(receipt_path) if receipt_path else None})

    def start(operation, points=None, *, face_walk=None, check_route_zone=True):
        nonlocal recording_restore
        nonlocal busy, foreground_stop, recording, recording_progress, playback_view, playback_active
        nonlocal stop_waiting_operation
        if busy or closing or nearby_picker is not None:
            return
        if (operation in ("go", "face", "face-bearing", "play", "resume", "teach", "map-go")
                and getattr(adapter, "_continuous_input_release_fault", False)):
            state.set("Movement blocked: the last owned key release is unverified. Restore RIFT focus and retry STOP cleanup.")
            return
        if marker_restart_pending:
            state.set("Wait while the overlay reader restarts.")
            return
        if draft_pending() and operation in ("go", "face", "face-bearing", "play", "resume", "teach", "record", "map", "target", "save", "map-go"):
            state.set("Apply or Reset fields before starting another action.")
            return
        if operation in ("go", "teach") and (not points or len(points) > MAX_WAYPOINTS):
            messagebox.showinfo("Choose waypoints", f"Select a waypoint, or add up to {MAX_WAYPOINTS} points for a route.")
            return
        if operation == "face" and (not points or len(points) != 1):
            state.set("Select one waypoint to face.")
            return
        if operation in ("go", "face", "face-bearing", "teach", "record", "map-go", "play", "resume", "survival-preflight") and markers.running():
            if stop_markers():
                state.set("Markers are closing; try the action again when they are hidden.")
            return
        busy = True
        if operation in ("go", "face", "face-bearing", "play", "resume", "teach", "map-go", "record"):
            stop.clear()
        if operation != "release":
            stop_waiting_operation=False
        stop_context.update(hadOwnedAction=False,activeRequestIdAtStop=None,result=None,
                            keyReleaseEvidence="not-measured",stationaryEvidence="not-measured")
        if operation == "teach":
            record_cancel.clear()
            record_stop.clear()
        if operation in ("go", "face", "face-bearing", "play", "resume", "teach", "map-go"):
            try:
                foreground_stop = ForegroundStop(window, stop, events)
            except Exception as exc:
                diagnostics.exception("Unable to start foreground safety monitor", exc=exc, operation=operation)
                busy = False
                state.set("Cannot start safely: " + str(exc))
                return
        if operation in ("play", "resume"):
            playback_active = True
            playback_view = {"direction": points[1], "nextIndex": 0}
            if operation == "resume":
                try:
                    playback_view["nextIndex"] = int(json.loads(checkpoint.read_text(encoding="utf-8"))["nextIndex"])
                except (OSError, ValueError, KeyError, TypeError):
                    pass  # Backend validates the checkpoint before any input.
            redraw()
        for widget in editable:
            widget.configure(state="disabled")
        if operation == "teach":
            recording_progress = {"sampleCount": 0, "observedPathLength": 0.0}
            redraw()
        if operation == "record":
            recording_restore = ([(item, table.item(item, "values")) for item in table.get_children()],
                                 tuple(table.selection()), deepcopy(route_metadata))
            recording = True
            recording_progress = {"sampleCount": 0, "observedPathLength": 0.0}
            record_stop.clear()
            record_cancel.clear()
            record_end_button.configure(state="normal")
            redraw()
        state.set(("Starting action — F8 or STOP releases owned movement." if getattr(foreground_stop,"registered",False)
                   else "Starting action — use STOP; F8 is unavailable.") if operation in ("go", "face", "face-bearing", "play", "resume", "teach", "map-go")
                  else "Recording your movement; click Stop Recording to save this route." if operation == "record"
                  else "Saving view…" if operation == "view"
                  else "Reading current RIFT pose…")
        context = deepcopy(route_metadata.get("routeContext")) if check_route_zone and (operation in ("go", "face", "play", "resume", "teach") or operation == "save" and isinstance(points, dict)) else None
        mode = True if operation in ("play", "resume") else walk_facing.get() if face_walk is None else face_walk
        request_id = cli_action["id"] if cli_action is not None else None
        engine = "continuous" if continuous_travel.get() else "pulse"
        if survival_enabled.get() and operation in ("go", "play", "resume"):
            engine = "survival"
        threading.Thread(target=worker, args=(operation, points, mode, context, request_id, engine), daemon=False).start()
        return True

    def request_stop():
        nonlocal cli_stop_at, cli_record_output, stop_waiting_operation
        cli_stop_at = time.time()
        click_move.set(False)
        # Evidence belongs to this STOP, never an unrelated previous receipt.
        if not stop.is_set() or not stop_waiting_operation:
            stop_context.update(hadOwnedAction=bool(busy),
                activeRequestIdAtStop=cli_action["id"] if cli_action else None,
                result=None,keyReleaseEvidence="not-measured",stationaryEvidence="not-measured")
            stop_waiting_operation = bool(busy)
        stop.set()
        if cli_action is not None:
            cli_action["cancelled"] = True
        if recording:
            cli_record_output = None
            record_cancel.set()
            record_stop.set()
            state.set("Recording cancelled — no route will be saved.")
            return
        markers_stopped = stop_markers()
        if not busy and getattr(adapter, "_continuous_input_release_fault", False):
            stop_waiting_operation = True
            if start("release", check_route_zone=False):
                state.set("STOP latched — retrying exact-target key release without changing focus.")
            return
        text = ("STOP requested — waiting for owned movement to release." if busy
                else "STOP latched — no owned action active; game motion unverified.")
        state.set(text if markers_stopped else text + " Could not hide markers.")

    def draft_pending():
        return (not form_loading and form_item is not None and table.exists(form_item)
                and form_baseline is not None and (name.get(), x.get(), z.get()) != form_baseline)

    def fill_fields(item=None):
        nonlocal form_item, form_baseline, form_loading, added_selection
        form_loading = True
        try:
            form_item = item if item is not None and table.exists(item) else None
            if form_item is not None:
                label, px, pz = table.item(form_item, "values")
                name.set(label); x.set(px); z.set(pz)
                added_selection = None
                form_baseline = (name.get(), x.get(), z.get())
                table.see(form_item)
            else:
                name.set(f"Point {len(table.get_children()) + 1}"); x.set(""); z.set("")
                form_baseline = None
        finally:
            form_loading = False
        update_edit_state()

    def reset_fields():
        selection = table.selection()
        fill_fields(selection[0] if len(selection) == 1 else None)

    def edit_draft_status():
        try:
            route_points([(name.get() or "Waypoint", x.get(), z.get())])
            valid, reason = True, None
        except (ValueError, TypeError):
            valid, reason = False, "Enter finite numeric X and Z coordinates."
        return dict(pending=bool(draft_pending()), point=table.index(form_item)+1 if form_item and table.exists(form_item) else None,
                    valid=valid, reason=reason)

    def update_preview_hint():
        points=table.get_children()
        map_hint_text.set("No pose · Refresh" if last_pose is None else "Apply / Reset first" if draft_pending()
            else "Preview only" if busy or closing or cli_action is not None else "Select · list full" if len(points)>=MAX_WAYPOINTS
            else "Click: move · clear path" if click_move.get()
            else "Click: select / add" if points else "Click to add")

    def update_direct_state():
        idle=not busy and not closing and cli_action is None and not draft_pending() and last_pose is not None
        selected=selected_points()
        points=selected_points(True)
        chosen=route_length(*last_pose[:2],selected) if idle and selected else None
        planned=route_length(*last_pose[:2],points) if idle and points else None
        for button,allowed in ((go_button,chosen is not None and chosen<=MAX_ROUTE_DISTANCE),
            (face_button,len(selected)==1 and chosen is not None and .3<chosen<=MAX_ROUTE_DISTANCE),
            (route_button,planned is not None and planned<=MAX_ROUTE_DISTANCE),(teach_button,planned is not None and planned<=MAX_ROUTE_DISTANCE),
            (record_button,True)):
            button.configure(state="normal" if idle and allowed else "disabled")
        if recording:
            record_button.configure(text="Stop Recording", state="disabled" if record_stop.is_set() else "normal")
        else:
            record_button.configure(text="Record")

    def update_edit_state(*_):
        if not edit_buttons:
            return
        selected = table.selection()
        single = len(selected) == 1
        draft = edit_draft_status()
        idle = not busy and not closing and cli_action is None
        index = table.index(selected[0]) if single else None
        count = len(table.get_children())
        allowed = {"Update Selected": single and draft["valid"] and draft["pending"],
                   "Set selected to current": single and adapter is not None and not draft["pending"],
                   "Reset fields": draft["pending"] or not draft["valid"],
                   "Up": single and index > 0 and not draft["pending"],
                   "Down": single and index < count-1 and not draft["pending"],
                   "Remove": bool(selected) and not draft["pending"], "Clear": count > 0 and not draft["pending"],
                   "New Route…": not draft["pending"],
                   "Load": not draft["pending"], "Save Route": count>0 and not draft["pending"],
                   "Save As": count>0 and not draft["pending"],
                   "Add X / Z": draft["valid"] and count < MAX_WAYPOINTS and not draft["pending"],
                   "New point": not draft["pending"],
                   "Save Current": adapter is not None and count < MAX_WAYPOINTS and not draft["pending"],
                   "Add Target": adapter is not None and count < MAX_WAYPOINTS and not draft["pending"],
                   "Add nearby": adapter is not None and count < MAX_WAYPOINTS and not draft["pending"] and not markers.running()}
        for label, button in edit_buttons.items():
            if label in allowed:
                button.configure(state="normal" if idle and allowed[label] else "disabled")
        undo_button.configure(state="normal" if idle and edit_history and not draft["pending"] else "disabled")
        if draft["pending"]:
            draft_notice_text.set(f"Unapplied edit · point {draft['point']}")
            if not draft_notice.winfo_manager(): draft_notice.pack(side="right",after=status_details,padx=(8,0))
            workflow.tab(edit_tab,text="Edit waypoint *")
            warning = ""
            if single and point_receipts.get(selected[0]) is not None:
                old = table.item(selected[0], "values")
                try:
                    if (finite(x.get()), finite(z.get())) != (finite(old[1]), finite(old[2])):
                        warning = " Changing X/Z removes its measured height."
                except (ValueError, TypeError): pass
            edit_hint.set(f"Point {draft['point']} · Unapplied fields — Apply with Enter or Reset fields. "
                          + (draft["reason"] or "") + warning)
        elif single:
            receipt = point_receipts.get(selected[0])
            evidence = f"Measured Y {receipt['position']['y']:.3f}" if receipt else "Estimated / unknown height"
            edit_hint.set(f"Point {index+1} of {count} · {evidence} · Enter applies · Alt+↑/↓ reorders · edits are undoable")
        else:
            edit_hint.set(f"{len(selected)} selected · Select one to edit; Remove supports multiple points." if selected
                          else "Select a waypoint to edit, or enter X / Z and choose Add X / Z.")
        if not draft["pending"]:
            draft_notice.pack_forget()
            workflow.tab(edit_tab,text="Edit waypoint")
        size_status()
        if cli_server is not None:
            update_direct_state()
            update_preview_hint()
            update_replay_status()
            update_library_readiness()
            update_scene_state(force=True)

    def new_point(*,discard_draft=False):
        if busy or closing or cli_action is not None:
            state.set("Wait for the active action before starting a new point.")
            return False
        if draft_pending() and not discard_draft:
            state.set("Apply or Reset fields before starting a new point.")
            return False
        table.selection_remove(*table.selection())
        fill_fields(None)
        redraw()
        return True

    def capture_selected(label=None):
        selected = table.selection()
        if len(selected) != 1 or draft_pending():
            state.set("Apply or Reset fields, then select one waypoint to measure.")
            return
        return start("save", dict(item=selected[0], revision=route_revision,
                                 label=label or table.item(selected[0], "values")[0]))

    def add_entered():
        if busy or closing or cli_action is not None or draft_pending():
            state.set("Apply or Reset fields and wait for the active action before adding another point.")
            return
        try:
            add_point(name.get() or "Waypoint", x.get(), z.get())
        except (ValueError, TypeError):
            state.set("Enter finite numeric X and Z coordinates; waypoint unchanged.")

    def update_selected():
        nonlocal added_selection, last_edit_change
        selected = table.selection()
        if len(selected) != 1:
            state.set("Select one waypoint to update.")
            return
        try:
            label, px, pz = route_points([(name.get() or "Waypoint", x.get(), z.get())])[0]
        except (ValueError, TypeError):
            state.set("Enter finite numeric X and Z coordinates; waypoint unchanged.")
            return
        old = table.item(selected[0], "values")
        px, pz = float(f"{px:.6f}"), float(f"{pz:.6f}")
        coordinates_changed = (px, pz) != (finite(old[1]), finite(old[2]))
        if label == old[0] and not coordinates_changed:
            fill_fields(selected[0])
            state.set("Waypoint unchanged.")
            return dict(nameChanged=False, coordinatesChanged=False, measurementDiscarded=False, recordingDiscarded=False, measurementReplaced=False)
        last_edit_change = dict(nameChanged=label != old[0], coordinatesChanged=coordinates_changed,
                                measurementDiscarded=coordinates_changed and point_receipts.get(selected[0]) is not None,
                                recordingDiscarded=coordinates_changed and "recording" in route_metadata, measurementReplaced=False)
        remember_edit()
        invalidate_progress(clear_metadata=coordinates_changed)
        if coordinates_changed:
            point_receipts.pop(selected[0], None)
        table.item(selected[0], values=(label, f"{px:.6f}", f"{pz:.6f}"))
        added_selection = None
        fill_fields(selected[0])
        redraw()
        state.set("Waypoint updated; save the route to keep this edit." +
                  (" Measured height removed; use Set selected to current to measure again." if last_edit_change["measurementDiscarded"] else ""))
        return deepcopy(last_edit_change)

    def save_route(save_as=False):
        if draft_pending():
            state.set("Apply or Reset fields before saving the route.")
            return
        if not table.get_children():
            state.set("Add a waypoint before saving the route.")
            return False
        path = route_path
        if save_as or path is None:
            options = {"defaultextension": ".json", "initialfile": path.name if path else "rift-waypoints.json"}
            directory = ROOT / "artifacts" / "waypoint-routes"
            directory.mkdir(parents=True, exist_ok=True)
            options["initialdir"] = str(directory)
            if path is not None:
                options["initialdir"] = str(path.parent)
            path = filedialog.asksaveasfilename(**options)
        if path:
            try:
                document = route_document()
                write_json_atomic(path, document)
                mark_saved(path)
                cache_route(document, "Route saved: " + str(path))
                return True
            except (ValueError, TypeError, OSError) as exc:
                diagnostics.exception("Unable to save route", exc=exc)
                messagebox.showerror("Cannot save route", str(exc))
        return False

    def load_from(path):
        if draft_pending():
            state.set("Apply or Reset fields before loading another route.")
            return
        nonlocal playback_view, pending_progress_selection
        if busy or closing:
            return
        try:
            document = prepared_document(json.loads(Path(path).read_text(encoding="utf-8")))
            if route_dirty:
                decision = messagebox.askyesnocancel(
                    "Unsaved route changes", "Save changes to the current route before loading another route?",
                    parent=window)
                if decision is None or (decision and not save_route()):
                    return
                if decision:
                    # Saving may have updated the very file being loaded.
                    document = prepared_document(json.loads(Path(path).read_text(encoding="utf-8")))
            progress = select_progress(document)
            show_document(document)
            edit_history.clear()
            pending_progress_selection = current_identity() is None
            playback_view = None
            if progress is not None:
                display_progress(progress)
            else:
                progress_text.set("No saved progress; choose Play Forward or Play Reverse.")
                redraw()
            mark_saved(path)
            cache_route(document, "Route loaded: " + str(path))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            diagnostics.exception("Unable to load route", exc=exc)
            messagebox.showerror("Cannot load route", str(exc))

    def begin_new_route(label=None):
        nonlocal route_metadata, route_path, route_dirty, route_recovered
        nonlocal playback_view, pending_progress_selection, route_revision
        table.delete(*table.get_children())
        point_receipts.clear()
        edit_history.clear()
        route_metadata = {"routeName": label.strip()} if label and label.strip() else {}
        context = zone_state()["context"]
        if context is not None:
            route_metadata["routeContext"] = context
        route_path, route_dirty, route_recovered = None, False, False
        playback_view, pending_progress_selection = None, False
        route_revision += 1
        fill_fields()
        progress_text.set("New route; add waypoints before playback.")
        update_route_status()
        redraw()
        state.set("New route ready. Add waypoints, then Save Route to create its JSON file.")

    def new_route():
        nonlocal route_path, route_dirty
        if busy or closing or cli_action is not None or draft_pending():
            return
        directory = ROOT / "artifacts" / "waypoint-routes"
        directory.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            title="New Waypoint File", parent=window, initialdir=str(directory),
            initialfile="new-route.json", defaultextension=".json",
            filetypes=[("Waypoint JSON", "*.json")])
        if not chosen:
            return
        if route_dirty:
            decision = messagebox.askyesnocancel(
                "Unsaved route changes", "Save changes to the current route before starting a new route?",
                parent=window)
            if decision is None or (decision and not save_route()):
                return
        route_file = Path(chosen).absolute()
        begin_new_route(route_file.stem)
        route_path, route_dirty = route_file, True
        update_route_status()
        state.set(f"New file: {route_file} — add waypoints, then Save Route.")

    def load_route():
        path = filedialog.askopenfilename(filetypes=[("Waypoint JSON", "*.json")])
        if path:
            load_from(path)

    def load_recent():
        index = recent_dropdown.current()
        value = recent_paths[index] if 0 <= index < len(recent_paths) else None
        if value is None or local_source_path(value) is None:
            state.set("Choose a recent local route to load.")
            return
        load_from(value)

    def remove_points():
        selected = table.selection()
        if selected:
            remember_edit()
            invalidate_progress()
        for item in selected:
            point_receipts.pop(item, None)
        table.delete(*selected)
        redraw()

    def move_point(direction):
        selected = table.selection()
        if len(selected) != 1:
            state.set("Select one waypoint to move up or down.")
            return
        item = selected[0]
        index = max(0, min(len(table.get_children()) - 1, table.index(item) + direction))
        if index != table.index(item):
            remember_edit()
            invalidate_progress()
        table.move(item, "", index)
        table.see(item)
        redraw()

    def clear_points():
        if table.get_children():
            remember_edit()
            invalidate_progress()
        table.delete(*table.get_children())
        point_receipts.clear()
        fill_fields()
        redraw()
        state.set("Waypoint list cleared.")

    def playback(direction=None):
        try:
            document = route_document()
            if direction is None:
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                direction = saved["direction"]
                start("resume", (document, direction))
            else:
                start("play", (document, direction))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            diagnostics.exception("Unable to start playback", exc=exc)
            state.set("Cannot start playback: " + str(exc))

    def stop_recording():
        if recording:
            record_stop.set()
            record_button.configure(state="disabled")
            record_end_button.configure(state="disabled")
            state.set("Finishing recording…")

    def toggle_recording():
        if recording:
            stop_recording()
        else:
            start("record")

    def save_view():
        nonlocal saved_unit_sample
        if busy or closing or nearby_picker is not None:
            return
        if adapter is None:
            state.set("Wait for RIFT to connect before saving a view.")
            return
        if draft_pending():
            state.set("Apply or Reset waypoint fields before capturing the route.")
            return
        readiness = capture_readiness()
        if not readiness["ready"]:
            state.set(readiness["reason"])
            return
        try:
            saved_unit_sample = None
            document = deepcopy(route_document())
            document["waypoints"] = [list(row) for row in document["waypoints"]]
            start("view", (document, adapter.pid, deepcopy(adapter.target),
                           "desktop" if view_bring_forward.get() else "wgc", view_include_units.get()))
        except (ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to save view", exc=exc)
            state.set("Cannot save view: " + str(exc))

    def close_nearby_picker():
        nonlocal nearby_picker
        if nearby_picker is not None:
            picker, nearby_picker = nearby_picker, None
            picker.grab_release()
            picker.destroy()

    def add_nearby():
        nonlocal nearby_picker
        if busy or closing or markers.running() or nearby_picker is not None:
            state.set("Wait until the current action and markers have stopped before adding a saved sample.")
            return
        try:
            identity = current_identity() or deepcopy(last_verified_owner)
            if identity is None:
                raise WaypointError("Connect a verified player once before browsing saved samples.")
            source = saved_unit_sample or filedialog.askopenfilename(
                parent=window, title="Choose retained units-sample.json",
                filetypes=[("Saved nearby samples", "units-sample.json"), ("JSON", "*.json")])
            if not source:
                return
            from scripts.saved_nearby_waypoints import load_saved_nearby_waypoints
            rows = deepcopy(load_saved_nearby_waypoints(source, identity))[:18]
            if not rows:
                raise WaypointError("No saved nearby samples are available.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to add nearby sample", exc=exc)
            messagebox.showerror("Cannot add nearby sample", str(exc), parent=window)
            return
        picker = nearby_picker = tk.Toplevel(window)
        picker.configure(background=PALETTE["base"])
        picker.title("Add nearby — saved samples")
        picker.transient(window)
        body = ttk.Frame(picker, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Saved samples; Add saves a fixed observed location. No movement or live tracking.",
                  wraplength=750).pack(anchor="w", pady=(0, 8))
        listing = ttk.Treeview(body, columns=("number", "name", "distance", "xyz"), show="headings",
                               selectmode="browse", height=min(18, len(rows)))
        for key, title, width in (("number", "U#", 45), ("name", "Candidate name", 230),
                                  ("distance", "Saved distance", 105), ("xyz", "Observed X / Y / Z", 310)):
            listing.heading(key, text=title)
            listing.column(key, width=width)
        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        listing.pack(in_=list_frame, side="left", fill="both", expand=True)
        nearby_scroll = ttk.Scrollbar(list_frame, command=listing.yview)
        nearby_scroll.pack(side="right", fill="y")
        listing.configure(yscrollcommand=nearby_scroll.set)
        samples = {}
        for row in rows:
            point = row["position"]
            item = listing.insert("", "end", values=(f"U{row['number']}", row["label"],
                f"{row['distance']:.2f}", f"{point['x']:.6f} / {point['y']:.6f} / {point['z']:.6f}"))
            samples[item] = row
        observed = tk.StringVar(value="Select a saved sample to see its observation UTC.")
        ttk.Label(body, textvariable=observed, wraplength=750).pack(anchor="w", pady=6)
        actions = ttk.Frame(body)
        actions.pack(fill="x")

        def selection_changed(_=None):
            selected = listing.selection()
            add_button.configure(state="normal" if len(selected) == 1 else "disabled")
            if len(selected) == 1:
                observed.set("Observed UTC: " + samples[selected[0]]["observedAtUtc"])

        def commit_selected():
            selected = listing.selection()
            if busy or closing or markers.running() or len(selected) != 1:
                return
            current = current_identity()
            if current is None or any(str(current.get(key, "")).casefold() != str(identity[key]).casefold()
                    for key in ("machine", "gameBuildSha256", "unitKey")):
                observed.set("Player identity unavailable or changed; cancel and refresh before adding.")
                return
            row = deepcopy(samples[selected[0]])
            point = row["position"]
            if last_y is None or abs(point["y"] - last_y) > 1:
                observed.set("Saved sample is on a different height; choose a ground point near the player.")
                return
            item = add_point(row["label"], point["x"], point["z"])
            if item is not None:
                point_receipts[item] = row["measurement"]
                redraw()
                state.set("Added fixed saved location: " + row["label"] + "; observed " + row["observedAtUtc"])
                close_nearby_picker()

        add_button = ttk.Button(actions, text="Add Selected", command=commit_selected, state="disabled")
        add_button.pack(side="left")
        ttk.Button(actions, text="Cancel", command=close_nearby_picker).pack(side="right")
        listing.bind("<<TreeviewSelect>>", selection_changed)
        picker.protocol("WM_DELETE_WINDOW", close_nearby_picker)
        picker.bind("<Escape>", lambda _: close_nearby_picker())
        picker.update_idletasks()
        popup_width = min(850, window.winfo_width() - 40)
        popup_height = min(picker.winfo_reqheight(), max(300, window.winfo_height() - 60))
        picker.geometry(f"{max(620, popup_width)}x{popup_height}"
                        f"+{window.winfo_rootx() + max(20, (window.winfo_width() - popup_width) // 2)}"
                        f"+{window.winfo_rooty() + 30}")
        picker.grab_set()

    def load_saved_scene(source):
        nonlocal saved_view, saved_rerun, saved_unit_sample, last_capture_state, last_capture_error
        path = cli_file(source)
        if path.stat().st_size > 1048576: raise ValueError("Scene manifest is too large")
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict) or manifest.get("status") != "saved-route-view-candidate":
            raise ValueError("Choose a saved scene manifest")
        def asset(value):
            if not value: return None
            candidate = Path(value)
            resolved = cli_file(candidate if candidate.is_absolute() else path.parent / candidate)
            return str(resolved) if resolved.is_file() else None
        image, rerun = asset(manifest.get("image")), asset((manifest.get("rerun") or {}).get("path"))
        sample = asset((manifest.get("unitSample") or {}).get("path"))
        if image is None and rerun is None: raise ValueError("Saved scene assets are unavailable")
        saved_view, saved_rerun, saved_unit_sample = image, rerun, sample
        last_capture_state, last_capture_error = "loaded", None
        state.set("Saved scene loaded; choose Open view or Open 3D view.")
        restore_editing()
        return cli_view_status()

    def open_saved_view():
        if busy or closing: return
        chosen = filedialog.askopenfilename(parent=window, title="Open saved scene manifest",
                                           filetypes=[("Saved scene JSON", "*.json")])
        if not chosen: return
        try:
            load_saved_scene(chosen)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            diagnostics.exception("Unable to load saved scene", exc=exc)
            state.set("Cannot load saved scene: " + str(exc))

    def open_view():
        if saved_view is None or busy or closing:
            return
        try:
            import os
            os.startfile(saved_view)
        except OSError as exc:
            diagnostics.exception("Unable to open scene image", exc=exc)
            state.set("Cannot open view: " + str(exc))

    def open_3d_view():
        nonlocal rerun_viewer
        if saved_rerun is None or busy or closing:
            return
        if rerun_viewer is not None and rerun_viewer.poll() is None:
            state.set("3D view is already open.")
            return
        try:
            from scripts.save_physical_route_view import launch_saved_rerun
            rerun_viewer = launch_saved_rerun(saved_rerun)
            state.set("3D view opened: " + saved_rerun)
        except (OSError, ValueError, TypeError) as exc:
            diagnostics.exception("Unable to open 3D scene", exc=exc)
            state.set("Cannot open 3D view: " + str(exc))

    def marker_payload():
        document = route_document() if table.get_children() else {"waypoints": []}
        selected = table.selection()
        landmark = table.index(selected[0]) + 1 if landmark_guide.get() and len(selected) == 1 else None
        if explore_controls is not None:
            guidance = explore_controls.navigation_state()
            if guidance["status"] == "active" and guidance["activeIndex"] is not None:
                landmark = guidance["activeIndex"] + 1
        return {"route": document, "landmarkNumber": landmark}

    def publish_marker_update():
        nonlocal marker_update_after, marker_pending_signature, marker_published
        marker_update_after = None
        marker_pending_signature = None
        if closing or loading_route or marker_identity is None or not markers.running() or markers.stop_requested:
            return
        try:
            if zone_comparison() == "mismatch":
                stop_markers()
                state.set("Markers hidden: route zone candidate differs from current zone.")
                return
            payload = marker_payload()
            signature = json.dumps(payload, sort_keys=True)
            if signature != marker_published:
                markers.update(payload["route"], landmark_number=payload["landmarkNumber"])
                marker_published = signature
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to publish marker update", exc=exc)
            reason = "Cannot update markers: " + str(exc)
            if not stop_markers():
                reason += "; marker shutdown could not be confirmed"
            state.set(reason)

    def schedule_marker_update():
        nonlocal marker_update_after, marker_pending_signature
        if loading_route or closing or marker_identity is None or not markers.running() or markers.stop_requested:
            return
        try:
            signature = json.dumps(marker_payload(), sort_keys=True)
        except (ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to prepare marker update", exc=exc)
            stop_markers()
            state.set("Cannot update markers: " + str(exc))
            return
        if signature == marker_published:
            if marker_update_after is not None:
                window.after_cancel(marker_update_after)
                marker_update_after = None
            marker_pending_signature = None
            return
        if marker_update_after is not None and signature == marker_pending_signature:
            return
        if marker_update_after is not None:
            window.after_cancel(marker_update_after)
        marker_pending_signature = signature
        marker_update_after = window.after(150, publish_marker_update)

    def stop_markers():
        nonlocal marker_update_after, marker_pending_signature, marker_restart_pending
        marker_restart_pending = False
        if marker_update_after is not None:
            window.after_cancel(marker_update_after)
            marker_update_after = None
        marker_pending_signature = None
        if not markers.running():
            return True
        try:
            markers.stop()
            marker_button.configure(text="Markers closing…", state="disabled")
            return True
        except OSError as exc:
            diagnostics.exception("Unable to stop markers", exc=exc)
            state.set("Cannot hide markers: " + str(exc))
            return False

    def toggle_markers():
        nonlocal marker_identity, marker_published, marker_anchor_y, marker_running_target
        if markers.running():
            if stop_markers():
                state.set("Hiding markers…")
            return
        # This read-only child performs its own fresh epoch/player/camera reads.
        # It need not wait for, or use the cached pose from, an idle GUI refresh.
        if busy or closing or adapter is None:
            state.set("Wait for the current RIFT connection before showing markers.")
            return
        try:
            if zone_comparison() == "mismatch":
                raise WaypointError("Saved route zone differs from current zone candidate; load a matching route first")
            options = {}
            from scripts.physical_waypoint_overlay import bind_companion_window
            if target_beacon.get():
                options["target_beacon"] = True
            if landmark_guide.get():
                selected = table.selection()
                if len(selected) != 1:
                    raise WaypointError("Select one saved marker to guide to")
                options["landmark_number"] = table.index(selected[0]) + 1
            options["companion"] = bind_companion_window(window.winfo_id())
            markers.start(route_document() if table.get_children() else {"waypoints": []}, adapter, **options)
            marker_anchor_y = last_y
            marker_running_target = target_beacon.get()
            marker_published = json.dumps(marker_payload(), sort_keys=True)
            target = adapter.target
            marker_identity = (adapter.pid, str(target["processStartUtcTicks"]),
                               target["executableSha256"].casefold(), target["hwnd"])
            marker_button.configure(text="Hide markers")
            state.set("Overlay reader started; beacons appear with a fresh camera frame in RIFT or this window."
                      + " Route edits and selected-guide changes sync automatically.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.exception("Unable to start marker reader", exc=exc)
            state.set("Cannot show markers: " + str(exc))

    def target_change_blocked():
        return (explore_controls is not None and (explore_controls.navigation_state().get("status") == "active"
                or explore_controls.trail.snapshot().get("active")))

    def change_target_inclusion():
        nonlocal marker_restart_pending
        if not markers.running() or target_beacon.get() == marker_running_target: return True
        if target_change_blocked():
            target_beacon.set(marker_running_target)
            state.set("Stop manual guidance and trail recording before changing target inclusion.")
            return False
        if not stop_markers():
            target_beacon.set(marker_running_target)
            return False
        marker_restart_pending = True
        state.set("Restarting overlay reader for target inclusion; appearance and radar settings retained.")
        return True

    def save_marker_appearance():
        nonlocal appearance_after
        if appearance_after is not None:
            window.after_cancel(appearance_after)
            appearance_after = None
        try:
            save_style(appearance_path, dict(schemaVersion=1, beaconScale=round(beacon_size.get()) / 100,
                                            opacity=round(beacon_opacity.get()) / 100,
                                            labelsVisible=beacon_labels.get()))
            return True
        except (OSError, ValueError, TypeError) as exc:
            diagnostics.exception("Unable to save marker appearance", exc=exc)
            state.set("Cannot save marker appearance: " + str(exc))
            return False

    def change_marker_appearance(_=None):
        nonlocal appearance_after
        size_percent.set(f"{round(beacon_size.get())}%")
        opacity_percent.set(f"{round(beacon_opacity.get())}%")
        if appearance_after is not None:
            window.after_cancel(appearance_after)
        appearance_after = window.after(150, save_marker_appearance)

    def reset_marker_appearance():
        beacon_size.set(DEFAULT_STYLE["beaconScale"] * 100)
        beacon_opacity.set(DEFAULT_STYLE["opacity"] * 100)
        beacon_labels.set(DEFAULT_STYLE["labelsVisible"])
        change_marker_appearance()
        return save_marker_appearance()

    buttons_selected = ttk.Frame(edit_tab, style="Surface.TFrame")
    buttons_selected.pack(fill="x", pady=(0, 6))
    buttons = ttk.Frame(edit_tab, style="Surface.TFrame")
    buttons.pack(fill="x", pady=(0, 6))
    buttons_second = ttk.Frame(edit_tab, style="Surface.TFrame")
    buttons_second.pack(fill="x")
    for label, parent, callback in (("Refresh", header_actions, lambda: start("refresh")),
            ("New point", buttons, new_point),
            ("Save Current", buttons, lambda: start("save")), ("Add X / Z", buttons, add_entered),
            ("Add Target", buttons, lambda: start("target")), ("Add nearby", buttons, add_nearby),
            ("Update Selected", buttons_selected, update_selected),
            ("Set selected to current", buttons_selected, capture_selected),
            ("Reset fields", buttons_selected, reset_fields), ("Up", buttons_selected, lambda: move_point(-1)),
            ("Down", buttons_selected, lambda: move_point(1)), ("Remove", buttons_selected, remove_points),
            ("Clear", buttons, clear_points), ("New Route…", file_toolbar, new_route),
            ("Load", file_toolbar, load_route),
            ("Save Route", file_toolbar, save_route), ("Save As", file_toolbar, lambda: save_route(True))):
        button = ttk.Button(parent, text=label, command=callback,
                            style="Primary.TButton" if label in ("Save Route", "Update Selected") else "TButton")
        if label == "Refresh":
            button.pack(anchor="e", before=header_actions.winfo_children()[0])
        else:
            button.pack(side="left", padx=(0, 6))
        editable.append(button)
        edit_buttons[label] = button
        if label == "Add nearby":
            nearby_button = button
    undo_button = ttk.Button(buttons_selected, text="Undo", command=undo_edit, state="disabled")
    undo_button.pack(side="left", padx=(0, 6))
    editable.append(undo_button)
    edit_hint_label = ttk.Label(edit_tab, textvariable=edit_hint, style="Muted.TLabel", wraplength=850)
    edit_hint_label.pack(anchor="w", pady=(8, 0))
    edit_tab.bind("<Configure>", lambda event: edit_hint_label.configure(wraplength=max(200, event.width-28)))
    for column,weight in enumerate((4,3,3)):
        replay_tab.columnconfigure(column, weight=weight, uniform="replaycards")
    playback_group = ttk.LabelFrame(replay_tab, text="PLAYBACK", padding=(10, 5), style="Card.TLabelframe")
    playback_group.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    recording_controls = ttk.LabelFrame(replay_tab, text="RECORD A PATH", padding=(10, 5), style="Card.TLabelframe")
    recording_controls.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
    controls = ttk.LabelFrame(replay_tab, text="DIRECT MOVEMENT", padding=(10, 3), style="Card.TLabelframe")
    controls.grid(row=0, column=2, sticky="nsew")
    compact_style = ttk.Style(window)
    compact_style.configure("Direct.TButton", padding=(7, 2), font=("Segoe UI", 9, "bold"))
    compact_style.configure("Direct.TCheckbutton", padding=(2, 0), font=("Segoe UI", 9))
    for label, row, column, span, callback in (
            ("Go Selected", 0, 0, 1, lambda: start("go", selected_points())),
            ("Face Selected", 0, 1, 1, lambda: start("face", selected_points())),
            ("Run Route", 1, 0, 2, lambda: start("go", selected_points(True)))):
        button = ttk.Button(controls, text=label, command=callback, style="Direct.TButton")
        button.grid(row=row, column=column, columnspan=span, sticky="ew", padx=(0, 5), pady=(0, 2))
        editable.append(button)
        if label == "Go Selected":
            go_button = button
        elif label == "Run Route":
            route_button = button
        else:
            face_button = button
    face_option = ttk.Checkbutton(controls, text="Face before direct / auto-walk",
                                  variable=walk_facing, style="Direct.TCheckbutton")
    face_option.grid(row=2, column=0, columnspan=2, sticky="w")
    editable.append(face_option)
    engine_option = ttk.Checkbutton(controls, text="Continuous travel", variable=continuous_travel,
                                    style="Direct.TCheckbutton")
    engine_option.grid(row=3, column=0, columnspan=2, sticky="w")
    editable.append(engine_option)
    def configure_survival(path=None):
        if busy or closing or cli_action is not None:
            raise WaypointError("Wait for the active action before changing survival")
        if path is None:
            path = filedialog.askopenfilename(parent=window, title="Choose survival ability profile",
                                             filetypes=[("Survival profile", "*.json")])
        if not path:
            return
        result = survival_runtime.configure(path, adapter)
        survival_summary.set("Survival: configured " + str(result.get("profileSource")))
        return result
    survival_option = ttk.Checkbutton(controls, text="Fight / retreat / recover on routes",
                                      variable=survival_enabled, style="Direct.TCheckbutton")
    survival_option.grid(row=4, column=0, columnspan=2, sticky="w")
    editable.append(survival_option)
    for column, label, callback in ((0, "Ability profile…", configure_survival),
                                     (1, "Check survival", lambda: start("survival-preflight"))):
        button = ttk.Button(controls, text=label, command=callback, style="Direct.TButton")
        button.grid(row=5, column=column, sticky="ew")
        editable.append(button)
    ttk.Label(controls, textvariable=survival_summary, style="Micro.TLabel", wraplength=260).grid(
        row=6, column=0, columnspan=2, sticky="w")
    teach_button = ttk.Button(recording_controls, text="Auto-walk + record", command=lambda: start("teach", selected_points(True)))
    teach_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
    editable.append(teach_button)
    stop_button = ttk.Button(stop_slot, text="STOP", command=request_stop, style="Danger.TButton", width=15)
    stop_button.pack(fill="both")
    stop_hint = tk.StringVar(value="F8 inactive · Esc in app")
    ttk.Label(stop_slot, textvariable=stop_hint, style="Base.Micro.TLabel").pack(anchor="center", pady=(5, 0))
    playback_buttons = {}
    for label, parent, row, column, callback in (("Record", recording_controls, 0, 0, toggle_recording),
            ("Play Forward", playback_group, 0, 0, lambda: playback("forward")),
            ("Play Reverse", playback_group, 1, 0, lambda: playback("reverse")),
            ("Resume", playback_group, 2, 0, playback)):
        button = ttk.Button(parent, text=label, command=callback,
                            style="Primary.TButton" if label == "Play Forward" else "TButton",
                            **({"width":12} if parent is playback_group else {}))
        button.grid(row=row, column=column, sticky="ew", padx=(0, 5), pady=(0,3) if parent is playback_group else (0,7))
        editable.append(button)
        playback_buttons[label] = button
    record_button = playback_buttons["Record"]
    forward_button = playback_buttons["Play Forward"]
    reverse_button = playback_buttons["Play Reverse"]
    resume_button = playback_buttons["Resume"]
    record_end_button = ttk.Button(recording_controls, text="Stop Recording", command=stop_recording, state="disabled")
    record_end_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=(0, 7))
    record_end_button.grid_remove()  # The main Record button now toggles stop/save.
    record_button.grid_configure(columnspan=2)
    for group in (playback_group, recording_controls, controls):
        group.columnconfigure(0, weight=1)
        group.columnconfigure(1, weight=1)
    playback_group.columnconfigure(0,weight=0)
    playback_group.columnconfigure(1,weight=1)
    ttk.Label(playback_group, text="Play walks to a nearby start, then follows the route", style="Micro.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
    ttk.Label(recording_controls, text="Click to start / stop · 5-unit spacing + turns", style="Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
    progress_text = tk.StringVar(value="No playback started.")
    progress_label = ttk.Label(replay_tab, textvariable=progress_text, style="Muted.TLabel", wraplength=860)
    progress_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
    replay_hints = {}
    replay_full_hints = {}
    replay_hint_labels = []
    for row, action in enumerate(("forward", "reverse", "resume")):
        replay_hints[action] = tk.StringVar(value=f"{action.title()}: waiting for pose")
        replay_full_hints[action]="Waiting for playback state"
        label = ttk.Label(playback_group, textvariable=replay_hints[action], style="Micro.TLabel", wraplength=205)
        label.grid(row=row, column=1, sticky="w", padx=(5,0), pady=(0,3))
        attach_path_tooltip(label,lambda action=action:replay_full_hints[action])
        attach_path_tooltip((forward_button,reverse_button,resume_button)[row],lambda action=action:replay_full_hints[action])
        replay_hint_labels.append(label)
    replay_progress = ttk.Progressbar(replay_tab, style="Replay.Horizontal.TProgressbar", mode="determinate", maximum=1, value=0)
    replay_progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    def size_replay(event):
        progress_label.configure(wraplength=max(200, event.width - 30))
    def size_playback(event):
        for label in replay_hint_labels:
            label.configure(wraplength=max(100,event.width-forward_button.winfo_reqwidth()-40))
    replay_tab.bind("<Configure>", size_replay)
    playback_group.bind("<Configure>",size_playback)
    scene_tab.columnconfigure(0, weight=1)
    scene_tab.columnconfigure(1, weight=1)
    view_controls = ttk.LabelFrame(scene_tab, text="CAPTURE & EXPLORE", padding=(12, 8), style="Card.TLabelframe")
    view_controls.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
    view_buttons = ttk.Frame(view_controls, style="Surface.TFrame")
    view_buttons.pack(fill="x", pady=(0, 8))
    save_view_button = ttk.Button(view_buttons, text="Save view", command=save_view, style="Primary.TButton")
    save_view_button.grid(row=0, column=0, sticky="ew", padx=(0,6), pady=(0,6))
    editable.append(save_view_button)
    open_view_button = ttk.Button(view_buttons, text="Open view", command=open_view, state="disabled")
    open_view_button.grid(row=1, column=0, sticky="ew", padx=(0,6))
    editable.append(open_view_button)
    open_3d_button = ttk.Button(view_buttons, text="Open 3D view", command=open_3d_view, state="disabled")
    open_3d_button.grid(row=1, column=1, sticky="ew")
    editable.append(open_3d_button)
    saved_scene_button = ttk.Button(view_buttons, text="Open saved…", command=open_saved_view)
    saved_scene_button.grid(row=0, column=1, sticky="ew", pady=(0,6))
    editable.append(saved_scene_button)
    view_buttons.columnconfigure(0, weight=1)
    view_buttons.columnconfigure(1, weight=1)
    capture_options = ttk.Frame(view_controls, style="Surface.TFrame")
    capture_options.pack(fill="x")
    view_focus_option = ttk.Checkbutton(capture_options, text="Bring RIFT forward for capture", variable=view_bring_forward)
    view_focus_option.pack(side="left", padx=(0,8))
    editable.append(view_focus_option)
    view_units_option = ttk.Checkbutton(capture_options, text="Nearby units in 3D", variable=view_include_units)
    view_units_option.pack(side="left")
    editable.append(view_units_option)
    capture_hint_label = ttk.Label(view_controls, textvariable=capture_hint, style="Muted.TLabel", wraplength=370)
    capture_hint_label.pack(anchor="w", pady=(5,0))
    view_controls.bind("<Configure>", lambda event:capture_hint_label.configure(wraplength=max(180,event.width-26)))
    marker_controls = ttk.LabelFrame(scene_tab, text="WORLD BEACONS", padding=(12, 8), style="Card.TLabelframe")
    marker_controls.grid(row=0, column=1, sticky="nsew")
    marker_actions = ttk.Frame(marker_controls, style="Surface.TFrame")
    marker_actions.grid(row=0, column=0, sticky="nw", padx=(0, 10))
    marker_controls.columnconfigure(1, weight=1)
    marker_button = ttk.Button(marker_actions, text="Show markers", command=toggle_markers)
    marker_button.pack(anchor="w", pady=(0, 8))
    editable.append(marker_button)
    target_option = ttk.Checkbutton(marker_actions, text="Include selected target in markers", variable=target_beacon,
                                   command=change_target_inclusion)
    target_option.pack(anchor="w")
    editable.append(target_option)
    landmark_option = ttk.Checkbutton(marker_actions, text="Guide selected marker", variable=landmark_guide,
                                     command=schedule_marker_update)
    landmark_option.pack(anchor="w", pady=(3, 0))
    editable.append(landmark_option)
    appearance_controls = ttk.Frame(marker_controls, style="Surface.TFrame")
    appearance_controls.grid(row=0, column=1, sticky="nsew")
    appearance_controls.columnconfigure(1, weight=1)
    appearance_widgets = []
    for row, label, variable, lower, upper, percent in ((0, "Size", beacon_size, 50, 200, size_percent),
                                                       (1, "Opacity", beacon_opacity, 20, 100, opacity_percent)):
        ttk.Label(appearance_controls, text=label, style="Surface.Micro.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 6))
        slider = ttk.Scale(appearance_controls, from_=lower, to=upper, variable=variable,
                           command=change_marker_appearance, length=80, style="Beacon.Horizontal.TScale")
        slider.grid(row=row, column=1, sticky="ew", pady=4)
        slider.bind("<ButtonRelease-1>", lambda _: save_marker_appearance())
        appearance_widgets.append(slider)
        ttk.Label(appearance_controls, textvariable=percent, style="Surface.Micro.TLabel", width=5).grid(
            row=row, column=2, sticky="e", padx=(6, 0))
    labels_option = ttk.Checkbutton(appearance_controls, text="Show labels", variable=beacon_labels,
                                   command=save_marker_appearance)
    labels_option.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))
    reset_appearance = ttk.Button(appearance_controls, text="Reset", command=reset_marker_appearance,
                                  style="Ghost.TButton", width=5)
    reset_appearance.grid(row=2, column=2, sticky="e", pady=(5, 0))
    appearance_widgets.extend((labels_option, reset_appearance))
    beacon_hint_label = ttk.Label(marker_controls, textvariable=beacon_hint, style="Muted.TLabel", wraplength=400)
    beacon_hint_label.grid(row=1, column=0, columnspan=2, sticky="nw", pady=(6,0))
    marker_controls.bind("<Configure>", lambda event:beacon_hint_label.configure(wraplength=max(180,event.width-26)))
    from scripts.waypoint_explore_ui import ExploreControls
    if not hasattr(markers, "radar_path"):
        markers.radar_path = (ROOT / "artifacts" / "waypoint-radar-style.json").absolute()
    def exploration_binding():
        path = getattr(markers, "pose_path", None)
        if adapter is None or path is None or not markers.running():
            return None
        return dict(target=adapter.target, playerKey=adapter.binding["runtimeIdentity"]["unitKey"],
                    sessionId=Path(path).stem)

    def publish_exploration(guidance, segments):
        nonlocal exploration_trail
        exploration_trail = segments
        path = getattr(markers, "exploration_path", None)
        if path is None or not markers.running() or markers.stop_requested:
            return
        try:
            from scripts.waypoint_explore_ui import write_feedback
            write_feedback(path, dict(version=1, owner=exploration_binding(),
                acquiredMonotonic=exploration_sample, guidance=guidance, trail=segments))
            schedule_marker_update()
        except (OSError, ValueError, TypeError) as exc:
            diagnostics.exception("Unable to publish exploration feedback", exc=exc)
            state.set("Exploration display temporarily unavailable; details in Activity.")

    def ensure_exploration_feed():
        live_pose.set(True)
        if not markers.running() and not marker_restart_pending:
            toggle_markers()

    def exploration_block_reason(operation="guide"):
        if closing:
            return "The helper is closing"
        if busy or cli_action is not None:
            return "Wait for the active action to finish"
        if operation == "guide" and cli_server is not None and zone_comparison() == "mismatch":
            return "Route zone candidate differs; load a matching route"
        return None

    explore_controls = ExploreControls(explore_tab, markers, ensure_exploration_feed, state,
        get_document=lambda: route_document() if table.get_children() else {"waypoints": []},
        get_selected_index=lambda: table.index(table.selection()[0]) if len(table.selection()) == 1 else None,
        get_binding=exploration_binding, on_navigation=publish_exploration,
        get_block_reason=exploration_block_reason,
        on_error=lambda message, exc: diagnostics.exception(message, exc=exc))
    recent_choice = tk.StringVar()
    ttk.Label(recent_controls, text="Recent routes", style="Surface.Micro.TLabel").grid(row=0, column=0, padx=(0, 8))
    recent_dropdown = ttk.Combobox(recent_controls, textvariable=recent_choice, state="readonly", width=18)
    recent_dropdown.grid(row=0, column=1, sticky="ew", padx=(0, 6))
    attach_path_tooltip(recent_dropdown, lambda: recent_paths[recent_dropdown.current()]
                        if 0 <= recent_dropdown.current() < len(recent_paths) else "")
    editable.append(recent_dropdown)
    recent_load_button = ttk.Button(recent_controls, text="Load recent", command=load_recent, state="disabled")
    recent_load_button.grid(row=0, column=2)
    editable.append(recent_load_button)
    footer_label = ttk.Label(frame, text=f"Clear path · route ≤ {MAX_ROUTE_DISTANCE:g} units / {MAX_WAYPOINTS} points · continuous or pulse travel · STOP/F8 releases owned movement. "
              "Stop Recording saves; STOP cancels recording. Play starts within 0.30 units of Start (Forward) or End (Reverse).",
              style="Base.Micro.TLabel", wraplength=900)
    footer_label.grid(row=5, column=0, sticky="w")
    frame.bind("<Configure>", lambda event: footer_label.configure(wraplength=max(200, event.width - 44)))
    table.tag_configure("completed", foreground="#7ba89a")
    table.tag_configure("next", foreground="#f4c779")

    close_prompt = False

    def restore_editing():
        for widget in editable:
            widget.configure(state="disabled" if busy or closing else "normal")
        if not busy and not closing:
            recent_dropdown.configure(state="readonly")
            recent_load_button.configure(state="normal" if recent_paths else "disabled")
            open_view_button.configure(state="normal" if saved_view else "disabled")
            open_3d_button.configure(state="normal" if saved_rerun else "disabled")
        redraw()
        if busy or closing:
            for widget in editable:
                widget.configure(state="disabled")

    def finish_close():
        nonlocal closing, close_prompt, cli_destroyed
        if cli_destroyed:
            return True
        if (not closing or close_prompt or busy or observing or zone_observing or foreground_stop is not None
                or markers.running()):
            return False
        close_prompt = True
        try:
            if route_dirty:
                decision = messagebox.askyesnocancel(
                    "Unsaved route changes", "Save changes to the current route before closing?", parent=window)
                if decision is None or (decision and not save_route()):
                    closing = False
                    restore_editing()
                    return False
            if appearance_after is not None:
                save_marker_appearance()
            if cli_close_id is not None:
                cli_server.complete(cli_close_id, cli_ok({"closed": True, "ownedWorkersReleased": True}))
            if cli_server is not None:
                cli_server.close()
            cli_destroyed = True
            window.destroy()
            return True
        finally:
            close_prompt = False

    def close(*, discard_trail=False):
        if draft_pending():
            state.set("Apply or Reset fields before closing, or use app close --discard.")
            return
        nonlocal closing
        if closing:
            return
        if explore_controls.trail.snapshot()["pointCount"] and not discard_trail:
            if not messagebox.askyesno("Discard breadcrumb trail?",
                    "The breadcrumb trail is kept only in this window.\n\n"
                    "Close and discard it? Choose No to save a segment in Explore first.", parent=window):
                return
        closing = True
        explore_controls.shutdown()
        close_nearby_picker()
        request_stop()
        for widget in editable:
            widget.configure(state="disabled")
        if stop_markers():
            finish_close()
        else:
            closing = False
            restore_editing()

    def display_pose(point, bearing=None, *, sampled_at=None, acquired=None,
                     source="existing-idle-reader", fill_entered=True):
        nonlocal last_pose, last_y, displayed_acquired, displayed_stamp, displayed_source, pose_unavailable_reason
        last_pose = (point["x"], point["z"], bearing if bearing is not None else last_pose[2] if last_pose else 0)
        last_y = point["y"]
        displayed_acquired = acquired if type(acquired) in (int,float) and math.isfinite(acquired) else None
        displayed_stamp = sampled_at
        if displayed_stamp is None and displayed_acquired is not None:
            from datetime import timedelta
            displayed_stamp = (datetime.now(timezone.utc)-timedelta(
                seconds=time.monotonic()-displayed_acquired)).isoformat()
        displayed_source, pose_unavailable_reason = source, None
        pose_text.set(f"X {point['x']:.3f}   Y {point['y']:.3f}   Z {point['z']:.3f}   Facing {last_pose[2]:.2f}°")
        if fill_entered and not x.get() and not z.get():
            x.set(f"{point['x']:.6f}")
            z.set(f"{point['z']:.6f}")

    def read_beacon_pose_display():
        nonlocal beacon_pose_token, beacon_pose_available, beacon_pose_stamp, beacon_display_active, next_beacon_pose_at, last_pose, last_y
        nonlocal exploration_sample, beacon_latest_error, marker_anchor_y
        beacon_display_active = True
        if time.monotonic() < next_beacon_pose_at:
            return
        next_beacon_pose_at = time.monotonic() + .2
        try:
            path = getattr(markers, "pose_path", None)
            if path is None:
                raise ValueError("waiting for the owned beacon reader")
            from scripts.waypoint_beacon_pose import read_pose
            last_sequence = beacon_pose_token[1] if beacon_pose_token and beacon_pose_token[0] == str(path) else None
            pose = read_pose(path, adapter.target, adapter.binding["runtimeIdentity"]["unitKey"], last_sequence=last_sequence)
            beacon_latest_error = None
            token = (str(path), pose["sequence"], pose["acquiredMonotonic"])
            if beacon_pose_token is None or beacon_pose_token[0] != str(path):
                marker_anchor_y = pose["position"]["y"]
            if token != beacon_pose_token or not beacon_pose_available:
                exploration_sample = pose["acquiredMonotonic"]
                explore_controls.on_pose(pose)
                display_pose(pose["position"], pose["bearing"], sampled_at=pose["sampledAtUtc"],
                    acquired=pose["acquiredMonotonic"], source="owned-beacon-reader", fill_entered=False)
                beacon_pose_token = token
                beacon_pose_stamp = pose["sampledAtUtc"]
                beacon_pose_available = True
                redraw()
            live_pose_option.configure(text="Live pose (beacons)")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if str(exc) != beacon_latest_error:
                beacon_latest_error = str(exc)
                diagnostics.warning("Beacon pose feedback unavailable", reason=str(exc),
                                    poseFile=str(getattr(markers, "pose_path", None)))
            exploration_sample = None
            explore_controls.unavailable(str(exc))
            beacon_pose_available = False
            last_pose = last_y = None
            stamp = "; last sample " + beacon_pose_stamp if beacon_pose_stamp else ""
            reason = ("waiting for the owned beacon reader" if isinstance(exc, FileNotFoundError)
                      else (exc.strerror or str(exc)) if isinstance(exc, OSError) else str(exc))
            pose_text.set("Position unavailable (beacons): " + reason + stamp)
            set_pose_unavailable(reason)
            live_pose_option.configure(text="Live pose (waiting)")
            redraw()

    # The GUI owns all mutable state. The console only exchanges bounded JSON
    # requests; dispatch and completion run on this same Tk thread.
    from scripts.waypoint_cli_protocol import LocalSessionServer, Deferred, CliError

    def cli_ok(data=None, status="completed"):
        return {"ok": True, "status": status, "data": data, "target": deepcopy(getattr(adapter, "target", None))}

    def cli_error(code, message, *, exit_code=1, hint=None, recorded=False, command=None, request_id=None):
        if not recorded:
            diagnostics.warning("CLI request refused", code=code, reason=message,
                                command=command, requestId=request_id)
        return {"ok": False, "status": "failed", "target": deepcopy(getattr(adapter, "target", None)), "error": {
            "code": code, "message": message, "exitCode": exit_code, "hint": hint}}

    def cli_document():
        return route_document() if table.get_children() else {"waypoints": []}

    def zone_state():
        context, age = current_zone_context, None
        if context is not None:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(context["observedAtUtc"].replace("Z", "+00:00"))).total_seconds()
        valid = (context is not None and adapter is not None and context["target"] == adapter.target
                 and age is not None and -.1 <= age <= 30 and zone_error is None)
        return dict(context=deepcopy(context) if valid else None, currentAgeSeconds=age,
                    status="available-candidate" if valid else "unavailable", reason=zone_error,
                    qualification="Zone ID candidate only; matching is not world/instance or terrain proof.")

    def zone_comparison(document=None):
        from scripts.waypoint_route_library import compare_context
        return compare_context((document if document is not None else route_metadata).get("routeContext"), zone_state()["context"])

    def route_heights(document=None):
        from scripts.waypoint_measurements import document_measurements
        from scripts.waypoint_height_context import height_context
        document = cli_document() if document is None else document
        rows = document.get("waypoints", [])
        receipts = document_measurements(document)
        measured = [(i, r["position"]["y"]) for i,r in enumerate(receipts) if r is not None]
        result = []
        for i,row in enumerate(rows):
            receipt = receipts[i]
            y, kind = (receipt["position"]["y"], "measured") if receipt else (None, "unknown")
            if receipt is None and measured:
                nearest = min(measured, key=lambda pair: math.hypot(row[1]-rows[pair[0]][1], row[2]-rows[pair[0]][2]))
                y, kind = nearest[1], "nearest-measured-estimate"
            elif receipt is None and (marker_anchor_y if markers.running() else last_y) is not None:
                y, kind = marker_anchor_y if markers.running() else last_y, "startup-player-estimate"
            context = height_context(dict(xyz={"y":y}, displayHeightKind=kind), last_y)
            result.append(dict(number=i+1, height=y, **context))
        return result

    def update_context_text():
        zone = zone_state()
        current = (zone["context"] or {}).get("zoneName") or (zone["context"] or {}).get("zoneIdCandidate") or "unknown"
        tagged = route_metadata.get("routeContext")
        saved = (tagged or {}).get("zoneName") or (tagged or {}).get("zoneIdCandidate") or "unknown / legacy"
        text = f"Zone candidate: {current} · Route: {saved} · {zone_comparison()}"
        selected = table.selection()
        if len(selected) == 1:
            heights = route_heights()
            index = table.index(selected[0])
            if index < len(heights): text += " · " + heights[index]["label"]
        context_text.set(text)

    def cli_display_status():
        path = getattr(markers, "status_path", None)
        if path is None or not markers.running(): return None
        try:
            if path.stat().st_size > 262144: return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if (data.get("version") != 1 or adapter is None or data.get("target") != adapter.target
                    or data.get("sessionId") != markers.pose_path.stem
                    or not 0 <= time.monotonic()-data["sampledMonotonic"] <= 1): return None
            return data
        except (OSError, ValueError, KeyError, TypeError): return None

    def cli_pose():
        if live_pose.get() and adapter is not None and markers.running() and not markers.stop_requested:
            try:
                from scripts.waypoint_beacon_pose import read_pose
                pose_path=getattr(markers,"pose_path",None)
                if pose_path is None: raise ValueError("waiting for the owned beacon reader")
                pose=read_pose(pose_path, adapter.target, adapter.binding["runtimeIdentity"]["unitKey"])
                return dict(pose,sampleStatus="fresh",liveEnabled=True,updating=False,
                            ageSeconds=time.monotonic()-pose["acquiredMonotonic"],freshForSeconds=1)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                return dict(status="unavailable",sampleStatus="unavailable",reason=str(exc),source="owned-beacon-reader",
                    liveEnabled=True,updating=False,
                    ageSeconds=time.monotonic()-displayed_acquired if displayed_acquired is not None else None,
                    sampledAtUtc=displayed_stamp,freshForSeconds=1,position=None,bearing=None,
                    qualification="Last valid sample time is historical only; the owned reader has no current pose.")
        age = time.monotonic() - displayed_acquired if displayed_acquired is not None else None
        limit = 1 if displayed_source=="owned-beacon-reader" else 2
        fresh=last_pose is not None and adapter is not None and live_pose.get() and not identity_unavailable and age is not None and 0<=age<=limit
        reason=("RIFT is not connected" if adapter is None else "Live pose paused" if not live_pose.get()
                else pose_unavailable_reason if last_pose is None else "Cached sample; refresh for current pose" if not fresh else None)
        return {"status": "fresh" if fresh else "unavailable", "sampleStatus":"fresh" if fresh else "cached" if last_pose else "unavailable",
                "source": displayed_source, "ageSeconds": age, "sampledAtUtc":displayed_stamp,"freshForSeconds":limit,
                "liveEnabled":live_pose.get(),"updating":observing or busy,"reason":reason,
                "position": dict(x=last_pose[0], y=last_y, z=last_pose[1]) if last_pose else None,
                "bearing": last_pose[2] if last_pose else None,
                "qualification": "Native pose candidate for display; acquisition freshness is separate from action admission. Cached or paused samples must not be used for control."}

    def set_pose_unavailable(reason):
        nonlocal pose_unavailable_reason
        pose_unavailable_reason=str(reason)
        pose_text.set("Position unavailable — "+str(reason))

    def change_live_pose():
        nonlocal next_live_at
        if live_pose.get(): next_live_at=0
        update_header_state()

    def cli_controls():
        listener=foreground_stop is not None
        return dict(stop_context,stopLatched=stop.is_set(),ownedActionActive=busy,recording=recording,
            inputReleaseFault=bool(getattr(adapter, "_continuous_input_release_fault", False)),
            inputRecovery=deepcopy(getattr(adapter, "_continuous_move_recovery", None)),
            f8="active" if listener and getattr(foreground_stop,"registered",False) else "unavailable" if listener else "inactive",
            qualification="STOP cancels this helper's work and waits for owned input release. Key release and observed stationary pose are separate evidence; other game movement is not cancelled.")

    def update_header_state():
        nonlocal replay_pose_key
        pose=cli_pose()
        age=pose.get("ageSeconds")
        age_text=f"{max(0,age):.1f}s" if age is not None else "age unknown"
        sample=pose.get("sampleStatus","unavailable")
        badge=(f"Fresh · {age_text}" if sample=="fresh" else f"Cached · {'paused' if not live_pose.get() else age_text}"
               if sample=="cached" else "Pose unavailable")
        pose_badge.set(badge+(" · reading" if pose.get("updating") else ""))
        pose_badge_label.configure(foreground=PALETTE["mint"] if sample=="fresh" else PALETTE["gold"] if sample=="cached" else PALETTE["muted"])
        controls=cli_controls()
        stop_hint.set("F8 active · Esc in app" if controls["f8"]=="active" else "F8 unavailable · use STOP" if controls["f8"]=="unavailable" else "F8 inactive · Esc in app")
        stop_button.configure(text="STOP requested…" if stop.is_set() and busy else "STOP")
        target=getattr(adapter,"target",None)
        pid=target.get("processId",getattr(adapter,"pid",args.physical_pid)) if target else None
        connection_text.set(f"{args.expected_host} / PID {pid}" if pid is not None else f"{args.expected_host} / Waiting for RIFT")
        pose_key=(pose.get("status"),pose.get("liveEnabled"))
        if pose_key!=replay_pose_key:
            replay_pose_key=pose_key
            update_replay_status()

    def cli_preview_status():
        from scripts.waypoint_map import fit_route_status
        available=last_pose is not None and map_view is not None
        pose=cli_pose()
        age=pose.get("ageSeconds")
        fresh=available and pose.get("sampleStatus")=="fresh"
        points=selected_points(True)
        fit=fit_route_status(*last_pose[:2],points) if available and points else None
        hidden=[dict(number=p["number"],name=table.item(p["identifier"],"values")[0])
                for p in map_render.get("offscreen",[]) if table.exists(p["identifier"])]
        return dict(radius=map_radius,allowedRadii=list(ZOOM_RADII),poseAvailable=available,
            clickToMoveEnabled=click_move.get(),
            canvasSize={"width":map_view.width,"height":map_view.height} if available else None,
            poseStatus="fresh" if fresh else "cached" if available else "unavailable",poseAgeSeconds=age,
            fitAvailable=available and bool(points),fitLimited=bool(fit and fit["capped"]),
            requiredRadius=fit["required_radius"] if fit else None,
            routeCount=len(points),selected=[table.index(i)+1 for i in table.selection()],
            visibleCount=map_render.get("visible_count",0) if available else 0,
            offscreenCount=map_render.get("offscreen_count",0) if available else None,offscreenPoints=hidden,
            terrainAvailable=False,inputSent=False,qualification="Player-relative cached reference only; no terrain, obstacle clearance or movement authority. Adding a point rechecks live pose.")

    def cli_radar_status():
        observed = None
        try:
            path = Path(explore_controls.extra_settings["statusPath"])
            if path.stat().st_size <= 16384:
                value = json.loads(path.read_text(encoding="utf-8"))
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(value["sampledAtUtc"])).total_seconds()
                if (0 <= age <= 1 and adapter is not None and value.get("target") == adapter.target
                        and markers.running() and not markers.stop_requested):
                    observed = value
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return dict(enabled=explore_controls.enabled.get(), unlocked=explore_controls.unlocked.get(),
                    range=int(explore_controls.radius.get()), opacity=round(explore_controls.opacity.get()),
                    requestedPosition=explore_controls.extra_settings.get("position"),
                    observed=observed, readerRunning=markers.running(),
                    qualification="Observed visibility is unavailable when the presenter feedback is stale.")

    def cli_beacon_status():
        display = cli_display_status()
        visibility = beacon_display_status(markers.running(), markers.running() and markers.stop_requested, display)
        if marker_restart_pending:
            visibility = dict(state="restarting", reason="Restarting reader for target inclusion", visible=None)
        return dict(readerRunning=markers.running(), closing=markers.running() and markers.stop_requested,
                    size=round(beacon_size.get()) / 100, opacity=round(beacon_opacity.get()),
                    labels=beacon_labels.get(), target=target_beacon.get(), guide=landmark_guide.get(),
                    appliedTarget=marker_running_target if markers.running() and not markers.stop_requested else None,
                    restartPending=marker_restart_pending, visibility=visibility,
                    reportFile=str(markers.output) if getattr(markers, "output", None) else None,
                    pose=cli_pose(), display=display, qualification="Reader state; visible means a fresh allowed overlay window, not terrain/occlusion or individual point visibility proof.")

    def capture_readiness():
        from scripts.waypoint_measurements import parse_projection_route, document_measurements
        document = cli_document()
        count = len(document.get("waypoints", []))
        try:
            parse_projection_route(document)
            measured=count
            measurement_ready=True
            measurement_reason="Measured route ready for capture"
        except (ValueError, TypeError, KeyError):
            try: measured = sum(r is not None for r in document_measurements(document))
            except (ValueError, TypeError, KeyError): measured = 0
            measurement_ready=False
            measurement_reason = ("Load a measured route before capture" if not count else
                      f"Capture needs measured XYZ for all points ({measured}/{count}); estimated beacons still work")
        reason=("Helper is closing" if closing else "Another action is active" if busy or cli_action is not None else
                "Connect to RIFT before capture" if adapter is None else
                "Apply or Reset Edit waypoint fields before capture" if draft_pending() else
                measurement_reason)
        return dict(ready=measurement_ready and not (closing or busy or cli_action is not None or adapter is None or draft_pending()),
                    reason=reason,measured=measured,total=count,
                    measurementReady=measurement_ready,measurementReason=measurement_reason)

    def cli_view_status():
        def available(value):
            try: return bool(value and Path(value).is_file())
            except OSError: return False
        return dict(options=dict(bringForward=view_bring_forward.get(), nearbyUnits=view_include_units.get()),
                    image=saved_view, rerun=saved_rerun, nearbySample=saved_unit_sample,
                    imageAvailable=available(saved_view), rerunAvailable=available(saved_rerun),
                    nearbyAvailable=available(saved_unit_sample), lastCaptureState=last_capture_state,
                    lastCaptureError=last_capture_error, readiness=capture_readiness())

    def update_scene_state(*,force=False):
        nonlocal next_scene_at
        if workflow.select() != str(scene_tab) or not force and time.monotonic() < next_scene_at: return
        next_scene_at = time.monotonic()+.25
        view = cli_view_status()
        idle = not busy and not closing and cli_action is None
        open_view_button.configure(state="normal" if idle and view["imageAvailable"] else "disabled")
        open_3d_button.configure(state="normal" if idle and view["rerunAvailable"] else "disabled")
        save_view_button.configure(state="normal" if view["readiness"]["ready"] else "disabled")
        if last_capture_state == "none":
            capture_hint.set("No capture yet · Save view or Open saved…" if view["readiness"]["ready"] else view["readiness"]["reason"])
        else:
            text = f"Last scene: image {'ready' if view['imageAvailable'] else 'unavailable'} · 3D {'ready' if view['rerunAvailable'] else 'unavailable'}"
            if last_capture_state == "failed": text += " · latest capture failed; previous assets retained"
            if not view["readiness"]["ready"]:
                text += "\n"+view["readiness"]["reason"]
            capture_hint.set(text)
        beacon = cli_beacon_status()
        hint = beacon["visibility"]["reason"]
        if marker_restart_pending: hint = "Restarting reader · appearance and radar retained"
        elif markers.running(): hint += " · Hide also stops the shared radar/pose reader"
        elif adapter is None: hint = "Connect RIFT before showing beacons"
        elif zone_comparison() == "mismatch": hint = "Load a matching-zone route before showing beacons"
        if len(table.selection()) != 1: hint += " · Select one point for guidance"
        if target_change_blocked(): hint += " · Stop guide/trail to change target"
        beacon_hint.set(hint)
        marker_button.configure(style="Ghost.TButton" if markers.running() else "Primary.TButton",
            state="normal" if idle and not marker_restart_pending and (not markers.running() or not markers.stop_requested)
            and (markers.running() or adapter is not None and zone_comparison() != "mismatch") else "disabled")

    replay_cache = {"key": None, "value": None}
    replay_pose_key = None

    def cli_playback_status():
        from scripts.waypoint_replay_readiness import replay_readiness
        pose = cli_pose()
        identity = getattr(adapter, "binding", None)
        identity = identity.get("runtimeIdentity") if isinstance(identity, dict) else None
        reason = "Another action is active" if busy or cli_action is not None else "Helper is closing" if closing else None
        if reason is None and draft_pending():
            reason = "Apply or Reset Edit waypoint fields first"
        if reason is None and pose.get("status") != "fresh":
            reason = "Waiting for a fresh player pose"
        if reason is None and route_metadata.get("routeContext") is not None:
            comparison = zone_comparison()
            if comparison != "matching":
                reason = "Route zone candidate differs" if comparison == "mismatch" else "Refresh zone context before playback"
        try:
            stamp = checkpoint.stat()
            checkpoint_key = (str(checkpoint), stamp.st_mtime_ns, stamp.st_size)
        except OSError:
            checkpoint_key = (str(checkpoint), None)
        position = pose.get("position")
        key = (route_revision, repr(identity), repr(position), reason, checkpoint_key)
        if key != replay_cache["key"]:
            try:
                readiness = replay_readiness(cli_document(), identity, position, checkpoint, reason, approach_start=True)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                readiness = {action: dict(ready=False, reason=str(exc), direction=None, nextIndex=None,
                                         nextName=None, remainingDistance=None) for action in ("forward", "reverse", "resume")}
            replay_cache.update(key=key, value=readiness)
        return dict(active=playback_active, progress=deepcopy(playback_view), checkpoint=str(checkpoint),
                    pointCount=len(table.get_children()),
                    faceWaypoints=True, readiness=deepcopy(replay_cache["value"]),
                    qualification="Read-only readiness from the existing pose; execution rechecks fresh pose, ownership and zone before input.")

    def update_replay_status():
        from textwrap import shorten
        snapshot = cli_playback_status()
        count = len(table.get_children())
        cursor = snapshot["readiness"]["resume"]
        for action, button in (("forward", forward_button), ("reverse", reverse_button), ("resume", resume_button)):
            item = snapshot["readiness"][action]
            detail = (f"Ready · {item['remainingDistance']:.2f}u remaining" if item["ready"] else item["reason"])
            if action in ("forward","reverse"):
                endpoint=item.get("startPointNumber") or (1 if action=="forward" else count)
                label=item.get("startName") or (table.item(table.get_children()[endpoint-1],"values")[0] if count and endpoint<=count else "No waypoint")
                title=f"{'Start' if action=='forward' else 'End'} #{endpoint} · {shorten(label,width=18,placeholder='…')}" if count else "No waypoints"
                full=f"Play {action.title()} starts a new run at {'Start' if action=='forward' else 'End'} #{endpoint}: {label}.\n{detail}\nA new admitted run replaces saved progress. Each leg faces before walking."
                if item.get("approachRequired"):
                    detail=f"Walk to start: {item['approachDistance']:.2f}u · then follow route"
                    full += "\nApproaches a nearby start on clear ground before following the route; STOP covers both."
                elif item.get("endpointDistance") is not None:
                    detail=f"{item['endpointDistance']:.2f}u away · need ≤ 0.30u"
            elif item.get("complete"):
                title=f"{item['direction'].title()} · Complete {count}/{count}"
                detail="Choose Play for a new run"
                full=f"The saved {item['direction']} run has confirmed all {count} waypoints. Resume sends no further input; choose Play Forward or Play Reverse at its endpoint to start a new run."
            elif item.get("nextPointNumber") is not None:
                title=f"{item['direction'].title()} → #{item['nextPointNumber']} · {shorten(item.get('nextName') or '',width=18,placeholder='…')}"
                full=f"Resume the saved {item['direction']} run at original waypoint #{item['nextPointNumber']}: {item.get('nextName')}.\n{item.get('completedCount',0)}/{count} confirmed. {detail}\nResume retains the saved direction and requires a position near the unfinished leg."
            else:
                title="No saved run" if item.get("reason")=="no saved playback progress" else "Saved run unavailable"
                full=f"{title}: {detail}. Start with Play Forward or Play Reverse at its endpoint."
            replay_hints[action].set(title+"\n"+shorten(detail,width=62,placeholder="…"))
            replay_full_hints[action]=full
            button.configure(state="normal" if item["ready"] else "disabled",
                             style="TButton")
            replay_hint_labels[("forward","reverse","resume").index(action)].configure(
                foreground=PALETTE["mint"] if item["ready"] else PALETTE["gold"] if item.get("complete") else PALETTE["muted"])
        view = playback_view if playback_active else cursor
        index = view.get("nextIndex") if view else None
        replay_progress.configure(maximum=max(1, count), value=min(count, index or 0))
        if not recording:
            direction=(view or {}).get("direction")
            if playback_active and direction:
                number=(index or 0)+1 if direction=="forward" else count-(index or 0)
                next_text=f" · next #{number}" if 1<=number<=count else " · confirming completion"
                progress_text.set(f"Playing {direction} · {index or 0}/{count} confirmed"+next_text)
            elif cursor.get("complete"):
                progress_text.set(f"{cursor['direction'].title()} complete · {count}/{count} confirmed. Play Forward starts at #1; Play Reverse starts at #{count}.")
            elif cursor.get("nextPointNumber") is not None:
                progress_text.set(f"Saved {cursor['direction']} · {cursor.get('completedCount',0)}/{count} confirmed · next #{cursor['nextPointNumber']} {shorten(cursor.get('nextName') or '',width=44,placeholder='…')}")
            else:
                progress_text.set("No saved playback progress. Play Forward starts at #1; Play Reverse starts at the last point." if cursor.get("reason")=="no saved playback progress" else "Saved progress unavailable: "+cursor["reason"])

    def cli_snapshot():
        return dict(host=args.expected_host, target=deepcopy(getattr(adapter, "target", None)),
                    diagnostics=diagnostics.status(),
                    app={"name": APP_NAME, "version": APP_VERSION,
                         "tab":next((key for key,tab in (("replay",replay_tab),("edit",edit_tab),("scene",scene_tab),
                            ("explore",explore_tab),("library",library_tab),("activity",activity_tab)) if workflow.select()==str(tab)),None),
                         "visible": window.state() not in ("withdrawn", "iconic"), "windowState": window.state(),
                         "busy": busy, "closing": closing, "state": state.get()},
                    route={"file": str(route_path) if route_path else None, "dirty": route_dirty,
                           "revision": route_revision, "count": len(table.get_children()),
                           "selected": [table.index(i)+1 for i in table.selection()],"editDraft":edit_draft_status()},
                    zone=zone_state(), routeContext=deepcopy(route_metadata.get("routeContext")),
                    contextComparison=zone_comparison(), heights=route_heights(),
                    pose=cli_pose(), controls=cli_controls(), radar=cli_radar_status(), beacons=cli_beacon_status(),
                    view=cli_view_status(),
                    guidance=explore_controls.navigation_state(), trail=cli_trail_status(),
                    routeLibrary=library_view_state(),
                    activity=activity_controls.view_state(),
                    preview=cli_preview_status(),
                    recording={"active": recording, "progress": recording_progress},
                    playback=cli_playback_status(),
                    survival=dict(survival_runtime.status(), enabled=survival_enabled.get()),
                    movementEngine="continuous" if continuous_travel.get() else "pulse",
                    clickMovementEngine="continuous",
                    activeRequestId=cli_action["id"] if cli_action else None,
                    recentResults=deepcopy(cli_recent), inputSent=False)

    def diagnostics_report():
        try:
            snapshot = cli_snapshot()
        except Exception as exc:
            diagnostics.exception("Unable to collect complete diagnostic state", exc=exc)
            snapshot = dict(app=dict(state=state.get(), snapshotError=str(exc)),
                            target=deepcopy(getattr(adapter, "target", None)),
                            route=dict(file=str(route_path) if route_path else None, dirty=route_dirty))
        return diagnostics.report(snapshot)

    def open_logs():
        try:
            if not diagnostics.directory.is_dir(): raise OSError("Log directory is unavailable")
            os.startfile(str(diagnostics.directory))
            diagnostics.info("Log directory opened")
            state.set("Log directory opened: " + str(diagnostics.directory))
            return dict(opened=True, directory=str(diagnostics.directory))
        except Exception as exc:
            diagnostics.exception("Unable to open log directory", exc=exc)
            state.set("Cannot open logs: " + str(exc))

    def copy_diagnostics():
        try:
            text = diagnostics_report()
            window.clipboard_clear()
            window.clipboard_append(text)
            window.update_idletasks()
            diagnostics.info("Diagnostics copied", characters=len(text))
            state.set(f"Diagnostics copied ({len(text):,} characters).")
            return dict(copied=True, characters=len(text), logFile=str(diagnostics.log_path))
        except Exception as exc:
            diagnostics.exception("Unable to copy diagnostics", exc=exc)
            state.set("Cannot copy diagnostics: " + str(exc))

    def cli_trail_status():
        snapshot = explore_controls.trail.snapshot()
        snapshot["segments"] = [dict(summary, identity=segment["identity"])
            for summary, segment in zip(explore_controls.trail.segment_summaries(), snapshot["segments"])]
        return snapshot

    def cli_file(value, *, fresh=False, overwrite=False):
        path = Path(value).absolute()
        if local_source_path(str(path)) is None:
            raise CliError("local-path-required", "Choose an absolute local disk path")
        if fresh and path.exists() and not overwrite:
            raise CliError("file-exists", f"File already exists: {path}", "Use --overwrite to replace it", 4)
        if fresh and not path.parent.is_dir():
            raise CliError("parent-unavailable", f"Parent directory does not exist: {path.parent}")
        return path

    def cli_wait(rid, callback):
        cli_waiters[rid] = callback
        return Deferred()

    def cli_begin(rid, operation, payload=None, *, command=None):
        nonlocal cli_action
        if busy or cli_action is not None or closing or nearby_picker is not None:
            raise CliError("busy", "Another action or dialog owns the helper", "Use status or stop", 4)
        if adapter is None and operation not in ("save", "target"):
            raise CliError("rift-unavailable", "Wait for a verified RIFT connection before starting", exit_code=3)
        job = {"id": rid, "command": command or operation, "operation": operation,
               "started": False, "finished": None, "recordedFile": None, "cancelled": False}
        cli_action = job
        if operation in ("go", "face", "face-bearing", "record", "map-go", "play", "resume", "survival-preflight") and markers.running():
            stop_markers()

        def advance():
            nonlocal cli_action
            if not job["started"]:
                if job["cancelled"]:
                    cli_action = None
                    return cli_error("cancelled", "Cancelled before starting", exit_code=130)
                if markers.running() and operation in ("go", "face", "face-bearing", "record", "map-go", "play", "resume", "survival-preflight"):
                    return None
                if not start(operation, payload, face_walk=True, check_route_zone=command not in ("move.to", "face")):
                    cli_action = None
                    return cli_error("start-refused", state.get(), exit_code=4)
                job["started"] = True
            if operation == "record" and job["finished"] is None and job.get("recordingObserved") and not record_stop.is_set():
                return cli_ok({"recording": True, "requestId": rid, "inputSent": False})
            if job["finished"] is None or busy:
                return None
            event = job["finished"]
            failure = event.get("failure") or job.get("editFailure")
            data = dict(operation=event["operation"], receipt=event.get("receipt"), failure=failure,
                        recordedFile=job.get("recordedFile"), state=state.get())
            if operation == "view": data.update(image=saved_view, rerun=saved_rerun)
            if operation == "zone" and not failure: data.update(zone_state())
            if operation == "survival-preflight" and not failure:
                data["result"] = deepcopy(event.get("result"))
                data["survival"] = deepcopy(event.get("result"))
            if operation in ("save", "target"):
                data.update(route=cli_snapshot()["route"], selected=[table.index(i)+1 for i in table.selection()])
                if job.get("change") is not None: data["change"] = job["change"]
            if operation=="refresh" and not failure:
                data=cli_pose()
            response = (cli_error("cancelled" if failure.get("status") == "stopped" else "operation-failed",
                                  failure["reason"], exit_code=130 if failure.get("status") == "stopped" else 1)
                        if failure else cli_ok(data))
            if failure:
                response["data"] = data
            cli_recent.append(dict(requestId=rid, command=job["command"], ok=not bool(failure),
                                   receipt=event.get("receipt"), failure=failure))
            del cli_recent[:-8]
            cli_action = None
            redraw()
            return response
        return cli_wait(rid, advance)

    def cli_dispatch(command, values, rid):
        nonlocal route_metadata, route_path, route_dirty, route_recovered, route_revision
        nonlocal playback_view, pending_progress_selection, checkpoint, cli_close_id, cli_record_output, map_radius
        nonlocal saved_view, saved_rerun, rerun_viewer
        nonlocal last_capture_state, last_capture_error
        try:
            if command.startswith("survival."):
                if command == "survival.status":
                    return cli_ok(dict(survival_runtime.status(), enabled=survival_enabled.get()))
                if busy or cli_action is not None or closing:
                    raise CliError("busy", "Wait for the active action", exit_code=4)
                if command == "survival.configure":
                    return cli_ok(configure_survival(values["profile"]))
                if command == "survival.set":
                    if values.get("enabled") not in ("on", "off"):
                        raise ValueError("enabled must be on or off")
                    survival_enabled.set(values["enabled"] == "on")
                    return cli_ok(dict(survival_runtime.status(), enabled=survival_enabled.get()))
                if command == "survival.preflight":
                    return cli_begin(rid, "survival-preflight", command=command)
                if command in ("survival.run", "survival.resume"):
                    if values.get("execute") is not True:
                        raise CliError("execute-required", "Survival route execution requires --execute", exit_code=2)
                    survival_enabled.set(True)
                    return cli_dispatch("playback.resume" if command.endswith("resume") else "playback.start", values, rid)
                raise ValueError("Unknown survival operation")
            if not command.endswith(".status") and command not in ("status", "route.list", "diagnostics.show", "diagnostics.events"):
                diagnostics.info("CLI request", command=command, requestId=rid)
            if command == "diagnostics.status": return cli_ok(dict(diagnostics.status(), activity=activity_controls.view_state()))
            if command == "diagnostics.events":
                return cli_ok(diagnostics.events(limit=values.get("limit",100),
                    level=values.get("level","all"),search=values.get("search","")))
            if command == "diagnostics.show":
                return cli_ok(dict(text=diagnostics_report(), **diagnostics.status()))
            if command == "diagnostics.copy":
                result = copy_diagnostics()
                if result is None: raise CliError("clipboard-unavailable", state.get())
                return cli_ok(result)
            if command == "diagnostics.open":
                result = open_logs()
                if result is None: raise CliError("log-directory-unavailable", state.get())
                return cli_ok(result)
            if command.startswith("preview."):
                if command == "preview.project":
                    if map_view is None:
                        raise CliError("preview-unavailable", "Refresh position before projecting a map destination", exit_code=3)
                    return cli_ok(dict(project_destination(values["canvas_x"], values["canvas_y"]),
                                       pose=cli_pose(), canvasSize={"width":map_view.width,"height":map_view.height}))
                if command == "preview.set":
                    radius=values.get("range")
                    if type(radius) not in (int,float) or radius not in ZOOM_RADII:
                        raise CliError("invalid-preview-range", "Preview range must be one of: " + ", ".join(map(str, ZOOM_RADII)), exit_code=2)
                    map_radius=int(radius)
                    redraw()
                elif command == "preview.fit":
                    if not fit_zoom():
                        raise CliError("preview-unavailable","A cached position and a route are needed to fit the preview",exit_code=3)
                elif command != "preview.status": raise CliError("unsupported-command",command,exit_code=2)
                return cli_ok(cli_preview_status())
            if command in ("pose.status","pose.set"):
                if command=="pose.set":
                    if values.get("live") not in ("on","off"):
                        raise CliError("invalid-live-pose","Live pose must be on or off",exit_code=2)
                    live_pose.set(values["live"]=="on")
                    change_live_pose()
                return cli_ok(cli_pose())
            if command == "move.mode":
                if busy or closing or cli_action is not None:
                    raise CliError("busy", "Wait for movement to finish before changing its engine", exit_code=4)
                if values.get("engine") not in ("continuous", "pulse"):
                    raise CliError("invalid-movement-engine", "Engine must be continuous or pulse", exit_code=2)
                continuous_travel.set(values["engine"] == "continuous")
                return cli_ok({"movementEngine": values["engine"], "inputSent": False})
            if command == "zone.status": return cli_ok(zone_state())
            if command == "zone.refresh": return cli_begin(rid, "zone", command=command)
            if command == "route.context":
                return cli_ok(dict(routeContext=deepcopy(route_metadata.get("routeContext")),
                    currentContext=zone_state()["context"], comparison=zone_comparison()))
            if command == "route.tag-zone":
                if busy or cli_action is not None: raise CliError("busy", "Wait for the active action", exit_code=4)
                if not table.get_children(): raise CliError("empty-route", "Add a waypoint before tagging its zone", exit_code=4)
                pending = cli_begin(rid, "zone", command=command)
                advance = cli_waiters[rid]
                def tagged():
                    nonlocal route_metadata, route_dirty, route_revision
                    response = advance()
                    if response is None or not response.get("ok"): return response
                    context = zone_state()["context"]
                    if context is None: return cli_error("zone-unavailable", "Wait for a current zone observation", exit_code=3)
                    remember_edit()
                    route_metadata["routeContext"] = context
                    route_dirty = True
                    route_revision += 1
                    update_route_status()
                    update_context_text()
                    return cli_ok(dict(routeContext=context, currentContext=context, comparison="matching"))
                cli_waiters[rid] = tagged
                return pending
            if command.startswith("library."):
                from scripts import waypoint_route_library as library
                directory = ROOT / "artifacts" / "waypoint-routes"
                if command == "library.list":
                    status = values.get("zone", "all")
                    all_rows = library.list_routes(zone_state()["context"], library_dir=directory)
                    rows = library.filter_routes(all_rows, None if status == "all" else status, search=values.get("search"))
                    return cli_ok(dict(routes=rows, totalCount=len(all_rows), shownCount=len(rows),
                        search=values.get("search") or "", filter=status, selectedId=library_selected_id(),
                        directory=str(directory), zone=zone_state(), view=library_view_state()))
                if command in ("library.show", "library.select", "library.load"):
                    rows = library.list_routes(zone_state()["context"], library_dir=directory)
                    requested = values["route_id"]
                    row = next((r for r in rows if r["id"].casefold() == requested.casefold()), None)
                    if row is None: raise CliError("library-entry-unavailable", "No library entry with that ID", "Use library list", 3)
                    if command == "library.select":
                        refresh_library(select_id=row["id"], clear_filters=True)
                        return cli_ok(dict(routeId=row["id"], row=row, view=library_view_state()))
                    document = library.load_route(requested, library_dir=directory)
                    if command == "library.show":
                        return cli_ok(dict(routeId=row["id"], file=row["path"], row=row, document=document,
                            contextComparison=zone_comparison(document), heights=route_heights(document)))
                if busy or cli_action is not None or closing: raise CliError("busy", "Wait for the active action", exit_code=4)
                if command == "library.load":
                    return cli_dispatch("route.load", dict(file=row["path"], discard=values.get("discard",False)), rid)
                if command == "library.save":
                    if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset fields before saving a library copy", exit_code=4)
                    route_id = library.save_route(route_document(), values["name"], values.get("route_id"),
                        overwrite=values.get("overwrite",False), library_dir=directory)
                elif command == "library.import":
                    source = cli_file(values["file"])
                    prepared_document(library._read_document(source))
                    route_id = library.import_route(source, values.get("name"), values.get("route_id"),
                        overwrite=values.get("overwrite",False), library_dir=directory)
                else: raise CliError("unsupported-command", command, exit_code=2)
                document = library.load_route(route_id, library_dir=directory)
                saved_row = next(r for r in library.list_routes(zone_state()["context"], library_dir=directory)
                                 if r["id"].casefold() == route_id.casefold())
                if command == "library.save" and route_path is not None and route_path.absolute() == Path(saved_row["path"]):
                    route_metadata["routeName"] = document["routeName"]
                    route_revision += 1
                    mark_saved(route_path)
                    cache_route(document,"Library route saved: "+document["routeName"])
                refresh_library(select_id=saved_row["id"], clear_filters=True)
                return cli_ok(dict(routeId=saved_row["id"], name=saved_row["name"], file=saved_row["path"],
                                   row=saved_row, routeContext=document.get("routeContext")))
            if command in ("status", "doctor"):
                data = cli_snapshot()
                if command == "doctor":
                    data["ready"] = adapter is not None and data["pose"]["status"] == "fresh"
                    data["nextSteps"] = (["RIFT/pose is ready. Movement still requires --execute and its normal foreground checks."]
                        if data["ready"] else ["Wait for RIFT connection; use beacons show for continuous shared pose or wait for idle refresh.",
                                               "If several RIFT clients exist, reopen with app open --pid PID."])
                return cli_ok(data)
            if command == "capabilities":
                from scripts.waypoints_cli import build_parser
                parser = build_parser()
                def operations(p):
                    found = set()
                    op = p.get_default("operation")
                    if op: found.add(op)
                    for action in p._actions:
                        if isinstance(action, argparse._SubParsersAction):
                            for child in action.choices.values(): found.update(operations(child))
                    return found
                return cli_ok(dict(operations=sorted(operations(parser)), version=1,
                                   units={"coordinates": "world units", "bearing": "degrees", "opacity": "percent",
                                          "radarPosition": "physical pixels relative to game client", "indices": "one-based"}))
            if command == "stop":
                requested = values.get("requestId")
                if requested and (cli_action is None or cli_action["id"] != requested):
                    # Ctrl+C can arrive before its movement request is admitted.
                    # Retire that ID without cancelling somebody else's action.
                    cli_cancelled_requests.add(requested)
                    return cli_ok({"requestId": requested, "activeRequestMatched": False,
                                   "queuedRequestRetired": True,
                                   "qualification": "No matching active action; this request ID cannot start later. Other actions were not cancelled."})
                request_stop()
                def stopped():
                    if busy or foreground_stop is not None or markers.running(): return None
                    return cli_ok(dict(cli_controls(),ownedActionEnded=True))
                return cli_wait(rid, stopped)
            if command == "app.show":
                if values.get("tab") is not None:
                    tabs = dict(replay=replay_tab,edit=edit_tab,scene=scene_tab,explore=explore_tab,library=library_tab,activity=activity_tab)
                    if values["tab"] not in tabs: raise CliError("unknown-tab", "Choose replay, edit, scene, explore, library or activity", exit_code=2)
                    workflow.select(tabs[values["tab"]])
                window.deiconify()
                window.lift()
                return cli_ok({"visible": True, "windowState": window.state(), "tab": values.get("tab")})
            if command == "app.hide":
                window.withdraw()
                return cli_ok({"visible": False, "windowState": window.state()})
            if command == "app.close":
                if draft_pending() and not values.get("discard"):
                    raise CliError("unapplied-edit", "Apply or Reset fields before closing", "Or use app close --discard", 4)
                if values.get("discard"): reset_fields()
                if route_dirty and not values.get("discard"):
                    raise CliError("unsaved-route", "The route has unsaved changes", "Save with route save FILE or close --discard", 4)
                if explore_controls.trail.snapshot()["pointCount"] and not values.get("discard"):
                    raise CliError("retained-trail", "The window contains a retained breadcrumb trail",
                                   "Save segments with trail save FILE; then use app close --discard or trail clear --discard", 4)
                if values.get("discard"): route_dirty = False
                cli_close_id = rid
                close(discard_trail=bool(values.get("discard")))
                return Deferred()
            if command in ("move.to", "move.pick", "face", "route.run", "playback.start", "playback.resume", "record.start"):
                if rid in cli_cancelled_requests:
                    cli_cancelled_requests.discard(rid)
                    return cli_error("cancelled-by-stop", "This request was cancelled before admission", exit_code=130)
                # STOP also retires older mailbox work that has not yet started.
                if (cli_server.path / "requests" / (rid+".json")).stat().st_mtime <= cli_stop_at:
                    return cli_error("cancelled-by-stop", "This request was queued before STOP; send a new explicit command", exit_code=130)
            read_only = command.endswith(".status") or command in ("route.list", "route.validate", "trail.list", "diagnostics.show")
            passive = command.startswith(("radar.", "beacons.", "guide.", "trail."))
            if closing or (busy or cli_action is not None) and not (read_only or passive or command in ("record.stop", "record.cancel")):
                raise CliError("busy", "The helper is busy", "Use status or stop", 4)
            if command=="pose.refresh": return cli_begin(rid,"refresh",command=command)
            if command in ("guide.start", "trail.start"):
                if busy or cli_action is not None:
                    raise CliError("busy", "Wait for the active action before starting passive exploration", exit_code=4)
                block_reason = exploration_block_reason("guide" if command == "guide.start" else "trail")
                if block_reason:
                    raise CliError("exploration-unavailable", block_reason, exit_code=4)
                if command == "guide.start":
                    explore_controls.validate_guidance(direction=values.get("direction", "forward"),
                        start_index=values.get("from_point", 1 if values.get("direction", "forward") == "forward" else len(table.get_children()))-1,
                        radius=values.get("radius"))
                ensure_exploration_feed()
                if not markers.running() or markers.stop_requested:
                    raise CliError("reader-unavailable", state.get(), exit_code=3)
                try:
                    explore_controls._owner()
                except ValueError:
                    pose_deadline = time.monotonic() + 4
                    def ready():
                        if not markers.running() or markers.stop_requested or closing:
                            return cli_error("reader-unavailable", "The owned beacon reader ended", exit_code=3)
                        if time.monotonic() >= pose_deadline:
                            return cli_error("pose-unavailable", "No fresh exploration pose; start was not applied",
                                exit_code=3, hint="Focus RIFT or Waypoints, wait for Live pose, then retry explicitly")
                        try: explore_controls._owner()
                        except ValueError: return None
                        return cli_dispatch(command, values, rid)
                    return cli_wait(rid, ready)
            if command.startswith("route."):
                if values.get("revision") is not None and values["revision"] != route_revision:
                    raise CliError("route-changed", "Route revision changed", "Read route list and retry with its revision", 4)
                if command in ("route.list", "route.validate"):
                    document = cli_document()
                    if command == "route.validate":
                        prepared_document(document)
                    from scripts.waypoint_measurements import document_measurements
                    measured = sum(r is not None for r in document_measurements(document))
                    return cli_ok(dict(document=document, file=str(route_path) if route_path else None,
                        dirty=route_dirty, revision=route_revision,
                        selected=[table.index(i)+1 for i in table.selection()], editDraft=edit_draft_status(),
                        measuredCount=measured, estimatedCount=len(document["waypoints"])-measured,
                        heights=route_heights(document), routeContext=document.get("routeContext"), contextComparison=zone_comparison(document),
                        preview=cli_preview_status(),
                        points=[dict(number=i+1, name=r[0], x=float(r[1]), z=float(r[2])) for i,r in enumerate(selected_points(True))],
                        qualification="Route structure only; terrain, obstacle clearance and playback admission remain live checks."))
                if command in ("route.load", "route.new"):
                    if draft_pending() and not values.get("discard"):
                        raise CliError("unapplied-edit", "Apply or Reset fields first", "Use --discard to abandon the draft", 4)
                    if values.get("discard"): reset_fields()
                    if route_dirty and not values.get("discard"):
                        raise CliError("unsaved-route", "The route has unsaved changes", "Save first or use --discard", 4)
                    if command == "route.load":
                        path = cli_file(values["file"])
                        document = prepared_document(json.loads(path.read_text(encoding="utf-8-sig")))
                        progress = select_progress(document)
                        show_document(document)
                        edit_history.clear()
                        pending_progress_selection = current_identity() is None
                        playback_view = None
                        if progress is not None: display_progress(progress)
                        mark_saved(path)
                        cache_route(document, "Route loaded: " + str(path))
                    else:
                        begin_new_route(values.get("name"))
                    return cli_ok(cli_snapshot()["route"])
                if command == "route.save":
                    if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset fields before saving", exit_code=4)
                    path = cli_file(values["file"], fresh=True, overwrite=values.get("overwrite", False))
                    document = route_document()
                    write_json_atomic(path, document)
                    mark_saved(path)
                    cache_route(document, "Route saved: " + str(path))
                    return cli_ok({"file": str(path), "revision": route_revision})
                if command == "route.add":
                    if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset fields before adding another point", "Use route select N --discard-draft", 4)
                    if len(table.get_children()) >= MAX_WAYPOINTS: raise CliError("route-full", f"Routes support at most {MAX_WAYPOINTS} points", exit_code=4)
                    if values.get("current") or values.get("target"):
                        label=values.get("name") or (None if values.get("target") else f"Point {len(table.get_children())+1}")
                        return cli_begin(rid,"target" if values.get("target") else "save",label,command=command)
                    add_point(values.get("name") or f"Point {len(table.get_children())+1}", values["x"], values["z"])
                elif command in ("route.select", "route.update", "route.remove", "route.reorder"):
                    if command=="route.select" and values.get("clear"):
                        if values.get("point") is not None:
                            raise CliError("invalid-selection","Choose a point number or --clear",exit_code=2)
                        if draft_pending() and not values.get("discard_draft"):
                            raise CliError("unapplied-edit","Apply or Reset fields before starting a new point",
                                           "Use route select --clear --discard-draft to abandon the draft",4)
                        new_point(discard_draft=bool(values.get("discard_draft")))
                        return cli_ok(dict(cli_snapshot()["route"],editDraft=edit_draft_status()))
                    children = table.get_children()
                    index = values["point"]-1
                    if not 0 <= index < len(children): raise CliError("point-out-of-range", "Choose an existing one-based point number")
                    item = children[index]
                    if draft_pending() and not (command == "route.select" and values.get("discard_draft")) and not (command == "route.update" and item == form_item):
                        raise CliError("unapplied-edit", "Apply or Reset fields before changing the selected point", "Use route select N --discard-draft", 4)
                    if command == "route.update":
                        old = table.item(item, "values")
                        if values.get("current"):
                            if values.get("x") is not None or values.get("z") is not None:
                                raise CliError("invalid-arguments", "--current cannot be combined with --x/--z", exit_code=2)
                            table.selection_set(item)
                            select_point(None, discard_draft=True)
                            label = route_points([(values.get("name") or old[0], old[1], old[2])])[0][0]
                            return cli_begin(rid, "save", dict(item=item, revision=route_revision, label=label), command=command)
                        route_points([(values.get("name", old[0]), values.get("x",old[1]), values.get("z",old[2]))])
                    table.selection_set(item)
                    select_point(None, force_name=True, discard_draft=True)
                    if command == "route.update":
                        for key,var in (("name",name),("x",x),("z",z)):
                            if values.get(key) is not None: var.set(values[key])
                        change = update_selected()
                        return cli_ok(dict(revision=route_revision, document=cli_document(), change=change,
                                           selected=[table.index(i)+1 for i in table.selection()]))
                    elif command == "route.remove": remove_points()
                    elif command == "route.reorder":
                        destination = values["to"]-1
                        if not 0 <= destination < len(children): raise CliError("point-out-of-range", "Destination must be an existing point index")
                        move_point(destination-index)
                elif command == "route.undo":
                    if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset fields before Undo", exit_code=4)
                    if not edit_history: raise CliError("nothing-to-undo", "There is no edit to undo", exit_code=4)
                    undo_edit()
                elif command == "route.run":
                    if values.get("execute") is not True: raise CliError("execute-required", "Movement requires --execute", exit_code=2)
                    rows = route_points(selected_points(True))
                    direction = values.get("direction", "forward")
                    index = values.get("from_point", 1 if direction == "forward" else len(rows))-1
                    if not 0 <= index < len(rows): raise CliError("point-out-of-range", "Choose an existing starting point")
                    rows = rows[index:] if direction == "forward" else list(reversed(rows[:index+1]))
                    return cli_begin(rid, "go", rows, command=command)
                else: raise CliError("unsupported-command", command)
                return cli_ok(dict(revision=route_revision, document=cli_document()))
            if command.startswith("radar."):
                if command == "radar.status": return cli_ok(cli_radar_status())
                if command not in ("radar.show", "radar.hide", "radar.lock", "radar.unlock", "radar.set", "radar.move", "radar.reset-position"):
                    raise CliError("unsupported-command", command)
                # Validate the complete request before changing variables or starting a reader.
                new_radius, new_opacity = None, None
                new_position = None
                if command == "radar.set":
                    if values.get("range") is not None:
                        if values["range"] not in (2,5,10,20): raise ValueError("radar range must be 2, 5, 10 or 20")
                        new_radius = int(values["range"])
                    if values.get("opacity") is not None:
                        new_opacity = finite(values["opacity"])
                        if not 20 <= new_opacity <= 100: raise ValueError("opacity must be 20..100 percent")
                elif command == "radar.move":
                    px, py = finite(values["x"]), finite(values["y"])
                    if not -100000 <= px <= 100000 or not -100000 <= py <= 100000:
                        raise ValueError("radar position must be within -100000..100000 physical pixels")
                    new_position = dict(x=round(px), y=round(py), revision=rid)
                elif command == "radar.reset-position":
                    new_position = dict(reset=True, revision=rid)
                previous_radar = (explore_controls.enabled.get(), explore_controls.unlocked.get(),
                    explore_controls.radius.get(), explore_controls.opacity.get(), deepcopy(explore_controls.extra_settings))
                if command in ("radar.show", "radar.hide"):
                    explore_controls.enabled.set(command == "radar.show")
                if command in ("radar.lock", "radar.unlock"):
                    explore_controls.unlocked.set(command == "radar.unlock")
                if new_radius is not None: explore_controls.radius.set(str(new_radius))
                if new_opacity is not None: explore_controls.opacity.set(new_opacity)
                if new_position is not None: explore_controls.extra_settings["position"] = new_position
                if not explore_controls.save():
                    enabled, unlocked, radius, opacity, extra = previous_radar
                    explore_controls.enabled.set(enabled)
                    explore_controls.unlocked.set(unlocked)
                    explore_controls.radius.set(radius)
                    explore_controls.opacity.set(opacity)
                    explore_controls.extra_settings = extra
                    explore_controls.refresh_context()
                    raise CliError("radar-save-failed", state.get(), exit_code=4)
                if command == "radar.show":
                    ensure_exploration_feed()
                    if not markers.running():
                        explore_controls.enabled.set(False)
                        explore_controls.save()
                        raise CliError("reader-unavailable", state.get(), exit_code=3)
                if command == "radar.hide" and not markers.running(): return cli_ok(cli_radar_status())
                if not explore_controls.enabled.get() and command != "radar.hide": return cli_ok(cli_radar_status(), "configured")
                if not markers.running(): raise CliError("reader-unavailable", state.get(), exit_code=3)
                display_deadline = time.monotonic() + 4
                def applied():
                    status = cli_radar_status()
                    observed = status["observed"]
                    if time.monotonic() >= display_deadline:
                        return cli_ok(dict(status, displayPending=True), "configured")
                    if observed is None: return None
                    if command in ("radar.move", "radar.reset-position") and observed.get("appliedRevision") != rid: return None
                    if observed["visible"] != explore_controls.enabled.get(): return None
                    if observed["visible"] and observed["unlocked"] != explore_controls.unlocked.get(): return None
                    if observed["visible"] and (observed.get("range") != int(explore_controls.radius.get())
                            or observed.get("opacity") != round(explore_controls.opacity.get())/100): return None
                    return cli_ok(status)
                return cli_wait(rid, applied)
            if command.startswith("beacons."):
                if command == "beacons.status": return cli_ok(cli_beacon_status())
                if command == "beacons.reset":
                    if not reset_marker_appearance(): raise CliError("appearance-save-failed", state.get())
                    return cli_ok(cli_beacon_status(), "configured")
                if command == "beacons.hide":
                    stop_markers()
                    return cli_wait(rid, lambda: None if markers.running() else cli_ok(cli_beacon_status()))
                if command == "beacons.set":
                    if values.get("guide") == "on" and len(table.selection()) != 1:
                        raise CliError("selection-required", "Select one waypoint before enabling its guide", "Use route select N", 4)
                    target_change = values.get("target") is not None and (values["target"] == "on") != target_beacon.get()
                    if target_change and markers.running() and target_change_blocked():
                        raise CliError("exploration-active", "Stop manual guidance and trail recording before changing target inclusion", exit_code=4)
                    if marker_restart_pending: raise CliError("reader-restarting", "Wait for the reader restart", exit_code=4)
                    if values.get("size") is not None and not .5 <= finite(values["size"]) <= 2: raise ValueError("size must be .5..2")
                    if values.get("opacity") is not None and not 20 <= finite(values["opacity"]) <= 100: raise ValueError("opacity must be 20..100 percent")
                    for key in ("labels","target","guide"):
                        if values.get(key) is not None and values[key] not in ("on","off"): raise ValueError(key+" must be on or off")
                    if values.get("size") is not None:
                        if not .5 <= finite(values["size"]) <= 2: raise ValueError("size must be .5..2")
                        beacon_size.set(values["size"]*100)
                    if values.get("opacity") is not None:
                        if not 20 <= finite(values["opacity"]) <= 100: raise ValueError("opacity must be 20..100 percent")
                        beacon_opacity.set(values["opacity"])
                    for key,var in (("labels",beacon_labels),("target",target_beacon),("guide",landmark_guide)):
                        if values.get(key) is not None: var.set(values[key] == "on")
                    change_marker_appearance()
                    if not save_marker_appearance(): raise CliError("appearance-save-failed", state.get())
                    schedule_marker_update()
                    if target_change and markers.running():
                        if not change_target_inclusion(): raise CliError("reader-restart-failed", state.get())
                        def restarted():
                            if marker_restart_pending or markers.running() and markers.stop_requested: return None
                            if not markers.running(): return cli_error("reader-restart-failed", state.get())
                            return cli_ok(cli_beacon_status(), "configured") if cli_pose()["status"] == "fresh" else None
                        return cli_wait(rid, restarted)
                    return cli_ok(cli_beacon_status(), "configured")
                if command != "beacons.show": raise CliError("unsupported-command", command)
                ensure_exploration_feed()
                if not markers.running() and not marker_restart_pending:
                    raise CliError("reader-unavailable", state.get(), exit_code=3)
                def shown():
                    if marker_restart_pending or markers.running() and markers.stop_requested: return None
                    if not markers.running(): return cli_error("reader-unavailable", state.get(), exit_code=3)
                    return cli_ok(cli_beacon_status()) if cli_pose()["status"] == "fresh" else None
                return cli_wait(rid, shown)
            if command.startswith("guide."):
                if command == "guide.start":
                    direction = values.get("direction", "forward")
                    index = values.get("from_point", 1 if direction == "forward" else len(table.get_children()))-1
                    explore_controls.start_guidance(direction=direction, start_index=index,
                        radius=values.get("radius"), raise_errors=True)
                elif command == "guide.stop": explore_controls.stop_guidance()
                elif command != "guide.status": raise CliError("unsupported-command", command)
                return cli_ok(explore_controls.navigation_state())
            if command.startswith("trail."):
                if command == "trail.start":
                    packet = explore_controls._owner()
                    explore_controls.trail.start(packet)
                    explore_controls.trail.observe(packet)
                    explore_controls._refresh()
                    explore_controls._notify()
                elif command == "trail.stop": explore_controls.stop_trail()
                elif command == "trail.clear":
                    if not values.get("discard"): raise CliError("discard-required", "Use trail clear --discard", exit_code=4)
                    if explore_controls.trail.snapshot()["active"]: raise CliError("trail-active", "Stop the trail before clearing", exit_code=4)
                    explore_controls.clear_trail(discard=True)
                elif command == "trail.save":
                    segments = explore_controls.trail.snapshot()["segments"]
                    index = len(segments)-1 if values.get("segment", "latest") == "latest" else int(values["segment"])-1
                    if not 0 <= index < len(segments): raise CliError("segment-out-of-range", "Choose an existing one-based segment")
                    document = explore_controls.trail.export_segment(index)
                    path = cli_file(values["file"], fresh=True, overwrite=values.get("overwrite", False))
                    write_json_atomic(path, document)
                    return cli_ok({"file": str(path), "segment": index+1, "pointCount": len(document["waypoints"])})
                elif command not in ("trail.status", "trail.list"): raise CliError("unsupported-command", command)
                return cli_ok(cli_trail_status())
            if command == "record.status": return cli_ok({"active": recording, "progress": recording_progress})
            if command == "record.start":
                if route_dirty: raise CliError("unsaved-route", "Save the current route before recording replaces it", exit_code=4)
                return cli_begin(rid, "record", command=command)
            if command in ("record.stop", "record.cancel"):
                if not recording: raise CliError("not-recording", "There is no active recording", exit_code=4)
                job = cli_action
                if command == "record.stop":
                    if cli_record_output is not None:
                        raise CliError("recording-finishing", "Recording already has a pending save destination", "Wait for its result or explicitly cancel", 4)
                    cli_record_output = cli_file(values["file"], fresh=True, overwrite=values.get("overwrite", False))
                    stop_recording()
                else:
                    cli_record_output = None
                    record_cancel.set()
                    record_stop.set()
                def record_done():
                    if busy: return None
                    if command == "record.cancel": return cli_ok({"cancelled": True, "saved": False})
                    if job and job.get("recordedFile"): return cli_ok({"file": job["recordedFile"], "saved": True})
                    if cli_last_record_file == str(cli_file(values["file"])):
                        return cli_ok({"file": cli_last_record_file, "saved": True})
                    return cli_error("recording-failed", state.get())
                return cli_wait(rid, record_done)
            if command in ("move.to", "move.pick", "face", "playback.start", "playback.resume"):
                if values.get("execute") is not True: raise CliError("execute-required", "Movement requires --execute", exit_code=2)
                if command == "move.pick":
                    if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset fields before moving", exit_code=4)
                    return cli_begin(rid, "map-go", map_destination(values["canvas_x"], values["canvas_y"]), command=command)
                if command == "move.to":
                    return cli_begin(rid, "go", [("CLI destination", finite(values["x"]), finite(values["z"]))], command=command)
                if command == "face":
                    bearing = finite(values["bearing"])
                    if not 0 <= bearing < 360: raise ValueError("bearing must be in [0,360)")
                    return cli_begin(rid, "face-bearing", bearing, command=command)
                selected_checkpoint=cli_file(values["checkpoint"]) if values.get("checkpoint") else checkpoint
                document = route_document()
                from scripts.waypoint_playback import validate_playback_document
                from scripts.waypoint_progress import RouteProgress,ProgressError
                if adapter is None: raise CliError("rift-unavailable","Wait for a verified RIFT connection before playback",exit_code=3)
                binding=getattr(adapter,"binding",None)
                identity=binding.get("runtimeIdentity") if isinstance(binding,dict) else None
                try:
                    validate_playback_document(document,identity)
                except (ValueError,KeyError,TypeError) as exc:
                    raise CliError("playback-unavailable",str(exc),"Inspect playback status",4)
                direction = values.get("direction")
                if command == "playback.resume":
                    try:
                        cursor=RouteProgress.load(selected_checkpoint,document,identity)
                    except (ProgressError,OSError,ValueError,KeyError,TypeError) as exc:
                        raise CliError("progress-unavailable",str(exc),"Inspect playback status or start a new run",4)
                    direction = direction or cursor.direction
                    if direction!=cursor.direction:
                        raise CliError("resume-direction-mismatch","Resume direction does not match saved progress",
                                       f"Omit --direction to resume {cursor.direction}",4)
                    if cursor.next_index>=len(cursor.ordered_points):
                        raise CliError("playback-complete","This saved run is complete; choose Play Forward or Play Reverse",
                                       "Start a new run at its endpoint",4)
                else:
                    direction = direction or "forward"
                    if values.get("from_point") is not None:
                        raise ValueError("Playback starts at its recorded endpoint; use guide start --from for passive guidance")
                if direction not in ("forward","reverse"): raise ValueError("direction must be forward or reverse")
                pending=cli_begin(rid,"resume" if command.endswith("resume") else "play",(document,direction),command=command)
                checkpoint=selected_checkpoint
                replay_cache["key"]=None
                update_replay_status()
                return pending
            if command == "playback.status":
                return cli_ok(cli_playback_status())
            if command == "view.status": return cli_ok(cli_view_status())
            if command == "view.load": return cli_ok(load_saved_scene(values["file"]))
            if command == "view.save":
                if adapter is None: raise CliError("rift-unavailable", "Connect to RIFT first", exit_code=3)
                if draft_pending(): raise CliError("unapplied-edit", "Apply or Reset waypoint fields before capturing", exit_code=4)
                readiness = capture_readiness()
                if not readiness["ready"]: raise CliError("capture-route-unavailable", readiness["reason"], "Load a fully measured route", 4)
                for key in ("bring_forward","nearby_units"):
                    if key in values and type(values[key]) is not bool: raise ValueError(key+" must be boolean")
                view_bring_forward.set(bool(values.get("bring_forward", False)))
                view_include_units.set(bool(values.get("nearby_units", False)))
                output = cli_file(values["file"], fresh=True, overwrite=values.get("overwrite", False))
                return cli_begin(rid, "view", (deepcopy(route_document()), adapter.pid, deepcopy(adapter.target),
                    "desktop" if view_bring_forward.get() else "wgc", view_include_units.get(), str(output)), command=command)
            if command in ("view.open", "view.open-3d"):
                path = cli_file(values["file"])
                if not path.is_file(): raise CliError("file-unavailable", str(path))
                if path.suffix.lower() == ".json":
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    if manifest.get("status") != "saved-route-view-candidate": raise ValueError("not a saved view manifest")
                    selected = manifest.get("image") if command == "view.open" else manifest.get("rerun", {}).get("path")
                    if not selected: raise ValueError("this view has no exported 3D recording")
                    path = cli_file(selected)
                    if not path.is_file(): raise ValueError("saved view asset is unavailable")
                if command == "view.open":
                    import os
                    os.startfile(str(path))
                    saved_view = str(path)
                else:
                    from scripts.save_physical_route_view import launch_saved_rerun
                    if rerun_viewer is not None and rerun_viewer.poll() is None: raise CliError("viewer-open", "The owned 3D viewer is already open", exit_code=4)
                    rerun_viewer = launch_saved_rerun(str(path))
                    saved_rerun = str(path)
                last_capture_state, last_capture_error = "loaded", None
                return cli_ok({"file": str(path), "opened": True})
            raise CliError("unsupported-command", command, exit_code=2)
        except CliError as exc:
            return cli_error(exc.code, str(exc), exit_code=exc.exit_code, hint=exc.hint, command=command, request_id=rid)
        except FileExistsError as exc:
            return cli_error("file-exists", str(exc), exit_code=4, hint="Choose another ID or explicitly use --overwrite",
                             command=command, request_id=rid)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            diagnostics.exception("CLI command failed", exc=exc, command=command, requestId=rid)
            return cli_error("operation-failed", str(exc), recorded=True)

    library_name = tk.StringVar()
    library_search = tk.StringVar()
    library_filter = tk.StringVar(value="all")
    library_summary = tk.StringVar(value="No saved routes")
    library_details = tk.StringVar(value="Choose a saved route to inspect it.")
    library_hint = tk.StringVar()
    library_rows, library_visible = {}, []
    library_pending = None
    library_auto_name = [None]
    library_buttons = {}
    library_tab.columnconfigure(0, weight=1)
    library_tab.columnconfigure(2, minsize=275)
    library_tab.rowconfigure(1, weight=1)
    library_tools = ttk.Frame(library_tab, style="Surface.TFrame")
    library_tools.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 5))
    ttk.Label(library_tools, text="Find", style="Surface.Micro.TLabel").pack(side="left", padx=(0,5))
    library_search_entry = ttk.Entry(library_tools, name="library_search", textvariable=library_search, width=22)
    library_search_entry.pack(side="left", padx=(0,8))
    attach_path_tooltip(library_search_entry, lambda:"Search names, IDs, saved zone/world context and entry errors.")
    zone_filter = ttk.Combobox(library_tools, textvariable=library_filter,
        values=("all","matching","mismatch","unknown"), state="readonly", width=10)
    zone_filter.pack(side="left", padx=(0,8))
    ttk.Style(window).configure("Library.Treeview",rowheight=26)
    ttk.Style(window).configure("Library.Treeview.Heading",padding=(7,3))
    library_table = ttk.Treeview(library_tab, columns=("name","id","zone","heights"), displaycolumns=("name","id","zone"),
        style="Library.Treeview", show="headings", height=3, selectmode="browse")
    for key,title,width in (("name","Saved route",240),("id","Library ID",130),("zone","Zone candidate",190),("heights","Points / height evidence",180)):
        library_table.heading(key,text=title)
        library_table.column(key,width=width,minwidth=70 if key=="id" else 100)
    library_table.grid(row=1,column=0,sticky="nsew")
    library_scroll = ttk.Scrollbar(library_tab,orient="vertical",command=library_table.yview)
    library_scroll.grid(row=1,column=1,sticky="ns")
    library_table.configure(yscrollcommand=library_scroll.set)
    library_table.tag_configure("error", foreground="#ffb4a9")
    library_detail_label = ttk.Label(library_tab, textvariable=library_details, style="Muted.TLabel", wraplength=260,width=43)
    library_detail_label.grid(row=1,column=2,sticky="nw",padx=(12,0))
    library_actions = ttk.Frame(library_tab,style="Surface.TFrame")
    library_actions.grid(row=3,column=0,columnspan=3,sticky="ew",pady=(5,0))
    ttk.Label(library_actions,text="Copy name",style="Surface.Micro.TLabel").pack(side="left",padx=(0,6))
    library_name_entry = ttk.Entry(library_actions,name="library_copy_name",textvariable=library_name,width=26)
    library_name_entry.pack(side="left",padx=(0,6))
    library_hint_label = ttk.Label(library_tab,textvariable=library_hint,style="Muted.TLabel",wraplength=850)
    library_hint_label.grid(row=4,column=0,columnspan=3,sticky="ew",pady=(3,0))
    def size_library(event):
        library_hint_label.configure(wraplength=max(200,event.width-30))
    library_tab.bind("<Configure>", size_library)

    def library_selected_id():
        selected = library_table.selection()
        return selected[0] if len(selected)==1 else None

    def library_block_reason():
        if busy or cli_action is not None or closing: return "Wait for the active action to finish."
        return None

    def library_view_state():
        selected = library_selected_id()
        row = library_rows.get(selected)
        common = library_block_reason()
        load_reason = common or ("Apply or Reset fields before loading." if draft_pending() else None)
        if load_reason is None:
            load_reason = "Choose a saved route." if row is None else ("Selected entry is unavailable: "+row["error"] if row.get("error") else None)
        save_reason = common or ("Apply or Reset fields before saving a copy." if draft_pending() else None)
        if save_reason is None:
            if not table.get_children(): save_reason="Add a waypoint before saving a copy."
            elif not library_name.get().strip() or len(library_name.get().strip())>120: save_reason="Copy name must contain 1–120 characters."
        return dict(directory=str(ROOT/"artifacts"/"waypoint-routes"),search=library_search.get(),filter=library_filter.get(),
            selectedId=selected,totalCount=len(library_rows),shownCount=len(library_visible),
            canLoad=load_reason is None,loadReason=load_reason,canSaveCopy=save_reason is None,saveReason=save_reason)

    def update_library_readiness(*_):
        default = route_metadata.get("routeName") or (route_path.stem if route_path else "My route")
        if library_auto_name[0] is None or library_name.get()==library_auto_name[0]:
            library_auto_name[0]=default
            if library_name.get()!=default: library_name.set(default)
        view=library_view_state()
        for label,allowed in (("Load selected",view["canLoad"]),("Save copy",view["canSaveCopy"]),
                              ("Import file",not library_block_reason()),("Refresh zone",not library_block_reason())):
            if label in library_buttons: library_buttons[label].configure(state="normal" if allowed else "disabled")
        if view["saveReason"]: hint=view["saveReason"]
        elif view["loadReason"]: hint=view["loadReason"]
        elif route_dirty: hint="Current route has unsaved changes; Load will ask. Save copy creates a separate entry."
        else: hint="Save copy creates a new ID; Import keeps the source name. Zone matches are candidate evidence only."
        library_hint.set(hint)

    def library_selection_changed(*_):
        row=library_rows.get(library_selected_id())
        if row is None:
            library_details.set("No routes match. Clear filters or import a route." if library_rows else "Library is empty. Save a copy of your route or import a JSON file.")
        elif row.get("error"):
            library_details.set("Unavailable: "+row["id"]+"\n"+str(row["error"])[:120])
        else:
            context=row.get("routeContext") or {}
            zone=context.get("zoneName") or context.get("zoneIdCandidate") or "Unknown / legacy"
            name=" ".join(row["name"].split())
            name=name if len(name)<=36 else name[:33]+"…"
            stamp=row.get("modifiedAtUtc")
            updated=datetime.fromisoformat(stamp.replace("Z","+00:00")).astimezone().strftime("%b %d %H:%M") if stamp else "unknown"
            library_details.set(f"Selected: {name}\nID {row['id']}\n"
                f"{row['waypointCount']} points · {row['planarDistance']:.1f}u path · {updated}\n"
                f"{row['measuredHeightCount']} measured / {row['estimatedHeightCount']} estimated heights\n"
                f"{zone} · {row['contextStatus']} candidate")
        update_library_readiness()

    attach_path_tooltip(library_detail_label, lambda: ((library_rows.get(library_selected_id()) or {}).get("path") or str(ROOT/"artifacts"/"waypoint-routes")))

    def filter_library(select_id=None):
        nonlocal library_visible,library_pending
        library_pending=None
        from scripts.waypoint_route_library import filter_routes
        selected=select_id or library_selected_id()
        try:
            rows=filter_routes(list(library_rows.values()),None if library_filter.get()=="all" else library_filter.get(), search=library_search.get())
            library_visible=[row["id"] for row in rows]
            library_table.delete(*library_table.get_children())
            for row in rows:
                context=row.get("routeContext") or {}
                zone=context.get("zoneName") or context.get("zoneIdCandidate") or "Unknown / legacy"
                evidence=("Unavailable" if row.get("error") else f"{row['waypointCount']} pts · {row['measuredHeightCount']} measured / {row['estimatedHeightCount']} est.")
                library_table.insert("","end",iid=row["id"],values=(row["name"],row["id"],zone+" · "+row["contextStatus"],evidence),tags=("error",) if row.get("error") else ())
            if selected not in library_visible: selected=next((r["id"] for r in rows if not r.get("error")),rows[0]["id"] if rows else None)
            if selected:
                library_table.selection_set(selected)
                library_table.focus(selected)
                library_table.see(selected)
            library_summary.set(f"{len(rows)} / {len(library_rows)} routes" if rows else "No routes match" if library_rows else "No saved routes")
            library_selection_changed()
        except (OSError,ValueError,TypeError) as exc:
            diagnostics.exception("Unable to filter route library",exc=exc)
            state.set("Cannot filter route library: "+str(exc))

    def refresh_library(*,select_id=None,clear_filters=False):
        nonlocal library_rows,library_pending
        from scripts.waypoint_route_library import list_routes
        if library_pending is not None:
            window.after_cancel(library_pending)
            library_pending=None
        try:
            rows=list_routes(zone_state()["context"],library_dir=ROOT/"artifacts"/"waypoint-routes")
            library_rows={row["id"]:row for row in rows}
            if clear_filters:
                library_search.set("")
                library_filter.set("all")
                if library_pending is not None: window.after_cancel(library_pending); library_pending=None
            filter_library(select_id)
        except (OSError,ValueError,TypeError) as exc:
            diagnostics.exception("Unable to read route library",exc=exc)
            state.set("Cannot read route library: "+str(exc))
            library_summary.set("Library unavailable")

    def library_save_copy():
        view=library_view_state()
        if not view["canSaveCopy"]: state.set(view["saveReason"]); return
        result = cli_dispatch("library.save",dict(name=library_name.get()),"gui-"+uuid.uuid4().hex)
        state.set((f"Library copy saved: {result['data']['name']} · ID {result['data']['routeId']}; current file unchanged.") if result.get("ok") else result["error"]["message"])

    def library_load_selected(_=None):
        view=library_view_state()
        if not view["canLoad"]: state.set(view["loadReason"]); return
        row=library_rows[library_selected_id()]
        load_from(row["path"])
        update_library_readiness()

    def library_import_file():
        path = filedialog.askopenfilename(parent=window,title="Import a route copy",filetypes=[("Waypoint JSON","*.json")])
        if path:
            result = cli_dispatch("library.import",dict(file=path),"gui-"+uuid.uuid4().hex)
            state.set((f"Imported copy: {result['data']['name']} · ID {result['data']['routeId']}; source unchanged.") if result.get("ok") else result["error"]["message"])

    for label,callback in (("Save copy",library_save_copy),("Load selected",library_load_selected),("Import file",library_import_file)):
        button = ttk.Button(library_actions,text=label,command=callback)
        button.pack(side="left",padx=(0,6))
        editable.append(button)
        library_buttons[label]=button
    attach_path_tooltip(library_buttons["Save copy"],lambda:"Save a new named library entry without changing the open file. Existing IDs require explicit CLI --id and --overwrite.")
    attach_path_tooltip(library_buttons["Import file"],lambda:"Import a separate copy using the source route name or filename. CLI library import --name overrides that name.")
    def clear_library_filters():
        nonlocal library_pending
        library_search.set("");library_filter.set("all")
        if library_pending is not None: window.after_cancel(library_pending)
        filter_library()
    ttk.Button(library_tools,text="Clear filters",width=10,command=clear_library_filters).pack(side="left",padx=(0,6))
    ttk.Button(library_tools,text="Refresh library",width=14,command=refresh_library).pack(side="left",padx=(0,6))
    library_zone_button=ttk.Button(library_tools,text="Refresh zone",width=11,command=lambda:start("zone"))
    library_zone_button.pack(side="left",padx=(0,6))
    library_buttons["Refresh zone"]=library_zone_button
    editable.append(library_zone_button)
    ttk.Label(library_tools,textvariable=library_summary,style="Surface.Micro.TLabel").pack(side="right")
    def schedule_library_filter(*_):
        nonlocal library_pending
        if library_pending is not None: window.after_cancel(library_pending)
        library_pending=window.after(150,filter_library)
    library_search.trace_add("write",schedule_library_filter)
    library_name.trace_add("write",lambda *_:update_library_readiness())
    zone_filter.bind("<<ComboboxSelected>>",lambda _:filter_library())
    library_table.bind("<<TreeviewSelect>>",library_selection_changed)
    library_table.bind("<Double-1>",library_load_selected)
    library_table.bind("<Return>",library_load_selected)
    workflow.bind("<<NotebookTabChanged>>",lambda _:workflow.configure(
        height=200 if workflow.select()==str(edit_tab) else 230 if workflow.select()==str(replay_tab) else 220 if workflow.select() in (str(library_tab),str(scene_tab),str(activity_tab)) else 184))

    def poll():
        nonlocal recording_restore, route_metadata
        nonlocal busy, recording, recording_progress, pending_recorded, foreground_stop, last_pose, last_y, saved_view, saved_rerun, saved_unit_sample, observing, next_live_at, playback_view, playback_active, marker_identity, pending_progress_selection, verified_adapter, verified_at, identity_unavailable, last_verified_owner
        nonlocal beacon_display_active, beacon_pose_token, beacon_pose_available, beacon_pose_stamp, exploration_sample
        nonlocal cli_action, cli_record_output, cli_last_operation, cli_last_record_file
        nonlocal current_zone_context, zone_error, zone_observing, next_zone_at
        nonlocal last_edit_change
        nonlocal marker_restart_pending, last_capture_state, last_capture_error
        nonlocal stop_waiting_operation
        cli_server.poll(cli_dispatch)
        if cli_destroyed:
            return
        # The registered F8 listener also latches the same STOP event.
        if stop.is_set() and busy and not stop_waiting_operation:
            stop_context.update(hadOwnedAction=True,activeRequestIdAtStop=cli_action["id"] if cli_action else None,
                result=None,keyReleaseEvidence="not-measured",stationaryEvidence="not-measured")
            stop_waiting_operation=True
        while not events.empty():
            event = events.get_nowait()
            status = event["status"]
            if status in ("zone", "zone-unavailable"):
                current_zone_context = event.get("context")
                zone_error = event.get("reason")
                next_zone_at = time.monotonic()+15
                if zone_comparison() == "mismatch":
                    explore_controls.stop_guidance()
                    explore_controls.unavailable("Route zone candidate differs from current zone")
                    stop_markers()
                    state.set("Route zone candidate differs; movement and markers require a matching route.")
                update_context_text()
                refresh_library()
                continue
            if status == "zone-idle":
                zone_observing = False
                continue
            if status == "operation-finished":
                cli_last_operation = event
                if stop_waiting_operation:
                    stop_context["result"]={k:v for k,v in event.items() if k not in ("result","status")}
                    stop_context["stationaryEvidence"]=(event.get("stopVerification") or {}).get("status","not-measured")
                    recovery = event.get("inputRecovery")
                    stop_context["keyReleaseEvidence"] = ("unverified" if event.get("inputReleaseFault") else
                        "verified-recovery" if isinstance(recovery, dict) and recovery.get("releaseSucceeded") is True else
                        "see-native-input-receipts" if event.get("inputReceiptPath") else "not-measured")
                    stop_waiting_operation=False
                if cli_action is not None and cli_action["operation"] == event["operation"]:
                    cli_action["finished"] = event
                continue
            if status == "survival-state":
                survival = event.get("survival")
                if isinstance(survival, dict) and survival.get("status") == "ready":
                    target = survival.get("targetId") or "no selected target"
                    text = ("Survival ready · advancing telemetry · qualified controls · "
                            + str(target))
                elif isinstance(survival, dict) and survival.get("state"):
                    owner = survival.get("owner") or "no action owner"
                    text = ("Survival " + str(survival["state"]) + " · " + str(owner)
                            + " · encounters " + str(survival.get("encounterCount", 0)))
                    if survival.get("reason"):
                        text += " · " + str(survival["reason"])
                else:
                    text = "Survival unavailable: " + str(survival)
                survival_summary.set(text)
                state.set(text)
                continue
            if status == "recording" and cli_action is not None and cli_action["operation"] == "record":
                cli_action["recordingObserved"] = True
            if status == "view-failed":
                last_capture_state, last_capture_error = "failed", event.get("reason")
                saved_unit_sample = None
            if status in ("stopping", "notice") and stop.is_set() and markers.running():
                if not stop_markers():
                    event = dict(event, reason=event.get("reason", "STOP requested.") + " Could not hide markers.")
            if status == "reconnected":
                diagnostics.set_context(riftTarget=deepcopy(getattr(adapter, "target", None)))
                diagnostics.info("RIFT connection changed", processId=event.get("pid"))
                if not stop_markers():
                    state.set("Cannot hide markers after RIFT reconnected.")
                pending_progress_selection = bool(table.get_children())
                window.title(f"{APP_TITLE} — {args.expected_host} / PID {event['pid']}")
                connection_text.set(f"{args.expected_host}  /  PID {event['pid']}")
                state.set(f"Reconnected to RIFT PID {event['pid']}.")
                continue
            if status == "halted":
                last_pose = None
                set_pose_unavailable(event.get("reason","Action halted; refresh position"))
                verified_adapter, verified_at = None, None
                identity_unavailable = True
                redraw()
            if status == "live-idle":
                observing = False
                select_pending_progress()
                continue
            if status == "live-unavailable":
                set_pose_unavailable(event["reason"])
                last_pose = None
                verified_adapter, verified_at = None, None
                identity_unavailable = True
                redraw()
                continue
            if status == "idle":
                if foreground_stop is not None:
                    try:
                        foreground_stop.close()
                    except WaypointError as exc:
                        state.set(str(exc))
                        window.after(200, lambda: events.put({"status": "idle"}))
                        continue
                    foreground_stop = None
                busy = False
                if playback_active:
                    playback_active = False
                    try:
                        restore_progress()
                    except (OSError, ValueError, KeyError, TypeError):
                        playback_view = None
                        progress_text.set("No saved progress; choose Play Forward or Play Reverse.")
                select_pending_progress()
                if recording_restore is not None:
                    old_rows, old_selection, route_metadata = recording_restore
                    table.delete(*table.get_children())
                    for item, values in old_rows:
                        table.insert("", "end", iid=item, values=values)
                    table.selection_set(old_selection)
                    recording_restore = None
                    update_route_status()
                recording = False
                recording_progress = None
                record_end_button.configure(state="disabled")
                restore_editing()
                if pending_recorded is not None and not closing:
                    events.put(dict(pending_recorded, status="recorded-ready"))
                    pending_recorded = None
                if closing:
                    pending_recorded = None
                continue
            if status == "recorded-pending":
                pending_recorded = event
                continue
            if status == "recorded-ready":
                if record_cancel.is_set() or closing or (event.get("operation") == "teach" and stop.is_set()):
                    state.set("Recording cancelled; no route saved.")
                    continue
                # This runs on the UI thread: STOP/close cannot race publication.
                recording = False
                record_end_button.configure(state="disabled")
                directory = ROOT / "artifacts" / "waypoint-routes"
                directory.mkdir(parents=True, exist_ok=True)
                output = cli_record_output or route_path or directory / ("recorded-route-" + uuid.uuid4().hex + ".json")
                cli_record_output = None
                try:
                    event["document"].setdefault("routeName", route_metadata.get("routeName", Path(output).stem))
                    write_json_atomic(output, event["document"])
                    document = prepared_document(event["document"])
                    progress = select_progress(document)
                    show_document(document)
                    pending_progress_selection = current_identity() is None
                    playback_view = None
                    if progress is not None:
                        display_progress(progress)
                    edit_history.clear()
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    state.set("Cannot finish recording: " + str(exc))
                    continue
                mark_saved(output)
                cli_last_record_file = str(output)
                if cli_action is not None and cli_action["operation"] == "record":
                    cli_action["recordedFile"] = str(output)
                cache_route(event["document"], "Recorded route saved: " + str(output))
                if progress is None:
                    progress_text.set("Recorded route ready; select playback direction.")
                continue
            if status == "view-saved":
                last_capture_state, last_capture_error = "saved", None
                saved_view = event["image"]
                rerun = event["rerun"]
                saved_rerun = str(rerun["path"]) if rerun.get("status") == "saved" and rerun.get("path") else None
                if saved_rerun is None: last_capture_state = "partial"
                suffix = ("" if rerun.get("status") == "saved" else
                          "; Rerun " + str(rerun.get("status", "unavailable"))
                          + (": " + str(rerun["reason"]) if rerun.get("reason") else ""))
                text = "View saved: " + saved_view + suffix
                unit_sample = event.get("unitSample")
                saved_unit_sample = (str(unit_sample["path"]) if isinstance(unit_sample, dict)
                                     and unit_sample.get("status") == "saved" and unit_sample.get("path") else None)
                if isinstance(unit_sample, dict) and unit_sample.get("status") == "unavailable":
                    text += " · Nearby units unavailable"
                    if unit_sample.get("reason"):
                        text += " (" + str(unit_sample["reason"]) + ")"
                state.set(text)
                continue
            if status in ("run-receipt", "receipt-error"):
                text = ("Run receipt: " + event["path"] if status == "run-receipt" else
                        "Could not save run receipt: " + event["reason"])
                failure = event.get("failure")
                state.set((f"{failure['status']}: {failure['reason']} — " if failure else "") + text)
                continue
            if "nextWaypoint" in event:
                count = event.get("totalWaypoints", event.get("waypointCount"))
                progress_text.set(f"Completed {event['nextWaypoint']} / {count} waypoints")
                if playback_view is not None:
                    playback_view["nextIndex"] = event["nextWaypoint"]
                    redraw()
            if "recordingProgress" in event:
                recording_progress = event["recordingProgress"]
            if "position" in event:
                point = event["position"]
                if status == "recording":
                    preview = event.get("preview")
                    if recording and not record_cancel.is_set() and isinstance(preview, dict):
                        table.delete(*table.get_children())
                        for index, row in enumerate(preview["waypoints"]):
                            table.insert("", "end", iid=f"record-preview-{index}", values=row)
                        if table.get_children():
                            table.see(table.get_children()[-1])
                        route_metadata = {**preview, "routeName": "Recording in progress"}
                        route_metadata.pop("waypoints", None)
                        route_status.set("Recording — live preview (not saved yet)")
                    recording_progress = {"sampleCount": event["sampleCount"],
                                          "observedPathLength": event["observedPathLength"]}
                display_pose(point, event.get("bearing"),acquired=event.get("acquired"))
                if (status in ("refresh", "live", "save", "target", "map")
                        or status in ("stopped", "arrived") and type(event.get("acquired")) in (int, float)):
                    verified_adapter, verified_at = adapter, event.get("acquired")
                    identity_unavailable = False
                    owner = current_identity()
                    if owner is not None:
                        last_verified_owner = owner
                if status in ("refresh", "live"):
                    try:
                        restore_progress()
                    except (OSError, ValueError, KeyError, TypeError):
                        playback_view = None
                        progress_text.set("Saved progress unavailable; load a matching route to continue."
                                          if checkpoint.exists() else "No saved progress; choose Play Forward or Play Reverse.")
                redraw()
            if status in ("live", "recording"):
                continue
            if status == "save":
                replacement = event.get("replacement")
                if replacement is not None:
                    item = replacement["item"]
                    if (not table.exists(item) or replacement["revision"] != route_revision
                            or event.get("captureTarget") != getattr(adapter, "target", None)):
                        state.set("Waypoint or RIFT identity changed; capture was not applied.")
                        if cli_action is not None:
                            cli_action["editFailure"] = dict(status="failed", reason=state.get())
                        continue
                    old = table.item(item, "values")
                    point = event["position"]
                    last_edit_change = dict(nameChanged=old[0] != replacement["label"],
                        coordinatesChanged=(finite(old[1]), finite(old[2])) != (round(point["x"],6), round(point["z"],6)),
                        measurementDiscarded=False, measurementReplaced=True, recordingDiscarded="recording" in route_metadata)
                    remember_edit()
                    invalidate_progress()
                    table.item(item, values=(replacement["label"], f"{point['x']:.6f}", f"{point['z']:.6f}"))
                    point_receipts[item] = event["measurement"]
                    table.selection_set(item)
                    fill_fields(item)
                    if cli_action is not None: cli_action["change"] = deepcopy(last_edit_change)
                    event["measurementReason"] = "Selected waypoint replaced with current measured XYZ; save the route to keep it."
                    redraw()
                else:
                    item = add_point(event.get("newLabel") or name.get() or "Waypoint", event["position"]["x"], event["position"]["z"])
                if item is not None and event.get("measurement") is not None:
                    point_receipts[item] = event["measurement"]
                    redraw()
            if "waypoint" in event:
                item = add_point(*event["waypoint"])
                if item is not None and event.get("measurement") is not None:
                    point_receipts[item] = event["measurement"]
                    redraw()
            text = (f"Route complete — {event['waypointCount']} waypoint{'s' if event['waypointCount'] != 1 else ''}, "
                    f"{event['distance']:.3f} units from the final point."
                    if status == "route-complete" else
                    f"{status}: {event['reason']}" if "reason" in event else
                    f"{status}: {abs(event['headingError']):.2f}° from requested facing" if "headingError" in event else
                    f"{status}: {event['distance']:.3f} units remaining" if "distance" in event else
                    f"{status}: {event.get('name', '')}" if status == "leg" else
                    event.get("measurementReason", "Saved current position.") if status == "save" else
                    event.get("measurementReason", "Saved the target's current ground position.") if status == "target" else
                    "Waypoint added from the preview; beacon height estimated." if status == "map" else
                    "Position refreshed.")
            state.set(text)
        for rid, callback in list(cli_waiters.items()):
            try:
                response = callback()
            except Exception as exc:
                diagnostics.exception("Deferred CLI request failed", exc=exc, requestId=rid)
                response = cli_error("operation-failed", str(exc), recorded=True)
            if response is not None:
                cli_server.complete(rid, response)
                del cli_waiters[rid]
        # A background Record command acknowledges when capture starts, but its
        # ownership remains until the recording worker actually ends.
        if (cli_action is not None and cli_action["operation"] == "record"
                and cli_action["finished"] is not None and not busy):
            cli_action = None
            cli_record_output = None
        if finish_close():
            return
        if marker_identity is not None:
            target = getattr(adapter, "target", {})
            current_marker_identity = (getattr(adapter, "pid", None), str(target.get("processStartUtcTicks")),
                                       str(target.get("executableSha256", "")).casefold(), target.get("hwnd"))
            if current_marker_identity != marker_identity:
                stop_markers()
            if not markers.running():
                if markers.exit_code and not markers.stop_requested:
                    diagnostics.warning("Overlay reader exited unexpectedly", exitCode=markers.exit_code,
                                        reportFile=str(getattr(markers,"output",None)))
                    state.set("Markers unavailable; check the route and RIFT connection.")
                elif state.get() == "Hiding markers…":
                    state.set("Markers hidden.")
                marker_identity = None
                marker_button.configure(text="Show markers", state="normal" if not busy else "disabled")
            elif markers.stop_requested:
                marker_button.configure(text="Markers closing…", state="disabled")
        if marker_restart_pending and not markers.running() and not busy and not closing:
            marker_restart_pending = False
            toggle_markers()
        target_option.configure(state="disabled" if busy or closing or marker_restart_pending or target_change_blocked() else "normal")
        if len(table.selection()) != 1 and landmark_guide.get():
            landmark_guide.set(False)
            schedule_marker_update()
        landmark_option.configure(state="disabled" if busy or closing or len(table.selection()) != 1 else "normal")
        for widget in appearance_widgets:
            widget.configure(state="disabled" if closing else "normal")
        update_scene_state()
        if workflow.select() == str(library_tab):
            update_library_readiness()
        if workflow.select() == str(explore_tab):
            explore_controls.refresh_context()
        if explore_controls.enabled.get() or workflow.select() == str(explore_tab):
            explore_controls.set_radar_observed(cli_radar_status()["observed"])
        activity_controls.refresh()
        nearby_button.configure(state="disabled" if busy or closing or markers.running() else "normal")
        if markers.running():
            if live_pose.get() and not busy and not closing:
                read_beacon_pose_display()
            elif not live_pose.get() and explore_controls.latest_pose is not None:
                exploration_sample = None
                explore_controls.unavailable("Live pose paused")
        else:
            live_pose_option.configure(text="Live pose (1 s)")
            if beacon_display_active:
                exploration_sample = None
                explore_controls.unavailable("beacon reader ended")
                last_pose = last_y = None
                stamp = "; last sample " + beacon_pose_stamp if beacon_pose_stamp else ""
                set_pose_unavailable("beacon reader ended; waiting for idle pose" + stamp)
                beacon_display_active = beacon_pose_available = False
                beacon_pose_token = beacon_pose_stamp = None
                redraw()
        if (live_pose.get() and not busy and not observing and not closing
                and time.monotonic() >= next_live_at and not markers.running()):
            observing = True
            next_live_at = time.monotonic() + 1
            threading.Thread(target=worker, args=("live",), daemon=False).start()
        if (adapter is not None and not busy and not observing and not zone_observing and not closing
                and time.monotonic() >= next_zone_at):
            zone_observing = True
            next_zone_at = time.monotonic()+15
            threading.Thread(target=worker, args=("zone-live",), daemon=False).start()
        update_header_state()
        window.after(80, poll)

    def select_point(_, *, force_name=False, discard_draft=False):
        nonlocal added_selection
        selected = table.selection()
        if draft_pending() and not discard_draft:
            if selected != (form_item,):
                table.selection_set(form_item)
                state.set("Apply or Reset fields before selecting another waypoint.")
            update_edit_state()
            return
        if len(selected) == 1:
            fill_fields(selected[0])
        else:
            fill_fields()
        redraw()

    def select_clicked(event):
        nonlocal added_selection
        added_selection = None
        select_point(event, force_name=True)

    def save_shortcut(save_as=False):
        if not busy and not closing:
            save_route(save_as)
        return "break"

    def edit_point_shortcut(_):
        if not busy and not closing and cli_action is None and len(table.selection()) == 1:
            workflow.select(edit_tab)
            if not draft_pending(): select_point(None, force_name=True)
            point_entries[0].focus_set()
            point_entries[0].selection_range(0, "end")
        return "break"

    def move_point_shortcut(_, direction):
        if not busy and not closing:
            move_point(direction)
        return "break"

    def remove_points_shortcut(_):
        if not busy and not closing:
            remove_points()
        return "break"

    def update_selected_shortcut(_):
        if not busy and not closing:
            update_selected()
        return "break"

    def point_tooltip(item):
        if not item or not table.exists(item): return "Select a row or a preview marker. Double-click a row or press F2 to edit."
        label,px,pz=table.item(item,"values")
        number=table.index(item)+1
        details=route_heights()
        height=details[number-1] if number<=len(details) else None
        evidence=("Measured height" if height and height["heightKind"]=="measured" else "Estimated height"
                  if height and height.get("height") is not None else "Height unknown")
        distance=math.hypot(float(px)-last_pose[0],float(pz)-last_pose[1]) if last_pose else None
        return f"Point {number} / {len(table.get_children())}: {label}\nX {px} / Z {pz}\n"+(
            f"From player: {distance:.2f} units (cached)\n" if distance is not None else "Player position unavailable\n")+(
            f"{evidence} · {height['label']}\n" if height else "")+"Double-click a row or press F2 to edit."

    table_hover=[None]
    live_pose_option.configure(command=change_live_pose)
    attach_path_tooltip(status_label,lambda:state.get())
    attach_path_tooltip(status_details,lambda:"Open Activity for complete status messages, receipts and errors.")
    attach_path_tooltip(draft_notice,lambda:"This waypoint has unapplied fields. Open Edit waypoint, then Apply or Reset before another action.")
    attach_path_tooltip(edit_buttons["New point"],lambda:"Clear the selection and fields to enter a new waypoint. Apply or Reset existing edits first; the route is unchanged.")
    attach_path_tooltip(connection_label,lambda:
        json.dumps(getattr(adapter,"target",None),indent=2) if adapter is not None else "Waiting for a verified local RIFT process.")
    attach_path_tooltip(pose_label,lambda:json.dumps(cli_pose(),indent=2))
    attach_path_tooltip(pose_badge_label,lambda:json.dumps(cli_pose(),indent=2))
    attach_path_tooltip(live_pose_option,lambda:"Use the existing beacon reader while it runs; otherwise read pose every second. Pausing keeps a clearly cached display and sends no game input.")
    attach_path_tooltip(stop_button,lambda:cli_controls()["qualification"]+"\n"+
        "STOP also cancels recording and hides this helper's overlays. Stop Recording saves instead. Esc works while this app has focus; F8 is registered only for an owned movement action.")
    table.bind("<Motion>",lambda event:table_hover.__setitem__(0,table.identify_row(event.y)))
    attach_path_tooltip(table,lambda:point_tooltip(table_hover[0] or (table.selection()[0] if table.selection() else None)))
    def preview_hover(event):
        from scripts.waypoint_map import hit_test_route
        hit=hit_test_route(map_render,event.x,event.y)
        map_hover[0]=hit["identifier"] if hit else None
        allowed=not busy and not closing and cli_action is None and not draft_pending()
        canvas.configure(cursor="hand2" if allowed and hit else "crosshair" if allowed and map_view is not None else "arrow")
    canvas.bind("<Motion>",preview_hover)
    attach_path_tooltip(canvas,lambda:point_tooltip(map_hover[0]) if map_hover[0] else
        "Player-relative cached reference; no terrain or obstacle clearance. Click a marker to select it; click open space to add a point after a fresh pose check.")
    attach_path_tooltip(fit_button,lambda:f"Fit route around the cached player position, capped at {ZOOM_RADII[-1]} units. "+(
        "Some points require a larger view than this preview allows." if cli_preview_status()["fitLimited"] else "Zoom never changes the route or movement limits."))
    attach_path_tooltip(route_status_label,lambda:str(route_path) if route_path else "Current route has no saved file.")
    def keep_selection_visible(_):
        if table.winfo_height()>=24*len(table.get_children())+32:
            table.yview_moveto(0)
        elif len(table.selection())==1: table.see(table.selection()[0])
    table.bind("<Configure>",keep_selection_visible)

    window.bind("<Control-s>", lambda _: save_shortcut())
    window.bind("<Control-Shift-S>", lambda _: save_shortcut(True))
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _: request_stop())
    canvas.bind("<Configure>", redraw)
    canvas.bind("<Button-1>", map_click)
    table.bind("<<TreeviewSelect>>", select_point)
    table.bind("<ButtonRelease-1>", select_clicked)
    table.bind("<Control-z>", undo_edit)
    table.bind("<F2>", edit_point_shortcut)
    table.bind("<Double-1>", edit_point_shortcut)
    table.bind("<Alt-Up>", lambda event: move_point_shortcut(event, -1))
    table.bind("<Alt-Down>", lambda event: move_point_shortcut(event, 1))
    table.bind("<Delete>", remove_points_shortcut)
    for entry in point_entries:
        entry.bind("<Control-Return>", update_selected_shortcut)
        entry.bind("<Return>", update_selected_shortcut)
    for variable in (name, x, z):
        variable.trace_add("write", lambda *_: None if form_loading else update_edit_state())
    if last_route.exists():
        try:
            history = json.loads(last_route.read_text(encoding="utf-8"))
            history = history.get("recentPaths", []) if isinstance(history, dict) else []
            if isinstance(history, list):
                for value in history:
                    source = local_source_path(value)
                    if source is not None and not any(str(source).casefold() == old.casefold() for old in recent_paths):
                        recent_paths.append(str(source))
                        if len(recent_paths) == 8:
                            break
            recent_dropdown.configure(values=route_labels(recent_paths))
            if recent_paths:
                recent_dropdown.current(0)
                recent_load_button.configure(state="normal")
        except (OSError, ValueError, TypeError):
            pass  # Damaged history does not prevent route recovery.
    if args.route:
        try:
            document = prepared_document(json.loads(args.route.read_text(encoding="utf-8")))
            progress = select_progress(document)
            show_document(document)
            pending_progress_selection = current_identity() is None
            if progress is not None:
                display_progress(progress)
            mark_saved(args.route)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if getattr(args, "cli", False):
                raise
            messagebox.showerror("Cannot load route", str(exc))
    restored_checkpoint = False
    if checkpoint.exists():
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if not args.route:
                from scripts.waypoint_progress import RouteProgress
                saved_progress = RouteProgress.load(checkpoint, saved["route"], saved["identity"])
                show_document(saved_progress.document)
                route_recovered = True
                update_route_status()
                restored_checkpoint = True
                pending_progress_selection = current_identity() is None
            restore_progress()
            restored_checkpoint = True
        except (OSError, ValueError, KeyError, TypeError):
            progress_text.set("Saved progress unavailable; load a route to continue.")
    cached_document = cached_source = None
    if not args.route and last_route.exists():
        try:
            snapshot = json.loads(last_route.read_text(encoding="utf-8"))
            if isinstance(snapshot, dict) and "waypoints" not in snapshot:
                if snapshot.get("version") != 1:
                    raise ValueError("Invalid last-route snapshot")
                cached_document, cached_source = snapshot["route"], snapshot.get("sourcePath")
            else:
                cached_document = snapshot
            cached_document = prepared_document(cached_document)
            if "pointMeasurements" in cached_document:
                from scripts.waypoint_measurements import document_measurements
                raw = cached_document["pointMeasurements"]
                measured = document_measurements(cached_document)
                if (not isinstance(raw, list) or len(raw) != len(cached_document["waypoints"])
                        or any(receipt is not None and parsed is None for receipt, parsed in zip(raw, measured))):
                    raise WaypointError("Invalid cached waypoint measurement list")
        except (OSError, ValueError, KeyError, TypeError):
            cached_document = None
            if not restored_checkpoint:
                progress_text.set("Last saved route unavailable; load a route to continue.")
    if not args.route and not restored_checkpoint and cached_document is not None:
        try:
            # A corrupt active checkpoint stays available for diagnosis. With
            # no active cursor, recover this cached route's archived progress
            # only after the whole document and current owner are verified.
            progress = None
            if not checkpoint.exists():
                pending_progress_selection = current_identity() is None
                if not pending_progress_selection:
                    progress = select_progress(cached_document)
            show_document(cached_document)
            route_recovered = True
            update_route_status()
            playback_view = None
            if progress is not None:
                display_progress(progress)
            else:
                progress_text.set("Last saved route restored; choose Play Forward or Play Reverse.")
            redraw()
        except (OSError, ValueError, KeyError, TypeError):
            progress_text.set("Last saved route unavailable; load a route to continue.")
    if not args.route and cached_document is not None and cached_source:
        try:
            source = local_source_path(cached_source)
            if (source is not None and json.loads(json.dumps(route_document())) == cached_document
                    and json.loads(source.read_text(encoding="utf-8")) == cached_document):
                mark_saved(source)
        except (OSError, ValueError, KeyError, TypeError):
            pass  # Keep recovered content unbound if the source is unavailable or changed.
    cli_server = LocalSessionServer(launch_token=getattr(args, "launch_token", None))
    diagnostics.set_context(sessionId=cli_server.session_id, riftTarget=deepcopy(getattr(adapter, "target", None)))
    diagnostics.info("Waypoint window ready")
    previous_callback_handler = window.report_callback_exception
    def callback_exception(exc_type, exc_value, exc_tb):
        diagnostics.exception("GUI callback failed", exc=exc_value.with_traceback(exc_tb))
        if busy:
            stop.set()
            record_cancel.set()
            record_stop.set()
        state.set("Unexpected UI error recorded. Open Activity for logs and diagnostics.")
        if sys.stderr is not None or getattr(previous_callback_handler, "__module__", "") != "tkinter":
            previous_callback_handler(exc_type, exc_value, exc_tb)
    window.report_callback_exception = callback_exception
    explore_controls.extra_settings["statusPath"] = str(cli_server.path / "radar-status.json")
    explore_controls.save()
    refresh_library()
    update_context_text()
    poll()
    start("refresh")
    try:
        window.mainloop()
    finally:
        cli_server.close()


def main(argv=None):
    from scripts.waypoint_progress import write_json_atomic
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--basis", type=Path, default=DEFAULT_BASIS)
    parser.add_argument("--route", type=Path, help="load a waypoint JSON into the window without running it")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--go", nargs=2, type=float, metavar=("X", "Z"))
    mode.add_argument("--run-route", type=Path, help="run a saved waypoint JSON with --execute")
    mode.add_argument("--play-route", type=Path, help="approach a recorded route start within 20 units, then replay with --execute")
    mode.add_argument("--face-bearing", type=float, help="face this +Z-to-+X bearing without walking")
    parser.add_argument("--face-waypoints", action="store_true", help="turn toward each waypoint and walk forward")
    parser.add_argument("--movement-engine", choices=("continuous", "pulse"), default="continuous",
                        help="continuous forward travel (default) or the original bounded pulse controller; teaching uses pulse")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--record-to", type=Path, help="save observed movement from this --go/--run-route")
    parser.add_argument("--reverse", action="store_true", help="replay from recorded end toward start")
    parser.add_argument("--progress", type=Path, help="recorded-route progress checkpoint")
    parser.add_argument("--resume", action="store_true", help="resume saved unfinished recorded route")
    args = parser.parse_args(argv)
    cli_action = (args.go is not None or args.face_bearing is not None or
                  args.run_route is not None or args.play_route is not None)
    if args.route is not None and cli_action:
        parser.error("--route cannot be combined with --go / --face-bearing / --run-route / --play-route")
    if (args.reverse or args.resume or args.progress) and args.play_route is None:
        parser.error("--reverse / --resume / --progress requires --play-route")
    if args.record_to is not None and args.go is None and args.run_route is None:
        parser.error("--record-to requires --go or --run-route")
    if not cli_action:
        launch_window(args)
        return 0
    if not args.execute:
        parser.error("--go / --face-bearing / --run-route / --play-route requires --execute; omit them to open the window")
    stop = threading.Event()
    adapter, checkpoint = None, None
    history = []

    def emit(event):
        history.append(dict(event))
        print(json.dumps({k: v for k, v in event.items() if k not in ("actions", "segments")}), flush=True)

    try:
        if args.record_to is not None and args.record_to.exists():
            raise WaypointError("Recording output already exists; choose a new path")
        adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
        runner = run_route
        if args.movement_engine == "continuous" and args.record_to is None:
            from scripts.continuous_move import run_continuous_route
            runner = run_continuous_route
        with cli_stop_controls(stop):
            if args.run_route is not None or args.play_route is not None or args.record_to is not None:
                path = args.play_route or args.run_route
                document = json.loads(path.read_text(encoding="utf-8")) if path else {"waypoints": [("Waypoint", *args.go)]}
                points = route_points(document["waypoints"])
                started = time.monotonic()
                if args.play_route:
                    from scripts.waypoint_playback import play_route
                    checkpoint = args.progress or args.play_route.with_suffix(".progress.json")
                    legs, _ = play_route(adapter, document, stop, emit, runner=runner,
                                        checkpoint=checkpoint, direction="reverse" if args.reverse else "forward",
                                        resume=args.resume, face_waypoints=args.face_waypoints, approach_start=True)
                elif args.record_to:
                    from scripts.waypoint_playback import teach_route
                    legs, recorded = teach_route(adapter, points, stop, emit, runner=run_route,
                                                 face_waypoints=args.face_waypoints)
                    args.record_to.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
                    emit({"status": "recorded", "path": str(args.record_to), "points": len(recorded["waypoints"])})
                else:
                    legs = runner(adapter, points, stop, emit, face_waypoints=args.face_waypoints)
                held = [leg.get("totalHoldMs") for leg in legs]
                result = {"status": "arrived", "waypointCount": len(legs),
                          "position": legs[-1]["position"], "bearing": legs[-1]["bearing"],
                          "distance": legs[-1]["distance"], "legs": legs,
                          "pulses": sum(leg.get("pulses", 0) for leg in legs),
                          "totalHoldMs": sum(held) if all(type(value) in (int, float) for value in held) else None,
                          "movementEngine": "pulse" if args.record_to else args.movement_engine,
                          "elapsedSeconds": round(time.monotonic()-started, 3),
                          "calibrationBinding": getattr(adapter, "binding", None),
                          "allInputsReleased": True,
                          "allPulsesReleased": True if args.record_to or args.movement_engine == "pulse" else None}
            else:
                result = (run_facing(adapter, stop, emit, bearing=args.face_bearing)
                          if args.face_bearing is not None else
                          runner(adapter, [("Waypoint", *args.go)], stop, emit,
                                    face_waypoints=args.face_waypoints)[0])
        output = ROOT / "artifacts" / ("waypoint-run-" + uuid.uuid4().hex + ".json")
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"status": result["status"], "receipt": str(output)}))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        stop.set()
        original_reason = str(exc)
        is_stop = isinstance(exc, Stopped)
        verification = verify_stopped_pose(adapter, after="STOP" if is_stop else "halt") if adapter is not None else None
        reason = original_reason
        if is_stop and verification and verification["status"] != "pass":
            reason = ("STOP requested; stationary check unavailable: " + verification["reason"]
                      if verification["status"] == "unavailable" else verification["reason"])
        failure = {"status": "stopped" if isinstance(exc, Stopped) and verification and verification["status"] == "pass" else "halted",
                   "reason": reason, "originalReason": original_reason,
                   "inputReceiptPath": str(adapter.input_receipt_path) if adapter is not None and hasattr(adapter, "input_receipt_path") else None,
                   "checkpointPath": str(checkpoint) if checkpoint is not None else None}
        receipt = {**failure, "failure": dict(failure), "events": history,
                   "completedLegs": [event for event in history if event.get("status") == "arrived"],
                   "calibrationBinding": getattr(adapter, "binding", None), "stopVerification": verification,
                   "releaseVerification": "see individual native input receipts for key release; measured stationary evidence is separate in stopVerification"}
        output = ROOT / "artifacts" / ("waypoint-run-" + uuid.uuid4().hex + ".json")
        try:
            write_json_atomic(output, receipt)
            failure["receipt"] = str(output)
        except (OSError, ValueError, TypeError) as write_error:
            failure["receiptError"] = str(write_error)
        print(json.dumps(failure), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
