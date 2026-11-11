#!/usr/bin/env python3
"""Calculate an OFFLINE candidate A/D matrix-angle rate from two physical RIFT captures.

A declared key and hold are not evidence of input delivery, body yaw, or camera yaw.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_physical_turn_pair as turn


class PhysicalTurnRateError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PhysicalTurnRateError(reason)


def calibrate(before: Path, after: Path, *, key: str, hold_ms: int,
              matrix_source: str, max_gap_seconds: float = 5.0) -> dict:
    require(key in ("a", "d"), "declared turn key must be a or d")
    require(type(hold_ms) is int and 20 <= hold_ms <= 150,
            "declared turn hold must be 20..150ms")
    require(type(max_gap_seconds) in (int, float) and
            math.isfinite(max_gap_seconds) and 0 < max_gap_seconds <= 30,
            "turn capture gap limit invalid")
    compared = turn.compare(before, after, max_gap_seconds=max_gap_seconds)
    allowed = ("primary", "secondary") if compared["sourceKind"] == "orientation" else (
        "actor", "model", "render")
    require(matrix_source in allowed, "matrix source does not match physical report kind")
    candidate = compared["matrixComparisons"][matrix_source]
    start_delta = candidate["toAfterStartDeltaDegreesCandidate"]
    end_delta = candidate["toAfterEndDeltaDegreesCandidate"]
    require(type(start_delta) in (int, float) and
            type(end_delta) in (int, float) and
            math.isfinite(start_delta) and math.isfinite(end_delta),
            "turn angle unavailable or ambiguous 180-degree alias")
    require(candidate["rawBitsChangedAtAfterEnd"] in (True, False),
            "turn matrix raw bit comparison unavailable")
    return {
        "schemaVersion": 1,
        "status": "offline-physical-yaw-rate-candidate",
        "movementEligible": False,
        "turnResponseVerified": False,
        "actorHeadingQualified": False,
        "cameraYawQualified": False,
        "key": key,
        "declaredHoldMilliseconds": hold_ms,
        "holdTimingSource": "declared-only-unverified",
        "sourceKind": compared["sourceKind"],
        "matrixSource": matrix_source,
        "matrixAxis": "structural-y-planar-candidate-not-proven-player-or-camera-yaw",
        "beforeEndDegreesCandidate": candidate["beforeEndDegreesCandidate"],
        "afterStartDegreesCandidate": candidate["afterStartDegreesCandidate"],
        "afterEndDegreesCandidate": candidate["afterEndDegreesCandidate"],
        "toAfterStartDeltaDegreesCandidate": start_delta,
        "toAfterEndDeltaDegreesCandidate": end_delta,
        "signedDegreesPerDeclaredMillisecondCandidate": end_delta / hold_ms,
        "rawBitsChangedAtAfterEnd": candidate["rawBitsChangedAtAfterEnd"],
        "captureGapSeconds": compared["captureGapSeconds"],
        "processIdentity": compared["processIdentity"],
        "playerKey": compared["playerKey"],
        "componentIdentity": compared["componentIdentity"],
        "beforeSourceSha256": compared["beforeSourceSha256"],
        "afterSourceSha256": compared["afterSourceSha256"],
        "limitations": [
            "Angle is shortest signed raw matrix-axis difference; rotations above 180 degrees alias.",
            "Declared key/hold are not verified key-down/up timing or proof that the key caused the angle change.",
            "Body facing, camera yaw, source freshness and restart durability remain unqualified.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--key", choices=("a", "d"), required=True)
    parser.add_argument("--hold-ms", type=int, required=True)
    parser.add_argument("--matrix-source", choices=(
        "primary", "secondary", "actor", "model", "render"), required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        result = calibrate(args.before, args.after, key=args.key,
                           hold_ms=args.hold_ms, matrix_source=args.matrix_source,
                           max_gap_seconds=args.max_gap_seconds)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            OverflowError, RecursionError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
