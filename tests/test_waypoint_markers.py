"""Owned marker lifecycle tests using fake processes and local files only."""
import json
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts.physical_waypoints import OwnedWaypointMarkers, WaypointError


class FakeChild:
    def __init__(self):
        self.returncode = None
    def poll(self):
        return self.returncode


class OwnedMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "artifacts").mkdir()
        self.child = FakeChild()
        self.popen = Mock(return_value=self.child)
        self.markers = OwnedWaypointMarkers(self.root, popen=self.popen)
        self.sha = "a" * 64
        self.identity = {"machine": "AMD-DESKTOP", "processId": 123, "processStartUtcTicks": "1234",
                         "gameBuildSha256": self.sha, "unitKey": "player"}
        self.adapter = SimpleNamespace(pid=123, binding={"runtimeIdentity": dict(self.identity)},
                                       target={"processId": 123, "processStartUtcTicks": "1234",
                                               "executableSha256": self.sha, "hwnd": 12345})
        self.route = {"waypoints": [["A", 1, 2], ["B", 3, 4]], "heights": [5, 6],
                      "recording": {"complete": True, "version": 1,
                                    "identity": {"runtimeIdentity": dict(self.identity)}}}

    def test_launch_pins_epoch_and_uses_owned_stop_file(self):
        self.markers.start(self.route, self.adapter)
        command = self.popen.call_args.args[0]
        self.assertEqual(str(Path(sys.executable).with_name("pythonw.exe")), command[0])
        self.assertEqual("native", command[command.index("--presenter") + 1])
        self.assertNotIn("--target-beacon", command)
        self.assertNotIn("--landmark-number", command)
        for flag, expected in (("--physical-pid", "123"), ("--expect-start-ticks", "1234"),
                               ("--expect-sha256", self.sha), ("--expect-hwnd", hex(12345)),
                               ("--max-age", ".35"), ("--duration", "600")):
            self.assertEqual(expected, command[command.index(flag) + 1])
        route = Path(command[command.index("--route") + 1])
        self.assertEqual(str(self.root / "artifacts" / "waypoint-current-progress.json"),
                         command[command.index("--progress-file") + 1])
        self.assertEqual(self.route, json.loads(route.read_text(encoding="utf-8")))
        self.assertFalse(self.markers.stop_path.exists())
        self.markers.stop()
        self.assertTrue(self.markers.stop_path.exists())
        self.markers.stop()
        self.assertTrue(self.markers.running())
        with self.assertRaises(WaypointError):
            self.markers.start(self.route, self.adapter)
        self.child.returncode = 0
        self.assertFalse(self.markers.running())

    def test_qt_environment_selects_qt_presenter(self):
        executable = self.root / ".local" / "overlay-venv" / "Scripts" / "pythonw.exe"
        executable.parent.mkdir(parents=True)
        executable.touch()
        self.markers.start(self.route, self.adapter)
        command = self.popen.call_args.args[0]
        self.assertEqual(str(executable), command[0])
        self.assertEqual("qt", command[command.index("--presenter") + 1])

    def test_target_beacon_opt_in_keeps_route_and_process_binding(self):
        self.markers.start(self.route, self.adapter, target_beacon=True)
        command = self.popen.call_args.args[0]
        self.assertEqual(1, command.count("--target-beacon"))
        self.assertEqual("1234", command[command.index("--expect-start-ticks") + 1])
        path = Path(command[command.index("--route") + 1])
        self.assertEqual(self.route, json.loads(path.read_text()))

    def test_explicit_landmark_number_is_one_based_without_creating_progress(self):
        self.markers.start(self.route, self.adapter, landmark_number=2)
        command = self.popen.call_args.args[0]
        self.assertEqual("2", command[command.index("--landmark-number") + 1])
        self.assertEqual(1, command.count("--landmark-number"))
        route = Path(command[command.index("--route") + 1])
        self.assertEqual(self.route, json.loads(route.read_text()))
        self.assertFalse((self.root / "artifacts" / "waypoint-current-progress.json").exists())

    def test_invalid_landmark_numbers_are_refused_before_popen(self):
        for number in (True, False, 0, -1, 3, 1.0, "1"):
            with self.subTest(number=number), self.assertRaises(WaypointError):
                self.markers.start(self.route, self.adapter, landmark_number=number)
        self.popen.assert_not_called()
        self.assertEqual([], list((self.root / "artifacts").iterdir()))

    def test_unrecorded_or_missing_height_route_is_refused(self):
        for route in ({"waypoints": [["A", 1, 2]]}, {**self.route, "heights": [5, None]}):
            with self.subTest(route=route), self.assertRaises(ValueError):
                self.markers.start(route, self.adapter)
        self.popen.assert_not_called()

    def test_changed_player_or_epoch_is_refused_before_launch(self):
        self.adapter.binding["runtimeIdentity"]["unitKey"] = "other"
        with self.assertRaises(WaypointError):
            self.markers.start(self.route, self.adapter)
        self.adapter.binding["runtimeIdentity"]["unitKey"] = "player"
        self.adapter.target["processStartUtcTicks"] = "5678"
        with self.assertRaises(WaypointError):
            self.markers.start(self.route, self.adapter)
        self.popen.assert_not_called()

    def test_failed_stop_keeps_child_owned_and_prevents_relaunch(self):
        self.markers.start(self.route, self.adapter)
        self.markers.stop_path.touch()
        with self.assertRaises(FileExistsError):
            self.markers.stop()
        self.assertTrue(self.markers.running())
        self.assertFalse(self.markers.stop_requested)
        with self.assertRaises(WaypointError):
            self.markers.start(self.route, self.adapter)
        self.assertEqual(1, self.popen.call_count)


if __name__ == "__main__":
    unittest.main()
