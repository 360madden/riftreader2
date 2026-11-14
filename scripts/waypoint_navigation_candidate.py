"""Inspect RiftWorld candidate paths offline; never authorizes movement.

The candidate hash checks internal consistency, not authenticity or the hashes of
referenced patch/build files. Source references are preserved, never executed or
opened. The result does not establish world identity, clearance, or traversal.

Usage: python scripts/waypoint_navigation_candidate.py inspect CANDIDATE.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys

_ID_FIELDS = ("schema", "patchId", "status", "world", "coordinates", "query", "points", "planner", "evidence")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_POINTS = 50000


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"invalid JSON number: {value}")


def read_candidate(path):
    """Read one bounded JSON document, rejecting ambiguous duplicate keys."""
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_CANDIDATE_BYTES + 1)
    if len(data) > MAX_CANDIDATE_BYTES:
        raise ValueError(f"candidate exceeds {MAX_CANDIDATE_BYTES} bytes")
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_json_object,
                      parse_constant=_reject_constant)


def _xyz(value, name):
    if not isinstance(value, list) or len(value) != 3 or any(
        not _finite_number(n) for n in value
    ):
        raise ValueError(f"{name} must contain three finite numbers")


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def inspect_candidate(candidate):
    """Return a provenance-preserving review document, or reject malformed input.

    Content identity detects accidental changes, not authenticity. No result grants
    execution authority; context, source integrity and traversal remain separate.
    """
    if not isinstance(candidate, dict) or candidate.get("schema") != "riftworld.candidate-path/1":
        raise ValueError("unsupported candidate schema")
    if any(k not in candidate for k in _ID_FIELDS):
        raise ValueError("candidate lacks identity fields")
    if isinstance(candidate.get("points"), list) and len(candidate["points"]) > MAX_POINTS:
        raise ValueError(f"candidate exceeds {MAX_POINTS} points")
    try:
        json.dumps(candidate, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("candidate contains invalid JSON values") from exc
    identity = {key: candidate[key] for key in _ID_FIELDS}
    identity["plannerResult"] = candidate.get("plannerResult")
    try:
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate identity contains invalid values") from exc
    if candidate.get("candidateId") != digest:
        raise ValueError("candidate content identity mismatch")
    if not isinstance(candidate.get("patchId"), str) or not _HEX64.fullmatch(candidate["patchId"]):
        raise ValueError("invalid patch identity")
    status = candidate["status"]
    if status not in ("complete", "partial", "unavailable"):
        raise ValueError("invalid candidate status")
    world, frame, query, planner, evidence = (candidate[k] for k in ("world", "coordinates", "query", "planner", "evidence"))
    if not all(isinstance(v, dict) for v in (world, frame, query, planner, evidence)):
        raise ValueError("candidate context must consist of objects")
    if any(not isinstance(world.get(k), str) or not world[k].strip() for k in ("sourceWorld", "authority")):
        raise ValueError("missing source world identity")
    if (frame.get("axisOrder") != ["x", "y", "z"] or frame.get("upAxis") != "y"
        or not isinstance(frame.get("frameId"), str) or not frame["frameId"].strip()
        or not isinstance(frame.get("units"), str) or not frame["units"].strip()
        or not isinstance(frame.get("transformToRr2Native"), dict)):
        raise ValueError("invalid coordinate frame")
    if not isinstance(planner.get("buildId"), str) or not _HEX64.fullmatch(planner["buildId"]):
        raise ValueError("invalid build identity")
    if not isinstance(planner.get("profile"), dict):
        raise ValueError("missing planner profile")
    profile = planner["profile"]
    for field in ("cell_size", "cell_height", "agent_height", "agent_radius", "agent_max_climb", "agent_max_slope", "region_min_size"):
        value = profile.get(field)
        if (not _finite_number(value)
            or value < 0 or (value == 0 and field in ("cell_size", "cell_height", "agent_height", "agent_radius"))):
            raise ValueError(f"invalid planner profile {field}")
    if profile["agent_max_slope"] > 90 or int(profile["region_min_size"]) != profile["region_min_size"]:
        raise ValueError("invalid planner profile limits")
    for key in ("requestedStartXYZ", "requestedGoalXYZ"):
        _xyz(query.get(key), f"query.{key}")
    for key in ("snappedStartXYZ", "snappedGoalXYZ"):
        if query.get(key) is not None:
            _xyz(query[key], f"query.{key}")
    allowed = {"geometry": {"render-mesh-approximation", "measured", "unknown"},
               "walkability": {"estimated", "unknown"}, "traversal": {"verified", "unverified"}}
    if any(not isinstance(evidence.get(k), str) or evidence[k] not in v for k, v in allowed.items()):
        raise ValueError("invalid evidence labels")
    points = candidate["points"]
    if not isinstance(points, list) or (status == "unavailable" and points) or (status != "unavailable" and not points):
        raise ValueError("points disagree with candidate status")
    if len(points) > MAX_POINTS:
        raise ValueError(f"candidate exceeds {MAX_POINTS} points")
    seen = set()
    for point in points:
        if not isinstance(point, dict) or not isinstance(point.get("id"), str) or not point["id"] or point["id"] in seen:
            raise ValueError("invalid or duplicate point identity")
        seen.add(point["id"])
        _xyz(point.get("xyz"), "point.xyz")
        if isinstance(point.get("flags"), bool) or not isinstance(point.get("flags"), int) or point["flags"] < 0:
            raise ValueError("invalid point flags")
    raw = candidate.get("plannerResult")
    if raw is not None:
        if not isinstance(raw, dict) or not isinstance(raw.get("waypoints"), list):
            raise ValueError("invalid planner result")
        if len(raw["waypoints"]) > MAX_POINTS:
            raise ValueError(f"planner result exceeds {MAX_POINTS} waypoints")
        try:
            raw_points = [{"xyz": p["pos"], "flags": p["flags"]} for p in raw["waypoints"]]
            if (raw_points != [{"xyz": p["xyz"], "flags": p["flags"]} for p in points]
                or raw["status"] != status or raw["cacheKey"] != planner["buildId"]
                or any(raw[k] != query.get(k) for k in ("requestedStartXYZ", "requestedGoalXYZ", "snappedStartXYZ", "snappedGoalXYZ"))):
                raise ValueError("planner result disagrees with candidate")
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid planner result") from exc
    blockers = ["review-only adapter never authorizes execution", "live world and source integrity are not established by this inspection", "segment clearance and live traversal are not established by this inspection"]
    if status != "complete":
        blockers.append(f"candidate status is {status}")
    transform = frame["transformToRr2Native"]
    if transform.get("kind") != "identity" or transform.get("qualification") != "verified":
        blockers.append("RR2 coordinate transform is not verified")
    return {"schema": "rr2.navigation-candidate-review/1", "reviewOnly": True,
            "autoRejoinAvailable": False, "inputSent": False, "segmentClearance": "unknown",
            "executionEligible": False, "executionBlockers": blockers,
            "candidate": copy.deepcopy(candidate)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inspect a candidate without executing or adopting it")
    inspect.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)
    try:
        value = read_candidate(args.candidate)
        result = inspect_candidate(value)
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc), "executionEligible": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
