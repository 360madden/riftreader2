"""Withdrawn-Tk sizing and STOP access for the movement controls.

No window is mapped and no native reader or game input is used.  Withdrawn Tk
does not allocate most descendants, so clipping coverage uses their real
requested sizes against the compact layout's source-owned column budgets.
"""
import re
import unittest

from tests import test_waypoint_playback_window_state as fixture
from tests import test_waypoint_route_preview_window as preview_fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class MovementControlsLayoutTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch
    route_table = fixture.PlaybackWindowStateTests.route_table
    prepare = preview_fixture.RoutePreviewWindowTests.prepare

    def test_compact_controls_fit_and_escape_reaches_stop(self):
        self.prepare()
        self.assertEqual("withdrawn", self.root.state())
        self.assertFalse(self.root.winfo_ismapped())

        checkboxes = {str(widget.cget("text")): widget
                      for widget in self.widgets(self.root)
                      if isinstance(widget, fixture.ttk.Checkbutton)}
        continuous = checkboxes["Continuous travel"]
        click_move = checkboxes["Click to move · clear path only"]

        # At the 980px minimum width, the 22px outer padding and 3:2 middle
        # split leave about 370px for the map card.  Replay's 4:3:3 split,
        # inner padding and gaps leave about 266px for direct movement.
        self.assertLessEqual(click_move.master.winfo_reqwidth(), 370)
        self.assertLessEqual(continuous.master.winfo_reqwidth(), 266)
        self.assertLessEqual(click_move.winfo_reqwidth(), click_move.master.winfo_reqwidth())
        self.assertLessEqual(continuous.winfo_reqwidth(), continuous.master.winfo_reqwidth())

        stop = self.button("STOP")
        self.root.update_idletasks()
        self.assertGreaterEqual(stop.winfo_width(), stop.winfo_reqwidth())
        self.assertGreaterEqual(stop.winfo_height(), stop.winfo_reqheight())

        # Invoke the registered window-local Escape binding through Tcl because
        # an intentionally withdrawn window cannot receive a synthetic key.
        click_move.invoke()
        self.assertTrue(self.root.getvar(click_move["variable"]))
        script = self.root.bind("<Escape>")
        command = re.search(r"\[([^ ]+)", script).group(1)
        self.root.tk.call(command, 0, 0, 0, 0, 27, 0, 0, 0, 0, 0,
                          "", 0, "Escape", 9, str(self.root), 2, 0, 0, 0)
        self.root.update()
        self.assertFalse(self.root.getvar(click_move["variable"]))


if __name__ == "__main__":
    unittest.main()
