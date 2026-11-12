#!/usr/bin/env python3
"""Small physical-RIFT waypoint prototype, using the existing RR2 controller.

Run without --go for the waypoint window. --go X Z --execute runs one bounded
open-ground leg. No memory writes, addon, service, Workbridge or mesh required.
"""
from __future__ import annotations

import argparse
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


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise WaypointError("Coordinates must be finite numbers")
    return result


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
                        bearing, time.monotonic(), capture["nativeOutput"])

    def calibrations(self, snapshot):
        # The empirical actor angle is the negative of our +Z -> +X bearing.
        return candidate_calibrations(self.basis, -snapshot.bearing)[0]

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
        if (completed.returncode != 0 or receipt.get("boundedActionCompleted") is not True
                or receipt.get("releaseSucceeded") is not True
                or receipt.get("allRequestedKeyDownsInserted") is not True
                or receipt.get("insertionUncertain") is not False
                or receipt.get("targetLost") is not False or receipt.get("cancelled") is not False
                or receipt.get("processId") != self.pid
                or str(receipt.get("processStartUtcTicks")) != self.target["processStartUtcTicks"]
                or str(receipt.get("executableSha256", "")).casefold()
                    != self.target["executableSha256"].casefold()):
            raise WaypointError(receipt.get("reason") or receipt.get("Error")
                                or "Input stopped or release unconfirmed; no retry")
        return receipt


def run_leg(adapter, goal_x, goal_z, stop, emit=lambda event: None, *, focus=True):
    """One existing bounded controller, with a fresh feedback read per pulse."""
    def check_stop():
        if stop.is_set():
            raise Stopped("Stopped; no further input")

    actions = []
    check_stop()
    with adapter.reserve() as lease:
        start = current = adapter.read()
        goal = Position(finite(goal_x), start.position.y, finite(goal_z))
        controller = WaypointController(adapter.calibrations(start), start.position, goal)
        started = time.monotonic()
        emit({"status": "moving", "position": asdict(current.position),
              "distance": planar_distance(current.position, goal)})
        while True:
            check_stop()
            lease.check()
            if time.monotonic() - current.acquired > 2:
                current = adapter.read()
            controller.calibrations = adapter.calibrations(current)
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
                          "distance": planar_distance(settled.position, goal),
                          "pulses": len(actions), "totalHoldMs": controller.total_hold_ms,
                          "elapsedSeconds": round(time.monotonic() - started, 3),
                          "allPulsesReleased": True, "actions": actions,
                          "qualification": "Supervised open-ground prototype; candidate native pose, no obstacle routing"}
                emit(result)
                return result
            check_stop()
            if time.monotonic() - current.acquired > 2:
                raise WaypointError("Pose expired before input")
            receipt = adapter.pulse(action, focus=focus and not actions)
            actions.append(receipt)
            # Wait with all keys released for the observed motion to settle.
            if stop.wait(.15):
                raise Stopped("Stopped; current pulse released")
            current = adapter.read()
            feedback = controller.record_feedback(current.position, time.monotonic() - started)
            emit({"status": feedback.status, "position": asdict(current.position),
                  "distance": feedback.distance_after, "pulse": len(actions),
                  "key": action.key, "holdMs": action.hold_ms})


def route_points(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise WaypointError("Route must have 1–20 points")
    if any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in rows):
        raise WaypointError("Each point needs name, X and Z")
    return [(str(row[0])[:80], finite(row[1]), finite(row[2])) for row in rows]


def run_route(adapter, points, stop, emit=lambda event: None):
    results = []
    movement_started = False
    for label, px, pz in route_points(points):
        if stop.is_set():
            raise Stopped("Stopped; no further input")
        emit({"status": "leg", "name": label})
        result = run_leg(adapter, px, pz, stop, emit, focus=not movement_started)
        results.append(result)
        movement_started = movement_started or result["pulses"] > 0
    return results


