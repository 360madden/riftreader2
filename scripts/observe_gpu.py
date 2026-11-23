"""Local focus-neutral WGC observation using the existing one-frame GPU probe."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket

from scripts.observe_physical import ROOT, _identity, _plain_path, _require, _run, valid_host_name

PROBE = ROOT / "tools/physical-wgc-probe/bin/Debug/net10.0-windows10.0.19041.0/win-x64/PhysicalWgcProbe.exe"


def check_probe():
    """Run the built probe's offline self-test without opening a target window."""
    result = {"status": "blocked", "path": str(PROBE)}
    if not PROBE.is_file():
        return {**result, "reason": "gpu-probe-build-required"}
    try:
        code, response = _run([PROBE, "--self-test"], 10,
                              env={**os.environ, "DOTNET_DISABLE_GUI_ERRORS": "1"})
    except (OSError, ValueError):
        return {**result, "reason": "gpu-probe-self-test-unavailable"}
    if code != 0:
        return {**result, "reason": "gpu-probe-self-test-failed", "exitCode": code}
    try:
        report = json.loads(response)
    except json.JSONDecodeError:
        report = None
    if (not isinstance(report, dict) or report.get("status") != "offline-self-test-passed"
            or report.get("inputSent") is not False or report.get("frameCaptured") is not False
            or type(report.get("passed")) is not int or report["passed"] < 1):
        return {**result, "reason": "gpu-probe-self-test-report-invalid"}
    return {**result, "status": "available", "checksPassed": report["passed"]}


def frame_tools():
    """Load the WGC receipt verifier on the Python interpreter that will use it."""
    try:
        from scripts import physical_turn_visual_pair
    except ImportError as error:
        if (error.name or "").split(".", 1)[0] == "PIL":
            raise ValueError("wgc-python-pillow-unavailable") from error
        raise
    return physical_turn_visual_pair


def capture_gpu(expected_host, output, *, physical_pid=None):
    target_id = "physical-" + str(expected_host).lower()
    try:
        host = socket.gethostname()
        _require(valid_host_name(expected_host), "invalid-host")
        _require(host.casefold() == expected_host.casefold(), "host-mismatch")
        directory = Path(output)
        _require(directory.is_absolute(), "absolute-output-required")
        _plain_path(directory)
        _require(not directory.exists() and directory.parent.is_dir(), "fresh-output-required")
        _require(PROBE.is_file(), "gpu-probe-build-required")
        frames = frame_tools()
        before = _identity(physical_pid)
        _require(before["hostName"].casefold() == host.casefold(), "host-mismatch")
        _require(physical_pid is None or before["processId"] == physical_pid, "physical-pid-mismatch")
        directory.mkdir()
        image = directory / "image.png"
        receipt = directory / "image.png.json"
        code, response = _run([
            PROBE, "--capture", "--allow-one-capture", "--host", host,
            "--process", "rift_x64", "--pid", before["processId"],
            "--start-ticks", before["processStartUtcTicks"],
            "--sha256", before["executableSha256"],
            "--hwnd", hex(before["hwnd"]), "--backend", "wgc", "--out", image,
        ], 20)
        if code:
            failure = json.loads(response) if response.strip() else {}
            reason = failure.get("reason") if isinstance(failure, dict) else None
            raise ValueError(reason or "gpu-capture-failed")
        _require(_identity(physical_pid) == before, "stale-identity")
        report, _, digest = frames.read_frame(image, receipt)
        pinned = report["targetBefore"]
        _require(report["machine"].casefold() == host.casefold() and report["requestedBackend"] == "wgc"
                 and pinned["pid"] == before["processId"]
                 and pinned["startTicks"] == int(before["processStartUtcTicks"])
                 and pinned["sha256"].casefold() == before["executableSha256"].casefold()
                 and pinned["hwnd"] == before["hwnd"], "gpu-target-mismatch")
        return {
            "status": "verified-awaiting-visual-review", "targetId": target_id,
            "workflow": "physical", "captureBackend": "Windows.Graphics.Capture",
            "image": str(image), "imageSha256": digest,
            "receipt": str(receipt), "capturedAtUtc": report["capturedCompletedAtUtc"],
            "target": before, "foregroundMayChange": False,
            "clientFrameMapping": frames.client_frame_mapping(report),
        }
    except (ValueError, OSError, KeyError, TypeError) as error:
        return {"status": "blocked", "targetId": target_id, "workflow": "physical",
                "reason": str(error), "captureBackend": "Windows.Graphics.Capture",
                "foregroundMayChange": False}
