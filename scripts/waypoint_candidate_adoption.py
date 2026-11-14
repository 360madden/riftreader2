"""Derive a scoped route from explicit candidate and native evidence; no game access.

Corresponding normalized planar arc-length breakpoints bound the entire paired
linear polylines by convexity. This deliberately does not infer correspondence,
clearance, or a global coordinate transform.
"""
from __future__ import annotations

import argparse
import bisect
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.waypoint_kinds import point_kinds
from scripts.waypoint_measurements import parse_projection_route
from scripts.waypoint_navigation_candidate import inspect_candidate, _read_document, MAX_CANDIDATE_BYTES
from scripts.waypoint_route_library import normalize_context, compare_context, _validate
from scripts.waypoint_progress import _route


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _near(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2]) <= .50 + 1e-9 and abs(a[1] - b[1]) <= 1.0


def _polyline(points):
    lengths = [0.0]
    # Identical planar vertices with differing height cannot define a planar
    # arc parameter; reject rather than silently selecting a floor.
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[2] - a[2])
        lengths.append(lengths[-1] + length)
    total = lengths[-1]
    if total < 1e-9:
        raise ValueError("degenerate-centerline")
    return [value / total for value in lengths]


def _at(points, fractions, fraction):
    index = min(len(points) - 2, max(0, bisect.bisect_right(fractions, fraction) - 1))
    while fractions[index + 1] == fractions[index] and index > 0:
        index -= 1
    t = (fraction - fractions[index]) / (fractions[index + 1] - fractions[index])
    return [a + t * (b - a) for a, b in zip(points[index], points[index + 1])]


