import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.waypoint_progress import ProgressError, RouteProgress, write_json_atomic


IDENTITY = {"machine": "AMD-DESKTOP", "gameBuildSha256": "ABCD", "unitKey": "player"}
ROUTE = {"waypoints": [["A", 0, 0], ["B", 3, 0], ["C", 3, 4]]}


class ProgressTests(unittest.TestCase):
    def test_forward_and_reverse_order_and_cursor(self):
        for direction, initial, order in (("forward", {"x": 0, "z": 0}, ["A", "B", "C"]),
                                          ("reverse", {"x": 3, "z": 4}, ["C", "B", "A"])):
            with self.subTest(direction=direction):
                p = RouteProgress(ROUTE, direction, IDENTITY)
                self.assertEqual([row[0] for row in p.ordered_points], order)
                p.begin(initial)
                for index, point in enumerate(p.ordered_points):
                    p.confirm_arrival(index, point)
                self.assertEqual(p.remaining_points(), [])
                with self.assertRaises(ProgressError):
                    p.begin(initial)

    def test_cursor_and_goal_must_match(self):
        p = RouteProgress(ROUTE, identity=IDENTITY)
        p.begin({"x": 0, "z": 0})
        with self.assertRaises(ProgressError):
            p.confirm_arrival(1, p.ordered_points[1])
        with self.assertRaises(ProgressError):
            p.confirm_arrival(0, p.ordered_points[1])
        self.assertEqual(p.next_index, 0)

    def test_persist_resume_and_identity_route_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            p = RouteProgress(ROUTE, identity=IDENTITY)
            p.begin({"x": 0.1, "z": 0, "y": 8})
            p.confirm_arrival(0, p.ordered_points[0])
            p.save(path)
            q = RouteProgress.load(path, ROUTE, {**IDENTITY, "machine": "amd-desktop", "gameBuildSha256": "abcd"})
            self.assertEqual(q.next_index, 1)
            self.assertEqual(q.start["x"], 0.1)
            q.begin({"x": 2, "z": 0.2, "y": 8})
            with self.assertRaisesRegex(ProgressError, "unfinished leg"):
                q.begin({"x": 2, "z": 1})
            with self.assertRaises(ProgressError):
                RouteProgress.load(path, ROUTE, {**IDENTITY, "unitKey": "other"})
            with self.assertRaises(ProgressError):
                RouteProgress.load(path, {"waypoints": [["A", 0, 0], ["B", 4, 0]]}, IDENTITY)

    def test_initial_near_endpoint_and_resume_endcaps(self):
        p = RouteProgress(ROUTE, identity=IDENTITY)
        with self.assertRaises(ProgressError):
            p.begin({"x": 0.31, "z": 0})
        p.begin({"x": 0, "z": 0})
        p.confirm_arrival(0, p.ordered_points[0])
        p.begin({"x": 3.4, "z": 0})
        with self.assertRaises(ProgressError):
            p.begin({"x": 3.51, "z": 0})

    def test_height_and_remaining_distance(self):
        p = RouteProgress({**ROUTE, "heights": [10, 10, 10]}, identity=IDENTITY)
        with self.assertRaises(ProgressError):
            p.begin({"x": 0, "z": 0})
        with self.assertRaises(ProgressError):
            p.begin({"x": 0, "z": 0, "y": 12})
        p.begin({"x": 0, "z": 0, "y": 10})
        long_route = {"waypoints": [["a", 0, 0], ["b", 11, 0], ["c", 22, 0]]}
        with self.assertRaisesRegex(ProgressError, "20 world"):
            RouteProgress(long_route, identity=IDENTITY).begin({"x": 0, "z": 0})

    def test_failed_atomic_replace_preserves_previous_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            p = RouteProgress(ROUTE, identity=IDENTITY)
            p.begin({"x": 0, "z": 0})
            p.save(path)
            p.confirm_arrival(0, p.ordered_points[0])
            with patch("scripts.waypoint_progress.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    p.save(path)
            self.assertEqual(RouteProgress.load(path, ROUTE, IDENTITY).next_index, 0)
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_atomic_route_write_preserves_old_file_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "route.json"
            original = {**ROUTE, "recording": {"complete": True}}
            write_json_atomic(path, original)
            before = path.read_bytes()
            for operation in ("fsync", "replace"):
                with self.subTest(operation=operation), \
                     patch(f"scripts.waypoint_progress.os.{operation}", side_effect=OSError("interrupted")):
                    with self.assertRaises(OSError):
                        write_json_atomic(path, {"waypoints": [["Changed", 1, 2]]})
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(original, json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual([path], list(Path(temp).iterdir()))

    def test_invalid_checkpoint_cursor(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            p = RouteProgress(ROUTE, identity=IDENTITY)
            p.begin({"x": 0, "z": 0})
            p.save(path)
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["nextIndex"] = True
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ProgressError):
                RouteProgress.load(path, ROUTE, IDENTITY)

    def test_checkpoint_round_trips_recording_metadata_and_heights(self):
        document = {**ROUTE, "heights": [10, 11, 12],
                    "recording": {"complete": True, "sources": ["native-report"], "sampleCount": 9}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            p = RouteProgress(document, identity=IDENTITY)
            p.begin({"x": 0, "z": 0, "y": 10})
            p.save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["route"], document)
            # Geometry identifies the route; checkpoint metadata stays authoritative.
            loaded = RouteProgress.load(path, {**document, "recording": {"different": True}}, IDENTITY)
            self.assertEqual(loaded.document, document)
            loaded.save(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["route"], document)


if __name__ == "__main__":
    unittest.main()
