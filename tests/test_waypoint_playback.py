"""Integration tests of recording and checkpoint playback with simulated motion."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.movement_controller import Position
from scripts.physical_waypoints import Stopped, run_route
from scripts.waypoint_playback import play_route, teach_route
from scripts.waypoint_progress import ProgressError
from tests.test_physical_waypoints import SimulatedRift


class BoundSim(SimulatedRift):
    binding = {"runtimeIdentity": {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                                   "unitKey": "123", "processId": 20}}


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkpoint = Path(self.temp.name) / "progress.json"

    def test_teach_l_then_reverse_reaches_recorded_start(self):
        sim = BoundSim()
        legs, document = teach_route(sim, [("Corner", 1.5, 0), ("End", 1.5, 1.5)],
                                     threading.Event(), lambda _: None, runner=run_route,
                                     face_waypoints=False)
        self.assertEqual(len(legs), 2)
        points = document["waypoints"]
        self.assertGreaterEqual(len(points), 3)
        self.assertTrue(any(abs(p[1] - 1.5) <= .3 and abs(p[2]) <= .3 for p in points[1:-1]))
        endpoint = sim.position
        _, cursor = play_route(sim, document, threading.Event(), lambda _: None,
                               runner=run_route, checkpoint=self.checkpoint,
                               direction="reverse", face_waypoints=False)
        self.assertEqual(cursor.ordered_points, [tuple(p) for p in reversed(points)])
        self.assertEqual(cursor.next_index, len(points))
        self.assertLessEqual(((sim.position.x - points[0][1]) ** 2 + (sim.position.z - points[0][2]) ** 2) ** .5, .3)
        self.assertGreater(abs(endpoint.x - sim.position.x) + abs(endpoint.z - sim.position.z), 1)

    def test_stop_after_pulse_preserves_unfinished_leg_then_resumes(self):
        stop = threading.Event()
        sim = BoundSim(stop_after=stop)
        document = {"waypoints": [["Start", 0, 0], ["Corner", 1.5, 0], ["End", 1.5, 1.5]]}
        with self.assertRaises(Stopped):
            play_route(sim, document, stop, lambda _: None, runner=run_route,
                       checkpoint=self.checkpoint, face_waypoints=False)
        payload = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(payload["nextIndex"], 1)
        self.assertEqual(len(sim.calls), 1)
        stop.clear(); sim.stop_after = None
        _, cursor = play_route(sim, document, stop, lambda _: None, runner=run_route,
                               checkpoint=self.checkpoint, resume=True, face_waypoints=False)
        self.assertEqual(cursor.next_index, 3)
        self.assertLessEqual(((sim.position.x - 1.5) ** 2 + (sim.position.z - 1.5) ** 2) ** .5, .3)

    def test_recording_identity_mismatch_rejected_before_runner(self):
        for key, value in (("machine", "OTHER"), ("gameBuildSha256", "b" * 64), ("unitKey", "999")):
            with self.subTest(key=key):
                identity = dict(BoundSim.binding["runtimeIdentity"], **{key: value})
                document = {"waypoints": [["Start", 0, 0]],
                            "recording": {"complete": True, "identity": {"runtimeIdentity": identity}}}
                runner = Mock()
                with self.assertRaises(ProgressError):
                    play_route(BoundSim(), document, threading.Event(), lambda _: None,
                               runner=runner, checkpoint=self.checkpoint)
                runner.assert_not_called()

    def test_same_stable_identity_new_process_is_allowed(self):
        identity = dict(BoundSim.binding["runtimeIdentity"], processId=99, processStartUtcTicks="old")
        document = {"waypoints": [["Start", 0, 0]],
                    "recording": {"complete": True, "identity": {"runtimeIdentity": identity}}}
        sim = BoundSim()
        _, cursor = play_route(sim, document, threading.Event(), lambda _: None, runner=run_route,
                               checkpoint=self.checkpoint, face_waypoints=False)
        self.assertEqual(cursor.next_index, 1)
        self.assertEqual(sim.calls, [])

    def test_arrival_on_wrong_floor_does_not_advance_checkpoint(self):
        document = {"waypoints": [["Start", 0, 0]], "heights": [10]}
        def wrong_floor_runner(adapter, points, stop, emit, *, entry_check, **kwargs):
            entry_check(Position(0, 10, 0))
            emit({"status": "arrived", "name": "Start", "goal": {"x": 0, "y": 10, "z": 0},
                  "position": {"x": 0, "y": 12, "z": 0}})
            self.fail("wrong-floor arrival was accepted")
        with self.assertRaisesRegex(ProgressError, "different height"):
            play_route(BoundSim(), document, threading.Event(), lambda _: None,
                       runner=wrong_floor_runner, checkpoint=self.checkpoint)
        payload = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(payload["nextIndex"], 0)

    def test_off_route_or_changed_route_resume_refused_before_input(self):
        stop = threading.Event(); sim = BoundSim(stop_after=stop)
        document = {"waypoints": [["Start", 0, 0], ["End", 1.5, 0]]}
        with self.assertRaises(Stopped):
            play_route(sim, document, stop, lambda _: None, runner=run_route,
                       checkpoint=self.checkpoint, face_waypoints=False)
        stop.clear(); sim.stop_after = None
        prior = len(sim.calls)
        changed = {"waypoints": [["Start", 0, 0], ["End", 1.6, 0]]}
        with self.assertRaises(ProgressError):
            play_route(sim, changed, stop, lambda _: None, runner=run_route,
                       checkpoint=self.checkpoint, resume=True, face_waypoints=False)
        self.assertEqual(len(sim.calls), prior)
        sim.position = Position(.4, 10, 2)
        with self.assertRaises(ProgressError):
            play_route(sim, document, stop, lambda _: None, runner=run_route,
                       checkpoint=self.checkpoint, resume=True, face_waypoints=False)
        self.assertEqual(len(sim.calls), prior)


if __name__ == "__main__": unittest.main()
