"""Create fresh Windows Python environments for RR2 workflows and validation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical, physical_rift


INTERPRETERS = {
    "RIFTREADER2_PYTHON": "core/Scripts/python.exe",
    "RR2_OVERLAY_PYTHON": "overlay/Scripts/pythonw.exe",
    "RR2_DXCAM_PYTHON": "overlay/Scripts/python.exe",
    "RR2_RERUN_PYTHON": "rerun/Scripts/python.exe",
    "RIFTREADER2_LUA_PYTHON": "validation/Scripts/python.exe",
}


def _interpreter_settings(output):
    return {name: str(output / relative) for name, relative in INTERPRETERS.items()
            if (output / relative).is_file()}


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


def _check_environment(name, python):
    command = [str(python), "-B"]
    if name == "core":
        _run([*command, "-c", "import tkinter; tkinter.Tcl(); from PIL import Image"],
             "Check Waypoints and WGC imports")
    elif name == "overlay":
        _run([*command, "-m", "scripts.qt_waypoint_overlay"], "Check Qt Windows platform plugin")
        _run([*command, "-c", "import numpy; import comtypes; "
              "from scripts.probe_dxcam import require_capture_python; require_capture_python()"],
             "Check Qt startup and DXcam installation")
    elif name == "rerun":
        env = dict(os.environ, CI="1")
        env.pop("FORCE_RERUN_ANALYTICS", None)
        version = _run([*command, "-m", "rerun", "--version"], "Check Rerun startup", env=env)
        if not version.startswith("rerun-cli "):
            raise ValueError("Rerun returned an unrecognized version response")
    elif name == "validation":
        _run([*command, str(ROOT / "scripts/check_validation_python.py")], "Check validation Python imports")
        _run([*command, str(ROOT / "scripts/check_lua_runtime.py")], "Check validation Lua 5.1 runtime")


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
    _check_environment("core", core)
    if "overlay" in extras:
        overlay = _create_environment(output / "overlay", ("requirements-overlay.txt", "requirements-capture.txt"))
        _check_environment("overlay", overlay)
    if "rerun" in extras:
        rerun = _create_environment(output / "rerun", ("requirements-visualization.txt",))
        _check_environment("rerun", rerun)
    if "validation" in extras:
        validation = _create_environment(output / "validation", ("requirements-validation.txt",))
        _check_environment("validation", validation)
    settings = _interpreter_settings(output)
    (output / ".ready").touch(exist_ok=False)
    return settings


def _link_stat(link):
    try:
        return link.lstat()
    except FileNotFoundError:
        return None


def _is_junction(info):
    return getattr(info, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT


def _create_junction(link, output):
    _run([observe_physical.POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
          "New-Item -ItemType Junction -Path $env:RR2_PYTHON_SETUP_LINK "
          "-Target $env:RR2_PYTHON_SETUP_OUTPUT -ErrorAction Stop | Out-Null"],
         "Link existing Python setup",
         env=dict(os.environ, RR2_PYTHON_SETUP_LINK=str(link), RR2_PYTHON_SETUP_OUTPUT=str(output)))
    if not _is_junction(_link_stat(link)) or link.resolve(strict=True) != output.resolve(strict=True):
        raise ValueError("physical-python-link-target-mismatch")


def _replace_junction(link, output, original):
    directory = Path(tempfile.mkdtemp(prefix=".physical-python-link-", dir=link.parent))
    prepared = directory / "new"
    previous = directory / "previous"
    try:
        _create_junction(prepared, output)
        current = _link_stat(link)
        if not _is_junction(current) or not os.path.samestat(current, original):
            raise ValueError("physical-python-link-changed-before-replacement")
        link.rename(previous)
        try:
            moved = _link_stat(previous)
            if not _is_junction(moved) or not os.path.samestat(moved, original):
                raise ValueError("physical-python-link-changed-during-replacement")
            prepared.rename(link)
        except (OSError, ValueError):
            try:
                previous.rename(link)
            except OSError as error:
                raise ValueError(f"Could not restore the previous Python link from {previous}") from error
            raise
        # Remove the saved junction entry with a nonrecursive operation.
        previous.rmdir()
    finally:
        if _is_junction(_link_stat(prepared)):
            prepared.rmdir()
        if _link_stat(prepared) is None and _link_stat(previous) is None:
            directory.rmdir()


def use_existing(output, *, replace_link=False):
    """Link a verified setup at its installed path into this checkout."""
    if sys.platform != "win32":
        raise ValueError("Physical Python setup requires Windows")
    output = observe_physical._local_absolute_path(output.absolute(), "invalid-physical-python-root")
    settings = _interpreter_settings(output)
    if not (output / ".ready").is_file() or "RIFTREADER2_PYTHON" not in settings:
        raise ValueError("existing-physical-python-setup-incomplete")
    link = ROOT / ".local/physical-python-link"
    observe_physical._plain_path(link.parent)
    existing = _link_stat(link)
    if replace_link and existing is not None:
        if not _is_junction(existing):
            raise ValueError("physical-python-link-replacement-requires-directory-junction")
        drive = Path(os.readlink(link)).drive.removeprefix("\\\\?\\")
        if len(drive) != 2 or drive[1] != ":":
            raise ValueError("physical-python-link-replacement-requires-local-directory-junction")
    replacing = existing is not None and link.resolve() != output
    if replacing and not replace_link:
        raise ValueError(f"Physical Python link already exists at {link}")
    if link.is_relative_to(output):
        raise ValueError("Physical Python link cannot be inside its target")
    environments = {Path(INTERPRETERS[key]).parts[0] for key in settings}
    for name in ("core", "overlay", "rerun", "validation"):
        if name in environments:
            _check_environment(name, output / name / "Scripts/python.exe")
    if replacing:
        _replace_junction(link, output, existing)
    elif existing is None:
        link.parent.mkdir(parents=True, exist_ok=True)
        _create_junction(link, output)
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, help="verified local Windows machine name")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output-root", default=ROOT / ".local/physical-python", type=Path,
                             help="new directory for these environments (default: .local/physical-python in the checkout)")
    destination.add_argument("--use-existing", type=Path, help="register a completed local setup with this checkout")
    parser.add_argument("--replace-link", action="store_true", help="replace an existing checkout Python junction")
    parser.add_argument("--extra", choices=("overlay", "rerun", "validation"), action="append", default=[],
                        help="also prepare Qt/DXcam, Rerun, or the development test suite (repeatable)")
    args = parser.parse_args(argv)
    if args.use_existing is not None and args.extra:
        parser.error("--extra is only used when creating environments")
    if args.replace_link and args.use_existing is None:
        parser.error("--replace-link requires --use-existing")
    host = socket.gethostname()
    try:
        if not physical_rift.is_local_host(args.expected_host):
            raise ValueError("physical-host-mismatch")
        settings = (setup(args.output_root, extras=args.extra) if args.use_existing is None
                    else use_existing(args.use_existing, replace_link=args.replace_link))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "blocked", "host": host, "reason": str(error)}))
        return 2
    print(json.dumps({"status": "ready", "host": host, "environment": settings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
