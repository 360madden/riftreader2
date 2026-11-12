"""Bounded read-only native waypoint projection feed for an owned overlay.

Candidate software projections only: world/zone, occlusion and terrain unverified.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift as physical
from scripts.waypoint_progress import write_json_atomic


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load_route(path):
    raw = Path(path).read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    recording = document.get("recording", {})
    require(recording.get("complete") is True and recording.get("version") == 1,
            "complete-recorded-route-required")
    provenance = recording.get("identity")
    require(isinstance(provenance, dict), "recording-identity-required")
    identity = provenance.get("runtimeIdentity", provenance)
    require(isinstance(identity, dict) and all(isinstance(identity.get(key), str) and identity[key]
            for key in ("machine", "gameBuildSha256", "unitKey")), "recording-identity-required")
    points, heights = document.get("waypoints"), document.get("heights")
    require(isinstance(points, list) and 1 <= len(points) <= 20 and isinstance(heights, list)
            and len(points) == len(heights), "recorded-xyz-heights-required")
    parsed = []
    for number, (point, height) in enumerate(zip(points, heights), 1):
        require(isinstance(point, list) and len(point) == 3 and isinstance(point[0], str),
                "invalid-recorded-waypoint")
        require(all(type(v) in (int, float) and math.isfinite(v) for v in (point[1], height, point[2])),
                "finite-recorded-xyz-heights-required")
        parsed.append({"number": number, "label": point[0], "xyz": dict(x=point[1], y=height, z=point[2])})
    return {"points": parsed, "identity": deepcopy(identity), "recordingIdentity": deepcopy(provenance),
            "path": str(Path(path).resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
            "document": document}


class ProjectionProvider:
    """One pinned selection, serial reads and plain packets; no overlay calls."""
    def __init__(self, selection, route, snapshot, *, read=None, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc), max_age=.8):
        require(selection.get("status") == "ready", "physical-selection-not-ready")
        self.selection, self.route = deepcopy(selection), deepcopy(route)
        self.target = self.selection["target"]
        self.snapshot, self.read = snapshot, read or physical.read_native
        self.clock, self.utcnow, self.max_age = clock, utcnow, max_age
        identity = route["identity"]
        require(identity["machine"].casefold() == self.target["hostName"].casefold()
                and identity["gameBuildSha256"].casefold() == self.target["executableSha256"].casefold(),
                "route-host-build-mismatch")
        self.latest_native = None
        self.last_stream_receipt = None
        self.stream_rows = 0
        self.stream_stderr = ""

    def acquire(self):
        before = self.snapshot(self.target)
        require(before.get("foreground") is True, "target-not-foreground")
        acquired = self.clock()  # Intentionally before child launch, not after it returns.
        result = self.read(self.selection, "facing", samples=1, include_target=True)
        self.latest_native = result.get("nativeOutput")
        require(result.get("status") == "complete", result.get("reason", "native-facing-unavailable"))
        require(result.get("target") == self.target, "native-selection-changed")
        report = json.loads(Path(self.latest_native).read_text(encoding="utf-8-sig"))
        return self.build_frame(report, acquired, before)

    def build_frame(self, report, acquired, before, *, stream=False):
        identity = report.get("identity", {})
        require(identity.get("processId") == self.target["processId"]
                and str(identity.get("processStartUtcTicks")) == str(self.target["processStartUtcTicks"])
                and str(identity.get("executableSha256", "")).casefold() == self.target["executableSha256"].casefold(),
                "native-identity-mismatch")
        values = physical._native_values("facing", report)
        require(values["sampleCount"] == 1, "single-native-facing-sample-required")
        require(values["playerKey"] == self.route["identity"]["unitKey"], "recorded-player-mismatch")
        row = report["observation"]
        if not stream:
            require(row.get("targetProjectionCameraStableCandidate") is True, "native-camera-not-stable")
        optical = values.get("opticalCamera")
        require(isinstance(optical, dict) and optical.get("status") == "available-candidate"
                and optical.get("projectionAvailableCandidate") is True, "full-camera-projection-required")
        sampled = datetime.fromisoformat(values["sampledAtUtc"].replace("Z", "+00:00"))
        age = (self.utcnow() - sampled).total_seconds()
        require(sampled.utcoffset().total_seconds() == 0 and -.1 <= age <= self.max_age, "native-sample-stale")
        after = self.snapshot(self.target)
        require(after.get("foreground") is True and before.get("clientRect") == after.get("clientRect"),
                "target-foreground-or-geometry-changed")
        require(0 <= self.clock() - acquired <= self.max_age, "native-acquisition-expired")
        camera = row["opticalCameraCandidate"]
        points = []
        for point in self.route["points"]:
            xyz = point["xyz"]
            points.append({"number": point["number"], "label": point["label"],
                "ground": physical._project_world_point(camera, xyz),
                "beaconTop": physical._project_world_point(camera, dict(x=xyz["x"], y=xyz["y"] + 1.5, z=xyz["z"]))})
        return {"target": deepcopy(self.target), "acquiredMonotonic": acquired,
                "clientRect": list(after["clientRect"]), "points": points,
                "playerGround": physical._project_world_point(camera, values["positionXYZCandidate"])}

    def stream_frame(self, packet, before, *, previous_end=None):
        require(packet.get("recordType") == "native-current-facing-stream-row/1"
                and packet.get("status") == "candidate", "invalid-stream-row")
        row = packet["observation"]
        started = physical._utc_tick_order_key(row["startedAtUtc"])
        completed = physical._utc_tick_order_key(row["completedAtUtc"])
        emitted = physical._utc_tick_order_key(packet["emittedAtUtc"])
        require(started <= completed <= emitted and (previous_end is None or previous_end <= started),
                "stream-acquisition-order-invalid")
        received = self.clock()
        now = self.utcnow()
        age = (now - started[0]).total_seconds()
        elapsed = packet.get("captureElapsedMilliseconds")
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0,
                "stream-capture-elapsed-required")
        require(age >= -.1, "stream-clock-future")
        require((now - emitted[0]).total_seconds() >= -.1, "stream-clock-future")
        age = max(elapsed / 1000, age)
        require(age <= self.max_age, "stream-row-expired")
        report = dict(schemaVersion=1, status="complete", identity=packet["identity"],
            contractVersion="native-current-facing-candidate-samples/1", requestedSamples=1,
            completedSamples=1, observation=row, observations=[row])
        return self.build_frame(report, received - age, before, stream=True), completed


def _stop_child(child):
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=1)


def stream_burst(provider, channel, stop, counts, *, popen=subprocess.Popen, samples=20):
    """One owned <=5-second child; bounded NDJSON and concurrent stderr draining."""
    if stop.is_set():
        return
    before = provider.snapshot(provider.target)
    require(before.get("foreground") is True, "target-not-foreground")
    require(type(samples) is int and 1 <= samples <= 30, "stream-samples-invalid")
    require(provider.target["hostName"].casefold() == socket.gethostname().casefold(), "host-mismatch")
    child = popen([str(physical.NATIVE_EXE), "sample-current-facing-stream", "--pid",
        str(provider.target["processId"]), "--start-ticks", str(provider.target["processStartUtcTicks"]),
        "--samples", str(samples), "--interval-ms", "50"], cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = queue.Queue(maxsize=32)
    stderr = bytearray()
    def stdout_pump():
        try:
            while True:
                line = child.stdout.readline(1024 * 1024 + 1)
                if not line:
                    lines.put_nowait(("eof", None))
                    return
                if len(line) > 1024 * 1024:
                    raise ValueError("stream-line-too-large")
                lines.put_nowait(("line", line))
        except Exception as error:
            try:
                lines.put_nowait(("error", str(error)))
            except queue.Full:
                pass
    def stderr_pump():
        try:
            while True:
                chunk = child.stderr.read(1024)
                if not chunk:
                    break
                stderr.extend(chunk)
                del stderr[:-4096]
        except (OSError, ValueError):
            pass
    pumps = [threading.Thread(target=stdout_pump, daemon=True), threading.Thread(target=stderr_pump, daemon=True)]
    for pump in pumps:
        pump.start()
    deadline, sequence, receipt, previous_end = time.monotonic() + 5, 0, None, None
    try:
        while True:
            if stop.is_set():
                return
            require(time.monotonic() < deadline, "stream-child-timeout")
            try:
                kind, raw = lines.get(timeout=.05)
            except queue.Empty:
                current = provider.snapshot(provider.target)
                require(current.get("foreground") is True and current.get("clientRect") == before.get("clientRect"),
                        "target-foreground-or-geometry-changed")
                continue
            if kind == "error":
                raise ValueError(raw)
            if kind == "eof":
                break
            packet = json.loads(raw)
            require(receipt is None, "stream-data-after-end")
            if packet.get("recordType") == "native-current-facing-stream-end/1":
                require(packet.get("status") in ("complete", "duration-limit")
                        and packet.get("requestedSamples") == samples
                        and packet.get("completedSamples") == sequence
                        and (packet["status"] != "complete" or sequence == samples), "invalid-stream-end")
                receipt = packet
                continue
            require(sequence < samples and type(packet.get("sequence")) is int
                    and packet["sequence"] == sequence, "stream-sequence-invalid")
            current = provider.snapshot(provider.target)
            require(current.get("foreground") is True and current.get("clientRect") == before.get("clientRect"),
                    "target-foreground-or-geometry-changed")
            frame, previous_end = provider.stream_frame(packet, current, previous_end=previous_end)
            sequence += 1
            provider.stream_rows += 1
            if not stop.is_set():
                _latest(channel, {"frame": frame})
                counts["acquired"] += 1
        require(receipt is not None, "stream-end-missing")
        require(child.wait(timeout=max(.01, deadline - time.monotonic())) == 0, "stream-child-failed")
        provider.last_stream_receipt = receipt
    finally:
        _stop_child(child)
        for pump in pumps:
            pump.join(timeout=1)
        provider.stream_stderr = bytes(stderr).decode("utf-8", errors="replace")
        child.stdout.close()
        child.stderr.close()


def stream_feed(provider, channel, stop, counts):
    while not stop.is_set():
        counts["attempts"] += 1
        try:
            stream_burst(provider, channel, stop, counts)
        except Exception as error:
            counts["failures"] += 1
            counts["latestFailure"] = str(error)
            if not stop.is_set():
                _latest(channel, {"reason": str(error)})
        stop.wait(.15)


def _latest(channel, packet):
    try:
        channel.get_nowait()
    except queue.Empty:
        pass
    channel.put_nowait(packet)


def feed(provider, channel, stop, counts):
    while not stop.is_set():
        counts["attempts"] += 1
        try:
            frame = provider.acquire()
            if not stop.is_set():
                _latest(channel, {"frame": frame})
                counts["acquired"] += 1
        except Exception as error:
            counts["failures"] += 1
            counts["latestFailure"] = str(error)
            if not stop.is_set():
                _latest(channel, {"reason": str(error)})
        stop.wait(.05)


def _expected_target(start_ticks, sha256, hwnd):
    supplied = [value is not None for value in (start_ticks, sha256, hwnd)]
    require(not any(supplied) or all(supplied), "all-target-expectations-required-together")
    if not any(supplied):
        return None
    require(type(start_ticks) in (str, int) and re.fullmatch(r"[0-9]+", str(start_ticks)) is not None
            and 0 < int(start_ticks) <= 3155378975999999999, "invalid-expected-start-ticks")
    require(isinstance(sha256, str) and re.fullmatch(r"[0-9a-fA-F]{64}", sha256) is not None,
            "invalid-expected-sha256")
    require(type(hwnd) is int and 0 < hwnd < 2**64, "invalid-expected-hwnd")
    return {"processStartUtcTicks": str(int(start_ticks)), "executableSha256": sha256.lower(), "hwnd": hwnd}


def _hwnd_argument(value):
    try:
        return int(value, 16 if value.lower().startswith("0x") else 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("HWND must be a decimal integer or 0x hexadecimal integer") from error


def apply_saved_progress(frame, progress_file, route):
    """Decorate a fresh projection from a checked historical cursor, never control it."""
    from scripts.waypoint_marker_progress import read_marker_progress
    progress = read_marker_progress(progress_file, route["document"], route["identity"])
    states = progress.get("states", {})
    for point in frame["points"]:
        point.pop("routeState", None)
        if point["number"] in states:
            point["routeState"] = states[point["number"]]
    return progress


def run(expected_host, physical_pid, route_path, *, duration=60, max_age=.8, output=None, reader="stream",
        expected_start_ticks=None, expected_sha256=None, expected_hwnd=None, stop_file=None,
        presenter="native", progress_file=None):
    require(isinstance(expected_host, str) and expected_host.casefold() == socket.gethostname().casefold(), "host-mismatch")
    require(type(physical_pid) is int and physical_pid > 0, "explicit-physical-pid-required")
    require(type(duration) in (int, float) and math.isfinite(duration) and 0 < duration <= 600, "duration-must-be-positive-at-most-600")
    require(type(max_age) in (int, float) and math.isfinite(max_age) and .1 <= max_age <= 2, "max-age-must-be-0.1-through-2")
    require(reader in ("single", "stream"), "invalid-reader-mode")
    require(presenter in ("native", "qt"), "invalid-presenter")
    expected = _expected_target(expected_start_ticks, expected_sha256, expected_hwnd)
    if stop_file is not None:
        stop_file = Path(stop_file)
        require(stop_file.is_absolute() and stop_file.parent.is_dir() and not stop_file.exists(),
                "new-absolute-stop-file-required")
    if output is not None:
        output = Path(output).resolve()
        require(not output.exists() and output.parent.is_dir(), "new-output-json-required")
    if progress_file is not None:
        progress_file = Path(progress_file)
        require(progress_file.is_absolute() and progress_file.parent.is_dir(), "absolute-progress-file-required")
    route = load_route(route_path)
    selection = physical.select_physical(expected_host, physical_pid)
    require(selection.get("status") == "ready", selection.get("reason", "physical-selection-not-ready"))
    require(selection["target"]["processId"] == physical_pid, "selected-pid-mismatch")
    if expected is not None:
        target = selection["target"]
        require(str(target.get("processStartUtcTicks")) == expected["processStartUtcTicks"]
                and str(target.get("executableSha256", "")).casefold() == expected["executableSha256"]
                and target.get("hwnd") == expected["hwnd"], "expected-target-identity-mismatch")
    from scripts.physical_waypoint_overlay import PhysicalWaypointOverlay, target_snapshot
    provider = ProjectionProvider(selection, route, target_snapshot, max_age=max_age)
    window_options = {}
    if presenter == "qt":
        try:
            from scripts.qt_waypoint_overlay import QtOwnedWindow
        except ImportError as error:
            raise ValueError("Qt overlay unavailable; use the isolated overlay environment "
                             "with requirements-overlay.txt: " + str(error)) from error
        window_options["window_factory"] = QtOwnedWindow
    overlay = PhysicalWaypointOverlay(selection["target"], max_age=max_age, **window_options)
    stop, channel = threading.Event(), queue.Queue(maxsize=1)
    counts = {"attempts": 0, "acquired": 0, "presented": 0, "failures": 0, "latestFailure": None}
    worker = threading.Thread(target=stream_feed if reader == "stream" else feed,
        args=(provider, channel, stop, counts), name="waypoint-native-reader")
    started = time.monotonic()
    reason = "duration-complete"
    latest_acquired = None
    latest_progress = None
    def cancel(why):
        nonlocal reason
        reason = why
        stop.set()
        overlay.hide(why)
        overlay.window.quit()
    def poll():
        nonlocal latest_acquired, latest_progress
        if stop.is_set():
            return
        if stop_file is not None and stop_file.exists():
            cancel("stop-requested")
            return
        if time.monotonic() - started >= duration:
            cancel("duration-complete")
            return
        try:
            packet = channel.get_nowait()
        except queue.Empty:
            packet = None
        try:
            if packet is not None:
                if "frame" in packet:
                    age = time.monotonic() - packet["frame"]["acquiredMonotonic"]
                    if 0 <= age <= max_age:
                        if progress_file is not None:
                            latest_progress = apply_saved_progress(packet["frame"], progress_file, route)
                        if overlay.present(packet["frame"]):
                            latest_acquired = packet["frame"]["acquiredMonotonic"]
                            counts["presented"] += 1
                        else:
                            counts["latestFailure"] = getattr(overlay, "reason", "presenter-refused-frame")
                            counts["failures"] += 1
                    else:
                        overlay.hide("queued-frame-expired")
                else:
                    overlay.hide(packet["reason"])
            if latest_acquired is not None and time.monotonic() - latest_acquired > max_age:
                overlay.hide("frame-expired")
        except Exception as error:
            counts["latestFailure"] = str(error)
            counts["failures"] += 1
            overlay.hide(str(error))
        overlay.window.after(25, poll)
    overlay.window.protocol("WM_DELETE_WINDOW", lambda: cancel("window-closed"))
    worker.start()
    try:
        overlay.window.after(0, poll)
        overlay.run()
    except KeyboardInterrupt:
        reason = "interrupted"
    finally:
        stop.set()
        overlay.hide(reason)
        # read_native's child has its existing bounded timeout and native lease.
        worker.join()
        overlay.close()
    result = {"status": "read-only-waypoint-feed-stopped", "reason": reason,
        "machine": socket.gethostname(), "target": selection["target"],
        "recordingIdentity": route["recordingIdentity"], "route": route["path"], "routeSha256": route["sha256"],
        "durationSeconds": time.monotonic() - started, "maxAgeSeconds": max_age,
        "counts": counts, "latestNativeReport": provider.latest_native, "inputSent": False,
        "nativeReaderMode": reader, "lastStreamReceipt": provider.last_stream_receipt,
        "presenter": presenter,
        "streamRows": provider.stream_rows, "nativeStderr": provider.stream_stderr,
        "stopFile": str(stop_file) if stop_file is not None else None, "expectedTarget": expected,
        "progressFile": str(progress_file) if progress_file is not None else None,
        "latestSavedProgress": latest_progress,
        "limitations": ["Native software projection candidates; smooth streaming unqualified.",
            "World/zone identity unavailable; matching host/build/player does not prove same world.",
            "Occlusion, depth and terrain not checked.", "Historical recording process epoch preserved.",
            "Marker progress is a saved checkpoint, not proof that playback is active or a point is currently reachable."]}
    if output is not None:
        write_json_atomic(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--max-age", type=float, default=.8)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reader", choices=("single", "stream"), default="stream")
    parser.add_argument("--presenter", choices=("native", "qt"), default="native")
    parser.add_argument("--expect-start-ticks")
    parser.add_argument("--expect-sha256")
    parser.add_argument("--expect-hwnd", type=_hwnd_argument)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--progress-file", type=Path, help="optional absolute saved checkpoint; display only")
    args = parser.parse_args(argv)
    try:
        result = run(args.expected_host, args.physical_pid, args.route, duration=args.duration,
                     max_age=args.max_age, output=args.output, reader=args.reader,
                     expected_start_ticks=args.expect_start_ticks, expected_sha256=args.expect_sha256,
                     expected_hwnd=args.expect_hwnd, stop_file=args.stop_file, presenter=args.presenter,
                     progress_file=args.progress_file)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        result = {"status": "blocked", "reason": str(error), "machine": socket.gethostname(), "inputSent": False}
        if args.output is not None and not args.output.exists() and args.output.parent.is_dir():
            write_json_atomic(args.output, result)
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
