"""Withdrawn Tk state checks with fake pose readers and no game input."""
from contextlib import ExitStack
import gc
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as app

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tk unavailable")
class PlaybackWindowStateTests(unittest.TestCase):
    def setUp(self):
        was_enabled = gc.isenabled()
        gc.collect()
        gc.disable()
        def restore_gc():
            gc.collect()
            if was_enabled:
                gc.enable()
        self.addCleanup(restore_gc)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(self.temp)
        (self.path / "artifacts").mkdir()
        self.stack.enter_context(patch.object(app, "ROOT", self.path))
        self.threads, self.roots, self.callback_errors = [], [], []
        actual_tk, actual_thread = tk.Tk, threading.Thread
        def root(*args, **kwargs):
            try:
                value = actual_tk(*args, **kwargs)
            except tk.TclError as exc:
                self.skipTest(f"Tk cannot initialize: {exc}")
            value.withdraw()
            value.report_callback_exception = lambda kind, error, trace: self.callback_errors.append(error)
            self.roots.append(value)
            return value
        def thread(*args, **kwargs):
            value = actual_thread(*args, **kwargs)
            self.threads.append(value)
            return value
        self.stack.enter_context(patch.object(tk, "Tk", side_effect=root))
        self.stack.enter_context(patch.object(actual_tk, "mainloop", return_value=None))
        self.stack.enter_context(patch.object(app.threading, "Thread", side_effect=thread))
        self.stack.enter_context(patch.object(app, "ForegroundStop", side_effect=AssertionError("no input")))
        self.addCleanup(self.cleanup_gui)

    def cleanup_gui(self):
        for thread in self.threads:
            thread.join(timeout=4)
            self.assertFalse(thread.is_alive())
        for root in self.roots:
            try:
                for callback in root.tk.call("after", "info"):
                    root.after_cancel(callback)
                root.destroy()
            except tk.TclError:
                pass
        self.assertFalse(self.callback_errors, self.callback_errors)

    def widgets(self, parent):
        for widget in parent.winfo_children():
            yield widget
            yield from self.widgets(widget)

    def button(self, label):
        return next(w for w in self.widgets(self.roots[0])
                    if isinstance(w, (tk.Button, ttk.Button)) and str(w["text"]) == label)

    def launch(self, adapter=None, route=None):
        args = SimpleNamespace(expected_host="AMD-DESKTOP", physical_pid=None if adapter is None else 123,
                               initial_adapter=adapter, basis=Path("unused"), face_waypoints=True,
                               route=route, auto_reconnect=True, initial_reason="waiting" if adapter is None else None)
        app.launch_window(args)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if (all(not thread.is_alive() for thread in self.threads)
                    and str(self.button("Refresh")["state"]) != "disabled"):
                return
            time.sleep(.01)
        self.fail("fake reader did not settle")

    def test_waiting_disables_actions_but_keeps_route_editing(self):
        self.stack.enter_context(patch.object(app, "PhysicalAdapter", side_effect=ValueError("absent")))
        self.launch()
        for label in ("Record", "Play Forward", "Play Reverse", "Resume"):
            self.assertEqual("disabled", str(self.button(label)["state"]))
        for label in ("Load", "Add X / Z"):
            self.assertNotEqual("disabled", str(self.button(label)["state"]))

    def test_complete_checkpoint_cannot_resume(self):
        path = self.path / "artifacts" / "waypoint-current-progress.json"
        path.write_text(json.dumps({"route": {"waypoints": [["A", 0, 0], ["B", 1, 0]]},
                                    "direction": "forward", "nextIndex": 2}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123)
        self.launch(adapter)
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]))
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("choose Play Forward or Play Reverse" in value for value in values), values)

    def test_explicit_matching_route_restores_unfinished_progress(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11]}
        route = self.path / "route.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": document, "direction": "reverse", "nextIndex": 1}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_explicit_different_route_cannot_resume(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 12]}), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11]},
                                          "direction": "reverse", "nextIndex": 1}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertEqual("disabled", str(self.button("Resume")["state"]))

    def test_loading_same_route_preserves_unfinished_checkpoint(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11],
                    "recording": {"complete": True}}
        route = self.path / "route.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": document, "direction": "forward", "nextIndex": 1}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(route)):
            self.button("Load").invoke()
        self.assertTrue(checkpoint.exists())
        self.assertEqual(1, json.loads(checkpoint.read_text(encoding="utf-8"))["nextIndex"])
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_loading_changed_route_invalidates_and_clears_progress(self):
        old = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11]}
        new = {"waypoints": [["A", 0, 0], ["B", 2, 0]], "heights": [10, 11],
               "recording": {"complete": True}}
        route = self.path / "route.json"
        route.write_text(json.dumps(new), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": old, "direction": "forward", "nextIndex": 1}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(route)):
            self.button("Load").invoke()
        self.assertFalse(checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("No saved progress; choose Play" in value for value in values), values)

    def test_rejected_play_restores_completed_checkpoint_view(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": document, "direction": "reverse", "nextIndex": 2}), encoding="utf-8")
        original = checkpoint.read_bytes()
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(close=lambda: None)))
        self.stack.enter_context(patch("scripts.waypoint_playback.play_route", side_effect=ValueError("wrong endpoint")))
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123, binding={})
        self.launch(adapter)
        self.button("Play Reverse").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertEqual(original, checkpoint.read_bytes())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("Saved progress: 2 / 2" in value for value in values), values)

    def test_partial_play_keeps_new_checkpoint_cursor(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": document, "direction": "forward", "nextIndex": 2}), encoding="utf-8")
        def partial(adapter, route, stop, emit, **kwargs):
            checkpoint.write_text(json.dumps({"route": document, "direction": "forward", "nextIndex": 1}), encoding="utf-8")
            emit({"status": "arrived", "nextWaypoint": 1, "waypointCount": 2})
            raise ValueError("later leg failed")
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(close=lambda: None)))
        self.stack.enter_context(patch("scripts.waypoint_playback.play_route", side_effect=partial))
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123, binding={}))
        self.button("Play Forward").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertEqual(1, json.loads(checkpoint.read_text(encoding="utf-8"))["nextIndex"])
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("Saved progress: 1 / 2" in value for value in values), values)

    def test_failed_route_replacement_preserves_existing_saved_route(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 10]}
        route = self.path / "loaded.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        destination = self.path / "saved.json"
        original = json.dumps({"waypoints": [["Previous", 5, 6]]}).encode("utf-8")
        destination.write_bytes(original)
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)), \
             patch("scripts.waypoint_progress.os.replace", side_effect=OSError("simulated replace failure")), \
             patch("tkinter.messagebox.showerror") as error:
            self.button("Save Route").invoke()
        self.assertEqual(original, destination.read_bytes())
        error.assert_called_once()
        self.assertIn("simulated replace failure", error.call_args.args[1])
        self.assertEqual([], list(self.path.glob("saved.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
