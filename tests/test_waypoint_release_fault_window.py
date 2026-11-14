"""GUI release-fault fencing with no native reads, focus, or game input."""
from pathlib import Path
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests import test_waypoint_playback_window_state as fixture


class FakeServer:
    def __init__(self, root):
        self.session_id = "release-fault-test"
        self.path = root / "server"
        self.path.mkdir()
        self.dispatch = None
        self.completed = {}

    def poll(self, dispatch):
        self.dispatch = dispatch

    def complete(self, request_id, response):
        self.completed[request_id] = response

    def close(self):
        pass


@unittest.skipIf(fixture.tk is None, "Tk unavailable")
class ReleaseFaultWindowTests(unittest.TestCase):
    setUp = fixture.PlaybackWindowStateTests.setUp
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    launch = fixture.PlaybackWindowStateTests.launch

    def settle(self, predicate=lambda: True):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.root.update()
            if all(not thread.is_alive() for thread in self.threads) and predicate():
                return
            time.sleep(.01)
        self.fail("release-fault window did not settle")

    def status(self, request_id="status"):
        response = self.server.dispatch("status", {}, request_id)
        self.assertIsInstance(response, dict)
        self.assertTrue(response["ok"])
        return response["data"]

    def test_fault_blocks_movement_stop_retries_release_and_only_new_run_unlatches(self):
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Start", 0, 0], ["End", 0, 2]],
                                     "heights": [10, 10]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(0, 10, 0), 0, time.monotonic(), "fake")
        adapter = SimpleNamespace(read=Mock(return_value=pose), pid=123,
            _continuous_input_release_fault=True,
            _continuous_move_recovery={"status": "halted", "releaseSucceeded": False})
        self.server = FakeServer(self.path)
        self.stack.enter_context(patch("scripts.waypoint_cli_protocol.LocalSessionServer",
                                       return_value=self.server))
        self.launch(adapter, route)
        self.root = self.roots[0]

        # A new movement request is refused before foreground/input setup while
        # the sticky release fault is unresolved.
        with patch("scripts.continuous_move.run_continuous_route") as runner:
            self.button("Play Forward").invoke()
            self.root.update()
            runner.assert_not_called()
        self.assertTrue(self.status()["controls"]["inputReleaseFault"])
        self.assertTrue(self.status()["controls"]["stopLatched"] is False)

        recovered = {"status": "halted", "releaseSucceeded": True,
                     "keys": [{"key": key, "verified": True} for key in ("w", "a", "d")]}

        def retry(source):
            self.assertIs(source, adapter)
            source._continuous_input_release_fault = False
            source._continuous_move_recovery = recovered
            return recovered

        with patch("scripts.continuous_move.retry_release", side_effect=retry) as release:
            self.button("STOP").invoke()
            self.settle(lambda: release.called and not self.status("during-stop")["app"]["busy"])
        release.assert_called_once_with(adapter)
        controls = self.status("after-release")["controls"]
        self.assertTrue(controls["stopLatched"])
        self.assertFalse(controls["inputReleaseFault"])
        self.assertEqual("verified-recovery", controls["keyReleaseEvidence"])
        self.assertEqual(recovered, controls["inputRecovery"])

        # Read-only refresh must not silently Resume or clear the STOP latch.
        self.button("Refresh").invoke()
        self.settle(lambda: not self.status("refresh-settled")["app"]["busy"])
        self.assertTrue(self.status("after-refresh")["controls"]["stopLatched"])

        observed = {}

        def run_route(_adapter, points, stop, emit, *, entry_check, **_):
            observed["stopAtRun"] = stop.is_set()
            entry_check(app.Position(0, 10, 0))
            legs = []
            for name, x, z in points:
                result = {"status": "arrived", "name": name,
                          "goal": {"x": x, "y": 10, "z": z},
                          "position": {"x": x, "y": 10, "z": z},
                          "bearing": 0, "distance": 0, "pulses": 0,
                          "totalHoldMs": 0, "acquired": time.monotonic()}
                emit(result)
                legs.append(result)
            return legs

        foreground = SimpleNamespace(registered=False, close=lambda: None)
        with patch.object(app, "ForegroundStop", return_value=foreground), patch.object(
                app, "run_route", side_effect=run_route), patch(
                "scripts.continuous_move.run_continuous_route", side_effect=run_route):
            self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]),
                                self.status("before-new-run"))
            self.button("Play Forward").invoke()
            self.settle()
        self.assertFalse(observed["stopAtRun"])
        self.assertFalse(self.status("after-new-run")["controls"]["stopLatched"])


if __name__ == "__main__":
    unittest.main()
