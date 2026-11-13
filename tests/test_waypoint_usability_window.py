"""Cross-tab editing/readiness checks with real withdrawn Tk and fake poses."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_measurements import measurement
from tests import test_waypoint_header_window as fixture
from tests.test_waypoint_playback_window_state import TEST_IDENTITY

tk, ttk = fixture.tk, fixture.ttk


@unittest.skipIf(tk is None, "Tk unavailable")
class UsabilityWindowTests(unittest.TestCase):
    setUp = fixture.HeaderWindowTests.setUp
    cleanup_gui = fixture.HeaderWindowTests.cleanup_gui
    widgets = fixture.HeaderWindowTests.widgets
    button = fixture.HeaderWindowTests.button
    route_table = fixture.HeaderWindowTests.route_table
    launch = fixture.HeaderWindowTests.launch
    labels = fixture.HeaderWindowTests.labels
    read_status = fixture.HeaderWindowTests.read_status

    def launch_route(self):
        points = [["Start", 1, 3], ["End", 4, 3]]
        document = dict(waypoints=points, heights=[2, 2], pointMeasurements=[
            measurement(dict(x=p[1], y=2, z=p[2]), TEST_IDENTITY, "fake-native",
                        "2026-11-13T12:00:00Z") for p in points])
        path = self.path / "route.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        self.reader = Mock(side_effect=lambda **kwargs: app.Snapshot(
            app.Position(1, 2, 3), 17, time.monotonic(), "fake-native"))
        self.launch(SimpleNamespace(read=self.reader, pid=123), path)
        self.window = self.roots[0]
        self.notebook = next(w for w in self.widgets(self.window) if isinstance(w, ttk.Notebook))
        self.edit_tab = self.window.nametowidget(self.notebook.tabs()[1])
        self.entries = [w for w in self.widgets(self.edit_tab) if isinstance(w, ttk.Entry)]
        self.table = self.route_table()
        self.table.selection_set(self.table.get_children()[0])
        self.window.update()

    def draft_name(self):
        self.entries[0].delete(0, "end")
        self.entries[0].insert(0, "Unapplied name")

    def document_state(self):
        state = self.read_status()["route"]
        return {key: state[key] for key in ("revision", "dirty", "count")}

    def test_draft_notice_and_readiness_follow_every_tab_without_changing_route(self):
        self.launch_route()
        before, reads = self.document_state(), self.reader.call_count
        self.draft_name()
        # Trace callbacks must update readiness before another poll interval.
        self.assertEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertEqual("disabled", str(self.button("Add X / Z")["state"]))
        self.assertEqual("disabled", str(self.button("Go Selected")["state"]))
        self.assertEqual("disabled", str(self.button("Record")["state"]))
        for slug, tab in zip(("replay", "edit", "scene", "explore", "library", "activity"), self.notebook.tabs()):
            with self.subTest(tab=self.notebook.tab(tab, "text")):
                self.notebook.select(tab)
                self.window.update()
                notices = [w for w in self.widgets(self.window) if isinstance(w, ttk.Button)
                           and str(w["textvariable"]) and "Unapplied edit" in str(w.getvar(str(w["textvariable"])))]
                self.assertEqual(1, len(notices))
                self.assertEqual("Unapplied edit · point 1", str(notices[0].getvar(str(notices[0]["textvariable"]))))
                self.assertEqual(slug, self.read_status()["app"]["tab"])
                self.assertIn("*", self.notebook.tab(self.notebook.tabs()[1], "text"))
                self.assertTrue(self.read_status()["route"]["editDraft"]["pending"])
                self.assertEqual(before, self.document_state())
                self.assertEqual("Unapplied name", self.entries[0].get())
        notices[0].invoke()
        self.window.update()
        self.assertEqual("edit", self.read_status()["app"]["tab"])
        self.assertEqual("Unapplied name", self.entries[0].get())
        self.button("Reset fields").invoke()
        self.assertNotIn("*", self.notebook.tab(self.notebook.tabs()[1], "text"))
        self.assertFalse(self.read_status()["route"]["editDraft"]["pending"])
        self.assertEqual(before, self.document_state())
        self.assertEqual(reads, self.reader.call_count)

    def test_new_point_and_cli_clear_preserve_route_and_require_draft_resolution(self):
        self.launch_route()
        before, reads = self.document_state(), self.reader.call_count
        self.draft_name()
        refused = self.dispatch("route.select", {"clear": True}, "clear-draft-refused")
        self.assertFalse(refused["ok"], refused)
        self.button("New point").invoke()
        self.assertTrue(self.table.selection())
        self.assertEqual("Unapplied name", self.entries[0].get())
        self.button("Reset fields").invoke()
        self.button("New point").invoke()
        self.assertFalse(self.table.selection())
        self.assertEqual("", self.entries[1].get())
        self.assertEqual("", self.entries[2].get())
        self.assertEqual(before, self.document_state())
        self.table.selection_set(self.table.get_children()[0])
        self.window.update()
        self.draft_name()
        cleared = self.dispatch("route.select", {"clear": True, "discard_draft": True}, "clear-discard")
        self.assertTrue(cleared["ok"], cleared)
        self.assertFalse(self.table.selection())
        self.assertFalse(self.read_status()["route"]["editDraft"]["pending"])
        self.assertEqual(before, self.document_state())
        self.assertEqual(reads, self.reader.call_count)
        self.entries[1].insert(0, "5")
        self.entries[2].insert(0, "6")
        self.button("Add X / Z").invoke()
        self.assertEqual(3, len(self.table.get_children()))
        self.assertEqual(("5.000000", "6.000000"), tuple(self.table.item(self.table.get_children()[-1], "values"))[1:])
        self.assertEqual(reads, self.reader.call_count)

    def test_capture_readiness_explains_draft_then_recovers_without_remeasurement(self):
        self.launch_route()
        ready = self.read_status()["view"]["readiness"]
        self.assertTrue(ready["ready"], ready)
        self.assertEqual(2, ready["measured"])
        reads = self.reader.call_count
        self.draft_name()
        blocked = self.read_status()["view"]["readiness"]
        self.assertFalse(blocked["ready"], blocked)
        self.assertIn("Apply", blocked["reason"])
        self.assertEqual(2, blocked["measured"])
        self.assertEqual(2, blocked["total"])
        self.button("Reset fields").invoke()
        self.assertTrue(self.read_status()["view"]["readiness"]["ready"])
        self.assertEqual(reads, self.reader.call_count)

    def test_cli_measured_add_labels_do_not_change_form_before_completion_or_erase_native_name(self):
        self.launch_route()
        native_name = {"text": "Native target name", "qualification": "Fake native name candidate"}
        target = {"status": "candidate", "targetKey": "42",
                  "positionXYZCandidate": {"x": 7., "y": 2., "z": 8.},
                  "sampledAtUtc": "2026-11-13T12:00:00Z"}
        target_pose = app.Snapshot(app.Position(1, 2, 3), 17, time.monotonic(), "fake-native", target)
        read_target = self.stack.enter_context(patch.object(app, "_read_target_waypoint",
            return_value=(target_pose, ("Native target name", 7., 8.), native_name)))
        for number, kind in enumerate(("current", "target"), 3):
            with self.subTest(kind=kind):
                self.button("New point").invoke()
                old_fields = [entry.get() for entry in self.entries]
                label = f"Explicit {kind} label"
                result = self.dispatch("route.add", {kind: True, "name": label}, f"named-{kind}")
                self.assertIsInstance(result, fixture.protocol.Deferred)
                self.assertEqual(old_fields, [entry.get() for entry in self.entries])
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    self.window.update()
                    status = self.read_status()
                    if status["route"]["count"] == number and status["activeRequestId"] is None:
                        break
                    time.sleep(.01)
                self.assertEqual(number, status["route"]["count"])
                self.assertFalse(status["app"]["busy"])
                document = self.dispatch("route.list", {}, f"inspect-{kind}")["data"]["document"]
                self.assertEqual(label, document["waypoints"][-1][0])
                receipt = document["pointMeasurements"][-1]
                self.assertIsNotNone(receipt)
                if kind == "target":
                    self.assertEqual([label, 7., 8.], document["waypoints"][-1])
                    self.assertEqual(native_name, receipt["nameCandidate"])
                    self.assertEqual("42", receipt["targetKey"])
        read_target.assert_called_once()


if __name__ == "__main__":
    unittest.main()
