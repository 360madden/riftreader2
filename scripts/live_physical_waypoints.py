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
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift as physical
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_marker_style import DEFAULT_STYLE, load_style


RECOVERABLE_STREAM_ROW_REASONS = frozenset({"full-camera-projection-required"})
TRANSPORT_GAP_REASONS = frozenset({"stream-child-timeout", "stream-end-missing", "stream-child-failed"})


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _display_allowed(snapshot):
    """Only a trusted local snapshot can admit the bound companion for display."""
    return snapshot.get("displayAllowed", snapshot.get("foreground")) is True


def load_route(path):
    raw = Path(path).read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    from scripts.waypoint_measurements import parse_projection_route
    parsed = parse_projection_route(document)
    return {**parsed, "path": str(Path(path).resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(), "document": document}


class ProjectionProvider:
    """One pinned selection, serial reads and plain packets; no overlay calls."""
    def __init__(self, selection, route, snapshot, *, read=None, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc), max_age=.8, target_beacon=False, landmark_number=None):
        require(selection.get("status") == "ready", "physical-selection-not-ready")
        self.selection, self.route = deepcopy(selection), deepcopy(route)
        self.target = self.selection["target"]
        self.snapshot, self.read = snapshot, read or physical.read_native
        self.clock, self.utcnow, self.max_age = clock, utcnow, max_age
        self.target_beacon = target_beacon
        require(landmark_number is None or (type(landmark_number) is int
                and any(point["number"] == landmark_number for point in self.route["points"])),
                "landmark-number-not-in-route")
        self.landmark_number = landmark_number
        identity = route["identity"]
        require(identity["machine"].casefold() == self.target["hostName"].casefold()
                and identity["gameBuildSha256"].casefold() == self.target["executableSha256"].casefold(),
                "route-host-build-mismatch")
        self.latest_native = None
        self.last_stream_receipt = None
        self.stream_rows = 0
        self.stream_stderr = ""
        self.stream_command = None
        self.stream_exit_code = None
        self.stream_last_nonempty_stderr = ""

    def acquire(self):
        before = self.snapshot(self.target)
        require(_display_allowed(before), "target-not-foreground")
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
        row = report["observation"]
        if not stream:
            require(row.get("targetProjectionCameraStableCandidate") is True
                    and physical._same_optical_projection_snapshot(row.get("opticalCameraCandidate"),
                                                                   row.get("opticalCameraAfterTargetCandidate")),
                    "native-camera-not-stable")
        try:
            values = physical._native_values("facing", report)
        except (ValueError, KeyError, TypeError):
            if not self.target_beacon:
                raise
            # Invalid optional target data must not suppress a valid player/route
            # frame; the original non-target fields still pass all reducer checks.
            clean = deepcopy(report)
            rows = clean.get("observations")
            observation = clean.get("observation")
            if not isinstance(rows, list) or not rows or not isinstance(observation, dict) or observation != rows[-1]:
                raise
            for clean_row in [observation, *rows]:
                if isinstance(clean_row, dict):
                    for key in ("targetPositionPairCandidate", "opticalCameraAfterTargetCandidate",
                                "targetProjectionCameraStableCandidate"):
                        clean_row.pop(key, None)
            values = physical._native_values("facing", clean)
        require(values["sampleCount"] == 1, "single-native-facing-sample-required")
        require(values["playerKey"] == self.route["identity"]["unitKey"], "recorded-player-mismatch")
        optical = values.get("opticalCamera")
        require(isinstance(optical, dict) and optical.get("status") == "available-candidate"
                and optical.get("projectionAvailableCandidate") is True, "full-camera-projection-required")
        sampled = datetime.fromisoformat(values["sampledAtUtc"].replace("Z", "+00:00"))
        age = (self.utcnow() - sampled).total_seconds()
        require(sampled.utcoffset().total_seconds() == 0 and -.1 <= age <= self.max_age, "native-sample-stale")
        after = self.snapshot(self.target)
        require(_display_allowed(after) and before.get("clientRect") == after.get("clientRect"),
                "target-foreground-or-geometry-changed")
        require(0 <= self.clock() - acquired <= self.max_age, "native-acquisition-expired")
        camera = row["opticalCameraCandidate"]
        # Match the projector's preserved float32 viewport, including offset views.
        viewport = [struct.unpack("<f", struct.pack("<I", bit))[0]
                    for bit in camera["projectionRawBits"][16:]]
        require(len(viewport) == 4 and all(math.isfinite(value) for value in viewport)
                and 0 <= viewport[0] < viewport[1] <= 1
                and 0 <= viewport[3] < viewport[2] <= 1, "invalid-native-camera-viewport")
        left, right, top, bottom = viewport
        player_xyz = values["positionXYZCandidate"]
        points = []
        for point in self.route["points"]:
            xyz = point["xyz"]
            points.append({"number": point["number"], "label": point["label"],
                "horizontalDistanceCandidate": math.hypot(xyz["x"] - player_xyz["x"],
                                                          xyz["z"] - player_xyz["z"]),
                "ground": physical._project_world_point(camera, xyz),
                "beaconTop": physical._project_world_point(camera, dict(x=xyz["x"], y=xyz["y"] + 1.5, z=xyz["z"]))})
            if point["number"] == self.landmark_number:
                points[-1]["displayLandmark"] = True
        frame = {"target": deepcopy(self.target), "acquiredMonotonic": acquired,
                 "clientRect": list(after["clientRect"]), "points": points,
                 "viewportRectNormalized": [left, 1 - top, right, 1 - bottom],
                 "playerGround": physical._project_world_point(camera, values["positionXYZCandidate"])}
        target = values.get("selectedTargetProjectionCandidate")
        if self.target_beacon and isinstance(target, dict) and target.get("status") == "candidate" \
                and target.get("cameraStableCandidate") is True:
            try:
                xyz, player, ground = target["positionXYZCandidate"], values["positionXYZCandidate"], target["screenPointCandidate"]
                distance = math.hypot(xyz["x"] - player["x"], xyz["z"] - player["z"])
                target_age = (self.utcnow() - datetime.fromisoformat(target["sampledAtUtc"].replace("Z", "+00:00"))).total_seconds()
                if (distance <= 35 and -.1 <= target_age <= self.max_age
                        and ground.get("status") == "available-candidate" and ground.get("insideViewportCandidate") is True
                        and all(type(ground.get(k)) in (int, float) and math.isfinite(ground[k])
                                for k in ("normalizedX", "normalizedY", "clipW"))
                        and 0 <= ground["normalizedX"] <= 1 and 0 <= ground["normalizedY"] <= 1
                        and ground["clipW"] > 1e-5):
                    frame["selectedTarget"] = {"status": "candidate", "targetKey": target["targetKey"],
                        "positionXYZCandidate": deepcopy(xyz), "distance": distance,
                        "cameraStableCandidate": True, "sampledAtUtc": target["sampledAtUtc"],
                        "ground": deepcopy(ground), "beaconTop": physical._project_world_point(
                            camera, dict(x=xyz["x"], y=xyz["y"] + 1.5, z=xyz["z"]))}
            except (ValueError, TypeError, KeyError, OverflowError):
                pass  # Optional target data never replaces or invalidates route markers.
        return frame

    def stream_row_timing(self, packet, *, previous_end=None):
        """Validate a stream envelope and return its acquired time and order cursor."""
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
        return received - age, completed

    def stream_frame_from_validated(self, packet, before, acquired):
        """Project a row whose envelope/order/freshness was already checked."""
        row = packet["observation"]
        report = dict(schemaVersion=1, status="complete", identity=packet["identity"],
            contractVersion="native-current-facing-candidate-samples/1", requestedSamples=1,
            completedSamples=1, observation=row, observations=[row])
        return self.build_frame(report, acquired, before, stream=True)

    def stream_frame(self, packet, before, *, previous_end=None):
        acquired, completed = self.stream_row_timing(packet, previous_end=previous_end)
        return self.stream_frame_from_validated(packet, before, acquired), completed


