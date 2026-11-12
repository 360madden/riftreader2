"""Normal close protects route edits after fake workers finish STOP cleanup."""
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests import test_waypoint_unsaved_load as load
from tests import test_waypoint_playback_window_state as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class UnsavedCloseTests(unittest.TestCase):
    setUp = load.UnsavedLoadTests.setUp
    cleanup_gui = load.UnsavedLoadTests.cleanup_gui
    widgets = load.UnsavedLoadTests.widgets
    button = load.UnsavedLoadTests.button
    launch = load.UnsavedLoadTests.launch
    prepare = load.UnsavedLoadTests.prepare
    enter = load.UnsavedLoadTests.enter
    route_label = load.UnsavedLoadTests.route_label
    dirty_route = load.UnsavedLoadTests.dirty_route
    values = load.UnsavedLoadTests.values
    snapshot = load.UnsavedLoadTests.snapshot

    def close(self):
        self.root.tk.call(self.root.protocol("WM_DELETE_WINDOW"))

    def destroyed(self):
        try:
            return not self.root.winfo_exists()
        except fixture.tk.TclError:
            return True

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("fake cleanup did not settle")
            self.root.update()
            time.sleep(.01)

    def test_idle_cancel_preserves_edits_files_history_and_resets_closing(self):
        self.dirty_route()
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertEqual(before, self.snapshot())
        self.assertIs(ask.call_args.kwargs["parent"], self.root)
        self.button("Undo").invoke()
        self.assertEqual("First", self.values()[0][0])
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as second:
            self.close()
        second.assert_called_once()

    def test_idle_save_writes_current_route_then_destroys(self):
        self.dirty_route()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("tkinter.filedialog.asksaveasfilename") as chooser:
            self.close()
        chooser.assert_not_called()
        self.assertTrue(self.destroyed())
        self.assertEqual("Named beacon", json.loads(self.source.read_text())["waypoints"][0][0])

    def test_idle_discard_destroys_without_saving(self):
        self.dirty_route()
        before = self.source.read_bytes()
        with patch("tkinter.messagebox.askyesnocancel", return_value=False):
            self.close()
        self.assertTrue(self.destroyed())
        self.assertEqual(before, self.source.read_bytes())

    def test_failed_save_keeps_data_and_window_open(self):
        self.dirty_route()
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("scripts.waypoint_progress.os.replace", side_effect=OSError("disk denied")), \
             patch("tkinter.messagebox.showerror") as error:
            self.close()
        error.assert_called_once()
        self.assertTrue(self.root.winfo_exists())
        self.assertEqual(before, self.snapshot())

    def test_new_route_cancelled_save_chooser_keeps_data(self):
        with patch.object(fixture.app, "PhysicalAdapter", side_effect=ValueError("offline")):
            self.launch()
        self.root = self.roots[0]
        self.table = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Treeview))
        self.entries = [w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Entry)
                        and not isinstance(w, fixture.ttk.Combobox)]
        self.enter("Beacon", "1", "2")
        self.button("Add X / Z").invoke()
        before = self.values()
        with patch("tkinter.messagebox.askyesnocancel", return_value=True), \
             patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            self.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertEqual(before, self.values())
        self.assertNotEqual("disabled", str(self.button("Undo")["state"]))

    def test_dialog_reentry_does_not_prompt_twice(self):
        self.dirty_route()
        def nested_close(*args, **kwargs):
            self.close()
            self.root.update()
            return None
        with patch("tkinter.messagebox.askyesnocancel", side_effect=nested_close) as ask:
            self.close()
        ask.assert_called_once()
        self.assertTrue(self.root.winfo_exists())

    def test_close_waits_for_owned_marker_exit_before_prompt(self):
        marker = SimpleNamespace(running=Mock(return_value=False), stop=Mock(),
                                 stop_requested=False, exit_code=None)
        with patch.object(fixture.app, "OwnedWaypointMarkers", return_value=marker):
            self.dirty_route()
        marker.running.return_value = True
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.close()
            self.assertTrue(marker.stop.called)
            ask.assert_not_called()
            self.assertEqual("disabled", str(self.button("Clear")["state"]))
            self.root.update()
            self.assertEqual("disabled", str(self.button("Clear")["state"]))
            marker.running.return_value = False
            self.wait_for(lambda: ask.called)
            ask.assert_called_once()
        self.assertTrue(self.root.winfo_exists())

    def test_marker_stop_failure_restores_readonly_and_unavailable_view_states(self):
        marker = SimpleNamespace(running=Mock(return_value=False), stop=Mock(side_effect=OSError("blocked")),
                                 stop_requested=False, exit_code=None)
        with patch.object(fixture.app, "OwnedWaypointMarkers", return_value=marker):
            self.dirty_route()
        marker.running.return_value = True
        before = self.snapshot()
        with patch("tkinter.messagebox.askyesnocancel") as ask:
            self.close()
        ask.assert_not_called()
        dropdown = next(w for w in self.widgets(self.root) if isinstance(w, fixture.ttk.Combobox))
        self.assertEqual("readonly", str(dropdown["state"]))
        self.assertEqual("disabled", str(self.button("Open view")["state"]))
        self.assertEqual("disabled", str(self.button("Open 3D view")["state"]))
        self.assertNotEqual("disabled", str(self.button("Clear")["state"]))
        self.assertEqual(before, self.snapshot())

    def test_close_waits_for_read_worker_before_prompt(self):
        reading, release = threading.Event(), threading.Event()
        block = [False]
        self.addCleanup(release.set)
        def idle_read(adapter, *args, **kwargs):
            if block[0]:
                reading.set()
                release.wait(2)
            return adapter, adapter.read(), False
        with patch("scripts.waypoint_connection.idle_read", side_effect=idle_read):
            self.dirty_route()
        block[0] = True
        with patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.button("Refresh").invoke()
            self.assertTrue(reading.wait(1))
            self.close()
            ask.assert_not_called()
            release.set()
            self.wait_for(lambda: ask.called)
            ask.assert_called_once()
        self.assertTrue(self.root.winfo_exists())

    def test_busy_close_stops_then_waits_for_foreground_release_before_prompt(self):
        entered, released, stopped = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(released.set)
        foreground_closed = Mock()
        marker = SimpleNamespace(running=Mock(return_value=False), stop=Mock(),
                                 stop_requested=False, exit_code=None)
        def play(adapter, document, stop, emit, **kwargs):
            entered.set()
            if stop.wait(2):
                stopped.set()
            released.wait(2)
            raise fixture.app.Stopped("fake stop")
        with patch.object(fixture.app, "ForegroundStop", return_value=SimpleNamespace(close=foreground_closed)), \
             patch("scripts.waypoint_playback.play_route", side_effect=play) as playback, \
             patch.object(fixture.app, "verify_stopped_pose", return_value={"status": "unavailable", "reason": "fake"}), \
             patch.object(fixture.app, "OwnedWaypointMarkers", return_value=marker), \
             patch("tkinter.messagebox.askyesnocancel", return_value=None) as ask:
            self.dirty_route()
            # prepare installs a no-input sentinel; replace it only for this fake trip.
            self.stack.enter_context(patch.object(fixture.app, "ForegroundStop",
                                                 return_value=SimpleNamespace(close=foreground_closed)))
            self.button("Play Forward").invoke()
            self.assertTrue(entered.wait(1))
            marker.running.return_value = True
            self.close()
            self.assertTrue(stopped.wait(1))
            ask.assert_not_called()
            foreground_closed.assert_not_called()
            self.close()
            released.set()
            self.wait_for(lambda: foreground_closed.called)
            ask.assert_not_called()
            self.assertEqual("disabled", str(self.button("Clear")["state"]))
            marker.running.return_value = False
            self.wait_for(lambda: ask.called)
            foreground_closed.assert_called_once()
            ask.assert_called_once()
            self.assertTrue(self.root.winfo_exists())
            self.assertNotEqual("disabled", str(self.button("Undo")["state"]))
            playback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
