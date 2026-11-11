#!/usr/bin/env python3
"""Compare two retained physical native XYZ bursts against one named anchor.

OFFLINE candidate arithmetic only; no input, control authority, or arrival proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import navigation_anchors as anchors
from scripts import physical_route_preview as route
from scripts.movement_controller import Position, planar_distance


class PhysicalPulseFeedbackError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PhysicalPulseFeedbackError(reason)


def compare(before_path: Path, after_path: Path, catalog_path: Path, anchor_id: str,
            *, max_gap_seconds: float = 10.0) -> dict:
    require(type(max_gap_seconds) in (int, float) and math.isfinite(max_gap_seconds)
            and 0 < max_gap_seconds <= 120, "physical pulse gap bound invalid")
    before, before_sha = route._read_native(before_path)
    after, after_sha = route._read_native(after_path)
    require(before_sha != after_sha, "pulse before/after reports must be independent")
    require(before["identity"] == after["identity"], "pulse process/build epoch changed")
    require(before["unitKey"] == after["unitKey"], "pulse player key changed")
    try:
        before_end = datetime.fromisoformat(before["lastSampleUtc"].replace("Z", "+00:00"))
        after_start = datetime.fromisoformat(after["firstSampleUtc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise PhysicalPulseFeedbackError("pulse capture time invalid") from error
    gap = (after_start - before_end).total_seconds()
    require(before_end.utcoffset() == timedelta(0)
            and after_start.utcoffset() == timedelta(0)
            and 0 < gap <= max_gap_seconds, "pulse capture time overlap or gap exceeded")

    catalog = anchors.load_catalog(catalog_path)
    chosen = anchors.resolve_anchor(catalog, anchor_id)["anchor"]
    identity = before["identity"]
    require(chosen["source"]["gameBuildSha256"].casefold()
            == identity["executableSha256"].casefold(),
            "pulse anchor and native samples use different game builds")
    start, end = before["positions"][-1], after["positions"][-1]
    destination = Position(**chosen["position"])
    displacement = Position(end.x - start.x, end.y - start.y, end.z - start.z)
    horizontal = math.hypot(displacement.x, displacement.z)
    distance_before = planar_distance(start, destination)
    distance_after = planar_distance(end, destination)
    progress = distance_before - distance_after
    require(all(math.isfinite(value) for value in (
            displacement.x, displacement.y, displacement.z, horizontal,
            distance_before, distance_after, progress)),
            "pulse movement metrics nonfinite")
    direction = ("toward-anchor-candidate" if progress > 1e-6 else
                 "away-from-anchor-candidate" if progress < -1e-6 else
                 "no-distance-change-candidate")
    return {
        "schemaVersion": 1,
        "status": "offline-physical-pulse-feedback-candidate",
        "movementEligible": False,
        "actionVerified": False,
        "arrivalQualified": False,
        "worldInstanceMatched": False,
        "direction": direction,
        "anchorId": chosen["id"],
        "anchorXYZ": chosen["position"],
        "beforeXYZ": {"x": start.x, "y": start.y, "z": start.z},
        "afterXYZ": {"x": end.x, "y": end.y, "z": end.z},
        "deltaXYZ": {"x": displacement.x, "y": displacement.y, "z": displacement.z},
        "horizontalDisplacementCandidate": horizontal,
        "planarDistanceBeforeCandidate": distance_before,
        "planarDistanceAfterCandidate": distance_after,
        "planarProgressCandidate": progress,
        "captureGapSeconds": gap,
        "beforeSampleCount": before["sampleCount"],
        "afterSampleCount": after["sampleCount"],
        "unitKey": before["unitKey"],
        "processId": identity["processId"],
        "processStartUtcTicks": str(identity["processStartUtcTicks"]),
        "gameBuildSha256": identity["executableSha256"].upper(),
        "beforeReportSha256": before_sha,
        "afterReportSha256": after_sha,
        "limitations": [
            "Native positions are cached candidates; no independent action or freshness proof.",
            "Anchor game build match does not prove same zone or world instance.",
            "Progress is planar X/Z arithmetic only; this does not prove arrival or authorize input.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--anchor-id", required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        result = compare(args.before, args.after, args.catalog, args.anchor_id,
                         max_gap_seconds=args.max_gap_seconds)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
