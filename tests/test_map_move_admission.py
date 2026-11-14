"""Owned-map movement admission is independent of game mouse dispatch."""
from copy import deepcopy
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_map import LocalMap


class MapMoveAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                         "unitKey": "123", "processId": 45}
        self.adapter = SimpleNamespace(binding={"runtimeIdentity": deepcopy(self.identity)})
        self.payload = {"view": LocalMap(10, 20, -170, 330, 220, 10),
                        "x": 12, "z": 24, "owner": deepcopy(self.identity)}

    def test_validated_view_origin_is_forwarded_for_native_race_recheck(self):
        mover = Mock(return_value={"status": "arrived"})
        pose = app.Snapshot(app.Position(10, 2, 20), -170, time.monotonic(), "fake")
        stop = threading.Event()
        with patch.object(app, "read_stationary", return_value=pose):
            result = app.run_map_move(self.adapter, self.payload, stop, mover=mover)
        self.assertEqual("arrived", result["status"])
        self.assertEqual({"x": 10, "z": 20, "bearing": -170}, mover.call_args.kwargs["expected_origin"])

    def test_changed_pose_or_map_owner_never_reaches_movement_backend(self):
        for mismatch in ("position", "bearing", "owner"):
            with self.subTest(mismatch=mismatch):
                payload = deepcopy(self.payload)
                if mismatch == "owner": payload["owner"]["processId"] = 99
                pose = app.Snapshot(app.Position(10.1 if mismatch == "position" else 10, 2, 20),
                                    -168 if mismatch == "bearing" else -170, time.monotonic(), "fake")
                mover = Mock()
                with patch.object(app, "read_stationary", return_value=pose), self.assertRaises(ValueError):
                    app.run_map_move(self.adapter, payload, threading.Event(), mover=mover)
                mover.assert_not_called()


if __name__ == "__main__": unittest.main()
