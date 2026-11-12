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
from scripts.waypoint_progress import RouteProgress

TEST_IDENTITY = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "player"}

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
        if adapter is not None and not getattr(adapter, "binding", None):
            adapter.binding = {"runtimeIdentity": dict(TEST_IDENTITY)}
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

    def write_checkpoint(self, document, direction, index):
        path = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(document, direction, TEST_IDENTITY)
        endpoint = progress.ordered_points[0]
        height = document.get("heights", [0] * len(progress.ordered_points))[0 if direction == "forward" else -1]
        progress.begin({"x": endpoint[1], "y": height if height is not None else 0, "z": endpoint[2]})
        for number in range(index):
            progress.confirm_arrival(number, progress.ordered_points[number])
        progress.save(path)
        return path

    def test_waiting_disables_actions_but_keeps_route_editing(self):
        self.stack.enter_context(patch.object(app, "PhysicalAdapter", side_effect=ValueError("absent")))
        self.launch()
        for label in ("Record", "Play Forward", "Play Reverse", "Resume", "Walk + Record"):
            self.assertEqual("disabled", str(self.button(label)["state"]))
        for label in ("Load", "Add X / Z"):
            self.assertNotEqual("disabled", str(self.button(label)["state"]))

    def test_play_buttons_follow_original_endpoints_without_extra_reads(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 4, 0]], "heights": [10, 11]}), encoding="utf-8")
        current = {"pose": app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")}
        reader = unittest.mock.Mock(side_effect=lambda **kwargs: current["pose"])
        self.launch(SimpleNamespace(read=reader, pid=123), route)
        self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertEqual("disabled", str(self.button("Play Reverse")["state"]))
        before = reader.call_count
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        table.selection_set(table.get_children()[0])
        self.roots[0].update()
        self.assertEqual(before, reader.call_count)
        current["pose"] = app.Snapshot(app.Position(4, 11, 0), 0, time.monotonic(), "fake")
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertNotEqual("disabled", str(self.button("Play Reverse")["state"]))

    def test_play_endpoint_height_and_point_three_boundary(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 2, 0]], "heights": [10, 10]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(.3000000005, 11, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]))

    def test_play_rejects_height_even_for_short_route(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 2, 0]], "heights": [10, 10]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 11.0001, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))

    def test_malformed_height_metadata_keeps_window_open_and_play_disabled(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 2, 0]], "heights": {}}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        reader = unittest.mock.Mock(return_value=pose)
        with patch("tkinter.messagebox.showerror") as error:
            self.launch(SimpleNamespace(read=reader, pid=123), route)
        error.assert_called_once()
        self.assertTrue(self.roots[0].winfo_exists())
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertEqual("disabled", str(self.button("Play Reverse")["state"]))
        self.assertEqual(1, reader.call_count)

    def test_play_rejects_just_outside_endpoint_radius(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 2, 0]]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(.300001, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))

    def test_play_accepts_exact_twenty_unit_route(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 20, 0]]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]))

    def test_play_rejects_wrong_height_and_route_over_twenty(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 21, 0]], "heights": [10, 10]}), encoding="utf-8")
        current = {"pose": app.Snapshot(app.Position(0, 12, 0), 0, time.monotonic(), "fake")}
        self.launch(SimpleNamespace(read=lambda **kwargs: current["pose"], pid=123), route)
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertEqual("disabled", str(self.button("Play Reverse")["state"]))
        # Correct the height; excessive route length still blocks forward play.
        current["pose"] = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))

    def test_complete_checkpoint_cannot_resume(self):
        self.write_checkpoint({"waypoints": [["A", 0, 0], ["B", 1, 0]]}, "forward", 2)
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
        self.write_checkpoint(document, "reverse", 1)
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_refresh_reconciles_checkpoint_completed_by_external_cli(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0], ["C", 2, 0], ["D", 3, 0]]}
        checkpoint = self.write_checkpoint(document, "reverse", 2)
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))
        self.write_checkpoint(document, "reverse", 4)
        unchanged = checkpoint.read_bytes()
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not t.is_alive() for t in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(unchanged, checkpoint.read_bytes())
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        self.assertEqual(4, len(table.get_children()))
        labels = [self.roots[0].getvar(w["textvariable"]) for w in self.widgets(self.roots[0])
                  if isinstance(w, ttk.Label) and w["textvariable"]]
        self.assertTrue(any("Saved progress: 4 / 4" in value for value in labels), labels)
        self.assertTrue(any("Remaining: 0.00" in value for value in labels), labels)

    def test_teach_progress_without_playback_cursor_after_completed_checkpoint(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        checkpoint = self.write_checkpoint(document, "reverse", 2)
        original = checkpoint.read_bytes()
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(close=lambda: None)))
        release = threading.Event()
        self.addCleanup(release.set)

        def teach(adapter, points, stop, emit, **kwargs):
            emit({"status": "moving", "position": {"x": .5, "y": 0, "z": 0}, "bearing": 0,
                  "recordingProgress": {"sampleCount": 8, "observedPathLength": 1.25}})
            if not release.wait(3):
                raise AssertionError("fake teaching was not released")
            raise app.Stopped("teaching cancelled")

        self.stack.enter_context(patch("scripts.waypoint_playback.teach_route", side_effect=teach))
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123, binding={},
                                    input_receipt_path=self.path / "pulses.jsonl"))
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.button("Walk + Record").invoke()
        deadline = time.monotonic() + 2
        found = False
        while time.monotonic() < deadline:
            self.roots[0].update()
            labels = [self.roots[0].getvar(w["textvariable"]) for w in self.widgets(self.roots[0])
                      if isinstance(w, ttk.Label) and w["textvariable"]]
            if any("Recording: 1.25 / 20 units" in value and "8 samples" in value for value in labels):
                found = True
                break
            time.sleep(.01)
        self.assertTrue(found, labels)
        self.assertFalse(self.callback_errors)
        self.button("STOP / F8").invoke()
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not t.is_alive() for t in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertFalse(self.callback_errors)
        self.assertEqual(original, checkpoint.read_bytes())

    def test_explicit_different_route_cannot_resume(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 12]}), encoding="utf-8")
        self.write_checkpoint({"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11]}, "reverse", 1)
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.assertEqual("disabled", str(self.button("Resume")["state"]))

    def test_loading_same_route_preserves_unfinished_checkpoint(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11],
                    "recording": {"complete": True}}
        route = self.path / "route.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        checkpoint = self.write_checkpoint(document, "forward", 1)
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(route)):
            self.button("Load").invoke()
        self.assertTrue(checkpoint.exists())
        self.assertEqual(1, json.loads(checkpoint.read_text(encoding="utf-8"))["nextIndex"])
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_loading_changed_route_invalidates_and_clears_progress(self):
        old = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11]}
        new = {"waypoints": [["A", 0, 0], ["B", 2, 0]], "heights": [10, 11],
               "recording": {"complete": True}}
        route = self.path / "route.json"
        route.write_text(json.dumps(new), encoding="utf-8")
        checkpoint = self.write_checkpoint(old, "forward", 1)
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
        checkpoint = self.write_checkpoint(document, "reverse", 2)
        original = checkpoint.read_bytes()
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(close=lambda: None)))
        current = {"pose": app.Snapshot(app.Position(1, 0, 0), 0, time.monotonic(), "fake")}
        def reject_changed_pose(adapter, *args, **kwargs):
            self.assertEqual(0, adapter.read().position.x)
            raise ValueError("wrong endpoint after pose changed")
        play = self.stack.enter_context(patch("scripts.waypoint_playback.play_route", side_effect=reject_changed_pose))
        adapter = SimpleNamespace(read=lambda **kwargs: current["pose"], pid=123, binding={})
        self.launch(adapter)
        current["pose"] = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
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
        play.assert_called_once()
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("Saved progress: 2 / 2" in value for value in values), values)

    def test_partial_play_keeps_new_checkpoint_cursor(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        checkpoint = self.write_checkpoint(document, "forward", 2)
        def partial(adapter, route, stop, emit, **kwargs):
            self.write_checkpoint(document, "forward", 1)
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
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                break
            time.sleep(.01)
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("Saved progress: 1 / 2" in value for value in values), values)

    def test_load_caches_route_for_restart_without_enabling_resume(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11],
                    "recording": {"complete": True}}
        path = self.path / "route.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
            self.button("Load").invoke()
        cache = self.path / "artifacts" / "waypoint-last-route.json"
        self.assertEqual(document, json.loads(cache.read_text(encoding="utf-8"))["route"])
        self.cleanup_gui()
        self.roots.clear()
        self.threads.clear()
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        self.assertEqual(2, len(table.get_children()))
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        with patch("tkinter.filedialog.asksaveasfilename") as chooser:
            self.button("Save Route").invoke()
        chooser.assert_not_called()
        self.assertEqual(document, json.loads(path.read_text(encoding="utf-8")))

    def test_checkpoint_and_explicit_route_take_precedence_over_cache(self):
        cache = self.path / "artifacts" / "waypoint-last-route.json"
        cache.write_text(json.dumps({"waypoints": [["Cached", 0, 0]]}), encoding="utf-8")
        self.write_checkpoint({"waypoints": [["Checkpoint", 0, 0]]}, "forward", 0)
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123)
        self.launch(adapter)
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        self.assertEqual("Checkpoint", table.item(table.get_children()[0], "values")[0])
        self.cleanup_gui()
        self.roots.clear()
        self.threads.clear()
        explicit = self.path / "explicit.json"
        explicit.write_text(json.dumps({"waypoints": [["Explicit", 0, 0]]}), encoding="utf-8")
        self.launch(adapter, explicit)
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        self.assertEqual("Explicit", table.item(table.get_children()[0], "values")[0])
        self.assertEqual("disabled", str(self.button("Resume")["state"]))

    def test_bad_checkpoint_falls_back_to_cache(self):
        cache = self.path / "artifacts" / "waypoint-last-route.json"
        cache.write_text(json.dumps({"waypoints": [["Cached", 0, 0]]}), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        checkpoint.write_text(json.dumps({"route": {"waypoints": [["Bad", 0, 0]]},
                                          "direction": "forward", "nextIndex": 99}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        table = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Treeview))
        self.assertEqual("Cached", table.item(table.get_children()[0], "values")[0])
        self.assertEqual("disabled", str(self.button("Resume")["state"]))

    def test_cache_failure_preserves_saved_route_and_old_cache(self):
        old = {"waypoints": [["Old", 0, 0]]}
        cache = self.path / "artifacts" / "waypoint-last-route.json"
        cache.write_text(json.dumps(old), encoding="utf-8")
        before = cache.read_bytes()
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        output = self.path / "saved.json"
        from scripts.waypoint_progress import write_json_atomic
        def fail_cache(path, document):
            if Path(path) == cache:
                raise OSError("cache unavailable")
            return write_json_atomic(path, document)
        with patch("scripts.waypoint_progress.write_json_atomic", side_effect=fail_cache), \
             patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)):
            self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
            self.button("Save Route").invoke()
        self.assertEqual(old, json.loads(output.read_text(encoding="utf-8")))
        self.assertEqual(before, cache.read_bytes())
        labels = [str(widget.cget("textvariable")) for widget in self.widgets(self.roots[0])
                  if isinstance(widget, ttk.Label) and widget.cget("textvariable")]
        values = [str(self.roots[0].getvar(label)) for label in labels]
        self.assertTrue(any("Route saved:" in value and "cache unavailable" in value for value in values), values)

    def test_save_updates_last_route_snapshot(self):
        source = self.path / "source.json"
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [5, 6]}
        source.write_text(json.dumps(document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 5, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), source)
        output = self.path / "saved.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)):
            self.button("Save As").invoke()
        saved = json.loads(output.read_text(encoding="utf-8"))
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        self.assertEqual(document, saved)
        self.assertEqual(saved, json.loads(snapshot.read_text(encoding="utf-8"))["route"])

    def test_recovered_route_asks_for_save_destination(self):
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        document = {"waypoints": [["Recovered", 0, 0]]}
        snapshot.write_text(json.dumps(document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        output = self.path / "recovered.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)) as dialog:
            self.button("Save Route").invoke()
        dialog.assert_called_once()
        self.assertEqual(document, json.loads(output.read_text(encoding="utf-8")))

    def test_changed_source_remains_recovered_and_save_asks(self):
        document = {"waypoints": [["Recorded", 0, 0]]}
        source = self.path / "changed.json"
        source.write_text(json.dumps({"waypoints": [["Changed", 0, 0]]}), encoding="utf-8")
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        snapshot.write_text(json.dumps({"version": 1, "route": document, "sourcePath": str(source)}), encoding="utf-8")
        before = source.read_bytes()
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.asksaveasfilename", return_value="") as chooser:
            self.button("Save Route").invoke()
        chooser.assert_called_once()
        self.assertEqual(before, source.read_bytes())

    def test_missing_source_and_matching_checkpoint_stay_unbound(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        snapshot.write_text(json.dumps({"version": 1, "route": document,
                                        "sourcePath": str(self.path / "missing.json")}), encoding="utf-8")
        self.write_checkpoint(document, "forward", 1)
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))
        with patch("tkinter.filedialog.asksaveasfilename", return_value="") as chooser:
            self.button("Save Route").invoke()
        chooser.assert_called_once()

    def test_checkpoint_mismatch_does_not_bind_cached_source(self):
        cached = {"waypoints": [["Cached", 0, 0]]}
        source = self.path / "source.json"
        source.write_text(json.dumps(cached), encoding="utf-8")
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        snapshot.write_text(json.dumps({"version": 1, "route": cached, "sourcePath": str(source)}), encoding="utf-8")
        self.write_checkpoint({"waypoints": [["Other", 0, 0]]}, "forward", 0)
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.asksaveasfilename", return_value="") as chooser:
            self.button("Save Route").invoke()
        chooser.assert_called_once()

    def test_unc_source_is_not_read_during_recovery(self):
        document = {"waypoints": [["Cached", 0, 0]]}
        snapshot = self.path / "artifacts" / "waypoint-last-route.json"
        snapshot.write_text(json.dumps({"version": 1, "route": document,
                                        "sourcePath": r"\\other-host\share\route.json"}), encoding="utf-8")
        original_read = Path.read_text
        def guarded_read(path, *args, **kwargs):
            if str(path).startswith("\\\\"):
                raise AssertionError("recovery attempted a remote read")
            return original_read(path, *args, **kwargs)
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        with patch.object(Path, "read_text", guarded_read):
            self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123))
        with patch("tkinter.filedialog.asksaveasfilename", return_value="") as chooser:
            self.button("Save Route").invoke()
        chooser.assert_called_once()

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
            self.button("Save As").invoke()
        self.assertEqual(original, destination.read_bytes())
        error.assert_called_once()
        self.assertIn("simulated replace failure", error.call_args.args[1])
        self.assertEqual([], list(self.path.glob("saved.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
