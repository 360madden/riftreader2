"""Playback/marker coordination using withdrawn Tk and fake child/readers."""
import json
from datetime import datetime, timezone
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts.waypoint_progress import RouteProgress
from scripts.waypoint_beacon_pose import write_pose
from tests import test_waypoint_recording_window as fixture


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class MarkerPlaybackTests(unittest.TestCase):
    pose = staticmethod(fixture.RecordingWindowTests.pose)
    batch = fixture.RecordingWindowTests.batch
    widgets = fixture.RecordingWindowTests.widgets
    button = fixture.RecordingWindowTests.button
    wait_for = fixture.RecordingWindowTests.wait_for

    def setUp(self):
        self.marker = SimpleNamespace(running=Mock(return_value=True), stop=Mock(), update=Mock(),
                                      stop_requested=False, exit_code=None, pose_path=None)
        self.marker_patch = patch.object(app, "OwnedWaypointMarkers", return_value=self.marker)
        self.marker_patch.start()
        self.addCleanup(self.marker_patch.stop)
        self.companion = {"processId": 456, "processStartUtcTicks": "123456789", "hwnd": 65536}
        self.bind_patch = patch("scripts.physical_waypoint_overlay.bind_companion_window", return_value=self.companion)
        self.bind_companion = self.bind_patch.start()
        self.addCleanup(self.bind_patch.stop)
        self.entered, self.stopped = threading.Event(), threading.Event()
        def playback(adapter, document, stop, emit, **kwargs):
            self.entered.set()
            if stop.wait(3):
                self.stopped.set()
            raise app.Stopped("fake stop")
        self.play_patch = patch("scripts.waypoint_playback.play_route", side_effect=playback)
        self.play_mock = self.play_patch.start()
        self.addCleanup(self.play_patch.stop)
        fixture.RecordingWindowTests.setUp(self)
        self.adapter.pid = 123
        self.adapter.target = {"processId": 123, "processStartUtcTicks": "1234",
                               "executableSha256": "a" * 64, "hwnd": 12345}
        self.adapter.binding["runtimeIdentity"]["processStartUtcTicks"] = "1234"
        self.no_input.side_effect = lambda *_: SimpleNamespace(close=lambda: None)
        self.table = next(w for w in self.widgets() if isinstance(w, fixture.ttk.Treeview)
                          and tuple(w["columns"]) == ("name", "x", "z"))
        self.table.insert("", "end", values=("Start", "0", "0"))
        self.table.insert("", "end", values=("End", "1", "0"))
        self.table.selection_set(self.table.get_children()[0])
        self.window.update()

    def guide_checkbox(self):
        return next(w for w in self.widgets() if isinstance(w, fixture.ttk.Checkbutton)
                    and str(w["text"]) == "Guide selected marker")

    def enable_marker_launch(self):
        self.marker.running.return_value = False
        self.wait_for(lambda: str(self.guide_checkbox()["state"]) != "disabled")
        def started(*args, **kwargs):
            self.marker.running.return_value = True
        self.marker.start = Mock(side_effect=started)

    def test_default_launch_does_not_opt_into_landmark_guidance(self):
        self.enable_marker_launch()
        checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
        self.assertFalse(checkpoint.exists())
        self.button("Show markers").invoke()
        self.marker.start.assert_called_once()
        self.assertEqual({"companion": self.companion}, self.marker.start.call_args.kwargs)
        self.bind_companion.assert_called_once_with(self.window.winfo_id())
        self.assertFalse(checkpoint.exists())

    def test_guide_launch_is_one_based_and_guide_remains_editable(self):
        self.enable_marker_launch()
        self.guide_checkbox().invoke()
        items = self.table.get_children()
        self.table.selection_set(items[1])
        self.button("Show markers").invoke()
        self.assertEqual({"landmark_number": 2, "companion": self.companion}, self.marker.start.call_args.kwargs)
        self.assertEqual(["Start", "End"],
                         [row[0] for row in self.marker.start.call_args.args[0]["waypoints"]])
        self.table.selection_set(items[0])
        self.wait_for(lambda: str(self.guide_checkbox()["state"]) != "disabled")
        self.marker.start.assert_called_once()
        self.assertEqual(2, self.marker.start.call_args.kwargs["landmark_number"])
        self.assertFalse((self.root_path / "artifacts" / "waypoint-current-progress.json").exists())

    def test_guide_requires_exactly_one_selection_before_launch(self):
        self.enable_marker_launch()
        self.guide_checkbox().invoke()
        for selected in ([], list(self.table.get_children())):
            with self.subTest(selected=selected):
                self.table.selection_set(selected)
                self.button("Show markers").invoke()
                self.marker.start.assert_not_called()
                labels = [str(self.window.getvar(w["textvariable"])) for w in self.widgets()
                          if isinstance(w, fixture.ttk.Label) and w["textvariable"]]
                self.assertTrue(any("Select one saved marker" in text for text in labels), labels)
        self.assertFalse((self.root_path / "artifacts" / "waypoint-current-progress.json").exists())

    def cleanup_windows(self):
        self.no_input.reset_mock()
        fixture.RecordingWindowTests.cleanup_windows(self)

    def supply_marker_pose(self):
        self.adapter.target.update(hostName="AMD-DESKTOP", executablePath=r"C:\RIFT\rift_x64.exe")
        self.marker.pose_path = self.root_path / "artifacts" / "owned-beacon-pose.json"
        write_pose(self.marker.pose_path, dict(target=self.adapter.target, acquiredMonotonic=time.monotonic(),
            playerPose=dict(playerKey=self.adapter.binding["runtimeIdentity"]["unitKey"],
                            position=dict(x=0, y=0, z=0), bearing=0,
                            sampledAtUtc=datetime.now(timezone.utc).isoformat())), 1)
        self.wait_for(lambda: str(self.button("Play Forward")["state"]) != "disabled")

    def test_play_keeps_markers_and_stop_latches_before_signal_failure(self):
        self.supply_marker_pose()
        def fail_stop():
            self.assertTrue(self.stopped.wait(1), "movement STOP must latch before marker signal")
            raise OSError("signal unavailable")
        self.marker.stop.side_effect = fail_stop
        self.button("Play Forward").invoke()
        self.assertTrue(self.entered.wait(2))
        self.marker.stop.assert_not_called()
        self.button("STOP").invoke()
        self.assertTrue(self.stopped.wait(1))
        self.marker.stop.assert_called_once()
        self.assertTrue(self.marker.running())
        self.wait_for(lambda: str(self.button("Refresh")["state"]) != "disabled")

    def test_go_still_requests_marker_stop_and_waits(self):
        self.button("Go Selected").invoke()
        self.marker.stop.assert_called_once()
        self.assertFalse(self.entered.is_set())

    def test_resume_keeps_marker_child_until_stop(self):
        checkpoint = self.root_path / "artifacts" / "waypoint-current-progress.json"
        progress = RouteProgress({"waypoints": [["Start", 0, 0], ["End", 1, 0]]},
                                 "forward", self.adapter.binding["runtimeIdentity"])
        progress.begin({"x": 0, "y": 0, "z": 0})
        progress.confirm_arrival(0, progress.ordered_points[0])
        progress.save(checkpoint)
        # A running child must supply its own fresh display packet. Missing
        # packets intentionally clear the radar and disable pose-dependent UI.
        self.adapter.target.update(hostName="AMD-DESKTOP", executablePath=r"C:\RIFT\rift_x64.exe")
        self.marker.pose_path = self.root_path / "artifacts" / "owned-beacon-pose.json"
        write_pose(self.marker.pose_path, dict(target=self.adapter.target, acquiredMonotonic=time.monotonic(),
            playerPose=dict(playerKey=self.adapter.binding["runtimeIdentity"]["unitKey"],
                            position=dict(x=0, y=0, z=0), bearing=0,
                            sampledAtUtc=datetime.now(timezone.utc).isoformat())), 1)
        self.button("Refresh").invoke()
        self.wait_for(lambda: str(self.button("Resume")["state"]) != "disabled")
        self.button("Resume").invoke()
        self.assertTrue(self.entered.wait(2))
        self.assertTrue(self.play_mock.call_args.kwargs["resume"])
        self.marker.stop.assert_not_called()
        self.button("STOP").invoke()
        self.assertTrue(self.stopped.wait(1))
        self.marker.stop.assert_called_once()
        self.wait_for(lambda: str(self.button("Refresh")["state"]) != "disabled")

    def test_f8_stop_event_also_requests_marker_shutdown(self):
        self.supply_marker_pose()
        listener = {}
        def foreground(window, stop, events):
            listener.update(stop=stop, events=events)
            return SimpleNamespace(close=lambda: None)
        self.no_input.side_effect = foreground
        self.button("Play Forward").invoke()
        self.assertTrue(self.entered.wait(2))
        listener["stop"].set()
        listener["events"].put({"status": "stopping", "reason": "F8 STOP requested"})
        self.wait_for(lambda: self.marker.stop.called)
        self.assertTrue(self.stopped.wait(1))
        self.wait_for(lambda: str(self.button("Refresh")["state"]) != "disabled")

    def test_marker_feed_suspends_idle_pose_even_with_helper_focus_until_markers_end(self):
        pose = self.pose(0)
        acquired = pose.acquired
        read = Mock(return_value=pose)
        self.adapter.read = read
        def displayed_pose():
            return next(str(self.window.getvar(w["textvariable"])) for w in self.widgets()
                        if isinstance(w, fixture.ttk.Label) and w["textvariable"]
                        and str(self.window.getvar(w["textvariable"])).startswith(
                            ("X ", "Position unavailable", "Position is loading")))
        previous = displayed_pose()
        with patch.object(self.window, "focus_displayof", return_value=self.window):
            deadline = time.monotonic() + 2.2
            while time.monotonic() < deadline:
                self.window.update()
                time.sleep(.01)
            self.assertEqual(0, read.call_count)
            self.assertIn("Position unavailable \u2014", displayed_pose())
            self.assertNotIn("updated ", displayed_pose())
            self.assertEqual(acquired, pose.acquired)
            self.marker.running.return_value = False
            self.wait_for(lambda: read.call_count == 1)
        self.assertEqual(acquired, pose.acquired)
        self.assertFalse(self.marker.running())


if __name__ == "__main__":
    unittest.main()
