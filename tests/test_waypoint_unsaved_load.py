"""Unsaved route switching through withdrawn Tk and fake readers only."""
import json
import unittest
from unittest.mock import patch

from tests import test_waypoint_edit_window as edits
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class UnsavedLoadTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    prepare = edits.WaypointEditTests.prepare
    enter = edits.WaypointEditTests.enter
    route_label = edits.WaypointEditTests.route_label

    def dirty_route(self):
        self.prepare()
        self.enter("Named beacon", "0", "0")
        self.button("Update Selected").invoke()
        self.other = self.path / "other.json"
        self.other_document = {"waypoints": [["Other", 2, 0]]}
        self.other.write_text(json.dumps(self.other_document), encoding="utf-8")
        self.source = self.path / "source.json"
        self.source_before = self.source.read_bytes()
        # A dirty route may coexist with newly saved playback progress.
        edited = {**self.document, "waypoints": [["Named beacon", 0, 0], ["Second", 1, 0]]}
        fixture.PlaybackWindowStateTests.write_checkpoint(self, edited, "forward", 1)

    def values(self):
        return [self.table.item(item, "values") for item in self.table.get_children()]

    def snapshot(self):
        return (self.values(), self.route_label(), str(self.button("Undo")["state"]),
                {str(path.relative_to(self.path)): path.read_bytes()
                 for path in self.path.rglob("*.json")})

    def load(self, path=None):
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path or self.other)):
            self.button("Load").invoke()

    def test_cancel_preserves_route_path_progress_cache_history_and_saved_files(self):
        self.dirty_route()
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.load()
        self.assertEqual(before, self.snapshot())
        self.assertIs(ask.call_args.kwargs["parent"], self.root)
        self.button("Undo").invoke()
        self.assertEqual("First", self.values()[0][0])

    def test_failed_save_refuses_load_and_preserves_everything(self):
        self.dirty_route()
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("scripts.waypoint_progress.os.replace", side_effect=OSError("disk denied")), \
             patch("tkinter.messagebox.showerror") as error:
            self.load()
        error.assert_called_once()
        self.assertEqual(before, self.snapshot())

    def test_cancelled_save_chooser_refuses_load_for_new_unsaved_route(self):
        with patch.object(fixture.app, "PhysicalAdapter", side_effect=ValueError("offline")):
            self.launch()
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)
                        and not isinstance(w, fixture.ttk.Combobox)]
        self.enter("New beacon", "1", "2")
        self.button("Add X / Z").invoke()
        other = self.path / "other.json"
        other.write_text(json.dumps({"waypoints": [["Other", 2, 0]]}), encoding="utf-8")
        before = self.values()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            self.load(other)
        self.assertEqual(before, self.values())
        self.assertNotEqual("disabled", str(self.button("Undo")["state"]))
        self.assertFalse((self.path / "artifacts" / "waypoint-last-route.json").exists())

    def test_save_then_load_keeps_edits_in_original_file(self):
        self.dirty_route()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("tkinter.filedialog.asksaveasfilename") as chooser:
            self.load()
        chooser.assert_not_called()
        self.assertEqual("Named beacon", json.loads(self.source.read_text())["waypoints"][0][0])
        self.assertEqual("Other", self.values()[0][0])
        self.assertEqual("disabled", str(self.button("Undo")["state"]))
        self.assertEqual(self.other_document, json.loads(self.cache.read_text())["route"])

    def test_discard_loads_destination_without_saving_original(self):
        self.dirty_route()
        with patch("tkinter.messagebox.askyesnocancel", return_value=False):
            self.load()
        self.assertEqual(self.source_before, self.source.read_bytes())
        self.assertEqual("Other", self.values()[0][0])
        self.assertEqual("disabled", str(self.button("Undo")["state"]))

    def test_save_before_loading_same_file_uses_newly_saved_content(self):
        self.dirty_route()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True):
            self.load(self.source)
        self.assertEqual("Named beacon", self.values()[0][0])
        self.assertEqual("source.json — Saved", self.route_label())

    def test_invalid_destination_is_reported_before_unsaved_prompt(self):
        self.dirty_route()
        self.other.write_text("invalid json", encoding="utf-8")
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel") as ask, \
             patch("tkinter.messagebox.showerror") as error:
            self.load()
        ask.assert_not_called()
        error.assert_called_once()
        self.assertEqual(before, self.snapshot())

    def test_load_recent_uses_same_cancel_guard(self):
        self.dirty_route()
        before = self.snapshot()
        recent_button=self.button("Load recent")
        dropdown = next(w for w in recent_button.master.winfo_children() if isinstance(w, fixture.ttk.Combobox))
        dropdown.current(0)
        self.assertIn(self.source.name,dropdown.get())
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.button("Load recent").invoke()
        ask.assert_called_once()
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
