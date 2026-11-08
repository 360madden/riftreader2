"""Offline candidate XYZ projection from one retained native sampler report.

No live access. Within-report motion is arithmetic only: unit/world/zone
continuity and source freshness are not established by this report.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
import math
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.xyz_track_reduce import TrackIdentity, TrackSample, reduce_pair

GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
QUALIFICATION = "candidate-only-not-passive-fresh-or-player-semantic-qualified"
MAX_BYTES = 8_000_000


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"invalid {name}")
    try:
        n = float(value)
    except OverflowError:
        raise ValueError(f"invalid {name}") from None
    if not math.isfinite(n):
        raise ValueError(f"invalid {name}")
    return n


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("invalid UTC timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid UTC timestamp") from None
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return stamp


def project(report, *, max_gap_seconds, max_speed_3d):
    """Return a candidate-only single-report track; thresholds have source units."""
    if not isinstance(report, dict):
        raise ValueError("invalid report")
    count = report.get("requestedSamples")
    if (type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1
        or report.get("contractVersion") != "native-current-position-candidate-samples/1"
        or report.get("qualification") != QUALIFICATION or report.get("status") != "complete"
        or report.get("sourceBuildSha256") != GAME_SHA or type(count) is not int or not 1 <= count <= 30
        or type(report.get("completedSamples")) is not int or report["completedSamples"] != count):
        raise ValueError("invalid native sampler contract")
    identity = report.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("missing process identity")
    pid, ticks = identity.get("processId"), identity.get("processStartUtcTicks")
    if (type(pid) is not int or not 0 < pid < 2**31 or type(ticks) is not int or not 0 < ticks < 2**63
        or identity.get("executableSha256") != GAME_SHA):
        raise ValueError("invalid process identity")
    rows = report.get("observations")
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("invalid sample count")
    # Version-1 legacy rows contain none of these; newer rows must contain all
    # three consistently. Numeric JSON keys are forbidden: uint64 needs lossless
    # canonical decimal and an independently checked formatted ID.
    owner_fields = ("unitKey", "unitIdCandidate", "ownerIdentityStatus")
    owner = None
    presence = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid sample sequence")
        flags = tuple(k in row for k in owner_fields)
        if any(flags) and not all(flags):
            raise ValueError("partial sampled unit identity")
        if presence is None:
            presence = all(flags)
        elif presence != all(flags):
            raise ValueError("mixed legacy and unit-identified rows")
        if all(flags):
            key, unit_id, status = (row[k] for k in owner_fields)
            if (not isinstance(key, str) or re.fullmatch(r"[1-9][0-9]{0,19}", key) is None
                or int(key) > 2**64 - 1
                or unit_id != f"u{int(key):016X}"
                or status != "player-component-chain-anchored"):
                raise ValueError("invalid sampled unit identity")
            if owner is None:
                owner = (key, unit_id)
            elif owner != (key, unit_id):
                raise ValueError("sampled unit identity changed")
    gap = _number(max_gap_seconds, "max gap")
    limit = _number(max_speed_3d, "max speed")
    if gap <= 0 or limit <= 0:
        raise ValueError("thresholds must be positive")

    # These tokens delimit this one calculation only: no reported or assumed
    # world, zone, session, or same-player identity is represented by them.
    private_identity = TrackIdentity(pid, ticks, GAME_SHA, "one-report-only", "unknown")
    prior = None
    previous_start = previous_end = previous_utc = None
    points = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or type(row.get("index")) is not int or row["index"] != index:
            raise ValueError("invalid sample sequence")
        start = _number(row.get("monotonicStartMilliseconds"), "monotonic start")
        end = _number(row.get("monotonicEndMilliseconds"), "monotonic end")
        begun, finished = _utc(row.get("startedAtUtc")), _utc(row.get("completedAtUtc"))
        if (start < 0 or end <= start or finished < begun
            or (previous_start is not None and start <= previous_start)
            or (previous_end is not None and start < previous_end)
            or (previous_utc is not None and begun <= previous_utc)):
            raise ValueError("invalid sample timing")
        xyz = tuple(_number(row.get(axis), axis) for axis in ("x", "y", "z"))
        current = TrackSample(*xyz, start / 1000.0, begun, private_identity, "unknown")
        # Monotonic timestamps are Stopwatch offsets, not today's clock.  Passing
        # current time only satisfies reducer arithmetic; its freshness is withheld.
        result = reduce_pair(prior, current, now_monotonic=current.monotonic,
                             stale_after=1, max_gap=gap, max_speed_3d=limit)
        motion = asdict(result)
        motion.pop("fresh")
        motion.pop("age_seconds")
        points.append({"index": index, "startedAtUtc": row["startedAtUtc"],
                       "elapsedStartMilliseconds": start - _number(rows[0]["monotonicStartMilliseconds"], "first start"),
                       "xyz": dict(zip(("x", "y", "z"), xyz)), "reduction": motion})
        prior = current
        previous_start, previous_end, previous_utc = start, end, begun
    return {"schemaVersion": 1, "contractVersion": "native-position-offline-track-candidate/1",
            "status": "candidate-only", "sourceQualification": QUALIFICATION,
            "processIdentity": identity, "freshness": "unavailable-offline",
            "unitIdentity": "same-sampled-unit-key-candidate" if owner else "unavailable-in-source",
            "sampledUnitKey": owner[0] if owner else None,
            "sampledUnitIdCandidate": owner[1] if owner else None,
            "ownerIdentityStatus": "player-component-chain-anchored" if owner else "unavailable-in-source",
            "worldIdentity": "unavailable-in-source",
            "zoneIdentity": "unavailable-in-source", "zoneBoundaries": "undetectable-in-source",
            "coordinateUnits": "unverified", "axes": {"planar": ["x", "z"], "vertical": "y"},
            "thresholds": {"maxGapSeconds": gap, "maxSpeed3dSourceUnitsPerSecond": limit},
            "limitations": ["Sampled key agreement is not proof of uninterrupted ownership, player semantics, or world continuity.",
                            "Zone transitions, source freshness and loaded module identity are unverified.",
                            "Speed-limit boundaries are not proof of teleport."],
            "observations": points}


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, required=True)
    parser.add_argument("--max-speed-3d", type=float, required=True,
                        help="maximum candidate speed in unverified source units per second")
    args = parser.parse_args(argv)
    try:
        with args.report.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("input report exceeds size limit")
        report = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
        result = project(report, max_gap_seconds=args.max_gap_seconds, max_speed_3d=args.max_speed_3d)
        result["sourceSha256"] = hashlib.sha256(data).hexdigest().upper()
        print(json.dumps(result, allow_nan=False))
        return 0
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
