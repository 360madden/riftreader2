"""Appearance preferences update through withdrawn widgets without marker restart."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_marker_style import DEFAULT_STYLE, save_style
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class MarkerAppearanceTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def ready(self):
        self.marker_running = False
        self.marker = SimpleNamespace(
            running=Mock(side_effect=lambda: self.marker_running),
            stop=Mock(side_effect=lambda: setattr(self, "marker_running", False)),
            start=Mock(side_effect=lambda *args, **kwargs: setattr(self, "marker_running", True)),
            update=Mock(), stop_requested=False, exit_code=None,
            status_path=self.path / "marker-status.json", pose_path=self.path / "marker-pose.json")
        self.stack.enter_context(patch.object(app, "OwnedWaypointMarkers", return_value=self.marker))
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.reader = Mock(return_value=pose)
        self.adapter = SimpleNamespace(pid=123, read=self.reader,
                                       target={"processId": 123, "processStartUtcTicks": "1234",
                                               "executableSha256": "a" * 64, "hwnd": 65537},
                                       binding={"runtimeIdentity": dict(fixture.TEST_IDENTITY)},
                                       selection=SimpleNamespace(),
                                       input_receipt_path=self.path / "unused-input.jsonl")
        self.launch(self.adapter)
        self.root = self.roots[0]
        self.preferences = self.path / "artifacts" / "waypoint-marker-style.json"
        notebook = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Notebook))
        scene = next(tab for tab in notebook.tabs() if notebook.tab(tab, "text") == "Scene & beacons")
        self.scales = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Scale)
                       and str(w).startswith(scene + ".")]
        self.labels = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Checkbutton)
                           and str(w["text"]) == "Show labels")

    def route_table(self):
        return next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview)
                    and tuple(str(name) for name in w["columns"]) == ("name", "x", "z"))

    def marker_toggle(self):
        return next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Button)
                    and str(w["text"]) in {"Show markers", "Show beacons", "Hide markers", "Hide beacons"})

    def text_values(self):
        return [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                if isinstance(w, fixture.ttk.Label) and w["textvariable"]]

    def settle(self, expected):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            self.root.update()
            if self.preferences.exists() and json.loads(self.preferences.read_text()) == expected:
                return
            time.sleep(.01)
        self.fail("appearance settings were not persisted")

    def test_sliders_and_labels_persist_live_without_stopping_or_starting_markers(self):
        self.ready()
        self.marker_running = True
        self.scales[0].set(150)
        self.scales[1].set(40)
        self.settle(dict(schemaVersion=1, beaconScale=1.5, opacity=.4, labelsVisible=True))
        self.labels.invoke()
        expected = dict(schemaVersion=1, beaconScale=1.5, opacity=.4, labelsVisible=False)
        self.assertEqual(expected, json.loads(self.preferences.read_text()))
        self.assertEqual("normal", str(self.labels["state"]))
        self.assertTrue(all(str(w["state"]) != "disabled" for w in self.scales))
        self.marker.stop.assert_not_called()
        self.marker.start.assert_not_called()
        self.assertFalse((self.path / "artifacts" / "waypoint-current-progress.json").exists())

    def test_saved_preferences_load_and_reset_restores_defaults(self):
        path = self.path / "artifacts" / "waypoint-marker-style.json"
        save_style(path, dict(schemaVersion=1, beaconScale=.5, opacity=.2, labelsVisible=False))
        self.ready()
        self.assertEqual([50, 20], [w.get() for w in self.scales])
        self.assertFalse(self.labels.instate(["selected"]))
        self.button("Reset").invoke()
        self.assertEqual(DEFAULT_STYLE, json.loads(path.read_text()))
        self.assertEqual([100, 100], [w.get() for w in self.scales])
        self.assertTrue(self.labels.instate(["selected"]))

    def test_corrupt_preferences_use_default_and_save_failure_remains_visible(self):
        path = self.path / "artifacts" / "waypoint-marker-style.json"
        path.write_text("broken", encoding="utf-8")
        failure = self.stack.enter_context(patch("scripts.waypoint_marker_style.save_style", side_effect=OSError("disk denied")))
        self.ready()
        self.assertEqual([100, 100], [w.get() for w in self.scales])
        self.labels.invoke()
        failure.assert_called_once()
        values = [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        self.assertTrue(any("Cannot save marker appearance: disk denied" in text for text in values))
        self.assertEqual("broken", path.read_text())

    def test_adjust_then_immediate_normal_close_flushes_debounced_preference(self):
        self.ready()
        self.scales[0].set(175)
        self.assertFalse(self.preferences.exists())
        self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(dict(schemaVersion=1, beaconScale=1.75, opacity=1., labelsVisible=True),
                         json.loads(self.preferences.read_text()))

    def test_scene_requested_size_fits_minimum_and_default_content_budgets(self):
        self.ready()
        self.root.update_idletasks()
        book = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Notebook))
        tab = next(self.root.nametowidget(item) for item in book.tabs()
                   if book.tab(item, "text") == "Scene & beacons")
        for width in (980, 1120):
            # Withdrawn children have no mapped allocations. Compare their real
            # Tk requests with outer padding44 + border4 + tab padding28.
            self.assertLessEqual(tab.winfo_reqwidth(), width - 76)
        self.assertLessEqual(tab.winfo_reqheight(), 220)

    def test_gui_marker_launch_binds_exact_root_and_passes_companion(self):
        self.ready()
        table = self.route_table()
        table.insert("", "end", values=("Ground", "0", "0"))
        companion = {"processId": 456, "processStartUtcTicks": "123456789", "hwnd": 65536}
        with patch("scripts.physical_waypoint_overlay.bind_companion_window", return_value=companion) as bind:
            self.marker_toggle().invoke()
        bind.assert_called_once_with(self.root.winfo_id())
        self.assertEqual(companion, self.marker.start.call_args.kwargs["companion"])

    def test_missing_gui_binding_refuses_marker_launch(self):
        self.ready()
        with patch("scripts.physical_waypoint_overlay.bind_companion_window", side_effect=ValueError("binding unavailable")):
            self.marker_toggle().invoke()
        self.marker.start.assert_not_called()
        values = [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                  if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
        self.assertTrue(any("binding unavailable" in text for text in values))

    def test_running_markers_pause_only_idle_pose_and_preserve_checked_preference(self):
        self.ready()
        checkbox = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Checkbutton)
                        and str(w["text"]).startswith("Live pose"))
        self.assertTrue(checkbox.instate(["selected"]))
        self.marker_running = True
        reads = self.reader.call_count
        time.sleep(2.05)
        self.root.update()
        self.assertEqual(reads, self.reader.call_count)
        self.assertEqual("Live pose (waiting)", str(checkbox["text"]))
        self.assertTrue(checkbox.instate(["selected"]))
        self.marker_running = False
        deadline = time.monotonic() + 1
        while self.reader.call_count == reads and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertGreater(self.reader.call_count, reads)
        self.assertEqual("Live pose (2 s)", str(checkbox["text"]))
        self.assertTrue(checkbox.instate(["selected"]))

    def test_beacon_status_does_not_equate_running_reader_with_visibility(self):
        unknown = app.beacon_display_status(True, False, None)
        self.assertEqual(("unknown", None), (unknown["state"], unknown["visible"]))
        hidden = app.beacon_display_status(True, False, {
            "presenterSnapshot": {"displayAllowed": False}, "overlayHasFrame": True})
        self.assertEqual(("hidden", False), (hidden["state"], hidden["visible"]))
        visible = app.beacon_display_status(True, False, {
            "presenterSnapshot": {"displayAllowed": True}, "overlayHasFrame": True,
            "nativeWindowVisible": True, "qtWidgetVisible": True,
            "frameAgeSeconds": .1, "maxAgeSeconds": .35})
        self.assertEqual(("visible", True), (visible["state"], visible["visible"]))

    def test_target_toggle_restarts_owned_reader_and_preserves_new_setting(self):
        self.ready()
        self.route_table().insert("", "end", values=("Ground", "0", "0"))
        target = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Checkbutton)
                      and "selected target" in str(w["text"]).casefold())
        with patch("scripts.physical_waypoint_overlay.bind_companion_window", return_value={
                "processId": 456, "processStartUtcTicks": "123456789", "hwnd": 65536}):
            self.marker_toggle().invoke()
            self.root.update()
            self.assertFalse(target.instate(["disabled"]))
            target.invoke()
            deadline = time.monotonic() + 1
            while self.marker.start.call_count < 2 and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
        self.assertEqual(1, self.marker.stop.call_count)
        self.assertEqual(2, self.marker.start.call_count)
        self.assertTrue(self.marker.start.call_args.kwargs["target_beacon"])

    def test_guide_control_requires_exactly_one_selected_waypoint(self):
        self.ready()
        table = self.route_table()
        first = table.insert("", "end", values=("A", "0", "0"))
        second = table.insert("", "end", values=("B", "1", "0"))
        guide = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Checkbutton)
                     and str(w["text"]) == "Guide selected marker")
        self.root.update()
        self.assertTrue(guide.instate(["disabled"]))
        table.selection_set(first)
        table.event_generate("<<TreeviewSelect>>")
        deadline = time.monotonic() + 1
        while guide.instate(["disabled"]) and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(guide.instate(["disabled"]))
        table.selection_set((first, second))
        table.event_generate("<<TreeviewSelect>>")
        deadline = time.monotonic() + 1
        while not guide.instate(["disabled"]) and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(guide.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
