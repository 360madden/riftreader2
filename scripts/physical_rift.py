"""Select a real, locally running RIFT process; never discover VMware guests."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
import re
from pathlib import Path
import socket
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical, summarize_native_vitals_burst

SUPPORTED_HOSTS = ("AMD-DESKTOP", "LEGION")
NATIVE_READS = {
    "position": "sample-current-position",
    "vitals": "sample-current-vitals",
    "orientation": "sample-current-orientation",
    "facing": "sample-current-facing",
    "unit-positions": "sample-current-unit-positions",
    "smoothed-scalar": "sample-current-smoothed-scalar",
    "actor-pose": "sample-current-actor-pose",
    "player-context": "sample-current-player-context",
    "selected-target": "sample-current-selected-target",
    "stats": "sample-current-stats",
}
NATIVE_RECEIPTS = {
    "position": "native-current-position-candidate-summary/1",
    "vitals": "native-current-vitals-candidate-summary/2",
    "orientation": "native-current-orientation-summary/1",
    "facing": "native-current-facing-summary/1",
    "unit-positions": "native-current-unit-positions-summary/1",
    "smoothed-scalar": "native-current-smoothed-scalar-summary/1",
    "actor-pose": "native-current-actor-pose-summary/1",
    "player-context": "native-current-player-context-candidate-summary/1",
    "selected-target": "native-current-selected-target-candidate-summary/1",
    "stats": "native-current-stats-summary/1",
}
NATIVE_EXE = (ROOT / "src" / "RiftReader2.Live" / "bin" / "Debug" /
              "net10.0-windows" / "win-x64" / "RiftReader2.Live.exe")


def select_physical(expected_host=None, physical_pid=None):
    """Return a fail-closed, PID/start/SHA-pinned physical process selection."""
    actual = socket.gethostname()
    target_id = "physical-" + actual.lower()
    try:
        if actual.upper() not in SUPPORTED_HOSTS:
            raise ValueError("unsupported-host")
        if expected_host is not None:
            if not isinstance(expected_host, str) or expected_host.upper() not in SUPPORTED_HOSTS:
                raise ValueError("invalid-expected-host")
            if actual.casefold() != expected_host.casefold():
                raise ValueError("host-mismatch")
        if physical_pid is not None and (type(physical_pid) is not int or not 1 <= physical_pid <= 4294967295):
            raise ValueError("invalid-physical-pid")
        # Selection needs a verified process, not an interactive game window.
        identity = observe_physical._identity(physical_pid, require_window=False)
        if identity.get("hostName", "").casefold() != actual.casefold():
            raise ValueError("identity-host-mismatch")
        if physical_pid is not None and identity.get("processId") != physical_pid:
            raise ValueError("physical-pid-mismatch")
        return {"status": "ready", "workflow": "physical", "targetId": target_id,
                "ownerHost": actual, "target": identity}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {"status": "blocked", "workflow": "physical", "targetId": target_id,
                "ownerHost": actual, "reason": str(exc)}


def _candidate_angle_steps(angles):
    """Shortest adjacent signed steps; an unavailable or 180-degree step is ambiguous."""
    if len(angles) < 2 or any(value is None for value in angles):
        return None
    steps = [((later - earlier + 180) % 360) - 180
             for earlier, later in zip(angles, angles[1:])]
    return None if any(abs(step) == 180 for step in steps) else steps


def _utc_tick_order_key(value):
    """Retain .NET's seventh fractional second digit instead of truncating to µs."""
    if not isinstance(value, str):
        raise ValueError("invalid-utc-tick-time")
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(Z|\+00:00)",
        value)
    if match is None:
        raise ValueError("invalid-utc-tick-time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("invalid-utc-tick-time")
    # Python datetime stores microseconds; .NET serializes 100 ns ticks.
    remainder = int((match.group(2) or "").ljust(7, "0")[-1])
    return parsed, remainder


def _optical_projection_values(camera, transform):
    """Optional current-camera projection, decoded from its preserved float32 bits."""
    names = (("projectionRowMajor", 16), ("viewportLeftRightTopBottom", 4))
    if all(camera.get(name) is None for name in ("projectionRawBits", *(name for name, _ in names))):
        return None
    bits = camera.get("projectionRawBits")
    if (not isinstance(bits, list) or len(bits) != 20
            or any(type(bit) is not int or not 0 <= bit < 2**32 for bit in bits)
            or any(not isinstance(camera.get(name), list) or len(camera[name]) != count
                   for name, count in names)):
        raise ValueError("invalid-native-optical-projection")
    values = [value for name, _ in names for value in camera[name]]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("invalid-native-optical-projection")
    try:
        encoded = [struct.unpack("<I", struct.pack("<f", value))[0] for value in values]
    except (OverflowError, struct.error) as error:
        raise ValueError("invalid-native-optical-projection") from error
    if any(a != b and {a, b} != {0, 0x80000000} for a, b in zip(encoded, bits)):
        raise ValueError("invalid-native-optical-projection-bits")
    raw = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]
    left, right, top, bottom = raw[16:]
    if (not 0 <= left < right <= 1 or not 0 <= bottom < top <= 1
            or any(abs(raw[12 + i] - transform[i * 3]) > .001 for i in range(3))
            or abs(raw[15] + sum(transform[i * 3] * transform[9 + i] for i in range(3))) > .001):
        raise ValueError("invalid-native-optical-projection-geometry")
    return raw[:16], raw[16:]


def _optical_camera_values(camera):
    if camera is None:
        return None
    if (not isinstance(camera, dict) or camera.get("cameraYawQualified") is not False
            or camera.get("sourceRootRva") != "0x3362848"
            or camera.get("selectedModeCameraGetterRva") != "0xF88580"):
        raise ValueError("invalid-native-optical-camera-source")
    if camera.get("status") == "unavailable":
        if (not isinstance(camera.get("unavailableReason"), str) or not camera["unavailableReason"]
                or any(camera.get(field) is not None for field in
                       ("rawBits", "bearingDegreesCandidate", "pitchDegreesCandidate", "worldEyeXYZ"))):
            raise ValueError("invalid-native-optical-camera-unavailable")
        return {"status": "unavailable", "reason": camera["unavailableReason"]}
    fields = (("rotationRowMajor", 9), ("rendererEyeXYZ", 3), ("renderOriginXYZ", 3))
    if (camera.get("status") != "available-candidate"
            or any(not isinstance(camera.get(name), list) or len(camera[name]) != count
                   for name, count in fields)):
        raise ValueError("invalid-native-optical-camera-transform")
    values = [value for name, _ in fields for value in camera[name]]
    bits = camera.get("rawBits")
    if (not isinstance(bits, list) or len(bits) != 15
            or any(type(bit) is not int or not 0 <= bit < 2**32 for bit in bits)
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
        raise ValueError("invalid-native-optical-camera-values")
    try:
        encoded = [struct.unpack("<I", struct.pack("<f", value))[0] for value in values]
    except (OverflowError, struct.error) as error:
        raise ValueError("invalid-native-optical-camera-values") from error
    if any(a != b and not (a in (0, 0x80000000) and b in (0, 0x80000000))
           for a, b in zip(encoded, bits)):
        raise ValueError("invalid-native-optical-camera-bits")
    raw = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]
    for row in range(3):
        for other in range(3):
            dot = sum(raw[row * 3 + col] * raw[other * 3 + col] for col in range(3))
            if abs(dot - (1 if row == other else 0)) > .001:
                raise ValueError("invalid-native-optical-camera-rotation")
    horizontal = math.hypot(raw[0], raw[6])
    expected_yaw = math.degrees(math.atan2(raw[0], raw[6])) if horizontal >= 1e-8 else None
    for field, expected in (("bearingDegreesCandidate", expected_yaw),
                            ("pitchDegreesCandidate", math.degrees(math.atan2(raw[3], horizontal)))):
        actual = camera.get(field)
        if ((expected is None and actual is not None)
                or (expected is not None and
                    (type(actual) not in (int, float) or not math.isfinite(actual)
                     or abs(actual - expected) > .00001))):
            raise ValueError("invalid-native-optical-camera-angle")
    eye = camera.get("worldEyeXYZ")
    if (not isinstance(eye, list) or len(eye) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   or abs(value - raw[9 + index] - raw[12 + index]) > .00001
                   for index, value in enumerate(eye))):
        raise ValueError("invalid-native-optical-camera-world-eye")
    projection = _optical_projection_values(camera, raw)
    return {"status": "available-candidate", "bearingDegreesCandidate": camera["bearingDegreesCandidate"],
            "pitchDegreesCandidate": camera["pitchDegreesCandidate"], "worldEyeXYZ": eye,
            "projectionAvailableCandidate": projection is not None,
            "cameraYawQualified": False}


