"""Bounded DXcam 0.3.0 diagnostic desktop-composite pilot; never focuses or sends input.

This is not an observe/WGC receipt and does not establish ownership of desktop pixels.
DXcam is imported lazily only after exact-host/target/foreground admission.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import socket
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.waypoint_progress import write_json_atomic


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _snapshot(target):
    from scripts.physical_waypoint_overlay import target_snapshot
    return target_snapshot(target)


class _DXcamBackend:
    """Version-pinned adapter: public timestamp getter waits indefinitely.

    The 0.3.0 private runtime peek is the same atomic frame/ticks operation used
    by get_latest_frame, but a nonblocking lock avoids its Event.wait loop.
    """
    def __init__(self):
        require(importlib.metadata.version("dxcam") == "0.3.0", "dxcam-0.3.0-required")
        import dxcam
        self.module = dxcam

    def outputs(self):
        factory = getattr(self.module, "__factory")
        rows = []
        for device_index, outputs in enumerate(factory.outputs):
            for output_index, output in enumerate(outputs):
                output.update_desc()
                rect = output.desc.DesktopCoordinates
                rows.append({"deviceIndex": device_index, "outputIndex": output_index,
                    "deviceName": output.devicename, "adapter": str(factory.devices[device_index]),
                    "desktopRect": [rect.left, rect.top, rect.right, rect.bottom],
                    "attachedToDesktop": output.attached_to_desktop,
                    "rotationDegrees": output.rotation_angle})
        return rows

    def create(self, selected, crop):
        return self.module.create(device_idx=selected["deviceIndex"],
            output_idx=selected["outputIndex"], region=tuple(crop), output_color="BGRA",
            max_buffer_len=2, backend="dxgi", processor_backend="numpy")

    def peek(self, camera):
        lock = getattr(camera, "_DXCamera__lock")
        if not lock.acquire(blocking=False):
            return None
        try:
            runtime = getattr(camera, "_DXCamera__capture_runtime")
            pair = runtime.peek_latest_with_ticks(copy=True)
            if pair is None:
                return None
            frame, ticks = pair
            duplicator = camera._duplicator
            return frame, ticks, duplicator.ticks_to_seconds(ticks), duplicator.performance_frequency
        finally:
            lock.release()


def _output(outputs, display, client):
    matches = [row for row in outputs if row["deviceName"].casefold() == display.casefold()]
    require(len(matches) == 1, "display-missing-or-ambiguous")
    row = matches[0]
    require(row["attachedToDesktop"] is True, "display-not-attached")
    x, y, width, height = client
    left, top, right, bottom = row["desktopRect"]
    require(left <= x and top <= y and x + width <= right and y + height <= bottom,
            "whole-client-must-fit-selected-monitor")
    return row, [x - left, y - top, x + width - left, y + height - top]


def probe(expected_host, physical_pid, display, output, *, frames=30, timeout=10,
          select=None, snapshot=None, backend_loader=None, clock=None, sleep=None):
    require(expected_host == "AMD-DESKTOP" and socket.gethostname().upper() == expected_host,
            "AMD-DESKTOP-host-required")
    require(type(physical_pid) is int and physical_pid > 0, "explicit-positive-pid-required")
    require(type(frames) is int and 1 <= frames <= 120, "frames-must-be-1-through-120")
    require(type(timeout) in (float, int) and math.isfinite(timeout) and 0 < timeout <= 30,
            "timeout-must-be-positive-through-30")
    require(isinstance(display, str) and bool(display), "explicit-display-required")
    output = Path(output).resolve()
    require(not output.exists() and output.parent.is_dir(), "fresh-output-directory-required")
    select = select or physical_rift.select_physical
    snapshot = snapshot or _snapshot
    backend_loader = backend_loader or _DXcamBackend
    clock, sleep = clock or time.perf_counter, sleep or time.sleep
    started = clock()
    deadline = started + timeout
    camera, backend, selected = None, None, None
    first_frame = last_frame = None
    accepted, waits, duplicate_polls, empty_polls = [], [], 0, 0
    result = {"schemaVersion": 1, "status": "blocked", "machine": expected_host,
        "diagnosticKind": "dxcam-desktop-composite-pilot/1", "dxcamVersion": "0.3.0",
        "inputSent": False, "focusChanged": False, "nativeCameraBracket": False,
        "requestedFrames": frames, "timeoutSeconds": timeout, "requestedDisplay": display,
        "startedAtUtc": datetime.now(timezone.utc).isoformat(),
        "timebase": "DXGI QPC ticks / QueryPerformanceFrequency; LastPresentTime with LastMouseUpdateTime fallback",
        "timestampAgeSeconds": None, "timestampAgeReason": "Python-clock compatibility not independently verified",
        "deadlineKind": "cooperative; DXGI calls, initialization and cleanup can exceed deadline",
        "limitations": ["Diagnostic desktop composite; not an authoritative WGC observation.",
            "Foreground and identity checks do not establish occlusion-free or RIFT-owned pixels.",
            "Advancing backend ticks can include mouse updates; not proof of a new RIFT render.",
            "No native camera bracket, world identity, depth, terrain or game response qualification."]}
    identity = None
    warmup = None
    before_snapshot = None
    def guard():
        value = snapshot(identity)
        require(type(value) is dict and value.get("foreground") is True, "target-not-foreground")
        rect = value.get("clientRect")
        require(isinstance(rect, (list, tuple)) and len(rect) == 4
                and all(type(n) is int for n in rect) and rect[2] > 0 and rect[3] > 0,
                "invalid-physical-client-rectangle")
        if before_snapshot is not None:
            require(value == before_snapshot, "target-client-or-foreground-changed")
        return value
    try:
        initial = select(expected_host, physical_pid)
        require(initial.get("status") == "ready", "physical-target-not-ready")
        identity = initial["target"]
        require(identity["processId"] == physical_pid
                and identity["hostName"].casefold() == expected_host.casefold(), "target-selection-mismatch")
        result["targetBefore"] = identity
        before_snapshot = guard()
        result["snapshotBefore"] = before_snapshot
        result["requestedClientRect"] = before_snapshot["clientRect"]
        require(clock() < deadline, "cooperative-deadline-expired")
        init_started = clock()
        backend = backend_loader()
        selected, crop = _output(backend.outputs(), display, before_snapshot["clientRect"])
        result.update(selectedOutput=selected, outputLocalCrop=crop)
        camera = backend.create(selected, crop)
        camera.start(target_fps=60, video_mode=False, delay=0)
        result["coldInitSeconds"] = clock() - init_started
        guard()
        wait_started = clock()
        while len(accepted) < frames:
            require(clock() < deadline, "new-frame-deadline-expired")
            guard()
            pair = backend.peek(camera)
            if pair is None:
                empty_polls += 1
                sleep(.005)
                continue
            frame, ticks, seconds, frequency = pair
            require(type(ticks) is int and ticks > 0 and type(frequency) is int and frequency > 0
                    and type(seconds) in (int, float) and math.isfinite(seconds)
                    and abs(seconds - ticks / frequency) < 1e-8, "invalid-backend-timestamp")
            previous = accepted[-1] if accepted else warmup
            if previous is not None and ticks <= previous["backendTicks"]:
                require(ticks == previous["backendTicks"], "backend-timestamp-regressed")
                duplicate_polls += 1
                sleep(.005)
                continue
            require(previous is None or frequency == previous["frequency"], "backend-timebase-changed")
            width, height = before_snapshot["clientRect"][2:]
            require(tuple(frame.shape) == (height, width, 4) and str(frame.dtype) == "uint8",
                    "capture-client-shape-or-format-changed")
            guard()
            require(clock() < deadline, "new-frame-deadline-expired")
            # Exact output identity/geometry, including rotation, cannot silently recover elsewhere.
            current, current_crop = _output(backend.outputs(), display, before_snapshot["clientRect"])
            require(current == selected and current_crop == crop, "selected-output-changed")
            now = clock()
            row = {"number": len(accepted) + 1, "backendTicks": ticks,
                   "backendSeconds": seconds, "frequency": frequency,
                   "acceptedElapsedSeconds": now - started, "waitSeconds": now - wait_started}
            if warmup is None:
                warmup = dict(row, number=0)
                result["warmupFrame"] = warmup
                result["coldToWarmupSeconds"] = now - init_started
                wait_started = now
                continue
            row["backendGapSeconds"] = seconds - previous["backendSeconds"]
            accepted.append(row)
            if first_frame is None:
                first_frame = frame.copy()
            last_frame = frame.copy()
            waits.append(row["waitSeconds"])
            wait_started = now
        result["status"] = "diagnostic-desktop-composite"
    except Exception as error:
        result.update(status="blocked", reason=str(error), errorType=type(error).__name__)
    finally:
        if camera is not None:
            errors = []
            for name in ("stop", "release"):
                try:
                    getattr(camera, name)()
                except Exception as error:
                    errors.append(name + ": " + str(error))
            result["cleanup"] = {"stopAndReleaseSucceeded": not errors, "errors": errors}
            if errors:
                result.update(status="blocked", reason="camera-cleanup-failed")
        if identity is not None:
            try:
                final = select(expected_host, physical_pid)
                require(final.get("status") == "ready" and final["target"] == identity,
                        "final-target-identity-changed")
                result["targetAfter"] = final["target"]
                result["snapshotAfter"] = guard()
            except Exception as error:
                result.update(status="blocked", reason=str(error), finalIdentityVerified=False)
    result.update(acceptedFrames=len(accepted), frames=accepted, duplicatePolls=duplicate_polls,
                  emptyPolls=empty_polls, elapsedSeconds=clock() - started)
    if waits:
        result["firstMeasuredFrameWaitSeconds"] = waits[0]
        result["warmNewFrameWaitSeconds"] = {"values": waits,
            "median": statistics.median(waits), "max": max(waits)}
    output.mkdir()
    if result["status"] == "diagnostic-desktop-composite":
        from PIL import Image
        images = []
        for name, frame in (("first.png", first_frame), ("last.png", last_frame)):
            path = output / name
            Image.fromarray(frame[..., [2, 1, 0]]).save(path, "PNG")
            images.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "coordinateSpace": "physical-client-crop-of-desktop-composite"})
        result["images"] = images
    result["report"] = str(output / "probe.json")
    write_json_atomic(output / "probe.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=("AMD-DESKTOP",))
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    try:
        result = probe(args.expected_host, args.physical_pid, args.display, args.output,
                       frames=args.frames, timeout=args.timeout)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2
    print(json.dumps({k: result[k] for k in ("status", "acceptedFrames", "elapsedSeconds", "report")}))
    return 0 if result["status"] == "diagnostic-desktop-composite" else 2


if __name__ == "__main__":
    raise SystemExit(main())
