"""Integration tests of recording and checkpoint playback with simulated motion."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.movement_controller import Position
from scripts.physical_waypoints import Stopped, run_route
from scripts.waypoint_playback import assess_start_approach, play_route, teach_route
from scripts.waypoint_progress import ProgressError, RouteProgress
from tests.test_physical_waypoints import SimulatedRift


class BoundSim(SimulatedRift):
    binding = {"runtimeIdentity": {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                                   "unitKey": "123", "processId": 20}}


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkpoint = Path(self.temp.name) / "progress.json"

    def measured_document(self, **changes):
        identity = dict(BoundSim.binding["runtimeIdentity"], processId=99, processStartUtcTicks="99", **changes)
        return {"waypoints": [["Saved current", 0, 0]], "heights": [10],
                "pointMeasurements": [{"version": 1, "kind": "native-player-position",
                    "identity": {"runtimeIdentity": identity}, "position": {"x": 0, "y": 10, "z": 0},
                    "source": "retained-native-pose.json", "observedAtUtc": "2026-11-12T20:00:00+00:00"}]}

    def test_measured_point_identity_and_invalid_provenance_refuse_before_runner(self):
        documents = [self.measured_document(**{key: value}) for key, value in (
            ("machine", "OTHER"), ("gameBuildSha256", "b" * 64), ("unitKey", "999"))]
        malformed = self.measured_document()
        malformed["pointMeasurements"][0]["position"]["x"] = 2
        documents.append(malformed)
        malformed = self.measured_document()
        malformed["pointMeasurements"] = "invalid"
        documents.append(malformed)
        for document in documents:
            with self.subTest(document=document):
                runner = Mock()
                with self.assertRaises(ProgressError):
                    play_route(BoundSim(), document, threading.Event(), lambda _: None,
                               runner=runner, checkpoint=self.checkpoint)
                runner.assert_not_called()
                self.assertFalse(self.checkpoint.exists())

    def test_measured_point_reuses_stable_identity_without_retagging_old_epoch(self):
        document = self.measured_document()
        document["waypoints"].append(["Manual", .1, 0])
        document["heights"].append(None)
        document["pointMeasurements"].append(None)
        sim = BoundSim()
        _, cursor = play_route(sim, document, threading.Event(), lambda _: None,
                               runner=run_route, checkpoint=self.checkpoint, face_waypoints=False)
        self.assertEqual(cursor.next_index, 2)
        self.assertEqual(document["pointMeasurements"][0]["identity"]["runtimeIdentity"]["processId"], 99)
        self.assertIsNone(document["heights"][1])

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

    def test_forward_and_reverse_approach_share_one_runner_and_confirm_real_endpoint_once(self):
        doc = {"waypoints": [["A", 0, 0], ["B", 2, 0]], "heights": [10, 10.5]}
        for direction in ("forward", "reverse"):
            with self.subTest(direction=direction):
                order = doc["waypoints"] if direction == "forward" else doc["waypoints"][::-1]
                self.checkpoint.write_bytes(b"existing progress")
                sim = BoundSim()
                sim.position = Position(order[0][1] + 4, 10, 0)
                events = []
                def report(event):
                    events.append(event)
                    if event["status"] == "approaching-route":
                        self.assertEqual(self.checkpoint.read_bytes(), b"existing progress")
                        self.assertEqual(event["approachDistance"], 4)
                    if event["status"] == "route-approach-complete":
                        self.assertEqual(json.loads(self.checkpoint.read_bytes())["nextIndex"], 1)
                def runner(adapter, points, stop, emit, **opts):
                    self.assertEqual(points, [tuple(row) for row in order])
                    return run_route(adapter, points, stop, emit, **opts)
                wrapped = Mock(side_effect=runner)
                legs, cursor = play_route(sim, doc, threading.Event(), report, runner=wrapped,
                    checkpoint=self.checkpoint, direction=direction,
                    approach_start=True, face_waypoints=False)
                wrapped.assert_called_once()
                self.assertEqual(cursor.next_index, 2)
                self.assertEqual(len(legs), 2)
                self.assertEqual([e["name"] for e in events if e["status"]=="arrived"], [r[0] for r in order])
                self.assertEqual([e["nextWaypoint"] for e in events if e["status"]=="route-approach-complete"], [1])

    def test_approach_stop_or_missing_release_preserves_previous_checkpoint(self):
        doc = {"waypoints": [["A", 0, 0]], "heights": [10]}
        prior = b"previous checkpoint"
        self.checkpoint.write_bytes(prior)
        for mode in ("stop", "missing", "keys-down", "stopped-on-arrival", "outside-radius"):
            with self.subTest(mode=mode):
                stop = threading.Event()
                sim = BoundSim(stop_after=stop if mode=="stop" else None)
                sim.position = Position(4, 10, 0)
                def runner(adapter, points, signal, emit, *, entry_check, **opts):
                    if mode == "stop":
                        return run_route(adapter, points, signal, emit, entry_check=entry_check, **opts)
                    entry_check(sim.position)
                    event = {"status":"arrived","name":"A","goal":{"x":0,"z":0},
                             "position":{"x":.31 if mode=="outside-radius" else 0,"z":0,"y":10}}
                    if mode != "missing":
                        event.update(releaseSucceeded=True, desktopInputsDown=["w"] if mode=="keys-down" else [])
                    if mode == "stopped-on-arrival": signal.set()
                    emit(event)
                with self.assertRaises((Stopped, ProgressError)):
                    play_route(sim, doc, stop, lambda _: None, runner=runner, checkpoint=self.checkpoint,
                               approach_start=True, face_waypoints=False)
                self.assertEqual(self.checkpoint.read_bytes(), prior)

    def test_approach_readiness_and_execution_share_distance_height_and_route_budget(self):
        for x, y, end, reason in [(20.01,10,0,"approach limit"), (4,11.51,0,"height"),
                                  (-4,10,998,"1000")]:
            with self.subTest(x=x,y=y,end=end):
                doc = {"waypoints":[["A",0,0],["B",end,0]],"heights":[10,10]}
                sim = BoundSim()
                sim.position = Position(x,y,0)
                cursor = RouteProgress(doc, "forward", sim.binding["runtimeIdentity"])
                with self.assertRaisesRegex(ProgressError, reason):
                    assess_start_approach(cursor, {"x":x,"y":y,"z":0})
                self.assertIsNone(cursor.start)
                with self.assertRaisesRegex(ProgressError, reason):
                    play_route(sim, doc, threading.Event(), lambda _: None, runner=run_route,
                               checkpoint=self.checkpoint, approach_start=True)
                self.assertEqual(sim.calls, [])
                self.assertFalse(self.checkpoint.exists())

    def test_near_start_and_resume_do_not_add_approach(self):
        doc = {"waypoints":[["A",0,0],["B",5,0]], "heights":[10,10]}
        sim = BoundSim()
        sim.position = Position(.29,10,0)
        events = []
        def stop_after_enter(_adapter, _points, _stop, _emit, *, entry_check, **_kwargs):
            entry_check(sim.position)
            raise Stopped("end test")
        with self.assertRaises(Stopped):
            play_route(sim, doc, threading.Event(), events.append, runner=stop_after_enter,
                       checkpoint=self.checkpoint, approach_start=True)
        self.assertEqual(json.loads(self.checkpoint.read_bytes())["nextIndex"], 0)
        before = self.checkpoint.read_bytes()
        sim.position = Position(4,10,0)
        with self.assertRaisesRegex(ProgressError, "unfinished leg"):
            play_route(sim, doc, threading.Event(), events.append, runner=stop_after_enter,
                       checkpoint=self.checkpoint, resume=True, approach_start=True)
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.assertFalse(events)

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
