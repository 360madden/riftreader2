"""Resolve optional physical view tools without importing image or GUI libraries."""
import json
import os
from pathlib import Path
import subprocess

from scripts.observe_physical import _plain_path


ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_PYTHON = ROOT / ".local/visualization-venv/Scripts/python.exe"
CAPTURE_PYTHON = ROOT / ".local/overlay-venv/Scripts/python.exe"
RERUN_EXPORT_PROBE = (
    "import json; from scripts.export_physical_rerun import check_export_dependencies; "
    "result = check_export_dependencies(); print(json.dumps(result)); "
    "raise SystemExit(0 if result['status'] == 'ready' else 2)"
)


def prepared_python(root, environment, executable="python.exe"):
    for name in ("physical-python-link", "physical-python"):
        setup = root / ".local" / name
        python = setup / environment / "Scripts" / executable
        if (setup / ".ready").is_file() and python.is_file():
            return python
    return None


def local_python(override, default, reason):
    if not override:
        return default
    executable = Path(override)
    if not executable.is_absolute() or executable.anchor.startswith(("\\\\", "//")):
        raise ValueError(reason)
    _plain_path(executable)
    return executable


def overlay_python(root):
    default = prepared_python(root, "overlay", "pythonw.exe") or root / ".local/overlay-venv/Scripts/pythonw.exe"
    return local_python(os.environ.get("RR2_OVERLAY_PYTHON"), default, "invalid-overlay-python-path")


def dxcam_python():
    default = prepared_python(ROOT, "overlay") or CAPTURE_PYTHON
    return local_python(os.environ.get("RR2_DXCAM_PYTHON"), default, "invalid-dxcam-python-path")


def rerun_python():
    return local_python(os.environ.get("RR2_RERUN_PYTHON"), prepared_python(ROOT, "rerun"),
                        "invalid-rerun-python-path")


def rerun_export_python():
    return rerun_python() or VISUALIZATION_PYTHON


def rerun_environment():
    environment = dict(os.environ, CI="1")
    environment.pop("FORCE_RERUN_ANALYTICS", None)
    return environment


def check_rerun_exporter():
    executable = rerun_export_python()
    if not executable.is_file():
        raise ValueError("visualization-environment-unavailable")
    try:
        probe = subprocess.run([str(executable), "-B", "-c", RERUN_EXPORT_PROBE],
                               cwd=ROOT, env=rerun_environment(), stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=45, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        raise ValueError("rerun-exporter-startup-timed-out") from error
    try:
        report = json.loads(probe.stdout)
    except ValueError:
        report = None
    if isinstance(report, dict):
        size = report.get("recordingBytes")
        if probe.returncode == 0 and report.get("status") == "ready" and type(size) is int and size > 0:
            return {"pythonExecutable": str(executable), "recordingBytes": size}
        if probe.returncode == 2 and report.get("status") == "blocked" and isinstance(report.get("reason"), str):
            raise ValueError(report["reason"])
    detail = probe.stderr.strip() or str(executable)
    raise ValueError("rerun-exporter-startup-failed: " + detail[-300:])


def check_rerun_viewer():
    """Probe the configured viewer in version mode without opening a window."""
    executable = rerun_python()
    if executable is not None:
        viewer = [str(executable), "-m", "rerun"]
    else:
        executable = VISUALIZATION_PYTHON.with_name("rerun.exe")
        viewer = [str(executable)]
    if not executable.is_file():
        raise ValueError("optional-rerun-viewer-not-installed")
    environment = rerun_environment()
    try:
        probe = subprocess.run([*viewer, "--version"], cwd=ROOT, env=environment,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=8, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        raise ValueError("optional-rerun-viewer-startup-timed-out") from error
    if probe.returncode != 0 or not probe.stdout.startswith("rerun-cli "):
        detail = (probe.stderr.strip() or str(executable))[-300:]
        raise ValueError("optional-rerun-viewer-startup-failed: " + detail)
    return viewer, environment, probe.stdout.splitlines()[0]
