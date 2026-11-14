import json
from copy import deepcopy
import threading
import tempfile
import unittest
from pathlib import Path

from scripts.waypoint_progress import ProgressError, RouteProgress
from scripts.waypoint_playback import play_route
from unittest.mock import Mock
from types import SimpleNamespace
from scripts.waypoint_replay_readiness import replay_readiness


IDENTITY = {"machine": "AMD-DESKTOP", "gameBuildSha256": "ABCD", "unitKey": "player"}
ROUTE = {"waypoints": [["A", 0, 0], ["B", 3, 0], ["C", 3, 4]]}


class ReplayReadinessTests(unittest.TestCase):
    def checkpoint(self, directory, *, document=ROUTE, direction="forward", arrivals=0):
        path = Path(directory) / "progress.json"
        cursor = RouteProgress(document, direction, IDENTITY)
        endpoint = cursor.ordered_points[0]
        heights = document.get("heights")
        original = 0 if direction == "forward" else len(cursor.ordered_points) - 1
        position = {"x": endpoint[1], "z": endpoint[2]}
        if heights is not None and heights[original] is not None:
            position["y"] = heights[original]
        cursor.begin(position)
        for index in range(arrivals):
            cursor.confirm_arrival(index, cursor.ordered_points[index])
        cursor.save(path)
        return path

    def test_saved_evidence_refusals_match_execution_before_runner(self):
        recorded = {**ROUTE, "recording": {"complete": True, "identity": IDENTITY}}
        documents = []
        for recording in ({"complete": False}, {"complete": True, "identity": None},
                          {"complete": True, "identity": {"runtimeIdentity": None}}):
            documents.append({**ROUTE, "recording": recording})
        for key in ("machine", "gameBuildSha256", "unitKey"):
            documents.append({**ROUTE, "recording": {"complete": True,
                "identity": dict(IDENTITY, **{key: "other"})}})
        measured = {"waypoints": [["A", 0, 0]], "heights": [10], "pointMeasurements": [{
            "version": 1, "kind": "native-player-position", "identity": {"runtimeIdentity": IDENTITY},
            "position": {"x": 0, "y": 10, "z": 0}, "source": "retained.json",
            "observedAtUtc": "2026-11-13T12:00:00+00:00"}]}
        for key in ("machine", "gameBuildSha256", "unitKey"):
            document = deepcopy(measured)
            document["pointMeasurements"][0]["identity"]["runtimeIdentity"][key] = "other"
            documents.append(document)
        malformed = deepcopy(measured)
        malformed["pointMeasurements"][0]["position"]["x"] = 9
        documents.extend([malformed, {**ROUTE, "pointMeasurements": "invalid"}])
        for document in documents:
            with self.subTest(document=document), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "progress.json"
                runner = Mock()
                with self.assertRaises(ProgressError) as refused:
                    play_route(SimpleNamespace(binding={"runtimeIdentity": IDENTITY}), document,
                               threading.Event(), lambda _: None, runner=runner, checkpoint=path)
                result = replay_readiness(document, IDENTITY, {"x": 0, "y": 10, "z": 0}, path,
                                          unavailable_reason="pose is refreshing")
                for action in ("forward", "reverse", "resume"):
                    self.assertFalse(result[action]["ready"])
                    self.assertEqual(str(refused.exception), result[action]["reason"])
                runner.assert_not_called()
                self.assertFalse(path.exists())
        # Same player/build/host remains reusable across a process restart.
        recorded["recording"]["identity"] = dict(IDENTITY, processId=999)
        self.assertTrue(replay_readiness(recorded, IDENTITY, {"x": 0, "z": 0})["forward"]["ready"])
        self.assertTrue(replay_readiness(measured, IDENTITY, {"x": 0, "y": 10, "z": 0})["forward"]["ready"])

    def test_reverse_resume_and_completed_cursor_do_not_mutate_saved_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.checkpoint(directory, direction="reverse", arrivals=1)
            before = path.read_bytes()
            value = replay_readiness(ROUTE, IDENTITY, {"x": 3, "z": 2}, path)["resume"]
            self.assertTrue(value["ready"])
            self.assertEqual(("reverse", 1, "B", 5.0),
                             (value["direction"], value["nextIndex"], value["nextName"], value["remainingDistance"]))
            self.assertEqual((3, 1, False, 2, 3, "C"),
                tuple(value[key] for key in ("pointCount", "completedCount", "complete", "nextPointNumber", "startPointNumber", "startName")))
            self.assertEqual(before, path.read_bytes())
            path = self.checkpoint(directory, direction="reverse", arrivals=3)
            before = path.read_bytes()
            value = replay_readiness(ROUTE, IDENTITY, None, path, "pose unavailable")["resume"]
            self.assertFalse(value["ready"])
            self.assertEqual("route already complete", value["reason"])
            self.assertEqual((3, True, None),
                (value["completedCount"], value["complete"], value["nextPointNumber"]))
            self.assertEqual(before, path.read_bytes())

    def test_endpoint_and_wrong_height_reasons(self):
        result = replay_readiness(ROUTE, IDENTITY, {"x": 0, "z": 0})
        self.assertTrue(result["forward"]["ready"])
        self.assertEqual(("A", 0, 7.0), (result["forward"]["nextName"],
                                         result["forward"]["nextIndex"],
                                         result["forward"]["remainingDistance"]))
        self.assertEqual((1, 1, "A"), tuple(result["forward"][key] for key in
            ("nextPointNumber", "startPointNumber", "startName")))
        self.assertEqual((3, 3, "C"), tuple(result["reverse"][key] for key in
            ("nextPointNumber", "startPointNumber", "startName")))
        self.assertFalse(result["reverse"]["ready"])
        self.assertIn("endpoint", result["reverse"]["reason"])
        self.assertEqual(5.0, result["reverse"]["endpointDistance"])
        self.assertIsNone(result["forward"]["endpointDistance"])
        elevated = {**ROUTE, "heights": [10, 10, 10]}
        wrong = replay_readiness(elevated, IDENTITY, {"x": 0, "y": 12, "z": 0})
        self.assertIn("different height", wrong["forward"]["reason"])

    def test_resume_rejects_off_leg_without_changing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.checkpoint(temporary, arrivals=1)
            before = path.read_bytes()
            result = replay_readiness(ROUTE, IDENTITY, {"x": 2, "z": 1}, path)
            self.assertFalse(result["resume"]["ready"])
            self.assertEqual(("forward", 1, "B"), (result["resume"]["direction"],
                                                    result["resume"]["nextIndex"],
                                                    result["resume"]["nextName"]))
            self.assertIn("unfinished leg", result["resume"]["reason"])
            self.assertEqual(before, path.read_bytes())

    def test_completed_and_missing_checkpoint_are_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.checkpoint(temporary, arrivals=3)
            complete = replay_readiness(ROUTE, IDENTITY, {"x": 3, "z": 4}, path)["resume"]
            self.assertFalse(complete["ready"])
            self.assertEqual((3, None, 0.0), (complete["nextIndex"], complete["nextName"],
                                             complete["remainingDistance"]))
            self.assertIn("complete", complete["reason"])
            missing = replay_readiness(ROUTE, IDENTITY, {"x": 0, "z": 0},
                                       Path(temporary) / "missing.json")["resume"]
            self.assertEqual("no saved playback progress", missing["reason"])

    def test_malformed_and_mismatched_checkpoint_block_without_crashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            malformed = Path(temporary) / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            value = replay_readiness(ROUTE, IDENTITY, {"x": 0, "z": 0}, malformed)["resume"]
            self.assertFalse(value["ready"])
            self.assertIn("cannot load", value["reason"])
            other = self.checkpoint(temporary, document={"waypoints": [["Other", 0, 0]]})
            value = replay_readiness(ROUTE, IDENTITY, {"x": 0, "z": 0}, other)["resume"]
            self.assertFalse(value["ready"])
            self.assertIn("identity changed", value["reason"])

    def test_unavailable_reason_preserves_cursor_details(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.checkpoint(temporary, direction="reverse", arrivals=1)
            result = replay_readiness(ROUTE, IDENTITY, None, path, "pose is refreshing")
            self.assertEqual("pose is refreshing", result["forward"]["reason"])
            self.assertEqual(("reverse", 1, "B"), (result["resume"]["direction"],
                                                    result["resume"]["nextIndex"],
                                                    result["resume"]["nextName"]))
            self.assertEqual("pose is refreshing", result["resume"]["reason"])

    def test_long_route_readiness_and_resume_preserve_cursor_integrity(self):
        route = {"waypoints": [[f"Point {index + 1}", index * 5, 0]
                                for index in range(101)]}
        ready = replay_readiness(route, IDENTITY, {"x": 0, "z": 0})
        self.assertTrue(ready["forward"]["ready"])
        self.assertEqual((101, 500.0),
                         (ready["forward"]["pointCount"], ready["forward"]["remainingDistance"]))
        with tempfile.TemporaryDirectory() as temporary:
            path = self.checkpoint(temporary, document=route, arrivals=40)
            before = path.read_bytes()
            resumed = replay_readiness(route, IDENTITY, {"x": 197.5, "z": 0}, path)["resume"]
            self.assertTrue(resumed["ready"])
            self.assertEqual((40, "Point 41", 302.5),
                             (resumed["completedCount"], resumed["nextName"],
                              resumed["remainingDistance"]))
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
