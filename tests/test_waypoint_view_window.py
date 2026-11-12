"""Withdrawn Tk save-view tests with fake backend and no native access."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class ViewWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self):
        self.document = {"waypoints": [["A", 0, 0], ["B", 1, 0]], "heights": [10, 11],
                         "recording": {"complete": True, "version": 1}}
        path = self.path / "route.json"
        path.write_text(json.dumps(self.document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.target = {"processId": 123, "processStartUtcTicks": "99", "hwnd": 100}
        self.adapter = SimpleNamespace(read=lambda **kwargs: pose, pid=123, target=self.target,
                                       input_receipt_path=self.path / "unused.jsonl")
        self.launch(self.adapter, path)

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if (all(not thread.is_alive() for thread in self.threads)
                    and str(self.button("Refresh")["state"]) != "disabled"):
                return
            time.sleep(.01)
        self.fail("view worker did not settle")

    def labels(self):
        return [str(self.roots[0].getvar(str(w.cget("textvariable")))) for w in self.widgets(self.roots[0])
                if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]

    def test_save_view_captures_snapshot_and_opens_only_on_click(self):
        self.prepare()
        entered, release = threading.Event(), threading.Event()
        def save(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("test did not release backend")
            return {"status": "saved-route-view-candidate", "image": str(self.path / "view.png"),
                    "inputSent": False, "focusChanged": True,
                    "rerun": {"status": "unavailable", "reason": "not installed"}}
        backend = Mock(side_effect=save)
        fake_module = SimpleNamespace(save_route_view=backend)
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": fake_module}), \
             patch.object(os, "startfile") as open_file:
            self.button("Save view").invoke()
            self.assertTrue(entered.wait(2))
            self.assertEqual("disabled", str(self.button("Save view")["state"]))
            self.assertEqual("disabled", str(self.button("Open view")["state"]))
            release.set()
            self.wait_idle()
            open_file.assert_not_called()
            self.assertNotEqual("disabled", str(self.button("Open view")["state"]))
            self.button("Open view").invoke()
            open_file.assert_called_once_with(str(self.path / "view.png"))
        args, kwargs = backend.call_args
        self.assertEqual(("AMD-DESKTOP", 123, self.document), args[:3])
        self.assertTrue(str(args[3]).startswith(str(self.path / "artifacts" / "waypoint-view-")))
        self.assertEqual(self.target, kwargs["expected_target"])
        self.assertIsNot(self.target, kwargs["expected_target"])
        self.assertTrue(kwargs["export_rerun"])
        self.assertEqual("desktop", kwargs["capture_backend"])
        self.assertTrue(any("Rerun unavailable: not installed" in value for value in self.labels()))

    def test_blocked_capture_keeps_open_view_disabled(self):
        self.prepare()
        backend = Mock(return_value={"status": "blocked", "reason": "not foreground", "inputSent": False,
                                     "focusChanged": False})
        with patch.dict(sys.modules, {"scripts.save_physical_route_view": SimpleNamespace(save_route_view=backend)}):
            self.button("Save view").invoke()
            self.wait_idle()
        self.assertEqual("disabled", str(self.button("Open view")["state"]))
        self.assertTrue(any("not foreground" in value for value in self.labels()))


if __name__ == "__main__":
    unittest.main()
