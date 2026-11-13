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

from scripts import physical_rift
from scripts.movement_controller import Position, WaypointController, planar_distance
from scripts.nav_physical_reservation import PhysicalClientIdentity, PhysicalClientReservation
from scripts.physical_move_basis_waypoint import read_basis, candidate_calibrations
from scripts.waypoint_map import LocalMap, ZOOM_RADII, draw_route, fit_route_radius, route_length
from scripts.waypoint_heading import choose_turn, heading_error
from scripts.waypoint_seed_feedback import verify_translation, verify_turn

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
        self.stop_requested = False
        self.exit_code = None

    def running(self):
        if self.child is not None:
            result = self.child.poll()
            if result is not None:
                self.exit_code = result
                self.child = None
        return self.child is not None

    def start(self, document, adapter, *, target_beacon=False, landmark_number=None):
        if type(target_beacon) is not bool:
            raise WaypointError("Invalid target beacon option")
        if landmark_number is not None and (type(landmark_number) is not int
                or not 1 <= landmark_number <= len(document.get("waypoints", []))):
            raise WaypointError("Select one saved marker to guide to")
        if self.running():
            raise WaypointError("Markers are already open or closing")
        from scripts.live_physical_waypoints import load_route
        from scripts.waypoint_progress import write_json_atomic
        token = uuid.uuid4().hex
        directory = self.root / "artifacts"
        route_path = directory / ("waypoint-markers-route-" + token + ".json")
        self.output = directory / ("waypoint-markers-summary-" + token + ".json")
        self.stop_path = directory / ("waypoint-markers-stop-" + token + ".signal")
        write_json_atomic(route_path, document)
        recorded = load_route(route_path)
        identity = adapter.binding["runtimeIdentity"]
        if any(str(recorded["identity"].get(key, "")).casefold() != str(identity[key]).casefold()
               for key in ("machine", "gameBuildSha256", "unitKey")):
            raise WaypointError("Recorded route belongs to another host, build or player")
        target = adapter.target
        if (identity["processId"] != adapter.pid or identity["processId"] != target["processId"]
                or str(identity["processStartUtcTicks"]) != str(target["processStartUtcTicks"])
                or identity["gameBuildSha256"].casefold() != target["executableSha256"].casefold()
                or type(target["hwnd"]) is not int or target["hwnd"] <= 0):
            raise WaypointError("Current RIFT identity is unavailable")
        qt_executable = self.root / ".local" / "overlay-venv" / "Scripts" / "pythonw.exe"
        presenter = "qt" if qt_executable.is_file() else "native"
        executable = qt_executable if presenter == "qt" else Path(sys.executable).with_name("pythonw.exe")
        command = [str(executable), str(self.root / "scripts" / "live_physical_waypoints.py"),
                   "--expected-host", identity["machine"], "--physical-pid", str(adapter.pid),
                   "--expect-start-ticks", str(target["processStartUtcTicks"]),
                   "--expect-sha256", target["executableSha256"], "--expect-hwnd", hex(target["hwnd"]),
                   "--route", str(route_path), "--duration", "600", "--max-age", ".35", "--presenter", presenter,
                   "--output", str(self.output), "--stop-file", str(self.stop_path),
                   "--progress-file", str(self.root / "artifacts" / "waypoint-current-progress.json")]
        if target_beacon:
            command.append("--target-beacon")
        if landmark_number is not None:
            command.extend(["--landmark-number", str(landmark_number)])
        self.child = self.popen(command, cwd=self.root,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.stop_requested = False
        self.exit_code = None

    def stop(self):
        if self.running() and not self.stop_requested:
            self.stop_path.touch(exist_ok=False)
            self.stop_requested = True


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
        if time.monotonic() - self.started > 120:
            raise WaypointError("Trip exceeded 120 seconds")
        if action is not None and (self.pulses >= 64 or self.hold_ms + action.hold_ms > 9000):
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
                        events.put({"status": "stopping", "reason": "F8 STOP requested; waiting for the bounded pulse to finish."})
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
              "headingError": error, "key": action.key, "holdMs": action.hold_ms})
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
            if distance > 20:
                raise WaypointError("Facing waypoint exceeds 20 units")
            bearing = (math.degrees(math.atan2(px-current.position.x, pz-current.position.z))
                       if distance > .3 else current.bearing)
        target = heading_error(finite(bearing), 0)
        started = time.monotonic()
        current, actions = align_heading(adapter, target, current, stop, lease,
                                        TripBudget(started), emit)
        result = {"status": "facing", "position": asdict(current.position),
                  "bearing": current.bearing, "targetBearing": target,
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
              "distance": planar_distance(current.position, goal)})
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
                  "distance": feedback.distance_after, "pulse": len(actions), "bearing": current.bearing,
                  "key": action.key, "holdMs": action.hold_ms})


def route_points(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise WaypointError("Route must have 1–20 points")
    if any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in rows):
        raise WaypointError("Each point needs name, X and Z")
    return [(str(row[0])[:80], finite(row[1]), finite(row[2])) for row in rows]


