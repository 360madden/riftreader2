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

    def bound_pose(self, *, after=None, change_owner=False):
        owner = {"machine": "TEST-STATION", "gameBuildSha256": "A"*64, "unitKey": "123"}
        transform = {"kind": "identity", "qualification": "landmark-reprojection-candidate",
                     "owner": owner, "boundsXYZ": [-1, -1, -1, 10, 10, 10]}
        self.patch.write_text(json.dumps({"patchId": "a"*64, "coordinates": {
            "transformToRr2Native": transform}}), encoding="utf-8")
        identity = {**owner, "processId": 42, "processStartUtcTicks": 100}
        before = {"nativeXYZ": self.start, "runtimeIdentity": identity,
                  "sampledAtUtc": "2026-11-27T00:00:00Z"}
        end = deepcopy(before)
        end["sampledAtUtc"] = "2026-11-27T00:00:01Z"
        if after is not None:
            end["nativeXYZ"] = after
        if change_owner:
            end["runtimeIdentity"]["processStartUtcTicks"] += 1
        admission = {"sessionId": "test", "stopEpoch": 1, "stopLatched": False}
        self.enterContext(patch.object(local.shared, "_session_state", return_value=admission))
        self.pose = self.enterContext(patch.object(local.shared, "_current_pose",
                                                   side_effect=[before, end]))
        return before, end

    def test_current_pose_brackets_local_query_without_input(self):
        before, after = self.bound_pose()
        result = self.plan(start=None, from_current=True, session="test")
        self.assertEqual(1, result["selected"]["index"])
        self.assertEqual(before, result["startObservation"])
        self.assertEqual(after, result["postPlanningObservation"])
        self.assertEqual(self.start, result["startXYZ"])
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["movementEligible"])
        self.assertEqual(2, self.pose.call_count)
        self.assertIsNone(result["observationBlocker"])

    def test_current_pose_drift_invalidates_selection(self):
        self.bound_pose(after=[.5, 1, 2])
        result = self.plan(start=None, from_current=True, session="test")
        self.assertIsNone(result["selected"])
        self.assertEqual("unavailable", result["status"])
        self.assertIn("moved-during-local-planning", result["observationBlocker"])

    def test_current_pose_changed_epoch_invalidates_selection(self):
        self.bound_pose(change_owner=True)
        result = self.plan(start=None, from_current=True, session="test")
        self.assertIsNone(result["selected"])
        self.assertIn("owner-or-stop-epoch-changed", result["observationBlocker"])

    def test_repeated_pose_is_not_fresh_feedback(self):
        before, after = self.bound_pose()
        after["sampledAtUtc"] = before["sampledAtUtc"]
        result = self.plan(start=None, from_current=True, session="test")
        self.assertIsNone(result["selected"])
        self.assertIn("did-not-advance", result["observationBlocker"])

    def test_stop_epoch_change_invalidates_selection(self):
        self.bound_pose()
        original = local.shared._session_state.return_value
        local.shared._session_state.side_effect = [original, {**original, "stopEpoch": 2}]
        result = self.plan(start=None, from_current=True, session="test")
        self.assertIsNone(result["selected"])
        self.assertIn("owner-or-stop-epoch-changed", result["observationBlocker"])

    def test_current_pose_outside_scope_refuses_before_query(self):
        before, _ = self.bound_pose()
        before["nativeXYZ"] = [20, 1, 2]
        with self.assertRaisesRegex(ValueError, "outside-qualified-map-scope"):
            self.plan(start=None, from_current=True, session="test")
        self.assertEqual(0, self.calls)
        self.assertFalse(self.output.exists())

    def test_unpinned_frame_and_wrong_map_owner_refuse_current_pose(self):
        before, _ = self.bound_pose()
        document = json.loads(self.patch.read_text())
        frame = document["coordinates"]["transformToRr2Native"]
        frame["owner"]["unitKey"] = "456"
        with self.assertRaisesRegex(ValueError, "map-owner-mismatch"):
            local._scoped_pose(document, before)
        frame["kind"] = "unknown"
        with self.assertRaisesRegex(ValueError, "identity-transform"):
            local._scoped_pose(document, before)

    def test_current_mode_requires_explicit_session_and_saved_mesh(self):
        for override in ({"start": None, "from_current": True},
                         {"from_current": True, "session": "test"},
                         {"session": "test"},
                         {"start": None, "from_current": True, "session": "test",
                          "obstacles": self.root/"layer.json"}):
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
