"""Isolated windows-capture 2.0.1 HWND diagnostic; no focus, input or native-camera proof.

The first delivered frame is copied inside its callback and capture is stopped.
Window-surface pixels are not claimed to be a verified client crop/WGC receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
from io import BytesIO
import json
import math
from pathlib import Path
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.physical_turn_visual_pair import MAX_PNG_BYTES, require
from scripts.probe_dxcam import _snapshot
from scripts.waypoint_progress import write_json_atomic


class _WindowsCaptureBackend:
    def start(self, hwnd, on_frame, on_closed):
        require(importlib.metadata.version("windows-capture") == "2.0.1", "windows-capture-2.0.1-required")
        from windows_capture import WindowsCapture
        capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False)
        capture.frame_handler, capture.closed_handler = on_frame, on_closed
        return capture, capture.start_free_threaded()


class _PngBuffer(BytesIO):
    def write(self, data):
        require(self.tell() + len(data) <= MAX_PNG_BYTES, "frame-image-oversized")
        return super().write(data)


def _image_quality(image):
    from PIL import ImageStat
    statistics = ImageStat.Stat(image.resize((96, 64)))
    return dict(channelExtrema=statistics.extrema, channelVariance=statistics.var,
                potentiallyBlankOrBlack=max(v[1] for v in statistics.extrema) <= 16 or max(statistics.var) <= 1)


def probe(expected_host, physical_pid, output, *, timeout=5, select=None, snapshot=None,
          backend_loader=None, clock=None):
    require(expected_host == "AMD-DESKTOP" and socket.gethostname().upper() == expected_host, "AMD-DESKTOP-host-required")
    require(type(physical_pid) is int and physical_pid > 0, "explicit-positive-pid-required")
    require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 30, "invalid-timeout")
    output = Path(output).resolve()
    require(not output.exists() and output.parent.is_dir(), "fresh-output-required")
    select, snapshot = select or physical_rift.select_physical, snapshot or _snapshot
    backend_loader, clock = backend_loader or _WindowsCaptureBackend, clock or time.monotonic
    started = clock()
    deadline = started + timeout
    result = dict(schemaVersion=1, status="withheld", diagnosticKind="windows-capture-hwnd-pilot/1",
        windowsCaptureVersion="2.0.1", machine=expected_host, requestedPid=physical_pid,
        inputSent=False, focusChanged=False, nativeCameraBracket=False, timeoutSeconds=timeout,
        deadlineKind="cooperative; backend startup/stop/wait and cleanup may overrun",
        timebase="WGC SystemRelativeTime, 100-nanosecond ticks; no independently calibrated UTC/age",
        timestampAgeSeconds=None,
        limitations=["Diagnostic HWND window-surface candidate; not an observe/WGC receipt.",
            "Window frame/client mapping, occlusion behavior and fresh game-render semantics unqualified.",
            "No native camera bracket or uninterrupted/ABA identity continuity proof."])
    done, callback_lock = threading.Event(), threading.Lock()
    state = {}
    target, geometry, control, capture = None, None, None, None

    def guard():
        current = snapshot(target)
        rect = current.get("clientRect")
        require(current.get("foreground") is True, "target-not-foreground")
        require(isinstance(rect, (list, tuple)) and len(rect) == 4 and all(type(n) is int for n in rect)
                and rect[2] > 0 and rect[3] > 0, "invalid-client-geometry")
        require(geometry is None or current == geometry, "client-or-foreground-changed")
        return current

    def on_frame_arrived(frame, internal_control):
        with callback_lock:
            if not done.is_set():
                try:
                    require(clock() < deadline, "frame-arrived-after-deadline")
                    require(type(frame.width) is int and type(frame.height) is int
                            and 64 <= frame.width <= 4096 and 64 <= frame.height <= 2160,
                            "invalid-frame-dimensions")
                    require(type(frame.timespan) is int and frame.timespan > 0, "invalid-frame-timespan")
                    require(tuple(frame.frame_buffer.shape) == (frame.height, frame.width, 4)
                            and str(frame.frame_buffer.dtype) == "uint8", "invalid-frame-shape-or-format")
                    state.update(frame=frame.frame_buffer.copy(), width=frame.width, height=frame.height,
                                 timespan=frame.timespan, frameCopiedAtUtc=datetime.now(timezone.utc).isoformat(),
                                 frameCopiedMonotonic=clock())
                except Exception as error:
                    state["error"] = str(error)
                finally:
                    try:
                        internal_control.stop()
                    except Exception as error:
                        state["error"] = "internal-stop-failed: " + str(error)
                    done.set()
            else:
                internal_control.stop()

    def on_closed():
        with callback_lock:
            if not done.is_set():
                state["error"] = "capture-closed-before-frame"
                done.set()

    try:
        selection = select(expected_host, physical_pid)
        require(selection.get("status") == "ready", "target-not-ready")
        target = selection["target"]
        require(target.get("hostName", "").upper() == expected_host and target.get("processId") == physical_pid
                and type(target.get("hwnd")) is int and target["hwnd"] > 0, "target-mismatch")
        geometry = guard()
        result.update(targetBefore=target, snapshotBefore=geometry)
        require(clock() < deadline, "cooperative-deadline-expired")
        capture, control = backend_loader().start(target["hwnd"], on_frame_arrived, on_closed)
        while not done.is_set():
            remaining = deadline - clock()
            require(remaining > 0, "capture-frame-deadline-expired")
            guard()
            done.wait(min(.05, remaining))
        require(clock() < deadline, "cooperative-deadline-expired")
        require("error" not in state, state.get("error", "callback-failed"))
        require("frame" in state, "frame-unavailable")
        guard()
        result["status"] = "diagnostic-hwnd-frame-candidate"
    except Exception as error:
        result.update(status="withheld", reason=str(error), errorType=type(error).__name__)
    finally:
        # Python's external stop joins the capture thread; wait is explicit and
        # idempotent after stop in the pinned API. Never force terminate it.
        errors = []
        if control is not None:
            for action in ("stop", "wait"):
                try:
                    getattr(control, action)()
                except Exception as error:
                    errors.append(action + ": " + str(error))
        result["cleanupErrors"] = errors
        if errors:
            result.update(status="withheld", reason="capture-cleanup-failed")
        if target is not None:
            try:
                final = select(expected_host, physical_pid)
                require(final.get("status") == "ready" and final["target"] == target, "final-target-identity-changed")
                result.update(targetAfter=final["target"], snapshotAfter=guard())
            except Exception as error:
                result.update(status="withheld", reason=str(error))
    result.update(elapsedSeconds=clock()-started, deadlineExceeded=clock() >= deadline,
                  report=str(output / "probe.json"))
    if result["deadlineExceeded"] and result["status"] == "diagnostic-hwnd-frame-candidate":
        result.update(status="withheld", reason="cooperative-deadline-expired")
    output.mkdir()
    if result["status"] == "diagnostic-hwnd-frame-candidate":
        path = output / "frame.png"
        try:
            from PIL import Image
            image = Image.fromarray(state["frame"][..., [2, 1, 0]])
            quality = _image_quality(image)
            interior_rect = [image.width//10, image.height//10, image.width-image.width//10,
                             image.height-image.height//10]
            interior = _image_quality(image.crop(tuple(interior_rect)))
            whole_blank = quality["potentiallyBlankOrBlack"]
            quality.update(interiorHeuristic=dict(interior,
                basis="central-80-percent-window-surface; not verified client mapping", rectangle=interior_rect),
                wholeSurfacePotentiallyBlankOrBlack=whole_blank,
                potentiallyBlankOrBlack=whole_blank or interior["potentiallyBlankOrBlack"])
            result.update(frameWidth=state["width"], frameHeight=state["height"], frameTimespan=state["timespan"],
                frameCopiedAtUtc=state["frameCopiedAtUtc"], frameCopiedMonotonic=state["frameCopiedMonotonic"],
                frameCoordinateSpace="window-capture-surface; client mapping unqualified", quality=quality)
            if whole_blank:
                result.update(status="withheld", reason="frame-blank-or-uninformative")
            elif interior["potentiallyBlankOrBlack"]:
                result.update(status="withheld", reason="frame-interior-blank-or-uninformative")
            else:
                with _PngBuffer() as buffer:
                    image.save(buffer, "PNG")
                    raw = buffer.getvalue()
                with path.open("xb") as destination:
                    destination.write(raw)
                result.update(image=str(path), imageBytes=len(raw), imageSha256=hashlib.sha256(raw).hexdigest())
        except Exception as error:
            # This path belongs to our freshly created output directory only.
            path.unlink(missing_ok=True)
            result.update(status="withheld", reason="frame-image-save-failed: " + str(error), errorType=type(error).__name__)
    write_json_atomic(output / "probe.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, choices=("AMD-DESKTOP",))
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    try:
        result = probe(args.expected_host, args.physical_pid, args.output, timeout=args.timeout)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "withheld", "reason": str(error)}))
        return 2
    print(json.dumps({key: result[key] for key in ("status", "elapsedSeconds", "report")}))
    return 0 if result["status"] == "diagnostic-hwnd-frame-candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
