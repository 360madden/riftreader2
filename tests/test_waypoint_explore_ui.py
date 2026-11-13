"""Compact exploration controls with withdrawn Tk and caller-validated fake packets."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import tkinter as tk
from tkinter import ttk

from scripts.waypoint_beacon_pose import SOURCE, QUALIFICATION
from scripts.waypoint_explore_ui import ExploreControls, write_feedback
from scripts.waypoint_ui_theme import apply_theme


class ExploreControlsTests(unittest.TestCase):
    def test_windows_display_replace_sharing_violation_is_retried_with_same_packet(self):
        packet = dict(version=1, acquiredMonotonic=12.5)
        with patch("scripts.waypoint_explore_ui.write_json_atomic", side_effect=[PermissionError(), None]) as writer:
            write_feedback("feedback.json", packet)
        self.assertEqual(2, writer.call_count)
        self.assertEqual(writer.call_args_list[0], writer.call_args_list[1])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.cleanup)
        apply_theme(self.root)
        self.parent = ttk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        self.markers = SimpleNamespace(radar_path=self.path / "radar.json", running=Mock(return_value=False))
        self.feed = Mock(side_effect=lambda: setattr(self.markers.running, "return_value", True))
        self.status = tk.StringVar(master=self.root)
        self.document = {"waypoints": [["A", 0, 0], ["B", 1, 0], ["C", 2, 0]]}
        self.selected = 1
        self.target = dict(hostName="AMD-DESKTOP", processId=123, processStartUtcTicks="1234",
                           executablePath=r"C:\RIFT\rift_x64.exe", executableSha256="a" * 64, hwnd=12345)
        self.binding = dict(target=self.target, playerKey="123", sessionId="owned-session")
        self.navigation = Mock()
        self.ui = ExploreControls(self.parent, self.markers, self.feed, self.status,
            get_document=lambda: self.document, get_selected_index=lambda: self.selected,
            get_binding=lambda: self.binding, on_navigation=self.navigation)
        self.base_time = datetime.now(timezone.utc) - timedelta(seconds=.25)

    def cleanup(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def packet(self, sequence, x=0, z=0, *, session="owned-session"):
        return dict(status="fresh", target=deepcopy(self.target), playerKey="123", sessionId=session,
                    source=SOURCE, qualification=QUALIFICATION, sequence=sequence,
                    position=dict(x=x, y=10., z=z), bearing=0., acquiredMonotonic=100. + sequence * .25,
                    sampledAtUtc=(self.base_time + timedelta(seconds=sequence * .25)).isoformat())

    def test_guide_reverse_selected_advances_in_order_without_checkpoint_writes(self):
        self.ui.on_pose(self.packet(1, 4))
        self.ui.direction.set("Reverse")
        self.ui.start_selected.set(True)
        self.ui.start_guidance()
        self.assertEqual([1, 0], self.ui.navigation_state()["order"])
        self.ui.on_pose(self.packet(2, 1))
        self.ui.on_pose(self.packet(3, 1))
        self.assertEqual([1], self.ui.navigation_state()["completedIndices"])
        self.assertEqual(0, self.ui.navigation_state()["activeIndex"])
        self.ui.on_pose(self.packet(3, 1))
        self.assertEqual([1], self.ui.navigation_state()["completedIndices"])
        self.ui.on_pose(self.packet(4, 0))
        self.ui.on_pose(self.packet(5, 0))
        self.assertTrue(self.ui.navigation_state()["complete"])
        self.assertIn("Route complete", self.ui.guide_text.get())
        self.assertEqual(["radar.json"], [p.name for p in self.path.iterdir()])

    def test_route_change_stops_guide_but_does_not_clear_trail(self):
        self.ui.on_pose(self.packet(1))
        self.ui.start_guidance()
        self.ui.start_trail()
        self.document["waypoints"][1][0] = "Renamed"
        self.ui.route_changed()
        self.assertEqual("route-changed", self.ui.navigation_state()["reason"])
        self.assertTrue(self.ui.trail.snapshot()["active"])
        self.assertEqual(1, self.ui.trail.snapshot()["pointCount"])

    def test_no_fresh_pose_or_wrong_binding_refuses_start_and_unavailable_clears_distance(self):
        self.ui.start_guidance()
        self.feed.assert_called_once()
        self.assertEqual("stopped", self.ui.navigation_state()["status"])
        self.ui.on_pose(self.packet(1, 4))
        self.binding["sessionId"] = "different"
        self.ui.start_guidance()
        self.assertIn("session changed", self.status.get())
        self.binding["sessionId"] = "owned-session"
        self.ui.start_guidance()
        self.assertIsNotNone(self.ui.navigation_state()["distance"])
        self.ui.unavailable("stale")
        self.assertIsNone(self.ui.navigation_state()["distance"])
        self.assertEqual("unavailable", self.ui.navigation_state()["status"])
        self.assertIsNone(self.ui.latest_pose)

    def test_trail_segments_clear_guard_and_explicit_save_leave_current_route_untouched(self):
        original = deepcopy(self.document)
        self.ui.on_pose(self.packet(1))
        self.ui.start_trail()
        self.assertEqual("disabled", str(self.ui.clear_trail_button["state"]))
        self.ui.on_pose(self.packet(2, .8))
        self.ui.on_pose(self.packet(3, 1.6))
        self.ui.clear_trail()
        self.assertEqual(3, self.ui.trail.snapshot()["pointCount"])
        self.ui.unavailable("gap")
        self.ui.on_pose(self.packet(4, 2.4))
        self.ui.on_pose(self.packet(5, 3.2))
        self.ui.stop_trail()
        self.assertEqual(2, len(self.ui.segment_dropdown["values"]))
        self.assertEqual(1, self.ui.segment_dropdown.current())
        self.ui.segment_dropdown.current(0)
        output = self.path / "saved-segment.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(output)) as chooser:
            self.ui.save_trail()
        self.assertIs(chooser.call_args.kwargs["parent"], self.root)
        saved = json.loads(output.read_text())
        self.assertEqual([0., 1.6], [row[1] for row in saved["waypoints"]])
        self.assertEqual(10, saved["heights"][0])
        self.assertEqual(self.packet(1)["sampledAtUtc"], saved["pointMeasurements"][0]["observedAtUtc"])
        self.assertEqual(original, self.document)
        self.ui.clear_trail()
        self.assertEqual(0, self.ui.trail.snapshot()["pointCount"])

    def test_stationary_segment_save_reports_refusal_without_opening_chooser(self):
        self.ui.on_pose(self.packet(1))
        self.ui.start_trail()
        self.ui.stop_trail()
        with patch("tkinter.messagebox.showerror") as error, patch("tkinter.filedialog.asksaveasfilename") as chooser:
            self.ui.save_trail()
        error.assert_called_once()
        chooser.assert_not_called()

    def test_fresh_pose_emits_even_without_guide_and_shutdown_hides_radar(self):
        packet = self.packet(1)
        self.ui.on_pose(packet)
        self.navigation.assert_called_once()
        state, segments = self.navigation.call_args.args
        self.assertEqual("stopped", state["status"])
        self.assertEqual([], segments)
        self.ui.enabled.set(True)
        self.ui.unlocked.set(True)
        self.ui.toggle()
        self.ui.start_guidance()
        self.ui.start_trail()
        self.ui.shutdown()
        self.assertEqual("stopped", self.ui.navigation_state()["status"])
        self.assertFalse(self.ui.trail.snapshot()["active"])
        saved = json.loads(self.markers.radar_path.read_text())
        self.assertFalse(saved["enabled"])
        self.assertFalse(saved["unlocked"])

    def test_radar_opacity_debounce_and_all_three_cards_fit_requested_budget(self):
        self.ui.opacity.set(40)
        self.ui.changed()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            self.root.update()
            if json.loads(self.markers.radar_path.read_text())["opacity"] == .4:
                break
            time.sleep(.01)
        self.assertEqual(.4, json.loads(self.markers.radar_path.read_text())["opacity"])
        self.root.update_idletasks()
        self.assertLessEqual(self.parent.winfo_reqwidth(), 904)
        self.assertLessEqual(self.parent.winfo_reqheight(), 184)

    def test_long_unavailable_reason_and_name_keep_compact_cards_and_complete_button_text(self):
        from tkinter import font as tkfont
        self.root.geometry("980x740")
        self.document["waypoints"][0][0] = "Very long waypoint " * 12
        self.ui.on_pose(self.packet(1, 4))
        self.ui.start_guidance()
        reason = "[Errno 2] No such file or directory: C:/work/riftreader2/artifacts/" + "long-owned-pose-path-" * 15
        self.ui.unavailable(reason)
        self.assertNotIn("C:/", self.ui.guide_text.get())
        self.assertNotIn("long-owned", self.ui.trail_text.get())
        self.assertNotIn("unavailable", self.ui.trail_text.get().lower())
        self.assertEqual(reason, self.ui.last_unavailable_reason)
        self.assertEqual(reason, self.ui.guidance.as_dict()["reason"])
        self.assertLessEqual(len(self.ui.guide_text.get().splitlines()[0]), 42)
        self.root.update_idletasks()
        self.assertLessEqual(self.parent.winfo_reqheight(), 184)
        # Withdrawn Tk does not allocate descendants. Check every actual pack
        # row's requested bounds against a conservative minimum-width card
        # budget, rather than accepting misleading 1x1 unmapped coordinates.
        card_inner_budget = 904 // 3 - 8 - 18
        for card in self.parent.winfo_children():
            if isinstance(card, ttk.LabelFrame):
                for row in card.winfo_children():
                    self.assertLessEqual(row.winfo_reqwidth(), card_inner_budget, str(row))
        button = self.ui.clear_trail_button
        spec = ttk.Style(self.root).lookup(button["style"], "font") or "TkDefaultFont"
        text_width = tkfont.Font(root=self.root, font=spec).measure(button["text"])
        self.assertGreaterEqual(button.winfo_reqwidth(), text_width + 20)

    def test_stale_start_refuses_and_every_start_or_enabled_radar_ensures_live_feedback(self):
        self.markers.running.return_value = True
        self.ui.on_pose(self.packet(1))
        self.ui.latest_pose["sampledAtUtc"] = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        self.ui.start_guidance()
        self.assertEqual("stopped", self.ui.navigation_state()["status"])
        self.assertIn("fresh live pose", self.status.get())
        self.assertIsNone(self.ui.latest_pose)
        self.feed.assert_called_once()
        self.ui.on_pose(self.packet(1))
        self.ui.start_trail()
        self.assertTrue(self.ui.trail.snapshot()["active"])
        self.assertEqual(2, self.feed.call_count)
        self.ui.enabled.set(True)
        self.ui.toggle()
        self.assertEqual(3, self.feed.call_count)


if __name__ == "__main__":
    unittest.main()
