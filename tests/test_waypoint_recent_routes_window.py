"""Recent route and explicit 3D view callbacks with fake readers and viewers."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_progress import RouteProgress
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class RecentRoutesTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self, route=None):
        pose = app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "player"}
        self.adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123,
                                       binding={"runtimeIdentity": self.identity},
                                       target={"processId": 123}, input_receipt_path=self.path / "unused")
        self.launch(self.adapter, route)
        self.window = self.roots[0]
        self.combo = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Combobox))

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.window.update()
            if all(not thread.is_alive() for thread in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                return
            time.sleep(.01)
        self.fail("worker did not settle")

    def test_load_recent_keeps_eight_full_local_paths_and_preserves_matching_progress(self):
        paths = []
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [5, 6],
                    "recording": {"complete": True}}
        for i in range(9):
            folder = self.path / str(i)
            folder.mkdir()
            path = folder / "route.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            paths.append(path)
        self.prepare()
        for path in paths:
            with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
                self.button("Load").invoke()
        history = list(self.combo.cget("values"))
        self.assertEqual([str(p) for p in reversed(paths[1:])], history)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(document, "reverse", self.identity)
        progress.begin({"x": 1, "y": 6, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0])
        progress.save(checkpoint)
        prior = checkpoint.read_bytes()
        self.combo.set(str(paths[2]))
        self.button("Load recent").invoke()
        self.assertEqual(prior, checkpoint.read_bytes())
        self.assertEqual(str(paths[2]), list(self.combo.cget("values"))[0])
        saved = json.loads((self.path / "artifacts" / "waypoint-last-route.json").read_text(encoding="utf-8"))
        self.assertEqual(document, saved["route"])
        self.assertEqual(list(self.combo.cget("values")), saved["recentPaths"])

    def test_corrupt_history_and_failed_recent_load_are_nonfatal(self):
        local_missing = self.path / "missing.json"
        cache = self.path / "artifacts" / "waypoint-last-route.json"
        cache.write_text(json.dumps({"version": 1, "route": {"waypoints": [["A", 0, 0]]},
                                     "sourcePath": None, "recentPaths": [r"\\other\share\x.json", 7, str(local_missing)]}), encoding="utf-8")
        self.prepare()
        self.assertEqual([str(local_missing)], list(self.combo.cget("values")))
        original = cache.read_bytes()
        self.combo.set(str(local_missing))
        with patch("tkinter.messagebox.showerror") as error:
            self.button("Load recent").invoke()
        error.assert_called_once()
        self.assertEqual(original, cache.read_bytes())

    def test_switch_away_and_back_restores_exact_reverse_cursor(self):
        a = {"waypoints": [["A", 0, 0], ["B", 1, 0], ["C", 2, 0]]}
        b = {"waypoints": [["Other", 0, 0], ["End", 0, 1]]}
        path_a, path_b = self.path / "a.json", self.path / "b.json"
        path_a.write_text(json.dumps(a), encoding="utf-8")
        path_b.write_text(json.dumps(b), encoding="utf-8")
        self.prepare(path_a)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(a, "reverse", self.identity)
        progress.begin({"x": 2, "y": 0, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0])
        progress.save(checkpoint)
        original = checkpoint.read_bytes()
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path_b)):
            self.button("Load").invoke()
        self.assertFalse(checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.combo.set(str(path_a))
        self.button("Load recent").invoke()
        self.assertEqual(original, checkpoint.read_bytes())
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(("reverse", 1), (RouteProgress.load(checkpoint, a, self.identity).direction,
                                          RouteProgress.load(checkpoint, a, self.identity).next_index))

    def test_archive_failure_does_not_replace_table_or_checkpoint(self):
        a = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        b = {"waypoints": [["Other", 0, 0]]}
        path_a, path_b = self.path / "a.json", self.path / "b.json"
        path_a.write_text(json.dumps(a), encoding="utf-8")
        path_b.write_text(json.dumps(b), encoding="utf-8")
        self.prepare(path_a)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(a, "reverse", self.identity)
        progress.begin({"x": 1, "y": 0, "z": 0})
        progress.save(checkpoint)
        original = checkpoint.read_bytes()
        table = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Treeview))
        before = [table.item(item, "values") for item in table.get_children()]
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path_b)), \
             patch("scripts.waypoint_progress.write_json_atomic", side_effect=OSError("archive failed")), \
             patch("tkinter.messagebox.showerror") as error:
            self.button("Load").invoke()
        error.assert_called_once()
        self.assertEqual(original, checkpoint.read_bytes())
        self.assertEqual(before, [table.item(item, "values") for item in table.get_children()])

    def test_edit_invalidates_only_current_route_cursor(self):
        a = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        b = {"waypoints": [["Other", 0, 0], ["End", 0, 1]]}
        path_a, path_b = self.path / "a.json", self.path / "b.json"
        path_a.write_text(json.dumps(a), encoding="utf-8")
        path_b.write_text(json.dumps(b), encoding="utf-8")
        self.prepare(path_a)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        old = RouteProgress(a, "forward", self.identity); old.begin({"x": 0, "y": 0, "z": 0}); old.save(checkpoint)
        original = checkpoint.read_bytes()
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path_b)):
            self.button("Load").invoke()
        current = RouteProgress(b, "forward", self.identity); current.begin({"x": 0, "y": 0, "z": 0}); current.save(checkpoint)
        table = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Treeview))
        table.selection_set(table.get_children()[0]); self.window.update()
        self.button("Remove").invoke()
        self.assertFalse(checkpoint.exists())
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path_a)):
            self.button("Load").invoke()
        self.assertEqual(original, checkpoint.read_bytes())

    def test_explicit_startup_restores_cursor_after_first_fresh_binding(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        source = self.path / "a.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "player"}
        progress = RouteProgress(document, "reverse", identity)
        progress.begin({"x": 1, "y": 0, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0]); progress.save(checkpoint)
        original = checkpoint.read_bytes()
        self.prepare(source)
        self.assertEqual(original, checkpoint.read_bytes())
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_unknown_identity_never_displays_cursor_and_recovers_after_refresh(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        source = self.path / "a.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        self.prepare(source)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(document, "reverse", self.identity)
        progress.begin({"x": 1, "y": 0, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0]); progress.save(checkpoint)
        original = checkpoint.read_bytes()
        self.adapter.binding = None
        with patch("tkinter.filedialog.askopenfilename", return_value=str(source)):
            self.button("Load").invoke()
        self.assertFalse(checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.adapter.binding = {"runtimeIdentity": self.identity}
        self.button("Refresh").invoke(); self.wait_idle()
        self.assertEqual(original, checkpoint.read_bytes())
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))

    def test_different_player_does_not_restore_other_players_cursor(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        source = self.path / "a.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        self.prepare(source)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress(document, "reverse", self.identity)
        progress.begin({"x": 1, "y": 0, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0]); progress.save(checkpoint)
        self.adapter.binding = {"runtimeIdentity": {**self.identity, "unitKey": "other"}}
        with patch("tkinter.filedialog.askopenfilename", return_value=str(source)):
            self.button("Load").invoke()
        self.assertFalse(checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(1, len(list((self.path / "artifacts" / "waypoint-progress").glob("*.json"))))

    def test_edit_while_identity_unavailable_clears_only_previous_owners_saved_cursor(self):
        from scripts.waypoint_progress import select_route_progress
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        source = self.path / "a.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        self.prepare(source)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        archive = checkpoint.parent / "waypoint-progress"
        other_owner = {**self.identity, "unitKey": "another-player"}
        for owner in (other_owner, self.identity):
            saved = RouteProgress(document, "reverse", owner)
            saved.begin({"x": 1, "z": 0})
            saved.confirm_arrival(0, saved.ordered_points[0])
            saved.save(checkpoint)
            select_route_progress(checkpoint, archive, document, None)

        self.adapter.binding = None
        self.combo.set(str(source))
        self.button("Load recent").invoke()
        table = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Treeview))
        table.selection_set(table.get_children()[0])
        self.button("Remove").invoke()
        self.button("Undo").invoke()
        self.adapter.binding = {"runtimeIdentity": self.identity}
        self.adapter.read = lambda **kwargs: app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.button("Refresh").invoke()
        self.wait_idle()
        self.combo.set(str(source))
        self.button("Load recent").invoke()
        self.assertFalse(checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(1, select_route_progress(checkpoint, archive, document, other_owner).next_index)

    def test_save_current_verifies_new_owner_before_editing(self):
        document = {"waypoints": [["A", 0, 0], ["B", 1, 0]]}
        source = self.path / "a.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        self.prepare(source)
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        other_owner = {**self.identity, "unitKey": "another-player"}
        saved = RouteProgress(document, "forward", other_owner)
        saved.begin({"x": 0, "z": 0})
        saved.save(checkpoint)
        self.adapter.read = lambda **kwargs: app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic()-5, "fake")
        self.button("Refresh").invoke()
        self.wait_idle()
        self.adapter.binding = {"runtimeIdentity": other_owner}
        self.adapter.read = lambda **kwargs: app.Snapshot(app.Position(0, 0, 0), 0, time.monotonic(), "fake")
        self.button("Save Current").invoke()
        self.wait_idle()
        self.assertFalse(checkpoint.exists())
        table = next(w for w in self.widgets(self.window) if isinstance(w, fixture.ttk.Treeview))
        self.assertEqual(3, len(table.get_children()))

    def test_explicit_3d_open_no_duplicate_and_new_capture_without_rerun_clears(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["A", 0, 0]]}), encoding="utf-8")
        self.prepare(route)
        child = SimpleNamespace(poll=Mock(return_value=None))
        launch_viewer = Mock(return_value=child)
        backend = Mock(side_effect=[{"status": "saved-route-view-candidate", "image": "first.png", "inputSent": False,
                                     "focusChanged": False, "rerun": {"status": "saved", "path": "first.rrd"}},
                                    {"status": "blocked", "reason": "unavailable", "inputSent": False, "focusChanged": False},
                                    {"status": "saved-route-view-candidate", "image": "second.png", "inputSent": False,
                                     "focusChanged": False, "rerun": {"status": "unavailable"}}])
        module = SimpleNamespace(save_route_view=backend, launch_saved_rerun=launch_viewer)
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": module}):
            self.assertEqual("disabled", str(self.button("Open 3D view")["state"]))
            self.button("Save view").invoke(); self.wait_idle()
            launch_viewer.assert_not_called()
            self.button("Open 3D view").invoke()
            self.button("Open 3D view").invoke()
            launch_viewer.assert_called_once_with("first.rrd")
            self.button("Save view").invoke(); self.wait_idle()
            self.assertNotEqual("disabled", str(self.button("Open 3D view")["state"]))
            child.poll.return_value = 0
            self.button("Open 3D view").invoke()
            self.assertEqual(2, launch_viewer.call_count)
            self.button("Save view").invoke(); self.wait_idle()
            self.assertEqual("disabled", str(self.button("Open 3D view")["state"]))


if __name__ == "__main__":
    unittest.main()