def _project_world_point(camera, xyz):
    """Top-left normalized client coordinates. This cannot establish occlusion."""
    optical = _optical_camera_values(camera)
    if optical is None or optical["status"] != "available-candidate":
        return {"status": "unavailable", "reason": "optical-camera-unavailable"}
    transform = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in camera["rawBits"]]
    projection = _optical_projection_values(camera, transform)
    if projection is None:
        return {"status": "unavailable", "reason": "projection-not-recorded"}
    if (not isinstance(xyz, dict) or any(type(xyz.get(axis)) not in (int, float)
                                       or not math.isfinite(xyz[axis]) for axis in ("x", "y", "z"))):
        raise ValueError("invalid-projection-world-point")
    matrix, viewport = projection
    point = [xyz[axis] - transform[12 + i] for i, axis in enumerate(("x", "y", "z"))] + [1]
    clip_w = sum(matrix[12 + i] * point[i] for i in range(4))
    if not math.isfinite(clip_w):
        raise ValueError("nonfinite-projection-result")
    if clip_w <= 1e-5:
        return {"status": "nonpositive-or-small-clip-w", "clipW": clip_w}
    ndc_x, ndc_y = (sum(matrix[row * 4 + i] * point[i] for i in range(4)) / clip_w
                    for row in (0, 1))
    left, right, top, bottom = viewport
    x = left + (right - left) * (ndc_x + 1) / 2
    y = 1 - (bottom + (top - bottom) * (ndc_y + 1) / 2)
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("nonfinite-projection-result")
    return {"status": "available-candidate", "normalizedX": x, "normalizedY": y,
            "clipW": clip_w, "insideViewportCandidate": left <= x <= right and 1 - top <= y <= 1 - bottom,
            "coordinateConvention": "top-left-normalized-client"}


def _target_relative_arithmetic(player_xyz, target_xyz, primary, body):
    """Native-coordinate arithmetic only; no world identity or control authority."""
    delta = {axis: target_xyz[axis] - player_xyz[axis] for axis in ("x", "y", "z")}
    horizontal = math.hypot(delta["x"], delta["z"])
    bearing = math.degrees(math.atan2(delta["x"], delta["z"])) if horizontal else None
    def angle_from(heading):
        steps = _candidate_angle_steps([heading, bearing])
        return steps[0] if steps is not None else None
    return {"deltaXYZCandidate": delta, "horizontalDistanceCandidate": horizontal,
            "distance3DCandidate": math.hypot(*delta.values()),
            "worldBearingDegreesCandidate": bearing,
            "primarySignedAngleToTargetDegreesCandidate": angle_from(primary),
            "bodySignedAngleToTargetDegreesCandidate": angle_from(body),
            "bearingConvention": "degrees-from-positive-z-toward-positive-x",
            "distanceUnit": "native-coordinate-units", "worldIdentityStatus": "unavailable",
            "headingQualified": False, "movementEligible": False}


def _xyz_from_raw_bits(point, bits, reason):
    if (not isinstance(point, dict) or not isinstance(bits, list) or len(bits) != 3
            or any(type(bit) is not int or not 0 <= bit < 2**32 for bit in bits)
            or any(type(point.get(axis)) not in (int, float) or not math.isfinite(point[axis]) for axis in ("x", "y", "z"))):
        raise ValueError(reason)
    try:
        encoded = [struct.unpack("<I", struct.pack("<f", point[axis]))[0] for axis in ("x", "y", "z")]
    except (OverflowError, struct.error) as error:
        raise ValueError(reason) from error
    if any(a != b and {a, b} != {0, 0x80000000} for a, b in zip(encoded, bits)):
        raise ValueError(reason + "-bits")
    return dict(zip(("x", "y", "z"), (struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits)))


def _facing_entity_position(row):
    point, bits = row.get("entityPositionCandidate"), row.get("entityPositionRawBits")
    if point is None and bits is None:
        return None
    return _xyz_from_raw_bits(point, bits, "invalid-native-facing-entity-position")


def _same_optical_projection_snapshot(camera, after_camera):
    before = _optical_camera_values(camera)
    after = _optical_camera_values(after_camera)
    address = camera.get("cameraAddressDecimal") if isinstance(camera, dict) else None
    return bool(before and after and before["status"] == after["status"] == "available-candidate"
                and before["projectionAvailableCandidate"] and after["projectionAvailableCandidate"]
                and isinstance(address, str) and address.isdecimal() and 0 < int(address) < 2**64
                and str(int(address)) == address and address == after_camera.get("cameraAddressDecimal")
                and camera["rawBits"] == after_camera["rawBits"]
                and camera["projectionRawBits"] == after_camera["projectionRawBits"])


def _target_screen_point(row):
    pair = row.get("targetPositionPairCandidate")
    after_camera = row.get("opticalCameraAfterTargetCandidate")
    stable = row.get("targetProjectionCameraStableCandidate")
    if pair is None and after_camera is None and stable is None:
        return None
    if (not isinstance(pair, dict) or pair.get("identity") != row["identity"]
            or pair.get("self", {}).get("unitKey") != row["playerKeyDecimal"]
            or pair["self"].get("position") != (row.get("entityPositionCandidate") or row["positionCandidate"])
            or pair.get("beforeGuardStatus") != pair.get("afterGuardStatus")
            or not isinstance(pair.get("targetStatus"), str) or type(stable) is not bool):
        raise ValueError("invalid-native-facing-target-owner")
    start, end = (_utc_tick_order_key(pair.get(field)) for field in ("startedAtUtc", "completedAtUtc"))
    span = pair.get("acquisitionSpanMilliseconds")
    if (not _utc_tick_order_key(row["startedAtUtc"]) <= start < end <= _utc_tick_order_key(row["completedAtUtc"])
            or type(span) not in (int, float) or not math.isfinite(span) or not 0 <= span <= 1000):
        raise ValueError("invalid-native-facing-target-interval")
    camera = row.get("opticalCameraCandidate")
    expected_stable = _same_optical_projection_snapshot(camera, after_camera)
    if stable != expected_stable:
        raise ValueError("invalid-native-facing-target-camera-bracket")
    target = pair.get("target")
    if target is None or target.get("status") != "candidate":
        return {"status": "unavailable", "reason": "target-position-unavailable",
                "targetStatus": pair["targetStatus"]}
    key, xyz = target.get("unitKey"), target.get("position")
    if (not isinstance(key, str) or not key.isdecimal() or not 0 < int(key) < 2**64 or str(int(key)) != key
            or target.get("unitIdCandidate") != f"u{int(key):016X}" or not isinstance(xyz, dict)
            or any(type(xyz.get(axis)) not in (int, float) or not math.isfinite(xyz[axis]) for axis in ("x", "y", "z"))
            or not start <= _utc_tick_order_key(target.get("startedAtUtc")) <=
                      _utc_tick_order_key(target.get("completedAtUtc")) <= end):
        raise ValueError("invalid-native-facing-target-position")
    # Recover the float32 coordinates serialized by the native position reader.
    exact = {axis: struct.unpack("<f", struct.pack("<f", xyz[axis]))[0] for axis in ("x", "y", "z")}
    player_xyz = _facing_entity_position(row) or dict(zip(("x", "y", "z"), (
        struct.unpack("<f", struct.pack("<I", bit))[0] for bit in row["rawBits"][4:])))
    screen = (_project_world_point(camera, exact) if stable else
              {"status": "unavailable", "reason": "camera-not-stable-across-target-read"})
    return {"status": "candidate", "targetKey": key, "targetUnitIdCandidate": target["unitIdCandidate"],
            "positionXYZCandidate": exact, "screenPointCandidate": screen,
            "relativeToPlayerCandidate": _target_relative_arithmetic(
                player_xyz, exact, row.get("primaryBearingDegreesCandidate"), row.get("bodyBearingDegreesCandidate")),
            "sampledAtUtc": target["completedAtUtc"], "acquisitionSpanMilliseconds": span,
            "cameraStableCandidate": stable, "guardStatus": pair["afterGuardStatus"]}


