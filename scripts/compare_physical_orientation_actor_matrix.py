#!/usr/bin/env python3
"""Compare two known native matrix access paths from saved physical RIFT captures.

Reports byte-identity candidates, not independent heading/freshness proof.
No process access, desktop capture, gameplay input or VM operations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_physical_turn_pair as turn


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare(orientation_path: Path, pose_path: Path, *, max_gap_seconds: float = 30.0):
    require(type(max_gap_seconds) in (int, float)
            and 0 < max_gap_seconds <= 120, "alias-gap-limit-invalid")
    orientation = turn._load(orientation_path)
    pose = turn._load(pose_path)
    require(orientation["kind"] == "orientation" and pose["kind"] == "actor-pose",
            "alias-source-kind-mismatch")
    require(orientation["identity"] == pose["identity"],
            "alias-process-build-epoch-mismatch")
    require(orientation["key"] == pose["key"],
            "alias-player-mismatch")
    require(str(orientation["owner"][0]) == pose["owner"][2],
            "alias-position-component-mismatch")
    gap = turn.elapsed_seconds(orientation["exactTimes"][-1][1], pose["exactTimes"][0][0])
    require(0 < gap <= max_gap_seconds, "alias-bursts-not-contemporaneous")
    require(orientation["sha256"] != pose["sha256"], "alias-source-not-distinct")

    secondary = [matrix["secondary"] for matrix in orientation["matrices"]]
    primary = [matrix["primary"] for matrix in orientation["matrices"]]
    actor = [matrix["actor"] for matrix in pose["matrices"]]
    require(all(matrix and matrix["angle"] is not None
                for matrix in (*secondary, *primary, *actor)),
            "alias-matrix-unavailable")

    secondary_stable = all(item["bits"] == secondary[0]["bits"] for item in secondary[1:])
    actor_stable = all(item["bits"] == actor[0]["bits"] for item in actor[1:])
    all_identical = (secondary_stable and actor_stable
                     and secondary[-1]["bits"] == actor[0]["bits"])
    mismatches = sum(a != b for a, b in zip(secondary[-1]["bits"], actor[0]["bits"]))
    primary_secondary_degrees = turn._angle_delta(
        primary[-1]["angle"], secondary[-1]["angle"])
    result = {
        "schemaVersion": 1,
        "status": ("stable-separate-captures-same-matrix-bits-candidate" if all_identical
                   else "matrix-copy-not-established-from-captures"),
        "sourceKind": "position-secondary-vs-actor-matrix",
        "targetBuildSha256": orientation["identity"]["executableSha256"].upper(),
        "processId": orientation["identity"]["processId"],
        "processStartUtcTicks": str(orientation["identity"]["processStartUtcTicks"]),
        "playerKey": orientation["key"],
        "positionComponent": str(orientation["owner"][0]),
        "actorComponent": pose["owner"][1],
        "positionSecondaryOffset": "0x94",
        "actorMatrixOffset": "0x398",
        "primaryPositionOffset": "0x60",
        "orientationSamples": orientation["samples"],
        "actorPoseSamples": pose["samples"],
        "captureGapSeconds": gap,
        "positionSecondaryStableWithinBurst": secondary_stable,
        "actorMatrixStableWithinBurst": actor_stable,
        "rawBitsEqualBetweenBursts": all_identical,
        "rawBitElementMismatchCount": mismatches,
        "positionSecondaryAngleDegreesCandidate": secondary[-1]["angle"],
        "actorMatrixAngleDegreesCandidate": actor[0]["angle"],
        "positionPrimaryAngleDegreesCandidate": primary[-1]["angle"],
        "primaryMinusSecondaryDegreesCandidate": (
            None if primary_secondary_degrees is None else -primary_secondary_degrees),
        "orientationSourceSha256": orientation["sha256"],
        "actorPoseSourceSha256": pose["sha256"],
        "actorHeadingQualified": False,
        "independentGameResponseVerified": False,
        "navigationEligible": False,
        "limitations": [
            "Same-value samples are not simultaneous; intervening rotation could break equivalence.",
            "Raw-value agreement between two native paths is not independent body/camera heading proof.",
            "Bit agreement does not prove a shared address, writer identity, or update latency.",
            "No live game input or screenshots were used in this comparison.",
        ],
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orientation", type=Path, required=True)
    parser.add_argument("--actor-pose", type=Path, required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=30.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.orientation, args.actor_pose,
                         max_gap_seconds=args.max_gap_seconds)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        print(rendered)
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            OverflowError, RecursionError) as err:
        print(json.dumps({"status": "blocked", "reason": str(err)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
