"""Select a real, locally running RIFT process; never discover VMware guests."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import socket
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical

SUPPORTED_HOSTS = ("AMD-DESKTOP", "LEGION")
NATIVE_READS = {
    "position": "sample-current-position",
    "vitals": "sample-current-vitals",
    "orientation": "sample-current-orientation",
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


def _native_values(kind, report, *, expect_position=False, expect_translation_sources=False):
    """Project immediate useful values; preserve exact large unit keys as text."""
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
                if actual != bit:
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
        result = {"unitKey": key, "headingQualified": False,
                  "refreshHandleRaw": refresh_handle, "refreshFlagRaw": refresh_flag,
                  "primaryPlanarDegreesCandidate": angles["primary"],
                  "secondaryPlanarDegreesCandidate": angles["secondary"],
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
                    if type(started_raw) is not str or type(completed_raw) is not str:
                        raise ValueError("missing-timestamp")
                    started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                    completed = datetime.fromisoformat(completed_raw.replace("Z", "+00:00"))
                    if (started.utcoffset() != timedelta(0) or
                            completed.utcoffset() != timedelta(0) or
                            not started < completed or
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
        last = observations[-1]
        return {"sampleCount": len(observations), "unitKey": last["unitKey"],
                "x": last["x"], "y": last["y"], "z": last["z"],
                "sampledAtUtc": last.get("completedAtUtc"),
                "refreshGuardStatus": last.get("refreshGuardStatus")}
    return None


def read_native(selection, kind, output=None, *, samples=None, interval_ms=None,
                include_position=False, include_transform_sources=False):
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
    if kind not in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation") and (samples is not None or interval_ms is not None):
        return dict(selection, status="blocked", reason="sampling-options-require-position-vitals-or-actor-pose")
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
    # Long, explicitly requested intervals must not hit the wrapper's timeout.
    timeout = (30 + ((samples if samples is not None else
                      (3 if kind == "position" else 1)) - 1)
               * (interval_ms if interval_ms is not None else 500) / 1000
               if kind in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation") else 30)
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=timeout, check=False)
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
        report = json.loads(path.read_text(encoding="utf-8"))
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
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return dict(selection, status="blocked", reason="invalid-native-reader-report")
    return dict(selection, status="complete", nativeRead=kind,
                nativeOutput=str(path), nativeSummary=summary, nativeValues=values,
                qualification="candidate-only; changed-state/freshness/restart-unverified")


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
                        help="position/vitals/actor-pose/smoothed-scalar/orientation: 1-30 samples (default: 3 position, 1 otherwise)")
    parser.add_argument("--interval-ms", type=int,
                        help="position/vitals/actor-pose/smoothed-scalar/orientation: 0-2000ms between reads (default: 500)")
    parser.add_argument("--include-position", action="store_true",
                        help="actor-pose only: bracket each pose with same-player native XYZ candidates")
    parser.add_argument("--include-transform-sources", action="store_true",
                        help="actor-pose only: read secondary XYZ and both actor transform offsets")
    args = parser.parse_args(argv)
    if args.read_native is not None and args.expected_host is None:
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "native-read-requires-expected-host"}
    elif args.include_position and args.read_native != "actor-pose":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "position-bracket-requires-actor-pose"}
    elif args.include_transform_sources and args.read_native != "actor-pose":
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "transform-sources-require-actor-pose"}
    elif (args.samples is not None or args.interval_ms is not None) and args.read_native not in ("position", "vitals", "actor-pose", "smoothed-scalar", "orientation"):
        result = {"status": "blocked", "workflow": "physical",
                  "reason": "sampling-options-require-position-vitals-or-actor-pose"}
    else:
        result = select_physical(args.expected_host, args.physical_pid)
    if args.output is not None and args.read_native is None:
        result = dict(result, status="blocked", reason="output-requires-native-read")
    elif args.read_native:
        result = read_native(result, args.read_native, args.output,
                             samples=args.samples, interval_ms=args.interval_ms,
                              include_position=args.include_position,
                              include_transform_sources=args.include_transform_sources)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("ready", "complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