def _compare_candidate(candidate, native, context, *, candidate_start, candidate_end,
                    native_start, native_end, direction):
    """Return a derived route, with zero-based inclusive indices in source order.

    Both ranges are selected explicitly; direction reverses both together. This
    internal comparison is called only after original native receipt validation.
    """
    inspect_candidate(candidate)
    if candidate["status"] != "complete":
        raise ValueError("complete-candidate-required")
    if candidate["coordinates"]["transformToRr2Native"].get("kind") != "identity":
        raise ValueError("explicit-identity-frame-required")
    if direction != "forward":
        raise ValueError("candidate-reverse-requires-independent-evidence")
    _validate(native)
    evidence = parse_projection_route(native)
    native_context = normalize_context(native.get("routeContext"))
    context = normalize_context(context)
    if compare_context(context, native_context) != "matching" or compare_context(native_context, context) != "matching":
        raise ValueError("matching-zone-context-required")
    owner = evidence["identity"]
    for ctx in (context, native_context):
        if (not ctx.get("playerKey") or ctx["playerKey"] != owner["unitKey"]
            or ctx["target"]["hostName"].casefold() != owner["machine"].casefold()
            or ctx["target"]["executableSha256"].casefold() != owner["gameBuildSha256"].casefold()):
            raise ValueError("context-owner-mismatch")
    candidates = candidate["points"]
    native_points = evidence["points"]
    for first, last, count in ((candidate_start, candidate_end, len(candidates)), (native_start, native_end, len(native_points))):
        if type(first) is not int or type(last) is not int or not 0 <= first < last < count:
            raise ValueError("invalid-contiguous-scope")
    query = candidate["query"]
    for requested, snapped in (("requestedStartXYZ", "snappedStartXYZ"), ("requestedGoalXYZ", "snappedGoalXYZ")):
        if query[snapped] is None or not _near(query[requested], query[snapped]):
            raise ValueError("candidate-endpoint-snap-outside-bound")
    if not _near(candidates[0]["xyz"], query["snappedStartXYZ"]) or not _near(candidates[-1]["xyz"], query["snappedGoalXYZ"]):
        raise ValueError("candidate-endpoint-inconsistent")
    c_indexes = list(range(candidate_start, candidate_end + 1))
    n_indexes = list(range(native_start, native_end + 1))
    candidate_line = [candidates[i]["xyz"] for i in c_indexes]
    native_line = [[native_points[i]["xyz"][axis] for axis in ("x", "y", "z")] for i in n_indexes]
    candidate_fractions, native_fractions = _polyline(candidate_line), _polyline(native_line)
    for fraction in sorted(set(candidate_fractions + native_fractions)):
        if not _near(_at(candidate_line, candidate_fractions, fraction),
                     _at(native_line, native_fractions, fraction)):
            raise ValueError("centerline-segment-outside-bound")
    # Check every vertex separately, including coincident planar vertices with
    # different heights. A zero-length segment has no unique arc parameter.
    for points, fractions, other, other_fractions in ((candidate_line, candidate_fractions, native_line, native_fractions),
                                                       (native_line, native_fractions, candidate_line, candidate_fractions)):
        for point, fraction in zip(points, fractions):
            if not _near(point, _at(other, other_fractions, fraction)):
                raise ValueError("centerline-segment-outside-bound")
    kinds = point_kinds(native)
    stations = [(fraction, 0, index) for index, fraction in enumerate(candidate_fractions)]
    stations += [(native_fractions[j], 1, j) for j, index in enumerate(n_indexes) if kinds[index] == "stop"]
    stations.sort()
    rows, heights, output_kinds = [], [], []
    for fraction, is_stop, index in stations:
        if is_stop:
            native_index = n_indexes[index]
            point = native_line[index]
            name = native["waypoints"][native_index][0]
        else:
            point = candidate_line[index]
            name = "Candidate " + str(c_indexes[index] + 1)
        rows.append([name, round(point[0], 6), round(point[2], 6)])
        heights.append(point[1])
        output_kinds.append("stop" if is_stop else "pass")
    # Inserting an exact native stop can bend the derived polyline. Recheck
    # that the final geometry, including every stop, remains within the envelope.
    derived = [[row[1], y, row[2]] for row, y in zip(rows, heights)]
    derived_fractions = _polyline(derived)
    for fraction in sorted(set(derived_fractions + native_fractions)):
        if not _near(_at(derived, derived_fractions, fraction), _at(native_line, native_fractions, fraction)):
            raise ValueError("derived-centerline-outside-bound")
    for point, fraction in zip(derived, derived_fractions):
        if not _near(point, _at(native_line, native_fractions, fraction)):
            raise ValueError("derived-centerline-outside-bound")
    result = {"waypoints": rows, "heights": heights, "pointKinds": output_kinds,
              "routeContext": native_context,
              "candidateAdoption": {"version": 1, "scope": "explicit-corresponding-centerline-only",
                  "candidateId": candidate["candidateId"], "patchId": candidate["patchId"],
                  "buildId": candidate["planner"]["buildId"], "frame": deepcopy(candidate["coordinates"]),
                  "candidateWorld": deepcopy(candidate["world"]), "assertedContext": context,
                  "nativeEvidenceSha256": _digest(native), "owner": {k: owner[k] for k in ("machine", "gameBuildSha256", "unitKey")}, "candidateIndices": c_indexes,
                  "nativeIndices": n_indexes, "direction": direction,
                  "planarTolerance": .5, "heightTolerance": 1.0,
                  "supportedDirections": ["forward"],
                  "hasOffMesh": any(candidate["points"][i]["flags"] & 4 for i in c_indexes),
                  "qualification": "scoped correspondence only; no global transform, clearance or live authority"}}
    _validate(result)
    return result


