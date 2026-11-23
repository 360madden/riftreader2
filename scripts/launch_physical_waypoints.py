"""Open the waypoint window for the single local physical RIFT client."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.physical_waypoints import PhysicalAdapter, launch_window, movement_basis_path, read_waypoints_basis


def start_window_process(arguments):
    command = [sys.executable, str(Path(__file__).resolve()), *arguments]
    return subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _check_tkinter():
    try:
        import tkinter
    except (ImportError, OSError):
        return {"status": "blocked", "reason": "tkinter-unavailable"}
    try:
        version = tkinter.Tcl().eval("info patchlevel")
    except tkinter.TclError:
        return {"status": "blocked", "reason": "tcl-initialization-failed"}
    return {"status": "available", "tclVersion": version}


def check_local_setup(physical_pid=None, basis=None, *, dependencies_only=False):
    """Check local Waypoints setup without a GUI, control ownership or game input."""
    host = socket.gethostname().upper()
    if not physical_rift.valid_host_name(host):
        raise ValueError("invalid-local-host")

    if dependencies_only and physical_pid is not None:
        raise ValueError("dependency-check-does-not-select-rift")
    basis_path = movement_basis_path(host, basis).absolute()
    reader = physical_rift._native_reader_path()
    checks = {"tkinter": _check_tkinter(), "nativeReader": {"status": "available", "path": str(reader)},
              "movementBasis": {"status": "present", "path": str(basis_path)}}
    if not reader.is_file():
        checks["nativeReader"].update(status="blocked", reason="native-reader-not-built")
    if not (basis_path.is_file() or basis_path.is_dir()):
        checks["movementBasis"].update(status="blocked", reason="movement-basis-missing")

    if dependencies_only:
        probe = physical_rift.check_native_reader(host, kind="facing")
        if probe["status"] != "ready":
            checks["nativeReader"].update(status="blocked", reason=probe["reason"])
        if checks["movementBasis"]["status"] == "present":
            try:
                calibration, _ = read_waypoints_basis(basis_path)
                if calibration["identity"]["machine"].casefold() != host.casefold():
                    raise ValueError("movement-basis-host-mismatch")
            except (OSError, ValueError) as error:
                checks["movementBasis"].update(status="blocked", reason=str(error))
        return {"scope": "local", "mode": "dependencies", "host": host, "target": None,
                "ready": all(check["status"] != "blocked" for check in checks.values()),
                "checks": checks, "inputSent": False}

    selection = physical_rift.select_physical(host, physical_pid)
    target = selection.get("target") if selection["status"] == "ready" else None
    if target is None:
        checks["rift"] = {"status": "blocked", "reason": selection["reason"]}
    elif type(target.get("hwnd")) is not int or target["hwnd"] <= 0:
        checks["rift"] = {"status": "blocked", "reason": "rift-window-unavailable"}
    else:
        checks["rift"] = {"status": "available"}

    checks["pose"] = {"status": "not-checked"}
    if all(checks[key]["status"] != "blocked" for key in ("nativeReader", "movementBasis", "rift")):
        try:
            # The adapter validates basis host/build/player and reads the native pose on construction.
            adapter = PhysicalAdapter(host, target["processId"], basis_path)
            if adapter.target != target:
                raise ValueError("rift-identity-changed")
            checks["pose"] = {"status": "available", "bearing": adapter.initial_pose.bearing,
                              "calibrationBinding": adapter.binding}
        except (OSError, ValueError) as error:
            checks["pose"] = {"status": "blocked", "reason": str(error)}

    return {"scope": "local", "host": host, "target": target,
            "ready": all(check["status"] != "blocked" for check in checks.values()),
            "checks": checks, "inputSent": False}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    detach_window = argv[:1] == ["--detach-window"]
    if detach_window:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, help="required when several RIFT clients are running")
    parser.add_argument("--basis", type=Path, help="local movement calibration file or complete folder")
    parser.add_argument("--view-native-reader", type=Path,
                        help="absolute path to a local published reader for Save view telemetry")
    parser.add_argument("--route", type=Path)
    parser.add_argument("--check", action="store_true", help="verify readiness without opening a window or sending input")
    parser.add_argument("--background", action="store_true", help="start with the helper window hidden")
    parser.add_argument("--cli", action="store_true", help="report startup errors without modal dialogs")
    parser.add_argument("--launch-token", help=argparse.SUPPRESS)
    parser.add_argument("--movement-engine", choices=("continuous", "pulse"), default="continuous",
                        help="continuous travel (default) or the original bounded pulse controller")
    args = parser.parse_args(argv)
    if detach_window and not args.check:
        try:
            start_window_process(argv)
        except OSError as error:
            print(f"Could not start Waypoints: {error}", file=sys.stderr)
            return 2
        return 0
    host = socket.gethostname().upper()
    from scripts.waypoint_diagnostics import Diagnostics
    from scripts.waypoint_brand import APP_NAME, APP_VERSION
    diagnostics = Diagnostics(ROOT)
    diagnostics.set_context(appName=APP_NAME, appVersion=APP_VERSION, host=host, guiPid=os.getpid(), phase="startup")
    diagnostics.install_hooks()
    diagnostics.info("Waypoint launcher started")
    try:
        if args.cli and args.route is not None:
            from scripts.physical_waypoints import validate_route_document
            validate_route_document(json.loads(args.route.read_text(encoding="utf-8-sig")))
        if not physical_rift.valid_host_name(host):
            raise ValueError("invalid-local-host")
        pid, adapter, pose, waiting_reason = None, None, None, None
        try:
            selected = physical_rift.select_physical(host, args.physical_pid)
            if selected.get("status") != "ready":
                raise ValueError(selected.get("reason", "Physical RIFT is unavailable"))
            pid = selected["target"]["processId"]
            diagnostics.set_context(target=selected["target"])
            # Validate current epoch and calibration before using a connection.
            adapter = PhysicalAdapter(host, pid, args.basis)
            pose = adapter.read()
        except Exception as exc:
            diagnostics.exception("Initial RIFT connection unavailable", exc=exc)
            if args.check or args.physical_pid is not None:
                raise
            # Re-select uniquely on each later attempt; do not retain a stale PID.
            pid, adapter, waiting_reason = None, None, str(exc)
        if args.check:
            print(json.dumps({"status": "ready", "host": host, "pid": pid,
                              "bearing": pose.bearing, "calibrationBinding": adapter.binding,
                              "inputSent": False}))
        else:
            launch_window(SimpleNamespace(expected_host=host, physical_pid=pid,
                                          basis=args.basis, route=args.route,
                                          view_native_reader=args.view_native_reader,
                                          face_waypoints=True, auto_reconnect=args.physical_pid is None,
                                          initial_adapter=adapter, initial_reason=waiting_reason,
                                          background=args.background, cli=args.cli, launch_token=args.launch_token,
                                          movement_engine=args.movement_engine,
                                          diagnostics=diagnostics))
        return 0
    except Exception as exc:
        diagnostics.exception("Waypoint startup failed", exc=exc)
        if args.check:
            print(json.dumps({"status": "blocked", "host": host, "reason": str(exc), "inputSent": False}))
        elif args.cli:
            if sys.stderr is not None:
                print(str(exc), file=sys.stderr)
        else:
            import tkinter as tk
            from tkinter import messagebox
            try:
                root = tk.Tk()
                root.withdraw()
                from scripts.waypoint_brand import APP_TITLE
                messagebox.showerror(APP_TITLE, f"{exc}\n\nDetails: {diagnostics.log_path}", parent=root)
                root.destroy()
            except Exception as dialog_error:
                diagnostics.exception("Unable to show startup error dialog", exc=dialog_error)
        return 2
    finally:
        diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
