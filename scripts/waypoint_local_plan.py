"""Local, deterministic coordinate-to-route planning using RiftWorld.

No game access or input. A calculated route is not a Waypoints playback route.
Supply alternative approach coordinates for the same objective; choose the
shortest complete, bounded-snap path rather than the closest straight-line goal.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import waypoint_destination_plan as shared
from scripts.waypoint_navigation_candidate import inspect_candidate, _finite_number
from scripts.waypoint_progress import write_json_atomic
from scripts.observe_physical import valid_host_name

SCHEMA = "rr2.local-path-plan/1"
MAX_GOALS = 4
# Invoke the peer's public planner with the locally registered upstream checkout.
# No new navigation engine, geometry generation, or verification algorithm.
OBSTACLE_QUERY = r"""
import json
from pathlib import Path
import sys
from riftworld.obstacle_navigation import plan_obstacle_route
from riftworld.storage import ensure_processing_space
layer, area, start, goal, out, cache, upstream, extent = sys.argv[1:]
ensure_processing_space(Path(cache), min_free_bytes=1024**3)
options = {"out_dir": Path(out), "cache_root": Path(cache),
           "search_extent": float(extent)}
if upstream:
    options["upstream"] = Path(upstream)
result = plan_obstacle_route(Path(layer), area, json.loads(start), json.loads(goal), **options)
print(json.dumps(result, allow_nan=False))
sys.exit({"known-geometry-clear": 0, "unavailable": 2,
          "blocked": 2, "indeterminate": 3}[result["status"]])
