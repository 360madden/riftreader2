#!/usr/bin/env python3
"""Compare one bounded waypoint prediction with an already completed helper receipt.

OFFLINE feedback only. No game access, keypress, approval, arrival, or heading proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_move_basis_waypoint as waypoint
from scripts import physical_move_key_calibration as calibration
from scripts import physical_route_preview as route
from scripts.movement_controller import MovementError, MovementHalted, Position, WaypointController


def require(value, reason):
    if not value:
        raise ValueError(reason)


def utc(raw):
    require(isinstance(raw, str), "feedback-time-invalid")
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("feedback-time-invalid") from error
    require(result.utcoffset() == timedelta(0), "feedback-time-invalid")
    return result


def compare(basis_path: Path, position_path: Path, goal_x: float,
            goal_z: float, receipt_path: Path, goal_y: float | None = None,
            *, post_position_path: Path | None = None) -> dict:
    # Recompute the plan from its exact two saved sources. Do not trust a
    # free-standing "suggested action" text field or execute anything.
    proposed = waypoint.preview(basis_path, position_path, goal_x, goal_z, goal_y)
    action = proposed["candidateAction"]
    require(action is not None and proposed["decision"] == "suggested-one-pulse",
            "feedback-no-proposed-action")

    imported = calibration.from_helper_receipt(receipt_path)
    require(imported["key"] == action["key"]
            and imported["requestedHoldMilliseconds"] == action["holdMilliseconds"],
            "feedback-command-mismatch")
    ident = proposed["identity"]
    require(imported["machine"] == ident["machine"]
            and imported["processId"] == ident["processId"]
            and imported["processStartUtcTicks"] == ident["processStartUtcTicks"]
            and imported["gameBuildSha256"].upper() == ident["gameBuildSha256"].upper()
            and imported["unitKey"] == ident["unitKey"],
            "feedback-target-mismatch")

    native, native_hash = route._read_native(position_path)
    require(native_hash == proposed["nativePositionReportSha256"],
            "feedback-position-source-changed")
    raw = Path(receipt_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest().upper() == imported["sourceReceiptSha256"],
            "feedback-receipt-source-changed")
    from json import loads
    receipt = loads(raw.decode("utf-8-sig"), object_pairs_hook=calibration.unique_pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("feedback-nonfinite-json")))
    before = receipt["xyzFeedback"]["beforeXYZ"]
    after = receipt["xyzFeedback"]["afterXYZ"]
    before_at = utc(before["startedAtUtc"])
    position_at = utc(native["lastSampleUtc"])
    delay = (before_at - position_at).total_seconds()
    require(0 < delay <= 20, "feedback-stale-or-overlapping-position")

    start = proposed["currentXYZ"]
    actual_before = {axis: float(before[axis]) for axis in ("x", "y", "z")}
    actual_after = {axis: float(after[axis]) for axis in ("x", "y", "z")}
    after_for_controller = actual_after
    post_source_sha = None
    post_gap_seconds = None
    post_position_candidate = None
    post_observation_end = utc(after["completedAtUtc"])
    if post_position_path is not None:
        post_native, post_source_sha = route._read_native(Path(post_position_path))
        require(post_source_sha != native_hash
                and post_source_sha != imported["sourceReceiptSha256"],
                "feedback-post-source-not-independent")
        require(post_native["identity"] == native["identity"]
                and post_native["unitKey"] == native["unitKey"],
                "feedback-post-owner-changed")
        post_gap_seconds = (utc(post_native["firstSampleUtc"]) - post_observation_end).total_seconds()
        require(0 < post_gap_seconds <= 5,
                "feedback-post-capture-gap-invalid")
        require(post_native["sampleCount"] >= 2,
                "feedback-post-insufficient-samples")
        post_burst_seconds = (utc(post_native["lastSampleUtc"])
                              - utc(post_native["firstSampleUtc"])).total_seconds()
        require(0 <= post_burst_seconds <= 2,
                "feedback-post-burst-too-long")
        last_post = post_native["positions"][-1]
        require(all(math.hypot(last_post.x - sample.x, last_post.z - sample.z) <= .05
                        and abs(last_post.y - sample.y) <= .10
                    for sample in post_native["positions"]),
                "feedback-post-capture-not-stationary")
        post_position_candidate = {"x": last_post.x, "y": last_post.y, "z": last_post.z}
        difference = math.hypot(last_post.x - actual_after["x"],
                                last_post.z - actual_after["z"])
        require(difference <= .05 and abs(last_post.y - actual_after["y"]) <= .10,
                "feedback-post-disagrees-with-helper")
        after_for_controller = post_position_candidate
        post_observation_end = utc(post_native["lastSampleUtc"])
    mismatch = math.sqrt(sum((actual_before[k] - start[k]) ** 2 for k in ("x", "y", "z")))
    require(math.isfinite(mismatch) and mismatch <= .05,
            "feedback-unexpected-start-position")

    hold = action["holdMilliseconds"]
    observed_hold = imported["observedHoldMilliseconds"]
    predicted = action["predictedDeltaXYZCandidate"]
    scaled = {axis: float(predicted[axis]) * observed_hold / hold for axis in ("x", "y", "z")}
    actual = {axis: actual_after[axis] - actual_before[axis] for axis in ("x", "y", "z")}
    error_x = actual["x"] - scaled["x"]
    error_z = actual["z"] - scaled["z"]
    prediction_error = math.hypot(error_x, error_z)
    expected_norm = math.hypot(scaled["x"], scaled["z"])
    actual_norm = math.hypot(actual["x"], actual["z"])
    require(all(math.isfinite(x) for x in (prediction_error, expected_norm, actual_norm)),
            "feedback-nonfinite-motion")
    tolerance = max(.15, expected_norm * .25)
    consistent = prediction_error <= tolerance
    goal = proposed["goalXYZ"]
    before_distance = math.hypot(goal["x"] - actual_before["x"], goal["z"] - actual_before["z"])
    after_distance = math.hypot(goal["x"] - after_for_controller["x"],
                                goal["z"] - after_for_controller["z"])
    progress = before_distance - after_distance

    # Replay the same bounded controller state against the observed candidate
    # instead of creating a second steering algorithm or refreshing its budget.
    next_status = "stop-divergent-feedback"
    next_action = None
    controller_status = "not-replayed"
    if consistent and progress < .03:
        next_status = "stop-insufficient-progress"
    elif consistent:
        b, basis_sha = waypoint.read_basis(basis_path)
        require(basis_sha == proposed["basisReportSha256"],
                "feedback-basis-source-changed")
        calibrations, vectors = waypoint.candidate_calibrations(b)
        controller = WaypointController(calibrations, Position(**start), Position(**goal))
        first = controller.decide(Position(**start), 0.0)
        require(first is not None and first.key == action["key"]
                and first.hold_ms == action["holdMilliseconds"],
                "feedback-proposed-controller-mismatch")
        # Charge observed key-down duration to the remaining hold budget.
        controller.total_hold_ms = max(controller.total_hold_ms,
                                       int(math.ceil(observed_hold)))
        elapsed = (post_observation_end - utc(native["firstSampleUtc"])).total_seconds()
        require(0 < elapsed <= controller.max_elapsed_seconds,
                "feedback-controller-elapsed-budget")
        after_position = Position(**after_for_controller)
        try:
            report = controller.record_feedback(after_position, elapsed)
            controller_status = report.status
            if report.status == "confirming-arrival":
                next_status = "requires-independent-arrival-settle"
            elif report.status == "active":
                following = controller.decide(after_position, elapsed)
                if following is None:
                    next_status = "requires-independent-arrival-settle"
                else:
                    vx, vz = vectors[following.key]
                    predicted_dx = vx * following.hold_ms
                    predicted_dz = vz * following.hold_ms
                    next_action = {
                        "key": following.key, "holdMilliseconds": following.hold_ms,
                        "predictedBeforeDistanceCandidate": following.distance_before,
                        "predictedAfterDistanceCandidate": following.predicted_distance_after,
                        "predictedDeltaXYZCandidate": {"x": predicted_dx, "y": 0.0, "z": predicted_dz},
                        "predictedAfterXYZCandidate": {
                            "x": after_for_controller["x"] + predicted_dx,
                            "y": after_for_controller["y"],
                            "z": after_for_controller["z"] + predicted_dz,
                        },
                        "inputSent": False, "navigationEligible": False,
                    }
                    next_status = "one-revised-offline-candidate"
            else:
                next_status = "stop-controller-state"
        except (MovementHalted, MovementError) as err:
            controller_status = "halted"
            next_status = "stop-controller-" + str(err)
    return {
        "schemaVersion": 1,
        "status": "offline-physical-waypoint-feedback-candidate",
        "comparison": "candidate-consistent" if consistent else "candidate-divergent",
        "decision": "stop-and-review" if next_status.startswith("stop-") else "observation-only",
        "inputSent": False,
        "navigationEligible": False,
        "gameResponseVerified": False,
        "arrivalQualified": False,
        "sameFacingConfirmed": False,
        "basisReportSha256": proposed["basisReportSha256"],
        "nativePositionReportSha256": native_hash,
        "sourceReceiptSha256": imported["sourceReceiptSha256"],
        "postPositionReportSha256": post_source_sha,
        "postCaptureGapSeconds": post_gap_seconds,
        "postPositionMatchesReceiptCandidate": True if post_source_sha is not None else None,
        "postPositionXYZCandidate": post_position_candidate,
        "key": action["key"],
        "requestedHoldMilliseconds": hold,
        "observedHoldMilliseconds": observed_hold,
        "gapPositionToActionSeconds": delay,
        "startPositionMismatch": mismatch,
        "predictedDeltaForObservedHoldCandidate": scaled,
        "observedDeltaCandidate": actual,
        "planarPredictionErrorCandidate": prediction_error,
        "planarErrorToleranceCandidate": tolerance,
        "predictedPlanarDisplacementCandidate": expected_norm,
        "observedPlanarDisplacementCandidate": actual_norm,
        "distanceBeforeCandidate": before_distance,
        "distanceAfterCandidate": after_distance,
        "progressTowardTargetCandidate": progress,
        "controllerFeedbackStatus": controller_status,
        "nextCandidateStatus": next_status,
        "nextCandidateAction": next_action,
        "limitations": [
            "The saved helper receipt reports Windows input; it is not independent game input-consumption proof.",
            "Native before/after XYZ can be cached; comparison is candidate-only.",
            "Matching source/player and timestamps does not establish facing, zone, world instance or arrival.",
            "No input is sent or automatically repeated; divergence means stop/review.",
            "A revised second step is an offline candidate derived from the same unqualified basis.",
            "In-tolerance feedback requires an independent stationary post-release observation.",
            "Optional separate native post-position burst matches only the same cache reader, not independent gameplay proof.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--basis", type=Path, required=True)
    p.add_argument("--position", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--post-position", type=Path, help="optional separate later native capture file")
    p.add_argument("--target-x", type=float, required=True)
    p.add_argument("--target-z", type=float, required=True)
    p.add_argument("--target-y", type=float)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    try:
        result = compare(a.basis, a.position, a.target_x,
                         a.target_z, a.receipt, a.target_y,
                         post_position_path=a.post_position)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if a.out:
            with a.out.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        print(rendered)
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError) as err:
        print(json.dumps({"status": "blocked", "reason": str(err)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
