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
        self.document = {"waypoints": [["First", 0, 0], ["Second", 1, 0]],
                         "heights": [10, 11], "recording": {"complete": True, "source": "retained"}}
        route = self.path / "source.json"
        route.write_text(json.dumps(self.document))
        self.checkpoint = self.path / "artifacts" / "waypoint-current-progress.json"
        self.checkpoint.write_text(json.dumps({"route": self.document, "direction": "forward", "nextIndex": 1}))
        self.original = self.checkpoint.read_bytes()
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=lambda **kwargs: pose, pid=123), route)
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.items = self.table.get_children()
        self.table.selection_set(self.items[0])
        self.root.update()
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)]
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
        self.assertFalse(self.checkpoint.exists())
        self.assert_unsaved_cache()
        saved = self.save_document()
        self.assertEqual(["First", .5, 1.25], saved["waypoints"][0])
        self.assertNotIn("heights", saved)
        self.assertNotIn("recording", saved)

    def test_noop_and_invalid_fields_preserve_route_checkpoint_and_metadata(self):
        self.prepare()
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        for bad in ("nan", "inf", "wrong"):
            self.enter("Changed", bad, "0")
            with patch("tkinter.messagebox.showerror") as error:
                self.button("Update Selected").invoke()
            error.assert_called_once()
            self.assertEqual("First", self.table.item(self.items[0], "values")[0])
            self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.table.selection_set(self.items)
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.assert_unsaved_cache()
        self.assertEqual(self.document, self.save_document())

    def test_new_additions_keep_generated_names_and_explicit_selection_populates_name(self):
        self.prepare()
        # Addition uses the entered name; its automatic selection leaves the
        # next generated name ready for another Save Current or map addition.
        self.enter("New point", "2", "0")
        self.button("Add X / Z").invoke()
        self.root.update()
        self.assertEqual("Point 4", self.entries[0].get())
        self.button("Save Current").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.root.update()
            if len(self.table.get_children()) == 4:
                break
            time.sleep(.01)
        self.assertEqual("Point 4", self.table.item(self.table.get_children()[-1], "values")[0])
        self.assertEqual("Point 5", self.entries[0].get())
        self.table.selection_set(self.items[0])
        self.root.update()
        self.assertEqual("First", self.entries[0].get())

    def test_immediate_added_row_update_keeps_name_and_subprecision_noop_keeps_metadata(self):
        self.prepare()
        # Values that serialize to the same stored precision are no-ops.
        self.enter("First", "0.0000001", "0")
        self.button("Update Selected").invoke()
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.enter("New point", "2", "0")
        self.button("Add X / Z").invoke()
        self.root.update()
        added = self.table.selection()[0]
        self.assertEqual("Point 4", self.entries[0].get())
        self.checkpoint.write_bytes(self.original)
        self.button("Update Selected").invoke()
        self.assertEqual("New point", self.table.item(added, "values")[0])
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.entries[1].delete(0, "end")
        self.entries[1].insert(0, "2.5")
        self.button("Update Selected").invoke()
        self.assertEqual(("New point", "2.500000", "0.000000"), self.table.item(added, "values"))
        self.assertEqual(["New point", "2.500000", "0.000000"], [w.get() for w in self.entries])
        self.assertFalse(self.checkpoint.exists())


if __name__ == "__main__":
    unittest.main()