def _full_native_route(receipt_paths, zone_path):
    """Validate and retain every native sample, including receipt junctions."""
    from scripts.export_continuous_route import export_route, _read, _native_receipts, _samples
    from scripts.waypoint_measurements import measurement
    hashes = [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in receipt_paths]
    zone_hash = hashlib.sha256(Path(zone_path).read_bytes()).hexdigest()
    native = export_route(receipt_paths, zone_path)
    identity = parse_projection_route(native)["identity"]
    rows = []
    for path in receipt_paths:
        for receipt in _native_receipts(_read(path)):
            samples = _samples(receipt, path, 0.0, False)
            for sample in samples:
                if rows:
                    previous = rows[-1]
                    dt = (sample["observed"] - previous["observed"]).total_seconds()
                    distance = math.dist(tuple(sample[a] for a in "xyz"), tuple(previous[a] for a in "xyz"))
                    if (dt < 0 or dt > 3.0 or math.hypot(sample["x"] - previous["x"], sample["z"] - previous["z"]) > 2.0
                        or abs(sample["y"] - previous["y"]) > 1.0 or distance > 12.0 * dt + .20):
                        raise ValueError("native-evidence-discontinuity")
                rows.append(sample)
    if hashes != [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in receipt_paths] or zone_hash != hashlib.sha256(Path(zone_path).read_bytes()).hexdigest():
        raise ValueError("native-evidence-changed-during-read")
    native["waypoints"] = [["Observed " + str(i + 1), row["x"], row["z"]] for i, row in enumerate(rows)]
    native["heights"] = [row["y"] for row in rows]
    native["pointMeasurements"] = [measurement({a: row[a] for a in "xyz"}, {"runtimeIdentity": identity},
                                               row["source"], row["observedAtUtc"]) for row in rows]
    _validate(native)
    return native


