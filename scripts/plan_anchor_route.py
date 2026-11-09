#!/usr/bin/env python3
"""Select the next named destination in an offline, ordered RR2 anchor route.

This produces suggestions only. No saved anchor, route checkpoint, or
calibration file authorizes live movement or proves current world identity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import navigation_anchors as anchors
from scripts import plan_steered_waypoint as steering


def plan_route(current_path: Path, catalog_path: Path, route_ids: list[str],
               completed_ids: list[str] | None = None,
               turn_paths: list[Path] | None = None,
               after_turn_path: Path | None = None) -> dict:
    catalog = anchors.load_catalog(catalog_path)
    completed_ids = completed_ids or []
    turn_paths = turn_paths or []
    steering.require(1 <= len(route_ids) <= anchors.MAX_ANCHORS,
                     "route must contain between 1 and 256 anchors")
    lookup = {item["id"].casefold(): item for item in catalog["anchors"]}
    normalized = []
    seen = set()
    for requested in route_ids:
        steering.require(isinstance(requested, str)
                         and anchors.ANCHOR_ID.fullmatch(requested) is not None,
                         "route anchor ID is invalid")
        folded = requested.casefold()
        steering.require(folded not in seen, "route contains duplicate anchor ID")
        steering.require(folded in lookup, "route anchor not found")
        seen.add(folded)
        normalized.append(lookup[folded]["id"])
    steering.require(len(completed_ids) <= len(normalized), "too many completed anchors")
    for index, completed in enumerate(completed_ids):
        steering.require(isinstance(completed, str)
                         and completed.casefold() == normalized[index].casefold(),
                         "completed anchors must be an ordered route prefix")

    current_value, current_hash = steering.load(current_path)
    current = steering.calibration(current_value)
    build = current["identity"]["target"]["executableSha256"]
    for selected in normalized:
        steering.require(lookup[selected.casefold()]["source"]["gameBuildSha256"] == build,
                         "route anchor game build differs from calibration")

    def response(decision: str, arrived_now: list[str], next_index: int,
                 step: dict | None = None) -> dict:
        return {
            "schemaVersion": 1,
            "evidenceKind": "saved-anchor-route-next/1",
            "status": "offline-reference-only",
            "movementEligible": False,
            "decision": decision,
            "coordinateFrame": anchors.COORDINATE_FRAME,
            "currentCalibrationSha256": current_hash,
            "routeAnchorIds": normalized,
            "declaredCompletedIds": normalized[:len(completed_ids)],
            "withinToleranceNowIds": arrived_now,
            "nextIndex": next_index if next_index < len(normalized) else None,
            "nextAnchorId": normalized[next_index] if next_index < len(normalized) else None,
            "step": step,
            "nextRequiredForMovement": (
                "independently verify current-world compatibility and fresh same-session "
                "position; obtain separate reviewed movement authorization"),
            "limitations": (
                "Declared checkpoints are operator-provided, not verified arrival receipts; "
                "the present calibration only supports planar X/Z tolerance."
            ),
        }

    arrived_now = []
    for index in range(len(completed_ids), len(normalized)):
        step = steering.next_step_saved_anchor(
            current_path, catalog_path, normalized[index], turn_paths, after_turn_path)
        if step["decision"] == "arrived":
            arrived_now.append(normalized[index])
            continue
        return response(step["decision"], arrived_now, index, step)
    return response("within-tolerance-or-declared-complete", arrived_now, len(normalized))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--current-w-calibration", type=Path, required=True)
    parser.add_argument("--anchor", action="append", required=True,
                        help="ordered destination ID; repeat for each stop")
    parser.add_argument("--completed-anchor", action="append", default=[],
                        help="operator-declared completed prefix, in order")
    parser.add_argument("--turn-calibration", type=Path, action="append", default=[])
    parser.add_argument("--after-turn-result", type=Path)
    parser.add_argument("--output", type=Path, help="optional new JSON output path")
    args = parser.parse_args(argv)
    try:
        plan = plan_route(args.current_w_calibration, args.catalog, args.anchor,
                          args.completed_anchor, args.turn_calibration, args.after_turn_result)
        if args.output:
            steering.save(args.output, plan)
        print(json.dumps(plan, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
