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
MAX_CASTS_BYTES = 64 * 1024 * 1024
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


def _read_document(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"document exceeds {limit} bytes")
    document = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_json_object,
                          parse_constant=_reject_constant)
    return document, hashlib.sha256(data).hexdigest().upper()


def read_candidate(path):
    """Read one bounded JSON document, rejecting ambiguous duplicate keys."""
    return _read_document(path, MAX_CANDIDATE_BYTES)[0]


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


def inspect_candidate(candidate, *, casts=None, patch=None, candidate_sha256=None, geometry_sha256=None):
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
    review = {"schema": "rr2.navigation-candidate-review/1", "reviewOnly": True,
            "autoRejoinAvailable": False, "inputSent": False, "segmentClearance": "unknown",
            "executionEligible": False, "executionBlockers": blockers,
            "candidate": copy.deepcopy(candidate)}
    if casts is not None:
        review["clearanceEvidence"] = _review_casts(candidate, casts, patch, candidate_sha256, geometry_sha256)
    elif patch is not None or geometry_sha256 is not None:
        raise ValueError("patch and geometry require cast evidence")
    return review


def _review_casts(candidate, casts, patch, candidate_sha256, geometry_sha256):
    """Bind published finite-line evidence to this exact candidate, not to its paths."""
    if not isinstance(casts, dict) or casts.get("schema") != "riftworld.finite-route-casts/1":
        raise ValueError("unsupported finite cast evidence")
    obj, settings, routes, samples = (casts.get(k) for k in ("obj", "settings", "routes", "casts"))
    if not isinstance(obj, dict) or not isinstance(obj.get("sha256"), str) or not _HEX64.fullmatch(obj["sha256"]):
        raise ValueError("cast evidence lacks a geometry hash")
    obj_hash = obj["sha256"].upper()
    if not isinstance(routes, list) or not isinstance(samples, list) or not isinstance(settings, dict):
        raise ValueError("invalid cast evidence structure")
    if len(routes) > MAX_POINTS or len(samples) > 500000:
        raise ValueError("cast evidence exceeds review limits")
    matches = [r for r in routes if isinstance(r, dict) and r.get("candidateId") == candidate["candidateId"]]
    if len(matches) != 1:
        raise ValueError("cast evidence must contain exactly one matching route")
    route = matches[0]
    if route.get("patchId") != candidate["patchId"] or route.get("candidateStatus") != candidate["status"]:
        raise ValueError("cast evidence route context mismatch")
    route_hash = route.get("sha256")
    if not isinstance(route_hash, str) or not _HEX64.fullmatch(route_hash):
        raise ValueError("cast evidence lacks candidate file hash")
    if candidate_sha256 is not None and (not isinstance(candidate_sha256, str) or route_hash.upper() != candidate_sha256.upper()):
        raise ValueError("cast evidence candidate file hash mismatch")
    source_status = "reported-only"
    if patch is not None:
        if not isinstance(patch, dict) or patch.get("schema") != "riftworld.patch/1":
            raise ValueError("unsupported patch descriptor")
        try:
            identity = {k: patch[k] for k in ("sourceWorld", "coordinates", "content")}
            if "coverage" in patch:
                identity["coverage"] = patch["coverage"]
            patch_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if (patch_id != candidate["patchId"] or patch.get("patchId") != patch_id
                or patch["coordinates"] != candidate["coordinates"]
                or patch["sourceWorld"] != candidate["world"]["sourceWorld"]
                or patch["content"]["geometrySha256"].upper() != obj_hash):
                raise ValueError("patch and cast evidence disagree")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("invalid patch descriptor") from exc
        source_status = "patch-content-matched"
    if geometry_sha256 is not None:
        if not isinstance(geometry_sha256, str) or not _HEX64.fullmatch(geometry_sha256) or geometry_sha256.upper() != obj_hash:
            raise ValueError("explicit geometry hash mismatch")
        source_status = "patch-and-supplied-geometry-hash-matched" if patch is not None else "reported-and-supplied-geometry-hash-matched"
    heights, offsets = settings.get("heightsAbovePath"), settings.get("lateralOffsets")
    if (not isinstance(heights, list) or not heights or not isinstance(offsets, list) or not offsets
        or any(not _finite_number(x) or x <= 0 for x in heights)
        or any(not _finite_number(x) for x in offsets)
        or settings.get("twoSidedTriangles") is not True):
        raise ValueError("invalid finite cast settings")
    if len(heights) > 128 or len(offsets) > 128 or len(heights) * len(offsets) > 16384:
        raise ValueError("cast settings exceed review limits")
    expected = {(h, o) for h in heights for o in offsets}
    if len(expected) > 128:
        raise ValueError("cast settings exceed review limits")
    segments = route.get("segments")
    points = candidate["points"]
    if not isinstance(segments, list) or len(segments) != max(0, len(points) - 1):
        raise ValueError("cast segment count mismatch")
    reviewed = []
    total_links = 0
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict) or type(segment.get("segment")) is not int or segment["segment"] != i:
            raise ValueError("cast segment ordering mismatch")
        links = segment.get("casts")
        if not isinstance(links, list):
            raise ValueError("invalid segment casts")
        total_links += len(links)
        if total_links > 500000:
            raise ValueError("segment casts exceed review limits")
        start, end = points[i]["xyz"], points[i + 1]["xyz"]
        if start == end:
            if links or segment.get("assessment") != "not-assessed-zero-length-segment":
                raise ValueError("invalid zero-length segment assessment")
            reviewed.append({"segment": i, "fromPointId": points[i]["id"], "toPointId": points[i+1]["id"], "state": "not-assessed-zero-length", "samples": []})
            continue
        actual, output = set(), []
        dx, dz = end[0] - start[0], end[2] - start[2]
        horizontal = math.hypot(dx, dz)
        for link in links:
            if not isinstance(link, dict):
                raise ValueError("invalid cast reference")
            cast_id, height, offset = link.get("castId"), link.get("heightAbovePath"), link.get("lateralOffset")
            if type(cast_id) is not int or not 0 <= cast_id < len(samples) or not _finite_number(height) or not _finite_number(offset):
                raise ValueError("invalid cast reference")
            pair = (height, offset)
            if pair not in expected or pair in actual:
                raise ValueError("cast settings are incomplete or duplicated")
            actual.add(pair)
            cast = samples[cast_id]
            if not isinstance(cast, dict) or not isinstance(cast.get("hits"), list) or type(cast.get("clearAtSampledLines")) is not bool:
                raise ValueError("invalid cast result")
            if cast["clearAtSampledLines"] != (len(cast["hits"]) == 0):
                raise ValueError("cast hit status disagrees")
            lateral = (-dz / horizontal * offset, dx / horizontal * offset) if horizontal else (0., 0.)
            for key, point in (("startXYZ", start), ("endXYZ", end)):
                _xyz(cast.get(key), f"cast.{key}")
                expected_xyz = (point[0] + lateral[0], point[1] + height, point[2] + lateral[1])
                if any(abs(a-b) > 1e-7 for a, b in zip(cast[key], expected_xyz)):
                    raise ValueError("cast coordinates disagree with candidate segment")
            for hit in cast["hits"]:
                if (not isinstance(hit, dict) or not isinstance(hit.get("group"), str)
                    or type(hit.get("objTriangleIndex")) is not int or hit["objTriangleIndex"] < 0
                    or not _finite_number(hit.get("segmentFraction")) or not 0 <= hit["segmentFraction"] <= 1):
                    raise ValueError("invalid triangle hit")
                _xyz(hit.get("pointXYZ"), "hit.pointXYZ")
                t = hit["segmentFraction"]
                if any(abs(hit["pointXYZ"][j] - (cast["startXYZ"][j] + t * (cast["endXYZ"][j] - cast["startXYZ"][j]))) > 1e-5 for j in range(3)):
                    raise ValueError("triangle hit lies outside its reported cast")
            output.append({"castId": cast_id, "heightAbovePath": height, "lateralOffset": offset,
                           "hitCount": len(cast["hits"]), "clearAtSampledLine": cast["clearAtSampledLines"]})
        if actual != expected:
            raise ValueError("cast settings are incomplete or duplicated")
        reviewed.append({"segment": i, "fromPointId": points[i]["id"], "toPointId": points[i+1]["id"],
                         "state": "hits-at-sampled-lines" if any(s["hitCount"] for s in output) else "clear-at-sampled-lines",
                         "lateralSampling": "collapsed-vertical-segment" if horizontal == 0 else "segment-local-offsets",
                         "samples": output})
    return {"schema": "rr2.finite-cast-review/1", "candidateFileHashStatus": "matched" if candidate_sha256 else "reported-only",
            "candidateFileSha256": route_hash, "candidateId": candidate["candidateId"], "patchId": candidate["patchId"],
            "sourceGeometrySha256": obj_hash, "sourceIdentityStatus": source_status,
            "settings": copy.deepcopy(settings), "segments": reviewed,
            "renderGeometry": candidate["evidence"]["geometry"],
            "navmeshWalkability": candidate["evidence"]["walkability"],
            "liveTraversal": candidate["evidence"]["traversal"],
            "usableWidth": "unknown", "floorIdentity": "unverified",
            "limitations": ["Finite sampled lines, not a swept volume or width; missing geometry and dynamic obstacles remain unknown.",
                            "Hashes establish matching content, not authenticity or live world identity."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inspect a candidate without executing or adopting it")
    inspect.add_argument("candidate", type=Path)
    inspect.add_argument("--casts", type=Path, help="Explicit finite-route-casts/1 evidence file")
    inspect.add_argument("--patch", type=Path, help="Explicit patch descriptor to check against evidence")
    inspect.add_argument("--obj", type=Path, help="Explicit geometry file whose bytes are hashed")
    args = parser.parse_args(argv)
    try:
        value, candidate_hash = _read_document(args.candidate, MAX_CANDIDATE_BYTES)
        cast_doc, cast_hash = _read_document(args.casts, MAX_CASTS_BYTES) if args.casts else (None, None)
        patch = _read_document(args.patch, MAX_CANDIDATE_BYTES)[0] if args.patch else None
        obj_hash = None
        if args.obj:
            with args.obj.open("rb") as stream:
                obj_hash = hashlib.file_digest(stream, "sha256").hexdigest().upper()
        result = inspect_candidate(value, casts=cast_doc, patch=patch,
                                   candidate_sha256=candidate_hash, geometry_sha256=obj_hash)
        if cast_hash:
            result["clearanceEvidence"]["evidenceFileSha256"] = cast_hash
            if obj_hash:
                result["clearanceEvidence"]["explicitGeometryBytesHashed"] = True
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"error": str(exc), "executionEligible": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