def _reason_text(error):
    text = str(error).strip() or error.__class__.__name__
    return text[:160]


def _increment_reason(reasons, reason, *, limit=64):
    if reason in reasons:
        reasons[reason] += 1
    elif len([key for key in reasons if key != "other"]) < limit:
        reasons[reason] = 1
    else:
        reasons["other"] = reasons.get("other", 0) + 1


def _record_failure(counts, error, *, row=False):
    reason = _reason_text(error)
    counts["failures"] = counts.get("failures", 0) + 1
    counts["latestFailure"] = reason
    reasons = counts.setdefault("failureReasons", {})
    _increment_reason(reasons, reason)
    if row:
        counts["rejectedRows"] = counts.get("rejectedRows", 0) + 1
    return reason


def _record_interval(counts, prefix, observed):
    previous_key = "last" + prefix + "Monotonic"
    previous = counts.get(previous_key)
    counts[previous_key] = observed
    if previous is None or observed < previous:
        return
    milliseconds = (observed - previous) * 1000
    key = prefix[0].lower() + prefix[1:] + "IntervalMilliseconds"
    timing = counts.setdefault(key, {"samples": 0, "minimum": None, "mean": None, "maximum": None})
    samples = timing["samples"] + 1
    timing["samples"] = samples
    timing["minimum"] = milliseconds if timing["minimum"] is None else min(timing["minimum"], milliseconds)
    timing["maximum"] = milliseconds if timing["maximum"] is None else max(timing["maximum"], milliseconds)
    timing["mean"] = milliseconds if timing["mean"] is None else timing["mean"] + (milliseconds - timing["mean"]) / samples


