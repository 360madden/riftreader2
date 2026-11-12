#!/usr/bin/env python3
"""Compare stored scalar fields against actor matrix states, without game input.

This only tests whether four values changed across two separated stationary
actor-pose states. It does not classify the scalar owner as body/camera yaw.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_physical_turn_pair as turn
from scripts import fresh_native_smoothed_scalar as scalar
from scripts.project_xyz_track import _pairs

MAX_BYTES = 200_000


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read_scalar(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_BYTES,
            "scalar-source-missing-or-oversized")
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_BYTES, "scalar-source-oversized")
    report = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            ValueError("scalar-nonfinite-source")))
    require(isinstance(report, dict) and report.get("schemaVersion") == 1
            and report.get("status") == "complete"
            and report.get("contractVersion") in (
                "native-current-smoothed-scalar-candidate/1",
                "native-current-smoothed-scalar-candidate-burst/1"),
            "scalar-source-contract-invalid")
    identity = report.get("identity")
    require(isinstance(identity, dict) and type(identity.get("processId")) is int
            and type(identity.get("processStartUtcTicks")) is int,
            "scalar-identity-invalid")
    rows = report.get("observations")
    if rows is None:
        require(report["contractVersion"].endswith("-candidate/1")
                and isinstance(report.get("observation"), dict), "scalar-source-count-invalid")
        rows = [report["observation"]]
    else:
        require(report["contractVersion"].endswith("-candidate-burst/1")
                and isinstance(rows, list) and 2 <= len(rows) <= 30
                and report.get("requestedSamples") == len(rows)
                and report.get("completedSamples") == len(rows)
                and report.get("observation") == rows[-1],
                "scalar-source-count-invalid")
    prev_end = None
    component = None
    key = None
    entity = None
    checked = []
    for row in rows:
        require(isinstance(row, dict) and row.get("identity") == identity,
                "scalar-identity-changed")
        scalar.validate_report(row, pid=identity["processId"],
                               ticks=identity["processStartUtcTicks"])
        row_owner = (row["playerKeyDecimal"], row["playerEntityDecimal"],
                     row["componentAddressDecimal"])
        if component is None:
            key, entity, component = row_owner
        require(row_owner == (key, entity, component), "scalar-owner-changed")
        start = turn._utc_tick_order_key(row["startedAtUtc"])
        end = turn._utc_tick_order_key(row["completedAtUtc"])
        require(start <= end and (prev_end is None or start > prev_end),
                "scalar-time-order-invalid")
        prev_end = end
        checked.append((start, end, tuple(row["rawBits"])))
    return {
        "identity": identity, "key": key, "entity": entity, "component": component,
        "times": (checked[0][0], checked[-1][1]),
        "bits": [b for _, _, b in checked],
        "values": [tuple(row[name] for name in scalar.VALUES) for row in rows],
        "sourceSha256": hashlib.sha256(raw).hexdigest().upper(),
        "sampleCount": len(rows),
    }


def pair(scalar_path, pose_path, *, max_gap_seconds=30.0):
    require(type(max_gap_seconds) in (int, float) and math.isfinite(max_gap_seconds)
            and 0 < max_gap_seconds <= 120, "scalar-pose-gap-limit-invalid")
    s = read_scalar(scalar_path)
    p = turn._load(pose_path)
    require(p["kind"] == "actor-pose", "scalar-pose-source-kind-invalid")
    require(s["identity"] == p["identity"] and s["key"] == p["key"],
            "scalar-pose-process-player-mismatch")
    require(s["entity"] == p["owner"][0], "scalar-pose-entity-mismatch")
    gap = (turn.elapsed_seconds(s["times"][1], p["exactTimes"][0][0])
           if s["times"][1] < p["exactTimes"][0][0] else
           turn.elapsed_seconds(p["exactTimes"][-1][1], s["times"][0]))
    require(0 < gap <= max_gap_seconds, "scalar-pose-captures-too-far-apart")
    matrices = [row["actor"] for row in p["matrices"]]
    require(all(m is not None and m["angle"] is not None for m in matrices),
            "scalar-pose-actor-angle-unavailable")
    return {
        "scalar": s, "pose": p, "gapSeconds": gap,
        "actorAngles": [m["angle"] for m in matrices],
        "actorBitSeries": [tuple(m["bits"]) for m in matrices],
    }


def compare(old_scalar, old_pose, new_scalar, new_pose, *, max_pair_gap_seconds=30):
    old = pair(old_scalar, old_pose, max_gap_seconds=max_pair_gap_seconds)
    new = pair(new_scalar, new_pose, max_gap_seconds=max_pair_gap_seconds)
    a, b = old["scalar"], new["scalar"]
    x, y = old["pose"], new["pose"]
    require(a["identity"] == b["identity"] == x["identity"] == y["identity"],
            "scalar-pose-epoch-changed")
    require((a["key"], a["entity"], a["component"]) == (b["key"], b["entity"], b["component"])
            and (x["key"], x["owner"]) == (y["key"], y["owner"]),
            "scalar-pose-owner-changed")
    require(max(a["times"][1], x["exactTimes"][-1][1])
            < min(b["times"][0], y["exactTimes"][0][0]),
            "scalar-pose-epochs-not-ordered")
    sha = [a["sourceSha256"], b["sourceSha256"], x["sha256"], y["sha256"]]
    require(len(set(sha)) == 4, "scalar-pose-identical-sources")
    all_scalar_bits = [*a["bits"], *b["bits"]]
    all_actor_bits = [*old["actorBitSeries"], *new["actorBitSeries"]]
    scalar_stable = all(v == all_scalar_bits[0] for v in all_scalar_bits)
    actor_stable_each = (
        len(set(old["actorBitSeries"])) == 1 and
        len(set(new["actorBitSeries"])) == 1)
    first_angle = old["actorAngles"][-1]
    last_angle = new["actorAngles"][0]
    delta = turn._angle_delta(first_angle, last_angle)
    require(delta is not None and math.isfinite(delta), "scalar-pose-angle-ambiguous")
    enough_rotation = abs(delta) >= 15
    return {
        "schemaVersion": 1,
        "status": "physical-scalar-vs-actor-state-candidate",
        "key": a["key"],
        "processId": a["identity"]["processId"],
        "processStartUtcTicks": str(a["identity"]["processStartUtcTicks"]),
        "gameBuildSha256": a["identity"]["executableSha256"].upper(),
        "playerEntityDecimal": a["entity"],
        "scalarComponentDecimal": a["component"],
        "actorComponentDecimal": str(x["owner"][1]),
        "oldActorAngleDegreesCandidate": first_angle,
        "newActorAngleDegreesCandidate": last_angle,
        "actorAngleChangeDegreesCandidate": delta,
        "actorPoseStableWithinEachPair": actor_stable_each,
        "scalarUnchangedAcrossBothPairs": scalar_stable,
        "oldScalarValues": list(a["values"][-1]),
        "newScalarValues": list(b["values"][-1]),
        "oldPairGapSeconds": old["gapSeconds"],
        "newPairGapSeconds": new["gapSeconds"],
        "sourceSha256": {
            "oldScalar": a["sourceSha256"], "oldActorPose": x["sha256"],
            "newScalar": b["sourceSha256"], "newActorPose": y["sha256"],
        },
        "scalarFieldsChangedAcrossActorStatesObserved": bool(not scalar_stable and enough_rotation),
        "unchangedScalarDespiteDifferentActorAngleCandidate": bool(
            scalar_stable and actor_stable_each and enough_rotation),
        "headingQualified": False,
        "navigationEligible": False,
        "gameInputResponseVerified": False,
        "limitations": [
            "Two stationary states do not establish a controlled A/D response or passive freshness.",
            "A constant scalar may be a relative offset or inactive smoothing state, not necessarily a defective field.",
            "Actor angle is a structural matrix candidate, not independently proven body yaw.",
            "Neither source is an independent RIFT UI/Lua validator.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("--old-scalar", "--old-pose", "--new-scalar", "--new-pose"):
        p.add_argument(flag, type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    try:
        result = compare(args.old_scalar, args.old_pose, args.new_scalar, args.new_pose)
        text = json.dumps(result, sort_keys=True, allow_nan=False)
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(text + "\n")
        print(text)
        return 0
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError,
            scalar.Blocked) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
