import json
import unittest
from unittest.mock import patch

from tests import test_waypoint_playback_window_state as fixture


class NewRouteTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    route_table = fixture.PlaybackWindowStateTests.route_table

    def prepare(self):
        self.source = self.path / "original.json"
        self.original = json.dumps({"waypoints": [["Old", 0, 0]]})
        self.source.write_text(self.original)
        self.launch(route=self.source)

    def test_new_route_detaches_file_and_saves_separately(self):
        self.prepare()
        target = self.path / "New hunt route.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(target)) as new_dialog:
            self.button("New Route…").invoke()
        self.roots[0].update()
        self.assertEqual((), self.route_table().get_children())
        self.assertEqual(self.original, self.source.read_text())
        entries = [w for w in self.widgets(self.roots[0])
                   if isinstance(w, fixture.ttk.Entry) and not isinstance(w, fixture.ttk.Combobox)][:3]
        for entry, value in zip(entries, ["First", "1", "2"]):
            entry.delete(0, "end")
            entry.insert(0, value)
        self.roots[0].update()
        self.button("Add X / Z").invoke()
        self.roots[0].update()
        self.assertEqual(1, len(self.route_table().get_children()), [(w.get(),str(w)) for w in entries])
        self.assertEqual(str(self.path / "artifacts" / "waypoint-routes"), new_dialog.call_args.kwargs["initialdir"])
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(target)) as dialog:
            self.button("Save Route").invoke()
        dialog.assert_not_called()
        self.assertEqual("New hunt route", json.loads(target.read_text())["routeName"])
        self.assertEqual(self.original, self.source.read_text())

    def test_cancel_preserves_unsaved_route(self):
        self.prepare()
        self.button("Clear").invoke()
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(self.path / "another.json")), patch(
                "tkinter.messagebox.askyesnocancel", return_value=None) as prompt:
            self.button("New Route…").invoke()
        prompt.assert_called_once()
        self.assertEqual(self.original, self.source.read_text())
        self.assertEqual((), self.route_table().get_children())
