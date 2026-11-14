#!/usr/bin/env python3
"""Analyze retained continuous-route body/camera samples without game access.

This reports candidate-only motion statistics.  Optical camera values remain
unqualified, and the report does not claim universal smoothness or live state.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re


MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_LEGS = 500
MAX_PATH_SAMPLES = 30000
MAX_KEY_EVENTS = 20000


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-json-key")
        value[key] = item
    return value


def _time(value):
    _require(isinstance(value, str) and len(value) <= 48, "invalid-event-time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid-event-time") from exc
    _require(result.utcoffset() is not None, "invalid-event-time")
    return result


def _number(value, reason="invalid-angle"):
    _require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def _load(path):
    path = Path(path)
    _require(not path.is_symlink() and path.is_file(), "camera-source-missing")
    size = path.stat().st_size
    _require(0 < size <= MAX_SOURCE_BYTES, "camera-source-empty-or-oversized")
    raw = path.read_bytes()
    _require(0 < len(raw) <= MAX_SOURCE_BYTES, "camera-source-empty-or-oversized")
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("nonfinite-camera-source")))
    except UnicodeError as exc:
        raise ValueError("invalid-camera-source-encoding") from exc
    _require(isinstance(value, dict), "invalid-camera-route-receipt")
    legs = value.get("legs")
    _require(isinstance(legs, list) and 1 <= len(legs) <= MAX_LEGS,
             "invalid-camera-route-legs")
    return value


def _unwrap(values):
    if not values:
        return []
    result = [float(values[0])]
    for value in values[1:]:
        delta = (float(value) - result[-1] + 180.0) % 360.0 - 180.0
        _require(abs(delta) != 180.0, "ambiguous-half-turn-sample")
        result.append(result[-1] + delta)
    return result


def _reversals(values, threshold):
    """Count direction changes only after an excursion and reversal reach threshold."""
    if len(values) < 3:
        return 0
    anchor = values[0]
    extreme = anchor
    direction = 0
    count = 0
    for value in values[1:]:
        if direction == 0:
            if value - anchor >= threshold:
                direction, extreme = 1, value
            elif anchor - value >= threshold:
                direction, extreme = -1, value
        elif direction > 0:
            if value > extreme:
                extreme = value
            elif extreme - value >= threshold:
                count += 1
                direction, extreme = -1, value
        else:
            if value < extreme:
                extreme = value
            elif value - extreme >= threshold:
                count += 1
                direction, extreme = 1, value
    return count


def _angle_metrics(values, *, reversal_degrees):
    if not values:
        return {
            "availability": "unavailable", "sampleCount": 0,
            "unavailableReason": "no-usable-samples",
        }
    unwrapped = _unwrap(values)
    variation = sum(abs(b - a) for a, b in zip(unwrapped, unwrapped[1:]))
    displacement = abs(unwrapped[-1] - unwrapped[0])
    return {
        "availability": "candidate", "sampleCount": len(unwrapped),
        "startDegreesCandidate": unwrapped[0],
        "endDegreesCandidate": unwrapped[-1],
        "unwrappedMinimumDegreesCandidate": min(unwrapped),
        "unwrappedMaximumDegreesCandidate": max(unwrapped),
        "unwrappedRangeDegreesCandidate": max(unwrapped) - min(unwrapped),
        "totalVariationDegreesCandidate": variation,
        "totalVariationExcessDegreesCandidate": max(0.0, variation - displacement),
        "significantReversalsCandidate": _reversals(unwrapped, reversal_degrees),
        "reversalHysteresisDegrees": reversal_degrees,
    }


def _sample_metrics(rows, start, end, *, reversal_degrees, gap_seconds):
    selected = [row for row in rows if start <= row["time"] <= end]
    body = _angle_metrics([row["body"] for row in selected],
                          reversal_degrees=reversal_degrees)
    camera_rows = [row for row in selected if row["camera"] is not None]
    camera = _angle_metrics([row["camera"] for row in camera_rows],
                            reversal_degrees=reversal_degrees)
    pitch = _angle_metrics([row["pitch"] for row in camera_rows],
                           reversal_degrees=reversal_degrees)
    gaps = [(b["time"] - a["time"]).total_seconds()
            for a, b in zip(camera_rows, camera_rows[1:])]
    camera.update({
        "statusCounts": _counts(row["cameraStatus"] for row in selected),
        "maximumSampleGapSeconds": max(gaps, default=None),
        "meanSampleGapSeconds": sum(gaps) / len(gaps) if gaps else None,
        "gapsOverThreshold": sum(gap > gap_seconds for gap in gaps),
        "gapThresholdSeconds": gap_seconds,
        "intervalSeconds": (end - start).total_seconds(),
        "bodySampleCount": len(selected),
        "opticalYawQualified": False,
    })
    return body, camera, pitch


def _counts(values):
    result = {}
    for value in values:
        key = "null" if value is None else str(value)
        result[key] = result.get(key, 0) + 1
    return result


def _path(receipt):
    path = receipt.get("path")
    _require(isinstance(path, list) and len(path) <= MAX_PATH_SAMPLES,
             "invalid-camera-path")
    result = []
    last = None
    for sample in path:
        _require(isinstance(sample, dict), "invalid-camera-path-sample")
        stamp = _time(sample.get("observedAtUtc"))
        _require(last is None or stamp >= last, "camera-path-time-order-invalid")
        last = stamp
        body = _number(sample.get("bearing"), "invalid-body-bearing")
        camera_value = sample.get("opticalCameraBearingDegreesCandidate")
        pitch_value = sample.get("opticalCameraPitchDegreesCandidate")
        status = sample.get("opticalCameraStatus")
        _require(status is None or isinstance(status, str),
                 "invalid-optical-camera-status")
        if camera_value is None and pitch_value is None:
            camera = pitch = None
        else:
            _require(camera_value is not None and pitch_value is not None,
                     "partial-optical-camera-sample")
            _require(status == "available-candidate",
                     "unavailable-optical-camera-values")
            camera = _number(camera_value, "invalid-optical-camera-bearing")
            pitch = _number(pitch_value, "invalid-optical-camera-pitch")
        result.append({"time": stamp, "body": body, "camera": camera,
                       "pitch": pitch, "cameraStatus": status})
    return result


def _events(receipt):
    events = receipt.get("keySendEvents")
    _require(isinstance(events, list) and len(events) <= MAX_KEY_EVENTS,
             "invalid-camera-key-events")
    result = []
    last = None
    for event in events:
        _require(isinstance(event, dict), "invalid-camera-key-event")
        key, phase = event.get("key"), event.get("phase")
        _require(key in ("w", "a", "d") and phase in ("key-down", "key-up"),
                 "invalid-camera-key-transition")
        started = _time(event.get("callStartedAtUtc"))
        completed = _time(event.get("callCompletedAtUtc"))
        _require(started <= completed and (last is None or started >= last),
                 "camera-key-time-order-invalid")
        last = started
        if event.get("inserted") is True:
            result.append({"key": key, "phase": phase, "started": started,
                           "completed": completed})
    return result


def _w_intervals(events):
    intervals = []
    down = None
    for event in events:
        if event["key"] != "w":
            continue
        if event["phase"] == "key-down":
            _require(down is None, "overlapping-forward-key-down")
            down = event
        else:
            _require(down is not None, "forward-key-up-without-down")
            _require(down["completed"] <= event["started"],
                     "invalid-forward-key-interval")
            intervals.append((down["completed"], event["started"]))
            down = None
    _require(down is None, "forward-key-release-missing")
    return intervals


def analyze_leg(leg, index, *, reversal_degrees, gap_seconds):
    _require(isinstance(leg, dict), "invalid-camera-route-leg")
    receipt = leg.get("nativeReceipt")
    _require(isinstance(receipt, dict), "camera-native-receipt-missing")
    path, events = _path(receipt), _events(receipt)
    intervals = []
    all_steering = []
    for number, (start, end) in enumerate(_w_intervals(events), 1):
        steering = [event for event in events
                    if event["key"] in ("a", "d")
                    and event["phase"] == "key-down"
                    and start <= event["started"] <= end]
        keys = [event["key"] for event in steering]
        all_steering.extend(keys)
        body, camera, pitch = _sample_metrics(
            path, start, end, reversal_degrees=reversal_degrees,
            gap_seconds=gap_seconds)
        intervals.append({
            "index": number, "startedAtUtc": start.isoformat(),
            "endedAtUtc": end.isoformat(),
            "durationSeconds": (end - start).total_seconds(),
            "travelSteeringKeyDownCount": len(keys),
            "travelSteeringAlternations": sum(a != b for a, b in zip(keys, keys[1:])),
            "travelSteeringSequence": keys,
            "bodyYaw": body, "opticalCameraYaw": camera,
            "opticalCameraPitch": pitch,
        })
    return {
        "index": index,
        "name": leg.get("name"),
        "nativeStatus": receipt.get("status"),
        "pathSampleCount": len(path),
        "forwardIntervalCount": len(intervals),
        "travelSteeringKeyDownCount": len(all_steering),
        "travelSteeringAlternations": sum(
            a != b for a, b in zip(all_steering, all_steering[1:])),
        "forwardIntervals": intervals,
    }


def analyze(path, *, reversal_degrees=2.0, camera_gap_seconds=0.1):
    _require(type(reversal_degrees) in (int, float)
             and math.isfinite(reversal_degrees) and 0 < reversal_degrees <= 90,
             "invalid-reversal-threshold")
    _require(type(camera_gap_seconds) in (int, float)
             and math.isfinite(camera_gap_seconds) and 0 < camera_gap_seconds <= 10,
             "invalid-camera-gap-threshold")
    source = _load(path)
    legs = [analyze_leg(leg, i, reversal_degrees=float(reversal_degrees),
                        gap_seconds=float(camera_gap_seconds))
            for i, leg in enumerate(source["legs"], 1)]
    camera_samples = sum(
        interval["opticalCameraYaw"]["sampleCount"]
        for leg in legs for interval in leg["forwardIntervals"])
    return {
        "schemaVersion": 1,
        "contractVersion": "follow-camera-acceptance-candidate/1",
        "status": "candidate-only",
        "source": str(Path(path).resolve()),
        "legCount": len(legs),
        "forwardIntervalCount": sum(leg["forwardIntervalCount"] for leg in legs),
        "opticalCameraSampleCount": camera_samples,
        "opticalCameraAvailability": "candidate" if camera_samples else "unavailable",
        "opticalYawQualified": False,
        "universalSmoothnessQualified": False,
        "qualification": (
            "Offline retained-receipt arithmetic only; optical camera yaw and "
            "universal camera smoothness are not qualified."),
        "legs": legs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path,
                        help="Retained route-run JSON containing legs[].nativeReceipt")
    parser.add_argument("--reversal-degrees", type=float, default=2.0,
                        help="Extrema hysteresis for significant yaw reversals (default: 2)")
    parser.add_argument("--camera-gap-seconds", type=float, default=0.1,
                        help="Report optical sample gaps above this duration (default: 0.1)")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(analyze(
            args.receipt, reversal_degrees=args.reversal_degrees,
            camera_gap_seconds=args.camera_gap_seconds),
            sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            RecursionError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[a-z0-9-]{1,100}", reason):
            reason = "follow-camera-analysis-unavailable"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
