"""Read-only route endpoint hints using withdrawn Tk and observed fake poses."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class EntryDistanceWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def summary(self):
        values = [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        return next(v for v in values if v.startswith(("Route:", "Remaining:", "Recording:")))

    def settle(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            self.root.update()
            if all(not t.is_alive() for t in self.threads) and str(self.button("Refresh")["state"]) != "disabled":
                return
            time.sleep(.01)
        self.fail("fake reader did not settle")

    def test_refresh_updates_distances_in_original_order_with_reverse_progress(self):
        document = {"waypoints": [["Start", 0, 0], ["End", 3, 4]]}
        checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        fixture.PlaybackWindowStateTests.write_checkpoint(self, document, "reverse", 1)
        original = checkpoint.read_bytes()
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        reader = Mock(return_value=pose)
        self.launch(SimpleNamespace(read=reader, pid=123))
        self.root = self.roots[0]
        self.assertEqual(1, reader.call_count)
        self.assertIn("Remaining: 0.00 / 1000 units", self.summary())
        self.assertIn("Start: 0.00 • End: 5.00 units", self.summary())
        table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview)
                     and tuple(w["columns"]) == ("name", "x", "z"))
        table.selection_set(table.get_children()[1])
        self.root.update()
        self.assertIn("Selected: 5.00 units", self.summary())
        self.assertEqual(1, reader.call_count)
        reader.return_value = app.Snapshot(app.Position(3, 10, 4), 0, time.monotonic(), "fake")
        self.button("Refresh").invoke()
        # A selection redraw while busy must not advertise an entry distance.
        table.selection_set(table.get_children()[0])
        table.event_generate("<<TreeviewSelect>>")
        self.assertNotIn("Start:", self.summary())
        self.settle()
        self.assertEqual(2, reader.call_count)
        self.assertIn("Start: 5.00 • End: 0.00 units", self.summary())
        self.assertIn("Selected: 5.00 units", self.summary())
        self.assertEqual(original, checkpoint.read_bytes())
        labels = [str(w["text"]) for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Label)]
        self.assertTrue(any("F8" in v and "Stop Recording saves; STOP cancels recording" in v
                            and "0.30 units of Start (Forward) or End (Reverse)" in v for v in labels))

    def test_without_points_summary_omits_endpoint_hint(self):
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        reader = Mock(return_value=pose)
        self.launch(SimpleNamespace(read=reader, pid=123))
        self.root = self.roots[0]
        self.assertTrue(self.summary().startswith("Route:"))
        self.assertNotIn("Start:", self.summary())
        self.assertEqual(1, reader.call_count)


if __name__ == "__main__":
    unittest.main()
