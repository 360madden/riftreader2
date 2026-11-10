"""Assess current-build native pose candidates with the historical V1 facing controls.

Use five successive, saved RR2 native readouts (position + actor-pose):
baseline, after CAMERA-ONLY movement, after A, after D, after W.
Operator-supplied labels are NOT action receipts. This tool reads evidence only;
it never sends input or qualifies native body yaw by itself.
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

from scripts.compare_native_player_reads import load, compare

PHASES = ("baseline", "camera-only", "turn-left", "turn-right", "forward")
MATRICES = ("actorMatrix", "modelMatrix", "renderMatrix")


def wrap180(degrees: float) -> float:
    return (degrees + 180.0) % 360.0 - 180.0


def v1_body_yaw_degrees(raw_radians: float) -> float:
    """Verified October-18 V1 float32 convention; NOT a new-build locator."""
    if type(raw_radians) not in (int, float) or not math.isfinite(raw_radians):
        raise ValueError("facing-reference-nonfinite")
    return wrap180(90.0 - math.degrees(raw_radians))


def _timestamp(text: str) -> datetime:
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("facing-observation-time-invalid")
    return result


def assess(paths: list[Path]) -> dict:
    if len(paths) != len(PHASES) or len({str(Path(p).resolve()) for p in paths}) != 5:
        raise ValueError("facing-five-distinct-captures-required")
    saved = [load(path) for path in paths]
    comparisons = []
    for (a, ah), (b, bh) in zip(saved, saved[1:]):
        result = compare(a, b, ah, bh)
        if not {"position", "actor-pose"}.issubset(result["fieldsCompared"]):
            raise ValueError("facing-position-and-pose-required")
        # The command collects sources sequentially. Do not attribute overlapping
        # source reads to the intended operator action.
        first_end = max(_timestamp(a[field]["observedAtUtc"])
                        for field in result["fieldsCompared"])
        second_start = min(_timestamp(b[field]["observedAtUtc"])
                           for field in result["fieldsCompared"])
        if second_start <= first_end:
            raise ValueError("facing-phase-overlap")
        comparisons.append(result)
    # Adjacent checks alone can miss a nonadjacent replay (A, B, A, C, D).
    # Distinct capture paths and later timestamps do not make old source
    # reports fresh. Enforce one original report hash per phase and field.
    for field in ("position", "actor-pose"):
        source_hashes = [readout[field]["sourceReportSha256"].upper()
                         for readout, _ in saved]
        if len(set(source_hashes)) != len(source_hashes):
            raise ValueError("facing-repeated-" + field + "-source")
    # Across all four adjacent comparisons, the same game, VM, agent and player
    # identity is required by the existing verified native-read comparison.
    camera, left, right, forward = (c["comparison"] for c in comparisons)
    travel = forward["position"]
    distance = travel.get("horizontalXZDistanceCandidate")
    course = travel.get("xzTravelAngleDegreesCandidate")
    moved = (type(distance) in (int, float) and math.isfinite(distance)
             and distance >= .05 and type(course) in (int, float)
             and math.isfinite(course))
    # A camera-only control and stationary A/D turns cannot establish body yaw
    # when these same phase windows also contain unaccounted X/Z translation.
    # Keep these as native coordinate candidates, never proof of input delivery.
    stationary_controls = {}
    for phase_name, phase_compare in zip(PHASES[1:4], (camera, left, right)):
        position = phase_compare["position"]
        xz = position.get("horizontalXZDistanceCandidate")
        finite = type(xz) in (int, float) and math.isfinite(xz)
        stationary_controls[phase_name] = {
            "horizontalXZDistanceCandidate": float(xz) if finite else None,
            "stationaryCandidate": (position.get("status") == "same-owner-displacement-candidate"
                                    and finite and 0 <= xz < .05),
        }
    controls_stationary = all(row["stationaryCandidate"]
                              for row in stationary_controls.values())
    results = {}
    for name in MATRICES:
        rows = [phase["actor-pose"]["matrices"][name]
                for phase in (camera, left, right, forward)]
        if any(type(row.get("beforeAngleDegreesCandidate")) not in (int, float)
               or type(row.get("afterAngleDegreesCandidate")) not in (int, float)
               or type(row.get("deltaDegreesCandidate")) not in (int, float)
               for row in rows):
            results[name] = {"status": "unavailable-matrix"}
            continue
        change = [float(row["deltaDegreesCandidate"]) for row in rows]
        camera_invariant = (not rows[0]["rawBitsChanged"] and abs(change[0]) <= .25)
        turn_left, turn_right = change[1], change[2]
        # The legacy field decreased under A and increased under D in the
        # +X=0,+Z=90 travel convention. The present matrix could use either sign.
        sign = (1 if turn_left <= -1 and turn_right >= 1 else
                -1 if turn_left >= 1 and turn_right <= -1 else None)
        forward_stable = abs(change[3]) <= 2.5
        consistent = (camera_invariant and sign is not None and moved
                      and forward_stable and controls_stationary)
        # One W bearing can fit any angular offset. Do not call this fit a
        # verification of absolute body heading until another heading is tested.
        offset = (wrap180(float(course) - sign * float(
            rows[3]["afterAngleDegreesCandidate"])) if consistent else None)
        results[name] = {
            "status": "provisional-behavior-consistent" if consistent else "inconclusive",
            "cameraRawBitsUnchanged": not rows[0]["rawBitsChanged"],
            "cameraInvariantCandidate": camera_invariant,
            "turnLeftDeltaDegreesCandidate": turn_left,
            "turnRightDeltaDegreesCandidate": turn_right,
            "signMultiplierCandidate": sign,
            "forwardAngleDeltaDegreesCandidate": change[3],
            "forwardAngleStableCandidate": forward_stable,
            "forwardTravelDegreesCandidate": float(course) if moved else None,
            "forwardXZDistanceCandidate": float(distance) if type(distance) in (int, float) else None,
            "singleForwardOffsetFitDegreesCandidate": offset,
            "absoluteFacingQualified": False,
        }
    return {
        "schemaVersion": 1,
        "status": "candidate-only",
        "lab": comparisons[0]["targetId"],
        "unitKey": comparisons[0]["unitKey"],
        "historicalReference": {
            "source": "V1 player-yaw-recovery-result-2026-10-18",
            "gameBuildSha256": "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD",
            "rootRva": "0x32E0200",
            "ownerYawOffset": "0x304",
            "meaning": "qualified for the historical build only",
            "currentLocatorReused": False,
        },
        "phases": list(PHASES),
        "readoutSha256": dict(zip(PHASES, (sha for _, sha in saved))),
        "stationaryControlPhases": stationary_controls,
        "matrixCandidates": results,
        "bodyFacingQualified": False,
        "qualification": ("Source identities and phase ordering checked; phase/action labels "
                          "are operator assertions without validated input receipts. "
                          "A single W bearing only fits an angular offset; a second "
                          "heading, independent actions, camera-negative control and "
                          "restart evidence are required before production facing."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for phase in PHASES:
        parser.add_argument("--" + phase, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = assess([getattr(args, phase.replace("-", "_")) for phase in PHASES])
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        print(json.dumps({"status": "blocked",
                          "reason": str(error) if isinstance(error, ValueError)
                          and str(error).startswith("facing-") else
                          "facing-evidence-invalid"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