def _record_hide(counts, reason):
    reason = str(reason)
    reasons = counts.setdefault("hideReasons", {})
    _increment_reason(reasons, reason)


def _stop_child(child):
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=1)


def stream_burst(provider, channel, stop, counts, *, popen=subprocess.Popen, samples=20,
                 interval_ms=50, duration_ms=None):
    """One owned bounded child; NDJSON with concurrent stderr draining."""
    if stop.is_set():
        return
    before = provider.snapshot(provider.target)
    require(_display_allowed(before), "target-not-foreground")
    continuous = type(duration_ms) is int and duration_ms == 0
    extended = type(duration_ms) is int and 2000 < duration_ms <= 600000
    require(duration_ms is None or continuous
            or (type(duration_ms) is int and 1 <= duration_ms <= 600000),
            "stream-duration-invalid")
    require(type(samples) is int and ((continuous and samples == 0)
            or (not continuous and 1 <= samples <= (30000 if extended else 30))), "stream-samples-invalid")
    require(type(interval_ms) is int and 20 <= interval_ms <= 200, "stream-interval-invalid")
    require(provider.target["hostName"].casefold() == socket.gethostname().casefold(), "host-mismatch")
    command = [str(physical.NATIVE_EXE), "sample-current-facing-stream", "--pid",
        str(provider.target["processId"]), "--start-ticks", str(provider.target["processStartUtcTicks"]),
        "--samples", str(samples), "--interval-ms", str(interval_ms)]
    if duration_ms is not None:
        command.extend(["--duration-ms", str(duration_ms)])
    if provider.target_beacon:
        command.extend(["--include-target", "true"])
    provider.stream_command = list(command)
    provider.stream_exit_code = None
    child = popen(command, cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = queue.Queue(maxsize=32)
    stderr = bytearray()
    pump_stop = threading.Event()
    def enqueue(item):
        while not stop.is_set() and not pump_stop.is_set():
            try:
                lines.put(item, timeout=.05)
                return True
            except queue.Full:
                continue
        return False
    def stdout_pump():
        try:
            while not stop.is_set() and not pump_stop.is_set():
                line = child.stdout.readline(1024 * 1024 + 1)
                if not line:
                    enqueue(("eof", None))
                    return
                if len(line) > 1024 * 1024:
                    raise ValueError("stream-line-too-large")
                if not enqueue(("line", line)):
                    return
        except Exception as error:
            enqueue(("error", str(error)))
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
    deadline_seconds = 5 if duration_ms is None else duration_ms / 1000 + 3
    deadline = None if continuous else time.monotonic() + deadline_seconds
    sequence, receipt, previous_end = 0, None, None
    try:
        while True:
            if stop.is_set():
                return
            require(deadline is None or time.monotonic() < deadline, "stream-child-timeout")
            try:
                kind, raw = lines.get(timeout=.05)
            except queue.Empty:
                current = provider.snapshot(provider.target)
                require(_display_allowed(current) and current.get("clientRect") == before.get("clientRect"),
                        "target-foreground-or-geometry-changed")
                continue
            if kind == "error":
                raise ValueError(raw)
            if kind == "eof":
                break
            packet = json.loads(raw)
            require(receipt is None, "stream-data-after-end")
            if packet.get("recordType") == "native-current-facing-stream-end/1":
                require(not continuous and packet.get("status") in ("complete", "duration-limit")
                        and packet.get("requestedSamples") == samples
                        and packet.get("completedSamples") == sequence
                        and (packet["status"] != "complete" or sequence == samples), "invalid-stream-end")
                receipt = packet
                continue
            require((continuous or sequence < samples) and type(packet.get("sequence")) is int
                    and packet["sequence"] == sequence, "stream-sequence-invalid")
            current = provider.snapshot(provider.target)
            require(_display_allowed(current) and current.get("clientRect") == before.get("clientRect"),
                    "target-foreground-or-geometry-changed")
            acquired, completed = provider.stream_row_timing(packet, previous_end=previous_end)
            try:
                frame = provider.stream_frame_from_validated(packet, current, acquired)
            except ValueError as error:
                reason = _reason_text(error)
                if reason not in RECOVERABLE_STREAM_ROW_REASONS:
                    raise
                sequence += 1
                previous_end = completed
                provider.stream_rows += 1
                _record_failure(counts, error, row=True)
                if not stop.is_set():
                    _latest(channel, {"reason": reason, "kind": "invalid-state"})
                continue
            sequence += 1
            previous_end = completed
            provider.stream_rows += 1
            if not stop.is_set():
                _latest(channel, {"frame": frame})
                counts["acquired"] += 1
                _record_interval(counts, "Accepted", frame["acquiredMonotonic"])
        wait_timeout = 3 if deadline is None else max(.01, deadline - time.monotonic())
        provider.stream_exit_code = child.wait(timeout=wait_timeout)
        require(provider.stream_exit_code == 0, "stream-child-failed")
        require(receipt is not None, "stream-end-missing")
        provider.last_stream_receipt = receipt
    finally:
        pump_stop.set()
        _stop_child(child)
        provider.stream_exit_code = child.poll()
        for pump in pumps:
            pump.join(timeout=1)
        provider.stream_stderr = bytes(stderr).decode("utf-8", errors="replace")
        if provider.stream_stderr.strip():
            provider.stream_last_nonempty_stderr = provider.stream_stderr
        child.stdout.close()
        child.stderr.close()


def _pinned_process_ended(target, alive=None):
    """Only a confirmed ended/replaced process epoch is terminal; errors stay unknown."""
    if alive is None:
        from scripts.waypoint_connection import process_epoch_alive
        alive = process_epoch_alive
    try:
        return alive(target["processId"], target["processStartUtcTicks"]) is False
    except Exception:
        return False


def stream_feed(provider, channel, stop, counts, burst_options=None):
    burst_options = burst_options or {}
    continuous = type(burst_options.get("duration_ms")) is int and burst_options["duration_ms"] == 0
    retry_delay = 1.
    while not stop.is_set():
        counts["attempts"] += 1
        acquired_before = counts.get("acquired", 0)
        failed = False
        try:
            stream_burst(provider, channel, stop, counts, **burst_options)
        except Exception as error:
            failed = True
            reason = _record_failure(counts, error)
            recent = counts.setdefault("recentStreamFailures", [])
            exit_code = getattr(provider, "stream_exit_code", None)
            stream_stderr = getattr(provider, "stream_stderr", "")
            recent.append({"reason": reason, "exitCode": exit_code if type(exit_code) is int else None,
                           "stderr": stream_stderr[-1000:] if isinstance(stream_stderr, str) else ""})
            del recent[:-5]
            if not stop.is_set():
                if _pinned_process_ended(provider.target):
                    _latest(channel, {"terminal": True, "reason": "target-process-ended"})
                    return
                _latest(channel, {"reason": reason,
                    "kind": "transport-gap" if reason in TRANSPORT_GAP_REASONS else "invalid-state"})
        if continuous and failed:
            if counts.get("acquired", 0) > acquired_before:
                retry_delay = 1.
            stop.wait(retry_delay)
            retry_delay = min(5., retry_delay * 2)
        else:
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
                _record_interval(counts, "Accepted", frame["acquiredMonotonic"])
        except Exception as error:
            reason = _record_failure(counts, error)
            if not stop.is_set():
                if _pinned_process_ended(provider.target):
                    _latest(channel, {"terminal": True, "reason": "target-process-ended"})
                    return
                _latest(channel, {"reason": reason, "kind": "invalid-state"})
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
        presenter="native", progress_file=None, target_beacon=False, landmark_number=None, appearance_file=None,
        companion_window=None):
    require(isinstance(expected_host, str) and expected_host.casefold() == socket.gethostname().casefold(), "host-mismatch")
    require(type(physical_pid) is int and physical_pid > 0, "explicit-physical-pid-required")
    require(type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 600,
            "duration-must-be-zero-through-600")
    require(type(max_age) in (int, float) and math.isfinite(max_age) and .1 <= max_age <= 2, "max-age-must-be-0.1-through-2")
    require(reader in ("single", "stream"), "invalid-reader-mode")
    require(duration != 0 or reader == "stream", "continuous-duration-requires-stream-reader")
    require(presenter in ("native", "qt"), "invalid-presenter")
    if companion_window is not None:
        from scripts.physical_waypoint_overlay import validate_companion
        companion_window = validate_companion(companion_window)
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
    if appearance_file is not None:
        appearance_file = Path(appearance_file)
        require(appearance_file.is_absolute() and appearance_file.parent.is_dir(), "absolute-appearance-file-required")
    appearance = dict(DEFAULT_STYLE)
    next_appearance_poll = 0.
    route = load_route(route_path)
    require(landmark_number is None or (type(landmark_number) is int and landmark_number > 0
            and any(point["number"] == landmark_number for point in route["points"])), "landmark-number-not-in-route")
    selection = physical.select_physical(expected_host, physical_pid)
    require(selection.get("status") == "ready", selection.get("reason", "physical-selection-not-ready"))
    require(selection["target"]["processId"] == physical_pid, "selected-pid-mismatch")
    if expected is not None:
        target = selection["target"]
        require(str(target.get("processStartUtcTicks")) == expected["processStartUtcTicks"]
                and str(target.get("executableSha256", "")).casefold() == expected["executableSha256"]
                and target.get("hwnd") == expected["hwnd"], "expected-target-identity-mismatch")
    from scripts.physical_waypoint_overlay import PhysicalWaypointOverlay, target_snapshot
    window_options = {}
    snapshot = target_snapshot
    if companion_window is not None:
        snapshot = lambda target: target_snapshot(target, companion=companion_window)
        window_options["companion"] = companion_window
    provider = ProjectionProvider(selection, route, snapshot, max_age=max_age, target_beacon=target_beacon,
                                  landmark_number=landmark_number)
    if presenter == "qt":
        try:
            from scripts.qt_waypoint_overlay import QtOwnedWindow
        except ImportError as error:
            raise ValueError("Qt overlay unavailable; use the isolated overlay environment "
                             "with requirements-overlay.txt: " + str(error)) from error
        window_options["window_factory"] = QtOwnedWindow
    overlay = PhysicalWaypointOverlay(selection["target"], max_age=max_age, **window_options)
    stop, channel = threading.Event(), queue.Queue(maxsize=1)
    counts = {"attempts": 0, "acquired": 0, "presented": 0, "presentationAccepted": 0, "failures": 0,
        "rejectedRows": 0, "latestFailure": None, "failureReasons": {}, "hideReasons": {},
        "lastAcceptedMonotonic": None, "lastPresentedMonotonic": None,
        "lastPresentationAcceptedMonotonic": None,
        "acceptedIntervalMilliseconds": {"samples": 0, "minimum": None, "mean": None, "maximum": None},
        "presentationAcceptedIntervalMilliseconds": {"samples": 0, "minimum": None, "mean": None, "maximum": None},
        "presentedIntervalMilliseconds": {"samples": 0, "minimum": None, "mean": None, "maximum": None}}
    worker_target = stream_feed if reader == "stream" else feed
    worker_args = (provider, channel, stop, counts)
    if reader == "stream" and duration == 0:
        worker_args += ({"duration_ms": 0, "samples": 0, "interval_ms": 20},)
    elif reader == "stream" and duration > 2:
        worker_args += ({"duration_ms": min(600000, math.ceil(duration * 1000)),
                         "samples": 30000, "interval_ms": 20},)
    worker = threading.Thread(target=worker_target, args=worker_args, name="waypoint-native-reader")
    started = time.monotonic()
    reason = "duration-complete"
    latest_acquired = None
    latest_progress = None
    visible = False
    def hide(why):
        nonlocal latest_acquired, visible
        if visible:
            _record_hide(counts, why)
        visible = False
        latest_acquired = None
        overlay.hide(why)
    def cancel(why):
        nonlocal reason
        reason = why
        stop.set()
        hide(why)
        overlay.window.quit()
    def poll():
        nonlocal latest_acquired, latest_progress, visible, appearance, next_appearance_poll
        if stop.is_set():
            return
        if stop_file is not None and stop_file.exists():
            cancel("stop-requested")
            return
        if duration > 0 and time.monotonic() - started >= duration:
            cancel("duration-complete")
            return
        if appearance_file is not None:
            now = time.monotonic()
            if now >= next_appearance_poll:
                appearance = load_style(appearance_file, fallback=appearance)
                next_appearance_poll = now + .2
        try:
            packet = channel.get_nowait()
        except queue.Empty:
            packet = None
        try:
            if packet is not None:
                if packet.get("terminal") is True:
                    cancel(packet["reason"])
                    return
                if "frame" in packet:
                    age = time.monotonic() - packet["frame"]["acquiredMonotonic"]
                    if 0 <= age <= max_age:
                        packet["frame"]["appearance"] = dict(appearance)
                        if progress_file is not None:
                            latest_progress = apply_saved_progress(packet["frame"], progress_file, route)
                        if overlay.present(packet["frame"]):
                            latest_acquired = packet["frame"]["acquiredMonotonic"]
                            visible = True
                            counts["presentationAccepted"] += 1
                            counts["presented"] += 1
                            _record_interval(counts, "PresentationAccepted", time.monotonic())
                            counts["lastPresentedMonotonic"] = counts["lastPresentationAcceptedMonotonic"]
                            counts["presentedIntervalMilliseconds"] = deepcopy(
                                counts["presentationAcceptedIntervalMilliseconds"])
                        else:
                            failure = getattr(overlay, "reason", "presenter-refused-frame")
                            _record_failure(counts, ValueError(failure))
                            hide(failure)
                    else:
                        hide("queued-frame-expired")
                elif packet.get("kind") == "transport-gap":
                    pass  # A prior accepted frame remains bounded by the unchanged hard TTL.
                else:
                    hide(packet["reason"])
            if latest_acquired is not None and time.monotonic() - latest_acquired > max_age:
                hide("frame-expired")
        except Exception as error:
            failure = _record_failure(counts, error)
            hide(failure)
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
        hide(reason)
        # read_native's child has its existing bounded timeout and native lease.
        worker.join()
        overlay.close()
    overlay_hide_reasons = getattr(overlay, "hide_reasons", None)
    if isinstance(overlay_hide_reasons, dict):
        counts["hideReasons"] = dict(overlay_hide_reasons)
    result = {"status": "read-only-waypoint-feed-stopped", "reason": reason,
        "machine": socket.gethostname(), "target": selection["target"],
        "recordingIdentity": route["recordingIdentity"], "route": route["path"], "routeSha256": route["sha256"],
        "provenanceKind": route["provenanceKind"],
        "durationSeconds": time.monotonic() - started, "maxAgeSeconds": max_age,
        "counts": counts, "latestNativeReport": provider.latest_native, "inputSent": False,
        "nativeReaderMode": reader, "lastStreamReceipt": provider.last_stream_receipt,
        "presenter": presenter,
        "targetBeaconEnabled": target_beacon,
        "landmarkNumber": landmark_number,
        "streamRows": provider.stream_rows, "nativeStderr": provider.stream_stderr,
        "nativeLastNonemptyStderr": provider.stream_last_nonempty_stderr,
        "nativeStreamCommand": provider.stream_command, "nativeStreamExitCode": provider.stream_exit_code,
        "stopFile": str(stop_file) if stop_file is not None else None, "expectedTarget": expected,
        "progressFile": str(progress_file) if progress_file is not None else None,
        "appearanceFile": str(appearance_file) if appearance_file is not None else None,
        "appearance": appearance,
        "companionWindow": companion_window,
        "latestSavedProgress": latest_progress,
        "limitations": ["Native software projection candidates; smooth streaming unqualified.",
            "Presentation-accepted counts and intervals are asynchronous presenter requests, not physical display FPS.",
            "Legacy presented fields are compatibility aliases for presentation-accepted fields.",
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
    parser.add_argument("--duration", type=float, default=60,
                        help="seconds through 600; 0 streams until owned stop, target loss or close")
    parser.add_argument("--max-age", type=float, default=.8)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reader", choices=("single", "stream"), default="stream")
    parser.add_argument("--presenter", choices=("native", "qt"), default="native")
    parser.add_argument("--appearance-file", type=Path,
                        help="live beacon display preferences saved by Waypoints")
    parser.add_argument("--companion-window", type=json.loads,
                        help="exact owning Waypoints window binding for live appearance preview")
    parser.add_argument("--expect-start-ticks")
    parser.add_argument("--expect-sha256")
    parser.add_argument("--expect-hwnd", type=_hwnd_argument)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--progress-file", type=Path, help="optional absolute saved checkpoint; display only")
    parser.add_argument("--target-beacon", action="store_true", help="show fresh selected-target candidate")
    parser.add_argument("--landmark-number", type=int, help="guide to one saved point (1-based; display only)")
    args = parser.parse_args(argv)
    try:
        result = run(args.expected_host, args.physical_pid, args.route, duration=args.duration,
                     max_age=args.max_age, output=args.output, reader=args.reader,
                     expected_start_ticks=args.expect_start_ticks, expected_sha256=args.expect_sha256,
                     expected_hwnd=args.expect_hwnd, stop_file=args.stop_file, presenter=args.presenter,
                     progress_file=args.progress_file, target_beacon=args.target_beacon, landmark_number=args.landmark_number,
                     appearance_file=args.appearance_file, companion_window=args.companion_window)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        result = {"status": "blocked", "reason": str(error), "machine": socket.gethostname(), "inputSent": False}
        if args.output is not None and not args.output.exists() and args.output.parent.is_dir():
            write_json_atomic(args.output, result)
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
