import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from scripts.waypoint_activity_ui import ActivityControls, MAX_DISPLAY_CHARS
from scripts.waypoint_ui_theme import apply_theme
from tests.tk_support import withdrawn_root


class FakeDiagnostics:
    def __init__(self, root: Path):
        self.root = root
        self.entries = []
        self.revision = 0
        self.available = True
        self.event_calls = 0

    def add(self, level="INFO", message="Activity", **fields):
        self.revision += 1
        self.entries.append({
            "eventId": self.revision,
            "timestamp": "2026-11-13T14:15:16.000Z",
            "level": level,
            "message": message,
            **fields,
        })

    def events(self, *, limit=100, level="all", search=""):
        self.event_calls += 1
        if len(search) > 200:
            raise ValueError("search too long")
        threshold = {"warning": {"WARNING", "ERROR"}, "error": {"ERROR"}}.get(level)
        matches = []
        for entry in reversed(self.entries):
            if threshold and entry["level"] not in threshold:
                continue
            if search and search.casefold() not in str(entry).casefold():
                continue
            matches.append(dict(entry))
        return {
            "entries": matches[:limit],
            "shownCount": min(limit, len(matches)),
            "matchedCount": len(matches),
            "totalBuffered": len(self.entries),
            "revision": self.revision,
            "available": self.available,
        }

    def status(self):
        return {
            "available": self.available,
            "eventRevision": self.revision,
            "retainedEvents": len(self.entries),
            "logFile": str(self.root / "activity.log"),
            "error": None,
        }


class ActivityControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = withdrawn_root(tk.Tk)
        apply_theme(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill="both", expand=True)
        self.diagnostics = FakeDiagnostics(self.path)
        self.controls = ActivityControls(
            self.frame, self.diagnostics, open_logs=lambda: None, copy_diagnostics=lambda: None
        )

    def tearDown(self):
        self.frame.destroy()
        self.temporary.cleanup()

    def text(self):
        return self.controls.text.get("1.0", "end-1c")

    def test_formats_filters_activity_status_and_bounds_display(self):
        self.diagnostics.add(status="Ready to play")
        self.diagnostics.add("WARNING", "Route paused", reason="foreground lost", requestId="r-1")
        self.diagnostics.add("ERROR", "Capture failed", exceptionType="RuntimeError", exceptionMessage="capture marker",
                             command="view.save", traceback="x" * 100_000)
        self.controls.show_details.set(True)
        self.controls.refresh(force=True)
        rendered = self.text()
        self.assertIn("Ready to play", rendered)
        self.assertIn("command: view.save", rendered)
        self.assertIn("exceptionMessage: capture marker", rendered)
        self.assertIn("reason: foreground lost", rendered)
        self.assertIn("details truncated in Activity", rendered)
        self.assertIn("Traceback:\n", rendered)
        self.assertNotIn("Traceback:\\n", rendered)
        self.assertLessEqual(len(rendered), MAX_DISPLAY_CHARS)

        self.controls.severity.set("Errors")
        self.controls.refresh(force=True)
        self.assertIn("Capture failed", self.text())
        self.assertNotIn("Route paused", self.text())
        self.controls.search.set("no such event")
        self.controls.refresh(force=True)
        self.assertIn("No activity matches", self.text())

    def test_unchanged_revision_skips_event_copy_and_long_search_is_bounded(self):
        self.diagnostics.add(message="First")
        self.controls.refresh(force=True)
        calls = self.diagnostics.event_calls
        self.controls.refresh()
        self.assertEqual(self.diagnostics.event_calls, calls)

        self.controls.search.set("x" * 500)
        self.controls.refresh(force=True)
        self.assertEqual(self.diagnostics.event_calls, calls + 1)
        self.assertIn("No activity matches", self.text())

    def test_clear_and_show_history_leave_the_real_log_unchanged(self):
        from scripts.waypoint_diagnostics import Diagnostics
        diagnostics = Diagnostics(self.path)
        self.addCleanup(diagnostics.close)
        diagnostics.warning("saved marker")
        self.controls.diagnostics = diagnostics
        self.controls.refresh(force=True)
        saved = diagnostics.log_path.read_bytes()
        self.controls.clear_view()
        self.assertEqual(saved, diagnostics.log_path.read_bytes())
        self.assertNotIn("saved marker", self.text())
        diagnostics.warning("new marker")
        self.controls.refresh()
        self.assertIn("new marker", self.text())
        self.assertNotIn("saved marker", self.text())
        self.controls._toggle_clear()
        self.assertIn("saved marker", self.text())
        self.assertEqual(3, len(diagnostics.events()["entries"]))

    def test_follow_off_freezes_text_and_reports_unseen_then_resume(self):
        self.diagnostics.add(message="First")
        self.controls.refresh(force=True)
        original = self.text()
        self.controls.text.configure(state="normal")
        self.controls.text.tag_add("sel", "1.0", "1.5")
        self.controls.text.configure(state="disabled")
        self.controls.follow.set(False)
        self.diagnostics.add(message="Second")
        self.controls.refresh()
        self.assertEqual(self.text(), original)
        self.assertEqual(
            (self.controls.text.index("sel.first"), self.controls.text.index("sel.last")),
            ("1.0", "1.5"),
        )
        self.assertEqual(self.controls.view_state()["unseenCount"], 1)
        self.assertIn("1 new", self.controls.footer.get())

        self.controls.follow.set(True)
        self.controls._follow_changed()
        self.assertIn("Second", self.text())
        self.assertEqual(self.controls.view_state()["unseenCount"], 0)

    def test_clear_is_view_only_and_history_can_be_restored(self):
        self.diagnostics.add(message="Before clear")
        self.controls.refresh(force=True)
        before_files = list(self.path.rglob("*"))
        before_entries = list(self.diagnostics.entries)
        self.controls.clear_view()
        self.assertIn("Saved logs were not changed", self.text())
        self.assertEqual(self.diagnostics.entries, before_entries)
        self.assertEqual(list(self.path.rglob("*")), before_files)

        self.diagnostics.add(message="After clear")
        self.controls.refresh()
        self.assertIn("After clear", self.text())
        self.assertNotIn("Before clear", self.text())
        self.controls._toggle_clear()
        self.assertIn("Before clear", self.text())

    def test_compact_toolbar_has_single_readonly_text_and_fits(self):
        self.frame.configure(width=980, height=220)
        self.frame.pack_propagate(False)
        self.root.update_idletasks()
        texts = []
        stack = [self.frame]
        while stack:
            widget = stack.pop()
            if widget.winfo_class() == "Text":
                texts.append(widget)
            stack.extend(widget.winfo_children())
        self.assertEqual(texts, [self.controls.text])
        self.assertEqual(self.controls.text.cget("state"), "disabled")
        self.assertLessEqual(self.frame.winfo_reqwidth(), 980)

    def test_geometry_scroll_callback_does_not_pause_follow(self):
        self.diagnostics.add(message="One")
        self.controls.refresh(force=True)
        self.assertTrue(self.controls.follow.get())
        self.controls._scroll_changed(self.controls.scrollbar, "0.0", "0.5")
        self.assertTrue(self.controls.follow.get())


if __name__ == "__main__":
    unittest.main()
