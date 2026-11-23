"""Create fresh Windows Python environments for RR2 workflows and validation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical, physical_rift


def _run(command, step, *, env=None):
    result = subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=300, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"{step} exited {result.returncode}: {detail[-500:]}")
    return result.stdout


def _create_environment(directory, requirements):
    directory.mkdir()
    _run([sys.executable, "-m", "venv", str(directory)], f"Create {directory.name} environment")
    python = directory / "Scripts/python.exe"
    install = [str(python), "-m", "pip", "--disable-pip-version-check", "install", "--no-input", "--only-binary=:all:"]
    for requirement in requirements:
        install.extend(["-r", str(ROOT / requirement)])
    _run(install, f"Install {directory.name} requirements")
    _run([str(python), "-m", "pip", "--disable-pip-version-check", "check"], f"Check {directory.name} requirements")
    return python


def setup(output, *, extras=()):
    """Create local environments once and return the paths used by the app."""
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise ValueError("Physical Python setup requires 64-bit Windows Python")
    output = Path(output).absolute()
    if output.drive.startswith(("\\", "/")) or ".." in output.parts:
        raise ValueError("Choose a new local output directory")
    observe_physical._plain_path(output)
    _run([sys.executable, "-B", "-c", "import tkinter; tkinter.Tcl()"], "Check base Python Tcl/Tk")
    output.mkdir(parents=True, exist_ok=False)

    core = _create_environment(output / "core", ("requirements-physical.txt",))
    _run([str(core), "-B", "-c", "import tkinter; tkinter.Tcl(); from PIL import Image"], "Check Waypoints and WGC imports")
    settings = {"RIFTREADER2_PYTHON": str(core)}
    if "overlay" in extras:
        overlay = _create_environment(output / "overlay", ("requirements-overlay.txt", "requirements-capture.txt"))
        _run([str(overlay), "-B", "-c", "from scripts import qt_waypoint_overlay; import numpy; import comtypes"],
             "Check Qt and capture environment imports")
        settings.update(RR2_OVERLAY_PYTHON=str(overlay.with_name("pythonw.exe")), RR2_DXCAM_PYTHON=str(overlay))
    if "rerun" in extras:
        rerun = _create_environment(output / "rerun", ("requirements-visualization.txt",))
        env = dict(os.environ, CI="1")
        env.pop("FORCE_RERUN_ANALYTICS", None)
        version = _run([str(rerun), "-B", "-m", "rerun", "--version"], "Check Rerun startup", env=env)
        if not version.startswith("rerun-cli "):
            raise ValueError("Rerun returned an unrecognized version response")
        settings["RR2_RERUN_PYTHON"] = str(rerun)
    if "validation" in extras:
        validation = _create_environment(output / "validation", ("requirements-validation.txt",))
        _run([str(validation), "-B", str(ROOT / "scripts/check_validation_python.py")],
             "Check validation Python imports")
        _run([str(validation), "-B", str(ROOT / "scripts/check_lua_runtime.py")], "Check validation Lua 5.1 runtime")
        settings["RIFTREADER2_LUA_PYTHON"] = str(validation)
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, help="verified local Windows machine name")
    parser.add_argument("--output-root", required=True, type=Path, help="new directory for these environments")
    parser.add_argument("--extra", choices=("overlay", "rerun", "validation"), action="append", default=[],
                        help="also prepare Qt/DXcam, Rerun, or the development test suite (repeatable)")
    args = parser.parse_args(argv)
    host = socket.gethostname()
    try:
        if not physical_rift.is_local_host(args.expected_host):
            raise ValueError("physical-host-mismatch")
        settings = setup(args.output_root, extras=args.extra)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "blocked", "host": host, "reason": str(error)}))
        return 2
    print(json.dumps({"status": "ready", "host": host, "environment": settings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
