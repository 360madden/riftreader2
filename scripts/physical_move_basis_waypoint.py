#!/usr/bin/env python3
"""Offline one-step RR2 waypoint preview from a measured physical key basis.

Never sends input. The later-facing strafe vectors are an unverified model;
the output is a candidate calculation, never an executable action approval.
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
from scripts import physical_route_preview as route
from scripts.movement_controller import (
    Calibration, MovementError, MovementHalted, Position,
    WaypointController, validate_noncollinear,
)


class BasisWaypointError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise BasisWaypointError(reason)


def number(v):
    require(type(v) in (int, float) and math.isfinite(v), "waypoint-coordinate-invalid")
    return float(v)


def read_basis(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 1 <= path.stat().st_size <= 262144,
            "waypoint-basis-missing-or-oversized")
    raw = path.read_bytes()
    require(1 <= len(raw) <= 262144, "waypoint-basis-oversized")
    try:
        b = json.loads(raw.decode("utf-8-sig"),
                       object_pairs_hook=anchors._unique_json_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           BasisWaypointError("waypoint-basis-nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as err:
        raise BasisWaypointError("waypoint-basis-invalid") from err
    require(isinstance(b, dict) and b.get("schemaVersion") == 1
            and b.get("status") == "offline-physical-key-basis-candidate"
            and b.get("navigationEligible") is False
            and b.get("movementEligible") is False
            and b.get("headingQualified") is False
            and b.get("sameFacingConfirmed") is False
            and b.get("gameResponseVerified") is False
            and b.get("cardinalGeometryCandidate") is True,
            "waypoint-basis-unqualified")
    model = b.get("laterFacingReprojectionCandidate")
    require(isinstance(model, dict)
            and model.get("status") == "unverified-rigid-rotation-model"
            and model.get("sameFacingConfirmed") is False
            and model.get("navigationEligible") is False
            and isinstance(model.get("modeledVectors"), dict)
            and set(model["modeledVectors"]) == {"s", "q", "e"},
            "waypoint-later-facing-model-unavailable")
    sample = b.get("samples")
    require(isinstance(sample, dict) and set(sample) == {"w", "s", "q", "e", "laterW"},
            "waypoint-basis-samples-invalid")
    sources = b.get("sourceReceiptsSha256")
    require(isinstance(sources, dict) and set(sources) == set(sample)
            and all(isinstance(v, str) and anchors.SHA256.fullmatch(v)
                    for v in sources.values())
            and len(set(sources.values())) == 5, "waypoint-basis-source-hashes-invalid")
    ident = b.get("identity")
    require(isinstance(ident, dict)
            and ident.get("machine") in ("AMD-DESKTOP", "LEGION")
            and type(ident.get("processId")) is int and ident["processId"] > 0
            and isinstance(ident.get("processStartUtcTicks"), str)
            and ident["processStartUtcTicks"].isdecimal()
            and isinstance(ident.get("unitKey"), str)
            and ident["unitKey"].isdecimal()
            and isinstance(ident.get("gameBuildSha256"), str)
            and anchors.SHA256.fullmatch(ident["gameBuildSha256"]),
            "waypoint-basis-identity-invalid")
    return b, hashlib.sha256(raw).hexdigest().upper()


def preview(basis_path, position_path, goal_x, goal_z, goal_y=None):
    b, basis_sha = read_basis(basis_path)
    native, position_sha = route._read_native(Path(position_path))
    ident = b["identity"]
    require(native["identity"]["processId"] == ident["processId"]
            and str(native["identity"]["processStartUtcTicks"]) == ident["processStartUtcTicks"]
            and native["identity"]["executableSha256"].casefold()
            == ident["gameBuildSha256"].casefold()
            and native["unitKey"] == ident["unitKey"],
            "waypoint-native-basis-identity-mismatch")
    try:
        position_at = datetime.fromisoformat(native["firstSampleUtc"].replace("Z", "+00:00"))
        calibration_at = datetime.fromisoformat(
            b["samples"]["laterW"]["afterSampleUtc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as err:
        raise BasisWaypointError("waypoint-sample-time-invalid") from err
    require(position_at.utcoffset() == timedelta(0)
            and calibration_at.utcoffset() == timedelta(0)
            and position_at > calibration_at,
            "waypoint-position-precedes-calibration")
    start = native["positions"][-1]
    goal = Position(number(goal_x), start.y if goal_y is None else number(goal_y),
                    number(goal_z))
    require(abs(goal.y - start.y) <= 1.5, "waypoint-vertical-target-unqualified")
    model = b["laterFacingReprojectionCandidate"]["modeledVectors"]
    later = b["samples"]["laterW"]
    vectors = {"w": (number(later.get("vxCandidate")), number(later.get("vzCandidate")))}
    for key in ("s", "q", "e"):
        row = model[key]
        vectors[key] = (number(row.get("vxPerMillisecondCandidate")),
                        number(row.get("vzPerMillisecondCandidate")))
    # Only speed/direction *candidates*. The Calibration record is used to
    # reuse RR2's pure bounded decision mathematics, not to claim qualification.
    calibrations = {}
    for key, (x, z) in vectors.items():
        require(math.hypot(x, z) > 0, "waypoint-basis-vector-zero")
        # The model's 100ms displacement is a projection, NOT a measured pulse.
        calibrations[key] = Calibration(key, x, z, 100,
                                        math.hypot(x, z) * 100, 0.0)
    validate_noncollinear(calibrations)
    try:
        controller = WaypointController(calibrations, start, goal)
        action = controller.decide(start, 0.0)
    except (MovementError, MovementHalted) as err:
        raise BasisWaypointError(str(err)) from err
    predicted_position = None
    predicted_displacement = None
    if action is not None:
        vx, vz = vectors[action.key]
        predicted_displacement = {
            "x": vx * action.hold_ms, "y": 0.0, "z": vz * action.hold_ms,
        }
        predicted_position = {
            "x": start.x + predicted_displacement["x"],
            "y": start.y,
            "z": start.z + predicted_displacement["z"],
        }
    return {
        "schemaVersion": 1,
        "status": "offline-physical-waypoint-candidate",
        "movementEligible": False,
        "navigationEligible": False,
        "headingQualified": False,
        "worldInstanceMatched": False,
        "arrivalQualified": False,
        "gameResponseVerified": False,
        "inputSent": False,
        "basisReportSha256": basis_sha,
        "nativePositionReportSha256": position_sha,
        "basisLastForwardSampleUtc": b["samples"]["laterW"]["afterSampleUtc"],
        "positionFirstSampleUtc": native["firstSampleUtc"],
        "identity": ident,
        "currentXYZ": {"x": start.x, "y": start.y, "z": start.z},
        "goalXYZ": {"x": goal.x, "y": goal.y, "z": goal.z},
        "candidateAction": None if action is None else {
            "key": action.key, "holdMilliseconds": action.hold_ms,
            "predictedBeforeDistanceCandidate": action.distance_before,
            "predictedAfterDistanceCandidate": action.predicted_distance_after,
            "predictedDeltaXYZCandidate": predicted_displacement,
            "predictedAfterXYZCandidate": predicted_position,
        },
        "decision": "within-tolerance-candidate" if action is None else "suggested-one-pulse",
        "limitations": [
            "Explicit destination does not prove same-world navigation or arrival.",
            "Only forward was observed at the later facing; S/Q/E are modeled rotations.",
            "Current native XYZ is cached candidate data, not independently refreshed gameplay state.",
            "Linear speed scaling to 20-150 ms is unqualified; this never executes input.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--basis", type=Path, required=True)
    p.add_argument("--position", type=Path, required=True)
    p.add_argument("--target-x", type=float, required=True)
    p.add_argument("--target-z", type=float, required=True)
    p.add_argument("--target-y", type=float)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    try:
        result = preview(a.basis, a.position, a.target_x, a.target_z, a.target_y)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if a.out is not None:
            with a.out.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        print(rendered)
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as err:
        print(json.dumps({"status": "blocked", "reason": str(err)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