def run_route(adapter, points, stop, emit=lambda event: None, *, face_waypoints=False,
              entry_check=None):
    """Follow up to 20 units of route using <=4-unit intermediate targets.

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
        if planned > 20:
            raise WaypointError("Route exceeds 20 world units; choose a shorter route")
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


def launch_window(args):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk()
    from scripts.waypoint_ui_theme import PALETTE, apply_theme, summarize_status
    apply_theme(window)
    from scripts.waypoint_connection import idle_read
    from scripts.waypoint_observation import observe_batch
    from scripts.waypoint_recording import RouteRecorder
    from scripts.waypoint_playback import play_route
    from scripts.waypoint_progress import _route as progress_route, write_json_atomic

    window.title(f"RR2 Waypoints — {args.expected_host} / "
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
    brand_context = ttk.Frame(brand)
    brand_context.pack(anchor="w")
    ttk.Label(brand_context, text="RIFT / READER 2", style="Base.Micro.TLabel").pack(side="left")
    connection_text = tk.StringVar(value=f"{args.expected_host}  /  "
        + (f"PID {args.physical_pid}" if args.physical_pid is not None else "Waiting for RIFT"))
    ttk.Label(brand_context, textvariable=connection_text, style="Base.Muted.TLabel").pack(side="left", padx=(12, 0))
    ttk.Label(brand, text="Waypoints", style="Brand.TLabel").pack(anchor="w")
    header_actions = ttk.Frame(header)
    header_actions.grid(row=0, column=1, sticky="e", padx=(12, 16))
    stop_slot = ttk.Frame(header)
    stop_slot.grid(row=0, column=2, sticky="e")
    state = tk.StringVar(value=("Waiting for RIFT: " + args.initial_reason
                                if getattr(args, "initial_reason", None) else
                                "Ready — save a point, click the map, or enter X / Z."))
    status_brief = tk.StringVar(value=summarize_status(state.get()))
    state.trace_add("write", lambda *_: status_brief.set(summarize_status(state.get())))
    status_strip = ttk.Frame(frame, style="Card.TFrame", padding=(14, 6))
    status_strip.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    status_label = ttk.Label(status_strip, textvariable=status_brief, style="Gold.TLabel", wraplength=900)
    status_label.pack(anchor="w")
    status_strip.bind("<Configure>", lambda event: status_label.configure(wraplength=max(200, event.width - 28)))
    pose_text = tk.StringVar(value="Position is loading…")
    telemetry = ttk.Frame(frame)
    telemetry.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(telemetry, textvariable=pose_text, style="Telemetry.TLabel").pack(anchor="w")
    route_status = tk.StringVar(value="New route — Unsaved")
    editable = []
    workflow = ttk.Notebook(frame, height=184)
    workflow.grid(row=4, column=0, sticky="ew", pady=(10, 6))
    replay_tab, edit_tab, scene_tab, activity_tab = [ttk.Frame(workflow, style="Surface.TFrame", padding=(14, 8)) for _ in range(4)]
    for tab, title in ((replay_tab, "Replay"), (edit_tab, "Edit waypoint"),
                       (scene_tab, "Scene & beacons"), (activity_tab, "Activity")):
        workflow.add(tab, text=title)
    coordinates = ttk.Frame(edit_tab, style="Surface.TFrame")
    coordinates.pack(fill="x", pady=(0, 12))
    name, x, z = tk.StringVar(value="Point 1"), tk.StringVar(), tk.StringVar()
    walk_facing = tk.BooleanVar(value=args.face_waypoints)
    target_beacon = tk.BooleanVar(value=False)
    landmark_guide = tk.BooleanVar(value=False)
    live_pose = tk.BooleanVar(value=True)
    view_bring_forward = tk.BooleanVar(value=False)
    view_include_units = tk.BooleanVar(value=False)
    point_entries = []
    for label, variable, width in (("Name", name, 26), ("X", x, 18), ("Z", z, 18)):
        ttk.Label(coordinates, text=label, style="Surface.TLabel").pack(side="left", padx=(0, 5))
        entry = ttk.Entry(coordinates, textvariable=variable, width=width)
        entry.pack(side="left", padx=(0, 10))
        editable.append(entry)
        point_entries.append(entry)
    ttk.Checkbutton(header_actions, text="Live pose (2 s)", variable=live_pose).pack(anchor="e", pady=(7, 0))
    summary = tk.StringVar(value="Refresh position to preview the route.")
    summary_label = ttk.Label(telemetry, textvariable=summary, style="Base.Muted.TLabel", wraplength=900)
    summary_label.pack(anchor="w", pady=(3, 0))
    telemetry.bind("<Configure>", lambda event: summary_label.configure(wraplength=max(200, event.width)))
    middle = ttk.Frame(frame)
    middle.grid(row=3, column=0, sticky="nsew")
    middle.columnconfigure(0, weight=3)
    middle.columnconfigure(1, weight=2)
    middle.rowconfigure(0, weight=1)
    route_card = ttk.Frame(middle, style="Card.TFrame", padding=12)
    route_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    route_card.columnconfigure(0, weight=1)
    route_card.rowconfigure(3, weight=1)
    route_heading = ttk.Frame(route_card, style="Surface.TFrame")
    route_heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(route_heading, text="YOUR ROUTE", style="Eyebrow.TLabel").pack(side="left", padx=(0, 12))
    route_status_label = ttk.Label(route_heading, textvariable=route_status, style="Gold.TLabel", wraplength=360)
    route_status_label.pack(side="left")
    route_heading.bind("<Configure>", lambda event: route_status_label.configure(wraplength=max(140, event.width - 100)))
    file_toolbar = ttk.Frame(route_card, style="Surface.TFrame")
    file_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
    recent_controls = ttk.Frame(route_card, style="Surface.TFrame")
    recent_controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    recent_controls.columnconfigure(1, weight=1)
    tree_frame = ttk.Frame(route_card, style="Surface.TFrame")
    tree_frame.grid(row=3, column=0, sticky="nsew")
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)
    table = ttk.Treeview(tree_frame, columns=("name", "x", "z"), show="headings", height=4)
    for col, label, width in (("name", "Waypoint", 220), ("x", "X", 120), ("z", "Z", 120)):
        table.heading(col, text=label)
        table.column(col, width=width)
    table.grid(row=0, column=0, sticky="nsew")
    tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=table.yview)
    tree_scroll.grid(row=0, column=1, sticky="ns")
    table.configure(yscrollcommand=tree_scroll.set)
    map_frame = ttk.Frame(middle, style="Card.TFrame", padding=12)
    map_frame.grid(row=0, column=1, sticky="nsew")
    ttk.Label(map_frame, text="LOCAL PREVIEW", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 10))
    canvas = tk.Canvas(map_frame, width=330, height=220, bg="#0b1723", highlightthickness=0)
    map_hint = ttk.Frame(map_frame, style="Surface.TFrame")
    # Reserve the toolbar before the expandable canvas consumes compact height.
    map_hint.pack(side="bottom", fill="x", pady=(4, 0))
    canvas.pack(fill="both", expand=True)
    ttk.Label(map_hint, text="Click to add", style="Surface.TLabel").pack(side="left", padx=(0, 6))
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
    recording_progress = None
    pending_recorded = None
    closing = False
    adapter = getattr(args, "initial_adapter", None)
    published_adapter = adapter
    foreground_stop = None
    last_pose = None
    last_y = None
    verified_adapter = None
    verified_at = None
    identity_unavailable = False
    saved_view = None
    saved_unit_sample = None
    nearby_picker = None
    saved_rerun = None
    rerun_viewer = None
    markers = OwnedWaypointMarkers(ROOT)
    marker_identity = None
    map_view = None
    observing = False
    next_live_at = time.monotonic() + 2
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
    from scripts.waypoint_recent_display import route_labels, attach_path_tooltip
    activity_tab.columnconfigure(0, weight=1)
    activity_tab.rowconfigure(1, weight=1)
    full_status_label = ttk.Label(activity_tab, textvariable=state, wraplength=860, style="Muted.TLabel")
    full_status_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    activity_tab.bind("<Configure>", lambda event: full_status_label.configure(wraplength=max(200, event.width - 30)))
    log = tk.Text(activity_tab, height=5, state="disabled", font=("Consolas", 10),
                  background="#0b1723", foreground="#dce8ef", insertbackground="#8dedc8",
                  relief="flat", borderwidth=0, padx=10, pady=8, wrap="word")
    log.grid(row=1, column=0, sticky="nsew")
    log_scroll = ttk.Scrollbar(activity_tab, command=log.yview)
    log_scroll.grid(row=1, column=1, sticky="ns")
    log.configure(yscrollcommand=log_scroll.set)

    def update_route_status():
        title = route_path.name if route_path is not None else "Recovered route" if route_recovered else "New route"
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
        nonlocal route_metadata, playback_view, route_dirty
        if not loading_route:
            if not stop_markers():
                raise WaypointError("Cannot stop markers; route unchanged")
            if table.get_children():
                from scripts.waypoint_progress import invalidate_route_progress
                # Editing the local route invalidates only the cursor belonging to
                # its known player, even when the last pose is too old for Resume.
                invalidate_route_progress(checkpoint, progress_archive, route_document(),
                                          current_identity() or last_verified_owner)
            if clear_metadata:
                route_metadata = {}
            playback_view = None
            route_dirty = True
            update_route_status()
            progress_text.set("No saved progress; choose Play Forward or Play Reverse.")

    def add_point(label, px, pz):
        nonlocal added_selection
        if len(table.get_children()) >= 20:
            state.set("Waypoint list is full; remove a point before adding another.")
            return
        px, pz = finite(px), finite(pz)
        remember_edit()
        invalidate_progress()
        item = table.insert("", "end", values=(label, f"{finite(px):.6f}", f"{finite(pz):.6f}"))
        added_selection = item
        table.selection_set(item)
        name.set(f"Point {len(table.get_children()) + 1}")
        x.set(f"{finite(px):.6f}")
        z.set(f"{finite(pz):.6f}")
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
        if busy or closing or not edit_history:
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
            text = success + "; last-route snapshot could not be saved: " + str(exc)
        state.set(text)
        log.configure(state="normal")
        log.insert("end", text + "\n")
        log.see("end")
        log.configure(state="disabled")

    def show_document(document):
        nonlocal loading_route, route_metadata
        from scripts.waypoint_measurements import document_measurements
        parsed = route_points(document["waypoints"])
        receipts = document_measurements(document)
        if not stop_markers():
            raise WaypointError("Cannot stop markers; route unchanged")
        loading_route = True
        try:
            table.delete(*table.get_children())
            point_receipts.clear()
            for row, receipt in zip(parsed, receipts):
                item = add_point(*row)
                if receipt is not None:
                    point_receipts[item] = deepcopy(receipt)
            route_metadata = {k: v for k, v in document.items() if k != "waypoints"}
            name.set(f"Point {len(table.get_children()) + 1}")
        finally:
            loading_route = False
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
        progress_text.set(f"Saved progress: {index} / {count}; {hint}")
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
            state.set("Cannot restore saved progress: " + str(exc))

    def prepared_document(document):
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
        if last_pose is None:
            return
        map_radius = fit_route_radius(*last_pose[:2], selected_points(True))
        redraw()

    def redraw(*_):
        nonlocal map_view
        radius_text.set(f"{map_radius:g} units")
        zoom_in.configure(state="disabled" if map_radius == ZOOM_RADII[0] else "normal")
        zoom_out.configure(state="disabled" if map_radius == ZOOM_RADII[-1] else "normal")
        fit_button.configure(state="normal" if last_pose is not None else "disabled")
        undo_button.configure(state="normal" if edit_history and not busy and not closing else "disabled")
        points = [(item, *table.item(item, "values")) for item in table.get_children()]
        original_points = points[:]
        completed, active = None, None
        if playback_view is not None:
            if playback_view["direction"] == "reverse":
                points.reverse()
            index = max(0, min(len(points), playback_view["nextIndex"]))
            completed = {row[0] for row in points[:index]}
            active = points[index][0] if index < len(points) else None
        for row in points:
            table.item(row[0], tags=("next",) if row[0] == active else
                       ("completed",) if completed is not None and row[0] in completed else ())
        if last_pose is None:
            map_view = None
            draw_route(canvas, None, [], set())
            summary.set("Position unavailable; refresh to preview the route.")
            if not busy:
                for button in (go_button, route_button, face_button, record_button,
                               forward_button, reverse_button, resume_button, teach_button):
                    button.configure(state="disabled")
            return
        map_view = LocalMap(*last_pose, max(100, canvas.winfo_width()), max(100, canvas.winfo_height()), map_radius)
        draw_route(canvas, map_view, points, set(table.selection()), completed=completed, active=active)
        remaining = points[index:] if playback_view is not None else points
        distance = route_length(*last_pose[:2], [row[1:] for row in remaining])
        planned_distance = route_length(*last_pose[:2], selected_points(True))
        selected = selected_points()
        chosen = route_length(*last_pose[:2], selected) if selected else None
        if recording_progress is not None:
            summary.set(f"Recording: {recording_progress['observedPathLength']:.2f} / 20 units"
                        f"   •   {recording_progress['sampleCount']} samples"
                        + ("   •   Stop Recording saves" if recording else "   •   STOP cancels"))
        else:
            endpoints = ""
            if not busy and not recording and original_points:
                distances = [math.hypot(finite(row[2]) - last_pose[0], finite(row[3]) - last_pose[1])
                             for row in (original_points[0], original_points[-1])]
                endpoints = f"   •   Start: {distances[0]:.2f} • End: {distances[1]:.2f} units"
            summary.set(f"{'Remaining' if playback_view is not None else 'Route'}: {distance:.2f} / 20 units"
                        + (f"   •   Selected: {chosen:.2f} units" if chosen is not None else "")
                        + endpoints
                        + (f"   •   3D: measured heights {sum(1 for row in original_points if point_receipts.get(row[0]) is not None)} / {len(original_points)}"
                           if original_points else "")
                        + ("   •   Shorten the route to run it" if distance > 20 else ""))
        if not busy:
            go_button.configure(state="normal" if selected and chosen <= 20 else "disabled")
            route_button.configure(state="normal" if points and planned_distance <= 20 else "disabled")
            teach_button.configure(state="normal" if points and planned_distance <= 20 else "disabled")
            face_button.configure(state="normal" if len(selected) == 1 and .3 < chosen <= 20 else "disabled")
            record_button.configure(state="normal")
            def can_play(reverse=False):
                if not original_points:
                    return False
                rows = [row[1:] for row in (reversed(original_points) if reverse else original_points)]
                endpoint = rows[0]
                if math.hypot(finite(endpoint[1]) - last_pose[0], finite(endpoint[2]) - last_pose[1]) > .30 + 1e-9:
                    return False
                heights = route_metadata.get("heights")
                if heights is not None:
                    if not isinstance(heights, list) or len(heights) != len(original_points):
                        return False
                    try:
                        height = heights[-1 if reverse else 0]
                        if height is not None and (last_y is None or abs(last_y - finite(height)) > 1):
                            return False
                    except (TypeError, ValueError, IndexError):
                        return False
                return route_length(*last_pose[:2], rows) <= 20
            forward_button.configure(state="normal" if can_play() else "disabled")
            reverse_button.configure(state="normal" if can_play(True) else "disabled")
            resumable = (playback_view is not None and checkpoint.exists()
                         and 0 <= playback_view["nextIndex"] < len(points))
            resume_button.configure(state="normal" if resumable else "disabled")

    def map_click(event):
        if busy or map_view is None:
            return
        px, pz = map_view.canvas_to_world(event.x, event.y)
        start("map", (map_view, px, pz, name.get() or "Waypoint"))

    def worker(operation, points=None, face_walk=False):
        with operation_gate:
            if operation == "live" and closing:
                events.put({"status": "live-idle"})
                return
            perform_operation(operation, points, face_walk)

    def perform_operation(operation, points=None, face_walk=False):
        nonlocal adapter, published_adapter
        retain = operation in ("go", "face", "play", "resume", "teach")
        history, outcome, failure = [], None, None
        stop_verification = None

        def emit(event):
            if retain:
                history.append(dict(event))
            events.put(event)

        try:
            if adapter is None:
                if operation not in ("refresh", "save", "map", "live", "target"):
                    raise WaypointError("RIFT is not connected; wait for a fresh pose")
                adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
            if retain:
                adapter.input_receipt_path = ROOT / "artifacts" / ("waypoint-input-" + uuid.uuid4().hex + ".jsonl")
                adapter.last_input_receipt = None
            if operation in ("refresh", "save", "map", "live", "target"):
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
                if operation == "save" and isinstance(getattr(adapter, "binding", None), dict):
                    try:
                        from scripts.waypoint_measurements import measurement
                        result["measurement"] = measurement(pose.position, adapter.binding, pose.source,
                                                            datetime.now(timezone.utc).isoformat())
                    except (ValueError, KeyError, TypeError, AttributeError):
                        result["measurementReason"] = "Position provenance unavailable; point saved without height."
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
                events.put(result)
            elif operation == "face":
                outcome = run_facing(adapter, stop, emit, point=points[0][1:])
            elif operation == "view":
                from scripts.save_physical_route_view import save_route_view
                document, pid, target, capture_backend, include_units = points
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
                events.put({"status": "view-saved", "image": str(result["image"]),
                            "rerun": result.get("rerun", {}), "unitSample": result.get("unitSample")})
            elif operation == "record":
                recorder = RouteRecorder(adapter.binding)
                while not record_stop.is_set() and not record_cancel.is_set():
                    # The batch revalidates process/build/player/owners itself.
                    # A read-only recorder must not contend for move-key's input
                    # semaphore merely to inspect the window between captures.
                    # The native lease spans the entire paced burst. Leave a
                    # real handoff window for other guarded one-pose readers.
                    for pose in observe_batch(adapter, samples=6):
                        recorder.observe(pose)
                    events.put({"status": "recording", "position": asdict(pose.position),
                                "bearing": pose.bearing, **recorder.progress})
                    record_stop.wait(.15)
                if record_cancel.is_set():
                    raise WaypointError("Recording cancelled; no route saved")
                document = recorder.finish()
                events.put({"status": "recorded-pending", "document": document})
            elif operation == "teach":
                from scripts.waypoint_playback import teach_route
                results, document = teach_route(adapter, points, stop, emit, runner=run_route,
                                                face_waypoints=face_walk)
                outcome = results
                events.put({"status": "recorded-pending", "document": document, "operation": "teach"})
            elif operation in ("play", "resume"):
                document, direction = points
                results, cursor = play_route(adapter, document, stop, emit, runner=run_route,
                                             checkpoint=checkpoint, direction=direction,
                                             resume=operation == "resume", face_waypoints=face_walk)
                outcome = results
                events.put({"status": "route-complete", "waypointCount": len(results),
                            "nextWaypoint": cursor.next_index, "totalWaypoints": len(cursor.ordered_points),
                            "position": results[-1]["position"], "bearing": results[-1]["bearing"],
                            "distance": results[-1]["distance"]})
            else:
                results = run_route(adapter, points, stop, emit, face_waypoints=face_walk)
                outcome = results
                events.put({"status": "route-complete", "waypointCount": len(results),
                            "position": results[-1]["position"], "bearing": results[-1]["bearing"],
                            "distance": results[-1]["distance"]})
        except Exception as exc:
            original_reason = str(exc)
            stopped_position = stopped_bearing = None
            if retain and adapter is not None:
                is_stop = isinstance(exc, Stopped)
                stop_verification = verify_stopped_pose(adapter, after="STOP" if is_stop else "halt")
                if is_stop and stop_verification["status"] == "pass":
                    stopped_position = stop_verification["samples"][-1]["position"]
                    stopped_bearing = stop_verification["samples"][-1]["bearing"]
                elif is_stop and stop_verification["status"] == "unavailable":
                    exc = WaypointError("STOP requested; stationary check unavailable: " + stop_verification["reason"])
                elif is_stop and stop_verification["status"] != "pass":
                    exc = WaypointError(stop_verification["reason"])
            failure = {"status": "live-unavailable" if operation == "live" else "view-failed" if operation == "view" else
                       "stopped" if isinstance(exc, Stopped) else "halted", "reason": str(exc),
                       "originalReason": original_reason,
                       **({"position": stopped_position, "bearing": stopped_bearing} if stopped_position else {}),
                       "inputReceiptPath": str(adapter.input_receipt_path) if adapter else None}
            emit(failure)
        finally:
            if retain:
                receipt = {"operation": operation,
                           "direction": points[1] if operation in ("play", "resume") and points else None,
                           "status": failure["status"] if failure else "completed",
                           "failure": failure, "result": outcome, "events": history,
                           "completedLegs": [event for event in history if event.get("status") == "arrived"],
                           "calibrationBinding": getattr(adapter, "binding", None),
                           "inputReceiptPath": str(adapter.input_receipt_path) if adapter else None,
                           "inputReceiptPresent": bool(adapter and adapter.input_receipt_path.exists()),
                           "stopVerification": stop_verification,
                           "releaseVerification": ("see individual native pulse receipts for key release; measured stationary evidence is separate in stopVerification"
                                                   if failure else "see completed result and pulse receipts")}
                receipt_path = ROOT / "artifacts" / ("waypoint-run-" + uuid.uuid4().hex + ".json")
                try:
                    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                    events.put({"status": "run-receipt", "path": str(receipt_path), "failure": failure})
                except (OSError, TypeError, ValueError) as exc:
                    events.put({"status": "receipt-error", "reason": str(exc), "failure": failure})
            events.put({"status": "live-idle" if operation == "live" else "idle"})

    def start(operation, points=None):
        nonlocal busy, foreground_stop, recording, recording_progress, playback_view, playback_active
        if busy or closing or nearby_picker is not None:
            return
        if operation in ("go", "teach") and (not points or len(points) > 20):
            messagebox.showinfo("Choose waypoints", "Select a waypoint, or add up to 20 points for a route.")
            return
        if operation == "face" and (not points or len(points) != 1):
            state.set("Select one waypoint to face.")
            return
        if operation in ("go", "face", "teach", "record") and markers.running():
            if stop_markers():
                state.set("Markers are closing; try the action again when they are hidden.")
            return
        busy = True
        stop.clear()
        if operation == "teach":
            record_cancel.clear()
            record_stop.clear()
        if operation in ("go", "face", "play", "resume", "teach"):
            try:
                foreground_stop = ForegroundStop(window, stop, events)
            except Exception as exc:
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
            recording = True
            recording_progress = {"sampleCount": 0, "observedPathLength": 0.0}
            record_stop.clear()
            record_cancel.clear()
            record_end_button.configure(state="normal")
            redraw()
        state.set("Starting action — F8 or STOP prevents the next pulse." if operation in ("go", "face", "play", "resume", "teach")
                  else "Recording your movement; choose Stop Recording to save." if operation == "record"
                  else "Saving view…" if operation == "view"
                  else "Reading current RIFT pose…")
        threading.Thread(target=worker, args=(operation, points, walk_facing.get()), daemon=False).start()

    def request_stop():
        stop.set()
        if recording:
            record_cancel.set()
            record_stop.set()
            state.set("Recording cancelled — no route will be saved.")
            return
        markers_stopped = stop_markers()
        text = ("STOP requested — waiting for the current bounded pulse to release." if busy
                else "Stopped — no input active.")
        state.set(text if markers_stopped else text + " Could not hide markers.")

    def add_entered():
        try:
            add_point(name.get() or "Waypoint", x.get(), z.get())
        except (ValueError, TypeError):
            messagebox.showerror("Invalid coordinates", "Enter finite X and Z coordinates.")

    def update_selected():
        nonlocal added_selection
        selected = table.selection()
        if len(selected) != 1:
            state.set("Select one waypoint to update.")
            return
        try:
            label, px, pz = route_points([(name.get() or "Waypoint", x.get(), z.get())])[0]
        except (ValueError, TypeError):
            messagebox.showerror("Invalid coordinates", "Enter finite X and Z coordinates.")
            return
        old = table.item(selected[0], "values")
        if selected[0] == added_selection and name.get() == f"Point {len(table.get_children()) + 1}":
            label = old[0]
        px, pz = float(f"{px:.6f}"), float(f"{pz:.6f}")
        coordinates_changed = (px, pz) != (finite(old[1]), finite(old[2]))
        if label == old[0] and not coordinates_changed:
            state.set("Waypoint unchanged.")
            return
        remember_edit()
        invalidate_progress(clear_metadata=coordinates_changed)
        if coordinates_changed:
            point_receipts.pop(selected[0], None)
        table.item(selected[0], values=(label, f"{px:.6f}", f"{pz:.6f}"))
        added_selection = None
        name.set(label)
        x.set(f"{px:.6f}")
        z.set(f"{pz:.6f}")
        redraw()
        state.set("Waypoint updated; save the route to keep this edit.")

    def save_route(save_as=False):
        path = route_path
        if save_as or path is None:
            options = {"defaultextension": ".json", "initialfile": path.name if path else "rift-waypoints.json"}
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
                messagebox.showerror("Cannot save route", str(exc))
        return False

    def load_from(path):
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
            if not stop_markers():
                raise WaypointError("Cannot stop markers; route unchanged")
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
            messagebox.showerror("Cannot load route", str(exc))

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
        name.set("Point 1")
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
            state.set("Cannot start playback: " + str(exc))

    def stop_recording():
        if recording:
            record_stop.set()
            record_end_button.configure(state="disabled")
            state.set("Finishing recording…")

    def save_view():
        nonlocal saved_unit_sample
        if busy or closing or nearby_picker is not None:
            return
        if adapter is None:
            state.set("Wait for RIFT to connect before saving a view.")
            return
        try:
            saved_unit_sample = None
            document = deepcopy(route_document())
            document["waypoints"] = [list(row) for row in document["waypoints"]]
            start("view", (document, adapter.pid, deepcopy(adapter.target),
                           "desktop" if view_bring_forward.get() else "wgc", view_include_units.get()))
        except (ValueError, KeyError, TypeError) as exc:
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

    def open_view():
        if saved_view is None or busy or closing:
            return
        try:
            import os
            os.startfile(saved_view)
        except OSError as exc:
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
            state.set("Cannot open 3D view: " + str(exc))

    def stop_markers():
        if not markers.running():
            return True
        try:
            markers.stop()
            marker_button.configure(text="Markers closing…", state="disabled")
            return True
        except OSError as exc:
            state.set("Cannot hide markers: " + str(exc))
            return False

    def toggle_markers():
        nonlocal marker_identity
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
            options = {}
            if target_beacon.get():
                options["target_beacon"] = True
            if landmark_guide.get():
                selected = table.selection()
                if len(selected) != 1:
                    raise WaypointError("Select one saved marker to guide to")
                options["landmark_number"] = table.index(selected[0]) + 1
            markers.start(route_document(), adapter, **options)
            target = adapter.target
            marker_identity = (adapter.pid, str(target["processStartUtcTicks"]),
                               target["executableSha256"].casefold(), target["hwnd"])
            marker_button.configure(text="Hide markers")
            state.set("Markers shown when RIFT is foreground."
                      + (" Selected landmark guide is pinned until Hide markers." if landmark_guide.get() else ""))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            state.set("Cannot show markers: " + str(exc))

    buttons = ttk.Frame(edit_tab, style="Surface.TFrame")
    buttons.pack(fill="x", pady=(0, 10))
    buttons_second = ttk.Frame(edit_tab, style="Surface.TFrame")
    buttons_second.pack(fill="x")
    for label, parent, callback in (("Refresh", header_actions, lambda: start("refresh")),
            ("Save Current", buttons, lambda: start("save")), ("Add X / Z", buttons, add_entered),
            ("Add Target", buttons, lambda: start("target")), ("Add nearby", buttons, add_nearby),
            ("Update Selected", buttons, update_selected), ("Up", buttons_second, lambda: move_point(-1)),
            ("Down", buttons_second, lambda: move_point(1)), ("Remove", buttons_second, remove_points),
            ("Clear", buttons_second, clear_points), ("Load", file_toolbar, load_route),
            ("Save Route", file_toolbar, save_route), ("Save As", file_toolbar, lambda: save_route(True))):
        button = ttk.Button(parent, text=label, command=callback,
                            style="Primary.TButton" if label in ("Save Route", "Update Selected") else "TButton")
        if label == "Refresh":
            button.pack(anchor="e", before=header_actions.winfo_children()[0])
        else:
            button.pack(side="left", padx=(0, 6))
        editable.append(button)
        if label == "Add nearby":
            nearby_button = button
    undo_button = ttk.Button(buttons_second, text="Undo", command=undo_edit, state="disabled")
    undo_button.pack(side="left", padx=(0, 6))
    editable.append(undo_button)
    for column in range(3):
        replay_tab.columnconfigure(column, weight=1)
    playback_group = ttk.LabelFrame(replay_tab, text="PLAYBACK", padding=(10, 5), style="Card.TLabelframe")
    playback_group.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    recording_controls = ttk.LabelFrame(replay_tab, text="RECORD A PATH", padding=(10, 5), style="Card.TLabelframe")
    recording_controls.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
    controls = ttk.LabelFrame(replay_tab, text="DIRECT MOVEMENT", padding=(10, 5), style="Card.TLabelframe")
    controls.grid(row=0, column=2, sticky="nsew")
    for column, (label, callback) in enumerate((("Go Selected", lambda: start("go", selected_points())),
                            ("Run Route", lambda: start("go", selected_points(True))),
                            ("Face Selected", lambda: start("face", selected_points())))):
        button = ttk.Button(controls, text=label, command=callback)
        button.grid(row=0, column=column, sticky="ew", padx=(0, 5), pady=(0, 8))
        editable.append(button)
        if label == "Go Selected":
            go_button = button
        elif label == "Run Route":
            route_button = button
        else:
            face_button = button
    face_option = ttk.Checkbutton(controls, text="Face, then walk", variable=walk_facing)
    face_option.grid(row=1, column=0, columnspan=3, sticky="w")
    editable.append(face_option)
    teach_button = ttk.Button(recording_controls, text="Walk + Record", command=lambda: start("teach", selected_points(True)))
    teach_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
    editable.append(teach_button)
    ttk.Button(stop_slot, text="STOP / F8", command=request_stop, style="Danger.TButton", width=15).pack(fill="both")
    ttk.Label(stop_slot, text="Always available · release & stop", style="Base.Muted.TLabel").pack(anchor="center", pady=(5, 0))
    playback_buttons = {}
    for label, parent, row, column, callback in (("Record", recording_controls, 0, 0, lambda: start("record")),
            ("Play Forward", playback_group, 0, 0, lambda: playback("forward")),
            ("Play Reverse", playback_group, 0, 1, lambda: playback("reverse")),
            ("Resume", playback_group, 1, 0, playback)):
        button = ttk.Button(parent, text=label, command=callback,
                            style="Primary.TButton" if label == "Play Forward" else "TButton")
        button.grid(row=row, column=column, sticky="ew", padx=(0, 5), pady=(0, 7))
        editable.append(button)
        playback_buttons[label] = button
    record_button = playback_buttons["Record"]
    forward_button = playback_buttons["Play Forward"]
    reverse_button = playback_buttons["Play Reverse"]
    resume_button = playback_buttons["Resume"]
    record_end_button = ttk.Button(recording_controls, text="Stop Recording", command=stop_recording, state="disabled")
    record_end_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=(0, 7))
    progress_text = tk.StringVar(value="No playback started.")
    progress_label = ttk.Label(replay_tab, textvariable=progress_text, style="Muted.TLabel", wraplength=860)
    progress_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
    replay_tab.bind("<Configure>", lambda event: progress_label.configure(wraplength=max(200, event.width - 30)))
    scene_tab.columnconfigure(0, weight=1)
    scene_tab.columnconfigure(1, weight=1)
    view_controls = ttk.LabelFrame(scene_tab, text="CAPTURE & EXPLORE", padding=(12, 8), style="Card.TLabelframe")
    view_controls.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
    view_buttons = ttk.Frame(view_controls, style="Surface.TFrame")
    view_buttons.pack(fill="x", pady=(0, 8))
    save_view_button = ttk.Button(view_buttons, text="Save view", command=save_view, style="Primary.TButton")
    save_view_button.pack(side="left", padx=(0, 6))
    editable.append(save_view_button)
    open_view_button = ttk.Button(view_buttons, text="Open view", command=open_view, state="disabled")
    open_view_button.pack(side="left", padx=(0, 6))
    editable.append(open_view_button)
    open_3d_button = ttk.Button(view_buttons, text="Open 3D view", command=open_3d_view, state="disabled")
    open_3d_button.pack(side="left")
    editable.append(open_3d_button)
    view_focus_option = ttk.Checkbutton(view_controls, text="Bring RIFT forward for capture", variable=view_bring_forward)
    view_focus_option.pack(anchor="w")
    editable.append(view_focus_option)
    view_units_option = ttk.Checkbutton(view_controls, text="Nearby units in 3D", variable=view_include_units)
    view_units_option.pack(anchor="w", pady=(3, 0))
    editable.append(view_units_option)
    marker_controls = ttk.LabelFrame(scene_tab, text="WORLD BEACONS", padding=(12, 8), style="Card.TLabelframe")
    marker_controls.grid(row=0, column=1, sticky="nsew")
    marker_button = ttk.Button(marker_controls, text="Show markers", command=toggle_markers)
    marker_button.pack(anchor="w", pady=(0, 8))
    editable.append(marker_button)
    target_option = ttk.Checkbutton(marker_controls, text="Include selected target in markers", variable=target_beacon)
    target_option.pack(anchor="w")
    editable.append(target_option)
    landmark_option = ttk.Checkbutton(marker_controls, text="Guide selected marker", variable=landmark_guide)
    landmark_option.pack(anchor="w", pady=(3, 0))
    editable.append(landmark_option)
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
    footer_label = ttk.Label(frame, text="Open ground · route ≤ 20 units · requested pulses ≤ 150 ms · F8 prevents the next pulse. "
              "Stop Recording saves; STOP cancels recording. Play starts within 0.30 units of its endpoint.",
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
        nonlocal closing, close_prompt
        if (not closing or close_prompt or busy or observing or foreground_stop is not None
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
            window.destroy()
            return True
        finally:
            close_prompt = False

    def close():
        nonlocal closing
        if closing:
            return
        closing = True
        close_nearby_picker()
        request_stop()
        for widget in editable:
            widget.configure(state="disabled")
        if stop_markers():
            finish_close()
        else:
            closing = False
            restore_editing()

    def poll():
        nonlocal busy, recording, recording_progress, pending_recorded, foreground_stop, last_pose, last_y, saved_view, saved_rerun, saved_unit_sample, observing, next_live_at, playback_view, playback_active, marker_identity, pending_progress_selection, verified_adapter, verified_at, identity_unavailable, last_verified_owner
        while not events.empty():
            event = events.get_nowait()
            status = event["status"]
            if status == "view-failed":
                saved_unit_sample = None
            if status in ("stopping", "notice") and stop.is_set() and markers.running():
                if not stop_markers():
                    event = dict(event, reason=event.get("reason", "STOP requested.") + " Could not hide markers.")
            if status == "reconnected":
                if not stop_markers():
                    state.set("Cannot hide markers after RIFT reconnected.")
                pending_progress_selection = bool(table.get_children())
                window.title(f"RR2 Waypoints - {args.expected_host} / PID {event['pid']}")
                connection_text.set(f"{args.expected_host}  /  PID {event['pid']}")
                state.set(f"Reconnected to RIFT PID {event['pid']}.")
                continue
            if status == "halted":
                last_pose = None
                verified_adapter, verified_at = None, None
                identity_unavailable = True
                redraw()
            if status == "live-idle":
                observing = False
                select_pending_progress()
                continue
            if status == "live-unavailable":
                pose_text.set("Live position unavailable: " + event["reason"])
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
                output = ROOT / "artifacts" / ("recorded-route-" + uuid.uuid4().hex + ".json")
                try:
                    write_json_atomic(output, event["document"])
                    document = prepared_document(event["document"])
                    if not stop_markers():
                        raise WaypointError("Cannot stop markers; route unchanged")
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
                cache_route(event["document"], "Recorded route saved: " + str(output))
                if progress is None:
                    progress_text.set("Recorded route ready; select playback direction.")
                continue
            if status == "view-saved":
                saved_view = event["image"]
                rerun = event["rerun"]
                saved_rerun = str(rerun["path"]) if rerun.get("status") == "saved" and rerun.get("path") else None
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
                log.configure(state="normal")
                log.insert("end", text + "\n")
                log.see("end")
                log.configure(state="disabled")
                continue
            if status in ("run-receipt", "receipt-error"):
                text = ("Run receipt: " + event["path"] if status == "run-receipt" else
                        "Could not save run receipt: " + event["reason"])
                failure = event.get("failure")
                state.set((f"{failure['status']}: {failure['reason']} — " if failure else "") + text)
                log.configure(state="normal")
                log.insert("end", text + "\n")
                log.see("end")
                log.configure(state="disabled")
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
                    recording_progress = {"sampleCount": event["sampleCount"],
                                          "observedPathLength": event["observedPathLength"]}
                last_pose = (point["x"], point["z"], event.get("bearing", last_pose[2] if last_pose else 0))
                last_y = point["y"]
                pose_text.set(f"Position X={point['x']:.6f}  Y={point['y']:.6f}  Z={point['z']:.6f}"
                              f"   facing={last_pose[2]:.2f}°   updated {time.strftime('%H:%M:%S')}")
                if not x.get() and not z.get():
                    x.set(f"{point['x']:.6f}")
                    z.set(f"{point['z']:.6f}")
                if status in ("refresh", "live", "save", "target", "map"):
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
                item = add_point(name.get() or "Waypoint", event["position"]["x"], event["position"]["z"])
                if item is not None and event.get("measurement") is not None:
                    point_receipts[item] = event["measurement"]
                    redraw()
                name.set(f"Point {len(table.get_children()) + 1}")
            if "waypoint" in event:
                item = add_point(*event["waypoint"])
                if item is not None and event.get("measurement") is not None:
                    point_receipts[item] = event["measurement"]
                    redraw()
                name.set(f"Point {len(table.get_children()) + 1}")
            text = (f"Route complete — {event['waypointCount']} waypoint{'s' if event['waypointCount'] != 1 else ''}, "
                    f"{event['distance']:.3f} units from the final point."
                    if status == "route-complete" else
                    f"{status}: {event['reason']}" if "reason" in event else
                    f"{status}: {abs(event['headingError']):.2f}° from requested facing" if "headingError" in event else
                    f"{status}: {event['distance']:.3f} units remaining" if "distance" in event else
                    f"{status}: {event.get('name', '')}" if status == "leg" else
                    event.get("measurementReason", "Saved current position.") if status == "save" else
                    event.get("measurementReason", "Saved the target's current ground position.") if status == "target" else
                    "Waypoint added from the preview." if status == "map" else
                    "Position refreshed.")
            state.set(text)
            log.configure(state="normal")
            log.insert("end", text + "\n")
            log.see("end")
            log.configure(state="disabled")
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
                    state.set("Markers unavailable; check the route and RIFT connection.")
                elif state.get() == "Hiding markers…":
                    state.set("Markers hidden.")
                marker_identity = None
                marker_button.configure(text="Show markers", state="normal" if not busy else "disabled")
            elif markers.stop_requested:
                marker_button.configure(text="Markers closing…", state="disabled")
        target_option.configure(state="disabled" if busy or closing or markers.running() else "normal")
        landmark_option.configure(state="disabled" if busy or closing or markers.running() else "normal")
        nearby_button.configure(state="disabled" if busy or closing or markers.running() else "normal")
        try:
            app_focused = window.focus_displayof() is not None
        except (AttributeError, tk.TclError):
            app_focused = False
        if (live_pose.get() and not busy and not observing and not closing
                and time.monotonic() >= next_live_at and (not markers.running() or app_focused)):
            observing = True
            next_live_at = time.monotonic() + 2
            threading.Thread(target=worker, args=("live",), daemon=False).start()
        window.after(80, poll)

    def select_point(_, *, force_name=False):
        nonlocal added_selection
        selected = selected_points()
        if len(selected) == 1:
            if force_name or table.selection()[0] != added_selection:
                added_selection = None
                name.set(selected[0][0])
            x.set(selected[0][1])
            z.set(selected[0][2])
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
        if not busy and not closing and len(table.selection()) == 1:
            workflow.select(edit_tab)
            select_point(None, force_name=True)
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
    table.bind("<Alt-Up>", lambda event: move_point_shortcut(event, -1))
    table.bind("<Alt-Down>", lambda event: move_point_shortcut(event, 1))
    table.bind("<Delete>", remove_points_shortcut)
    for entry in point_entries:
        entry.bind("<Control-Return>", update_selected_shortcut)
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
    poll()
    start("refresh")
    window.mainloop()


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
    mode.add_argument("--play-route", type=Path, help="replay a recorded route from its endpoint with --execute")
    mode.add_argument("--face-bearing", type=float, help="face this +Z-to-+X bearing without walking")
    parser.add_argument("--face-waypoints", action="store_true", help="turn toward each waypoint and walk forward")
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
        with cli_stop_controls(stop):
            if args.run_route is not None or args.play_route is not None or args.record_to is not None:
                path = args.play_route or args.run_route
                document = json.loads(path.read_text(encoding="utf-8")) if path else {"waypoints": [("Waypoint", *args.go)]}
                points = route_points(document["waypoints"])
                started = time.monotonic()
                if args.play_route:
                    from scripts.waypoint_playback import play_route
                    checkpoint = args.progress or args.play_route.with_suffix(".progress.json")
                    legs, _ = play_route(adapter, document, stop, emit, runner=run_route,
                                        checkpoint=checkpoint, direction="reverse" if args.reverse else "forward",
                                        resume=args.resume, face_waypoints=args.face_waypoints)
                elif args.record_to:
                    from scripts.waypoint_playback import teach_route
                    legs, recorded = teach_route(adapter, points, stop, emit, runner=run_route,
                                                 face_waypoints=args.face_waypoints)
                    args.record_to.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
                    emit({"status": "recorded", "path": str(args.record_to), "points": len(recorded["waypoints"])})
                else:
                    legs = run_route(adapter, points, stop, emit, face_waypoints=args.face_waypoints)
                result = {"status": "arrived", "waypointCount": len(legs),
                          "position": legs[-1]["position"], "bearing": legs[-1]["bearing"],
                          "distance": legs[-1]["distance"], "legs": legs,
                          "pulses": sum(leg["pulses"] for leg in legs),
                          "totalHoldMs": sum(leg["totalHoldMs"] for leg in legs),
                          "elapsedSeconds": round(time.monotonic()-started, 3),
                          "calibrationBinding": getattr(adapter, "binding", None),
                          "allPulsesReleased": True}
            else:
                result = (run_facing(adapter, stop, emit, bearing=args.face_bearing)
                          if args.face_bearing is not None else
                          run_route(adapter, [("Waypoint", *args.go)], stop, emit,
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
                   "releaseVerification": "see individual native pulse receipts for key release; measured stationary evidence is separate in stopVerification"}
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
