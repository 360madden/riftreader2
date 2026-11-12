"""Window-local point shortcuts with withdrawn Tk and fake readers only."""
import re
import unittest
from unittest.mock import patch

from tests import test_waypoint_edit_window as edits
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class KeyboardWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    prepare = edits.WaypointEditTests.prepare
    enter = edits.WaypointEditTests.enter
    save_document = edits.WaypointEditTests.save_document
    assert_unsaved_cache = edits.WaypointEditTests.assert_unsaved_cache

    def shortcut(self, widget, sequence):
        # Invoke the actual widget binding without any desktop key events.
        command = re.search(r'\[([^ ]+)', widget.bind(sequence)).group(1)
        return self.root.tk.call(command, "fake-event")

    def values(self):
        return [self.table.item(item, "values") for item in self.table.get_children()]

    def test_f2_prefills_and_selects_name_without_route_changes(self):
        self.prepare()
        self.enter("Unapplied", "8", "9")
        with patch.object(self.entries[0], "focus_set") as focus:
            self.assertEqual("break", self.shortcut(self.table, "<F2>"))
        focus.assert_called_once_with()
        self.assertEqual(["First", "0.000000", "0.000000"], [w.get() for w in self.entries])
        self.assertEqual(0, self.entries[0].index("sel.first"))
        self.assertEqual(len("First"), self.entries[0].index("sel.last"))
        self.assertEqual(self.original, self.checkpoint.read_bytes())
        self.assertEqual("disabled", str(self.button("Undo")["state"]))
        self.assert_unsaved_cache()
        self.table.selection_set(self.items)
        self.root.update()
        self.enter("Unapplied", "8", "9")
        with patch.object(self.entries[0], "focus_set") as focus:
            self.assertEqual("break", self.shortcut(self.table, "<F2>"))
        focus.assert_not_called()
        self.assertEqual("Unapplied", self.entries[0].get())

    def test_reorder_and_delete_each_undo_to_original_metadata_and_selection(self):
        self.prepare()
        original = self.values()
        for sequence, expected in (("<Alt-Down>", [original[1], original[0]]),
                                   ("<Alt-Up>", original),
                                   ("<Delete>", [original[1]])):
            with self.subTest(sequence=sequence):
                if sequence == "<Alt-Up>":
                    self.table.selection_set(self.table.get_children()[1])
                    expected = [original[1], original[0]]
                self.assertEqual("break", self.shortcut(self.table, sequence))
                self.assertEqual(expected, self.values())
                self.assertFalse(self.checkpoint.exists())
                self.assertEqual("break", self.shortcut(self.table, "<Control-z>"))
                self.assertEqual(original, self.values())
                self.assertEqual(1 if sequence == "<Alt-Up>" else 0,
                                 self.table.index(self.table.selection()[0]))
                self.assertEqual(self.document, self.save_document())
                self.table.selection_set(self.table.get_children()[0])

    def test_control_enter_from_each_field_uses_edit_metadata_rules(self):
        self.prepare()
        self.enter("Renamed", "0", "0")
        self.assertEqual("break", self.shortcut(self.entries[0], "<Control-Return>"))
        self.assertFalse(self.checkpoint.exists())
        renamed = self.save_document()
        self.assertEqual(self.document["heights"], renamed["heights"])
        self.assertEqual(self.document["recording"], renamed["recording"])
        self.enter("Renamed", "2", "0")
        self.assertEqual("break", self.shortcut(self.entries[1], "<Control-Return>"))
        changed = self.save_document()
        self.assertNotIn("heights", changed)
        self.assertNotIn("recording", changed)
        self.enter("Renamed", "2", "3")
        self.assertEqual("break", self.shortcut(self.entries[2], "<Control-Return>"))
        self.assertEqual(("Renamed", "2.000000", "3.000000"), self.values()[0])

    def test_busy_and_closing_guards_and_no_entry_navigation_bindings(self):
        self.prepare()
        for entry in self.entries:
            for sequence in ("<Delete>", "<Alt-Up>", "<Alt-Down>", "<F2>"):
                self.assertFalse(entry.bind(sequence))
        self.assertFalse(self.table.bind("<Control-Return>"))
        self.assertFalse(self.root.bind("<Delete>"))
        original = self.values()
        self.enter("Unapplied", "8", "9")
        # busy is synchronous; worker completion stays queued until Tk polls.
        self.button("Refresh").invoke()
        for closing in (False, True):
            if closing:
                self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))
            with patch.object(self.entries[0], "focus_set") as focus:
                for sequence in ("<F2>", "<Alt-Up>", "<Alt-Down>", "<Delete>"):
                    self.assertEqual("break", self.shortcut(self.table, sequence))
                for entry in self.entries:
                    self.assertEqual("break", self.shortcut(entry, "<Control-Return>"))
            focus.assert_not_called()
            self.assertEqual(original, self.values())
            self.assertEqual("Unapplied", self.entries[0].get())
            self.assertEqual(self.original, self.checkpoint.read_bytes())



if __name__ == "__main__":
    unittest.main()
