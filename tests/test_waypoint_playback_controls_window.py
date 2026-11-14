"""Playback action/readiness presentation with fake poses and withdrawn Tk."""
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app
from tests import test_waypoint_header_window as fixture
from tests import test_waypoint_playback_window_state as progress_fixture

tk, ttk = fixture.tk, fixture.ttk


@unittest.skipIf(tk is None, "Tk unavailable")
class PlaybackControlsWindowTests(unittest.TestCase):
    setUp = fixture.HeaderWindowTests.setUp
    cleanup_gui = fixture.HeaderWindowTests.cleanup_gui
    widgets = fixture.HeaderWindowTests.widgets
    button = fixture.HeaderWindowTests.button
    route_table = fixture.HeaderWindowTests.route_table
    launch = fixture.HeaderWindowTests.launch
    read_status = fixture.HeaderWindowTests.read_status
    labels = fixture.HeaderWindowTests.labels
    pose_toggle = fixture.HeaderWindowTests.pose_toggle
    write_checkpoint = progress_fixture.PlaybackWindowStateTests.write_checkpoint

    def launch_route(self, *, direction=None, completed=0):
        self.document = {"waypoints": [["Alpha", 0, 0], ["Beta", 1, 0],
                                       ["Gamma", 2, 0], ["Delta", 3, 0]], "heights": [0] * 4}
        route = self.path / "route.json"
        route.write_text(json.dumps(self.document), encoding="utf-8")
        if direction:
            self.checkpoint = self.write_checkpoint(self.document, direction, completed)
        self.current = {"x": 3. if direction == "reverse" else 0.}
        self.reader = Mock(side_effect=lambda **kwargs: app.Snapshot(app.Position(self.current["x"], 0, 0),
                                                                  0, time.monotonic(), "fake-native"))
        self.launch(SimpleNamespace(read=self.reader, pid=123), route)
        self.window = self.roots[0]

    def playback_labels(self):
        group = next(w for w in self.widgets(self.window)
                     if isinstance(w, ttk.LabelFrame) and str(w["text"]) == "PLAYBACK")
        result = []
        for widget in self.widgets(group):
            if isinstance(widget, ttk.Label):
                variable = str(widget["textvariable"])
                result.append(str(widget.getvar(variable)) if variable else str(widget["text"]))
        return result

    def progressbar(self):
        notebook = next(w for w in self.widgets(self.window) if isinstance(w, ttk.Notebook))
        replay = self.window.nametowidget(notebook.tabs()[0])
        return next(w for w in self.widgets(replay) if isinstance(w, ttk.Progressbar))

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.window.update()
            if all(not worker.is_alive() for worker in self.threads) and not self.read_status()["app"]["busy"]:
                return
            time.sleep(.01)
        self.fail("Fake playback did not settle")

    def test_reverse_button_stays_steady_across_idle_refresh_cycles(self):
        self.launch_route(direction="reverse", completed=0)
        reverse = self.button("Play Reverse")
        states, styles = set(), set()
        deadline = time.monotonic() + 3.2
        while time.monotonic() < deadline:
            self.window.update()
            states.add(str(reverse["state"]))
            styles.add(str(reverse["style"]))
            time.sleep(.02)
        self.assertEqual({"normal"}, states)
        self.assertEqual({"TButton"}, styles)
        self.assertGreaterEqual(self.reader.call_count, 3)
        self.pose_toggle().invoke()
        self.window.update()
        self.assertEqual("disabled", str(reverse["state"]))
        self.assertEqual("TButton", str(reverse["style"]))

    def test_direction_endpoints_and_reverse_resume_original_point_are_in_playback_group(self):
        self.launch_route(direction="reverse", completed=1)
        before = self.reader.call_count
        text = self.playback_labels()
        self.assertTrue(any("#1" in line and "Alpha" in line for line in text), text)
        self.assertTrue(any("#4" in line and "Delta" in line for line in text), text)
        self.assertTrue(any("#3" in line and "Gamma" in line and "reverse" in line.casefold() for line in text), text)
        readiness = self.read_status()["playback"]["readiness"]
        self.assertEqual(3, readiness["resume"]["nextPointNumber"])
        self.assertEqual(1, readiness["resume"]["completedCount"])
        self.assertNotEqual("disabled", str(self.button("Play Forward")["state"]))
        self.assertTrue(readiness["forward"]["approachRequired"])
        self.assertEqual(3., readiness["forward"]["approachDistance"])
        self.assertTrue(any("Walk to start: 3.00u" in line for line in text), text)
        self.assertNotEqual("disabled", str(self.button("Play Reverse")["state"]))
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(before, self.reader.call_count)

    def test_complete_progress_stays_full_when_live_pose_is_paused_and_edit_is_pending(self):
        self.launch_route(direction="reverse", completed=4)
        original = self.checkpoint.read_bytes()
        before = self.reader.call_count
        self.pose_toggle().invoke()
        table = self.route_table()
        table.selection_set(table.get_children()[0])
        self.window.update()
        notebook = next(w for w in self.widgets(self.window) if isinstance(w, ttk.Notebook))
        edit = self.window.nametowidget(notebook.tabs()[1])
        name = next(w for w in self.widgets(edit) if isinstance(w, ttk.Entry))
        name.delete(0, "end")
        name.insert(0, "Draft Alpha")
        self.window.update()
        resume = self.read_status()["playback"]["readiness"]["resume"]
        self.assertTrue(resume["complete"])
        self.assertFalse(resume["ready"])
        self.assertEqual(4, resume["completedCount"])
        self.assertEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(4., float(self.progressbar()["value"]))
        self.assertEqual(4., float(self.progressbar()["maximum"]))
        self.assertTrue(any("Complete" in text and "4/4" in text.replace(" ", "") for text in self.labels()), self.labels())
        self.assertEqual(original, self.checkpoint.read_bytes())
        self.assertEqual(before, self.reader.call_count)

    def test_stopped_reverse_play_keeps_cursor_and_resume_uses_saved_direction(self):
        entered = threading.Event()
        self.stack.enter_context(patch.object(app, "ForegroundStop", return_value=SimpleNamespace(
            registered=False, close=lambda: None)))
        calls = []
        def fake_play(adapter, document, stop, emit, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                self.write_checkpoint(document, "reverse", 1)
                emit({"status": "arrived", "nextWaypoint": 1, "waypointCount": 4})
                entered.set()
                if not stop.wait(3):
                    raise AssertionError("Test did not stop fake playback")
            raise app.Stopped("Fake reverse playback stopped")
        self.stack.enter_context(patch("scripts.waypoint_playback.play_route", side_effect=fake_play))
        def fake_stationary(*args, **kwargs):
            now = time.monotonic()
            return {"status": "pass", "samples": [
                {"position": {"x": 2., "y": 0., "z": 0.}, "bearing": 0, "acquired": stamp}
                for stamp in (now - .1, now)], "xyzDrift": 0.}
        self.stack.enter_context(patch.object(app, "verify_stopped_pose", side_effect=fake_stationary))
        self.launch_route(direction="reverse", completed=0)
        before = self.reader.call_count
        self.button("Play Reverse").invoke()
        self.assertTrue(entered.wait(2))
        self.current["x"] = 2.
        self.button("STOP").invoke()
        self.wait_idle()
        saved = self.read_status()["playback"]["readiness"]["resume"]
        self.assertEqual("reverse", saved["direction"])
        self.assertEqual(1, saved["completedCount"])
        self.assertEqual(3, saved["nextPointNumber"])
        self.assertEqual("Gamma", saved["nextName"])
        self.assertEqual(1., float(self.progressbar()["value"]))
        self.assertTrue(saved["ready"], saved)
        self.assertNotEqual("disabled", str(self.button("Resume")["state"]))
        self.assertEqual(before, self.reader.call_count)
        self.button("Resume").invoke()
        self.wait_idle()
        self.assertEqual(2, len(calls))
        self.assertTrue(calls[1]["resume"])
        self.assertEqual("reverse", calls[1]["direction"])

    def test_cli_resume_refusals_preserve_checkpoint_binding_without_starting_work(self):
        self.launch_route(direction="reverse", completed=1)
        baseline = self.read_status()["playback"]["checkpoint"]
        before, workers = self.reader.call_count, len(self.threads)
        malformed = self.path / "malformed.json"
        malformed.write_text("{}", encoding="utf-8")
        for arguments, code in (({"checkpoint": str(self.path / "absent.json")}, None),
                                ({"checkpoint": str(malformed)}, "progress-unavailable"),
                                ({"direction": "forward"}, "resume-direction-mismatch")):
            with self.subTest(arguments=arguments):
                # Admission checks the transport request's queue timestamp.
                (self.server.path / "requests" / "refused-resume.json").write_text("{}", encoding="utf-8")
                result = self.dispatch("playback.resume", dict(execute=True, **arguments), "refused-resume")
                self.assertFalse(result["ok"], result)
                if code:
                    self.assertEqual(code, result["error"]["code"], result)
                status = self.read_status()
                self.assertEqual(baseline, status["playback"]["checkpoint"])
                self.assertIsNone(status["activeRequestId"])
                self.assertFalse(status["app"]["busy"])
        self.write_checkpoint(self.document, "reverse", 4)
        (self.server.path / "requests" / "complete-resume.json").write_text("{}", encoding="utf-8")
        complete = self.dispatch("playback.resume", {"execute": True}, "complete-resume")
        self.assertFalse(complete["ok"], complete)
        self.assertEqual("playback-complete", complete["error"]["code"], complete)
        self.assertEqual(baseline, self.read_status()["playback"]["checkpoint"])
        self.assertEqual(before, self.reader.call_count)
        self.assertEqual(workers, len(self.threads))


if __name__ == "__main__":
    unittest.main()
