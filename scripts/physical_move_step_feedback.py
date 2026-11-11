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
            goal_z: float, receipt_path: Path, goal_y: float | None = None) -> dict:
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
    after_distance = math.hypot(goal["x"] - actual_after["x"], goal["z"] - actual_after["z"])
    return {
        "schemaVersion": 1,
        "status": "offline-physical-waypoint-feedback-candidate",
        "comparison": "candidate-consistent" if consistent else "candidate-divergent",
        "decision": "stop-and-review" if not consistent else "observation-only",
        "inputSent": False,
        "navigationEligible": False,
        "gameResponseVerified": False,
        "arrivalQualified": False,
        "sameFacingConfirmed": False,
        "basisReportSha256": proposed["basisReportSha256"],
        "nativePositionReportSha256": native_hash,
        "sourceReceiptSha256": imported["sourceReceiptSha256"],
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
        "progressTowardTargetCandidate": before_distance - after_distance,
        "limitations": [
            "The saved helper receipt reports Windows input; it is not independent game input-consumption proof.",
            "Native before/after XYZ can be cached; comparison is candidate-only.",
            "Matching source/player and timestamps does not establish facing, zone, world instance or arrival.",
            "No input is sent or automatically repeated; divergence means stop/review.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--basis", type=Path, required=True)
    p.add_argument("--position", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--target-x", type=float, required=True)
    p.add_argument("--target-z", type=float, required=True)
    p.add_argument("--target-y", type=float)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    try:
        result = compare(a.basis, a.position, a.target_x,
                         a.target_z, a.receipt, a.target_y)
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
