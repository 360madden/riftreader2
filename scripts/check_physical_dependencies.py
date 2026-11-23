"""Check physical workflow startup dependencies on the verified local Windows host."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift, physical_view_tools


def workflow_commands(host):
    physical = ("--target", "physical", "--expected-host", host, "--check-dependencies",
                "--physical-capture-backend")
    local = ("--expected-host", host, "--check-dependencies")
    return {
        "waypoints": ("waypoints_cli.py", "--json", "doctor", "--local", "--dependencies-only"),
        "wgc": ("observe_target.py", *physical, "wgc", "--native-facing"),
        "workbridge": ("observe_target.py", *physical, "workbridge"),
        "dxcam": ("probe_dxcam_native_pair.py", *local),
        "readerbridge": ("capture_readerbridge_v3.py", *local, "--include-selected-target"),
        "npc-survey": ("prepare_physical_npc_survey.py", *local, "--include-levels"),
        "telemetry": ("capture_physical_telemetry_target_series.py", *local),
        "prepared-maps": ("waypoint_destination_plan.py", "--check-dependencies"),
    }


def run_check(executable, args, *, cwd=None):
    return subprocess.run([str(executable), "-B", *args], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=False, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def check_workflow(workflow, command):
    try:
        if workflow == "rerun":
            viewer, _, version = physical_view_tools.check_rerun_viewer()
            return {"status": "ready", "command": viewer, "version": version}
        if workflow == "qt":
            python = physical_view_tools.local_python(os.environ.get("RR2_OVERLAY_PYTHON"),
                                                      ROOT / ".local/overlay-venv/Scripts/pythonw.exe",
                                                      "invalid-overlay-python-path")
            if not python.is_file():
                return {"status": "blocked", "pythonExecutable": str(python), "reason": "overlay-python-unavailable"}
            probe = run_check(python, ("-c", "from scripts import qt_waypoint_overlay"), cwd=ROOT)
            result = {"status": "ready", "pythonExecutable": str(python), "exitCode": probe.returncode}
            return result if probe.returncode == 0 else dict(result, status="blocked", reason="qt-overlay-import-failed")

        python = sys.executable
        if workflow == "dxcam":
            python = physical_view_tools.local_python(os.environ.get("RR2_DXCAM_PYTHON"),
                                                      physical_view_tools.CAPTURE_PYTHON,
                                                      "invalid-dxcam-python-path")
            if not python.is_file():
                return {"status": "blocked", "pythonExecutable": str(python),
                        "reason": "desktop-capture-environment-unavailable"}
        script, *args = command
        probe = run_check(python, (str(ROOT / "scripts" / script), *args))
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "reason": "dependency-check-timed-out"}
    except (OSError, ValueError) as error:
        return {"status": "blocked", "reason": str(error)}

    try:
        receipt = json.loads(probe.stdout)
    except ValueError:
        receipt = None
    if not isinstance(receipt, dict):
        return {"status": "blocked", "exitCode": probe.returncode, "reason": "invalid-dependency-check-output"}
    return {"status": "ready" if probe.returncode == 0 else "blocked", "exitCode": probe.returncode,
            "result": receipt}


def main(argv=None):
    host = socket.gethostname()
    commands = workflow_commands(host)
    workflows = (*commands, "qt", "rerun")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, help="verified local Windows machine name")
    parser.add_argument("--workflow", action="append", choices=workflows,
                        help="run only this check (repeatable, defaults to all)")
    args = parser.parse_args(argv)

    result = {"host": host, "status": "blocked", "checks": {}, "inputSent": False, "captureAttempted": False}
    if physical_rift.is_local_host(args.expected_host):
        result["checks"] = {
            workflow: check_workflow(workflow, commands.get(workflow))
            for workflow in dict.fromkeys(args.workflow or workflows)
        }
        if all(check["status"] == "ready" for check in result["checks"].values()):
            result["status"] = "ready"
    else:
        result.update(reason="physical-host-mismatch", expectedHost=args.expected_host)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
