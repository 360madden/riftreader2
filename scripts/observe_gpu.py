"""Local focus-neutral WGC observation using the existing one-frame GPU probe."""
from __future__ import annotations

import json
from pathlib import Path
import socket

from scripts.observe_physical import ROOT, _identity, _plain_path, _require, _run
from scripts.physical_turn_visual_pair import read_frame

PROBE = ROOT / "tools/physical-wgc-probe/bin/Debug/net10.0-windows10.0.19041.0/win-x64/PhysicalWgcProbe.exe"


def capture_gpu(expected_host, output, *, physical_pid=None):
    target_id = "physical-" + str(expected_host).lower()
    try:
        _require(expected_host == "AMD-DESKTOP", "gpu-probe-amd-desktop-only")
        _require(socket.gethostname().casefold() == expected_host.casefold(), "host-mismatch")
        directory = Path(output)
        _require(directory.is_absolute(), "absolute-output-required")
        _plain_path(directory)
        _require(not directory.exists() and directory.parent.is_dir(), "fresh-output-required")
        _require(PROBE.is_file(), "gpu-probe-build-required")
        before = _identity(physical_pid)
        _require(before["hostName"].casefold() == expected_host.casefold(), "host-mismatch")
        directory.mkdir()
        image = directory / "image.png"
        receipt = directory / "image.png.json"
        code, response = _run([
            PROBE, "--capture", "--allow-one-capture", "--host", expected_host,
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
        report, _, digest = read_frame(image, receipt)
        pinned = report["targetBefore"]
        _require(report["machine"] == expected_host and report["requestedBackend"] == "wgc"
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
        }
    except (ValueError, OSError, KeyError, TypeError) as error:
        return {"status": "blocked", "targetId": target_id, "workflow": "physical",
                "reason": str(error), "captureBackend": "Windows.Graphics.Capture",
                "foregroundMayChange": False}
