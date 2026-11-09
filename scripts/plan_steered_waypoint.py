#!/usr/bin/env python3
"""Plan one chosen-coordinate steering step from retained movement evidence.

This module is deliberately offline. It never connects to a VM, acquires a
lease, arms controls, or sends input. Operators execute its one recommended
step through the separately reviewed movement runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from . import navigation_anchors as anchors
else:
    import navigation_anchors as anchors


class SteeringPlanError(ValueError):
    pass


ARRIVAL_TOLERANCE = .30
MINIMUM_PULSE_MS = 20
MAXIMUM_PULSE_MS = 150
MINIMUM_PROGRESS = .03


def require(value, message):
    if not value:
        raise SteeringPlanError(message)


def load(path: Path) -> tuple[dict, str]:
    path = Path(path)
    require(not path.is_symlink(), "symbolic input is not allowed")
    path = path.resolve(strict=True)
    require(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024,
            "missing, symbolic, or oversized input")
    data = path.read_bytes()
    value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(
        SteeringPlanError("nonfinite JSON")))
    require(isinstance(value, dict), "JSON object required")
    return value, hashlib.sha256(data).hexdigest().upper()


def save(path: Path, value: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def finite(value, name):
    require(not isinstance(value, bool) and isinstance(value, (int, float)),
            f"{name} must be numeric")
    result = float(value)
    require(math.isfinite(result), f"{name} must be finite")
    return result


IDENTITY_KEYS = (
    "lab", "player", "addonEpoch", "sourceAddress", "readerProcessId",
    "readerProcessStartUtcTicks", "readerExecutableSha256", "readerInstance",
    "readerNonce", "receiverInstance",
)


def identity(sample: dict) -> dict:
    require(isinstance(sample, dict) and all(key in sample for key in IDENTITY_KEYS),
            "sample identity is incomplete")
    target = sample.get("target")
    require(isinstance(target, dict)
            and all(key in target for key in
                    ("processId", "processStartUtcTicks", "executableSha256")),
            "sample target identity is incomplete")
    result = {key: sample[key] for key in IDENTITY_KEYS}
    result["target"] = {key: target[key] for key in
                        ("processId", "processStartUtcTicks", "executableSha256")}
    if isinstance(result.get("readerExecutableSha256"), str):
        result["readerExecutableSha256"] = result["readerExecutableSha256"].upper()
    if isinstance(result["target"].get("executableSha256"), str):
        result["target"]["executableSha256"] = result["target"]["executableSha256"].upper()
    return result


def advancing(before: dict, after: dict):
    for key in ("outerSequence", "addonSequence"):
        require(type(before.get(key)) is int and type(after.get(key)) is int
                and after[key] > before[key], f"{key} did not advance")
    before_clock = finite(before.get("addonClock"), "addonClock")
    after_clock = finite(after.get("addonClock"), "addonClock")
    require(after_clock > before_clock, "addonClock did not advance")


def xyz(sample: dict) -> tuple[float, float, float]:
    value = sample.get("xyz") if isinstance(sample, dict) else None
    require(isinstance(value, dict) and set(value) == {"x", "y", "z"},
            "sample xyz is invalid")
    return tuple(finite(value[key], f"xyz.{key}") for key in ("x", "y", "z"))


def planar(a, b) -> float:
    return math.hypot(float(b[0]) - float(a[0]), float(b[2]) - float(a[2]))


def calibration(value: dict, expected_key="w") -> dict:
    require(value.get("success") is True and value.get("mode") == "calibration"
            and value.get("status") == "calibrated"
            and value.get("movementDimension") == "1d"
            and value.get("calibrationKeys") == [expected_key],
            "a successful matching 1d calibration is required")
    samples = value.get("samples")
    require(isinstance(samples, list) and len(samples) >= 2,
            "calibration samples are required")
    vector = value.get("calibrations", {}).get(expected_key)
    require(isinstance(vector, dict) and vector.get("key") == expected_key,
            "calibration vector is missing")
    dx = finite(vector.get("dx_per_ms"), "dx_per_ms")
    dz = finite(vector.get("dz_per_ms"), "dz_per_ms")
    hold = vector.get("calibration_hold_ms")
    require(type(hold) is int and 20 <= hold <= 150, "calibration hold is invalid")
    step_x, step_z = dx * hold, dz * hold
    magnitude = math.hypot(step_x, step_z)
    require(.05 <= magnitude <= 2.0, "calibration displacement is implausible")
    require(identity(samples[0]) == identity(samples[-1]) == value.get("calibrationIdentity"),
            "calibration identity differs from its samples")
    advancing(samples[0], samples[-1])
    start, end = xyz(samples[0]), xyz(samples[-1])
    require(math.isclose(step_x, end[0] - start[0], rel_tol=1e-6, abs_tol=1e-6)
            and math.isclose(step_z, end[2] - start[2], rel_tol=1e-6, abs_tol=1e-6),
            "calibration vector differs from its sample displacement")
    return {"value": value, "samples": samples, "identity": identity(samples[0]),
            "start": start, "end": end,
            "step": (step_x, step_z), "magnitude": magnitude,
            "holdMilliseconds": hold}


def signed_angle(before: tuple[float, float], after: tuple[float, float]) -> float:
    before_norm, after_norm = math.hypot(*before), math.hypot(*after)
    require(before_norm > 0 and after_norm > 0, "heading vector is zero")
    cross = before[0] * after[1] - before[1] * after[0]
    dot = before[0] * after[0] + before[1] * after[1]
    return math.atan2(cross, dot)


def turn_hold_timing(turn: dict, requested_ms: int) -> tuple[float, str]:
    """Prefer observed inserted-key hold over a nominal turn command duration."""
    evidence = turn.get("actionEvidence")
    if evidence is None:
        return float(requested_ms), "nominal-without-action-evidence"
    require(isinstance(evidence, list) and len(evidence) == 1
            and isinstance(evidence[0], dict) and evidence[0].get("index") == 1,
            "turn action evidence is invalid")
    item = evidence[0]
    decision, receipt = item.get("decision"), item.get("result")
    require(isinstance(decision, dict) and decision.get("key") == turn["turnKey"]
            and decision.get("hold_ms") == requested_ms,
            "turn action decision differs from reported key or hold")
    require(isinstance(receipt, dict), "turn action receipt is missing")
    action, result, events = (receipt.get("action"), receipt.get("result"),
                              receipt.get("inputEvents"))
    require(isinstance(action, dict) and action.get("keys") == [turn["turnKey"]]
            and action.get("holdMilliseconds") == requested_ms,
            "turn action receipt differs from reported key or hold")
    require(isinstance(result, dict) and result.get("deliverySucceeded") is True
            and result.get("releaseSucceeded") is True
            and result.get("cancelled") is False
            and result.get("targetLost") is False
            and result.get("stateUncertain") is False
            and receipt.get("recoveryRequired") is not True,
            "turn delivery or key release is not verified")
    require(isinstance(events, list), "turn key timing events are missing")
    down = [event for event in events if isinstance(event, dict)
            and event.get("kind") == "keyDownInserted"]
    up = [event for event in events if isinstance(event, dict)
          and event.get("kind") == "keyUpInserted"]
    require(len(down) == len(up) == 1
            and down[0].get("value") == up[0].get("value") == turn["turnKey"],
            "turn key timing events are incomplete or ambiguous")
    start = finite(down[0].get("elapsedMilliseconds"), "turn key-down time")
    end = finite(up[0].get("elapsedMilliseconds"), "turn key-up time")
    require(0 <= start < end, "turn key timing events are out of order")
    observed = end - start
    require(observed <= 250 and abs(observed - requested_ms)
            <= max(25.0, requested_ms * .25), "turn measured hold drifted")
    reported = result.get("observedKeyHoldMilliseconds")
    if reported is not None:
        require(abs(finite(reported, "reported turn hold") - observed) <= .5,
                "reported turn hold disagrees with inserted-key events")
    return observed, "inserted-key-events"


def measure_turn(before_path: Path, turn_path: Path, after_path: Path) -> dict:
    before_value, before_sha = load(before_path)
    turn, turn_sha = load(turn_path)
    after_value, after_sha = load(after_path)
    before, after = calibration(before_value), calibration(after_value)
    require(turn.get("success") is True and turn.get("mode") == "turn"
            and turn.get("status") == "turn-input-completed"
            and turn.get("headingClaimed") is False and turn.get("turnKey") in ("a", "d"),
            "a completed non-heading a/d turn result is required")
    hold = turn.get("holdMs")
    require(type(hold) is int and 20 <= hold <= 150, "turn hold is invalid")
    turn_samples = turn.get("samples")
    require(isinstance(turn_samples, list) and len(turn_samples) >= 2,
            "turn samples are required")
    common = before["identity"]
    require(common == identity(turn_samples[0]) == identity(turn_samples[-1]) == after["identity"],
            "turn evidence identities differ")
    advancing(before["samples"][-1], turn_samples[0])
    advancing(turn_samples[-1], after["samples"][0])
    require(planar(before["end"], xyz(turn_samples[0])) <= .10,
            "turn did not start at the before-calibration endpoint")
    turn_planar = planar(xyz(turn_samples[0]), xyz(turn_samples[-1]))
    require(turn_planar <= .05, "turn translated too far")
    require(planar(xyz(turn_samples[-1]), after["start"]) <= .10,
            "after calibration did not start at the turn endpoint")
    angle = signed_angle(before["step"], after["step"])
    require(abs(angle) >= math.radians(1), "turn angle is below the measurable threshold")
    rate_hold, timing_source = turn_hold_timing(turn, hold)
    rate = angle / rate_hold
    return {
        "schemaVersion": 1,
        "evidenceKind": "provisional-session-turn-calibration/1",
        "status": "provisional",
        "key": turn["turnKey"],
        "holdMilliseconds": hold,
        "rateDenominatorMilliseconds": rate_hold,
        "holdTimingSource": timing_source,
        "signedRadians": angle,
        "signedRadiansPerMillisecond": rate,
        "turnPlanarDisplacement": turn_planar,
        "beforeForwardVector": {"x": before["step"][0], "z": before["step"][1]},
        "afterForwardVector": {"x": after["step"][0], "z": after["step"][1]},
        "identity": common,
        "sourceSha256": {"beforeCalibration": before_sha, "turnResult": turn_sha,
                         "afterCalibration": after_sha},
        "limitations": ["Turn angle is derived from W displacement vectors, not a facing field.",
                        "This rate is provisional for this exact reader/game session only.",
                        "This single measurement is not permanent key semantics."] +
                       (["No inserted-key timing evidence; rate uses nominal hold."]
                        if timing_source != "inserted-key-events" else []),
    }


def read_turn_measurement(path: Path, expected_identity: dict) -> dict:
    value, digest = load(path)
    require(value.get("schemaVersion") == 1
            and value.get("evidenceKind") == "provisional-session-turn-calibration/1"
            and value.get("status") == "provisional" and value.get("key") in ("a", "d")
            and value.get("identity") == expected_identity,
            "turn measurement is invalid or belongs to another identity")
    rate = finite(value.get("signedRadiansPerMillisecond"), "signed turn rate")
    require(abs(rate) > 0, "signed turn rate is zero")
    return {"path": str(Path(path).resolve()), "sha256": digest,
            "key": value["key"], "rate": rate}


def post_turn_pin(path: Path, current: dict) -> dict:
    value, digest = load(path)
    require(value.get("success") is True and value.get("mode") == "turn"
            and value.get("status") == "turn-input-completed"
            and value.get("headingClaimed") is False and value.get("turnKey") in ("a", "d"),
            "after-turn result is not a completed non-heading turn")
    samples = value.get("samples")
    require(isinstance(samples, list) and len(samples) >= 2,
            "after-turn result samples are required")
    require(identity(samples[-1]) == current["identity"],
            "after-turn result belongs to another identity")
    advancing(samples[-1], current["samples"][0])
    require(planar(xyz(samples[-1]), current["start"]) <= .10,
            "current calibration did not start at the after-turn endpoint")
    return {"path": str(Path(path).resolve()), "sha256": digest}


def next_step(current_path: Path, goal_xz: tuple[float, float],
              turn_paths: list[Path], after_turn_path: Path | None = None) -> dict:
    current_value, current_sha = load(current_path)
    current = calibration(current_value)
    goal = tuple(finite(value, f"goal.{name}") for value, name in zip(goal_xz, ("x", "z")))
    x, y, z = current["end"]
    gx, gz = goal
    error = (gx - x, gz - z)
    distance = math.hypot(*error)
    base = {"schemaVersion": 1, "evidenceKind": "steered-waypoint-next-step/1",
            "currentCalibrationSha256": current_sha,
            "current": {"x": x, "y": y, "z": z},
            "planarGoal": {"x": gx, "z": gz},
            "planarDistance": distance, "arrivalKind": "planar-xz",
            "identity": current["identity"]}
    after_turn = post_turn_pin(after_turn_path, current) if after_turn_path else None
    if after_turn:
        base["afterTurnResult"] = after_turn
    if distance <= ARRIVAL_TOLERANCE:
        return {**base, "decision": "arrived", "reason": "within-planar-tolerance"}

    fx, fz = current["step"]
    magnitude = current["magnitude"]
    ux, uz = fx / magnitude, fz / magnitude
    projection = error[0] * ux + error[1] * uz
    signed_cross_track = ux * error[1] - uz * error[0]
    heading_error = math.atan2(signed_cross_track, projection)
    base.update({"signedHeadingErrorRadians": heading_error,
                 "crossTrackResidual": abs(signed_cross_track),
                 "forwardProjection": projection})

    if projection > 0 and abs(signed_cross_track) <= .05:
        alpha = projection / magnitude
        if alpha <= 2.5:
            dx_per_ms = fx / current["holdMilliseconds"]
            dz_per_ms = fz / current["holdMilliseconds"]
            best_after_pulse = min(math.hypot(
                error[0] - dx_per_ms * hold,
                error[1] - dz_per_ms * hold,
            ) for hold in range(MINIMUM_PULSE_MS, MAXIMUM_PULSE_MS + 1))
            if distance - best_after_pulse < MINIMUM_PROGRESS:
                return {**base, "decision": "blocked",
                        "reason": "no-bounded-forward-pulse-makes-useful-progress",
                        "bestAfterPulseDistance": best_after_pulse}
            target = {"x": gx, "y": y, "z": gz}
            kind = "chosen-planar-coordinate"
        elif alpha > 2.5:
            alpha = 2.0
            target = {"x": x + fx * alpha, "y": y, "z": z + fz * alpha}
            kind = "intermediate-forward-segment"
        runner_arguments = ["prepare", "--mode", "movement", "--dimension", "1d",
                            "--keys", "w", "--calibration-profile",
                            str(Path(current_path).resolve())]
        if after_turn:
            runner_arguments.extend(["--after-turn-result", after_turn["path"]])
        runner_arguments.extend(["--goal", str(target["x"]), str(target["y"]),
                                 str(target["z"])])
        return {**base, "decision": "forward", "targetKind": kind,
                "calibratedDisplacements": alpha, "target": target,
                "targetInterpretation": "planar-xz-only; y is the current observation",
                "runner": {"mode": "movement", "dimension": "1d", "keys": ["w"],
                           "calibrationProfile": str(Path(current_path).resolve()),
                           "goal": [target["x"], target["y"], target["z"]]},
                "runnerArgumentFragment": runner_arguments}

    turns = [read_turn_measurement(path, current["identity"]) for path in turn_paths]
    candidates = []
    for turn in turns:
        if heading_error * turn["rate"] <= 0:
            continue
        raw_hold = abs(heading_error / turn["rate"])
        hold = max(20, min(100, int(round(raw_hold))))
        predicted_error = abs(heading_error - turn["rate"] * hold)
        if predicted_error < abs(heading_error):
            candidates.append((predicted_error, hold, turn["key"], turn))
    if not candidates:
        return {**base, "decision": "blocked",
                "reason": "no-measured-turn-direction-reduces-error"}
    predicted_error, hold, key, selected = min(
        candidates, key=lambda option: (*option[:3], option[3]["sha256"],
                                        option[3]["path"]))
    return {**base, "decision": "turn", "key": key, "holdMilliseconds": hold,
            "predictedAbsoluteHeadingErrorRadians": predicted_error,
            "turnMeasurement": {"path": selected["path"], "sha256": selected["sha256"]},
            "runner": {"mode": "turn", "keys": [key], "turnHoldMilliseconds": hold},
            "runnerArgumentFragment": ["prepare", "--mode", "turn", "--keys", key,
                                       "--turn-hold-ms", str(hold)],
            "nextRequired": "fresh reviewed W calibration after the turn"}


def next_step_saved_anchor(current_path: Path, catalog_path: Path, anchor_id: str,
                           turn_paths: list[Path],
                           after_turn_path: Path | None = None) -> dict:
    """Calculate an offline-only step from a saved X/Z anchor; never authorize movement."""
    resolved = anchors.resolve_anchor(anchors.load_catalog(catalog_path), anchor_id)
    anchor = resolved["anchor"]
    current_value, current_sha = load(current_path)
    current = calibration(current_value)
    current_build = current["identity"]["target"]["executableSha256"]
    require(isinstance(current_build, str)
            and current_build.upper() == anchor["source"]["gameBuildSha256"],
            "saved anchor game build differs from calibration")
    point = resolved["planarGoal"]
    result = next_step(current_path, (point["x"], point["z"]),
                       turn_paths, after_turn_path)
    require(result["currentCalibrationSha256"] == current_sha
            and result["identity"] == current["identity"],
            "calibration changed during saved-anchor planning")
    # Saved destinations remain offline coordinates, never executable live goals.
    result.pop("runner", None)
    result.pop("runnerArgumentFragment", None)
    result["movementEligible"] = False
    result["savedAnchor"] = {
        "id": anchor["id"], "label": anchor["label"],
        "position": anchor["position"], "zoneLabel": anchor["zoneLabel"],
        "source": anchor["source"],
        "qualification": "offline-reference-only",
        "zoneLabelIsMetadataOnly": True,
        "sameWorldInstanceVerified": False,
    }
    result["nextRequiredForMovement"] = (
        "fresh same-session position and independently verified world/zone compatibility; "
        "saved coordinates are not an executable movement instruction")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    measure = commands.add_parser("measure-turn")
    measure.add_argument("--before-w-calibration", type=Path, required=True)
    measure.add_argument("--turn-result", type=Path, required=True)
    measure.add_argument("--after-w-calibration", type=Path, required=True)
    measure.add_argument("--output", type=Path, required=True)
    plan = commands.add_parser("next")
    plan.add_argument("--current-w-calibration", type=Path, required=True)
    goal = plan.add_mutually_exclusive_group(required=True)
    goal.add_argument("--goal-xz", nargs=2, type=float, metavar=("X", "Z"),
                      help="chosen planar destination; this planner makes no Y/3D claim")
    goal.add_argument("--anchor-id", help="offline saved XYZ anchor ID; requires --catalog")
    plan.add_argument("--catalog", type=Path, help="offline saved-anchor catalog")
    plan.add_argument("--turn-calibration", type=Path, action="append", default=[])
    plan.add_argument("--after-turn-result", type=Path,
                      help="pin the latest turn result when the W calibration followed a turn")
    plan.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "measure-turn":
            value = measure_turn(args.before_w_calibration, args.turn_result,
                                 args.after_w_calibration)
        elif args.anchor_id is not None:
            require(args.catalog is not None, "--anchor-id requires --catalog")
            value = next_step_saved_anchor(
                args.current_w_calibration, args.catalog, args.anchor_id,
                args.turn_calibration, args.after_turn_result)
        else:
            require(args.catalog is None, "--catalog requires --anchor-id")
            value = next_step(args.current_w_calibration, tuple(args.goal_xz),
                              args.turn_calibration, args.after_turn_result)
        save(args.output, value)
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, json.JSONDecodeError, SteeringPlanError,
            anchors.AnchorCatalogError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