"""


def _xyz(value):
    return shared._xyz(value)


def _length(points):
    return math.fsum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _snap_cost(start, goal, points, snapped_start, snapped_goal, horizontal, vertical):
    """Keep actual requested-to-snapped connectors out of the route itself."""
    if not isinstance(points, list) or not 2 <= len(points) <= 50000:
        raise ValueError("no nonzero complete path")
    points = [_xyz(point) for point in points]
    snapped = [_xyz(snapped_start), _xyz(snapped_goal)]
    for requested, projected, endpoint in zip((start, goal), snapped, (points[0], points[-1])):
        if (math.hypot(requested[0]-projected[0], requested[2]-projected[2]) > horizontal
                or abs(requested[1]-projected[1]) > vertical):
            raise ValueError("endpoint-snap-exceeds-limit")
        # Float32 source-world coordinates may differ slightly between the
        # projected point and surface-following waypoint. Never join a gap.
        if math.dist(projected, endpoint) > .002:
            raise ValueError("path-endpoint-disagrees-with-projection")
    length = _length(points)
    if not math.isfinite(length) or length <= 0:
        raise ValueError("invalid-path-length")
    return length, length + math.dist(start, snapped[0]) + math.dist(goal, snapped[1])


def _saved_mesh_candidate(candidate, start, goal, patch_id, build_id, horizontal, vertical):
    inspect_candidate(candidate)
    query = candidate["query"]
    if (candidate["patchId"] != patch_id or candidate["planner"]["buildId"] != build_id
            or query["requestedStartXYZ"] != start or query["requestedGoalXYZ"] != goal):
        raise ValueError("local-query-source-mismatch")
    if candidate["status"] != "complete":
        return None
    raw = candidate.get("plannerResult")
    if (not isinstance(raw, dict) or raw.get("surfaceFollowing", {}).get("status") != "complete"
            or any(point["flags"] & 4 for point in candidate["points"])):
        raise ValueError("surface-path-incomplete-or-offmesh")
    return _snap_cost(start, goal, [p["xyz"] for p in candidate["points"]],
                      query["snappedStartXYZ"], query["snappedGoalXYZ"], horizontal, vertical)


def _obstacle_candidate(candidate, start, goal, layer_ref, area, horizontal, vertical):
    if (candidate.get("schema") != "riftworld.obstacle-aware-route/1"
            or candidate.get("routeId") != shared._identity(
                {k: v for k, v in candidate.items() if k != "routeId"})
            or candidate.get("area") != area
            or candidate.get("requestedStartXYZ") != start
            or candidate.get("requestedGoalXYZ") != goal
            or candidate.get("obstacles", {}).get("descriptor") != layer_ref["path"]
            or candidate["obstacles"].get("sha256") != layer_ref["sha256"]
            or any(candidate.get(key) is not False for key in
                   ("navigationSafetyVerified", "nativeCollisionVerified", "traversalVerified"))):
        raise ValueError("obstacle-query-source-mismatch")
    if candidate.get("status") != "known-geometry-clear":
        return None
    # Unknown coverage is never selected by this normal local planner.
    if (candidate.get("coverageStatus") != "complete"
            or candidate.get("coverage", {}).get("complete") is not True
            or candidate.get("allowUnknownCoverage") is not False
            or candidate.get("obstacleCleared") is not True
            or candidate.get("knownDecodedGeometryStatus") != "clear"):
        raise ValueError("obstacle-coverage-or-clearance-unqualified")
    verification = candidate.get("verification", {})
    points = candidate.get("points")
    raw = candidate.get("plannerResult", {})
    physical = candidate.get("physicalAgentProfile", {})
    capsule = verification.get("capsule", {})
    waypoints = raw.get("waypoints", [])
    raw_points = [point["pos"] for point in waypoints]
    raw_points = [point for index, point in enumerate(raw_points)
                  if index == 0 or point != raw_points[index - 1]]
    if (raw.get("status") != "complete" or raw_points != points
            or any(type(point.get("flags")) is not int or point["flags"] & 4
                   for point in waypoints)):
        raise ValueError("obstacle-path-incomplete-or-offmesh")
    if (verification.get("schema") != "riftworld.obstacle-route-verification/1"
            or verification.get("knownDecodedGeometryStatus") != "clear"
            or verification.get("knownDecodedGeometryAvoidanceVerified") is not True
            or verification.get("obstacleLayerSource") != layer_ref
            or verification.get("area") != area
            or verification.get("obstacleLayerId") != candidate["obstacles"].get("obstacleLayerId")
            or any(not _finite_number(physical.get(field)) or physical[field] <= 0
                   or physical[field] != capsule.get(other)
                   for field, other in (("agent_radius", "agentRadius"),
                                        ("agent_height", "agentHeight")))
            or verification.get("route", {}).get("points") != points
            or candidate.get("verifiedPolylineSha256") != shared._identity(points)):
        raise ValueError("obstacle-verification-mismatch")
    connectors = candidate.get("endpointConnectors", {})
    if set(connectors) != {"start", "goal"} or any(
            row.get("traversalVerified") is not False
            or row.get("status") != "projection-only-not-in-verified-route"
            or row.get("requestedXYZ") != requested
            for row, requested in zip((connectors["start"], connectors["goal"]), (start, goal))):
        raise ValueError("invalid-endpoint-connector")
    return _snap_cost(start, goal, points, connectors["start"]["snappedXYZ"],
                      connectors["goal"]["snappedXYZ"], horizontal, vertical)


def plan_local(*, expected_host, start, goals, output_directory, patch=None, build=None,
               obstacles=None, area=None, search_extent=.55, max_horizontal_snap=.30,
               max_vertical_snap=.50, timeout_seconds=120, riftworld_root=None,
               riftworld_python=None, riftworld_upstream=None, runner=subprocess.run):
    """Choose one local geometry candidate; never authorize movement or edit a route."""
    host = platform.node()
    if not valid_host_name(host) or not valid_host_name(expected_host) or host.casefold() != expected_host.casefold():
        raise ValueError("wrong-host")
    start, goals = _xyz(start), [_xyz(goal) for goal in goals]
    if not 1 <= len(goals) <= MAX_GOALS or len({tuple(g) for g in goals}) != len(goals):
        raise ValueError("provide one to four distinct alternative approach coordinates")
    if any(goal == start for goal in goals):
        raise ValueError("zero-length requested path")
    if (any(not _finite_number(v) or v < 0 for v in (max_horizontal_snap, max_vertical_snap))
            or not _finite_number(search_extent) or not 0 < search_extent <= 10
            or not _finite_number(timeout_seconds) or not 0 < timeout_seconds <= 300):
        raise ValueError("invalid local planning limits")
    if ((obstacles is None and (patch is None or build is None or area is not None))
            or (obstacles is not None and (patch is not None or build is not None
                                          or not isinstance(area, str) or not area.strip()))):
        raise ValueError("choose patch+build or obstacles+area")
    registered = shared._registered_riftworld(riftworld_root, riftworld_python, riftworld_upstream)
    root, _, python = shared._riftworld_tools(riftworld_root, riftworld_python, registered)
    upstream = shared._configured_riftworld_upstream(riftworld_upstream, registered)
    environment = shared._riftworld_environment(registered)
    output = Path(output_directory).resolve()
    output.mkdir(exist_ok=False)
    inputs, rows = {}, []
    if obstacles is None:
        patch = Path(patch).resolve()
        build = Path(build).resolve()
        if build.is_dir():
            build /= "navigation.json"
        patch_doc, patch_sha = shared._read(patch)
        build_doc, build_sha = shared._read(build)
        inputs = {"patch": {"path": str(patch), "sha256": patch_sha},
                  "build": {"path": str(build), "sha256": build_sha}}
        # Reuse an already-local persisted mesh; relocate only when necessary.
        if (upstream is not None and
                Path(build_doc.get("pipelineCheckout", "")).resolve() != upstream):
            inputs["originalBuild"] = inputs["build"]
            build = shared._relocate_navigation_build(inputs["originalBuild"], output / "navigation-build", upstream)
            inputs["build"] = shared._reference(build)
    else:
        layer = Path(obstacles).resolve()
        if layer.is_dir():
            layer /= "obstacles.json"
        inputs = {"obstacles": shared._reference(layer)}

    def unchanged():
        if any(shared._hash(ref["path"]) != ref["sha256"] for ref in inputs.values()):
            raise ValueError("local-planning-input-changed")

    def coords(point):
        return ",".join(format(v, ".17g") for v in point)

    for index, goal in enumerate(goals):
        unchanged()
        folder = output / f"goal-{index:02d}"
        if obstacles is None:
            folder.mkdir()
            candidate_path = folder / "candidate.json"
            command = [str(python), "-B", "-m", "riftworld", "query",
                       "--patch", str(patch), "--build", str(build),
                       "--from", coords(start), "--to", coords(goal),
                       "--search-extent", str(search_extent),
                       "--max-horizontal-snap", str(max_horizontal_snap),
                       "--max-vertical-snap", str(max_vertical_snap),
                       "--out", str(candidate_path)]
        else:
            candidate_path = folder / "route.json"
            command = [str(python), "-B", "-c", OBSTACLE_QUERY, str(layer), area,
                       json.dumps(start), json.dumps(goal), str(folder), str(output / "cache"),
                       str(upstream or ""), str(search_extent)]
        row = {"index": index, "goalXYZ": goal, "status": "unavailable"}
        try:
            completed = runner(command, cwd=root, text=True, capture_output=True,
                               check=False, timeout=timeout_seconds, **environment)
            row["exitCode"] = completed.returncode
            if not candidate_path.is_file():
                raise ValueError("planner-did-not-publish: " + completed.stderr[-300:])
            candidate, digest = shared._read(candidate_path, 32 * 1024 * 1024)
            row.update(candidate={"path": str(candidate_path), "sha256": digest},
                       plannerStatus=candidate.get("status"))
            metric = (_saved_mesh_candidate(candidate, start, goal, patch_doc["patchId"],
                                            build_doc["buildId"], max_horizontal_snap, max_vertical_snap)
                      if obstacles is None else
                      _obstacle_candidate(candidate, start, goal, inputs["obstacles"], area,
                                          max_horizontal_snap, max_vertical_snap))
            if metric is not None:
                if completed.returncode != 0:
                    raise ValueError("planner-exit-contradicts-complete-path")
                row.update(status="complete-candidate", pathLength3d=metric[0], score=metric[1])
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            row.update(status="unavailable", reason=str(error)[:400])
        unchanged()
        rows.append(row)

    # Deterministic tie-break: caller's alternative order. Recheck every
    # candidate byte pin before selecting, including the ones not selected.
    for row in rows:
        if "candidate" in row and shared._hash(row["candidate"]["path"]) != row["candidate"]["sha256"]:
            raise ValueError("local-candidate-changed-before-selection")
    unchanged()
    choices = [row for row in rows if row["status"] == "complete-candidate"]
    selected = min(choices, key=lambda row: (row["score"], row["index"])) if choices else None
    result = {"schema": SCHEMA, "host": host,
              "status": "planned-candidate" if selected else "unavailable",
              "backend": "decoded-obstacle" if obstacles is not None else "saved-detour",
              "startXYZ": start, "inputs": inputs, "alternatives": rows, "selected": selected,
              "movementEligible": False, "inputSent": False, "currentRouteChanged": False,
              "qualification": "Local pathfinding in source coordinates; endpoint connectors, "
                               "native frame/world, live traversal and movement authority are not established."}
    write_json_atomic(output / "plan.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--from", dest="start", type=_xyz, required=True)
    parser.add_argument("--to", dest="goals", type=_xyz, action="append", required=True)
    parser.add_argument("--out-dir", dest="output_directory", type=Path, required=True)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--obstacles", type=Path)
    parser.add_argument("--area")
    parser.add_argument("--search-extent", type=float, default=.55)
    parser.add_argument("--max-horizontal-snap", type=float, default=.30)
    parser.add_argument("--max-vertical-snap", type=float, default=.50)
    parser.add_argument("--timeout-seconds", type=float, default=120)
    for name in ("root", "python", "upstream"):
        parser.add_argument("--riftworld-" + name, type=Path)
    try:
        result = plan_local(**vars(parser.parse_args(argv)))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0 if result["selected"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
