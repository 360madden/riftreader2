#!/usr/bin/env python3
"""Small physical-RIFT waypoint prototype, using the existing RR2 controller.

Run without --go for the waypoint window. --go X Z --execute runs one bounded
open-ground trip. No memory writes, addon, service, Workbridge or mesh required.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
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
    """Own-window no-activate mode and a temporary F8 STOP registration."""

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
        window.update_idletasks()
        self.handle = self.api.GetAncestor(window.winfo_id(), 2)
        self.original_style = self.api.GetWindowLongPtrW(self.handle, -20)
        ctypes.set_last_error(0)
        self.api.SetWindowLongPtrW(self.handle, -20, self.original_style | 0x08000000)
        if ctypes.get_last_error():
            raise WaypointError("Could not enable a STOP window that preserves RIFT focus")
        self.thread_id = None
        self.ready = threading.Event()
        self.cancelled = threading.Event()

        def listen():
            self.thread_id = self.kernel.GetCurrentThreadId()
            registered = bool(self.api.RegisterHotKey(None, 1, 0x4000, 0x77))
            self.ready.set()
            if self.cancelled.is_set():
                if registered:
                    self.api.UnregisterHotKey(None, 1)
                return
            if not registered:
                events.put({"status": "notice", "reason": "F8 unavailable; use the STOP button."})
                return
            try:
                message = wintypes.MSG()
                while self.api.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    if message.message == 0x0312:
                        stop.set()
                        events.put({"status": "stopping", "reason": "F8 STOP requested; waiting for the bounded pulse to finish."})
            finally:
                self.api.UnregisterHotKey(None, 1)

        self.thread = threading.Thread(target=listen, daemon=True)
        self.thread.start()
        if not self.ready.wait(1):
            self.cancelled.set()
            self.api.SetWindowLongPtrW(self.handle, -20, self.original_style)
            raise WaypointError("F8 listener startup did not complete; no movement started")

    def close(self):
        self.cancelled.set()
        if self.thread.is_alive() and self.thread_id:
            posted = self.api.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            if not posted and self.thread.is_alive():
                raise WaypointError("Waiting for F8 listener shutdown")
            self.thread.join(timeout=1)
            if self.thread.is_alive():
                raise WaypointError("Waiting for F8 listener shutdown")
        self.api.SetWindowLongPtrW(self.handle, -20, self.original_style)


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise WaypointError("Coordinates must be finite numbers")
    return result


def spatial_distance(a, b):
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def pose_drift(first, second):
    return (spatial_distance(first.position, second.position),
            abs(heading_error(second.bearing, first.bearing)))


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
    """Exact-epoch reads and guarded, released native pulses; never retry input."""

    def __init__(self, host, pid, basis_path):
        self.host, self.pid = host, pid
        self.selection = physical_rift.select_physical(host, pid)
        if self.selection.get("status") != "ready":
            raise WaypointError(self.selection.get("reason", "RIFT unavailable"))
        self.target = self.selection["target"]
        self.basis, self.basis_sha = read_basis(basis_path)
        ident = self.basis["identity"]
        if (ident["machine"].casefold() != host.casefold()
                or ident["processId"] != pid
                or ident["processStartUtcTicks"] != self.target["processStartUtcTicks"]
                or ident["gameBuildSha256"].casefold() != self.target["executableSha256"].casefold()):
            raise WaypointError("Movement basis belongs to another process/build; recalibrate first")
        self.unit_key = ident["unitKey"]
        self.input_receipt_path = ROOT / "artifacts" / ("waypoint-input-" + uuid.uuid4().hex + ".jsonl")
        self.last_input_receipt = None

    def identity(self):
        selected = physical_rift.select_physical(self.host, self.pid)
        if selected.get("status") != "ready" or selected["target"] != self.target:
            raise WaypointError("RIFT process or window identity changed")
        return self.pinned_identity()

    def pinned_identity(self):
        return PhysicalClientIdentity(self.host, self.pid,
                                      int(self.target["processStartUtcTicks"]),
                                      self.target["executableSha256"].lower())

    def reserve(self):
        return PhysicalClientReservation(self.pinned_identity(), self.identity)

    def read(self):
        capture = physical_rift.read_native(self.selection, "facing", samples=1)
        if capture.get("status") != "complete":
            raise WaypointError(capture.get("reason", "Native pose unavailable"))
        values = capture["nativeValues"]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(values["sampledAtUtc"])).total_seconds()
        if not -0.1 <= age <= 2 or values["playerKey"] != self.unit_key:
            raise WaypointError("Stale pose or player identity changed")
        if values.get("positionSource") != "entity-owned-position-component+0x48":
            raise WaypointError("Entity-owned position unavailable")
        bearing = finite(values["bodyBearingDegreesCandidate"])
        point = values["positionXYZCandidate"]
        return Snapshot(Position(*(finite(point[k]) for k in ("x", "y", "z"))),
                        bearing, time.monotonic() - max(0, age), capture["nativeOutput"])

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
                  "qualification": "Current-epoch candidate body facing; restart qualification pending"}
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
            current = adapter.read()
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


def run_route(adapter, points, stop, emit=lambda event: None, *, face_waypoints=False):
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
            count = max(1, math.ceil(distance / (3.5 if face_waypoints else 4)))
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
            result = dict(segments[-1], start=asdict(start), goal=asdict(goal),
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
    window.title(f"RR2 Waypoints — {args.expected_host} / PID {args.physical_pid}")
    window.geometry("1060x770")
    frame = ttk.Frame(window, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="RIFT waypoints", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Open ground • route ≤ 20 units • pulses ≤ 150 ms • foreground loss stops movement").pack(anchor="w", pady=(0, 10))
    state = tk.StringVar(value="Ready — save a point, click the map, or enter X / Z.")
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
    closing = False
    adapter = None
    foreground_stop = None
    last_pose = None
    map_view = None
    observing = False
    next_live_at = time.monotonic() + 2
    operation_gate = threading.Lock()
    log = tk.Text(frame, height=6, state="disabled", font=("Consolas", 10))

    def add_point(label, px, pz):
        if len(table.get_children()) >= 20:
            state.set("Waypoint list is full; remove a point before adding another.")
            return
        item = table.insert("", "end", values=(label, f"{finite(px):.6f}", f"{finite(pz):.6f}"))
        table.selection_set(item)
        x.set(f"{finite(px):.6f}")
        z.set(f"{finite(pz):.6f}")
        redraw()
        return item

    def selected_points(all_points=False):
        return [table.item(item, "values") for item in (table.get_children() if all_points else table.selection())]

    def redraw(*_):
        nonlocal map_view
        points = [(item, *table.item(item, "values")) for item in table.get_children()]
        if last_pose is None:
            map_view = None
            draw_route(canvas, None, [], set())
            summary.set("Position unavailable; refresh to preview the route.")
            if not busy:
                for button in (go_button, route_button, face_button):
                    button.configure(state="disabled")
            return
        map_view = LocalMap(*last_pose, max(100, canvas.winfo_width()), max(100, canvas.winfo_height()))
        draw_route(canvas, map_view, points, set(table.selection()))
        distance = route_length(*last_pose[:2], selected_points(True))
        selected = selected_points()
        chosen = route_length(*last_pose[:2], selected) if selected else None
        summary.set(f"Route: {distance:.2f} / 20 units"
                    + (f"   •   Selected: {chosen:.2f} units" if chosen is not None else "")
                    + ("   •   Shorten the route to run it" if distance > 20 else ""))
        if not busy:
            go_button.configure(state="normal" if selected and chosen <= 20 else "disabled")
            route_button.configure(state="normal" if points and distance <= 20 else "disabled")
            face_button.configure(state="normal" if len(selected) == 1 and .3 < chosen <= 20 else "disabled")

    def map_click(event):
        if busy or map_view is None:
            return
        px, pz = map_view.canvas_to_world(event.x, event.y)
        start("map", (map_view, px, pz, name.get() or "Waypoint"))

    def worker(operation, points=None, face_walk=False):
        with operation_gate:
            perform_operation(operation, points, face_walk)

    def perform_operation(operation, points=None, face_walk=False):
        nonlocal adapter
        try:
            if adapter is None:
                adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
            if operation in ("refresh", "save", "map", "live"):
                pose = adapter.read()
                result = {"status": operation, "position": asdict(pose.position), "bearing": pose.bearing}
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
                run_facing(adapter, stop, events.put, point=points[0][1:])
            else:
                run_route(adapter, points, stop, events.put, face_waypoints=face_walk)
        except Exception as exc:
            stopped_position = stopped_bearing = None
            if isinstance(exc, Stopped) and adapter is not None:
                try:
                    time.sleep(.35)
                    first = adapter.read()
                    time.sleep(.25)
                    second = adapter.read()
                    drift, yaw_drift = pose_drift(first, second)
                    if drift > .05:
                        exc = WaypointError(f"Movement still detected after STOP ({drift:.3f} units); recovery required")
                    elif yaw_drift > .5:
                        exc = WaypointError(f"Facing still changing after STOP ({yaw_drift:.2f}°); recovery required")
                    else:
                        stopped_position = asdict(second.position)
                        stopped_bearing = second.bearing
                except Exception as observation_error:
                    exc = WaypointError("STOP requested; stationary check unavailable: " + str(observation_error))
            events.put({"status": "live-unavailable" if operation == "live" else
                        "stopped" if isinstance(exc, Stopped) else "halted", "reason": str(exc),
                        **({"position": stopped_position, "bearing": stopped_bearing} if stopped_position else {}),
                        "inputReceiptPath": str(adapter.input_receipt_path) if adapter else None})
        finally:
            events.put({"status": "live-idle" if operation == "live" else "idle"})

    def start(operation, points=None):
        nonlocal busy, foreground_stop
        if busy or closing:
            return
        if operation == "go" and (not points or len(points) > 20):
            messagebox.showinfo("Choose waypoints", "Select a waypoint, or add up to 20 points for a route.")
            return
        if operation == "face" and (not points or len(points) != 1):
            state.set("Select one waypoint to face.")
            return
        busy = True
        stop.clear()
        if operation in ("go", "face"):
            try:
                foreground_stop = ForegroundStop(window, stop, events)
            except Exception as exc:
                busy = False
                state.set("Cannot start safely: " + str(exc))
                return
        for widget in editable:
            widget.configure(state="disabled")
        state.set("Starting action — F8 or STOP prevents the next pulse." if operation in ("go", "face")
                  else "Reading current RIFT pose…")
        threading.Thread(target=worker, args=(operation, points, walk_facing.get()), daemon=False).start()

    def request_stop():
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
            Path(path).write_text(json.dumps({"waypoints": selected_points(True)}, indent=2), encoding="utf-8")

    def load_route():
        path = filedialog.askopenfilename(filetypes=[("Waypoint JSON", "*.json")])
        if not path:
            return
        try:
            parsed = route_points(json.loads(Path(path).read_text(encoding="utf-8"))["waypoints"])
            table.delete(*table.get_children())
            for row in parsed:
                add_point(*row)
            name.set(f"Point {len(table.get_children()) + 1}")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            messagebox.showerror("Cannot load route", str(exc))

    def remove_points():
        table.delete(*table.selection())
        redraw()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=4)
    for label, callback in (("Refresh", lambda: start("refresh")),
                            ("Save Current", lambda: start("save")), ("Add X / Z", add_entered),
                            ("Remove", remove_points),
                            ("Load", load_route), ("Save Route", save_route)):
        button = ttk.Button(buttons, text=label, command=callback)
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
    tk.Button(controls, text="STOP / F8", bg="#b3261e", fg="white", font=("Segoe UI", 12, "bold"),
              command=request_stop, width=16).pack(side="right")
    log.pack(fill="x", pady=4)
    ttk.Label(frame, text="F8 stops without changing focus. STOP preserves focus during a run; edits unlock after cleanup.").pack(anchor="w")

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
        nonlocal busy, foreground_stop, last_pose, observing, next_live_at
        while not events.empty():
            event = events.get_nowait()
            status = event["status"]
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
                for widget in editable:
                    widget.configure(state="normal")
                redraw()
                if closing:
                    window.destroy()
                    return
                continue
            if "position" in event:
                point = event["position"]
                last_pose = (point["x"], point["z"], event.get("bearing", last_pose[2] if last_pose else 0))
                pose_text.set(f"Position X={point['x']:.6f}  Y={point['y']:.6f}  Z={point['z']:.6f}"
                              f"   facing={last_pose[2]:.2f}°   updated {time.strftime('%H:%M:%S')}")
                if not x.get() and not z.get():
                    x.set(f"{point['x']:.6f}")
                    z.set(f"{point['z']:.6f}")
                redraw()
            if status == "live":
                continue
            if status == "save":
                add_point(name.get() or "Waypoint", event["position"]["x"], event["position"]["z"])
                name.set(f"Point {len(table.get_children()) + 1}")
            if "waypoint" in event:
                add_point(*event["waypoint"])
                name.set(f"Point {len(table.get_children()) + 1}")
            text = (f"{status}: {event['reason']}" if "reason" in event else
                    f"{status}: {abs(event['headingError']):.2f}° from requested facing" if "headingError" in event else
                    f"{status}: {event['distance']:.3f} units remaining" if "distance" in event else
                    f"{status}: {event.get('name', '')}" if status == "leg" else
                    "Saved current position." if status == "save" else
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
        for row in route_points(json.loads(args.route.read_text(encoding="utf-8"))["waypoints"]):
            add_point(*row)
        name.set(f"Point {len(table.get_children()) + 1}")
    poll()
    start("refresh")
    window.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--basis", type=Path, default=DEFAULT_BASIS)
    parser.add_argument("--route", type=Path, help="load a waypoint JSON into the window without running it")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--go", nargs=2, type=float, metavar=("X", "Z"))
    mode.add_argument("--face-bearing", type=float, help="face this +Z-to-+X bearing without walking")
    parser.add_argument("--face-waypoints", action="store_true", help="turn toward each waypoint and walk forward")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.go is None and args.face_bearing is None:
        launch_window(args)
        return 0
    if not args.execute:
        parser.error("--go / --face-bearing requires --execute; omit both to open the window")
    stop = threading.Event()
    try:
        adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
        emit = lambda event: print(json.dumps({k: v for k, v in event.items()
                                               if k not in ("actions", "segments")}), flush=True)
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
        print(json.dumps({"status": "halted", "reason": str(exc)}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
