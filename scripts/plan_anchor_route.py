#!/usr/bin/env python3
"""Select the next named destination in an offline, ordered RR2 anchor route.

This produces suggestions only. No saved anchor, route checkpoint, or
calibration file authorizes live movement or proves current world identity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from . import navigation_anchors as anchors
    from . import plan_steered_waypoint as steering
else:
    import navigation_anchors as anchors
    import plan_steered_waypoint as steering


def plan_route(current_path: Path, catalog_path: Path, route_ids: list[str],
               completed_ids: list[str] | None = None,
               turn_paths: list[Path] | None = None,
               after_turn_path: Path | None = None,
               arrival_result_paths: list[Path] | None = None) -> dict:
    catalog = anchors.load_catalog(catalog_path)
    completed_ids = completed_ids or []
    turn_paths = turn_paths or []
    arrival_result_paths = arrival_result_paths or []
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

    steering.require(not (completed_ids and arrival_result_paths),
                     "choose declared checkpoints or recorded arrivals, not both")
    steering.require(len(arrival_result_paths) <= len(normalized),
                     "too many recorded arrivals")
    recorded = []
    last_sample = None
    for index, path in enumerate(arrival_result_paths):
        receipt, receipt_hash = steering.load(path)
        steering.require(receipt.get("success") is True
                         and receipt.get("mode") == "movement"
                         and receipt.get("status") == "arrived"
                         and type(receipt.get("settles")) is int and receipt["settles"] == 1
                         and type(receipt.get("arrivalObservations")) is int
                         and receipt["arrivalObservations"] == 2
                         and type(receipt.get("feedbackIterations")) is int
                         and receipt["feedbackIterations"] >= 1,
                         "recorded arrival is not a completed released movement")
        observations = receipt.get("samples")
        actions = receipt.get("actionEvidence")
        steering.require(isinstance(observations, list) and len(observations) >= 3
                         and isinstance(actions, list) and len(actions) >= 1,
                         "recorded arrival lacks observations or action evidence")
        for action in actions:
            delivery = action.get("result", {}).get("result", {}) if isinstance(action, dict) else {}
            steering.require(isinstance(delivery, dict)
                             and delivery.get("deliverySucceeded") is True
                             and delivery.get("releaseSucceeded") is True
                             and delivery.get("cancelled") is False
                             and delivery.get("targetLost") is False
                             and delivery.get("stateUncertain") is False
                             and action["result"].get("recoveryRequired") is False,
                             "recorded arrival action was not cleanly released")
        before, after = observations[0], observations[-1]
        steering.require(all(steering.identity(sample) == current["identity"]
                             for sample in observations),
                         "recorded arrival belongs to another source identity")
        steering.advancing(before, after)
        if last_sample is not None:
            steering.advancing(last_sample, before)
        anchor = lookup[normalized[index].casefold()]
        goal = receipt.get("goal")
        steering.require(isinstance(goal, dict) and set(goal) == {"x", "y", "z"},
                         "recorded arrival goal is invalid")
        goal_point = tuple(steering.finite(goal[axis], "arrival goal") for axis in ("x", "y", "z"))
        position = tuple(anchor["position"][axis] for axis in ("x", "y", "z"))
        error = steering.planar(steering.xyz(after), position)
        steering.require(steering.planar(goal_point, position) <= .30 and error <= .30,
                         "recorded arrival does not match route anchor")
        recorded.append({"anchorId": normalized[index],
                         "resultSha256": receipt_hash,
                         "finalPlanarError": error,
                         "lastOuterSequence": after["outerSequence"]})
        last_sample = after
    if last_sample is not None:
        steering.advancing(last_sample, current["samples"][0])
        steering.require(steering.planar(steering.xyz(last_sample), current["start"]) <= .30,
                         "current calibration does not follow recorded route arrival")
    completed_count = len(completed_ids) + len(recorded)

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
            "recordedArrivalIds": [item["anchorId"] for item in recorded],
            "recordedArrivalResults": recorded,
            "withinToleranceAtCalibrationIds": arrived_now,
            "nextIndex": next_index if next_index < len(normalized) else None,
            "nextAnchorId": normalized[next_index] if next_index < len(normalized) else None,
            "step": step,
            "nextRequiredForMovement": (
                "independently verify current-world compatibility and fresh same-session "
                "position; obtain separate reviewed movement authorization"),
            "limitations": (
                "Declared checkpoints are operator-provided; saved arrival receipts "
                "are offline evidence, not current-world proof or movement permission; "
                "this calibration supports only planar X/Z tolerance."
            ),
        }

    arrived_now = []
    for index in range(completed_count, len(normalized)):
        step = steering.next_step_saved_anchor(
            current_path, catalog_path, normalized[index], turn_paths, after_turn_path)
        steering.require(step["currentCalibrationSha256"] == current_hash
                         and step["identity"] == current["identity"],
                         "calibration changed during route planning")
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
    parser.add_argument("--arrival-result", type=Path, action="append", default=[],
                        help="ordered saved arrived movement results; no live authority")
    parser.add_argument("--turn-calibration", type=Path, action="append", default=[])
    parser.add_argument("--after-turn-result", type=Path)
    parser.add_argument("--output", type=Path, help="optional new JSON output path")
    args = parser.parse_args(argv)
    try:
        plan = plan_route(args.current_w_calibration, args.catalog, args.anchor,
                          args.completed_anchor, args.turn_calibration, args.after_turn_result,
                          args.arrival_result)
        if args.output:
            steering.save(args.output, plan)
        print(json.dumps(plan, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
