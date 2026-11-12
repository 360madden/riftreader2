"""Saved-sample picker tests with withdrawn Tk, fake loader and fake view backend."""
import json
import threading
import time
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from scripts.waypoint_measurements import loaded_unit_measurement
from tests import test_waypoint_view_window as view
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class NearbyPickerTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    prepare = view.ViewWindowTests.prepare
    wait_idle = view.ViewWindowTests.wait_idle

    def ready(self):
        self.prepare()
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.before = [self.table.item(item, "values") for item in self.table.get_children()]
        self.pickers = []
        actual = fixture.tk.Toplevel
        def withdrawn(*args, **kwargs):
            picker = actual(*args, **kwargs)
            picker.withdraw()
            self.pickers.append(picker)
            return picker
        self.stack.enter_context(patch.object(fixture.tk, "Toplevel", side_effect=withdrawn))
        original = dict(fixture.TEST_IDENTITY, processId=99, processStartUtcTicks="123")
        position = {"x": .5, "y": 10, "z": .25}
        receipt = loaded_unit_measurement(position, original, "retained-native.json", "2026-11-12T12:00:00Z",
                    unit_key="456", entity_address="65536", source_sha256="b" * 64)
        self.rows = [dict(number=1, label="Saved NPC", unitKey="456", entityAddressDecimal="65536",
                          position=position, observedAtUtc="2026-11-12T12:00:00Z", distance=.56,
                          measurement=receipt)]
        self.loader = self.stack.enter_context(patch("scripts.saved_nearby_waypoints.load_saved_nearby_waypoints",
                                                    return_value=self.rows))

    def picker_button(self, label):
        return next(w for w in self.widgets(self.pickers[-1]) if isinstance(w, fixture.ttk.Button)
                    and str(w["text"]) == label)

    def open_picker(self):
        with patch("tkinter.filedialog.askopenfilename", return_value="retained-units-sample.json") as chooser:
            self.button("Add nearby").invoke()
        return chooser

    def select(self):
        listing = next(w for w in self.widgets(self.pickers[-1]) if isinstance(w, fixture.ttk.Treeview))
        listing.selection_set(listing.get_children()[0])
        self.root.update()

    def route_values(self):
        return [self.table.item(item, "values") for item in self.table.get_children()]

    def test_cancel_and_empty_selection_do_not_mutate_route(self):
        self.ready()
        chooser = self.open_picker()
        self.assertIs(chooser.call_args.kwargs["parent"], self.root)
        self.assertEqual("disabled", str(self.picker_button("Add Selected")["state"]))
        self.picker_button("Add Selected").invoke()
        self.picker_button("Cancel").invoke()
        self.assertEqual(self.before, self.route_values())
        self.assertFalse((self.path / "artifacts" / "waypoint-current-progress.json").exists())

    def test_add_preserves_original_receipt_height_time_and_undo(self):
        self.ready()
        expected = deepcopy(self.rows[0]["measurement"])
        self.open_picker()
        self.select()
        self.picker_button("Add Selected").invoke()
        self.assertEqual("Saved NPC", self.route_values()[-1][0])
        destination = self.path / "saved-nearby.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)):
            self.button("Save As").invoke()
        document = json.loads(destination.read_text())
        self.assertEqual(expected, document["pointMeasurements"][-1])
        self.assertEqual(10, document["heights"][-1])
        self.button("Undo").invoke()
        self.assertEqual(self.before, self.route_values())
        self.assertFalse((self.path / "artifacts" / "waypoint-current-progress.json").exists())

    def test_invalid_source_does_not_open_or_mutate(self):
        self.ready()
        self.loader.side_effect = ValueError("wrong observer")
        with patch("tkinter.messagebox.showerror") as error:
            self.open_picker()
        error.assert_called_once()
        self.assertEqual([], self.pickers)
        self.assertEqual(self.before, self.route_values())

    def test_different_height_or_changed_owner_refuses_add(self):
        self.ready()
        self.rows[0]["position"]["y"] = 12
        self.open_picker()
        self.select()
        self.picker_button("Add Selected").invoke()
        self.assertEqual(self.before, self.route_values())
        self.picker_button("Cancel").invoke()
        self.rows[0]["position"]["y"] = 10
        self.open_picker()
        self.select()
        self.adapter.binding["runtimeIdentity"]["unitKey"] = "other"
        self.picker_button("Add Selected").invoke()
        self.assertEqual(self.before, self.route_values())
        self.picker_button("Cancel").invoke()

    def test_latest_saved_view_source_used_then_cleared_for_no_units_or_failure(self):
        self.ready()
        backend = Mock(return_value={"status": "saved-route-view-candidate", "image": str(self.path / "view.png"),
            "inputSent": False, "focusChanged": False, "rerun": {"status": "unavailable"},
            "unitSample": {"status": "saved", "path": "latest-units-sample.json"}})
        with patch("scripts.save_physical_route_view.save_route_view", backend):
            self.button("Save view").invoke()
            self.wait_idle()
            with patch("tkinter.filedialog.askopenfilename") as chooser:
                self.button("Add nearby").invoke()
            chooser.assert_not_called()
            self.assertEqual("latest-units-sample.json", self.loader.call_args.args[0])
            self.picker_button("Cancel").invoke()
            backend.return_value.pop("unitSample")
            self.button("Save view").invoke()
            self.wait_idle()
            self.open_picker().assert_called_once()
            self.picker_button("Cancel").invoke()
            backend.return_value["unitSample"] = {"status": "saved", "path": "new-units-sample.json"}
            self.button("Save view").invoke()
            self.wait_idle()
            backend.side_effect = ValueError("capture failed")
            self.button("Save view").invoke()
            self.wait_idle()
            self.open_picker().assert_called_once()
            self.picker_button("Cancel").invoke()

    def test_parent_close_destroys_picker_and_no_source_chooser_cancellation_mutates(self):
        self.ready()
        with patch("tkinter.filedialog.askopenfilename", return_value=""):
            self.button("Add nearby").invoke()
        self.loader.assert_not_called()
        self.open_picker()
        picker = self.pickers[-1]
        self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))
        try:
            self.assertFalse(picker.winfo_exists())
        except fixture.tk.TclError:
            pass  # Destroying the parent also destroys the Tcl application.

    def test_full_route_refuses_add_without_dropping_picker_or_points(self):
        self.ready()
        for number in range(18):
            self.table.insert("", "end", values=(f"Extra {number}", "0", "0"))
        self.open_picker()
        self.select()
        self.picker_button("Add Selected").invoke()
        self.assertEqual(20, len(self.table.get_children()))
        self.assertTrue(self.pickers[-1].winfo_exists())
        self.picker_button("Cancel").invoke()

    def test_owned_markers_disable_picker_and_refuse_source_loading(self):
        from types import SimpleNamespace
        marker = SimpleNamespace(running=Mock(return_value=False), stop=Mock(),
                                 stop_requested=False, exit_code=None)
        with patch.object(fixture.app, "OwnedWaypointMarkers", return_value=marker):
            self.ready()
        marker.running.return_value = True
        # Process the existing idle timer; no native acquisition is installed.
        import time
        deadline = time.monotonic() + 1
        while str(self.button("Add nearby")["state"]) != "disabled" and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertEqual("disabled", str(self.button("Add nearby")["state"]))
        self.button("Add nearby").invoke()
        self.loader.assert_not_called()

    def test_busy_view_disables_picker_until_worker_finishes(self):
        self.ready()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def save(*args, **kwargs):
            entered.set()
            release.wait(2)
            return {"status": "saved-route-view-candidate", "image": str(self.path / "view.png"),
                    "inputSent": False, "focusChanged": False, "rerun": {"status": "unavailable"}}
        with patch("scripts.save_physical_route_view.save_route_view", side_effect=save):
            self.button("Save view").invoke()
            self.assertTrue(entered.wait(1))
            self.assertEqual("disabled", str(self.button("Add nearby")["state"]))
            self.button("Add nearby").invoke()
            self.loader.assert_not_called()
            release.set()
            self.wait_idle()
        self.assertNotEqual("disabled", str(self.button("Add nearby")["state"]))

    def test_inflight_idle_read_allows_last_known_browsing_but_add_waits_for_fresh_owner(self):
        self.ready()
        reading, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def read(**kwargs):
            reading.set()
            release.wait(2)
            return fixture.app.Snapshot(fixture.app.Position(0, 10, 0), 0, time.monotonic(), "fresh fake")
        self.adapter.read = read
        # Let the existing two-second idle observer start with the previous
        # verified pose now stale; no native reader is installed in this test.
        time.sleep(2.05)
        self.root.update()
        self.assertTrue(reading.wait(1))
        self.open_picker()
        self.loader.assert_called_once()
        self.assertEqual(fixture.TEST_IDENTITY, self.loader.call_args.args[1])
        self.select()
        self.picker_button("Add Selected").invoke()
        self.assertEqual(self.before, self.route_values())
        self.assertTrue(self.pickers[-1].winfo_exists())
        release.set()
        self.wait_idle()
        deadline = time.monotonic() + 1
        while self.route_values() == self.before and time.monotonic() < deadline:
            self.root.update()
            self.picker_button("Add Selected").invoke()
            time.sleep(.01)
        self.assertEqual("Saved NPC", self.route_values()[-1][0])


if __name__ == "__main__":
    unittest.main()
