#!/usr/bin/env python3
"""Compare two retained physical-RIFT orientation/actor-pose captures offline.

The result is matrix arithmetic ONLY. It does not establish a reviewed turn,
player heading, camera yaw, input delivery, live freshness, or restart recovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.physical_rift import _native_values, _utc_tick_order_key
from scripts.project_xyz_track import _pairs

MAX_FILE_BYTES = 2_000_000
CONTRACTS = {
    "native-current-orientation-candidate/1": "orientation",
    "native-current-orientation-candidate-burst/1": "orientation",
    "native-current-actor-pose-candidate/1": "actor-pose",
    "native-current-actor-pose-candidate-burst/1": "actor-pose",
}
SOURCE_NAMES = {
    "orientation": (("primary", "primary"), ("secondary", "secondary")),
    "actor-pose": (("actor", "actorMatrix"), ("model", "modelMatrix"),
                   ("render", "renderMatrix")),
}
HEX = re.compile(r"[0-9a-fA-F]{64}\Z")


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _utc(value):
    try:
        _require(type(value) is str and len(value) <= 48, "invalid-capture-time")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(result.utcoffset() == timedelta(0), "invalid-capture-time")
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid-capture-time") from exc


def _angle_delta(before, after):
    if before is None or after is None:
        return None
    delta = (after - before + 180.0) % 360.0 - 180.0
    return None if abs(delta) == 180.0 else delta


def _matrix(value, *, allow_absent=False):
    if value is None and allow_absent:
        return None
    _require(isinstance(value, dict), "invalid-turn-matrix")
    bits, floats = value.get("rawBits"), value.get("rowMajorF32")
    _require(isinstance(bits, list) and len(bits) == 9
             and all(type(b) is int and 0 <= b <= 0xFFFFFFFF for b in bits)
             and isinstance(floats, list) and len(floats) == 9,
             "invalid-turn-matrix")
    for bit, v in zip(bits, floats):
        _require(type(v) in (int, float) and math.isfinite(v),
                 "invalid-turn-matrix")
        try:
            actual = struct.unpack("<I", struct.pack("<f", v))[0]
        except (ValueError, OverflowError, struct.error) as exc:
            raise ValueError("invalid-turn-matrix") from exc
        _require(actual == bit, "turn-matrix-raw-bits-mismatch")
    status = value.get("status")
    angle = value.get("planarAngleDegreesCandidate")
    if status == "structural-y-planar-matrix-candidate":
        _require(type(angle) in (int, float) and math.isfinite(angle)
                 and -180 <= angle <= 180, "invalid-turn-angle")
        derived = math.degrees(math.atan2(floats[6], floats[0]))
        _require(abs((angle - derived + 180) % 360 - 180) <= .001,
                 "turn-angle-matrix-mismatch")
    else:
        _require(angle is None, "unqualified-turn-matrix-angle")
    return {"bits": bits, "angle": angle, "status": status}


def _load(path):
    path = Path(path)
    _require(not path.is_symlink() and path.is_file()
             and 0 < path.stat().st_size <= MAX_FILE_BYTES,
             "turn-source-missing-or-oversized")
    raw = path.read_bytes()
    _require(0 < len(raw) <= MAX_FILE_BYTES, "turn-source-oversized")
    report = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            ValueError("nonfinite-turn-source")))
    _require(isinstance(report, dict) and report.get("schemaVersion") == 1
             and report.get("status") == "complete"
             and report.get("contractVersion") in CONTRACTS,
             "invalid-physical-turn-contract")
    kind = CONTRACTS[report["contractVersion"]]
    observation = report.get("observation")
    ident = report.get("identity")
    if ident is None and isinstance(observation, dict):
        ident = observation.get("identity")
    _require(isinstance(ident, dict), "invalid-physical-turn-identity")
    if report["contractVersion"].endswith("-candidate-burst/1"):
        _require(report.get("identity") == ident,
                 "invalid-physical-turn-identity")
    _require(type(ident.get("processId")) is int and ident["processId"] > 0
             and type(ident.get("processStartUtcTicks")) is int
             and ident["processStartUtcTicks"] > 0
             and type(ident.get("moduleBaseAddress")) is int
             and ident["moduleBaseAddress"] > 0
             and type(ident.get("moduleSize")) is int and ident["moduleSize"] > 0
             and isinstance(ident.get("executablePath"), str)
             and ident["executablePath"].lower().endswith("rift_x64.exe")
             and isinstance(ident.get("executableSha256"), str)
             and HEX.fullmatch(ident["executableSha256"]),
             "invalid-physical-turn-identity")
    rows = report.get("observations")
    if rows is None:
        _require(report["contractVersion"].endswith("-candidate/1")
                 and isinstance(report.get("observation"), dict),
                 "invalid-physical-turn-count")
        rows = [report["observation"]]
    else:
        _require(report["contractVersion"].endswith("-candidate-burst/1")
                 and isinstance(rows, list) and 2 <= len(rows) <= 30
                 and type(report.get("requestedSamples")) is int
                 and type(report.get("completedSamples")) is int
                 and len(rows) == report["requestedSamples"] == report["completedSamples"]
                 and rows[-1] == report.get("observation"),
                 "invalid-physical-turn-count")
    _require(all(isinstance(r, dict) and r.get("identity") == ident
                 for r in rows), "turn-process-epoch-changed")
    if kind == "orientation":
        key_field, components = "unitKey", ("componentAddress",)
    else:
        key_field, components = "playerKeyDecimal", (
            "playerEntityDecimal", "actorComponentDecimal", "positionComponentDecimal")
    key = rows[0].get(key_field)
    _require(isinstance(key, str) and re.fullmatch(r"[1-9][0-9]{0,19}", key)
             and int(key) < 2**64, "invalid-turn-player-key")
    owner = tuple(rows[0].get(field) for field in components)
    for v in owner:
        _require((type(v) is int and v > 0) if kind == "orientation"
                 else (isinstance(v, str) and re.fullmatch(r"[1-9][0-9]{0,19}", v)
                       and int(v) < 2**64), "invalid-turn-component")
    times = []
    exact_times = []
    last_exact_end = None
    for row in rows:
        _require(row.get(key_field) == key
                 and tuple(row.get(field) for field in components) == owner,
                 "turn-player-or-component-changed")
        _require("candidate" in str(row.get("qualification", "")).lower(),
                 "turn-qualification-missing")
        # .NET emits 100 ns timestamps. Preserve its seventh fractional digit
        # when checking rapid bursts; Python datetime truncates to microseconds.
        exact_start = _utc_tick_order_key(row.get("startedAtUtc"))
        exact_end = _utc_tick_order_key(row.get("completedAtUtc"))
        _require(exact_start <= exact_end
                 and (last_exact_end is None or exact_start > last_exact_end),
                 "turn-capture-time-order-invalid")
        last_exact_end = exact_end
        exact_times.append((exact_start, exact_end))
        times.append((exact_start[0], exact_end[0]))
    # Reuse the production physical projection's burst/owner/bit guards.
    bracketed = (kind == "actor-pose" and
                 all(row.get("positionBracketCandidate") is not None for row in rows))
    _native_values(kind, report, expect_position=bracketed)
    matrices = []
    for row in rows:
        matrices.append({
            name: _matrix(row.get(field), allow_absent=(name == "render"))
            for name, field in SOURCE_NAMES[kind]
        })
    return {"identity": ident, "kind": kind, "key": key, "owner": owner,
            "times": times, "exactTimes": exact_times, "matrices": matrices, "sha256": hashlib.sha256(raw).hexdigest().upper(),
            "samples": len(rows)}


def burst_stability(capture, matrix_name):
    angles = [row[matrix_name]["angle"] if row[matrix_name] else None
              for row in capture["matrices"]]
    duration = (capture["times"][-1][1] - capture["times"][0][0]).total_seconds()
    starts = [start for start, _ in capture["times"]]
    intervals = [(later - earlier).total_seconds() for earlier, later in zip(starts, starts[1:])]
    max_interval = max(intervals, default=None)
    sample_span = (starts[-1] - starts[0]).total_seconds()
    span = None
    if all(angle is not None for angle in angles):
        # Smallest circular arc containing every sample, including wrap at +/-180.
        ordered = sorted(angle % 360 for angle in angles)
        gaps = [b - a for a, b in zip(ordered, ordered[1:])]
        gaps.append(ordered[0] + 360 - ordered[-1])
        span = round(360 - max(gaps), 12)
    return {
        "samples": len(angles),
        "observationSeconds": duration,
        "maximumSampleIntervalSeconds": max_interval,
        "angularSpanDegreesCandidate": span,
        "sampledPoseStableCandidate": (len(angles) >= 3 and sample_span >= .2
                                       and max_interval is not None and max_interval <= .25
                                       and span is not None and span < .01),
        "qualification": "Stability during sampled interval only; later settling and body yaw unverified.",
    }


def compare(before_path, after_path, *, max_gap_seconds=120.0):
    _require(type(max_gap_seconds) in (int, float) and math.isfinite(max_gap_seconds)
             and 0 < max_gap_seconds <= 3600, "invalid-turn-gap-limit")
    before, after = _load(before_path), _load(after_path)
    _require(before["sha256"] != after["sha256"], "turn-identical-sources")
    _require(before["kind"] == after["kind"], "turn-source-kind-mismatch")
    _require(before["identity"] == after["identity"], "turn-process-epoch-changed")
    _require(before["key"] == after["key"] and before["owner"] == after["owner"],
             "turn-player-or-component-changed")
    start, start_remainder = after["exactTimes"][0][0]
    end, end_remainder = before["exactTimes"][-1][1]
    elapsed = start - end
    micros = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    gap = (micros * 10 + start_remainder - end_remainder) / 10_000_000
    _require(gap > 0, "turn-capture-time-order-invalid")
    _require(gap <= max_gap_seconds, "turn-capture-gap-exceeded")
    first, next_start, next_end = (before["matrices"][-1],
                                   after["matrices"][0], after["matrices"][-1])
    changes = {}
    for name, _ in SOURCE_NAMES[before["kind"]]:
        old, start, end = first[name], next_start[name], next_end[name]
        old_angle = old["angle"] if old else None
        start_angle = start["angle"] if start else None
        end_angle = end["angle"] if end else None
        changes[name] = {
            "beforeBurstStability": burst_stability(before, name),
            "afterBurstStability": burst_stability(after, name),
            "beforeEndDegreesCandidate": old_angle,
            "afterStartDegreesCandidate": start_angle,
            "afterEndDegreesCandidate": end_angle,
            "toAfterStartDeltaDegreesCandidate": _angle_delta(old_angle, start_angle),
            "toAfterEndDeltaDegreesCandidate": _angle_delta(old_angle, end_angle),
            "rawBitsChangedAtAfterStart": (old["bits"] != start["bits"]
                                           if old and start else None),
            "rawBitsChangedAtAfterEnd": (old["bits"] != end["bits"]
                                         if old and end else None),
            "beforeStatus": old["status"] if old else None,
            "afterStatus": end["status"] if end else None,
        }
    return {
        "schemaVersion": 1,
        "contractVersion": "physical-native-turn-pair-candidate/1",
        "status": "candidate-only",
        "sourceKind": before["kind"],
        "processIdentity": dict(before["identity"],
                                processStartUtcTicks=str(before["identity"]["processStartUtcTicks"])),
        "playerKey": before["key"],
        "componentIdentity": list(before["owner"]),
        "beforeSourceSha256": before["sha256"],
        "afterSourceSha256": after["sha256"],
        "beforeSamples": before["samples"],
        "afterSamples": after["samples"],
        "captureGapSeconds": gap,
        "matrixComparisons": changes,
        "actorHeadingQualified": False,
        "cameraYawQualified": False,
        "inputResponseVerified": False,
        "freshness": "unavailable-offline",
        "qualification": "raw-matrix-angle-arithmetic-only; physical player-facing and camera yaw unqualified",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=120.0)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(compare(args.before, args.after,
                                 max_gap_seconds=args.max_gap_seconds),
                         sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            OverflowError, RecursionError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[a-z0-9-]{1,100}", reason):
            reason = "physical-turn-pair-unavailable"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
