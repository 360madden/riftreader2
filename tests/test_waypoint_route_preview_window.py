"""Route-list and local-preview behavior with withdrawn Tk and fake poses.

These checks never send game input.  They exercise the real window callbacks
with the same fixture used by the other waypoint GUI tests.
"""
import json
import re
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class RoutePreviewWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    write_checkpoint = fixture.PlaybackWindowStateTests.write_checkpoint
    route_table = fixture.PlaybackWindowStateTests.route_table

    def prepare(self, points=None, *, pose=None, heights=None):
        points = points if points is not None else [["First", 0, 2], ["Second", 0, 7]]
        heights = heights if heights is not None else [10] * len(points)
        self.document = {"waypoints": points, "heights": heights}
        self.route = self.path / "route.json"
        self.route.write_text(json.dumps(self.document), encoding="utf-8")
        self.pose = pose or app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        self.read = Mock(return_value=self.pose)
        # An empty route is the app's normal new-document state; serialized
        # route files intentionally require at least one waypoint.
        self.launch(SimpleNamespace(read=self.read, pid=123), self.route if points else None)
        self.root = self.roots[0]
        self.table = self.route_table()
        self.canvas = next(w for w in self.widgets(self.root) if isinstance(w, fixture.tk.Canvas))
        self.entries = [w for w in self.widgets(self.root)
                        if isinstance(w, fixture.ttk.Entry)
                        and not isinstance(w, fixture.ttk.Combobox)][:3]

    def settle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.root.update()
            if (all(not thread.is_alive() for thread in self.threads)
                    and str(self.button("Refresh")["state"]) != "disabled"):
                return
            time.sleep(.01)
        self.fail("preview callback did not settle")

    def click(self, x, y):
        # A withdrawn widget is intentionally never mapped to the desktop, so
        # Windows does not deliver a synthetic pointer event to it. Invoke the
        # registered Tk binding with a complete ButtonPress substitution tuple.
        command = re.search(r'\[([^ ]+)', self.canvas.bind("<Button-1>")).group(1)
        x, y = round(x), round(y)
        self.root.tk.call(command, 0, 1, 0, 100, 0, 0, 0, 100, x, y,
                          "", 0, "??", 0, str(self.canvas), 4, x, y, 0)
        self.root.update()

    def tagged_centers(self, tag):
        centers = []
        for item in self.canvas.find_withtag(tag):
            box = self.canvas.bbox(item)
            if box:
                centers.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
        return centers

    def blank_point(self):
        occupied = self.tagged_centers("waypoint-node") + self.tagged_centers("number-badge")
        for point in ((18, 82), (82, 82), (18, 50), (82, 50), (25, 25), (75, 75)):
            if all((point[0] - x) ** 2 + (point[1] - y) ** 2 > 18 ** 2 for x, y in occupied):
                return point
        self.fail("fixture could not find blank preview space")

    def labels(self):
        return [str(self.root.getvar(w["textvariable"])) for w in self.widgets(self.root)
                if isinstance(w, fixture.ttk.Label) and w["textvariable"]]

    def assert_ordinals(self, expected):
        self.assertEqual([str(value) for value in expected],
                         [self.table.item(item, "text") for item in self.table.get_children()])

    def test_node_and_badge_click_select_without_read_or_add(self):
        self.prepare()
        items = self.table.get_children()
        before_values = [self.table.item(item, "values") for item in items]
        before_reads = self.read.call_count

        self.table.selection_set(items[1])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        node = self.tagged_centers("waypoint-node")[0]
        self.click(*node)
        self.assertEqual((items[0],), self.table.selection())

        self.table.selection_set(items[0])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        badge = self.tagged_centers("number-badge")[1]
        self.click(*badge)
        self.assertEqual((items[1],), self.table.selection())
        self.assertEqual(before_reads, self.read.call_count)
        self.assertEqual(before_values,
                         [self.table.item(item, "values") for item in self.table.get_children()])

    def test_pending_draft_map_click_preserves_fields_selection_and_route(self):
        self.prepare()
        items = self.table.get_children()
        self.table.selection_set(items[0])
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        for entry, value in zip(self.entries, ("Unapplied draft", "3", "4")):
            entry.delete(0, "end")
            entry.insert(0, value)
        before_reads = self.read.call_count
        before_rows = [self.table.item(item, "values") for item in items]

        # A node click would normally change selection; a pending draft blocks
        # both selection and blank-space addition.
        self.click(*self.tagged_centers("waypoint-node")[1])
        self.click(*self.blank_point())
        self.assertEqual((items[0],), self.table.selection())
        self.assertEqual(["Unapplied draft", "3", "4"], [entry.get() for entry in self.entries])
        self.assertEqual(before_rows, [self.table.item(item, "values") for item in items])
        self.assertEqual(before_reads, self.read.call_count)

    def test_blank_click_uses_fresh_default_name_and_one_pose_read(self):
        self.prepare()
        first = self.table.get_children()[0]
        self.table.selection_set(first)
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        self.assertEqual("First", self.entries[0].get())
        before_reads = self.read.call_count

        self.click(*self.blank_point())
        self.settle()
        rows = self.table.get_children()
        self.assertEqual(3, len(rows))
        self.assertEqual("Point 3", self.table.item(rows[-1], "values")[0])
        self.assertEqual(before_reads + 1, self.read.call_count)
        self.assertEqual((rows[-1],), self.table.selection())

    def test_ordinals_follow_current_order_through_edit_and_undo(self):
        self.prepare()
        self.assertEqual(("name", "x", "z"), tuple(self.table["columns"]))
        self.assert_ordinals((1, 2))

        self.table.selection_remove(self.table.selection())
        self.table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        for entry, value in zip(self.entries, ("Third", "0", "3")):
            entry.delete(0, "end")
            entry.insert(0, value)
        self.button("Add X / Z").invoke()
        self.assert_ordinals((1, 2, 3))

        self.button("Up").invoke()
        self.assert_ordinals((1, 2, 3))
        selected = self.table.selection()[0]
        self.assertEqual(1, self.table.index(selected))
        self.button("Remove").invoke()
        self.assert_ordinals((1, 2))
        self.button("Undo").invoke()
        self.assert_ordinals((1, 2, 3))
        self.assertEqual("Third", self.table.item(self.table.get_children()[1], "values")[0])

    def test_reverse_progress_keeps_original_badge_numbers(self):
        points = [["One", 0, 1], ["Two", 0, 2], ["Three", 0, 3]]
        document = {"waypoints": points, "heights": [10, 10, 10]}
        route = self.path / "reverse.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        self.write_checkpoint(document, "reverse", 0)
        pose = app.Snapshot(app.Position(0, 10, 3), 0, time.monotonic(), "fake")
        self.read = Mock(return_value=pose)
        self.launch(SimpleNamespace(read=self.read, pid=123), route)
        self.root = self.roots[0]
        self.canvas = next(w for w in self.widgets(self.root) if isinstance(w, fixture.tk.Canvas))

        # Reverse traversal is drawn Three -> Two -> One, but badges retain the
        # route's stable original numbers 3 -> 2 -> 1.
        badge_text = [self.canvas.itemcget(item, "text")
                      for item in self.canvas.find_withtag("waypoint-number")]
        self.assertEqual(["3", "2", "1"], badge_text)

    def test_fit_is_cached_and_reports_capped_points(self):
        self.prepare(points=[["Near", 0, 1], ["Beyond preview", 0, 50]])
        before_reads = self.read.call_count
        self.button("Fit").invoke()
        self.root.update()
        self.assertEqual(before_reads, self.read.call_count)
        self.assertTrue(any("off-screen" in value.casefold() for value in self.labels()), self.labels())

    def test_empty_route_disables_fit_and_compact_toolbar_fits_budget(self):
        self.prepare(points=[], heights=[])
        self.assertEqual("disabled", str(self.button("Fit")["state"]))
        fit = self.button("Fit")
        toolbar = fit.master
        self.root.update_idletasks()
        requested = sum(child.winfo_reqwidth() for child in toolbar.winfo_children())
        self.assertLessEqual(requested, 330)
        style_name = str(self.table.cget("style")) or "Treeview"
        self.assertGreaterEqual(int(fixture.ttk.Style(self.root).lookup(style_name, "rowheight")), 22)


if __name__ == "__main__":
    unittest.main()
