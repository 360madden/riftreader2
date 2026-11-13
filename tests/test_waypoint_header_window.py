"""Real withdrawn-Tk header callbacks with fake poses and isolated CLI files."""
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from scripts import waypoint_cli_protocol as protocol
from tests import test_waypoint_playback_window_state as fixture

tk, ttk = fixture.tk, fixture.ttk


@unittest.skipIf(tk is None, "Tk unavailable")
class HeaderWindowTests(unittest.TestCase):
    # Reuse the established no-input window fixture without inheriting its tests.
    cleanup_gui = fixture.PlaybackWindowStateTests.cleanup_gui
    widgets = fixture.PlaybackWindowStateTests.widgets
    button = fixture.PlaybackWindowStateTests.button
    route_table = fixture.PlaybackWindowStateTests.route_table
    launch = fixture.PlaybackWindowStateTests.launch

    def setUp(self):
        fixture.PlaybackWindowStateTests.setUp(self)
        owner = self
        class IsolatedServer(protocol.LocalSessionServer):
            def __init__(self, **kwargs):
                super().__init__(root=owner.path / "helpers", **kwargs)
                owner.server = self

            def poll(self, dispatch):
                # Capture the real GUI dispatcher, never inspect a running helper.
                owner.dispatch = dispatch
                return super().poll(dispatch)

        self.stack.enter_context(patch.object(protocol, "LocalSessionServer", IsolatedServer))

    def read_status(self):
        result = self.dispatch("status", {}, "header-status")
        self.assertTrue(result["ok"], result)
        return result["data"]

    def labels(self):
        result = []
        for widget in self.widgets(self.roots[0]):
            if isinstance(widget, ttk.Label):
                variable = str(widget["textvariable"])
                result.append(str(widget.getvar(variable)) if variable else str(widget["text"]))
        return result

    def pose_toggle(self):
        return next(w for w in self.widgets(self.roots[0])
                    if isinstance(w, ttk.Checkbutton) and str(w["text"]).startswith("Live pose"))

    def launch_pose(self, *, age=0):
        self.reader = Mock(return_value=app.Snapshot(app.Position(1.234567, 2.345678, 3.456789),
                           17.1234, time.monotonic() - age, "fake-native"))
        self.launch(SimpleNamespace(read=self.reader, pid=123))

    def test_old_acquisition_stays_cached_in_header_and_cli(self):
        self.launch_pose(age=10)
        pose = self.read_status()["pose"]
        self.assertEqual("unavailable", pose["status"])
        self.assertEqual("cached", pose["sampleStatus"])
        self.assertGreaterEqual(pose["ageSeconds"], 10)
        self.assertTrue(any("Cached" in text for text in self.labels()), self.labels())
        self.assertTrue(any("1.235" in text and "3.457" in text for text in self.labels()))

    def test_pause_marks_sample_cached_without_another_read(self):
        self.launch_pose()
        before = self.reader.call_count
        self.pose_toggle().invoke()
        self.roots[0].update()
        pose = self.read_status()["pose"]
        self.assertFalse(pose["liveEnabled"])
        self.assertEqual("cached", pose["sampleStatus"])
        self.assertTrue(any("paused" in text.casefold() for text in self.labels()), self.labels())
        self.assertEqual(before, self.reader.call_count)

    def test_idle_stop_latches_without_claiming_release_or_stationary_evidence(self):
        self.launch_pose()
        before = self.reader.call_count
        self.button("STOP").invoke()
        self.roots[0].update()
        controls = self.read_status()["controls"]
        self.assertTrue(controls["stopLatched"])
        self.assertFalse(controls["ownedActionActive"])
        self.assertFalse(controls["hadOwnedAction"])
        self.assertIn("not", str(controls["keyReleaseEvidence"]).casefold())
        self.assertIn("not", str(controls["stationaryEvidence"]).casefold())
        self.assertEqual(before, self.reader.call_count)
        self.assertNotEqual("disabled", str(self.button("Refresh")["state"]))
        self.button("Refresh").invoke()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            if (all(not worker.is_alive() for worker in self.threads)
                    and str(self.button("Refresh")["state"]) != "disabled"):
                break
            time.sleep(.01)
        self.assertEqual(before + 1, self.reader.call_count)
        self.assertFalse(self.read_status()["controls"]["ownedActionActive"])

    def test_idle_header_does_not_advertise_active_global_f8(self):
        self.launch_pose()
        controls = self.read_status()["controls"]
        self.assertEqual("inactive", controls["f8"])
        self.assertTrue(any("F8 inactive" in text for text in self.labels()), self.labels())

    def test_details_opens_activity_without_reading_pose(self):
        self.launch_pose()
        before = self.reader.call_count
        self.button("Details").invoke()
        self.roots[0].update()
        notebook = next(w for w in self.widgets(self.roots[0]) if isinstance(w, ttk.Notebook))
        self.assertEqual("Activity", notebook.tab(notebook.select(), "text"))
        self.assertEqual(before, self.reader.call_count)

    def test_pose_api_changes_live_state_and_rejects_invalid_values_without_mutation(self):
        self.launch_pose()
        before = self.reader.call_count
        for enabled, argument in ((False, "off"), (True, "on")):
            result = self.dispatch("pose.set", {"live": argument}, "pose-valid")
            self.assertTrue(result["ok"], result)
            self.assertIs(enabled, result["data"]["liveEnabled"])
            for invalid in (True, False, None, 1, [], {}, "yes", "ON"):
                with self.subTest(enabled=enabled, invalid=invalid):
                    rejected = self.dispatch("pose.set", {"live": invalid}, "pose-invalid")
                    self.assertFalse(rejected["ok"], rejected)
                    self.assertEqual("invalid-live-pose", rejected["error"]["code"])
                    self.assertIs(enabled, self.read_status()["pose"]["liveEnabled"])
        self.assertEqual(before, self.reader.call_count)

    def test_unavailable_f8_and_owned_stop_remain_distinct_from_stationary_evidence(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        listeners = []
        class FakeListener:
            registered = False
            def __init__(self, window, stop, events):
                self.closed = False
                listeners.append(self)
            def close(self):
                self.closed = True

        def fake_facing(adapter, stop, emit, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test did not release fake facing worker")
            self.assertTrue(stop.is_set())
            raise app.Stopped("Fake bounded operation stopped")

        self.stack.enter_context(patch.object(app, "ForegroundStop", FakeListener))
        self.stack.enter_context(patch.object(app, "run_facing", side_effect=fake_facing))
        verification = {"status": "pass", "samples": [
            {"position": {"x": 1., "y": 2., "z": 3.}, "bearing": 17.}], "xyzDrift": 0.}
        verify = self.stack.enter_context(patch.object(app, "verify_stopped_pose", return_value=verification))
        route = self.path / "route.json"
        route.write_text(json.dumps({"waypoints": [["Target", 4, 3]]}), encoding="utf-8")
        pose = app.Snapshot(app.Position(1, 2, 3), 17, time.monotonic(), "fake")
        self.launch(SimpleNamespace(read=Mock(return_value=pose), pid=123), route)
        table = self.route_table()
        table.selection_set(table.get_children()[0])
        self.roots[0].update()
        self.button("Face Selected").invoke()
        self.assertTrue(entered.wait(2))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            self.roots[0].update()
            if any("F8 unavailable" in text for text in self.labels()):
                break
            time.sleep(.01)
        controls = self.read_status()["controls"]
        self.assertTrue(controls["ownedActionActive"])
        self.assertEqual("unavailable", controls["f8"])
        self.assertTrue(any("F8 unavailable" in text for text in self.labels()), self.labels())
        self.button("STOP").invoke()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            self.roots[0].update()
            if any(isinstance(w, ttk.Button) and str(w["text"]) == "STOP requested…"
                   for w in self.widgets(self.roots[0])):
                break
            time.sleep(.01)
        controls = self.read_status()["controls"]
        self.assertTrue(controls["stopLatched"])
        self.assertTrue(controls["hadOwnedAction"])
        self.assertEqual("not-measured", controls["stationaryEvidence"])
        self.assertEqual("STOP requested…", str(self.button("STOP requested…")["text"]))
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.roots[0].update()
            controls = self.read_status()["controls"]
            if not controls["ownedActionActive"]:
                break
            time.sleep(.01)
        self.assertFalse(controls["ownedActionActive"])
        self.assertEqual("pass", controls["stationaryEvidence"])
        self.assertEqual("not-measured", controls["keyReleaseEvidence"])
        self.assertEqual("inactive", controls["f8"])
        self.assertTrue(listeners[0].closed)
        verify.assert_called_once()
        self.button("STOP").invoke()
        controls = self.read_status()["controls"]
        self.assertFalse(controls["hadOwnedAction"])
        self.assertIsNone(controls["result"])
        self.assertEqual("not-measured", controls["stationaryEvidence"])
        self.assertEqual("not-measured", controls["keyReleaseEvidence"])
        verify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
