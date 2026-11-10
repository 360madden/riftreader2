"""Offline paired-motion consistency review: two native owner reads and two advancing Lua frames.

No VM, process, control server, input, or network access. This reviewer checks
near-time paired observations but deliberately does not infer a causal movement
stimulus or synchronized clocks. Raw reports and SHA-256 pins remain required.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import review_current_pointer_xyz as native

AXES = ("x", "y", "z")
KIND = "native-motion-pair-review/1"


def _xyz(obj: object, description: str) -> dict[str, float]:
    native._require(isinstance(obj, dict), description + " XYZ is missing")
    native._require(set(obj) == set(AXES)
                    and all(type(obj[k]) in (int, float)
                            and math.isfinite(float(obj[k])) for k in AXES),
                    description + " XYZ is incomplete or nonfinite")
    return {k: float(obj[k]) for k in AXES}


def _typed_pair(source: dict, target: dict) -> dict:
    native._require(source.get("schemaVersion") == 1
                    and source.get("evidenceKind") == native.SOURCE_KIND
                    and source.get("status") == "advanced-in-covered-scope",
                    "source is not an advancing typed-wire comparison")
    identity = source.get("identity")
    native._require(isinstance(identity, dict)
                    and all(identity.get(k) == v for k, v in target.items()),
                    "typed Lua process/build epoch differs")
    selected, captures = source.get("selected"), source.get("source")
    native._require(isinstance(selected, dict) and isinstance(captures, dict),
                    "typed source selected/capture evidence missing")
    result = {}
    previous_completion = None
    for stage in ("before", "after"):
        frame, capture = selected.get(stage), captures.get(stage)
        native._require(isinstance(frame, dict) and isinstance(capture, dict)
                        and capture.get("status") == "complete",
                        stage + " typed capture incomplete")
        stamp = native._time(capture.get("completedAtUtc"))
        start = native._time(capture.get("startedAtUtc"))
        native._require(start <= stamp, stage + " typed capture has reversed times")
        if previous_completion is not None:
            native._require(start > previous_completion,
                            "typed capture windows overlap or touch")
        previous_completion = stamp
        snap = capture.get("snapshotSha256")
        wire = frame.get("wireSha256")
        native._pin_sha(snap)
        native._pin_sha(wire)
        unit = frame.get("playerUnitId")
        native._require(isinstance(unit, str) and unit.startswith("u"),
                        stage + " player identity invalid")
        seq, clock = frame.get("sequence"), frame.get("frameTime")
        native._require(type(seq) is int and seq > 0
                        and type(clock) in (int, float)
                        and math.isfinite(float(clock)),
                        stage + " typed frame sequence/clock invalid")
        result[stage] = {
            "completedAtUtc": stamp.isoformat(),
            "snapshotSha256": snap,
            "wireSha256": wire,
            "playerUnitId": unit,
            "sequence": seq,
            "frameTime": float(clock),
            "xyz": _xyz(frame.get("xyz"), stage + " typed"),
        }
    a, b = result["before"], result["after"]
    native._require(a["playerUnitId"] == b["playerUnitId"],
                    "typed source player identity changed")
    native._require(a["sequence"] < b["sequence"]
                    and a["frameTime"] < b["frameTime"]
                    and native._time(a["completedAtUtc"]) < native._time(b["completedAtUtc"])
                    and a["snapshotSha256"] != b["snapshotSha256"]
                    and a["wireSha256"] != b["wireSha256"],
                    "typed source did not advance in independent captures")
    return result


def review(before: Path, after: Path, request: Path, source: Path,
           source_sha256: str, *, tolerance: float = 0.02,
           max_pair_lag_seconds: float = 180.0,
           min_movement_units: float = 0.1) -> dict:
    native._pin_sha(source_sha256)
    native._require(math.isfinite(tolerance) and 0 < tolerance <= 0.1,
                    "paired XYZ tolerance outside bound")
    native._require(math.isfinite(max_pair_lag_seconds)
                    and 1 <= max_pair_lag_seconds <= 300,
                    "maximum pair lag outside 1..300 seconds")
    native._require(math.isfinite(min_movement_units)
                    and 0.05 <= min_movement_units <= 10,
                    "minimum movement threshold outside 0.05..10 units")
    req, request_sha = native.read_source(request)
    target = native._target(req)
    typed_raw, typed_sha = native.read_source(source)
    native._require(typed_sha == source_sha256,
                    "advancing Lua comparison SHA-256 pin changed")
    typed = _typed_pair(typed_raw, target)
    reports = {}
    for stage, path in (("before", before), ("after", after)):
        obj, digest = native.read_source(path)
        reports[stage] = native._native(obj, digest, request_sha, target)
    a, b = reports["before"], reports["after"]
    native._require(a["sourceSha256"] != b["sourceSha256"],
                    "native before/after reports reused identical bytes")
    nat_a, nat_b = native._time(a["completedAtUtc"]), native._time(b["completedAtUtc"])
    src_a = native._time(typed["before"]["completedAtUtc"])
    src_b = native._time(typed["after"]["completedAtUtc"])
    native._require(nat_a < nat_b, "native samples are not in chronological order")
    native._require(max(nat_a, src_a) < min(nat_b, src_b),
                    "before/after observation intervals overlap")
    raw_offsets = {
        "before": (nat_a - src_a).total_seconds(),
        "after": (nat_b - src_b).total_seconds(),
    }
    # Gate the unrounded durations; rounding is strictly for human-readable output.
    native._require(all(abs(v) <= max_pair_lag_seconds for v in raw_offsets.values()),
                    "native/Lua acquisition lag exceeds near-time bound")
    offsets = {k: round(v, 3) for k, v in raw_offsets.items()}

    endpoints = {}
    for stage in ("before", "after"):
        delta = {k: round(reports[stage]["xyz"][k] - typed[stage]["xyz"][k], 10)
                 for k in AXES}
        endpoints[stage] = {
            "nativeMinusLua": delta,
            "allAxesWithinTolerance": all(abs(v) <= tolerance for v in delta.values()),
        }
    lua_delta = {k: round(typed["after"]["xyz"][k] - typed["before"]["xyz"][k], 10)
                 for k in AXES}
    native_delta = {k: round(b["xyz"][k] - a["xyz"][k], 10)
                    for k in AXES}
    residual = {k: round(native_delta[k] - lua_delta[k], 10) for k in AXES}
    significant_source = max(abs(x) for x in lua_delta.values()) >= min_movement_units
    significant_native = max(abs(x) for x in native_delta.values()) >= min_movement_units
    paired_agreement = all(v["allAxesWithinTolerance"] for v in endpoints.values())
    motion_agreement = all(abs(v) <= 2 * tolerance for v in residual.values())
    if not significant_source:
        status = "insufficient-source-motion"
    elif paired_agreement and significant_native and motion_agreement:
        status = "candidate-motion-consistent"
    else:
        status = "candidate-motion-disagrees"
    return {
        "schemaVersion": 1,
        "evidenceKind": KIND,
        "status": status,
        "qualification": "candidate-only-no-stimulus-or-clock-skew-proof",
        "target": target,
        "playerUnitId": typed["before"]["playerUnitId"],
        "rootRva": "0x32E0200",
        "xyzOffsets": ["0x320", "0x324", "0x328"],
        "requestSha256": request_sha,
        "typedComparisonSha256": typed_sha,
        "tolerance": tolerance,
        "maxPairLagSeconds": max_pair_lag_seconds,
        "minMovementUnits": min_movement_units,
        "nativeSamples": reports,
        "typedSamples": typed,
        "nativeMinusTypedSampleTimeSeconds": offsets,
        "endpointAgreement": endpoints,
        "typedDisplacement": lua_delta,
        "nativeDisplacement": native_delta,
        "nativeMinusTypedDisplacement": residual,
        "limitations": [
            "Guest native and typed source acquisition times are not simultaneous; source age is bounded, not zero.",
            "Guest and host clock skew has not been independently measured.",
            "No independent reviewed movement action/release receipt is checked here; correlation is not causation.",
            "A typed producer frame can predate its capture; advancing sequence alone cannot prove wall-clock freshness.",
            "Only the pinned one-hop owner window in the exact process epoch was read; patch/restart resilience is unproved.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-before", type=Path, required=True)
    parser.add_argument("--native-after", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--typed-comparison", type=Path, required=True)
    parser.add_argument("--typed-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--max-pair-lag-seconds", type=float, default=180)
    parser.add_argument("--min-movement-units", type=float, default=0.1)
    args = parser.parse_args(argv)
    try:
        native._require(args.output.parent.is_dir() and not args.output.exists()
                        and not args.output.is_symlink(),
                        "output parent missing or output already exists")
        result = review(args.native_before, args.native_after, args.request,
                        args.typed_comparison, args.typed_sha256,
                        tolerance=args.tolerance,
                        max_pair_lag_seconds=args.max_pair_lag_seconds,
                        min_movement_units=args.min_movement_units)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (native.EvidenceError, OSError, TypeError, KeyError, OverflowError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "qualification": result["qualification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
