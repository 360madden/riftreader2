import json
from pathlib import Path
import tempfile
import unittest

from scripts.waypoint_marker_progress import read_marker_progress
from scripts.waypoint_progress import RouteProgress


class MarkerProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "progress.json"
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "ABC", "unitKey": "player"}
        self.document = {"waypoints": [["A", 0, 0], ["B", 1, 0], ["C", 1, 1]],
                         "heights": [10, 10, 10], "recording": {"complete": True}}

    def save(self, direction, completed):
        progress = RouteProgress(self.document, direction, self.identity)
        start = progress.ordered_points[0]
        progress.begin({"x": start[1], "z": start[2], "y": 10})
        for index in range(completed):
            progress.confirm_arrival(index, progress.ordered_points[index])
        progress.save(self.path)

    def test_forward_reverse_and_complete_mapping(self):
        for direction, completed, expected, number in (
                ("forward", 1, {1: "completed", 2: "next", 3: "pending"}, 2),
                ("reverse", 1, {3: "completed", 2: "next", 1: "pending"}, 2),
                ("reverse", 3, {3: "completed", 2: "completed", 1: "completed"}, None)):
            with self.subTest(direction=direction, completed=completed):
                self.save(direction, completed)
                result = read_marker_progress(self.path, self.document, self.identity)
                self.assertEqual("saved-progress-candidate", result["status"])
                self.assertEqual((direction, completed, 3, number),
                                 (result["direction"], result["nextIndex"], result["pointCount"], result["nextNumber"]))
                self.assertEqual(expected, result["states"])

    def test_mismatch_and_malformed_never_guess(self):
        self.save("forward", 1)
        before = self.path.read_bytes()
        for identity in ({**self.identity, "unitKey": "other"},
                         {**self.identity, "gameBuildSha256": "other"},
                         {**self.identity, "machine": "other"}):
            result = read_marker_progress(self.path, self.document, identity)
            self.assertEqual("unavailable", result["status"])
            self.assertNotIn("states", result)
        changed = {**self.document, "waypoints": [["A", 0, 0], ["B", 2, 0], ["C", 1, 1]]}
        self.assertEqual("unavailable", read_marker_progress(self.path, changed, self.identity)["status"])
        self.assertEqual(before, self.path.read_bytes())
        payload = json.loads(before)
        for value in (True, -1, 4):
            payload["nextIndex"] = value
            self.path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual("unavailable", read_marker_progress(self.path, self.document, self.identity)["status"])
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual("unavailable", read_marker_progress(self.path, self.document, self.identity)["status"])
        self.path.unlink()
        self.assertEqual("unavailable", read_marker_progress(self.path, self.document, self.identity)["status"])

    def test_invalid_or_changed_direction_is_unavailable(self):
        self.save("forward", 1)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for direction in ("reverse", "sideways"):
            payload["direction"] = direction
            self.path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual("unavailable", read_marker_progress(self.path, self.document, self.identity)["status"])


if __name__ == "__main__":
    unittest.main()
