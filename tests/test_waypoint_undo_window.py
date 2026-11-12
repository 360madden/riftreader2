"""Bounded in-memory route undo, using withdrawn Tk and fake pose readers."""
import re
import unittest
from unittest.mock import patch

from tests import test_waypoint_edit_window as edits
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class UndoWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    prepare = edits.WaypointEditTests.prepare
    enter = edits.WaypointEditTests.enter
    save_document = edits.WaypointEditTests.save_document
    assert_unsaved_cache = edits.WaypointEditTests.assert_unsaved_cache

    def values(self):
        return [self.table.item(item, "values") for item in self.table.get_children()]

    def test_coordinate_undo_restores_metadata_selection_without_checkpoint_or_file_changes(self):
        self.prepare()
        source = self.path / "source.json"
        original_file = source.read_bytes()
        self.enter("Changed", "2", "3")
        self.button("Update Selected").invoke()
        self.button("Undo").invoke()
        self.root.update()
        self.assertEqual("First", self.values()[0][0])
        self.assertEqual(0, self.table.index(self.table.selection()[0]))
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assert_unsaved_cache()
        self.assertEqual(original_file, source.read_bytes())
        self.assertEqual(self.document, self.save_document())
        self.assertEqual("disabled", str(self.button("Undo")["state"]))

    def test_remove_reorder_clear_and_empty_undo_keep_order(self):
        self.prepare()
        original = self.values()
        for operation in ("Remove", "Down", "Clear"):
            with self.subTest(operation=operation):
                self.table.selection_set(self.table.get_children()[0])
                self.button(operation).invoke()
                self.button("Undo").invoke()
                self.assertEqual(original, self.values())
                self.assertEqual(0, self.table.index(self.table.selection()[0]))
        self.button("Clear").invoke()
        self.enter("Only", "5", "6")
        self.button("Add X / Z").invoke()
        self.button("Undo").invoke()
        self.assertEqual([], self.values())
        self.button("Undo").invoke()
        self.assertEqual(original, self.values())

    def test_noop_invalid_update_and_boundary_reorder_do_not_push(self):
        self.prepare()
        self.button("Update Selected").invoke()
        self.button("Up").invoke()
        self.enter("Bad", "nan", "0")
        with patch("tkinter.messagebox.showerror"):
            self.button("Update Selected").invoke()
            self.button("Add X / Z").invoke()
        self.assertEqual("disabled", str(self.button("Undo")["state"]))
        self.assertEqual(self.original, self.checkpoint.read_bytes())

    def test_save_retains_history_load_clears_it(self):
        self.prepare()
        self.enter("Renamed", "0", "0")
        self.button("Update Selected").invoke()
        self.save_document()
        self.assertNotEqual("disabled", str(self.button("Undo")["state"]))
        with patch("tkinter.filedialog.askopenfilename", return_value=str(self.path / "saved.json")):
            self.button("Load").invoke()
        self.root.update()
        self.assertEqual("disabled", str(self.button("Undo")["state"]))

    def test_tree_shortcut_guard_refuses_undo_while_busy(self):
        self.prepare()
        self.enter("Changed", "0", "0")
        self.button("Update Selected").invoke()
        # Exercise the command bound ONLY on Treeview, without desktop events.
        command = re.search(r'\[([^ ]+)', self.table.bind("<Control-z>")).group(1)
        self.assertFalse(self.entries[0].bind("<Control-z>"))
        self.button("Refresh").invoke()
        # busy is set synchronously before the read worker is dispatched.
        self.root.tk.call(command)
        self.assertEqual("Changed", self.values()[0][0])
        self.assertEqual("disabled", str(self.button("Undo")["state"]))

    def test_first_add_can_undo_to_initial_empty_route_while_offline(self):
        with patch.object(fixture.app, "PhysicalAdapter", side_effect=ValueError("offline")):
            self.launch()
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)]
        self.enter("First", "1", "2")
        self.button("Add X / Z").invoke()
        self.assertNotEqual("disabled", str(self.button("Undo")["state"]))
        self.button("Undo").invoke()
        self.assertEqual([], self.values())
        self.assertEqual("disabled", str(self.button("Undo")["state"]))

    def test_history_is_bounded_to_twenty_edits(self):
        self.prepare()
        for index in range(25):
            self.enter(f"Rename {index}", "0", "0")
            self.button("Update Selected").invoke()
        for _ in range(20):
            self.button("Undo").invoke()
        self.assertEqual("Rename 4", self.values()[0][0])
        self.assertEqual("disabled", str(self.button("Undo")["state"]))


if __name__ == "__main__":
    unittest.main()
