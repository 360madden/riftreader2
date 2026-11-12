"""Withdrawn Tk run-receipt callbacks with fake runners and no native input."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
        emit(self.result)
        return [self.result], SimpleNamespace(next_index=1, ordered_points=document["waypoints"])

    def receipts(self):
        return list((self.root_path / "artifacts").glob("waypoint-run-*.json"))

    def invoke_and_wait(self, label):
        before = len(self.receipts())
        self.button(label).invoke()
        self.wait_for(lambda: len(self.receipts()) > before)
        self.wait_for(lambda: str(self.button("Record")["state"]) != "disabled")
        return json.loads(max(self.receipts(), key=lambda p: p.stat().st_mtime_ns).read_text())

    def test_successful_go_preserves_full_result_events_binding_and_pulses(self):
        receipt = self.invoke_and_wait("Go Selected")
        self.assertEqual("completed", receipt["status"])
        self.assertEqual([self.result], receipt["result"])
        self.assertEqual([self.result], receipt["completedLegs"])
        self.assertEqual(self.adapter.binding, receipt["calibrationBinding"])
        self.assertEqual(str(self.adapter.input_receipt_path), receipt["inputReceiptPath"])

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
