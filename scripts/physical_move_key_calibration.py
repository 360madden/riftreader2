#!/usr/bin/env python3
"""Offline physical W/S/Q/E calibration from one retained RR2 move-key JSON receipt.

This reads an already completed helper report; never launches RIFT or sends input.
Candidate vectors are not qualified heading, game consumption, or navigation authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import movement_controller as movement
from scripts import physical_calibration as physical

HEX = re.compile(r"[0-9a-fA-F]{64}\Z")
UNIT = re.compile(r"[1-9][0-9]{0,19}\Z")
MAX_BYTES = 128 * 1024


class HelperCalibrationError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise HelperCalibrationError(reason)


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate-helper-receipt-field")
        obj[key] = value
    return obj


def finite(value, reason):
    require(type(value) in (int, float) and math.isfinite(value), reason)
    return float(value)


def utc(value):
    require(isinstance(value, str) and len(value) <= 48, "invalid-helper-sample-time")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise HelperCalibrationError("invalid-helper-sample-time") from err
    require(stamp.utcoffset() == timedelta(0), "invalid-helper-sample-time")
    return stamp


def forward_pose_comparison(receipt, dx, dz):
    from scripts.analyze_physical_turn_pair import _matrix
    from scripts.physical_rift import _utc_tick_order_key as tick

    pose = receipt.get("poseFeedback")
    if receipt["keys"] != ["w"] or not isinstance(pose, dict) or pose.get("status") != "candidate-native-actor-pose-feedback":
        return None
    xyz = receipt["xyzFeedback"]
    timing = receipt.get("inputCallTiming")
    if not isinstance(timing, dict):
        return None
    angles = []
    owners = []
    intervals = []
    for key in ("beforePose", "afterPose"):
        row = pose.get(key)
        require(isinstance(row, dict), "helper-pose-unavailable")
        ident = row.get("identity")
        require(isinstance(ident, dict) and ident.get("processId") == receipt["processId"]
                and ident.get("processStartUtcTicks") == receipt["processStartUtcTicks"]
                and ident.get("executableSha256") == receipt["executableSha256"]
                and row.get("playerKeyDecimal") == xyz["beforeXYZ"]["unitKey"],
                "helper-pose-owner-mismatch")
        owner = tuple(row.get(k) for k in ("playerEntityDecimal", "actorComponentDecimal",
                                           "positionComponentDecimal"))
        require(all(isinstance(v, str) and UNIT.fullmatch(v) for v in owner),
                "helper-pose-owner-mismatch")
        owners.append(owner)
        matrix = row.get("actorMatrix")
        require(isinstance(matrix, dict) and matrix.get("sourceOffset") == 0x398,
                "helper-actor-matrix-invalid")
        angles.append(_matrix(matrix)["angle"])
        intervals.append((tick(row.get("startedAtUtc")), tick(row.get("completedAtUtc"))))
    require(owners[0] == owners[1], "helper-pose-owner-mismatch")
    require(tick(xyz["beforeXYZ"]["completedAtUtc"]) <= intervals[0][0] <= intervals[0][1]
            <= tick(timing["startedAtUtc"]) and tick(timing["completedAtUtc"])
            <= tick(xyz["afterXYZ"]["startedAtUtc"]) <= tick(xyz["afterXYZ"]["completedAtUtc"])
            <= intervals[1][0] <= intervals[1][1], "helper-pose-timing-mismatch")
    if None in angles or math.hypot(dx, dz) == 0:
        return None
    travel = math.degrees(math.atan2(dx, dz))
    return {"travelDegreesFromPositiveZTowardPositiveX": travel,
            "beforeActorDegrees": angles[0], "afterActorDegrees": angles[1],
            "travelMinusNegatedBeforeActorDegrees": (travel + angles[0] + 180) % 360 - 180,
            "travelMinusNegatedAfterActorDegrees": (travel + angles[1] + 180) % 360 - 180,
            "headingQualified": False}


def from_helper_receipt(path: Path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file()
            and 1 <= path.stat().st_size <= MAX_BYTES,
            "helper-receipt-missing-or-oversized")
    raw = path.read_bytes()
    require(1 <= len(raw) <= MAX_BYTES, "helper-receipt-oversized")
    try:
        receipt = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 HelperCalibrationError("nonfinite-helper-json")))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise HelperCalibrationError("invalid-helper-json") from err
    require(isinstance(receipt, dict), "invalid-helper-receipt")
    require(receipt.get("status") == "input-inserted-game-response-unverified"
            and receipt.get("machine") in ("AMD-DESKTOP", "LEGION")
            and type(receipt.get("processId")) is int and receipt["processId"] > 0
            and type(receipt.get("processStartUtcTicks")) is int
            and receipt["processStartUtcTicks"] > 0
            and isinstance(receipt.get("executableSha256"), str)
            and HEX.fullmatch(receipt["executableSha256"]),
            "helper-receipt-identity-invalid")
    keys = receipt.get("keys")
    require(isinstance(keys, list) and len(keys) == 1
            and type(keys[0]) is str and keys[0] in movement.MOVEMENT_KEYS,
            "helper-receipt-movement-key-invalid")
    require(receipt.get("windowsInputInserted") is True
            and receipt.get("windowsInputAttempted") is True
            and receipt.get("allRequestedKeyDownsInserted") is True
            and receipt.get("keyDownAttempts") == 1
            and receipt.get("keyDownInsertions") == 1
            and receipt.get("boundedActionCompleted") is True
            and receipt.get("releaseSucceeded") is True
            and receipt.get("insertionUncertain") is False
            and receipt.get("targetLost") is False
            and receipt.get("cancelled") is False
            and receipt.get("gameResponseVerified") is False
            and receipt.get("error") is None,
            "helper-receipt-delivery-or-release-unverified")
    requested = receipt.get("holdMilliseconds")
    observed = finite(receipt.get("observedMilliseconds"), "helper-observed-hold-invalid")
    require(type(requested) is int and 20 <= requested <= 3000
            and 20 <= observed <= physical.MAX_PHYSICAL_CALIBRATION_HOLD_MS
            and abs(observed - requested) <= max(50, requested * .25),
            "helper-observed-hold-invalid")
    hold_source = "executor-total-duration-legacy"
    hold_bounds = None
    effective_hold = observed
    timing_keys = ("inputCallTiming", "keySendEvents", "keyHoldWindows")
    if any(k in receipt for k in timing_keys):
        require("inputCallTiming" in receipt
                and ("keySendEvents" in receipt) == ("keyHoldWindows" in receipt),
                "helper-keysend-timing-incomplete")
        timing = receipt["inputCallTiming"]
        events = receipt.get("keySendEvents")
        windows = receipt.get("keyHoldWindows")
        require(isinstance(timing, dict)
                and timing.get("utcOrderValid") is True
                and timing.get("wallClockConsistentWithMonotonic") is True,
                "helper-keysend-timing-invalid")
        call_start = utc(timing.get("startedAtUtc"))
        call_end = utc(timing.get("completedAtUtc"))
        call_elapsed = finite(timing.get("monotonicElapsedMilliseconds"),
                              "helper-keysend-timing-invalid")
        executor_elapsed = finite(timing.get("executorObservedMilliseconds"),
                                  "helper-keysend-timing-invalid")
        require(call_start < call_end and call_elapsed >= 20
                and abs(executor_elapsed - observed) <= 0.2
                and abs((call_end - call_start).total_seconds()*1000 - call_elapsed)
                    <= max(50, call_elapsed*.2),
                "helper-keysend-timing-invalid")
        if events is None:
            hold_source = "executor-total-duration-with-call-envelope"
        else:
            require(isinstance(events, list) and len(events) == 2
                    and isinstance(windows, list) and len(windows) == 1,
                    "helper-keysend-timing-invalid")
            stamp_pairs = []
            for event, phase in zip(events, ("key-down", "key-up")):
                require(isinstance(event, dict) and event.get("key") == keys[0]
                        and event.get("phase") == phase and event.get("inserted") is True,
                        "helper-keysend-event-invalid")
                began = utc(event.get("callStartedAtUtc"))
                ended = utc(event.get("callCompletedAtUtc"))
                elapsed_ms = finite(event.get("sendCallElapsedMilliseconds"),
                                    "helper-keysend-event-invalid")
                require(call_start <= began <= ended <= call_end
                        and 0 <= elapsed_ms <= 100
                        and abs((ended - began).total_seconds()*1000 - elapsed_ms) <= 50,
                        "helper-keysend-event-invalid")
                stamp_pairs.append((began, ended))
            require(stamp_pairs[0][1] <= stamp_pairs[1][0],
                    "helper-keysend-event-order-invalid")
            w = windows[0]
            require(isinstance(w, dict) and w.get("key") == keys[0]
                    and w.get("status") == "candidate-sendinput-hold-bounds"
                    and w.get("exactKeyDownUpTimesKnown") is False
                    and w.get("gameResponseVerified") is False,
                    "helper-keysend-window-invalid")
            minimum = finite(w.get("minimumMillisecondsCandidate"),
                             "helper-keysend-window-invalid")
            maximum = finite(w.get("maximumMillisecondsCandidate"),
                             "helper-keysend-window-invalid")
            midpoint = finite(w.get("midpointMillisecondsCandidate"),
                              "helper-keysend-window-invalid")
            require(20 <= minimum <= midpoint <= maximum
                    and maximum <= physical.MAX_PHYSICAL_CALIBRATION_HOLD_MS
                    and math.isclose(midpoint, (minimum+maximum)/2, rel_tol=0, abs_tol=.01)
                    and abs(midpoint - requested) <= max(50, requested*.25)
                    and maximum <= call_elapsed+50
                    and w.get("downCallStartedAtUtc") == events[0]["callStartedAtUtc"]
                    and w.get("downCallCompletedAtUtc") == events[0]["callCompletedAtUtc"]
                    and w.get("upCallStartedAtUtc") == events[1]["callStartedAtUtc"]
                    and w.get("upCallCompletedAtUtc") == events[1]["callCompletedAtUtc"],
                    "helper-keysend-window-invalid")
            min_wall = (stamp_pairs[1][0]-stamp_pairs[0][1]).total_seconds()*1000
            max_wall = (stamp_pairs[1][1]-stamp_pairs[0][0]).total_seconds()*1000
            require(abs(minimum-min_wall) <= 50 and abs(maximum-max_wall) <= 50,
                    "helper-keysend-window-time-mismatch")
            effective_hold = midpoint
            hold_source = "sendinput-keydown-keyup-bounded-midpoint"
            hold_bounds = {"minimumMillisecondsCandidate": minimum,
                           "maximumMillisecondsCandidate": maximum}
    rounded = int(math.floor(effective_hold + .5))
    feedback = receipt.get("xyzFeedback")
    require(isinstance(feedback, dict)
            and feedback.get("status") == "candidate-native-xyz-feedback"
            and feedback.get("movementCandidate") is True
            and feedback.get("gameResponseVerified") is False,
            "helper-native-motion-evidence-invalid")
    before, after = feedback.get("beforeXYZ"), feedback.get("afterXYZ")
    require(isinstance(before, dict) and isinstance(after, dict),
            "helper-native-position-unavailable")
    keys_before = before.get("unitKey")
    require(type(keys_before) is str and UNIT.fullmatch(keys_before)
            and int(keys_before) < 2**64 and after.get("unitKey") == keys_before,
            "helper-native-player-changed")
    def native_coordinate(value):
        number = finite(value, "helper-native-position-invalid")
        return struct.unpack("<f", struct.pack("<f", number))[0]

    point = []
    for item in (before, after):
        a, b = utc(item.get("startedAtUtc")), utc(item.get("completedAtUtc"))
        require(a <= b and (b-a).total_seconds() <= 5, "helper-native-sample-interval-invalid")
        pos = movement.Position(*(native_coordinate(item.get(axis))
                                  for axis in ("x", "y", "z")))
        point.append((a, b, pos))
    capture_gap = (point[1][0] - point[0][1]).total_seconds()
    if "inputCallTiming" in receipt:
        require(point[0][1] <= call_start and call_end <= point[1][0],
                "helper-keysend-native-capture-order-invalid")
    require(0 < capture_gap <= observed / 1000 + 3,
            "helper-native-capture-gap-invalid")
    require(abs(finite(feedback.get("captureGapSeconds"), "helper-native-gap-mismatch")
                - capture_gap) <= .002,
            "helper-native-gap-mismatch")
    delta = feedback.get("deltaXYZ")
    require(isinstance(delta, dict), "helper-native-delta-invalid")
    a, b = point[0][2], point[1][2]
    dx, dy, dz = b.x-a.x, b.y-a.y, b.z-a.z
    for axis, actual in (("x", dx), ("y", dy), ("z", dz)):
        require(math.isclose(finite(delta.get(axis), "helper-native-delta-invalid"),
                             actual, rel_tol=0, abs_tol=.001),
                "helper-native-delta-mismatch")
    horizontal = math.hypot(dx, dz)
    require(math.isclose(finite(feedback.get("planarDisplacementCandidate"),
                               "helper-native-distance-invalid"),
                         horizontal, rel_tol=0, abs_tol=.001),
            "helper-native-distance-mismatch")
    try:
        measured = movement.calibrate_displacement(
            keys[0], a, b, rounded,
            maximum_horizontal=physical.physical_horizontal_limit(rounded),
            maximum_calibration_hold_ms=physical.MAX_PHYSICAL_CALIBRATION_HOLD_MS)
    except movement.MovementError as err:
        raise HelperCalibrationError(str(err)) from err
    result = {
        "schemaVersion": 1,
        "status": "offline-helper-move-calibration-candidate",
        "sourceKind": "rr2-move-key-json-receipt",
        "sourceReceiptSha256": hashlib.sha256(raw).hexdigest().upper(),
        "qualification": "windows-key-inserted-and-released-with-native-xyz-candidates-only",
        "movementEligible": False, "actionVerified": False, "headingQualified": False,
        "gameResponseVerified": False, "key": measured.key,
        "requestedHoldMilliseconds": requested, "observedHoldMilliseconds": effective_hold,
        "executorObservedMilliseconds": observed,
        "holdMeasurementSource": hold_source,
        "holdBoundsCandidate": hold_bounds,
        "calibrationHoldMillisecondsRounded": rounded,
        "dxPerMillisecondCandidate": dx / effective_hold,
        "dzPerMillisecondCandidate": dz / effective_hold,
        "horizontalDisplacementCandidate": measured.horizontal_displacement,
        "verticalDisplacementCandidate": measured.vertical_displacement,
        "captureGapSeconds": capture_gap,
        "machine": receipt["machine"], "processId": receipt["processId"],
        "processStartUtcTicks": str(receipt["processStartUtcTicks"]),
        "gameBuildSha256": receipt["executableSha256"].upper(),
        "unitKey": keys_before,
        "beforeSampleUtc": before["completedAtUtc"], "afterSampleUtc": after["startedAtUtc"],
        "limitations": [
            "Native XYZ values are unqualified candidates, not independent game response.",
            "This receipt has one source hash, not two independent native capture reports.",
            "A supplied receipt is not cryptographic proof of the claimed Windows events.",
            "Facing/zone continuity and navigation eligibility are unqualified.",
        ],
    }
    if keys == ["w"] and receipt.get("poseFeedback") is not None:
        pose = forward_pose_comparison(receipt, dx, dz)
        if pose is not None:
            result["forwardPoseComparisonCandidate"] = pose
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="new output file, never overwrite")
    args = parser.parse_args(argv)
    try:
        result = from_helper_receipt(args.receipt)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if args.out:
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(rendered + "\n")
        print(rendered)
        return 0
    except (OSError, ValueError, OverflowError, RecursionError) as err:
        print(json.dumps({"status": "blocked", "reason": str(err)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
