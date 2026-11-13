"""Waypoint theme state checks use only a withdrawn Tk root."""
import unittest

from scripts.waypoint_ui_theme import PALETTE, apply_theme, summarize_status


class WaypointThemeTests(unittest.TestCase):
    def test_routine_path_compaction_preserves_failures_and_stop_reasons(self):
        self.assertEqual("Route loaded", summarize_status(r"Route loaded: C:\routes\first.json"))
        self.assertEqual("Snapshot saved", summarize_status(r"View saved: C:\captures\view.png"))
        self.assertEqual("Run receipt saved", summarize_status(r"Run receipt: C:\runs\ok.json"))
        for message in ("STOP requested — waiting for the current bounded pulse to release.",
                        r"halted: Foreground lost — Run receipt: C:\runs\halt.json",
                        r"View saved: C:\captures\view.png · Nearby units unavailable (sample expired)",
                        r"Route loaded: C:\routes\first.json; last-route snapshot could not be saved: disk full",
                        "Waiting for RIFT: no verified player", "F8 stopped playback after waypoint 1."):
            self.assertEqual(message, summarize_status(message))

    def test_withdrawn_root_controls_get_dark_theme_focus_and_selection_states(self):
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError as exc:
            self.skipTest(str(exc))
        try:
            window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        window.withdraw()
        self.addCleanup(window.destroy)
        style = ttk.Style(window)
        self.assertEqual(PALETTE, apply_theme(window))
        self.assertEqual("clam", style.theme_use())
        self.assertEqual("withdrawn", window.state())
        self.assertEqual(PALETTE["base"], window.cget("background"))
        self.assertEqual(PALETTE["mint"], style.lookup("Primary.TButton", "background"))
        self.assertNotEqual(style.lookup("Primary.TButton", "background", ("disabled",)),
                            style.lookup("Primary.TButton", "background", ("active",)))
        self.assertEqual(PALETTE["mint"], style.lookup("TEntry", "bordercolor", ("focus",)))
        self.assertEqual(PALETTE["ink"], style.lookup("Treeview", "foreground", ("selected",)))
        self.assertEqual(32, int(style.lookup("Treeview", "rowheight")))
        self.assertEqual(PALETTE["gold"], style.lookup("Gold.TLabel", "foreground"))
        self.assertEqual(PALETTE["blue"], style.lookup("Telemetry.TLabel", "foreground"))
        self.assertEqual(PALETTE["inset"], tk.Text(window).cget("background"))
        for name in ("Card.TLabelframe", "Card.TFrame", "Inset.TFrame", "Ghost.TButton", "Danger.TButton",
                     "TNotebook.Tab", "Treeview.Heading", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
            with self.subTest(style=name):
                self.assertTrue(style.layout(name))


if __name__ == "__main__":
    unittest.main()
