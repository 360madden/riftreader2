"""Manual XZ points remain unmeasured while the GUI explains beacon estimates."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class EstimatedBeaconWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def test_plain_xz_route_reports_estimates_and_save_does_not_invent_y(self):
        document = {"waypoints": [["Map point 1", 0, 0], ["Map point 2", 1, 0]]}
        route = self.path / "plain.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(pid=123, read=lambda **kwargs: pose), route)
        root = self.roots[0]
        labels = [str(root.getvar(w["textvariable"])) for w in self.widgets(root)
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        self.assertTrue(any("Beacons: 0 measured · 2 estimated" in text for text in labels), labels)
        saved = self.path / "saved.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(saved)):
            self.button("Save As").invoke()
        self.assertEqual(document, json.loads(saved.read_text()))
        self.assertNotIn("heights", json.loads(saved.read_text()))
        self.assertNotIn("pointMeasurements", json.loads(saved.read_text()))


if __name__ == "__main__":
    unittest.main()
