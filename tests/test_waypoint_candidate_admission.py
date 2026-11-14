"""Fresh context admission at the shared movement boundary; no game input."""
import unittest
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

from scripts.movement_controller import Position
from scripts.physical_waypoints import admit_candidate_route, candidate_dispatch
from scripts.waypoint_candidate_adoption import _adoption_digest
from scripts.waypoint_playback import play_route
from scripts.waypoint_progress import RouteProgress
from scripts.waypoint_replay_readiness import replay_readiness
from tests.test_waypoint_candidate_adoption import CTX, run


class CandidateAdmissionTests(unittest.TestCase):
    def test_legacy_route_needs_no_new_context_reader(self):
        with patch("scripts.physical_waypoints.read_route_context") as read:
            admit_candidate_route(SimpleNamespace(), {"waypoints": [["A", 0, 0]]})
        read.assert_not_called()

    def test_adopted_route_passes_new_context_and_selected_direction(self):
        identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "abc", "unitKey": "self"}
        adapter = SimpleNamespace(binding={"runtimeIdentity": identity})
        route = {"candidateAdoption": {}}
        fresh = {"source": "newly-acquired-context"}
        with patch("scripts.physical_waypoints.read_route_context", return_value=fresh) as read, \
             patch("scripts.waypoint_candidate_adoption.validate_adopted_route") as validate:
            admit_candidate_route(adapter, route, "reverse")
        read.assert_called_once_with(adapter)
        validate.assert_called_once_with(route, identity, fresh, "reverse")

    def test_unavailable_context_cannot_be_replaced_by_saved_context(self):
        adapter = SimpleNamespace(binding={"runtimeIdentity": {}})
        with patch("scripts.physical_waypoints.read_route_context", side_effect=ValueError("expired")), \
             patch("scripts.waypoint_candidate_adoption.validate_adopted_route") as validate:
            with self.assertRaisesRegex(ValueError, "expired"):
                admit_candidate_route(adapter, {"candidateAdoption": {}, "routeContext": {"old": True}})
        validate.assert_not_called()

    def route(self):
        route = run()
        route.update(waypoints=[["A", 0, 0], ["B", 4, 0], ["C", 4, 4], ["D", 0, 0]],
                     heights=[1, 2, 3, 1], pointKinds=["pass", "stop", "pass", "pass"])
        metadata = route["candidateAdoption"]
        metadata["integritySha256"] = _adoption_digest(route)
        return route, SimpleNamespace(binding={"runtimeIdentity": metadata["owner"]})

    def test_direct_slice_uses_verified_source_rows_kinds_heights_and_pose(self):
        route, adapter = self.route()
        with patch("scripts.physical_waypoints.read_route_context", return_value=CTX):
            rows, guards = candidate_dispatch(adapter, route, [1, 2], "forward", "survival")
            self.assertEqual([("B", 4, 0), ("C", 4, 4)], rows)
            self.assertEqual(["stop", "pass"], guards["point_kinds"])
            self.assertEqual([2, 3], guards["goal_heights"])
            guards["entry_check"](Position(4, 2, .10))
            for pos in (Position(0, 1, 0), Position(4, 3, 0)):
                with self.assertRaisesRegex(ValueError, "stationary start"):
                    guards["entry_check"](pos)
            _, guards = candidate_dispatch(adapter, route, [2, 1], "reverse", "continuous")
            with self.assertRaisesRegex(ValueError, "direction"):
                guards["entry_check"](Position(4, 3, 4))

    def test_direct_slice_refuses_noncontiguous_shortcuts_or_pulse(self):
        route, adapter = self.route()
        for indices in ([], [0, 3], [0, 0], [1, 0], [False, 1]):
            with self.subTest(indices=indices), self.assertRaisesRegex(ValueError, "contiguous"):
                candidate_dispatch(adapter, route, indices, "forward", "continuous")
        with self.assertRaisesRegex(ValueError, "height-aware"):
            candidate_dispatch(adapter, route, [0], "forward", "pulse")

    def test_play_never_approaches_an_adopted_route_through_unknown_space(self):
        route, adapter = self.route()
        with tempfile.TemporaryDirectory() as directory, patch(
                "scripts.physical_waypoints.read_route_context", return_value=CTX):
            checkpoint = Path(directory) / "progress.json"
            def runner(adapter, rows, stop, emit, **opts):
                opts["entry_check"](Position(.75, 1, 0))
                self.fail("Off-route entry reached movement")
            for continuous, message in [(False, "height-aware"), (True, "stationary start")]:
                with self.assertRaisesRegex(ValueError, message):
                    play_route(adapter, route, threading.Event(), lambda event: None, runner=runner,
                               checkpoint=checkpoint, approach_start=True, pass_through=continuous,
                               height_aware=continuous)
                self.assertFalse(checkpoint.exists())

    def test_cached_readiness_checks_direction_height_engine_and_context(self):
        route, adapter = self.route()
        owner = adapter.binding["runtimeIdentity"]
        pose = {"x": 0, "y": 1, "z": 0}
        ready = replay_readiness(route, owner, pose, current_context=CTX, approach_start=True)
        self.assertTrue(ready["forward"]["ready"])
        self.assertIn("direction", ready["reverse"]["reason"])
        for opts, pos in [({"candidate_engine": False, "current_context": CTX}, pose),
                          ({"current_context": None}, pose),
                          ({"current_context": CTX}, dict(pose, x=.75)),
                          ({"current_context": CTX}, dict(pose, y=2))]:
            with self.subTest(opts=opts, pos=pos):
                self.assertFalse(replay_readiness(route, owner, pos, approach_start=True, **opts)["forward"]["ready"])

    def test_resume_refuses_same_geometry_checkpoint_from_different_scope(self):
        route, adapter = self.route()
        owner = adapter.binding["runtimeIdentity"]
        legacy = {key: value for key, value in route.items() if key != "candidateAdoption"}
        pose = {"x": 0, "y": 1, "z": 0}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "progress.json"
            cursor = RouteProgress(legacy, "forward", owner)
            cursor.begin(pose)
            cursor.confirm_arrival(0, cursor.remaining_points()[0])
            cursor.save(checkpoint)
            old = checkpoint.read_bytes()
            readiness = replay_readiness(route, owner, pose, checkpoint, current_context=CTX)
            self.assertIn("different adoption scope", readiness["resume"]["reason"])
            with self.assertRaisesRegex(ValueError, "different adoption scope"):
                play_route(adapter, route, threading.Event(), lambda event: None, runner=None,
                           checkpoint=checkpoint, height_aware=True, pass_through=True, resume=True)
            self.assertEqual(old, checkpoint.read_bytes())

    def test_tk_roundtrip_preserves_adoption_and_edit_cannot_remove_its_guard(self):
        from tests.test_waypoint_cli_gui import GuiBridgeTests
        from scripts.waypoint_candidate_adoption import validate_adopted_route
        gui = GuiBridgeTests()
        self.addCleanup(gui.doCleanups)
        gui.setUp()  # Isolated Tk subprocess and fake RIFT adapter.
        route, _ = self.route()
        route["waypoints"] = [["Enter", 12.0, 24.0], ["Finish", 12.765432, 24.0]]
        route["heights"] = [3.0, 3.0]
        route["pointKinds"] = ["pass", "pass"]
        ctx = gui.call("zone.refresh")["data"]["context"]
        route["routeContext"] = ctx
        meta = route["candidateAdoption"]
        meta["owner"]["unitKey"] = ctx["playerKey"]
        meta["assertedContext"] = ctx
        meta["integritySha256"] = _adoption_digest(route)
        source = gui.root / "candidate.json"
        source.write_text(json.dumps(route), encoding="utf-8")
        loaded = gui.call("route.load", {"file": str(source)})
        self.assertTrue(loaded["ok"], loaded)
        saved = gui.root / "round-trip.json"
        result = gui.call("route.save", {"file": str(saved)})
        self.assertTrue(result["ok"], result)
        round_trip = json.loads(saved.read_text(encoding="utf-8"))
        validate_adopted_route(round_trip, meta["owner"], ctx, "forward")
        edit = gui.call("route.update", {"point": 2, "x": 13.5})
        self.assertTrue(edit["ok"], edit)
        edited = edit["data"]["document"]
        self.assertEqual(meta, edited["candidateAdoption"])
        with self.assertRaisesRegex(ValueError, "integrity"):
            validate_adopted_route(edited, meta["owner"], ctx, "forward")
        self.assertFalse((gui.root / "movement-called").exists())


if __name__ == "__main__":
    unittest.main()
