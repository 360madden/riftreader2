"""Open the waypoint window for the single local physical RIFT client."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.physical_waypoints import DEFAULT_BASIS, PhysicalAdapter, launch_window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, help="required when several RIFT clients are running")
    parser.add_argument("--basis", type=Path, default=DEFAULT_BASIS)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--check", action="store_true", help="verify readiness without opening a window or sending input")
    args = parser.parse_args(argv)
    host = socket.gethostname().upper()
    try:
        selected = physical_rift.select_physical(host, args.physical_pid)
        if selected.get("status") != "ready":
            raise ValueError(selected.get("reason", "Physical RIFT is unavailable"))
        pid = selected["target"]["processId"]
        # Validate the current epoch and same-host/build/player calibration before
        # opening the window. Startup never starts a trip.
        adapter = PhysicalAdapter(host, pid, args.basis)
        pose = adapter.read()
        if args.check:
            print(json.dumps({"status": "ready", "host": host, "pid": pid,
                              "bearing": pose.bearing, "calibrationBinding": adapter.binding,
                              "inputSent": False}))
        else:
            launch_window(SimpleNamespace(expected_host=host, physical_pid=pid,
                                          basis=args.basis, route=args.route,
                                          face_waypoints=True, auto_reconnect=args.physical_pid is None,
                                          initial_adapter=adapter))
        return 0
    except Exception as exc:
        if args.check:
            print(json.dumps({"status": "blocked", "host": host, "reason": str(exc), "inputSent": False}))
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("RIFT waypoints", str(exc), parent=root)
            root.destroy()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
