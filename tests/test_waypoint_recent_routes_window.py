"""Recent route and explicit 3D view callbacks with fake readers and viewers."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
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
        self.adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123,
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
        checkpoint.write_text(json.dumps({"route": document, "direction": "reverse", "nextIndex": 1}), encoding="utf-8")
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
