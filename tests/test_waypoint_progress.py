import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.waypoint_progress import (ProgressError, RouteProgress, invalidate_route_progress,
                                       select_route_progress, write_json_atomic)
from scripts.waypoint_limits import MAX_ROUTE_DISTANCE, MAX_WAYPOINTS


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
        self.assertEqual(22, RouteProgress(long_route, identity=IDENTITY).begin({"x": 0, "z": 0}))
        too_long = {"waypoints": [["a", 0, 0], ["b", MAX_ROUTE_DISTANCE + 1, 0]]}
        with self.assertRaisesRegex(ProgressError, f"{MAX_ROUTE_DISTANCE:g} world"):
            RouteProgress(too_long, identity=IDENTITY)

    def test_more_than_twenty_waypoints_and_resume_hash_compatibility(self):
        route = {"waypoints": [[f"P{i}", i, 0] for i in range(25)]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            cursor = RouteProgress(route, identity=IDENTITY)
            self.assertEqual(24, cursor.begin({"x": 0, "z": 0}))
            cursor.confirm_arrival(0, cursor.ordered_points[0])
            cursor.save(path)
            resumed = RouteProgress.load(path, route, IDENTITY)
            self.assertEqual((1, cursor.route_hash), (resumed.next_index, resumed.route_hash))
        self.assertEqual(RouteProgress(ROUTE, identity=IDENTITY).route_hash,
                         "c84c8058a83e1c62e28e5ec609c3aa222e4e262b2df24ea36ba5699f6c67eb2a")

    def test_waypoint_count_limit(self):
        accepted = {"waypoints": [[f"P{i}", i, 0] for i in range(MAX_WAYPOINTS)]}
        self.assertEqual(MAX_WAYPOINTS, len(RouteProgress(accepted, identity=IDENTITY).points))
        with self.assertRaisesRegex(ProgressError, f"1-{MAX_WAYPOINTS}"):
            RouteProgress({"waypoints": accepted["waypoints"] + [["extra", 0, 0]]}, identity=IDENTITY)

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

    def test_transient_atomic_write_omits_fsync_but_default_stays_durable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            with patch("scripts.waypoint_progress.os.fsync") as sync:
                write_json_atomic(path, {"value": "saved"})
                sync.assert_called_once()
                sync.reset_mock()
                real_replace = os.replace
                def check_replace(source, target):
                    self.assertEqual({"value": "saved"}, json.loads(path.read_text(encoding="utf-8")))
                    self.assertEqual({"value": "fresh"}, json.loads(Path(source).read_text(encoding="utf-8")))
                    real_replace(source, target)
                with patch("scripts.waypoint_progress.os.replace", side_effect=check_replace) as replace:
                    write_json_atomic(path, {"value": "fresh"}, durable=False)
                sync.assert_not_called()
                replace.assert_called_once()
            self.assertEqual({"value": "fresh"}, json.loads(path.read_text(encoding="utf-8")))
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


class RouteSelectionTests(unittest.TestCase):
    other = {"waypoints": [["Other", 3, 0]]}

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.active = Path(temp.name) / "waypoint-current-progress.json"
        self.archive = self.active.parent / "waypoint-progress"
        self.cursor = RouteProgress(ROUTE, "reverse", IDENTITY)
        self.cursor.begin({"x": 3.1, "z": 4, "y": 8})
        self.cursor.confirm_arrival(0, self.cursor.ordered_points[0])
        self.cursor.save(self.active)

    def select(self, document, identity=IDENTITY):
        return select_route_progress(self.active, self.archive, document, identity)

    def test_return_to_stopped_reverse_and_consume_archive(self):
        original = self.active.read_bytes()
        self.assertEqual(1, self.select(ROUTE).next_index)
        self.assertEqual(original, self.active.read_bytes())
        self.assertFalse(self.archive.exists())
        self.assertIsNone(self.select(self.other))
        self.assertFalse(self.active.exists())
        other = RouteProgress(self.other, "forward", IDENTITY)
        other.begin({"x": 3, "z": 0})
        other.save(self.active)
        restored = self.select(ROUTE, {**IDENTITY, "machine": "amd-desktop"})
        self.assertEqual(("reverse", 1, self.cursor.start), (restored.direction, restored.next_index, restored.start))
        self.assertEqual(original, self.active.read_bytes())
        self.assertEqual(1, len(list(self.archive.glob("*.json"))))  # Only the other route remains.
        invalidate_route_progress(self.active, self.archive, ROUTE, IDENTITY)
        self.assertIsNone(self.select(ROUTE))
        self.assertEqual("forward", self.select(self.other).direction)

    def test_changed_route_or_player_never_restores_original(self):
        for changed in ({"waypoints": [["Z", 0, 0], *ROUTE["waypoints"][1:]]},
                        {"waypoints": [["A", 1, 0], *ROUTE["waypoints"][1:]]},
                        {"waypoints": list(reversed(ROUTE["waypoints"]))},
                        {**ROUTE, "heights": [9, 9, 9]}):
            with self.subTest(document=changed):
                self.assertIsNone(self.select(changed))
        for key in ("machine", "gameBuildSha256", "unitKey"):
            with self.subTest(key=key):
                other_identity = {**IDENTITY, key: "different"}
                self.assertIsNone(self.select(ROUTE, other_identity))
                invalidate_route_progress(self.active, self.archive, ROUTE, other_identity)
        self.assertEqual(1, self.select(ROUTE).next_index)

    def test_unknown_identity_shelves_and_never_promotes(self):
        self.assertIsNone(self.select(ROUTE, None))
        self.assertFalse(self.active.exists())
        self.assertIsNone(self.select(ROUTE, None))
        invalidate_route_progress(self.active, self.archive, ROUTE, None)
        self.assertEqual(1, self.select(ROUTE).next_index)

    def test_new_completed_cursor_supersedes_older_archive(self):
        self.select(self.other)
        for i in (1, 2):
            self.cursor.confirm_arrival(i, self.cursor.ordered_points[i])
        self.cursor.save(self.active)
        self.select(self.other)
        restored = self.select(ROUTE)
        self.assertEqual([], restored.remaining_points())

    def test_archive_write_failure_preserves_active(self):
        before = self.active.read_bytes()
        with patch("scripts.waypoint_progress.os.replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.select(self.other)
        self.assertEqual(before, self.active.read_bytes())
        self.assertEqual([], list(self.archive.iterdir()))

    def test_concurrently_changed_active_is_never_removed(self):
        def archive_then_advance(path, payload):
            write_json_atomic(path, payload)
            self.cursor.confirm_arrival(1, self.cursor.ordered_points[1])
            updated = {**payload, "nextIndex": self.cursor.next_index}
            write_json_atomic(self.active, updated)
        with patch("scripts.waypoint_progress.write_json_atomic", side_effect=archive_then_advance):
            with self.assertRaisesRegex(ProgressError, "changed during route switch"):
                self.select(self.other)
        self.assertEqual(2, RouteProgress.load(self.active, ROUTE, IDENTITY).next_index)

    def test_invalid_archive_never_promotes(self):
        self.select(self.other)
        slot, = self.archive.glob("*.json")
        corrupt = json.loads(slot.read_bytes())
        corrupt["nextIndex"] = 99
        write_json_atomic(slot, corrupt)
        self.assertIsNone(self.select(ROUTE))
        self.assertFalse(self.active.exists())

    def test_promotion_failure_keeps_displaced_and_incoming_checkpoints(self):
        self.select(self.other)
        other = RouteProgress(self.other, identity=IDENTITY)
        other.begin({"x": 3, "z": 0})
        other.save(self.active)
        before = self.active.read_bytes()
        real_replace = os.replace

        def fail_promotion(source, target):
            if target == self.active:
                raise OSError("file in use")
            return real_replace(source, target)

        with patch("scripts.waypoint_progress.os.replace", side_effect=fail_promotion):
            with self.assertRaisesRegex(OSError, "file in use"):
                self.select(ROUTE)
        self.assertEqual(before, self.active.read_bytes())
        self.assertEqual(1, self.select(ROUTE).next_index)

    def test_invalidation_only_removes_selected_route_and_owner(self):
        self.select(self.other)
        other = RouteProgress(self.other, identity=IDENTITY)
        other.begin({"x": 3, "z": 0})
        other.save(self.active)
        before = self.active.read_bytes()
        invalidate_route_progress(self.active, self.archive, ROUTE, IDENTITY)
        self.assertEqual(before, self.active.read_bytes())
        self.assertIsNone(self.select(ROUTE))
        self.assertEqual(0, self.select(self.other).next_index)


if __name__ == "__main__":
    unittest.main()
