"""Local focus-neutral WGC observation using the existing one-frame GPU probe."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket

from scripts.observe_physical import (
    ROOT, _identity, _plain_path, _require, _run, published_physical_tool, valid_host_name, workbridge_root,
)

PROBE = ROOT / "tools/physical-wgc-probe/bin/Debug/net10.0-windows10.0.19041.0/win-x64/PhysicalWgcProbe.exe"
# .NET apphost exit codes, independent of the host's display language.
DOTNET_PROBE_ERRORS = {
    0x80008083: "gpu-probe-dotnet-runtime-unavailable",
    0x80008096: "gpu-probe-dotnet-runtime-unavailable",
    0x8000809A: "gpu-probe-publish-incomplete",
}


def _probe_path():
    override = os.environ.get("RR2_WGC_PROBE")
    if not override:
        return published_physical_tool("wgc-probe/PhysicalWgcProbe.exe") or PROBE
    probe = Path(override)
    _require(probe.is_absolute() and not probe.anchor.startswith(("\\\\", "//"))
             and ".." not in probe.parts, "invalid-gpu-probe-path")
    _plain_path(probe)
    return probe


def check_probe():
    """Run the built probe's offline self-test without opening a target window."""
    try:
        probe = _probe_path()
    except (OSError, ValueError) as error:
        return {"status": "blocked", "reason": str(error)}
    result = {"status": "blocked", "path": str(probe)}
    if not probe.is_file():
        return {**result, "reason": "gpu-probe-build-required"}
    try:
        code, response = _run([probe, "--self-test"], 10,
                              env={**os.environ, "DOTNET_DISABLE_GUI_ERRORS": "1"})
    except (OSError, ValueError):
        return {**result, "reason": "gpu-probe-self-test-unavailable"}
    if code != 0:
        reason = DOTNET_PROBE_ERRORS.get(code & 0xFFFFFFFF, "gpu-probe-self-test-failed")
        return {**result, "reason": reason, "exitCode": code}
    try:
        report = json.loads(response)
    except json.JSONDecodeError:
        report = None
    if (not isinstance(report, dict) or report.get("status") != "offline-self-test-passed"
            or report.get("inputSent") is not False or report.get("frameCaptured") is not False
            or type(report.get("passed")) is not int or report["passed"] < 1):
        return {**result, "reason": "gpu-probe-self-test-report-invalid"}
    if report.get("outputCheckoutDiscovery") is not True and not probe.is_relative_to(ROOT):
        return {**result, "reason": "gpu-probe-relocation-update-required"}
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
        probe = _probe_path()
        _require(probe.is_file(), "gpu-probe-build-required")
        frames = frame_tools()
        bridge = workbridge_root()
        before = _identity(physical_pid)
        _require(before["hostName"].casefold() == host.casefold(), "host-mismatch")
        _require(physical_pid is None or before["processId"] == physical_pid, "physical-pid-mismatch")
        directory.mkdir()
        image = directory / "image.png"
        receipt = directory / "image.png.json"
        code, response = _run([
            probe, "--capture", "--allow-one-capture", "--host", host,
            "--process", "rift_x64", "--pid", before["processId"],
            "--start-ticks", before["processStartUtcTicks"],
            "--sha256", before["executableSha256"],
            "--hwnd", hex(before["hwnd"]), "--backend", "wgc", "--out", image,
        ], 20, env={**os.environ, "DOTNET_DISABLE_GUI_ERRORS": "1", "RR2_WORKBRIDGE_ROOT": str(bridge)})
        if code:
            runtime_failure = DOTNET_PROBE_ERRORS.get(code & 0xFFFFFFFF)
            if runtime_failure:
                raise ValueError(runtime_failure)
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
