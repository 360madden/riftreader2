"""Offline Tk admission checks for movement versus the owned pose reader."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts import waypoint_cli_protocol as protocol
from scripts.waypoint_progress import RouteProgress
from tests import test_waypoint_header_window as fixture

tk, ttk = fixture.tk, fixture.ttk


class FakeMarkers:
    """A reader that acknowledges STOP but exits only when the test allows it."""

    def __init__(self, root):
        self.active = True
        self.stop_requested = False
        self.stop_calls = 0
        self.exit_code = None
        self.identity = None
        self.output = None
        self.pose_path = None
        self.status_path = None
        self.route_updates_path = None
        self.exploration_path = None
        self.appearance_path = root / "appearance.json"
        self.radar_path = root / "radar.json"

    def running(self):
        return self.active

    def stop(self):
        self.stop_calls += 1
        self.stop_requested = True


@unittest.skipIf(tk is None, "Tk unavailable")
class OverlayMovementAdmissionTests(unittest.TestCase):
    setUp = fixture.HeaderWindowTests.setUp
    cleanup_gui = fixture.HeaderWindowTests.cleanup_gui
    widgets = fixture.HeaderWindowTests.widgets
    button = fixture.HeaderWindowTests.button
    route_table = fixture.HeaderWindowTests.route_table
    launch = fixture.HeaderWindowTests.launch
    read_status = fixture.HeaderWindowTests.read_status

    def prepare(self, *, checkpoint=False):
        self.markers = FakeMarkers(self.path)
        self.stack.enter_context(patch.object(app, "OwnedWaypointMarkers",
                                              return_value=self.markers))
        self.runner = self.stack.enter_context(patch.object(app, "run_route"))
        document = {"waypoints": [["Start", 0, 0], ["End", 4, 0]],
                    "heights": [10, 10]}
        route = self.path / "route.json"
        route.write_text(json.dumps(document), encoding="utf-8")
        if checkpoint:
            progress = RouteProgress(document, "forward", fixture.fixture.TEST_IDENTITY)
            progress.begin({"x": 0, "y": 10, "z": 0})
            progress.save(self.path / "artifacts" / "waypoint-current-progress.json")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(read=Mock(return_value=pose), pid=123)
        self.launch(adapter, route)
        return document

    def test_gui_play_and_resume_only_request_reader_shutdown(self):
        self.prepare(checkpoint=True)
        window = self.roots[0]
        baseline_threads = len(self.threads)

        # The reader makes movement widgets visually unavailable. Exercise the
        # callbacks directly to prove their second, race-closing admission gate.
        for label in ("Play Forward", "Resume"):
            button = self.button(label)
            window.tk.call(str(button["command"]))
        window.update()

        self.assertEqual(2, self.markers.stop_calls)
        self.assertTrue(self.markers.stop_requested)
        self.runner.assert_not_called()
        self.assertEqual(baseline_threads, len(self.threads))
        self.assertFalse(self.read_status()["app"]["busy"])
        self.markers.active = False

    def test_cli_map_move_stays_deferred_until_reader_process_exits(self):
        self.prepare()
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(
            registered=False, close=lambda: None)))
        moved = Mock(return_value={"status": "arrived", "position": {"x": 1, "y": 10, "z": 0},
                                  "bearing": 0, "distance": 0})
        self.stack.enter_context(patch.object(app, "run_map_move", moved))

        rid = "map-reader-barrier"
        (self.server.path / "requests" / (rid + ".json")).write_text("{}", encoding="utf-8")
        pending = self.dispatch("move.pick",
            {"execute": True, "canvas_x": 50, "canvas_y": 50}, rid)
        self.assertIsInstance(pending, protocol.Deferred)
        self.assertEqual(1, self.markers.stop_calls)
        for _ in range(3):
            self.roots[0].update()
        moved.assert_not_called()
        self.assertFalse(self.read_status()["app"]["busy"])

        self.markers.active = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not moved.called:
            self.roots[0].update()
            time.sleep(.01)
        self.assertTrue(moved.called)


if __name__ == "__main__":
    unittest.main()
