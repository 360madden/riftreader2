"""Hot route publication through withdrawn GUI callbacks and one fake owned child."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_measurements import measurement
from tests import test_waypoint_playback_window_state as fixture
from tests.test_waypoint_markers import FakeChild


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class MarkerSyncTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def ready(self):
        self.child = FakeChild()
        self.popen = Mock(return_value=self.child)
        self.owned = app.OwnedWaypointMarkers(self.path, popen=self.popen)
        self.stack.enter_context(patch.object(app, "OwnedWaypointMarkers", return_value=self.owned))
        self.stack.enter_context(patch("scripts.physical_waypoint_overlay.bind_companion_window",
            return_value={"processId": 456, "processStartUtcTicks": "1234", "hwnd": 65536}))
        identity = dict(fixture.TEST_IDENTITY, processId=123, processStartUtcTicks="1234")
        points = [[f"Point {i + 1}", i, 0] for i in range(7)]
        receipts = [measurement({"x": row[1], "y": 10, "z": row[2]}, identity,
                               "retained.json", "2026-11-12T12:00:00Z") for row in points[:2]]
        self.document = {"waypoints": points, "heights": [10, 10] + [None] * 5,
                         "pointMeasurements": receipts + [None] * 5}
        self.source = self.path / "source.json"
        self.source.write_text(json.dumps(self.document), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(pid=123, read=lambda **kwargs: pose, binding={"runtimeIdentity": identity},
                                  target={"processId": 123, "processStartUtcTicks": "1234",
                                          "executableSha256": "a" * 64, "hwnd": 65537})
        self.adapter = adapter
        self.launch(adapter, self.source)
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)
                        and not isinstance(w, fixture.ttk.Combobox)]
        self.guide = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Checkbutton)
                          and str(w["text"]) == "Guide selected marker")
        self.button("Show markers").invoke()
        self.assertEqual(1, self.popen.call_count)

    def enter(self, label, x, z):
        for widget, value in zip(self.entries, (label, x, z)):
            widget.delete(0, "end")
            widget.insert(0, str(value))

    def payload(self):
        return json.loads(self.owned.route_updates_path.read_text())

    def wait_payload(self, predicate):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            self.root.update()
            value = self.payload()
            if predicate(value):
                self.assertEqual(1, self.popen.call_count)
                self.assertFalse(self.owned.stop_path.exists())
                return value
            time.sleep(.01)
        self.fail("route update did not arrive")

    def test_add_edit_reorder_remove_clear_undo_and_selection_keep_one_child(self):
        self.ready()
        self.enter("Added XZ", 7, 1)
        self.button("Add X / Z").invoke()
        value = self.wait_payload(lambda v: len(v["route"]["waypoints"]) == 8)
        self.assertIsNone(value["route"]["heights"][-1])
        self.enter("Renamed", 7, 1)
        self.button("Update Selected").invoke()
        self.wait_payload(lambda v: v["route"]["waypoints"][-1][0] == "Renamed")
        self.button("Up").invoke()
        self.wait_payload(lambda v: v["route"]["waypoints"][-2][0] == "Renamed")
        self.button("Remove").invoke()
        self.wait_payload(lambda v: len(v["route"]["waypoints"]) == 7)
        self.table.selection_set(self.table.get_children()[0])
        self.root.update()
        self.enter("Edited coordinate", .2, 0)
        self.button("Update Selected").invoke()
        value = self.wait_payload(lambda v: v["route"]["waypoints"][0][0] == "Edited coordinate")
        self.assertIsNone(value["route"]["pointMeasurements"][0])
        self.assertIsNotNone(value["route"]["pointMeasurements"][1])
        self.button("Clear").invoke()
        self.wait_payload(lambda v: v == {"route": {"waypoints": []}, "landmarkNumber": None})
        self.assertTrue(self.owned.running())
        self.button("Undo").invoke()
        self.wait_payload(lambda v: len(v["route"]["waypoints"]) == 7)
        self.guide.invoke()
        self.table.selection_set(self.table.get_children()[1])
        self.wait_payload(lambda v: v["landmarkNumber"] == 2)
        self.table.selection_set(self.table.get_children()[2])
        self.wait_payload(lambda v: v["landmarkNumber"] == 3)
        self.button("Hide markers").invoke()
        previous = self.owned.route_updates_path.read_bytes()
        self.enter("After Hide", 8, 0)
        self.button("Add X / Z").invoke()
        time.sleep(.17)
        self.root.update()
        self.assertEqual(previous, self.owned.route_updates_path.read_bytes())
        self.assertEqual(1, self.popen.call_count)

    def test_save_as_and_load_publish_new_route_without_hiding(self):
        self.ready()
        destination = self.path / "copy.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)):
            self.button("Save As").invoke()
        self.assertEqual(self.document, json.loads(destination.read_text()))
        other = self.path / "other.json"
        plain = {"waypoints": [["Other", 1, 1]]}
        other.write_text(json.dumps(plain), encoding="utf-8")
        with patch("tkinter.filedialog.askopenfilename", return_value=str(other)):
            self.button("Load").invoke()
        self.wait_payload(lambda v: v["route"] == plain)
        self.assertEqual(self.document, json.loads(self.source.read_text()))

    def test_publication_failure_stops_owned_child_and_never_respawns(self):
        self.ready()
        previous = self.owned.route_updates_path.read_bytes()
        with patch.object(self.owned, "update", side_effect=OSError("disk denied")):
            self.enter("Cannot publish", 8, 0)
            self.button("Add X / Z").invoke()
            deadline = time.monotonic() + 2
            while not self.owned.stop_requested and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
        self.assertTrue(self.owned.stop_requested)
        self.assertTrue(self.owned.stop_path.exists())
        self.assertEqual(previous, self.owned.route_updates_path.read_bytes())
        self.assertEqual(1, self.popen.call_count)
        labels = [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        self.assertTrue(any("Cannot update markers: disk denied" in text for text in labels))


if __name__ == "__main__":
    unittest.main()
