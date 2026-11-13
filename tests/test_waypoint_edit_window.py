"""Selected waypoint edits through withdrawn Tk callbacks and fake poses."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class WaypointEditTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def prepare(self):
        self.identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                         "unitKey": "player", "processId": 123, "processStartUtcTicks": "12345"}
        self.document = {"waypoints": [["First", 0, 0], ["Second", 1, 0]],
                         "heights": [10, 11],
                         "recording": {"complete": True, "version": 1,
                                       "identity": {"runtimeIdentity": dict(self.identity)},
                                       "sources": ["native-source.json"],
                                       "firstObservedAtUtc": "2026-11-13T10:00:00Z",
                                       "lastObservedAtUtc": "2026-11-13T10:00:05Z"}}
        route = self.path / "source.json"
        route.write_text(json.dumps(self.document))
        self.checkpoint = fixture.PlaybackWindowStateTests.write_checkpoint(self, self.document, "forward", 1)
        self.original = self.checkpoint.read_bytes()
        self.pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.adapter = SimpleNamespace(read=lambda **kwargs: self.pose, pid=123,
                                       binding={"runtimeIdentity": dict(self.identity)},
                                       input_receipt_path=self.path / "unused")
        self.launch(self.adapter, route)
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview)
                          and tuple(w["columns"]) == ("name", "x", "z"))
        self.items = self.table.get_children()
        # Normalize whichever row a restored checkpoint selected before this
        # test explicitly chooses its editing target.
        self.button("Reset fields").invoke()
        self.table.selection_set(self.items[0])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)
                        and not isinstance(w, fixture.ttk.Combobox)][:3]
        self.assertEqual(["First", "0.000000", "0.000000"], [w.get() for w in self.entries])
        self.cache = self.path / "artifacts" / "waypoint-last-route.json"
        self.cache_before = self.cache.read_bytes() if self.cache.exists() else None

    def enter(self, name, x, z):
        for widget, value in zip(self.entries, (name, x, z)):
            widget.delete(0, "end")
            widget.insert(0, value)

    def save_document(self):
        destination = self.path / "saved.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)):
            self.button("Save As").invoke()
        return json.loads(destination.read_text())

    def assert_unsaved_cache(self):
        current = self.cache.read_bytes() if self.cache.exists() else None
        self.assertEqual(self.cache_before, current)

    def route_label(self):
        labels = [str(w.cget("textvariable")) for w in self.widgets(self.root)
                  if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]
        return next(str(self.root.getvar(value)) for value in labels
                    if str(self.root.getvar(value)).startswith(("source.json ", "saved.json ")))

    def text_values(self):
        return [str(self.root.getvar(w.cget("textvariable"))) for w in self.widgets(self.root)
                if isinstance(w, fixture.ttk.Label) and w.cget("textvariable")]

    def test_quick_save_uses_loaded_path_and_tracks_real_edits(self):
        self.prepare()
        self.assertEqual("source.json — Saved", self.route_label())
        self.button("Update Selected").invoke()
        self.button("Up").invoke()
        self.assertEqual("source.json — Saved", self.route_label())
        self.enter("Renamed", "0", "0")
        self.button("Update Selected").invoke()
        self.assertEqual("source.json — Unsaved changes", self.route_label())
        with patch("tkinter.filedialog.asksaveasfilename") as dialog:
            self.button("Save Route").invoke()
        dialog.assert_not_called()
        saved = json.loads((self.path / "source.json").read_text())
        self.assertEqual("Renamed", saved["waypoints"][0][0])
        self.assertEqual(self.document["heights"], saved["heights"])
        self.assertEqual(self.document["recording"], saved["recording"])
        self.assertEqual("source.json — Saved", self.route_label())

    def test_save_as_cancel_and_failure_keep_path_and_dirty_state(self):
        self.prepare()
        self.enter("Changed", "0", "0")
        self.button("Update Selected").invoke()
        original = (self.path / "source.json").read_bytes()
        with patch("tkinter.filedialog.asksaveasfilename", return_value="") as dialog:
            self.button("Save As").invoke()
        self.assertEqual("source.json", dialog.call_args.kwargs["initialfile"])
        self.assertEqual(str(self.path), dialog.call_args.kwargs["initialdir"])
        self.assertEqual("source.json — Unsaved changes", self.route_label())
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(self.path / "saved.json")), \
             patch("scripts.waypoint_progress.os.replace", side_effect=OSError("disk denied")), \
             patch("tkinter.messagebox.showerror") as error:
            self.button("Save As").invoke()
        error.assert_called_once()
        self.assertEqual(original, (self.path / "source.json").read_bytes())
        self.assertEqual("source.json — Unsaved changes", self.route_label())
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(self.path / "saved.json")):
            self.button("Save As").invoke()
        self.assertEqual("saved.json — Saved", self.route_label())

    def test_rename_preserves_metadata_order_and_selection_but_invalidates_progress(self):
        self.prepare()
        self.enter("Renamed" * 15, "0", "0")
        self.button("Update Selected").invoke()
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual(self.items, self.table.get_children())
        self.assertEqual((self.items[0],), self.table.selection())
        self.assertEqual(("Renamed" * 15)[:80], self.table.item(self.items[0], "values")[0])
        self.assert_unsaved_cache()
        saved = self.save_document()
        self.assertEqual(self.document["heights"], saved["heights"])
        self.assertEqual(self.document["recording"], saved["recording"])

    def test_coordinate_edit_discards_recording_metadata(self):
        self.prepare()
        self.enter("First", "0.5", "1.25")
        self.button("Update Selected").invoke()
        self.assertTrue(any("Measured height removed" in value for value in self.text_values()),
                        self.text_values())
        self.assertFalse(self.checkpoint.exists())
        self.assert_unsaved_cache()
        saved = self.save_document()
        self.assertEqual(["First", .5, 1.25], saved["waypoints"][0])
        self.assertEqual([None, 11], saved["heights"])
        self.assertIsNone(saved["pointMeasurements"][0])
        self.assertIsNotNone(saved["pointMeasurements"][1])
        self.assertNotIn("recording", saved)

    def test_noop_and_invalid_fields_preserve_route_checkpoint_and_metadata(self):
        self.prepare()
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        for bad in ("nan", "inf", "wrong"):
            self.enter("Changed", bad, "0")
            with patch("tkinter.messagebox.showerror") as error:
                self.button("Update Selected").invoke()
            error.assert_not_called()
            self.assertTrue(any("finite numeric X and Z" in value for value in self.text_values()), self.text_values())
            self.assertEqual("First", self.table.item(self.items[0], "values")[0])
            self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.button("Reset fields").invoke()
        self.table.selection_set(self.items)
        self.table.event_generate("<<TreeviewSelect>>")
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.assert_unsaved_cache()
        self.assertEqual(self.document, self.save_document())

    def test_new_addition_keeps_form_coherent_with_selected_row(self):
        self.prepare()
        self.button("New point").invoke()
        self.assertEqual((), self.table.selection())
        self.assertEqual(self.items, self.table.get_children())
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.enter("New point", "2", "0")
        self.button("Add X / Z").invoke()
        self.root.update()
        added = self.table.get_children()[-1]
        self.assertEqual((added,), self.table.selection())
        self.assertEqual(["New point", "2.000000", "0.000000"], [w.get() for w in self.entries])
        self.assertEqual(tuple(self.entries[i].get() for i in range(3)), self.table.item(added, "values"))
        self.table.selection_set(self.items[0])
        self.root.update()
        self.assertEqual("First", self.entries[0].get())

    def test_immediate_added_row_update_keeps_name_and_subprecision_noop_keeps_metadata(self):
        self.prepare()
        # Values that serialize to the same stored precision are no-ops.
        self.enter("First", "0.0000001", "0")
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.button("New point").invoke()
        self.assertEqual((), self.table.selection())
        self.assertEqual(self.items, self.table.get_children())
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.enter("New point", "2", "0")
        self.button("Add X / Z").invoke()
        self.root.update()
        added = self.table.selection()[0]
        self.assertEqual("New point", self.entries[0].get())
        self.checkpoint.write_bytes(self.original)
        self.button("Update Selected").invoke()
        self.assertEqual("New point", self.table.item(added, "values")[0])
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.entries[1].delete(0, "end")
        self.entries[1].insert(0, "2.5")
        self.button("Update Selected").invoke()
        self.assertEqual(("New point", "2.500000", "0.000000"), self.table.item(added, "values"))
        self.assertEqual(["New point", "2.500000", "0.000000"], [w.get() for w in self.entries])
        # The injected checkpoint belongs to the original route, not this edited route.
        self.assertEqual(self.original, self.checkpoint.read_bytes())

    def test_set_selected_to_current_preserves_name_order_and_undo_restores(self):
        self.prepare()
        original = [self.table.item(item, "values") for item in self.items]
        self.pose = app.Snapshot(app.Position(7.25, 19.5, 8.75), 10, time.monotonic(),
                                 "replacement-native.json")
        self.button("Set selected to current").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.root.update()
            values = self.table.item(self.items[0], "values")
            if tuple(values[1:]) == ("7.250000", "8.750000"):
                break
            time.sleep(.01)
        self.assertEqual(("First", "7.250000", "8.750000"), self.table.item(self.items[0], "values"))
        self.assertEqual(self.items, self.table.get_children())
        self.assertEqual((self.items[0],), self.table.selection())
        saved = self.save_document()
        self.assertEqual(19.5, saved["heights"][0])
        self.assertEqual("replacement-native.json", saved["pointMeasurements"][0]["source"])
        self.button("Undo").invoke()
        restored_items = self.table.get_children()
        self.assertEqual(original, [self.table.item(item, "values") for item in restored_items])
        self.assertEqual(0, self.table.index(self.table.selection()[0]))

    def test_edit_actions_follow_selection_and_reset_restores_fields(self):
        self.prepare()
        self.assertEqual("disabled", str(self.button("Up")["state"]))
        self.assertNotEqual("disabled", str(self.button("Down")["state"]))
        self.enter("Draft", "2", "3")
        self.button("Reset fields").invoke()
        self.assertEqual(["First", "0.000000", "0.000000"], [w.get() for w in self.entries])
        self.table.selection_remove(self.table.selection())
        self.root.update()
        for label in ("Update Selected", "Set selected to current", "Remove", "Up", "Down"):
            self.assertEqual("disabled", str(self.button(label)["state"]), label)

    def test_pending_form_draft_is_not_silently_overwritten_by_selection(self):
        self.prepare()
        self.enter("Unapplied draft", "2", "3")
        self.table.selection_set(self.items[1])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        self.assertEqual((self.items[0],), self.table.selection())
        self.assertEqual(["Unapplied draft", "2", "3"], [w.get() for w in self.entries])
        self.assertTrue(any("Apply" in value and "Reset" in value for value in self.text_values()),
                        self.text_values())
        self.button("Reset fields").invoke()
        self.table.selection_set(self.items[1])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        self.assertEqual((self.items[1],), self.table.selection())
        self.assertEqual(["Second", "1.000000", "0.000000"], [w.get() for w in self.entries])


if __name__ == "__main__":
    unittest.main()
