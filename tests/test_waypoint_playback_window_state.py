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

    def launch(self, adapter=None):
        args = SimpleNamespace(expected_host="AMD-DESKTOP", physical_pid=None if adapter is None else 123,
                               initial_adapter=adapter, basis=Path("unused"), face_waypoints=True,
                               route=None, auto_reconnect=True, initial_reason="waiting" if adapter is None else None)
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


if __name__ == "__main__":
    unittest.main()
