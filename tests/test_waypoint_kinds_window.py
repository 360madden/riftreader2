"""Withdrawn-window checks for route type edits; no game input."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts import waypoint_cli_protocol as protocol
from tests import test_waypoint_playback_window_state as fixture

tk, ttk = fixture.tk, fixture.ttk


@unittest.skipIf(tk is None, "Tk unavailable")
class WaypointKindsWindowTests(unittest.TestCase):
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    route_table = fixture.PlaybackWindowStateTests.route_table
    launch = fixture.PlaybackWindowStateTests.launch

    def setUp(self):
        fixture.PlaybackWindowStateTests.setUp(self)
        owner = self
        class Server(protocol.LocalSessionServer):
            def __init__(self, **kwargs):
                super().__init__(root=owner.path / "helpers", **kwargs)
            def poll(self, dispatch):
                owner.dispatch = dispatch
                return super().poll(dispatch)
        self.stack.enter_context(patch.object(protocol, "LocalSessionServer", Server))
        self.stack.enter_context(patch.object(app, "PhysicalAdapter", side_effect=ValueError("absent")))
        self.launch()

    def call(self, command, **values):
        result = self.dispatch(command, values, "test-" + command)
        self.assertTrue(result["ok"], result)
        self.roots[0].update()
        return result["data"]

    def document(self):
        return self.call("route.list")["document"]

    def test_type_edits_follow_rows_and_survive_save_load(self):
        self.call("route.add", name="A", x=1, z=2, kind="stop")
        self.call("route.add", name="B", x=3, z=4)
        self.call("route.add", name="C", x=5, z=6)
        self.assertEqual(["stop", "pass", "pass"], self.document()["pointKinds"])
        # The real CLI request contains explicit None values for omitted options.
        self.call("route.update", point=2, name=None, x=None, z=None, current=False, kind="stop")
        self.assertEqual(["stop", "stop", "pass"], self.document()["pointKinds"])
        self.call("route.reorder", point=2, to=3)
        self.assertEqual(["A", "C", "B"], [p[0] for p in self.document()["waypoints"]])
        self.assertEqual(["stop", "pass", "stop"], self.document()["pointKinds"])
        self.call("route.remove", point=1)
        self.assertEqual(["pass", "stop"], self.document()["pointKinds"])
        self.call("route.undo")
        self.assertEqual(["stop", "pass", "stop"], self.document()["pointKinds"])
        path = self.path / "saved.json"
        self.call("route.save", file=str(path))
        self.assertEqual(["stop", "pass", "stop"], json.loads(path.read_text(encoding="utf-8"))["pointKinds"])
        self.call("route.new")
        self.call("route.load", file=str(path))
        self.assertEqual(["stop", "pass", "stop"], self.document()["pointKinds"])

    def test_invalid_protocol_types_do_not_mutate_route(self):
        self.call("route.add", name="A", x=1, z=2)
        before = self.call("route.list")
        for command, values in (("route.add", {"name": "B", "x": 3, "z": 4}),
                                ("route.update", {"point": 1})):
            for invalid in ("bogus", [], ["stop"], True):
                with self.subTest(command=command, invalid=invalid):
                    rejected = self.dispatch(command, {**values, "kind": invalid}, "invalid-kind")
                    self.assertFalse(rejected["ok"], rejected)
                    self.assertEqual("invalid-kind", rejected["error"]["code"])
                    after = self.call("route.list")
                    self.assertEqual(before["document"], after["document"])
                    self.assertEqual(before["revision"], after["revision"])
                    self.assertEqual(before["dirty"], after["dirty"])

    def test_selected_gui_type_control_is_undoable(self):
        self.call("route.add", name="A", x=1, z=2)
        self.call("route.add", name="B", x=3, z=4)
        self.call("route.select", point=1)
        control = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Combobox)
                       and tuple(w["values"]) == ("Pass through", "Stop at point"))
        self.assertEqual("Pass through", control.get())
        control.set("Stop at point")
        control.event_generate("<<ComboboxSelected>>")
        self.roots[0].update()
        self.assertEqual(["stop", "pass"], self.document()["pointKinds"])
        self.assertIn("S", self.route_table().item(self.route_table().get_children()[0], "text"))
        self.call("route.undo")
        self.assertNotIn("pointKinds", self.document())
        self.call("route.select", clear=True)
        self.assertEqual("Pass through", control.get())
        self.assertEqual("disabled", str(control["state"]))


if __name__ == "__main__":
    unittest.main()
