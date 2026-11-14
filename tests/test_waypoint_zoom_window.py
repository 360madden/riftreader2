"""Display-only waypoint zoom callbacks with withdrawn Tk and fake poses."""
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class ZoomWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self):
        self.document = {"waypoints": [["Origin", 100, 200], ["Corner", 104, 200]],
                         "heights": [10, 10]}
        route = self.path / "route.json"
        route.write_text(json.dumps(self.document))
        pose = app.Snapshot(app.Position(100, 10, 200), 0, time.monotonic(), "fake")
        self.read = Mock(return_value=pose)
        self.launch(SimpleNamespace(read=self.read, pid=123), route)
        self.root = self.roots[0]
        self.canvas = next(w for w in self.widgets(self.root) if isinstance(w, fixture.tk.Canvas))
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))

    def labels(self):
        return [self.root.getvar(w["textvariable"]) for w in self.widgets(self.root)
                if isinstance(w, fixture.ttk.Label) and w["textvariable"]]

    def test_zoom_fit_boundaries_preserve_world_route_selection_without_reads(self):
        self.prepare()
        selected = self.table.selection()
        before = [self.table.item(i, "values") for i in self.table.get_children()]
        reads = self.read.call_count
        self.assertIn("10 units", self.labels())
        self.button("+").invoke()
        self.assertIn("5 units", self.labels())
        self.button("+").invoke()
        self.assertIn("2 units", self.labels())
        self.assertEqual("disabled", str(self.button("+")["state"]))
        self.button("Fit").invoke()
        self.assertIn("5 units", self.labels())
        for _ in app.ZOOM_RADII:
            self.button("-").invoke()
        self.assertIn("1500 units", self.labels())
        self.assertEqual("disabled", str(self.button("-")["state"]))
        self.assertEqual(reads, self.read.call_count)
        self.assertEqual(selected, self.table.selection())
        self.assertEqual(before, [self.table.item(i, "values") for i in self.table.get_children()])
        # Actual rendered selected point moves on the canvas; its route-world
        # coordinates remain exactly the same through every redraw.
        texts = [self.canvas.itemcget(i, "text") for i in self.canvas.find_all()
                 if self.canvas.type(i) == "text"]
        self.assertIn("750", texts)
        self.assertIn("1500", texts)

    def test_fit_disabled_without_pose_zoom_remains_display_only(self):
        with patch.object(app, "PhysicalAdapter", side_effect=ValueError("offline")):
            self.launch()
        self.root = self.roots[0]
        self.assertEqual("disabled", str(self.button("Fit")["state"]))
        self.button("+").invoke()
        self.assertIn("5 units", self.labels())

    def test_zoom_and_fit_are_usable_during_busy_read_without_dispatching_reads(self):
        self.prepare()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def pending(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("fake read not released")
            return app.Snapshot(app.Position(100, 10, 200), 0, time.monotonic(), "fake")

        self.read.side_effect = pending
        self.button("Refresh").invoke()
        self.assertTrue(entered.wait(1))
        calls = self.read.call_count
        for label in ("+", "-", "Fit"):
            self.assertNotEqual("disabled", str(self.button(label)["state"]))
            self.button(label).invoke()
        self.assertEqual(calls, self.read.call_count)
        self.assertIn("5 units", self.labels())
        release.set()


if __name__ == "__main__":
    unittest.main()