def launch_window(args):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk()
    window.title(f"RR2 Waypoints — {args.expected_host} / PID {args.physical_pid}")
    window.geometry("760x570")
    frame = ttk.Frame(window, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="RIFT waypoints", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Open ground • each leg ≤ 6 units • pulses ≤ 150 ms • foreground loss stops movement").pack(anchor="w", pady=(0, 10))
    state = tk.StringVar(value="Ready — refresh position, save a point, or enter X / Z.")
    ttk.Label(frame, textvariable=state, wraplength=710).pack(anchor="w", pady=5)
    coordinates = ttk.Frame(frame)
    coordinates.pack(fill="x", pady=5)
    name, x, z = tk.StringVar(value="Point 1"), tk.StringVar(), tk.StringVar()
    for label, variable, width in (("Name", name, 18), ("X", x, 16), ("Z", z, 16)):
        ttk.Label(coordinates, text=label).pack(side="left", padx=(0, 5))
        ttk.Entry(coordinates, textvariable=variable, width=width).pack(side="left", padx=(0, 10))
    table = ttk.Treeview(frame, columns=("name", "x", "z"), show="headings", height=9)
    for col, label, width in (("name", "Waypoint", 260), ("x", "X", 180), ("z", "Z", 180)):
        table.heading(col, text=label)
        table.column(col, width=width)
    table.pack(fill="both", expand=True, pady=8)
    events, stop = queue.Queue(), threading.Event()
    busy = False
    closing = False
    adapter = None
    log = tk.Text(frame, height=6, state="disabled", font=("Consolas", 10))

    def add_point(label, px, pz):
        table.insert("", "end", values=(label, f"{finite(px):.6f}", f"{finite(pz):.6f}"))

    def selected_points(all_points=False):
        return [table.item(item, "values") for item in (table.get_children() if all_points else table.selection())]

    def worker(operation, points=None):
        nonlocal adapter
        try:
            if adapter is None:
                adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
            if operation in ("refresh", "save"):
                pose = adapter.read()
                events.put({"status": operation, "position": asdict(pose.position), "bearing": pose.bearing})
            else:
                run_route(adapter, points, stop, events.put)
        except Exception as exc:
            events.put({"status": "stopped" if isinstance(exc, Stopped) else "halted", "reason": str(exc)})
        finally:
            events.put({"status": "idle"})

    def start(operation, points=None):
        nonlocal busy
        if busy:
            return
        if operation == "go" and (not points or len(points) > 20):
            messagebox.showinfo("Choose waypoints", "Select a waypoint, or add up to 20 points for a route.")
            return
        busy = True
        stop.clear()
        state.set("Reading current RIFT pose…" if operation != "go" else "Starting route — STOP prevents the next pulse.")
        threading.Thread(target=worker, args=(operation, points), daemon=False).start()

    def request_stop():
        stop.set()
        state.set("STOP requested — waiting for the current bounded pulse to release.")

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
        except (ValueError, KeyError, TypeError, OSError) as exc:
            messagebox.showerror("Cannot load route", str(exc))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=4)
    for label, callback in (("Refresh", lambda: start("refresh")),
                            ("Save Current", lambda: start("save")), ("Add X / Z", add_entered),
                            ("Remove", lambda: table.delete(*table.selection())),
                            ("Load", load_route), ("Save Route", save_route)):
        ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=(0, 5))
    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=8)
    ttk.Button(controls, text="Go Selected", command=lambda: start("go", selected_points())).pack(side="left", padx=(0, 6))
    ttk.Button(controls, text="Run Route", command=lambda: start("go", selected_points(True))).pack(side="left")
    tk.Button(controls, text="STOP", bg="#b3261e", fg="white", font=("Segoe UI", 12, "bold"),
              command=request_stop, width=16).pack(side="right")
    log.pack(fill="x", pady=4)
    ttk.Label(frame, text="STOP or close waits for release. Switching away from RIFT aborts; movement never refocuses mid-route.").pack(anchor="w")

    def close():
        nonlocal closing
        if busy:
            closing = True
            request_stop()
        else:
            window.destroy()

    def poll():
        nonlocal busy
        while not events.empty():
            event = events.get_nowait()
            status = event["status"]
            if status == "idle":
                busy = False
                if closing:
                    window.destroy()
                    return
                continue
            if "position" in event:
                point = event["position"]
                x.set(f"{point['x']:.6f}")
                z.set(f"{point['z']:.6f}")
            if status == "save":
                add_point(name.get() or "Waypoint", x.get(), z.get())
                name.set(f"Point {len(table.get_children()) + 1}")
            text = (f"{status}: {event['reason']}" if "reason" in event else
                    f"{status}: {event['distance']:.3f} units remaining" if "distance" in event else
                    f"{status}: {event.get('name', '')}" if status == "leg" else
                    f"Position X={x.get()}  Z={z.get()}  facing={event.get('bearing', 0):.2f}°")
            state.set(text)
            log.configure(state="normal")
            log.insert("end", text + "\n")
            log.see("end")
            log.configure(state="disabled")
        window.after(80, poll)

    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _: request_stop())
    if args.route:
        for row in route_points(json.loads(args.route.read_text(encoding="utf-8"))["waypoints"]):
            add_point(*row)
    poll()
    start("refresh")
    window.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--basis", type=Path, default=DEFAULT_BASIS)
    parser.add_argument("--route", type=Path, help="load a waypoint JSON into the window without running it")
    parser.add_argument("--go", nargs=2, type=float, metavar=("X", "Z"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.go is None:
        launch_window(args)
        return 0
    if not args.execute:
        parser.error("--go requires --execute; omit --go to open the waypoint window")
    stop = threading.Event()
    try:
        adapter = PhysicalAdapter(args.expected_host, args.physical_pid, args.basis)
        result = run_leg(adapter, *args.go, stop,
                         lambda event: print(json.dumps(event), flush=True))
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
