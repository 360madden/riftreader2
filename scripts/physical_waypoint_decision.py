#!/usr/bin/env python3
"""One OFFLINE candidate W/Q waypoint pulse from retained physical XYZ and measured displacement.

No live process access, control, freshness claim, route execution, or arrival proof.
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

from scripts import navigation_anchors as anchors
from scripts import physical_calibration as physical_cal
from scripts import physical_route_preview as route
from scripts.movement_controller import (
    MovementError, MovementHalted, Position, WaypointController,
    calibrate_displacement, validate_noncollinear,
)


class PhysicalWaypointError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PhysicalWaypointError(reason)


def _calibration(path: Path, key: str, native: dict) -> tuple[object, str]:
    """Accept the exact candidate output from scripts/physical_calibration.py."""
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 1024 * 1024,
            "calibration report missing, symbolic, or oversized")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8-sig"),
                           object_pairs_hook=anchors._unique_json_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               PhysicalWaypointError("nonfinite calibration JSON")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise PhysicalWaypointError("calibration JSON invalid") from error
    fields = {
        "schemaVersion", "status", "movementEligible", "actionVerified", "qualification",
        "key", "dx_per_ms", "dz_per_ms", "calibration_hold_ms",
        "horizontal_displacement", "vertical_displacement", "processId",
        "processStartUtcTicks", "gameBuildSha256", "unitKey", "beforeReportSha256",
        "afterReportSha256", "beforeSampleUtc", "afterSampleUtc",
    }
    require(isinstance(value, dict) and set(value) == fields
            and type(value["schemaVersion"]) is int and value["schemaVersion"] == 1
            and value["status"] == "offline-physical-calibration-candidate"
            and value["movementEligible"] is False
            and value["actionVerified"] is False
            and value["qualification"] ==
            "nominal-key-hold-and-two-native-position-candidates-only"
            and value["key"] == key, "physical calibration contract invalid")
    identity = native["identity"]
    require(type(value["processId"]) is int and value["processId"] == identity["processId"]
            and isinstance(value["processStartUtcTicks"], str)
            and value["processStartUtcTicks"] == str(identity["processStartUtcTicks"])
            and isinstance(value["gameBuildSha256"], str)
            and value["gameBuildSha256"].casefold() ==
            identity["executableSha256"].casefold()
            and isinstance(value["unitKey"], str)
            and value["unitKey"] == native["unitKey"],
            "calibration game/player/process epoch mismatch")
    require(all(isinstance(value[name], str) and
                anchors.SHA256.fullmatch(value[name]) is not None
                for name in ("beforeReportSha256", "afterReportSha256"))
            and value["beforeReportSha256"].casefold() !=
            value["afterReportSha256"].casefold(), "calibration source evidence invalid")
    try:
        before = datetime.fromisoformat(value["beforeSampleUtc"].replace("Z", "+00:00"))
        after = datetime.fromisoformat(value["afterSampleUtc"].replace("Z", "+00:00"))
        current_start = datetime.fromisoformat(native["firstSampleUtc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise PhysicalWaypointError("calibration sample UTC invalid") from error
    require(before.utcoffset() == timedelta(0) and
            after.utcoffset() == timedelta(0) and
            current_start.utcoffset() == timedelta(0) and
            before < after <= current_start,
            "calibration sample chronology invalid")
    hold = value["calibration_hold_ms"]
    numbers = ("dx_per_ms", "dz_per_ms", "horizontal_displacement",
               "vertical_displacement")
    require(all(type(value[name]) in (int, float) and math.isfinite(value[name])
                for name in numbers), "calibration vector nonfinite")
    dx, dz, vertical = value["dx_per_ms"], value["dz_per_ms"], value["vertical_displacement"]
    require(type(hold) is int and 20 <= hold <= physical_cal.MAX_PHYSICAL_CALIBRATION_HOLD_MS
            and all(math.isfinite(component * hold) for component in (dx, dz)),
            "calibration displacement invalid")
    measured = calibrate_displacement(
        key, Position(0, 0, 0),
        Position(dx * hold, vertical, dz * hold), hold,
        maximum_horizontal=physical_cal.physical_horizontal_limit(hold),
        maximum_calibration_hold_ms=physical_cal.MAX_PHYSICAL_CALIBRATION_HOLD_MS)
    require(math.isclose(measured.horizontal_displacement, value["horizontal_displacement"],
                         rel_tol=1e-6, abs_tol=1e-8), "calibration report magnitude mismatch")
    return measured, hashlib.sha256(raw).hexdigest().upper()


def decide(position_report: Path, catalog: Path, anchor_id: str,
           w_calibration: Path, q_calibration: Path) -> dict:
    # Preview checks build, owner chain, UTC ordering, source hash and finite XYZ
    # and refuses arithmetic overflow. The second read needs the same exact bytes.
    reference = route.preview(position_report, catalog, anchor_id)
    native, source_hash = route._read_native(position_report)
    require(source_hash == reference["nativeReportSha256"],
            "physical position report changed during decision")
    w, w_sha = _calibration(w_calibration, "w", native)
    q, q_sha = _calibration(q_calibration, "q", native)
    measured = {"w": w, "q": q}
    validate_noncollinear(measured)
    current = native["positions"][-1]
    goal = Position(**reference["anchorXYZ"])
    controller = WaypointController(measured, current, goal)
    action = controller.decide(current, 0.0)
    common = {
        "schemaVersion": 1,
        "status": "offline-candidate-decision",
        "movementEligible": False,
        "arrivalQualified": False,
        "headingQualified": False,
        "worldInstanceMatched": False,
        "nextRequired": "independently fresh player XYZ, same-world qualification, exclusive reviewed physical controller and release confirmation",
        "anchorId": reference["anchorId"],
        "candidateCurrentXYZ": reference["candidateCurrentXYZ"],
        "anchorXYZ": reference["anchorXYZ"],
        "planarDistanceCandidate": reference["planarDistanceEndCandidate"],
        "processId": reference["processId"],
        "processStartUtcTicks": reference["processStartUtcTicks"],
        "gameBuildSha256": reference["gameBuildSha256"],
        "unitKey": reference["unitKey"],
        "nativeReportSha256": source_hash,
        "calibrationReportSha256": {"w": w_sha, "q": q_sha},
    }
    if action is None:
        return {**common, "decision": "within-tolerance-candidate",
                "candidateWithinTolerance": True, "candidateAction": None}
    require(all(math.isfinite(value) for value in
                (action.distance_before, action.predicted_distance_after)),
            "nonfinite predicted movement metric")
    return {**common, "decision": "suggested-one-pulse",
            "candidateWithinTolerance": False,
            "candidateAction": {
                "key": action.key,
                "holdMilliseconds": action.hold_ms,
                "distanceBeforeCandidate": action.distance_before,
                "predictedDistanceAfterCandidate": action.predicted_distance_after,
                "predictedProgressCandidate":
                    action.distance_before - action.predicted_distance_after,
            }}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--position-report", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--anchor-id", required=True)
    parser.add_argument("--w-calibration", type=Path, required=True)
    parser.add_argument("--q-calibration", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = decide(args.position_report, args.catalog, args.anchor_id,
                        args.w_calibration, args.q_calibration)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, MovementError, MovementHalted) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