def _native_values(kind, report, *, expect_position=False, expect_translation_sources=False):
    """Project immediate useful values; preserve exact large unit keys as text."""
    if kind == "unit-positions":
        observation = report.get("observation")
        if (report.get("schemaVersion") != 1 or report.get("status") != "complete"
                or report.get("contractVersion") != "native-current-unit-positions-candidate-sample/1"
                or not isinstance(observation, dict) or not isinstance(observation.get("identity"), dict)):
            raise ValueError("invalid-native-unit-positions-report")
        key = observation.get("selfKey")
        if not isinstance(key, str) or not key.isdecimal() or not 0 < int(key) < 2**64 or str(int(key)) != key:
            raise ValueError("invalid-native-unit-positions-self")
        self_xyz = _xyz_from_raw_bits(observation.get("selfPositionCandidate"), observation.get("selfPositionRawBits"),
                                     "invalid-native-unit-positions-self")
        limit, examined, absent, unavailable, chains, visited, start, buckets, byte_count = (
            observation.get(name) for name in ("unitLimit", "examined", "noPosition", "unavailable",
                                               "unavailableChains", "bucketsExamined", "startBucket", "bucketCount", "readBytes"))
        rows = observation.get("rows")
        limited = observation.get("unitLimitReached")
        if (any(type(n) is not int for n in (limit, examined, absent, unavailable, chains, visited, start, buckets, byte_count))
                or not 1 <= limit <= 512 or not 0 <= examined <= limit or not 1 <= buckets <= 4096
                or not 0 <= start < buckets or not 1 <= visited <= buckets or not 0 <= chains <= visited
                or min(absent, unavailable) < 0 or not 0 < byte_count <= 2 * 1024 * 1024
                or type(limited) is not bool or (limited and examined != limit)
                or (not limited and visited != buckets) or not isinstance(rows, list)
                or len(rows) + absent + unavailable != examined
                or observation.get("worldIdentityStatus") != "unavailable"):
            raise ValueError("invalid-native-unit-positions-coverage")
        begin = _utc_tick_order_key(observation.get("startedAtUtc"))
        end = _utc_tick_order_key(observation.get("completedAtUtc"))
        if begin >= end:
            raise ValueError("invalid-native-unit-positions-time")
        camera = observation.get("opticalCameraCandidate")
        stable = observation.get("cameraStableCandidate")
        if type(stable) is not bool or stable != _same_optical_projection_snapshot(
                camera, observation.get("opticalCameraAfterCandidate")):
            raise ValueError("invalid-native-unit-positions-camera")
        units, keys, previous = [], set(), begin
        for row in rows:
            unit_key = row.get("unitKey")
            address = row.get("entityAddressDecimal")
            if (not isinstance(unit_key, str) or not unit_key.isdecimal() or not 0 < int(unit_key) < 2**64
                    or str(int(unit_key)) != unit_key or unit_key in keys
                    or row.get("unitIdCandidate") != f"u{int(unit_key):016X}"
                    or not isinstance(address, str) or not address.isdecimal()
                    or not 0x10000 <= int(address) <= 0x7FFFFFFFFFFF - 0x110 or int(address) % 8):
                raise ValueError("invalid-native-unit-position-owner")
            keys.add(unit_key)
            start_time, end_time = (_utc_tick_order_key(row.get(name)) for name in ("startedAtUtc", "completedAtUtc"))
            if not previous <= start_time <= end_time <= end:
                raise ValueError("invalid-native-unit-position-time")
            previous = end_time
            xyz = _xyz_from_raw_bits(row.get("positionCandidate"), row.get("rawBits"), "invalid-native-unit-position")
            distance = math.hypot(xyz["x"] - self_xyz["x"], xyz["z"] - self_xyz["z"])
            actual = row.get("horizontalDistanceCandidate")
            if type(actual) not in (int, float) or not math.isfinite(actual) or abs(actual - distance) > 1e-6:
                raise ValueError("invalid-native-unit-position-distance")
            units.append({"unitKey": unit_key, "unitIdCandidate": row["unitIdCandidate"],
                          "positionXYZCandidate": xyz, "horizontalDistanceCandidate": distance,
                          "screenPointCandidate": _project_world_point(camera, xyz) if stable else
                          {"status": "unavailable", "reason": "camera-not-stable-across-unit-scan"},
                          "sampledAtUtc": row["completedAtUtc"]})
        return {"selfKey": key, "selfPositionXYZCandidate": self_xyz,
                "unitsExamined": examined, "positionsFound": len(units), "unitsWithoutPosition": absent,
                "unavailableUnits": unavailable, "unavailableChains": chains, "bucketsExamined": visited,
                "bucketCount": buckets, "startBucket": start, "unitLimitReached": limited,
                "cameraStableCandidate": stable, "opticalCamera": _optical_camera_values(camera),
                "units": sorted(units, key=lambda row: (row["horizontalDistanceCandidate"], row["unitKey"])),
                "sampledAtUtc": observation["completedAtUtc"], "worldIdentityStatus": "unavailable",
                "worldCoverage": "bounded-unit-manager-subset"}
    if kind == "facing":
        rows = report.get("observations")
        if (report.get("schemaVersion") != 1 or report.get("status") != "complete"
                or report.get("contractVersion") != "native-current-facing-candidate-samples/1"
                or not isinstance(rows, list) or not 1 <= len(rows) <= 30
                or report.get("requestedSamples") != len(rows)
                or report.get("completedSamples") != len(rows)
                or report.get("observation") != rows[-1]):
            raise ValueError("invalid-native-facing-report")
        owner = None
        previous_end = None
        bearings = []
        primary_bearings = []
        system_bearings = []
        aim_bearings = []
        for row in rows:
            if (not isinstance(row, dict) or row.get("identity") != report.get("identity")
                    or row.get("headingQualified") is not False
                    or row.get("cameraYawQualified") is not False
                    or row.get("bearingConvention") != "degrees-from-positive-z-toward-positive-x"):
                raise ValueError("invalid-native-facing-identity")
            current_owner = tuple(row.get(field) for field in
                                  ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal"))
            if (any(not isinstance(value, str) or not value.isdecimal()
                    or not 0 < int(value) < 2**64 or str(int(value)) != value
                    for value in current_owner)
                    or (owner is not None and current_owner != owner)):
                raise ValueError("invalid-native-facing-owner")
            owner = current_owner
            started = _utc_tick_order_key(row.get("startedAtUtc"))
            completed = _utc_tick_order_key(row.get("completedAtUtc"))
            if started >= completed or (previous_end is not None and started <= previous_end):
                raise ValueError("invalid-native-facing-time")
            previous_end = completed
            xyz, aim = row.get("positionCandidate"), row.get("cameraAimPointCandidate")
            if not isinstance(xyz, dict) or not isinstance(aim, dict):
                raise ValueError("invalid-native-facing-coordinates")
            values = [row.get("playerSystemYawRadiansCandidate")] + [point.get(axis)
                      for point in (aim, xyz) for axis in ("x", "y", "z")]
            bits = row.get("rawBits")
            if (not isinstance(bits, list) or len(bits) != 7
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for value in values)
                    or any(type(bit) is not int or not 0 <= bit < 2**32 for bit in bits)):
                raise ValueError("invalid-native-facing-values")
            for bit, value in zip(bits, values):
                try:
                    actual = struct.unpack("<I", struct.pack("<f", value))[0]
                except (OverflowError, struct.error) as error:
                    raise ValueError("invalid-native-facing-values") from error
                if bit != actual and not (bit in (0, 0x80000000) and actual in (0, 0x80000000)):
                    raise ValueError("invalid-native-facing-bits")
            raw_values = [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]
            expected_system = (math.degrees(raw_values[0]) + 180) % 360 - 180
            system_bearing = row.get("playerSystemBearingDegreesCandidate")
            if (type(system_bearing) not in (float, int) or not math.isfinite(system_bearing)
                    or not -180 <= system_bearing < 180 or abs(system_bearing - expected_system) > .00001):
                raise ValueError("invalid-native-facing-bearing")
            orientation = row.get("positionOrientationCandidate")
            if (not isinstance(orientation, dict) or orientation.get("identity") != row["identity"]
                    or orientation.get("unitKey") != current_owner[0]):
                raise ValueError("invalid-native-facing-orientation-owner")
            source = _native_values("orientation", {"observation": orientation})
            primary_matrix = orientation["primary"]["rowMajorF32"]
            expected_primary = ((math.degrees(math.atan2(primary_matrix[2], primary_matrix[8]))
                                 + 180) % 360 - 180
                                if source["primaryPlanarDegreesCandidate"] is not None else None)
            primary = row.get("primaryBearingDegreesCandidate")
            if ((expected_primary is None and primary is not None)
                    or (expected_primary is not None and
                        (type(primary) not in (float, int) or not math.isfinite(primary)
                         or abs(primary - expected_primary) > .00001))):
                raise ValueError("invalid-native-facing-primary-bearing")
            expected_primary_delta = ((system_bearing - primary + 180) % 360 - 180
                                      if primary is not None else None)
            primary_delta = row.get("playerSystemMinusPrimaryDegreesCandidate")
            if ((expected_primary_delta is None and primary_delta is not None)
                    or (expected_primary_delta is not None and
                        (type(primary_delta) not in (float, int) or not math.isfinite(primary_delta)
                         or abs(primary_delta - expected_primary_delta) > .00001))):
                raise ValueError("invalid-native-facing-primary-source-delta")
            secondary = source["secondaryPlanarDegreesCandidate"]
            expected_body = (-secondary + 180) % 360 - 180 if secondary is not None else None
            body = row.get("bodyBearingDegreesCandidate")
            if ((expected_body is None and body is not None)
                    or (expected_body is not None and
                        (type(body) not in (float, int) or not math.isfinite(body)
                         or abs(body - expected_body) > .00001))):
                raise ValueError("invalid-native-facing-body-bearing")
            expected_delta = (system_bearing - body + 180) % 360 - 180 if body is not None else None
            delta = row.get("playerSystemMinusBodyDegreesCandidate")
            if ((expected_delta is None and delta is not None)
                    or (expected_delta is not None and
                        (type(delta) not in (float, int) or not math.isfinite(delta)
                         or abs(delta - expected_delta) > .00001))):
                raise ValueError("invalid-native-facing-source-delta")
            dx, dz = raw_values[1] - raw_values[4], raw_values[3] - raw_values[6]
            camera = row.get("cameraAimBearingDegreesCandidate")
            expected_camera = math.degrees(math.atan2(dx, dz)) if dx or dz else None
            if ((expected_camera is None and camera is not None)
                    or (expected_camera is not None and
                        (type(camera) not in (float, int) or not math.isfinite(camera)
                         or abs(camera - expected_camera) > .00001))):
                raise ValueError("invalid-native-facing-camera-bearing")
            bearings.append(body)
            primary_bearings.append(primary)
            system_bearings.append(system_bearing)
            aim_bearings.append(camera)
            optical = _optical_camera_values(row.get("opticalCameraCandidate"))
            entity_xyz = _facing_entity_position(row)
            current_xyz = entity_xyz or dict(zip(("x", "y", "z"), raw_values[4:]))
            player_screen = _project_world_point(row.get("opticalCameraCandidate"),
                                                current_xyz)
            target_screen = _target_screen_point(row)
        return {
            "playerKey": owner[0], "playerSystemYawRadiansCandidate": values[0],
            "playerSystemBearingDegreesCandidate": system_bearings[-1],
            "bodyBearingDegreesCandidate": bearings[-1],
            "primaryBearingDegreesCandidate": primary_bearings[-1],
            "primaryBearingSeriesDegreesCandidate": primary_bearings,
            "playerSystemMinusPrimaryDegreesCandidate": primary_delta,
            "playerSystemMinusBodyDegreesCandidate": delta,
            "cameraAimBearingDegreesCandidate": aim_bearings[-1],
            "opticalCamera": optical,
            "playerScreenPointCandidate": player_screen,
            "selectedTargetProjectionCandidate": target_screen,
            "positionXYZCandidate": current_xyz,
            "positionSource": "entity-owned-position-component+0x48" if entity_xyz else "legacy-player-system-snapshot+0x320",
            "playerSystemPositionXYZCandidate": dict(zip(("x", "y", "z"), raw_values[4:])),
            "bearingConvention": rows[-1]["bearingConvention"],
            "bodyBearingSeriesDegreesCandidate": bearings,
            "playerSystemBearingSeriesDegreesCandidate": system_bearings,
            "cameraAimBearingSeriesDegreesCandidate": aim_bearings,
            "sampleCount": len(rows), "sampledAtUtc": rows[-1]["completedAtUtc"],
            "headingQualified": False, "cameraYawQualified": False,
        }
    if kind == "orientation":
        observation = report.get("observation")
        if not isinstance(observation, dict):
            raise ValueError("invalid-native-orientation")
        key = observation.get("unitKey")
        if (not isinstance(key, str) or not key.isdecimal() or
                not 0 < int(key) < 2**64 or str(int(key)) != key):
            raise ValueError("invalid-native-orientation-owner")
        refresh_handle = observation.get("refreshHandleRaw")
        refresh_flag = observation.get("refreshFlagRaw")
        if (not isinstance(refresh_handle, str) or len(refresh_handle) != 18 or
                not refresh_handle.startswith("0x") or
                any(c not in "0123456789abcdefABCDEF" for c in refresh_handle[2:]) or
                type(refresh_flag) is not int or not 0 <= refresh_flag <= 255):
            raise ValueError("invalid-native-orientation-refresh")
        matrices = {}
        angles = {}
        states = {}
        for name, offset in (("primary", 0x60), ("secondary", 0x94)):
            matrix = observation.get(name)
            if (not isinstance(matrix, dict) or matrix.get("sourceOffset") != offset or
                    not isinstance(matrix.get("status"), str)):
                raise ValueError("invalid-native-orientation-matrix")
            bits, values = matrix.get("rawBits"), matrix.get("rowMajorF32")
            if (not isinstance(bits, list) or len(bits) != 9 or
                    not isinstance(values, list) or len(values) != 9 or
                    any(type(bit) is not int or not 0 <= bit <= 0xFFFFFFFF
                        for bit in bits)):
                raise ValueError("invalid-native-orientation-matrix")
            for bit, value in zip(bits, values):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("invalid-native-orientation-matrix")
                try:
                    actual = struct.unpack("<I", struct.pack("<f", value))[0]
                except (ValueError, OverflowError, struct.error) as exc:
                    raise ValueError("invalid-native-orientation-matrix") from exc
                # JSON may serialize -0.0 as integer 0, losing its sign.
                if actual != bit and not (actual in (0, 0x80000000) and bit in (0, 0x80000000)):
                    raise ValueError("invalid-native-orientation-matrix-bits")
            angle = matrix.get("planarAngleDegreesCandidate")
            structural = matrix["status"] == "structural-y-planar-matrix-candidate"
            if (structural and
                    (type(angle) not in (int, float) or not math.isfinite(angle) or
                     not -180 <= angle <= 180)):
                raise ValueError("invalid-native-orientation-angle")
            if structural:
                derived = math.degrees(math.atan2(values[6], values[0]))
                signed_error = ((angle - derived + 180) % 360) - 180
                if abs(signed_error) > 0.001:
                    raise ValueError("invalid-native-orientation-angle")
            elif angle is not None:
                raise ValueError("invalid-native-orientation-angle")
            matrices[name], angles[name], states[name] = values, angle, matrix["status"]
        angular_difference = _candidate_angle_steps([angles["secondary"], angles["primary"]])
        result = {"unitKey": key, "headingQualified": False,
                  "refreshHandleRaw": refresh_handle, "refreshFlagRaw": refresh_flag,
                  "primaryPlanarDegreesCandidate": angles["primary"],
                  "secondaryPlanarDegreesCandidate": angles["secondary"],
                  "primaryMinusSecondaryDegreesCandidate": (
                      angular_difference[0] if angular_difference is not None else None),
                  "primaryMatrixStatus": states["primary"],
                  "secondaryMatrixStatus": states["secondary"],
                  "primarySecondaryMaxAbsElementDeltaCandidate": max(
                      abs(a - b) for a, b in zip(matrices["primary"], matrices["secondary"])),
                  "sampledAtUtc": observation.get("completedAtUtc")}
        observations = report.get("observations")
        if observations is not None:
            if (not isinstance(observations, list) or len(observations) < 2 or
                    type(report.get("requestedSamples")) is not int or
                    report["requestedSamples"] != len(observations) or
                    type(report.get("completedSamples")) is not int or
                    report["completedSamples"] != len(observations) or
                    observations[-1] != observation or
                    any(not isinstance(row, dict) or row.get("identity") != report.get("identity")
                        or row.get("unitKey") != key or
                        row.get("componentAddress") != observation.get("componentAddress")
                        for row in observations)):
                raise ValueError("invalid-native-orientation-burst")
            # Travel depends on acquisition order. A replayed, overlapping, or
            # reordered capture can otherwise manufacture an apparent turn.
            last_completed = None
            for row in observations:
                try:
                    started_raw, completed_raw = row["startedAtUtc"], row["completedAtUtc"]
                    started = _utc_tick_order_key(started_raw)
                    completed = _utc_tick_order_key(completed_raw)
                    if (not started < completed or
                            (last_completed is not None and started <= last_completed)):
                        raise ValueError("overlap-or-not-utc")
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    raise ValueError("invalid-native-orientation-burst-time") from exc
                last_completed = completed
            series = [_native_values("orientation", {"observation": row})
                      for row in observations]
            angles_by_source = {
                name: [row[name + "PlanarDegreesCandidate"] for row in series]
                for name in ("primary", "secondary")
            }
            result["sampleCount"] = len(series)
            result["orientationSeriesDegreesCandidate"] = angles_by_source
            result["orientationSignedTravelDegreesCandidate"] = {
                name: sum(steps) if steps is not None else None
                for name, values in angles_by_source.items()
                for steps in [_candidate_angle_steps(values)]
            }
            result["primarySecondaryMaxAbsElementDeltaSeriesCandidate"] = [
                row["primarySecondaryMaxAbsElementDeltaCandidate"] for row in series
            ]
            differences = [row["primaryMinusSecondaryDegreesCandidate"] for row in series]
            result["primaryMinusSecondaryDegreesSeriesCandidate"] = differences
            result["primarySecondaryMaxAbsAngleDeltaDegreesCandidate"] = (
                max(abs(value) for value in differences) if None not in differences else None)
            result["refreshFlagSeriesRaw"] = [row["refreshFlagRaw"] for row in series]
            result["refreshHandleSeriesRaw"] = [row["refreshHandleRaw"] for row in series]
        return result
    if kind == "smoothed-scalar":
        observation = report.get("observation")
        if not isinstance(observation, dict) or observation.get("headingQualified") is not False:
            raise ValueError("invalid-native-smoothed-scalar")
        key = observation.get("playerKeyDecimal")
        if not isinstance(key, str) or not key.isdecimal() or not 0 < int(key) < 2**64:
            raise ValueError("invalid-native-smoothed-scalar")
        raw_bits = observation.get("rawBits")
        if (not isinstance(raw_bits, list) or len(raw_bits) != 4 or
                any(type(bit) is not int or not 0 <= bit <= 0xFFFFFFFF for bit in raw_bits)):
            raise ValueError("invalid-native-smoothed-scalar")
        values = {"playerKey": key, "headingQualified": False,
                  "sampledAtUtc": observation.get("completedAtUtc")}
        for name, bits in zip(("currentCandidate", "sourceCandidate", "targetCandidate",
                               "factorCandidate"), raw_bits):
            value = observation.get(name)
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("invalid-native-smoothed-scalar")
            try:
                actual = struct.unpack("<I", struct.pack("<f", value))[0]
            except (ValueError, OverflowError, struct.error) as exc:
                raise ValueError("invalid-native-smoothed-scalar") from exc
            if actual != bits:
                raise ValueError("invalid-native-smoothed-scalar-raw-bits")
            values[name] = value
        observations = report.get("observations")
        if observations is not None:
            if (not isinstance(observations, list) or len(observations) < 2 or
                    report.get("requestedSamples") != len(observations) or
                    report.get("completedSamples") != len(observations) or
                    observations[-1] != observation or
                    any(not isinstance(row, dict) or row.get("identity") != report.get("identity")
                        or row.get("playerKeyDecimal") != key for row in observations)):
                raise ValueError("invalid-native-smoothed-scalar-burst")
            series = [_native_values("smoothed-scalar", {"observation": row})
                      for row in observations]
            values["sampleCount"] = len(series)
            values["smoothedScalarSeriesCandidate"] = {
                name: [sample[name] for sample in series]
                for name in ("currentCandidate", "sourceCandidate", "targetCandidate", "factorCandidate")
            }
        return values
    if kind == "actor-pose":
        observation = report.get("observation")
        if not isinstance(observation, dict):
            raise ValueError("invalid-native-actor-pose-report")
        key = observation.get("playerKeyDecimal")
        if (not isinstance(key, str) or not key.isdecimal() or
                not 0 < int(key) < 2**64 or str(int(key)) != key or
                observation.get("actorHeadingQualified") is not False or
                not isinstance(observation.get("renderStatus"), str)):
            raise ValueError("invalid-native-actor-pose-report")
        observations = report.get("observations")
        if observations is not None:
            if (not isinstance(observations, list) or len(observations) < 2 or
                    type(report.get("requestedSamples")) is not int or
                    report["requestedSamples"] != len(observations) or
                    type(report.get("completedSamples")) is not int or
                    report["completedSamples"] != len(observations) or
                    observations[-1] != observation or
                    any(not isinstance(row, dict) or row.get("identity") != report.get("identity")
                        or row.get("playerKeyDecimal") != key or
                        row.get("actorHeadingQualified") is not False for row in observations)):
                raise ValueError("invalid-native-actor-pose-burst")
            for row in observations:
                if not isinstance(row.get("renderStatus"), str):
                    raise ValueError("invalid-native-actor-pose-burst")
                for name in ("actorMatrix", "modelMatrix", "renderMatrix"):
                    matrix = row.get(name)
                    if name == "renderMatrix" and matrix is None:
                        continue
                    if (not isinstance(matrix, dict) or
                            "planarAngleDegreesCandidate" not in matrix):
                        raise ValueError("invalid-native-actor-pose-burst")
                    angle = matrix["planarAngleDegreesCandidate"]
                    if angle is not None and (type(angle) not in (int, float) or
                                              not math.isfinite(angle) or
                                              not -180 <= angle <= 180):
                        raise ValueError("invalid-native-actor-pose-burst")
        angles = {}
        for name in ("actorMatrix", "modelMatrix", "renderMatrix"):
            matrix = observation.get(name)
            if matrix is None and name == "renderMatrix":
                angles[name] = None
                continue
            if (not isinstance(matrix, dict) or
                    "planarAngleDegreesCandidate" not in matrix):
                raise ValueError("invalid-native-actor-pose-report")
            value = matrix["planarAngleDegreesCandidate"]
            if value is not None and (type(value) not in (float, int) or
                                      not math.isfinite(value) or
                                      not -180 <= value <= 180):
                raise ValueError("invalid-native-actor-pose-report")
            angles[name] = value
        result = {"playerKey": key,
                  "actorPlanarDegreesCandidate": angles["actorMatrix"],
                  "modelPlanarDegreesCandidate": angles["modelMatrix"],
                  "renderPlanarDegreesCandidate": angles["renderMatrix"],
                  "renderStatus": observation["renderStatus"],
                  "actorHeadingQualified": False,
                  "sampledAtUtc": observation.get("completedAtUtc")}
        # Optional additions: older native reports have no world translations.
        for field in ("actorWorldTranslationCandidate", "renderWorldTranslationCandidate"):
            if field not in observation:
                continue
            candidate = observation[field]
            if candidate is None:
                result[field] = None
                continue
            if (not isinstance(candidate, dict) or
                    any(type(candidate.get(axis)) not in (int, float) or
                        not math.isfinite(candidate[axis]) for axis in ("x", "y", "z"))):
                raise ValueError("invalid-native-actor-world-translation")
            result[field] = {axis: candidate[axis] for axis in ("x", "y", "z")}
        field = "renderWorldTranslationMaxAbsDeltaCandidate"
        if field in observation:
            delta = observation[field]
            if delta is not None and (type(delta) not in (int, float) or
                                      not math.isfinite(delta) or delta < 0):
                raise ValueError("invalid-native-actor-world-translation")
            result[field] = delta
        if observations is not None:
            result["sampleCount"] = len(observations)
            series = {
                short: [row[matrix]["planarAngleDegreesCandidate"]
                        if row[matrix] is not None else None for row in observations]
                for short, matrix in (("actor", "actorMatrix"),
                                      ("model", "modelMatrix"),
                                      ("render", "renderMatrix"))
            }
            steps = {name: _candidate_angle_steps(values)
                     for name, values in series.items()}
            result["planarAngleSeriesDegreesCandidate"] = series
            result["planarSignedTravelDegreesCandidate"] = {
                name: sum(deltas) if deltas is not None else None
                for name, deltas in steps.items()
            }
            result["actorMaxAdjacentStepDegreesCandidate"] = (
                max(map(abs, steps["actor"])) if steps["actor"] is not None else None)
        rows = observations if observations is not None else [observation]
        if expect_translation_sources and any(not isinstance(row.get("translationSourcesCandidate"), dict)
                                              for row in rows):
            raise ValueError("missing-native-actor-translation-sources")
        if "translationSourcesCandidate" in observation:
            sources = observation["translationSourcesCandidate"]
            if not isinstance(sources, dict):
                raise ValueError("invalid-native-actor-translation-sources")
            for name in ("positionSecondaryXyz", "actorOffsetAt04F8", "actorOffsetAt0770",
                         "reconstructedActorWorldTranslation"):
                coords = sources.get(name)
                if (not isinstance(coords, dict) or
                        any(type(coords.get(axis)) not in (int, float) or
                            not math.isfinite(coords[axis]) for axis in ("x", "y", "z"))):
                    raise ValueError("invalid-native-actor-translation-sources")
            residual = sources.get("actorWorldTranslationMaxAbsDelta")
            if type(residual) not in (int, float) or not math.isfinite(residual) or residual < 0:
                raise ValueError("invalid-native-actor-translation-sources")
            result["translationSourcesCandidate"] = sources
        if expect_position:
            brackets = []
            for row in rows:
                bracket = row.get("positionBracketCandidate")
                if (not isinstance(bracket, dict) or
                        bracket.get("playerKeyDecimal") != key):
                    raise ValueError("invalid-native-actor-position-bracket")
                elapsed = bracket.get("elapsedMilliseconds")
                if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError("invalid-native-actor-position-bracket")
                pair = {"elapsedMilliseconds": elapsed}
                for edge in ("before", "after"):
                    coords = bracket.get(edge)
                    if (not isinstance(coords, dict) or
                            any(type(coords.get(axis)) not in (int, float) or
                                not math.isfinite(coords[axis]) for axis in ("x", "y", "z"))):
                        raise ValueError("invalid-native-actor-position-bracket")
                    pair[edge] = {axis: coords[axis] for axis in ("x", "y", "z")}
                brackets.append(pair)
            net = math.hypot(brackets[-1]["after"]["x"] - brackets[0]["before"]["x"],
                             brackets[-1]["after"]["z"] - brackets[0]["before"]["z"])
            within = [math.hypot(b["after"]["x"] - b["before"]["x"],
                                 b["after"]["z"] - b["before"]["z"]) for b in brackets]
            anchors = [point for bracket in brackets
                       for point in (bracket["before"], bracket["after"])]
            steps = [math.hypot(later["x"] - earlier["x"],
                                later["z"] - earlier["z"])
                     for earlier, later in zip(anchors, anchors[1:])]
            observed_path = sum(steps)
            if (not math.isfinite(net) or
                    any(not math.isfinite(value) for value in within + steps) or
                    not math.isfinite(observed_path)):
                raise ValueError("invalid-native-actor-position-bracket")
            result["positionBracketSeriesCandidate"] = brackets
            result["positionNetPlanarDisplacementCandidate"] = net
            result["positionMaxWithinSamplePlanarChangeCandidate"] = max(within)
            result["positionObservedPlanarPathLengthCandidate"] = observed_path
            result["positionMaxAdjacentPlanarStepCandidate"] = max(steps)
            if any("actorWorldTranslationCandidate" in row for row in rows):
                planar_residuals = []
                vertical_offsets = []
                for row, bracket in zip(rows, brackets):
                    actor = row.get("actorWorldTranslationCandidate")
                    if actor is None:
                        planar_residuals.append(None)
                        vertical_offsets.append(None)
                        continue
                    if (not isinstance(actor, dict) or
                            any(type(actor.get(axis)) not in (int, float) or
                                not math.isfinite(actor[axis]) for axis in ("x", "y", "z"))):
                        raise ValueError("invalid-native-actor-world-translation")
                    before, after = bracket["before"], bracket["after"]
                    dx, dz = after["x"] - before["x"], after["z"] - before["z"]
                    length_squared = dx * dx + dz * dz
                    projection = ((actor["x"] - before["x"]) * dx +
                                  (actor["z"] - before["z"]) * dz)
                    fraction = min(1.0, max(0.0, projection / length_squared)) if length_squared else 0.0
                    residual = math.hypot(actor["x"] - (before["x"] + fraction * dx),
                                          actor["z"] - (before["z"] + fraction * dz))
                    vertical = actor["y"] - (before["y"] + fraction * (after["y"] - before["y"]))
                    if not math.isfinite(residual) or not math.isfinite(vertical):
                        raise ValueError("invalid-native-actor-position-fit")
                    planar_residuals.append(residual)
                    vertical_offsets.append(vertical)
                result["actorPositionPlanarResidualSeriesCandidate"] = planar_residuals
                result["actorPositionVerticalOffsetSeriesCandidate"] = vertical_offsets
                result["actorPositionMaxPlanarResidualCandidate"] = (
                    max(planar_residuals) if all(v is not None for v in planar_residuals) else None)
        elif any(row.get("positionBracketCandidate") is not None for row in rows):
            raise ValueError("unexpected-native-actor-position-bracket")
        return result
    if kind == "player-context":
        if report.get("contractVersion") == "native-current-player-context-candidate-burst/1":
            rows = report.get("observations")
            identity = report.get("identity")
            count = report.get("requestedSamples")
            if (type(count) is not int or not 2 <= count <= 30
                    or report.get("completedSamples") != count
                    or not isinstance(rows, list) or len(rows) != count
                    or rows[-1] != report.get("observation")
                    or not isinstance(identity, dict)):
                raise ValueError("invalid-native-player-context-burst")
            projected = []
            previous_end = None
            for row in rows:
                if not isinstance(row, dict) or row.get("identity") != identity:
                    raise ValueError("invalid-native-player-context-burst-identity")
                single = dict(report, contractVersion="native-current-player-context-candidate-sample/1",
                              observation=row)
                single.pop("observations", None)
                value = _native_values(kind, single)
                start = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
                if ((previous_end is not None and start < previous_end)
                        or (projected and value["unitKey"] != projected[0]["unitKey"])):
                    raise ValueError("invalid-native-player-context-burst-order-or-owner")
                previous_end = end
                projected.append(value)
            last = projected[-1]
            targets = [value["target"]["unitIdCandidate"] for value in projected]
            compared = [(before, after) for before, after in zip(targets, targets[1:])
                        if before is not None and after is not None]
            return dict(last, sampleCount=count,
                        selfKeyStableCandidate=True,
                        targetStatusSeries=[value["target"]["status"] for value in projected],
                        targetIdSeriesCandidate=targets,
                        comparableTargetPairs=len(compared),
                        changedTargetPairsCandidate=sum(a != b for a, b in compared))
        observation = report.get("observation")
        qualification = "candidate-only; changed-state, API correspondence and restart unverified"
        if (type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1
                or report.get("contractVersion") != "native-current-player-context-candidate-sample/1"
                or report.get("qualification") != qualification
                or not isinstance(observation, dict)
                or observation.get("qualification") != qualification):
            raise ValueError("invalid-native-player-context-contract")
        unit = observation.get("unitKey")
        level, combat = observation.get("rawLevel"), observation.get("rawCombat")
        fallback, target_key = observation.get("rawFallbackKey"), observation.get("targetKeyCandidate")
        target_status, target_id = observation.get("targetStatus"), observation.get("targetUnitIdCandidate")
        if (type(unit) is not int or not 0 < unit < 2**64
                or type(level) is not int or not -(2**31) <= level < 2**31
                or type(combat) is not int or not 0 <= combat <= 255
                or observation.get("combatStatus") != "raw-byte-candidate"
                or type(observation.get("combatCandidate")) is not bool
                or observation["combatCandidate"] != (combat != 0)
                or observation.get("levelStatus") not in (
                    "alternate-component-unavailable",
                    "numeric-getter-and-presentation-candidate",
                    "numeric-getter-candidate-presentation-unqualified")
                or type(fallback) is not int or not 0 <= fallback < 2**64):
            raise ValueError("invalid-native-player-context-values")
        if target_status == "fallback-key-candidate":
            if (type(target_key) is not int or target_key == 0
                    or target_key != fallback or target_id != f"u{target_key:016X}"):
                raise ValueError("invalid-native-player-context-target")
        elif target_status == "raw-getter-zero-candidate":
            if target_key != 0 or type(target_key) is not int or fallback != 0 or target_id is not None:
                raise ValueError("invalid-native-player-context-target")
        elif target_status in ("override-unavailable", "guard-unreadable-or-invalid"):
            if target_key is not None or target_id is not None:
                raise ValueError("invalid-native-player-context-target")
        else:
            raise ValueError("invalid-native-player-context-target")
        calling = observation.get("rawCalling")
        calling_name = observation.get("callingCandidate")
        calling_names = {1: "warrior", 2: "cleric", 3: "mage", 4: "rogue", 7: "primalist"}
        if ((calling is not None and (type(calling) is not int
                                       or not 0 <= calling < 2**32
                                       or calling_name != calling_names.get(calling)))
                or (calling is None and calling_name is not None)):
            raise ValueError("invalid-native-player-context-calling")
        try:
            started = datetime.fromisoformat(observation["startedAtUtc"].replace("Z", "+00:00"))
            completed = datetime.fromisoformat(observation["completedAtUtc"].replace("Z", "+00:00"))
            if (started.utcoffset() != timedelta(0) or completed.utcoffset() != timedelta(0)
                    or completed < started):
                raise ValueError("invalid-native-player-context-time")
        except (KeyError, AttributeError, ValueError, TypeError, OverflowError) as exc:
            raise ValueError("invalid-native-player-context-time") from exc
        return {
            "unitKey": str(unit), "sampledAtUtc": observation["completedAtUtc"],
            "level": {"status": observation["levelStatus"], "rawCandidate": level},
            "combat": {"status": "raw-byte-candidate", "rawByte": combat,
                       "candidate": observation["combatCandidate"]},
            "target": {"status": target_status, "unitIdCandidate": target_id},
            "calling": {"rawCandidate": calling, "nameCandidate": calling_name},
        }
    if kind == "vitals":
        observation = report.get("observation")
        if not isinstance(observation, dict) or type(observation.get("unitKey")) is not int:
            raise ValueError("invalid-native-vitals-report")
        if not 0 < observation["unitKey"] < 2**64:
            raise ValueError("invalid-native-vitals-report")
        result = {"unitKey": str(observation["unitKey"])}
        observations = report.get("observations")
        if observations is not None:
            if (not isinstance(observations, list) or not observations or
                    report.get("requestedSamples") != len(observations) or
                    report.get("completedSamples") != len(observations) or
                    observations[-1] != observation or
                    any(not isinstance(row, dict) or row.get("unitKey") != observation["unitKey"]
                        or row.get("identity") != report.get("identity") for row in observations)):
                raise ValueError("invalid-native-vitals-report")
            result["sampleCount"] = len(observations)
            result["sampledAtUtc"] = observation.get("completedAtUtc")
        for resource in ("health", "energy", "mana"):
            entry = observation.get(resource)
            if not isinstance(entry, dict) or not isinstance(entry.get("status"), str):
                raise ValueError("invalid-native-vitals-report")
            result[resource] = {name: entry.get(name) for name in
                                ("status", "current", "maximum", "unavailableReason")}
        return result
    if kind == "position":
        observations = report.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError("invalid-native-position-report")
        unit_keys = set()
        for sample in observations:
            if not isinstance(sample, dict):
                raise ValueError("invalid-native-position-report")
            key = sample.get("unitKey")
            if (not isinstance(key, str) or not key.isdecimal() or
                    not 0 < int(key) < 2**64 or str(int(key)) != key or
                    any(type(sample.get(axis)) not in (float, int) or
                        not math.isfinite(sample[axis]) for axis in ("x", "y", "z"))):
                raise ValueError("invalid-native-position-report")
            unit_keys.add(key)
        if len(unit_keys) != 1:
            raise ValueError("native-position-owner-changed")
        # Observed path length captures out-and-back travel that net displacement
        # misses. Neither a zero path nor a changed XYZ proves source freshness.
        if any("index" in sample for sample in observations):
            if any(type(sample.get("index")) is not int or sample["index"] != i
                   for i, sample in enumerate(observations, 1)):
                raise ValueError("invalid-native-position-sample-order")
        first, last = observations[0], observations[-1]
        planar_steps = [
            math.hypot(later["x"] - earlier["x"], later["z"] - earlier["z"])
            for earlier, later in zip(observations, observations[1:])
        ]
        net = math.hypot(last["x"] - first["x"], last["z"] - first["z"])
        try:
            path = math.fsum(planar_steps)
        except OverflowError as exc:
            raise ValueError("invalid-native-position-motion") from exc
        vertical_delta = last["y"] - first["y"]
        if not all(math.isfinite(v) for v in (net, path, vertical_delta, *planar_steps)):
            raise ValueError("invalid-native-position-motion")
        result = {"sampleCount": len(observations), "unitKey": last["unitKey"],
                  "x": last["x"], "y": last["y"], "z": last["z"],
                  "sampledAtUtc": last.get("completedAtUtc"),
                  "refreshGuardStatus": last.get("refreshGuardStatus")}
        # A single point cannot establish displacement or a traveled path.
        if len(observations) > 1:
            result.update({
                "firstPositionCandidate": {axis: first[axis] for axis in ("x", "y", "z")},
                "netPlanarDisplacementCandidate": net,
                "observedPlanarPathLengthCandidate": path,
                "maxAdjacentPlanarStepCandidate": max(planar_steps),
                "verticalDeltaCandidate": vertical_delta,
            })
        return result
    return None


