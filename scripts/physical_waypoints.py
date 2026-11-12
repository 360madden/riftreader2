#!/usr/bin/env python3
"""Small physical-RIFT waypoint prototype, using the existing RR2 controller.

Run without --go for the waypoint window. --go X Z --execute runs one bounded
open-ground trip. No memory writes, addon, service, Workbridge or mesh required.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
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
from scripts.waypoint_map import LocalMap, draw_route, route_length
from scripts.waypoint_heading import choose_turn, heading_error
from scripts.waypoint_seed_feedback import verify_translation, verify_turn

DEFAULT_BASIS = ROOT / "config/physical-movement-basis.amd-desktop.json"


class WaypointError(ValueError):
    pass


class Stopped(WaypointError):
    pass


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
    from scripts.waypoint_connection import idle_read
    from scripts.waypoint_observation import observe_batch
    from scripts.waypoint_recording import RouteRecorder
    from scripts.waypoint_playback import play_route
    from scripts.waypoint_progress import _route as progress_route, write_json_atomic

    window.title(f"RR2 Waypoints — {args.expected_host} / "
                 + (f"PID {args.physical_pid}" if args.physical_pid is not None else "waiting for RIFT"))
    window.geometry("1060x770")
    frame = ttk.Frame(window, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="RIFT waypoints", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Open ground • route ≤ 20 units • pulses ≤ 150 ms • foreground loss stops movement").pack(anchor="w", pady=(0, 10))
    state = tk.StringVar(value=("Waiting for RIFT: " + args.initial_reason
                                if getattr(args, "initial_reason", None) else
                                "Ready — save a point, click the map, or enter X / Z."))
    ttk.Label(frame, textvariable=state, wraplength=1000).pack(anchor="w", pady=5)
    pose_text = tk.StringVar(value="Position is loading…")
    ttk.Label(frame, textvariable=pose_text).pack(anchor="w", pady=(0, 3))
    editable = []
    coordinates = ttk.Frame(frame)
    coordinates.pack(fill="x", pady=5)
    name, x, z = tk.StringVar(value="Point 1"), tk.StringVar(), tk.StringVar()
    walk_facing = tk.BooleanVar(value=args.face_waypoints)
    live_pose = tk.BooleanVar(value=True)
    for label, variable, width in (("Name", name, 18), ("X", x, 16), ("Z", z, 16)):
        ttk.Label(coordinates, text=label).pack(side="left", padx=(0, 5))
        entry = ttk.Entry(coordinates, textvariable=variable, width=width)
        entry.pack(side="left", padx=(0, 10))
        editable.append(entry)
    ttk.Checkbutton(coordinates, text="Live pose (2 s)", variable=live_pose).pack(side="left", padx=(16, 0))
    summary = tk.StringVar(value="Refresh position to preview the route.")
    ttk.Label(frame, textvariable=summary).pack(anchor="w", pady=(5, 0))
    middle = ttk.Frame(frame)
    middle.pack(fill="both", expand=True, pady=8)
    table = ttk.Treeview(middle, columns=("name", "x", "z"), show="headings", height=9)
    for col, label, width in (("name", "Waypoint", 210), ("x", "X", 140), ("z", "Z", 140)):
        table.heading(col, text=label)
        table.column(col, width=width)
    table.pack(side="left", fill="both", expand=True)
    map_frame = ttk.Frame(middle, padding=(12, 0, 0, 0))
    map_frame.pack(side="right", fill="both")
    canvas = tk.Canvas(map_frame, width=330, height=310, bg="#101c25", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    ttk.Label(map_frame, text="Click to add • facing up • rings 5 / 10 units").pack(anchor="w", pady=(4, 0))
    events, stop = queue.Queue(), threading.Event()
    busy = False
    recording = False
    recording_progress = None
    closing = False
    adapter = getattr(args, "initial_adapter", None)
    published_adapter = adapter
    foreground_stop = None
    last_pose = None
    map_view = None
    observing = False
    next_live_at = time.monotonic() + 2
    operation_gate = threading.Lock()
    record_stop, record_cancel = threading.Event(), threading.Event()
    checkpoint = ROOT / "artifacts" / "waypoint-current-progress.json"
    last_route = ROOT / "artifacts" / "waypoint-last-route.json"
    route_metadata = {}
    playback_view = None
    playback_active = False
    loading_route = False
    log = tk.Text(frame, height=6, state="disabled", font=("Consolas", 10))

    def invalidate_progress(*, clear_metadata=True):
        nonlocal route_metadata, playback_view
        if not loading_route:
            checkpoint.unlink(missing_ok=True)
            if clear_metadata:
                route_metadata = {}
            playback_view = None
            progress_text.set("No saved progress; choose Play Forward or Play Reverse.")

    def add_point(label, px, pz):
        if len(table.get_children()) >= 20:
            state.set("Waypoint list is full; remove a point before adding another.")
            return
        invalidate_progress()
        item = table.insert("", "end", values=(label, f"{finite(px):.6f}", f"{finite(pz):.6f}"))
        table.selection_set(item)
        x.set(f"{finite(px):.6f}")
        z.set(f"{finite(pz):.6f}")
        redraw()
        return item

    def selected_points(all_points=False):
        return [table.item(item, "values") for item in (table.get_children() if all_points else table.selection())]

    def route_document():
        return {**route_metadata, "waypoints": route_points(selected_points(True))}

    def cache_route(document, success):
        try:
            write_json_atomic(last_route, document)
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
        parsed = route_points(document["waypoints"])
        loading_route = True
        try:
            table.delete(*table.get_children())
            for row in parsed:
                add_point(*row)
            route_metadata = {k: v for k, v in document.items() if k != "waypoints"}
            name.set(f"Point {len(table.get_children()) + 1}")
        finally:
            loading_route = False
        redraw()

    def restore_progress():
        nonlocal playback_view
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if progress_route(route_document()) != progress_route(saved["route"]):
            raise ValueError("Saved progress belongs to a different route")
        count = len(saved["route"]["waypoints"])
        index = saved["nextIndex"]
        if (saved["direction"] not in ("forward", "reverse") or type(index) is not int
                or not 0 <= index <= count):
            raise ValueError("Invalid saved progress")
        playback_view = {"direction": saved["direction"], "nextIndex": index}
        hint = "choose Play Forward or Play Reverse." if index == count else "choose Resume."
        progress_text.set(f"Saved progress: {index} / {count}; {hint}")
        redraw()

    def redraw(*_):
        nonlocal map_view
        points = [(item, *table.item(item, "values")) for item in table.get_children()]
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
        map_view = LocalMap(*last_pose, max(100, canvas.winfo_width()), max(100, canvas.winfo_height()))
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
            summary.set(f"{'Remaining' if playback_view is not None else 'Route'}: {distance:.2f} / 20 units"
                        + (f"   •   Selected: {chosen:.2f} units" if chosen is not None else "")
                        + ("   •   Shorten the route to run it" if distance > 20 else ""))
        if not busy:
            go_button.configure(state="normal" if selected and chosen <= 20 else "disabled")
            route_button.configure(state="normal" if points and planned_distance <= 20 else "disabled")
            teach_button.configure(state="normal" if points and planned_distance <= 20 else "disabled")
            face_button.configure(state="normal" if len(selected) == 1 and .3 < chosen <= 20 else "disabled")
            record_button.configure(state="normal")
            forward_button.configure(state="normal" if points else "disabled")
            reverse_button.configure(state="normal" if points else "disabled")
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
                result = {"status": operation, "position": asdict(pose.position), "bearing": pose.bearing}
                if operation == "target":
                    result["waypoint"] = target_waypoint(pose)
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
            failure = {"status": "live-unavailable" if operation == "live" else
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
        if busy or closing:
            return
        if operation in ("go", "teach") and (not points or len(points) > 20):
            messagebox.showinfo("Choose waypoints", "Select a waypoint, or add up to 20 points for a route.")
            return
        if operation == "face" and (not points or len(points) != 1):
            state.set("Select one waypoint to face.")
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
                  else "Reading current RIFT pose…")
        threading.Thread(target=worker, args=(operation, points, walk_facing.get()), daemon=False).start()

    def request_stop():
        if recording:
            record_cancel.set()
            record_stop.set()
            state.set("Recording cancelled — no route will be saved.")
            return
        stop.set()
        state.set("STOP requested — waiting for the current bounded pulse to release." if busy
                  else "Stopped — no input active.")

    def add_entered():
        try:
            add_point(name.get() or "Waypoint", x.get(), z.get())
        except (ValueError, TypeError):
            messagebox.showerror("Invalid coordinates", "Enter finite X and Z coordinates.")

    def save_route():
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="rift-waypoints.json")
        if path:
            try:
                document = route_document()
                write_json_atomic(path, document)
                cache_route(document, "Route saved: " + str(path))
            except (ValueError, TypeError, OSError) as exc:
                messagebox.showerror("Cannot save route", str(exc))

    def load_route():
        path = filedialog.askopenfilename(filetypes=[("Waypoint JSON", "*.json")])
        if not path:
            return
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            route_points(document["waypoints"])
            progress_route(document)
            show_document(document)
            try:
                restore_progress()
            except (OSError, ValueError, KeyError, TypeError):
                invalidate_progress(clear_metadata=False)
                redraw()
            cache_route(document, "Route loaded: " + str(path))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            messagebox.showerror("Cannot load route", str(exc))

    def remove_points():
        if table.selection():
            invalidate_progress()
        table.delete(*table.selection())
        redraw()

    def move_point(direction):
        selected = table.selection()
        if len(selected) != 1:
            state.set("Select one waypoint to move up or down.")
            return
        item = selected[0]
        index = max(0, min(len(table.get_children()) - 1, table.index(item) + direction))
        if index != table.index(item):
            invalidate_progress()
        table.move(item, "", index)
        table.see(item)
        redraw()

    def clear_points():
        if table.get_children():
            invalidate_progress()
        table.delete(*table.get_children())
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

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=4)
    buttons_second = ttk.Frame(frame)
    buttons_second.pack(fill="x", pady=4)
    for index, (label, callback) in enumerate((("Refresh", lambda: start("refresh")),
                            ("Save Current", lambda: start("save")), ("Add X / Z", add_entered),
                            ("Remove", remove_points),
                            ("Load", load_route), ("Save Route", save_route),
                            ("Up", lambda: move_point(-1)), ("Down", lambda: move_point(1)),
                            ("Clear", clear_points), ("Add Target", lambda: start("target")))):
        button = ttk.Button(buttons if index < 5 else buttons_second, text=label, command=callback)
        button.pack(side="left", padx=(0, 5))
        editable.append(button)
    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=8)
    for label, callback in (("Go Selected", lambda: start("go", selected_points())),
                            ("Run Route", lambda: start("go", selected_points(True))),
                            ("Face Selected", lambda: start("face", selected_points()))):
        button = ttk.Button(controls, text=label, command=callback)
        button.pack(side="left", padx=(0, 6))
        editable.append(button)
        if label == "Go Selected":
            go_button = button
        elif label == "Run Route":
            route_button = button
        else:
            face_button = button
    face_option = ttk.Checkbutton(controls, text="Face, then walk", variable=walk_facing)
    face_option.pack(side="left", padx=(10, 0))
    editable.append(face_option)
    teach_button = ttk.Button(controls, text="Walk + Record", command=lambda: start("teach", selected_points(True)))
    teach_button.pack(side="left", padx=(10, 0))
    editable.append(teach_button)
    tk.Button(controls, text="STOP / F8", bg="#b3261e", fg="white", font=("Segoe UI", 12, "bold"),
              command=request_stop, width=16).pack(side="right")
    recording_controls = ttk.Frame(frame)
    recording_controls.pack(fill="x", pady=4)
    playback_buttons = {}
    for label, callback in (("Record", lambda: start("record")),
                            ("Play Forward", lambda: playback("forward")),
                            ("Play Reverse", lambda: playback("reverse")),
                            ("Resume", playback)):
        button = ttk.Button(recording_controls, text=label, command=callback)
        button.pack(side="left", padx=(0, 6))
        editable.append(button)
        playback_buttons[label] = button
    record_button = playback_buttons["Record"]
    forward_button = playback_buttons["Play Forward"]
    reverse_button = playback_buttons["Play Reverse"]
    resume_button = playback_buttons["Resume"]
    record_end_button = ttk.Button(recording_controls, text="Stop Recording", command=stop_recording, state="disabled")
    record_end_button.pack(side="left", padx=(0, 6))
    progress_text = tk.StringVar(value="No playback started.")
    ttk.Label(recording_controls, textvariable=progress_text).pack(side="left", padx=8)
    log.pack(fill="x", pady=4)
    ttk.Label(frame, text="During movement F8 stops without changing focus. Stop Recording saves; STOP cancels recording.").pack(anchor="w")
    table.tag_configure("completed", foreground="#52806d")
    table.tag_configure("next", foreground="#ad6500")

    def close():
        nonlocal closing
        if busy or observing:
            closing = True
            for widget in editable:
                widget.configure(state="disabled")
            request_stop()
        else:
            window.destroy()

    def poll():
        nonlocal busy, recording, recording_progress, foreground_stop, last_pose, observing, next_live_at, playback_view, playback_active
        while not events.empty():
            event = events.get_nowait()
            status = event["status"]
            if status == "reconnected":
                window.title(f"RR2 Waypoints - {args.expected_host} / PID {event['pid']}")
                state.set(f"Reconnected to RIFT PID {event['pid']}.")
                continue
            if status == "halted":
                last_pose = None
                redraw()
            if status == "live-idle":
                observing = False
                if closing and not busy:
                    window.destroy()
                    return
                continue
            if status == "live-unavailable":
                pose_text.set("Live position unavailable: " + event["reason"])
                last_pose = None
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
                recording = False
                recording_progress = None
                record_end_button.configure(state="disabled")
                for widget in editable:
                    widget.configure(state="normal")
                redraw()
                if closing and not observing:
                    window.destroy()
                    return
                continue
            if status == "recorded-pending":
                if record_cancel.is_set() or closing or (event.get("operation") == "teach" and stop.is_set()):
                    state.set("Recording cancelled; no route saved.")
                    continue
                # This runs on the UI thread: STOP/close cannot race publication.
                recording = False
                record_end_button.configure(state="disabled")
                output = ROOT / "artifacts" / ("recorded-route-" + uuid.uuid4().hex + ".json")
                try:
                    write_json_atomic(output, event["document"])
                    invalidate_progress()
                    show_document(event["document"])
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    state.set("Cannot finish recording: " + str(exc))
                    continue
                cache_route(event["document"], "Recorded route saved: " + str(output))
                progress_text.set("Recorded route ready; select playback direction.")
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
                pose_text.set(f"Position X={point['x']:.6f}  Y={point['y']:.6f}  Z={point['z']:.6f}"
                              f"   facing={last_pose[2]:.2f}°   updated {time.strftime('%H:%M:%S')}")
                if not x.get() and not z.get():
                    x.set(f"{point['x']:.6f}")
                    z.set(f"{point['z']:.6f}")
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
                add_point(name.get() or "Waypoint", event["position"]["x"], event["position"]["z"])
                name.set(f"Point {len(table.get_children()) + 1}")
            if "waypoint" in event:
                add_point(*event["waypoint"])
                name.set(f"Point {len(table.get_children()) + 1}")
            text = (f"Route complete — {event['waypointCount']} waypoint{'s' if event['waypointCount'] != 1 else ''}, "
                    f"{event['distance']:.3f} units from the final point."
                    if status == "route-complete" else
                    f"{status}: {event['reason']}" if "reason" in event else
                    f"{status}: {abs(event['headingError']):.2f}° from requested facing" if "headingError" in event else
                    f"{status}: {event['distance']:.3f} units remaining" if "distance" in event else
                    f"{status}: {event.get('name', '')}" if status == "leg" else
                    "Saved current position." if status == "save" else
                    "Saved the target's current ground position." if status == "target" else
                    "Waypoint added from the preview." if status == "map" else
                    "Position refreshed.")
            state.set(text)
            log.configure(state="normal")
            log.insert("end", text + "\n")
            log.see("end")
            log.configure(state="disabled")
        if live_pose.get() and not busy and not observing and not closing and time.monotonic() >= next_live_at:
            observing = True
            next_live_at = time.monotonic() + 2
            threading.Thread(target=worker, args=("live",), daemon=False).start()
        window.after(80, poll)

    def select_point(_):
        selected = selected_points()
        if len(selected) == 1:
            x.set(selected[0][1])
            z.set(selected[0][2])
        redraw()

    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _: request_stop())
    canvas.bind("<Configure>", redraw)
    canvas.bind("<Button-1>", map_click)
    table.bind("<<TreeviewSelect>>", select_point)
    if args.route:
        show_document(json.loads(args.route.read_text(encoding="utf-8")))
    restored_checkpoint = False
    if checkpoint.exists():
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if not args.route:
                progress_route(saved["route"])
                if (saved["direction"] not in ("forward", "reverse") or type(saved["nextIndex"]) is not int
                        or not 0 <= saved["nextIndex"] <= len(saved["route"]["waypoints"])):
                    raise ValueError("Invalid saved progress")
                show_document(saved["route"])
            restore_progress()
            restored_checkpoint = True
        except (OSError, ValueError, KeyError, TypeError):
            progress_text.set("Saved progress unavailable; load a route to continue.")
    if not args.route and not restored_checkpoint and last_route.exists():
        try:
            document = json.loads(last_route.read_text(encoding="utf-8"))
            progress_route(document)
            show_document(document)
            playback_view = None
            progress_text.set("Last saved route restored; choose Play Forward or Play Reverse.")
            redraw()
        except (OSError, ValueError, KeyError, TypeError):
            progress_text.set("Last saved route unavailable; load a route to continue.")
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
    mode.add_argument("--play-route", type=Path, help="replay a recorded route from its endpoint")
    mode.add_argument("--face-bearing", type=float, help="face this +Z-to-+X bearing without walking")
    parser.add_argument("--face-waypoints", action="store_true", help="turn toward each waypoint and walk forward")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--record-to", type=Path, help="save observed movement from this --go/--run-route")
    parser.add_argument("--reverse", action="store_true", help="replay from recorded end toward start")
    parser.add_argument("--progress", type=Path, help="recorded-route progress checkpoint")
    parser.add_argument("--resume", action="store_true", help="resume saved unfinished recorded route")
    args = parser.parse_args(argv)
    if (args.reverse or args.resume or args.progress) and args.play_route is None:
        parser.error("--reverse / --resume / --progress requires --play-route")
    if args.record_to is not None and args.go is None and args.run_route is None:
        parser.error("--record-to requires --go or --run-route")
    if args.go is None and args.face_bearing is None and args.run_route is None and args.play_route is None:
        launch_window(args)
        return 0
    if not args.execute:
        parser.error("--go / --face-bearing / --run-route requires --execute; omit them to open the window")
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
