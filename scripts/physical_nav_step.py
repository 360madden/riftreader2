#!/usr/bin/env python3
"""Offline next pulse from retained native before/after feedback.

No live input, freshness, delivery or arrival proof is provided.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_pulse_feedback as feedback
from scripts import physical_waypoint_decision as waypoint
from scripts.movement_controller import MovementHalted

# Match the existing movement controller's minimum useful progress.
MINIMUM_PROGRESS = 0.03


def next_step(before: Path, after: Path, catalog: Path, anchor_id: str,
              w_calibration: Path | None, q_calibration: Path | None,
              *, max_gap_seconds: float = 10.0) -> dict:
    measured = feedback.compare(before, after, catalog, anchor_id,
                                max_gap_seconds=max_gap_seconds)
    result = {
        "schemaVersion": 1,
        "status": "offline-physical-nav-step-candidate",
        "movementEligible": False,
        "actionVerified": False,
        "arrivalQualified": False,
        "worldInstanceMatched": False,
        "feedback": measured,
        "candidateAction": None,
    }
    if measured["planarProgressCandidate"] < MINIMUM_PROGRESS:
        return {**result, "decision": "stop", "reason": "insufficient-measured-progress"}

    if w_calibration is None:
        return {**result, "decision": "stop", "reason": "w-calibration-required-for-steering"}
    if q_calibration is None:
        return {**result, "decision": "stop", "reason": "q-calibration-required-for-steering"}

    try:
        plan = waypoint.decide(after, catalog, anchor_id, w_calibration, q_calibration)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError, MovementHalted) as error:
        return {**result, "decision": "stop", "reason": "waypoint-decision-unavailable",
                "detail": str(error)}
    # Both computations must use the same bytes and target, even if files change
    # between the separate offline readers.
    if (plan["nativeReportSha256"] != measured["afterReportSha256"]
            or plan["anchorId"] != measured["anchorId"]
            or plan["anchorXYZ"] != measured["anchorXYZ"]):
        raise ValueError("feedback and decision evidence changed")
    return {**result, "decision": plan["decision"],
            "candidateAction": plan["candidateAction"], "waypointDecision": plan}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--anchor-id", required=True)
    parser.add_argument("--w-calibration", type=Path, help="required to recommend steering")
    parser.add_argument("--q-calibration", type=Path, help="required to recommend steering")
    parser.add_argument("--max-gap-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        result = next_step(args.before, args.after, args.catalog, args.anchor_id,
                           args.w_calibration, args.q_calibration,
                           max_gap_seconds=args.max_gap_seconds)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError, MovementHalted) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
