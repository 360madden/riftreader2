"""Withdrawn-Tk checks for Library usability and document safety; no game input."""
import json
import threading
import time
import unittest
from unittest.mock import patch

from scripts import waypoint_route_library as library
from tests import test_waypoint_edit_window as edits
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class LibraryWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    prepare = edits.WaypointEditTests.prepare
    enter = edits.WaypointEditTests.enter

    def setup_library(self):
        self.prepare()
        self.library_dir = self.path / "artifacts" / "waypoint-routes"
        self.library_table = next(
            widget for widget in self.widgets(self.root)
            if isinstance(widget, fixture.ttk.Treeview)
            and tuple(widget["columns"]) == ("name", "id", "zone", "heights")
        )
        self.library_tab = self.library_table.master
        named = {widget.winfo_name(): widget for widget in self.widgets(self.library_tab)}
        self.search = named["library_search"]
        self.copy_name = named["library_copy_name"]
        self.button("Refresh library").invoke()
        self.root.update()

    def library_text(self):
        values = []
        for widget in self.widgets(self.library_tab):
            if isinstance(widget, fixture.ttk.Label) and widget.cget("textvariable"):
                values.append(str(self.root.getvar(widget.cget("textvariable"))))
        return "\n".join(values)

    def set_entry(self, widget, value):
        widget.delete(0, "end")
        widget.insert(0, value)
        # Search filtering is intentionally debounced for normal typing.
        deadline = time.monotonic() + .25
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.005)

    def select(self, route_id):
        self.library_table.selection_set(route_id)
        self.library_table.focus(route_id)
        self.library_table.event_generate("<<TreeviewSelect>>")
        self.root.update()

    def write_library_route(self, route_id, name, *, context=None):
        document = {
            "routeName": name,
            "waypoints": [["Start", 0, 0], ["Finish", 3, 4]],
            "heights": [10, None],
        }
        if context is not None:
            document["routeContext"] = context
        self.library_dir.mkdir(parents=True, exist_ok=True)
        (self.library_dir / f"{route_id}.json").write_text(
            json.dumps(document), encoding="utf-8"
        )

    def route_values(self):
        return tuple(tuple(self.table.item(item, "values")) for item in self.table.get_children())

    def test_save_copy_validates_name_selects_copy_and_preserves_working_route(self):
        self.setup_library()
        source_before = (self.path / "source.json").read_bytes()
        rows_before = self.route_values()

        for invalid in ("", "x" * 121):
            self.set_entry(self.copy_name, invalid)
            self.assertEqual("disabled", str(self.button("Save copy")["state"]))

        self.set_entry(self.copy_name, "Working copy")
        self.assertNotEqual("disabled", str(self.button("Save copy")["state"]))
        self.button("Save copy").invoke()
        self.root.update()

        self.assertEqual(1, len(self.library_table.selection()))
        route_id = self.library_table.selection()[0]
        self.assertEqual("Working copy", library.load_route(route_id, self.library_dir)["routeName"])
        self.assertEqual(source_before, (self.path / "source.json").read_bytes())
        self.assertEqual(rows_before, self.route_values())

        self.enter("Pending draft", "0", "0")
        self.root.update()
        self.assertEqual("disabled", str(self.button("Save copy")["state"]))

    def test_search_includes_zone_details_no_results_and_clear(self):
        self.setup_library()
        self.write_library_route("camp", "Camp loop", context={"version": 1, "zoneName": "Silverwood"})
        self.write_library_route("road", "Road loop")
        self.button("Refresh library").invoke()
        self.root.update()

        self.set_entry(self.search, "Silverwood")
        self.assertEqual(("camp",), self.library_table.get_children())
        self.select("camp")
        details = self.library_text()
        self.assertIn("Camp loop", details)
        self.assertIn("Silverwood", details)
        self.assertIn("5.0", details)
        self.assertIn("1 / 2 routes", details)

        self.set_entry(self.search, "definitely-no-such-route")
        self.assertEqual((), self.library_table.get_children())
        self.assertIn("No routes match", self.library_text())
        self.button("Clear filters").invoke()
        self.root.update()
        self.assertEqual({"camp", "road"}, set(self.library_table.get_children()))

    def test_malformed_entry_is_visible_and_cannot_load(self):
        self.setup_library()
        self.library_dir.mkdir(parents=True, exist_ok=True)
        (self.library_dir / "broken.json").write_text("{not-json", encoding="utf-8")
        self.button("Refresh library").invoke()
        self.root.update()

        self.assertIn("broken", self.library_table.get_children())
        self.assertIn("error", self.library_table.item("broken", "tags"))
        self.select("broken")
        self.assertEqual("disabled", str(self.button("Load selected")["state"]))
        self.assertIn("Unavailable:", self.library_text())

    def test_dirty_cancel_busy_and_double_click_preserve_current_document(self):
        self.setup_library()
        self.write_library_route("other", "Other route")
        self.button("Refresh library").invoke()
        self.root.update()
        self.select("other")

        self.enter("Unsaved", "0", "0")
        self.button("Update Selected").invoke()
        dirty_values = self.route_values()
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as prompt:
            self.button("Load selected").invoke()
        prompt.assert_called_once()
        self.assertEqual(dirty_values, self.route_values())

        entered = threading.Event()
        release = threading.Event()
        original_read = self.adapter.read

        def blocking_read(**kwargs):
            entered.set()
            release.wait(2)
            return original_read(**kwargs)

        self.adapter.read = blocking_read
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 2
        while not entered.is_set() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(entered.is_set())
        self.root.update()
        self.assertEqual("disabled", str(self.button("Load selected")["state"]))
        with patch.object(library, "load_route", side_effect=AssertionError("busy load")):
            self.button("Load selected").invoke()
            # Tk rejects a synthetic <Double-1> modifier; two presses exercise
            # the same binding through Tk's click-count recognition.
            self.library_table.event_generate("<Button-1>", x=5, y=25)
            self.library_table.event_generate("<Button-1>", x=5, y=25)
            self.root.update()
        self.assertEqual(dirty_values, self.route_values())
        release.set()


if __name__ == "__main__":
    unittest.main()
