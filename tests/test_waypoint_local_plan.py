"""Offline local planner regressions. Real Watch mesh acceptance is separate."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import waypoint_local_plan as local
from scripts.waypoint_candidate_adoption import reject_review_route
from tests.test_waypoint_navigation_candidate import sample, sign


def candidate(start, goal, points, *, status="complete"):
    value = sample()
    value.update(status=status, points=[
        {"id": str(i), "xyz": xyz, "flags": 1 if i == 0 else 2 if i == len(points)-1 else 0}
        for i, xyz in enumerate(points)])
    value["query"].update(requestedStartXYZ=start, requestedGoalXYZ=goal,
                          snappedStartXYZ=points[0], snappedGoalXYZ=points[-1])
    value["plannerResult"] = {
        "status": status, "cacheKey": value["planner"]["buildId"],
        **value["query"], "surfaceFollowing": {"status": "complete"},
        "waypoints": [{"pos": p["xyz"], "flags": p["flags"]} for p in value["points"]]}
    return sign(value)


class LocalPlanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.patch = self.root / "patch.json"
        self.build = self.root / "navigation.json"
        self.patch.write_text(json.dumps({"patchId": "a"*64}), encoding="utf-8")
        self.build.write_text(json.dumps({"buildId": "B"*64}), encoding="utf-8")
        self.enterContext(patch.object(local.platform, "node", return_value="TEST-STATION"))
        self.enterContext(patch.object(local.shared, "_registered_riftworld", return_value={}))
        self.enterContext(patch.object(local.shared, "_riftworld_tools",
                                      return_value=(self.root, self.root/"query.py", self.root/"python.exe")))
        self.enterContext(patch.object(local.shared, "_configured_riftworld_upstream", return_value=None))
        self.enterContext(patch.object(local.shared, "_riftworld_environment", return_value={}))
        self.output = self.root / "out"
        self.start, self.goals = [0, 1, 2], [[2, 1, 2], [3, 1, 2]]
        self.calls = 0
        self.change = None

    def runner(self, args, **kwargs):
        self.assertEqual(args[2:5], ["-m", "riftworld", "query"])
        self.assertEqual(kwargs["timeout"], 120)
        goal = self.goals[self.calls]
        # The nearer goal has a longer obstacle detour; the farther one wins.
        points = [self.start, [0, 1, 5], [2, 1, 5], goal] if not self.calls else [self.start, goal]
        value = candidate(self.start, goal, points)
        if self.change:
            self.change(self.calls, value)
        path = Path(args[args.index("--out")+1])
        path.write_text(json.dumps(sign(value)), encoding="utf-8")
        self.calls += 1
        return subprocess.CompletedProcess(args, {"complete": 0, "partial": 3}[value["status"]], "", "")

    def plan(self, **overrides):
        args = dict(expected_host="TEST-STATION", start=self.start, goals=self.goals,
                    patch=self.patch, build=self.build, output_directory=self.output, runner=self.runner)
        args.update(overrides)
        return local.plan_local(**args)

    def test_uses_actual_path_cost_not_nearest_euclidean_goal(self):
        result = self.plan()
        self.assertEqual(1, result["selected"]["index"])
        self.assertEqual(3.0, result["selected"]["pathLength3d"])
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["inputSent"])
        self.assertNotIn("waypoints", result)
        self.assertEqual(2, self.calls)
        self.assertEqual(result, json.loads((self.output/"plan.json").read_text()))

    def test_partial_path_cannot_win(self):
        def change(index, value):
            if index == 1:
                value["status"] = value["plannerResult"]["status"] = "partial"
        self.change = change
        self.assertEqual(0, self.plan()["selected"]["index"])

    def test_complete_path_with_excessive_snap_is_refused(self):
        def change(index, value):
            if index == 1:
                value["query"]["snappedGoalXYZ"] = [4, 1, 2]
                value["plannerResult"]["snappedGoalXYZ"] = [4, 1, 2]
        self.change = change
        result = self.plan()
        self.assertEqual(0, result["selected"]["index"])
        self.assertIn("endpoint-snap", result["alternatives"][1]["reason"])

    def test_source_mutation_aborts_before_publication(self):
        self.change = lambda *_: self.patch.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local-planning-input-changed"):
            self.plan()
        self.assertFalse((self.output/"plan.json").exists())

    def test_wrong_host_and_duplicate_goals_refused_before_launch(self):
        for override in ({"expected_host": "WRONG-STATION"}, {"goals": [self.goals[0]]*2}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.plan(**override)
        self.assertEqual(0, self.calls)

    def test_obstacle_receipt_and_scope_boundary(self):
        layer = {"path": str(self.root/"obstacles.json"), "sha256": "A"*64}
        points = [self.start, self.goals[0]]
        result = {
            "schema": "riftworld.obstacle-aware-route/1", "area": "A",
            "requestedStartXYZ": points[0], "requestedGoalXYZ": points[1],
            "obstacles": {"descriptor": layer["path"], "sha256": layer["sha256"], "obstacleLayerId": "layer"},
            "navigationSafetyVerified": False, "nativeCollisionVerified": False, "traversalVerified": False,
            "status": "known-geometry-clear", "coverageStatus": "complete", "obstacleCleared": True,
            "coverage": {"complete": True}, "allowUnknownCoverage": False,
            "knownDecodedGeometryStatus": "clear", "points": points,
            "physicalAgentProfile": {"agent_radius": .5, "agent_height": 1.8},
            "plannerResult": {"status": "complete", "waypoints": [
                {"pos": point, "flags": i+1} for i, point in enumerate(points)]},
            "verification": {"schema": "riftworld.obstacle-route-verification/1", "area": "A",
                             "knownDecodedGeometryStatus": "clear",
                             "knownDecodedGeometryAvoidanceVerified": True, "obstacleLayerSource": layer,
                             "obstacleLayerId": "layer", "route": {"points": points},
                             "capsule": {"agentRadius": .5, "agentHeight": 1.8}},
            "verifiedPolylineSha256": local.shared._identity(points),
            "endpointConnectors": {name: {"requestedXYZ": point, "snappedXYZ": point,
                "traversalVerified": False, "status": "projection-only-not-in-verified-route"}
                for name, point in zip(("start", "goal"), points)},
        }
        def check(value):
            value["routeId"] = local.shared._identity({k: v for k, v in value.items() if k != "routeId"})
            return local._obstacle_candidate(value, *points, layer, "A", .3, .5)
        self.assertEqual((2.0, 2.0), check(result))
        bad = deepcopy(result)
        bad.update(coverageStatus="unknown", obstacleCleared=False)
        with self.assertRaisesRegex(ValueError, "coverage"):
            check(bad)
        bad = deepcopy(result)
        bad["verification"]["route"]["points"] = [[99, 1, 2], points[1]]
        with self.assertRaisesRegex(ValueError, "verification"):
            check(bad)
        bad = deepcopy(result)
        bad["verification"]["capsule"]["agentRadius"] = .25
        with self.assertRaisesRegex(ValueError, "verification"):
            check(bad)
        bad = deepcopy(result)
        bad["plannerResult"]["waypoints"][0]["flags"] = 4
        with self.assertRaisesRegex(ValueError, "offmesh"):
            check(bad)
        for schema in (local.SCHEMA, "riftworld.obstacle-aware-route/1",
                       "riftworld.route-draft/1", "riftworld.route-draft-check/1"):
            with self.assertRaisesRegex(ValueError, "scoped-adoption"):
                reject_review_route({"schema": schema, "waypoints": [["x", 1, 2]]})


if __name__ == "__main__":
    unittest.main()
