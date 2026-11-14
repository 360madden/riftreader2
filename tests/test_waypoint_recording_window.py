"""Withdrawn Tk callback tests; fake observations only, no native/game input."""
from contextlib import ExitStack
import gc
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests.tk_support import withdrawn_root, reject_error_dialog

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tk is unavailable")
class RecordingWindowTests(unittest.TestCase):
    def setUp(self):
        # Tk variables from a previous destroyed window can remain in callback
        # cycles. Collect them on the Tk owner thread before any new worker,
        # and prevent automatic collection on observation workers during tests.
        self.assertIs(threading.current_thread(), threading.main_thread())
        gc.collect()
        gc_was_enabled = gc.isenabled()
        gc.disable()

        def restore_gc():
            # Registered first: runs after worker joins, Tk destruction and
            # patch cleanup. The next setUp also collects newly unreachable
            # TestCase/callback cycles before it launches any workers.
            gc.collect()
            if gc_was_enabled:
                gc.enable()

        self.addCleanup(restore_gc)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("tkinter.messagebox.showerror", side_effect=reject_error_dialog))
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root_path = Path(self.temp)
        (self.root_path / "artifacts").mkdir()
        self.threads, self.roots = [], []
        self.callback_errors = []
        self.capture_pending, self.release_capture = threading.Event(), threading.Event()
        self.calls = 0
        actual_tk, actual_thread = tk.Tk, threading.Thread

        def make_window(*args, **kwargs):
            window = withdrawn_root(actual_tk, *args, **kwargs)
            window.report_callback_exception = lambda kind, error, trace: self.callback_errors.append(error)
            self.roots.append(window)
            return window

        def make_thread(*args, **kwargs):
            thread = actual_thread(*args, **kwargs)
            self.threads.append(thread)
            return thread

        self.stack.enter_context(patch.object(tk, "Tk", side_effect=make_window))
        self.stack.enter_context(patch.object(actual_tk, "mainloop", return_value=None))
        self.stack.enter_context(patch.object(app, "ROOT", self.root_path))
        self.stack.enter_context(patch.object(app.threading, "Thread", side_effect=make_thread))
        self.no_input = self.stack.enter_context(patch.object(app, "ForegroundStop",
                                                 side_effect=AssertionError("Input is forbidden")))
        self.stack.enter_context(patch("scripts.waypoint_observation.observe_batch", side_effect=self.batch))
        self.identity = Mock(side_effect=AssertionError("passive recorder must not claim input control"))
        self.adapter = SimpleNamespace(binding={"runtimeIdentity": {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                                                                         "unitKey": "player", "processId": 123}},
                                       input_receipt_path=self.root_path / "unused.jsonl",
                                       read=lambda **_: self.pose(0), identity=self.identity)
        args = SimpleNamespace(expected_host="AMD-DESKTOP", physical_pid=123,
                               initial_adapter=self.adapter, basis=Path("unused"),
                               face_waypoints=True, route=None, auto_reconnect=False)
        self.addCleanup(self.cleanup_windows)
        app.launch_window(args)
        self.window = self.roots[0]
        self.wait_for(lambda: str(self.button("Record")["text"]) == "Record" and str(self.button("Record")["state"]) != "disabled")

    @staticmethod
    def pose(x):
        return app.Snapshot(app.Position(x, 0., 0.), 0., time.monotonic(), "fake-native.json")

    def batch(self, adapter, *, samples):
        self.assertIs(adapter, self.adapter)
        self.assertEqual(6, samples)
        self.calls += 1
        if self.calls == 1:
            now = time.monotonic()
            return [app.Snapshot(app.Position(x, 0., 0.), 0., now - .2 + x * .1,
                                 "fake-native.json") for x in (0., 1., 2.)]
        self.capture_pending.set()
        if not self.release_capture.wait(3):
            raise RuntimeError("Test did not release fake capture")
        return [self.pose(2.)]

    def widgets(self, parent=None):
        for widget in (parent or self.window).winfo_children():
            yield widget
            yield from self.widgets(widget)

    def button(self, label):
        if label == "Record" and hasattr(self, "record_toggle"):
            return self.record_toggle
        return next(w for w in self.widgets()
                    if isinstance(w, (tk.Button, ttk.Button)) and str(w["text"]) == label)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("GUI callback did not settle")
            self.window.update()
            time.sleep(.01)

    def start_pending_recording(self):
        self.record_toggle = self.button("Record")
        self.record_toggle.invoke()
        self.wait_for(self.capture_pending.is_set)
        self.assertEqual("Stop Recording", self.record_toggle["text"])
        self.assertNotEqual("disabled", str(self.record_toggle["state"]))

    def saved(self):
        return list((self.root_path / "artifacts" / "waypoint-routes").glob("recorded-route-*.json"))

    def destroyed(self):
        try:
            return not self.window.winfo_exists()
        except tk.TclError:
            return True

    def close(self):
        self.window.tk.call(self.window.protocol("WM_DELETE_WINDOW"))

    def cleanup_windows(self):
        self.release_capture.set()
        for thread in self.threads:
            thread.join(timeout=4)
            self.assertFalse(thread.is_alive(), "Fake observation worker leaked")
        for root in self.roots:
            try:
                for callback in root.tk.call("after", "info"):
                    root.after_cancel(callback)
                root.destroy()
            except tk.TclError:
                pass
        self.no_input.assert_not_called()
        self.identity.assert_not_called()
        self.assertEqual([], self.callback_errors, "Tk callback failures must fail the test")

    def test_normal_stop_publishes_and_loads_recorded_route(self):
        self.start_pending_recording()
        self.record_toggle.invoke()
        self.release_capture.set()
        self.wait_for(lambda: bool(self.saved()))
        document = json.loads(self.saved()[0].read_text(encoding="utf-8"))
        snapshot = self.root_path / "artifacts" / "waypoint-last-route.json"
        saved_snapshot = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(document, saved_snapshot["route"])
        self.assertEqual(str(self.saved()[0]), saved_snapshot["sourcePath"])
        table = next(w for w in self.widgets() if isinstance(w, ttk.Treeview)
                     and tuple(w["columns"]) == ("name", "x", "z"))
        points = [table.item(item, "values") for item in table.get_children()]
        self.assertEqual(len(document["waypoints"]), len(points))
        self.assertEqual([0., 2.], [float(row[1]) for row in points])
        self.assertTrue(document["recording"]["complete"])
        self.wait_for(lambda: str(self.button("Record")["text"]) == "Record" and str(self.button("Record")["state"]) != "disabled")
        self.assertEqual("disabled", str(self.button("Stop Recording")["state"]))

    def test_stop_cancels_without_publishing(self):
        self.start_pending_recording()
        self.button("STOP").invoke()
        self.release_capture.set()
        self.wait_for(lambda: str(self.button("Record")["text"]) == "Record" and str(self.button("Record")["state"]) != "disabled")
        self.assertEqual([], self.saved())

    def test_toggle_saves_to_selected_new_route_file(self):
        chosen = self.root_path / "my-walk.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(chosen)):
            self.button("New Route…").invoke()
        self.window.update()
        self.start_pending_recording()
        self.record_toggle.invoke()
        self.release_capture.set()
        self.wait_for(chosen.exists)
        self.assertEqual(5.0, json.loads(chosen.read_text())["recording"]["waypointSpacing"])

    def test_recording_displays_actual_capture_budget_then_clears_on_cancel(self):
        self.start_pending_recording()
        def label_values():
            return [str(self.window.getvar(w["textvariable"])) for w in self.widgets()
                    if isinstance(w, ttk.Label) and w["textvariable"]]
        self.assertTrue(any("Recording: 2.00 / 1000 units" in value and "3 samples" in value
                            for value in label_values()), label_values())
        self.button("STOP").invoke()
        self.release_capture.set()
        self.wait_for(lambda: str(self.button("Record")["text"]) == "Record" and str(self.button("Record")["state"]) != "disabled")
        self.assertFalse(any(value.startswith("Recording:") for value in label_values()))
        self.assertEqual([], self.saved())

    def test_close_waits_for_pending_capture_and_discards_recording(self):
        self.start_pending_recording()
        self.close()
        self.assertTrue(self.window.winfo_exists())
        self.assertTrue(any(t.is_alive() for t in self.threads))
        self.release_capture.set()
        self.wait_for(self.destroyed)
        self.assertEqual([], self.saved())

    def test_stop_after_worker_finishes_prevents_queued_publication(self):
        self.start_pending_recording()
        self.button("Stop Recording").invoke()
        self.release_capture.set()
        # Let the worker queue its document without pumping the Tk poll callback.
        # STOP still owns the final decision before UI-thread publication.
        for thread in self.threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.button("STOP").invoke()
        self.wait_for(lambda: str(self.button("Record")["text"]) == "Record" and str(self.button("Record")["state"]) != "disabled")
        self.assertEqual([], self.saved())


if __name__ == "__main__":
    unittest.main()
