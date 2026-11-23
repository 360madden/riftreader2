"""One fenced, warm DXGI desktop event between native facing reads; candidate only."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import observe_physical, physical_rift as native
from scripts.probe_dxcam import _DXcamBackend, _output, _snapshot, check_capture_python, require
from scripts.waypoint_progress import write_json_atomic
from scripts.live_physical_waypoints import _expected_target, _hwnd_argument


def check_dependencies(expected_host, native_reader=None):
    """Check Save view startup without importing DXcam or selecting a window."""
    result = {"status": "blocked", "workflow": "dxcam", "ownerHost": socket.gethostname(),
              "pythonExecutable": sys.executable, "inputSent": False, "focusChanged": False}
    if not native.is_local_host(expected_host):
        return dict(result, reason="host-mismatch")
    result.update(check_capture_python())
    if "reason" in result:
        return result
    reader = native.check_native_reader(expected_host, native_reader, kind="facing")
    result["nativeReader"] = reader
    if reader["status"] != "ready":
        return dict(result, reason=reader["reason"])
    return dict(result, status="ready")


class Qpc:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name in ("QueryPerformanceCounter", "QueryPerformanceFrequency"):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = [ctypes.POINTER(ctypes.c_longlong)], ctypes.c_int
    def call(self, name):
        value = ctypes.c_longlong()
        require(getattr(self.kernel, name)(ctypes.byref(value)) != 0, "QPC-call-failed")
        return value.value
    def read(self):
        return self.call("QueryPerformanceCounter")
    def frequency(self):
        return self.call("QueryPerformanceFrequency")


def calibrate(qpc, perf_ns=time.perf_counter_ns, info=None):
    info = info or time.get_clock_info("perf_counter")
    require(info.monotonic and not info.adjustable, "Python-clock-not-monotonic-fixed")
    frequency = qpc.frequency()
    require(type(frequency) is int and frequency > 0, "invalid-QPC-frequency")
    samples = []
    for _ in range(8):
        q0, p, q1 = qpc.read(), perf_ns(), qpc.read()
        require((not samples or q0 >= samples[-1]["qpcAfter"]) and q0 <= q1 and (q0 - 1) * 10**9 <= p * frequency <= (q1 + 1) * 10**9,
                "Python-QPC-clock-incompatible")
        samples.append({"qpcBefore": q0, "perfCounterNs": p, "qpcAfter": q1,
                        "bracketWidthSeconds": (q1 - q0) / frequency})
    require(qpc.frequency() == frequency, "QPC-frequency-changed")
    return {"frequency": frequency, "implementation": info.implementation,
            "orderingAllowanceTicks": 1, "samples": samples}


def compare(reports, target):
    values = [native._native_values("facing", report) for report in reports]
    first, last = [report["observation"] for report in reports]
    identity = reports[0]["identity"]
    stamp = native._utc_tick_order_key
    require(stamp(first["completedAtUtc"]) <= stamp(last["startedAtUtc"]), "native-source-acquisition-order-invalid")
    require(reports[1]["identity"] == identity and identity["processId"] == target["processId"]
            and str(identity["processStartUtcTicks"]) == str(target["processStartUtcTicks"])
            and identity["executableSha256"].casefold() == target["executableSha256"].casefold(),
            "native-target-identity-mismatch")
    for field in ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal", "rawBits",
                  "entityPositionRawBits", "opticalCameraCandidate"):
        require(first.get(field) == last.get(field), "native-camera-player-bracket-changed")
    for source in ("primary", "secondary"):
        require(first["positionOrientationCandidate"][source]["rawBits"] ==
                last["positionOrientationCandidate"][source]["rawBits"], "native-orientation-changed")
    require(first.get("opticalCameraCandidate", {}).get("status") == "available-candidate"
            and all(row.get("targetProjectionCameraStableCandidate") is True for row in (first, last)),
            "native-camera-not-stable")
    require(all(row["opticalCameraCandidate"] == row.get("opticalCameraAfterTargetCandidate")
                for row in (first, last)), "native-camera-target-bracket-changed")
    fields = ("status", "reason", "targetKey", "positionXYZCandidate", "screenPointCandidate", "guardStatus")
    require([{k: (value.get("selectedTargetProjectionCandidate") or {}).get(k) for k in fields}
             for value in values][0] ==
            [{k: (value.get("selectedTargetProjectionCandidate") or {}).get(k) for k in fields}
             for value in values][1], "selected-target-changed")
    require(values[-1]["opticalCamera"].get("projectionAvailableCandidate") is True, "full-projection-required")
    return values[-1]


def probe(expected_host, physical_pid, display, output, *, timeout=10, select=None, snapshot=None,
          backend_loader=None, read_native=None, qpc=None, perf_ns=None, clock=None, sleep=None, clock_info=None,
          expected_start_ticks=None, expected_sha256=None, expected_hwnd=None, native_reader=None):
    require(native.valid_host_name(expected_host)
            and socket.gethostname().casefold() == expected_host.casefold(), "host-mismatch")
    require(type(physical_pid) is int and physical_pid > 0, "explicit-positive-pid-required")
    require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 30, "invalid-timeout")
    require(isinstance(display, str) and display, "explicit-display-required")
    expected = _expected_target(expected_start_ticks, expected_sha256, expected_hwnd)
    output = Path(output).resolve()
    require(not output.exists() and output.parent.is_dir(), "fresh-output-required")
    from scripts.plot_physical_units import _saved

    select, snapshot = select or native.select_physical, snapshot or _snapshot
    backend_loader = backend_loader or _DXcamBackend
    read_native = native.bind_native_reader(read_native or native.read_native, native_reader)
    clock, sleep, perf_ns = clock or time.perf_counter, sleep or time.sleep, perf_ns or time.perf_counter_ns
    started, camera, target, backend, geometry = clock(), None, None, None, None
    deadline, result = started + timeout, {"status": "withheld", "diagnosticKind": "dxcam-native-event-pair/1",
        "machine": expected_host, "inputSent": False, "focusChanged": False,
        "limitations": ["Desktop-composite event bracket candidate; not a WGC receipt.",
            "DXcam ticks use LastPresentTime with LastMouseUpdateTime fallback; no fresh RIFT-render claim.",
            "Occlusion, world identity, terrain, unit freshness and uninterrupted/ABA continuity unqualified.",
            "Deadline is cooperative; native/GPU calls and cleanup may overrun."]}
    def guard():
        value = snapshot(target)
        require(value.get("foreground") is True, "target-not-foreground")
        rect = value.get("clientRect")
        require(isinstance(rect, (list, tuple)) and len(rect) == 4 and
                all(type(x) is int for x in rect) and rect[2] > 0 and rect[3] > 0, "invalid-client")
        require(geometry is None or value == geometry, "client-or-foreground-changed")
        return value
    def check_deadline():
        require(clock() < deadline, "cooperative-deadline-expired")
    try:
        observe_physical.require_clear_desktop_turn()
        selection = select(expected_host, physical_pid)
        require(selection.get("status") == "ready", "target-not-ready")
        target = selection["target"]
        require(target["processId"] == physical_pid
                and target["hostName"].casefold() == expected_host.casefold(), "target-mismatch")
        if expected is not None:
            require(str(target.get("processStartUtcTicks")) == expected["processStartUtcTicks"]
                    and str(target.get("executableSha256", "")).casefold() == expected["executableSha256"]
                    and target.get("hwnd") == expected["hwnd"], "expected-target-identity-mismatch")
        result["expectedTarget"] = expected
        geometry = guard()
        result.update(targetBefore=target, snapshotBefore=geometry, requestedDisplay=display)
        qpc = qpc or Qpc()
        result["clockBefore"] = calibrate(qpc, perf_ns, clock_info)
        frequency = result["clockBefore"]["frequency"]
        check_deadline()
        backend = backend_loader()
        selected, crop = _output(backend.outputs(), display, geometry["clientRect"])
        result.update(selectedOutput=selected, outputLocalCrop=crop)
        camera = backend.create(selected, crop)
        camera.start(target_fps=60, video_mode=False, delay=0)
        def frame_after(fence):
            while True:
                check_deadline()
                guard()
                q0 = qpc.read()
                pair = backend.peek(camera)
                q1 = qpc.read()
                require(q1 >= q0, "QPC-regressed")
                if pair is not None:
                    frame, ticks, seconds, frame_frequency = pair
                    require(type(ticks) is int and ticks > 0 and frame_frequency == frequency
                            and math.isfinite(seconds) and abs(seconds - ticks / frequency) < 1e-8,
                            "invalid-frame-timebase")
                    require(ticks <= q1 + 1, "future-backend-event")
                    if ticks > fence + 1:
                        width, height = geometry["clientRect"][2:]
                        require(tuple(frame.shape) == (height, width, 4) and str(frame.dtype) == "uint8", "frame-shape-changed")
                        guard()
                        current, current_crop = _output(backend.outputs(), display, geometry["clientRect"])
                        require(current == selected and current_crop == crop, "output-changed")
                        check_deadline()
                        return frame.copy(), {"backendTicks": ticks, "backendSeconds": seconds,
                            "qpcPeekBefore": q0, "qpcPeekAfter": q1,
                            "backendEventAgeBoundsSeconds": [max(0, (q0-ticks-1)/frequency), (q1-ticks+1)/frequency]}
                sleep(.005)
        _, result["warmupFrame"] = frame_after(-1)
        guard()
        begin, q_begin = clock(), qpc.read()
        before = read_native(selection, "facing", samples=1, include_target=True)
        fence = qpc.read()  # Native subprocess has fully returned before this fence.
        result["nativeBeforeOutput"] = before.get("nativeOutput")
        require(before.get("status") == "complete", "native-before-unavailable")
        frame, event = frame_after(fence)
        accepted = qpc.read()
        after_invoked = qpc.read()
        after = read_native(selection, "facing", samples=1, include_target=True)
        completed, end = qpc.read(), clock()
        result["nativeAfterOutput"] = after.get("nativeOutput")
        result.update(event=event, qpcMarks={"nativeBeforeInvoked": q_begin, "nativeBeforeReturnedFence": fence,
            "frameAccepted": accepted, "nativeAfterInvoked": after_invoked, "nativeAfterReturned": completed},
            nativeBracketSpanSeconds=end-begin)
        require(0 <= end-begin <= 5 and 0 <= completed-q_begin <= 5*frequency, "native-bracket-exceeded-five-seconds")
        require(after.get("status") == "complete", "native-after-unavailable")
        check_deadline()
        require(fence + 1 < event["backendTicks"] <= accepted + 1 and accepted <= after_invoked <= completed, "event-order-invalid")
        reports, sources = [], []
        for side in (before, after):
            require(side.get("target") == target, "native-read-target-changed")
            report, source = _saved(side["nativeOutput"])
            reports.append(report)
            sources.append(source)
        result["nativeSources"] = sources
        result["nativeValues"] = compare(reports, target)
        result["clockAfter"] = calibrate(qpc, perf_ns, clock_info)
        require(result["clockAfter"]["frequency"] == frequency, "QPC-frequency-changed")
        result["status"] = "stable-native-composite-event-candidate"
    except Exception as error:
        result.update(status="withheld", reason=str(error), errorType=type(error).__name__)
    finally:
        errors = []
        if camera is not None:
            for action in ("stop", "release"):
                try:
                    getattr(camera, action)()
                except Exception as error:
                    errors.append(action + ": " + str(error))
        result["cleanupErrors"] = errors
        if errors:
            result.update(status="withheld", reason="camera-cleanup-failed")
        if target is not None:
            try:
                final = select(expected_host, physical_pid)
                require(final.get("status") == "ready" and final["target"] == target, "final-target-changed")
                result.update(targetAfter=final["target"], snapshotAfter=guard())
                if backend is not None and "selectedOutput" in result:
                    last, last_crop = _output(backend.outputs(), display, geometry["clientRect"])
                    require(last == selected and last_crop == crop, "final-output-changed")
                observe_physical.require_clear_desktop_turn()
            except Exception as error:
                result.update(status="withheld", reason=str(error))
    result.update(elapsedSeconds=clock()-started, report=str(output / "pair.json"))
    output.mkdir()
    if result["status"] == "stable-native-composite-event-candidate":
        from PIL import Image
        image = output / "frame.png"
        Image.fromarray(frame[..., [2, 1, 0]]).save(image, "PNG")
        result.update(image=str(image), imageSha256=hashlib.sha256(image.read_bytes()).hexdigest())
    write_json_atomic(output / "pair.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True, help="verified local Windows machine name")
    parser.add_argument("--check-dependencies", action="store_true",
                        help="check the DXcam environment and Save view reader without selecting RIFT")
    parser.add_argument("--physical-pid", type=int)
    parser.add_argument("--display")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--expect-start-ticks")
    parser.add_argument("--expect-sha256")
    parser.add_argument("--expect-hwnd", type=_hwnd_argument)
    parser.add_argument("--native-reader", type=Path,
                        help="absolute local path to a published RiftReader2.Live.exe")
    args = parser.parse_args(argv)
    capture_args = (args.physical_pid, args.display, args.output)
    if args.check_dependencies:
        if any(value is not None for value in (*capture_args, args.timeout,
                                                args.expect_start_ticks, args.expect_sha256, args.expect_hwnd)):
            parser.error("--check-dependencies accepts only --expected-host and --native-reader")
        result = check_dependencies(args.expected_host, args.native_reader)
        print(json.dumps(result))
        return 0 if result["status"] == "ready" else 2
    if any(value is None for value in capture_args):
        parser.error("capture requires --physical-pid, --display and --output")
    try:
        result = probe(args.expected_host, args.physical_pid, args.display, args.output,
                       timeout=10 if args.timeout is None else args.timeout,
                       expected_start_ticks=args.expect_start_ticks, expected_sha256=args.expect_sha256,
                       expected_hwnd=args.expect_hwnd, native_reader=args.native_reader)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "withheld", "reason": str(error)}))
        return 2
    print(json.dumps({k: result[k] for k in ("status", "elapsedSeconds", "report")}))
    return 0 if result["status"] == "stable-native-composite-event-candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