def adopt_receipt_candidate(candidate, receipt_paths, zone_path, *, candidate_start, candidate_end,
                            native_start, native_end, direction):
    """Build a bounded route from validated native receipts; never sends input."""
    native = _full_native_route(receipt_paths, zone_path)
    route = _compare_candidate(candidate, native, native["routeContext"],
        candidate_start=candidate_start, candidate_end=candidate_end,
        native_start=native_start, native_end=native_end, direction=direction)
    route["candidateAdoption"]["sourceReceipts"] = [
        {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        for path in receipt_paths]
    route["candidateAdoption"]["zoneContextSha256"] = hashlib.sha256(Path(zone_path).read_bytes()).hexdigest()
    route["candidateAdoption"]["integritySha256"] = _adoption_digest(route)
    return route


def corroborate_reverse(route, reverse_candidate, receipt_paths, zone_path, *,
                        candidate_start, candidate_end, native_start, native_end):
    """Add reverse authority only after a separately queried and witnessed return."""
    if route["candidateAdoption"].get("hasOffMesh"):
        raise ValueError("candidate-reverse-offmesh-unsupported")
    native = _full_native_route(receipt_paths, zone_path)
    validate_adopted_route(route, route["candidateAdoption"]["owner"], native["routeContext"], "forward")
    original = route["candidateAdoption"]
    if (reverse_candidate.get("patchId") != original.get("patchId")
        or reverse_candidate.get("planner", {}).get("buildId") != original.get("buildId")
        or reverse_candidate.get("coordinates") != original.get("frame")
        or reverse_candidate.get("world") != original.get("candidateWorld")):
        raise ValueError("candidate-reverse-frame-mismatch")
    reverse = _compare_candidate(reverse_candidate, native, native["routeContext"],
        candidate_start=candidate_start, candidate_end=candidate_end,
        native_start=native_start, native_end=native_end, direction="forward")
    if reverse["candidateAdoption"].get("hasOffMesh"):
        raise ValueError("candidate-reverse-offmesh-unsupported")
    if reverse["candidateAdoption"]["owner"] != route["candidateAdoption"]["owner"] or compare_context(route["routeContext"], native["routeContext"]) != "matching":
        raise ValueError("candidate-reverse-context-mismatch")
    points = parse_projection_route(native)["points"][native_start:native_end + 1]
    native_line = [[p["xyz"][a] for a in ("x", "y", "z")] for p in points]
    original_line = [[p[1], y, p[2]] for p, y in zip(reversed(route["waypoints"]), reversed(route["heights"]))]
    a, b = _polyline(original_line), _polyline(native_line)
    for f in sorted(set(a + b)):
        if not _near(_at(original_line, a, f), _at(native_line, b, f)):
            raise ValueError("candidate-reverse-route-outside-bound")
    for points, fractions, other, other_fractions in ((original_line, a, native_line, b),
                                                       (native_line, b, original_line, a)):
        for point, fraction in zip(points, fractions):
            if not _near(point, _at(other, other_fractions, fraction)):
                raise ValueError("candidate-reverse-route-outside-bound")
    result = deepcopy(route)
    meta = result["candidateAdoption"]
    meta["supportedDirections"] = ["forward", "reverse"]
    meta["reverseEvidence"] = {"candidateId": reverse_candidate["candidateId"],
        "patchId": reverse_candidate["patchId"], "buildId": reverse_candidate["planner"]["buildId"],
        "candidateIndices": [candidate_start, candidate_end], "nativeIndices": [native_start, native_end],
        "nativeEvidenceSha256": _digest(native), "sourceReceipts": [
            {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for path in receipt_paths]}
    meta["integritySha256"] = _adoption_digest(result)
    return result


def _adoption_digest(document):
    metadata = deepcopy(document["candidateAdoption"])
    metadata.pop("integritySha256", None)
    points, heights = _route(document)
    return _digest({"waypoints": points, "heights": heights,
                    "pointKinds": point_kinds(document), "routeContext": document.get("routeContext"),
                    "candidateAdoption": metadata})


def validate_adopted_route(document, identity, current_context, direction):
    """Gate candidate-origin playback with the supplied *fresh* context and owner.

    This function reads no live state. The caller must obtain fresh context and
    must enforce its normal identity, input ownership, and STOP checks.
    """
    if "candidateAdoption" not in document:
        return
    metadata = document["candidateAdoption"]
    if not isinstance(metadata, dict) or metadata.get("version") != 1 or metadata.get("scope") != "explicit-corresponding-centerline-only":
        raise ValueError("invalid-candidate-adoption")
    if not isinstance(metadata.get("integritySha256"), str) or metadata["integritySha256"] != _adoption_digest(document):
        raise ValueError("candidate-adoption-integrity-mismatch")
    owner = metadata.get("owner")
    if not isinstance(owner, dict) or not isinstance(identity, dict) or any(
        not isinstance(owner.get(k), str) or not isinstance(identity.get(k), str)
        or (owner[k].casefold() != identity[k].casefold() if k != "unitKey" else owner[k] != identity[k])
        for k in ("machine", "gameBuildSha256", "unitKey")):
        raise ValueError("candidate-adoption-owner-mismatch")
    if direction not in metadata.get("supportedDirections", []):
        raise ValueError("candidate-adoption-direction-unsupported")
    context = normalize_context(current_context)
    if compare_context(document.get("routeContext"), context) != "matching" or compare_context(context, document.get("routeContext")) != "matching":
        raise ValueError("candidate-adoption-current-context-mismatch")
    if context.get("playerKey") != identity["unitKey"]:
        raise ValueError("candidate-adoption-current-player-mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("native", type=Path, help="Original native continuous-movement receipt JSON")
    parser.add_argument("context", type=Path, help="Historical normalized zone context JSON for the receipt")
    parser.add_argument("output", type=Path, help="New output file; never overwrites")
    for name in ("candidate-start", "candidate-end", "native-start", "native-end"):
        parser.add_argument("--" + name, type=int, required=True)
    parser.add_argument("--direction", choices=("forward", "reverse"), required=True)
    parser.add_argument("--reverse-candidate", type=Path)
    parser.add_argument("--reverse-native-start", type=int)
    parser.add_argument("--reverse-native-end", type=int)
    args = parser.parse_args(argv)
    try:
        candidate, _ = _read_document(args.candidate, MAX_CANDIDATE_BYTES)
        route = adopt_receipt_candidate(candidate, [args.native], args.context, candidate_start=args.candidate_start,
            candidate_end=args.candidate_end, native_start=args.native_start, native_end=args.native_end,
            direction=args.direction)
        reverse_options = (args.reverse_candidate, args.reverse_native_start, args.reverse_native_end)
        if any(value is not None for value in reverse_options):
            if any(value is None for value in reverse_options):
                raise ValueError("candidate-reverse-evidence-incomplete")
            reverse, _ = _read_document(args.reverse_candidate, MAX_CANDIDATE_BYTES)
            route = corroborate_reverse(route, reverse, [args.native], args.context,
                candidate_start=0, candidate_end=len(reverse["points"]) - 1,
                native_start=args.reverse_native_start, native_end=args.reverse_native_end)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(route, stream, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"output": str(args.output), "scope": route["candidateAdoption"]["scope"], "inputSent": False}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"error": str(exc), "inputSent": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
