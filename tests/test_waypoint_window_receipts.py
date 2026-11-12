"""Withdrawn Tk run-receipt callbacks with fake runners and no native input."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests import test_waypoint_recording_window as fixture


@unittest.skipIf(fixture.tk is None, "Tk is unavailable")
class WindowReceiptTests(unittest.TestCase):
    # Reuse the existing withdrawn-root/thread lifecycle without inheriting its
    # recording tests. The only foreground helper here is an inert fake.
    pose = staticmethod(fixture.RecordingWindowTests.pose)
    batch = fixture.RecordingWindowTests.batch
    widgets = fixture.RecordingWindowTests.widgets
    button = fixture.RecordingWindowTests.button
    wait_for = fixture.RecordingWindowTests.wait_for

    def setUp(self):
        fixture.RecordingWindowTests.setUp(self)
        self.no_input.side_effect = lambda *_: SimpleNamespace(close=lambda: None)
        self.result = {"status": "arrived", "position": {"x": 2., "y": 0., "z": 0.},
                       "bearing": 0., "distance": .02, "actions": [{"key": "w", "released": True}],
                       "segments": [{"duration": 25}], "sentinel": "full-result-preserved"}
        self.runner = self.stack.enter_context(patch.object(app, "run_route", side_effect=self.fake_run))
        self.face = self.stack.enter_context(patch.object(app, "run_facing", side_effect=self.turn))
        self.play = self.stack.enter_context(patch("scripts.waypoint_playback.play_route",
                                                  side_effect=self.playback))
        # play_route is imported when launch_window initializes, so install this
        # fake in the callback closure's globals through a fresh launch instead.
        self.close_existing()
        args = SimpleNamespace(expected_host="AMD-DESKTOP", physical_pid=123,
                               initial_adapter=self.adapter, basis=Path("unused"),
                               face_waypoints=True, route=None, auto_reconnect=False)
        app.launch_window(args)
        self.window = self.roots[-1]
        self.wait_for(lambda: str(self.button("Record")["state"]) != "disabled")
        self.table = next(w for w in self.widgets() if isinstance(w, fixture.ttk.Treeview))
        item = self.table.insert("", "end", values=("Goal", "2", "0"))
        self.table.selection_set(item)
        self.window.update()

    def close_existing(self):
        for root in self.roots:
            for callback in root.tk.call("after", "info"):
                root.after_cancel(callback)
            root.destroy()
        for thread in self.threads:
            thread.join(timeout=2)

    def cleanup_windows(self):
        self.no_input.reset_mock()
        fixture.RecordingWindowTests.cleanup_windows(self)

    def fake_run(self, adapter, points, stop, emit, **kwargs):
        emit(self.result)
        return [self.result]

    def turn(self, adapter, stop, emit, **kwargs):
        emit({"status": "faced", "headingError": .2})
        return {"status": "faced", "actions": [{"key": "a"}], "sentinel": "full-turn"}

    def playback(self, adapter, document, stop, emit, **kwargs):
        kwargs["checkpoint"].write_text(json.dumps({"route": document, "direction": "reverse", "nextIndex": 1}))
        emit(self.result)
        return [self.result], SimpleNamespace(next_index=1, ordered_points=document["waypoints"])

    def receipts(self):
        return list((self.root_path / "artifacts").glob("waypoint-run-*.json"))

    def invoke_and_wait(self, label):
        before = len(self.receipts())
        self.button(label).invoke()
        self.wait_for(lambda: len(self.receipts()) > before)
        latest = max(self.receipts(), key=lambda p: p.stat().st_mtime_ns)
        self.wait_for(lambda: any(str(latest) in self.window.getvar(w["textvariable"])
                                 for w in self.widgets() if isinstance(w, fixture.ttk.Label)
                                 and w["textvariable"]))
        return json.loads(latest.read_text())

    def test_successful_go_preserves_full_result_events_binding_and_pulses(self):
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("completed", receipt["status"])
        self.assertEqual([self.result], receipt["result"])
        self.assertEqual([self.result], receipt["completedLegs"])
        self.assertEqual(self.adapter.binding, receipt["calibrationBinding"])
        self.assertEqual(str(self.adapter.input_receipt_path), receipt["inputReceiptPath"])

    def test_walk_and_record_uses_teaching_backend_and_saves_observed_route(self):
        document = {"waypoints": [["Observed start", 0, 0], ["Observed corner", 1, 1]],
                    "recording": {"complete": True, "sampleCount": 12}}
        checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text('{"old":true}')
        with patch("scripts.waypoint_playback.teach_route", return_value=([self.result], document)) as teach:
            receipt = self.invoke_and_wait("Walk + Record")
        self.assertEqual("teach", receipt["operation"])
        self.assertEqual([self.result], receipt["result"])
        args, kwargs = teach.call_args
        self.assertIs(self.adapter, args[0])
        self.assertEqual([("Goal", "2", "0")], args[1])
        self.assertIs(self.runner, kwargs["runner"])
        self.assertTrue(kwargs["face_waypoints"])
        saved = list((self.root_path / "artifacts").glob("recorded-route-*.json"))
        self.assertEqual(1, len(saved))
        self.assertEqual(document, json.loads(saved[0].read_text()))
        snapshot = self.root_path / "artifacts" / "waypoint-last-route.json"
        saved_snapshot = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(document, saved_snapshot["route"])
        self.assertEqual(str(saved[0]), saved_snapshot["sourcePath"])
        self.assertFalse(checkpoint.exists())
        self.assertEqual(["Observed start", "Observed corner"],
                         [self.table.item(i, "values")[0] for i in self.table.get_children()])
        log = next(w for w in self.widgets() if isinstance(w, fixture.tk.Text))
        self.assertIn(str(saved[0]), log.get("1.0", "end"))

    def test_walk_record_stop_and_queued_stop_do_not_publish_or_replace_prior_route(self):
        for queued in (False, True):
            with self.subTest(queued=queued):
                ready, release = threading.Event(), threading.Event()
                checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
                checkpoint.write_text('{"old":true}')
                snapshot = self.root_path / "artifacts" / "waypoint-last-route.json"
                snapshot.write_text('{"waypoints":[["Old",0,0]]}', encoding="utf-8")
                prior_snapshot = snapshot.read_bytes()
                prior_points = [self.table.item(i, "values") for i in self.table.get_children()]

                def teach(adapter, points, stop, emit, **kwargs):
                    emit({"status": "moving", "position": {"x": 1, "y": 0, "z": 0}, "bearing": 0,
                          "recordingProgress": {"sampleCount": 8, "observedPathLength": 1.25}})
                    ready.set()
                    if not release.wait(2):
                        raise AssertionError("fake teaching not released")
                    if not queued:
                        self.assertTrue(stop.is_set(), "teaching STOP must latch controller stop")
                        raise app.Stopped("teaching stopped")
                    return [self.result], {"waypoints": [["New", 0, 0], ["New end", 1, 0]]}

                with patch("scripts.waypoint_playback.teach_route", side_effect=teach):
                    self.button("Walk + Record").invoke()
                    self.assertTrue(ready.wait(1))
                    self.wait_for(lambda: any("Recording: 1.25 / 20 units" in self.window.getvar(w["textvariable"])
                                             and "8 samples" in self.window.getvar(w["textvariable"])
                                             for w in self.widgets() if isinstance(w, fixture.ttk.Label)
                                             and w["textvariable"]))
                    if queued:
                        release.set()
                        for thread in self.threads:
                            thread.join(timeout=2)
                            self.assertFalse(thread.is_alive())
                    self.button("STOP / F8").invoke()
                    release.set()
                    self.wait_for(lambda: all(not t.is_alive() for t in self.threads))
                    # Pump the queued publication/idle events.
                    self.wait_for(lambda: str(self.button("Refresh")["state"]) != "disabled")
                self.assertEqual([], list((self.root_path / "artifacts").glob("recorded-route-*.json")))
                self.assertEqual('{"old":true}', checkpoint.read_text())
                self.assertEqual(prior_snapshot, snapshot.read_bytes())
                self.assertEqual(prior_points, [self.table.item(i, "values") for i in self.table.get_children()])

    def test_walk_record_close_before_queued_publication_discards_document(self):
        checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text('{"old":true}')
        document = {"waypoints": [["New", 0, 0], ["New end", 1, 0]]}
        with patch("scripts.waypoint_playback.teach_route", return_value=([self.result], document)):
            self.button("Walk + Record").invoke()
            for thread in self.threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            # No update() yet: the UI has not published the queued document.
            self.window.tk.call(self.window.protocol("WM_DELETE_WINDOW"))

            def destroyed():
                try:
                    return not self.window.winfo_exists()
                except fixture.tk.TclError:
                    return True

            self.wait_for(destroyed)
        self.assertEqual([], list((self.root_path / "artifacts").glob("recorded-route-*.json")))
        self.assertEqual('{"old":true}', checkpoint.read_text())

    def test_face_and_playback_receipts_keep_operation_and_direction(self):
        face = self.invoke_and_wait("Face Selected")
        self.assertEqual("face", face["operation"])
        self.assertEqual("full-turn", face["result"]["sentinel"])
        self.table.insert("", "end", values=("Unfinished", "3", "0"))
        checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"direction": "reverse", "nextIndex": 1}))
        forward = self.invoke_and_wait("Play Forward")
        self.assertEqual(("play", "forward"), (forward["operation"], forward["direction"]))
        resumed = self.invoke_and_wait("Resume")
        self.assertEqual(("resume", "reverse"), (resumed["operation"], resumed["direction"]))
        self.assertTrue(self.play.call_args.kwargs["resume"])

    def test_stop_retains_original_reason_and_pulse_path(self):
        self.runner.side_effect = app.Stopped("operator stopped this trip")
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("stopped", receipt["status"])
        self.assertEqual("operator stopped this trip", receipt["failure"]["originalReason"])
        self.assertEqual(str(self.adapter.input_receipt_path), receipt["failure"]["inputReceiptPath"])
        verification = receipt["stopVerification"]
        self.assertEqual("pass", verification["status"])
        self.assertEqual(2, len(verification["samples"]))
        self.assertEqual(["fake-native.json"] * 2, [s["source"] for s in verification["samples"]])
        self.assertEqual((0., 0.), (verification["xyzDrift"], verification["yawDriftDegrees"]))
        self.assertEqual((.05, .5), (verification["maxXyzDrift"], verification["maxYawDriftDegrees"]))

    def test_stop_retains_changing_pose_evidence(self):
        self.runner.side_effect = app.Stopped("operator stopped")
        self.adapter.read = Mock(side_effect=[self.pose(0), self.pose(.1)])
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("halted", receipt["status"])
        verification = receipt["stopVerification"]
        self.assertEqual("movement-detected", verification["status"])
        self.assertAlmostEqual(.1, verification["xyzDrift"])
        self.assertEqual([0., .1], [s["position"]["x"] for s in verification["samples"]])
        self.assertEqual(2, self.adapter.read.call_count)

    def test_stop_retains_partial_evidence_when_second_read_unavailable(self):
        self.runner.side_effect = app.Stopped("operator stopped")
        self.adapter.read = Mock(side_effect=[self.pose(0), app.WaypointError("native lease unavailable")])
        receipt = self.invoke_and_wait("Go Selected")
        verification = receipt["stopVerification"]
        self.assertEqual("unavailable", verification["status"])
        self.assertEqual(1, len(verification["samples"]))
        self.assertEqual("native lease unavailable", verification["reason"])
        self.assertIsNone(verification["xyzDrift"])
        self.assertIsNone(verification["yawDriftDegrees"])
        self.assertEqual(2, self.adapter.read.call_count)

    def test_action_failure_retains_reason_and_completed_leg_evidence(self):
        def partial_failure(adapter, points, stop, emit, **kwargs):
            emit(self.result)
            raise app.WaypointError("next leg drifted")

        self.runner.side_effect = partial_failure
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("halted", receipt["status"])
        self.assertEqual("next leg drifted", receipt["failure"]["reason"])
        self.assertEqual([self.result], receipt["completedLegs"])
        self.assertEqual(str(self.adapter.input_receipt_path), receipt["inputReceiptPath"])
        self.assertEqual("pass", receipt["stopVerification"]["status"])
        self.assertIn("after halt", receipt["stopVerification"]["qualification"])

    def test_action_failure_preserves_reason_when_halt_measurement_unavailable(self):
        self.runner.side_effect = app.WaypointError("foreground lost")
        self.adapter.read = Mock(side_effect=ValueError("native unavailable"))
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("halted", receipt["status"])
        self.assertEqual("foreground lost", receipt["failure"]["reason"])
        self.assertEqual("unavailable", receipt["stopVerification"]["status"])
        self.assertEqual(1, self.adapter.read.call_count)

    def test_refresh_error_does_not_measure_halt(self):
        self.adapter.read = Mock(side_effect=ValueError("native unavailable"))
        with patch.object(app, "verify_stopped_pose") as verify:
            self.button("Refresh").invoke()
            self.wait_for(lambda: str(self.button("Refresh")["state"]) != "disabled")
        verify.assert_not_called()

    def test_rejected_action_does_not_reference_previous_input_receipt(self):
        previous = self.invoke_and_wait("Go Selected")
        self.runner.side_effect = app.WaypointError("wrong endpoint")
        rejected = self.invoke_and_wait("Go Selected")
        self.assertNotEqual(previous["inputReceiptPath"], rejected["inputReceiptPath"])
        self.assertFalse(rejected["inputReceiptPresent"])
        self.assertFalse(Path(rejected["inputReceiptPath"]).exists())

    def test_write_failure_remains_visible_with_original_action_failure(self):
        self.runner.side_effect = app.WaypointError("blocked by drift")
        original = Path.write_text

        def fail_receipt(path, *args, **kwargs):
            if path.name.startswith("waypoint-run-"):
                raise OSError("disk write denied")
            return original(path, *args, **kwargs)

        with patch.object(Path, "write_text", fail_receipt):
            self.button("Go Selected").invoke()
            self.wait_for(lambda: str(self.button("Record")["state"]) != "disabled")
        labels = [self.window.getvar(w["textvariable"]) for w in self.widgets()
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        self.assertTrue(any("blocked by drift" in text and "disk write denied" in text for text in labels))
        self.assertEqual([], self.receipts())


if __name__ == "__main__":
    unittest.main()