def read_native(selection, kind, output=None, *, samples=None, interval_ms=None,
                include_position=False, include_transform_sources=False, include_target=False,
                unit_limit=None, start_bucket=None):
    """Read a candidate from the exact selected LOCAL physical process, without input."""
    if selection.get("status") != "ready":
        return selection
    # A cached selection is never authority to read a different physical PC.
    actual_host = socket.gethostname()
    owner_host = selection.get("ownerHost")
    if (actual_host.upper() not in SUPPORTED_HOSTS or
            not isinstance(owner_host, str) or
            owner_host.casefold() != actual_host.casefold()):
        return dict(selection, status="blocked", reason="host-mismatch")
    if kind not in NATIVE_READS:
        return dict(selection, status="blocked", reason="unknown-native-read")
    if type(include_position) is not bool or (include_position and kind != "actor-pose"):
        return dict(selection, status="blocked", reason="position-bracket-requires-actor-pose")
    if type(include_transform_sources) is not bool or (include_transform_sources and kind != "actor-pose"):
        return dict(selection, status="blocked", reason="transform-sources-require-actor-pose")
    if type(include_target) is not bool or (include_target and kind != "facing"):
        return dict(selection, status="blocked", reason="target-projection-requires-facing")
    if ((unit_limit is not None or start_bucket is not None) and kind != "unit-positions"):
        return dict(selection, status="blocked", reason="unit-scan-options-require-unit-positions")
    if ((unit_limit is not None and (type(unit_limit) is not int or not 1 <= unit_limit <= 512))
            or (start_bucket is not None and (type(start_bucket) is not int or not 0 <= start_bucket < 2**64))):
        return dict(selection, status="blocked", reason="invalid-unit-scan-options")
    if kind not in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation", "facing", "player-context") and (samples is not None or interval_ms is not None):
        return dict(selection, status="blocked", reason="sampling-options-require-supported-native-burst")
    if ((samples is not None and (type(samples) is not int or not 1 <= samples <= 30))
            or (interval_ms is not None and (type(interval_ms) is not int or not 0 <= interval_ms <= 2000))):
        return dict(selection, status="blocked", reason="invalid-position-sampling")
    target = selection.get("target")
    if not isinstance(target, dict):
        return dict(selection, status="blocked", reason="invalid-local-process-identity")
    pid, ticks = target.get("processId"), target.get("processStartUtcTicks")
    target_host = target.get("hostName")
    if (type(pid) is not int or pid <= 0 or not isinstance(ticks, str)
            or not ticks.isdecimal() or int(ticks) <= 0
            or not isinstance(target_host, str)
            or target_host.casefold() != actual_host.casefold()):
        return dict(selection, status="blocked", reason="invalid-local-process-identity")
    if not NATIVE_EXE.is_file():
        return dict(selection, status="blocked", reason="native-reader-not-built",
                    buildHint="dotnet build src/RiftReader2.Live")
    path = (Path(output) if output is not None else
            ROOT / "artifacts" / ("physical-native-" + kind + "-" + uuid.uuid4().hex + ".json"))
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        return dict(selection, status="blocked", reason="native-output-exists")
    command = [str(NATIVE_EXE), NATIVE_READS[kind], "--pid", str(pid),
               "--start-ticks", ticks, "--output", str(path)]
    if samples is not None:
        command.extend(("--samples", str(samples)))
    if interval_ms is not None:
        command.extend(("--interval-ms", str(interval_ms)))
    if include_position:
        command.extend(("--include-position", "true"))
    if include_transform_sources:
        command.extend(("--include-transform-sources", "true"))
    if include_target:
        command.extend(("--include-target", "true"))
    if unit_limit is not None:
        command.extend(("--unit-limit", str(unit_limit)))
    if start_bucket is not None:
        command.extend(("--start-bucket", str(start_bucket)))
    # Long, explicitly requested intervals must not hit the wrapper's timeout.
    timeout = (30 + ((samples if samples is not None else
                      (3 if kind == "position" else 1)) - 1)
               * (interval_ms if interval_ms is not None else 500) / 1000
               if kind in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation", "facing", "player-context") else 30)
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=timeout, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(selection, status="blocked", reason="native-reader-launch-failed",
                    errorType=type(exc).__name__)
    if completed.returncode != 0:
        return dict(selection, status="blocked", reason="native-reader-failed",
                    exitCode=completed.returncode,
                    detail=completed.stderr.strip()[-240:])
    try:
        # Position emits per-sample JSON lines before its final summary receipt.
        lines = completed.stdout.splitlines()
        summary = json.loads(lines[-1]) if lines else None
    except (ValueError, TypeError):
        return dict(selection, status="blocked", reason="invalid-native-reader-receipt")
    if (not isinstance(summary, dict) or not path.is_file()
            or summary.get("recordType") != NATIVE_RECEIPTS[kind]
            or not isinstance(summary.get("output"), str)
            or Path(summary["output"]).resolve() != path.resolve()
            or summary.get("status") != (None if kind == "stats" else "complete")):
        return dict(selection, status="blocked", reason="invalid-native-reader-receipt")
    try:
        report_bytes = path.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
        observation = report.get("observation")
        identity = report.get("identity") or (observation.get("identity")
                                                if isinstance(observation, dict) else None)
        if (report.get("status") != "complete" or not isinstance(identity, dict)
                or identity.get("processId") != pid
                or str(identity.get("processStartUtcTicks")) != ticks
                or str(identity.get("executableSha256", "")).casefold()
                    != str(target.get("executableSha256", "")).casefold()):
            raise ValueError("report-identity-or-status-mismatch")
        if kind == "position":
            expected_count = 3 if samples is None else samples
            rows = report.get("observations")
            if (type(report.get("requestedSamples")) is not int or
                    report["requestedSamples"] != expected_count or
                    type(report.get("completedSamples")) is not int or
                    report["completedSamples"] != expected_count or
                    not isinstance(rows, list) or len(rows) != expected_count):
                raise ValueError("incomplete-native-position-burst")
        if kind == "facing" and report.get("completedSamples") != (1 if samples is None else samples):
            raise ValueError("incomplete-native-facing-burst")
        if (kind == "player-context" and samples is not None and samples > 1
                and (report.get("completedSamples") != samples or
                     not isinstance(report.get("observations"), list))):
            raise ValueError("incomplete-native-player-context-burst")
        if (kind == "vitals" and samples is not None and samples > 1
                and report.get("completedSamples") != samples):
            raise ValueError("incomplete-native-vitals-burst")
        if (kind == "actor-pose" and samples is not None and samples > 1
                and (report.get("completedSamples") != samples or
                     not isinstance(report.get("observations"), list))):
            raise ValueError("incomplete-native-actor-pose-burst")
        if (kind == "smoothed-scalar" and samples is not None and samples > 1
                and (report.get("completedSamples") != samples or
                     not isinstance(report.get("observations"), list))):
            raise ValueError("incomplete-native-smoothed-scalar-burst")
        if (kind == "orientation" and samples is not None and samples > 1
                and (report.get("completedSamples") != samples or
                     not isinstance(report.get("observations"), list))):
            raise ValueError("incomplete-native-orientation-burst")
        values = _native_values(kind, report, expect_position=include_position,
                                expect_translation_sources=include_transform_sources)
        if kind == "unit-positions" and (observation["unitLimit"] != (512 if unit_limit is None else unit_limit)
                or observation["startBucket"] != (0 if start_bucket is None else start_bucket) % observation["bucketCount"]):
            raise ValueError("native-unit-position-options-mismatch")
        if include_target and any(row.get("targetPositionPairCandidate") is None
                                  for row in report["observations"]):
            raise ValueError("missing-native-facing-target")
        # Reuse the strict offline reducer for candidate HP/resource deltas.
        burst_summary = (summarize_native_vitals_burst.summarize(
            report, hashlib.sha256(report_bytes).hexdigest())
            if kind == "vitals" and samples is not None and samples > 1 else None)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return dict(selection, status="blocked", reason="invalid-native-reader-report")
    return dict(selection, status="complete", nativeRead=kind,
                nativeOutput=str(path), nativeSummary=summary, nativeValues=values,
                qualification="candidate-only; changed-state/freshness/restart-unverified",
                **({"nativeBurstSummary": burst_summary} if burst_summary is not None else {}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", choices=SUPPORTED_HOSTS,
                        help="optional guard: refuse a different physical PC")
    parser.add_argument("--physical-pid", type=int,
                        help="pin one local rift_x64.exe PID; required if multiple exist")
    parser.add_argument("--read-native", choices=tuple(NATIVE_READS),
                        help="read one candidate from the pinned physical process; no input")
    parser.add_argument("--output", type=Path,
                        help="new JSON file for --read-native (default: unique artifacts path)")
    parser.add_argument("--samples", type=int,
                        help="bounded native sampling: 1-30 samples (default: 3 position, 1 otherwise)")
    parser.add_argument("--interval-ms", type=int,
                        help="bounded native sampling: 0-2000ms between reads (facing default: 100, others: 500)")
    parser.add_argument("--include-position", action="store_true",
                        help="actor-pose only: bracket each pose with same-player native XYZ candidates")
    parser.add_argument("--include-transform-sources", action="store_true",
                        help="actor-pose only: read secondary XYZ and both actor transform offsets")
    parser.add_argument("--include-target", action="store_true",
                        help="facing only: project selected target position with a camera stability bracket")
    parser.add_argument("--unit-limit", type=int, help="unit-positions only: bounded 1-512 examined units (default 512)")
    parser.add_argument("--start-bucket", type=int, help="unit-positions only: first unit-manager bucket (default 0)")
    parser.add_argument("--anchor-catalog", type=Path,
                        help="with native position: offline compare XYZ to named-anchor catalog")
    parser.add_argument("--anchor-id",
                        help="with --anchor-catalog: offline destination ID; no movement")
    parser.add_argument("--project-world", type=float, nargs=3, metavar=("X", "Y", "Z"),
                        help="with facing: project this world point into normalized client coordinates")
    args = parser.parse_args(argv)
    anchor_requested = args.anchor_catalog is not None or args.anchor_id is not None
    if args.project_world is not None and (args.read_native != "facing" or
                                           any(not math.isfinite(value) for value in args.project_world)):
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "world-projection-requires-facing-and-finite-xyz"}
    elif anchor_requested and (args.anchor_catalog is None or args.anchor_id is None
                             or args.read_native != "position"):
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "anchor-preview-requires-position-catalog-and-id"}
    elif args.read_native is not None and args.expected_host is None:
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "native-read-requires-expected-host"}
    elif args.include_position and args.read_native != "actor-pose":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "position-bracket-requires-actor-pose"}
    elif args.include_transform_sources and args.read_native != "actor-pose":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "transform-sources-require-actor-pose"}
    elif args.include_target and args.read_native != "facing":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "target-projection-requires-facing"}
    elif (args.unit_limit is not None or args.start_bucket is not None) and args.read_native != "unit-positions":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "unit-scan-options-require-unit-positions"}
    elif (args.samples is not None or args.interval_ms is not None) and args.read_native not in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation", "facing", "player-context"):
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "sampling-options-require-position-vitals-or-actor-pose"}
    else:
        result = select_physical(args.expected_host, args.physical_pid)
    if args.output is not None and args.read_native is None:
        result = dict(result, status="blocked", reason="output-requires-native-read")
    elif args.read_native:
        scan_options = ({"unit_limit": args.unit_limit, "start_bucket": args.start_bucket}
                        if args.unit_limit is not None or args.start_bucket is not None else {})
        result = read_native(result, args.read_native, args.output,
                             samples=args.samples, interval_ms=args.interval_ms,
                              include_position=args.include_position,
                              include_transform_sources=args.include_transform_sources,
                              include_target=args.include_target, **scan_options)
    if anchor_requested and result["status"] == "complete":
        from scripts import physical_route_preview
        try:
            preview = physical_route_preview.preview(
                Path(result["nativeOutput"]), args.anchor_catalog, args.anchor_id)
            result = dict(result, offlineAnchorPreview=preview)
        except (OSError, ValueError) as exc:
            result = dict(result, status="blocked", reason="offline-anchor-preview-failed",
                          detail=str(exc)[:240])
    if args.project_world is not None and result["status"] == "complete":
        try:
            report = json.loads(Path(result["nativeOutput"]).read_text(encoding="utf-8"))
            point = dict(zip(("x", "y", "z"), args.project_world))
            result["projectedWorldPointCandidate"] = dict(
                _project_world_point(report["observation"].get("opticalCameraCandidate"), point),
                worldXYZ=point)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result = dict(result, status="blocked", reason="world-projection-failed",
                          detail=str(exc)[:240])
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("ready", "complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
