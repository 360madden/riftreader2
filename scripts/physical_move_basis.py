#!/usr/bin/env python3
"""Read-only empirical W/S/Q/E geometry from retained physical move-key receipts.

Calculates velocity/basis candidates only. No current-game access or input.
No source here certifies unchanged player facing between individual pulses.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.physical_move_key_calibration import from_helper_receipt

KEYS = ("w", "s", "q", "e")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _utc(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("basis-time-invalid") from exc
    require(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
            "basis-time-invalid")
    return result


def vector(report):
    return (report["dxPerMillisecondCandidate"],
            report["dzPerMillisecondCandidate"])


def geometry(first, second):
    x, z = first
    a, b = second
    norm1, norm2 = math.hypot(x, z), math.hypot(a, b)
    require(all(math.isfinite(v) for v in (x, z, a, b, norm1, norm2))
            and norm1 > 0 and norm2 > 0, "basis-velocity-invalid")
    dot = (x * a + z * b) / (norm1 * norm2)
    cross = (x * b - z * a) / (norm1 * norm2)
    dot = max(-1.0, min(1.0, dot))
    cross = max(-1.0, min(1.0, cross))
    return {
        "unsignedAngleDegreesCandidate": math.degrees(math.acos(dot)),
        "signedAngleDegreesCandidate": math.degrees(math.atan2(cross, dot)),
        "normalizedDotCandidate": dot,
        "normalizedCrossCandidate": cross,
        "firstSpeedOverSecondCandidate": norm1 / norm2,
    }


def analyze(paths, *, later_forward=None):
    require(type(paths) is dict and set(paths) == set(KEYS), "basis-keys-required")
    inputs = {key: from_helper_receipt(Path(paths[key])) for key in KEYS}
    require(all(inputs[key]["key"] == key for key in KEYS), "basis-key-mismatch")
    if later_forward is not None:
        after = from_helper_receipt(Path(later_forward))
        require(after["key"] == "w", "basis-later-forward-key-invalid")
        inputs["laterW"] = after

    values = tuple(inputs.values())
    identifiers = ("machine", "processId", "processStartUtcTicks",
                   "gameBuildSha256", "unitKey")
    require(all(all(r[field] == values[0][field] for field in identifiers)
                for r in values), "basis-player-process-build-mismatch")
    source_hashes = [v["sourceReceiptSha256"] for v in values]
    require(len(set(source_hashes)) == len(source_hashes), "basis-duplicate-source")

    ordered_keys = [*KEYS]
    if "laterW" in inputs:
        ordered_keys.append("laterW")
    starts = [_utc(inputs[k]["beforeSampleUtc"]) for k in ordered_keys]
    ends = [_utc(inputs[k]["afterSampleUtc"]) for k in ordered_keys]
    require(all(starts[i] < ends[i] for i in range(len(starts))), "basis-sample-time-invalid")
    require(all(ends[i] < starts[i + 1] for i in range(len(starts) - 1)),
            "basis-chronology-invalid")
    gaps = {f"{ordered_keys[i]}_to_{ordered_keys[i+1]}":
            (starts[i+1] - ends[i]).total_seconds()
            for i in range(len(starts) - 1)}

    matrix = {
        "forwardVsBackward": geometry(vector(inputs["w"]), vector(inputs["s"])),
        "forwardVsLeftStrafe": geometry(vector(inputs["w"]), vector(inputs["q"])),
        "leftVsRightStrafe": geometry(vector(inputs["q"]), vector(inputs["e"])),
        "backwardVsLeftStrafe": geometry(vector(inputs["s"]), vector(inputs["q"])),
    }
    if "laterW" in inputs:
        matrix["earlyVsLaterForward"] = geometry(
            vector(inputs["w"]), vector(inputs["laterW"]))
    cardinal = (
        abs(matrix["forwardVsBackward"]["unsignedAngleDegreesCandidate"] - 180) <= 10
        and abs(matrix["forwardVsLeftStrafe"]["unsignedAngleDegreesCandidate"] - 90) <= 10
        and abs(matrix["leftVsRightStrafe"]["unsignedAngleDegreesCandidate"] - 180) <= 10
        and abs(matrix["backwardVsLeftStrafe"]["unsignedAngleDegreesCandidate"] - 90) <= 10
    )

    reprojected = None
    if "laterW" in inputs and cardinal:
        # A *model*, not measured current strafe. Relative angular rotation
        # follows observed forward direction; speed scale assumes proportional
        # movement response across keys and is unverified for changed facing.
        signed = matrix["earlyVsLaterForward"]["signedAngleDegreesCandidate"]
        forward_scale = math.hypot(*vector(inputs["laterW"])) / math.hypot(*vector(inputs["w"]))
        if abs(signed) <= 45 and 0.8 <= forward_scale <= 1.2:
            radians = math.radians(signed)
            c, s = math.cos(radians), math.sin(radians)
            reprojected = {}
            for key in ("s", "q", "e"):
                x, z = vector(inputs[key])
                reprojected[key] = {
                    "vxPerMillisecondCandidate": (x*c - z*s) * forward_scale,
                    "vzPerMillisecondCandidate": (x*s + z*c) * forward_scale,
                }
            reprojected = {
                "status": "unverified-rigid-rotation-model",
                "relativeDirectionChangeDegreesCandidate": signed,
                "speedScaleFromForwardCandidate": forward_scale,
                "modeledVectors": reprojected,
                "sameFacingConfirmed": False,
                "navigationEligible": False,
                "qualification": "Rotated earlier key vectors to later forward; no later strafe measurements.",
            }

    return {
        "schemaVersion": 1,
        "status": "offline-physical-key-basis-candidate",
        "movementEligible": False,
        "navigationEligible": False,
        "headingQualified": False,
        "sameFacingConfirmed": False,
        "gameResponseVerified": False,
        "cardinalGeometryCandidate": cardinal,
        "sourceKind": "same-epoch-distinct-helper-receipts",
        "identity": {field: values[0][field] for field in identifiers},
        "sourceReceiptsSha256": {key: inputs[key]["sourceReceiptSha256"] for key in ordered_keys},
        "samples": {key: {
            "observedHoldMilliseconds": inputs[key]["observedHoldMilliseconds"],
            "horizontalSpeedPerMillisecondCandidate": math.hypot(*vector(inputs[key])),
            "vxCandidate": vector(inputs[key])[0],
            "vzCandidate": vector(inputs[key])[1],
            "beforeSampleUtc": inputs[key]["beforeSampleUtc"],
            "afterSampleUtc": inputs[key]["afterSampleUtc"],
        } for key in ordered_keys},
        "timeBetweenSamplesSeconds": gaps,
        "geometry": matrix,
        "laterFacingReprojectionCandidate": reprojected,
        "limitations": [
            "Same process/player/build does not prove unchanged facing, zone or world instance.",
            "Observed XYZ vectors are native-memory candidates; game consumption is unverified.",
            "No actor-yaw sample accompanies these historical key receipts.",
            "A matching cardinal pattern is not approval to execute navigation.",
            "Long key holds are observations, not a validated linear model for short pulses.",
            "Optional later-facing reprojection assumes rigid rotation and proportional speeds; not observed.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key, long_name in (("w", "--forward"), ("s", "--backward"),
                           ("q", "--left"), ("e", "--right")):
        parser.add_argument(long_name, type=Path, required=True, dest=key)
    parser.add_argument("--later-forward", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze({key: getattr(args, key) for key in KEYS},
                         later_forward=args.later_forward)
        rendered = json.dumps(result, sort_keys=True, allow_nan=False)
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        print(rendered)
        return 0
    except (OSError, ValueError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
