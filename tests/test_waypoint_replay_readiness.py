import json
import tempfile
import unittest
from pathlib import Path

from scripts.waypoint_progress import RouteProgress
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

    def test_endpoint_and_wrong_height_reasons(self):
        result = replay_readiness(ROUTE, IDENTITY, {"x": 0, "z": 0})
        self.assertTrue(result["forward"]["ready"])
        self.assertEqual(("A", 0, 7.0), (result["forward"]["nextName"],
                                         result["forward"]["nextIndex"],
                                         result["forward"]["remainingDistance"]))
        self.assertFalse(result["reverse"]["ready"])
        self.assertIn("endpoint", result["reverse"]["reason"])
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


if __name__ == "__main__":
    unittest.main()
