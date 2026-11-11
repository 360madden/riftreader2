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
    rounded = int(math.floor(observed + .5))
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
    point = []
    for item in (before, after):
        a, b = utc(item.get("startedAtUtc")), utc(item.get("completedAtUtc"))
        require(a <= b and (b-a).total_seconds() <= 5, "helper-native-sample-interval-invalid")
        pos = movement.Position(*(finite(item.get(axis), "helper-native-position-invalid")
                                  for axis in ("x", "y", "z")))
        point.append((a, b, pos))
    capture_gap = (point[1][0] - point[0][1]).total_seconds()
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
    return {
        "schemaVersion": 1,
        "status": "offline-helper-move-calibration-candidate",
        "sourceKind": "rr2-move-key-json-receipt",
        "sourceReceiptSha256": hashlib.sha256(raw).hexdigest().upper(),
        "qualification": "windows-key-inserted-and-released-with-native-xyz-candidates-only",
        "movementEligible": False, "actionVerified": False, "headingQualified": False,
        "gameResponseVerified": False, "key": measured.key,
        "requestedHoldMilliseconds": requested, "observedHoldMilliseconds": observed,
        "calibrationHoldMillisecondsRounded": rounded,
        "dxPerMillisecondCandidate": measured.dx_per_ms,
        "dzPerMillisecondCandidate": measured.dz_per_ms,
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
