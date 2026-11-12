from contextlib import redirect_stdout, redirect_stderr
import io
import json
import signal
import subprocess
import sys
import threading
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as waypoint
from tests.test_physical_waypoints import SimulatedRift


class WaypointCliTests(unittest.TestCase):
    def setUp(self):
        self.stop_guard = self.enterContext(patch.object(waypoint, "ForegroundStop"))

    def test_saved_route_requires_explicit_execution(self):
        with patch.object(waypoint, "PhysicalAdapter") as adapter, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                               "--run-route", "route.json"])
        self.assertEqual(2, caught.exception.code)
        adapter.assert_not_called()
        self.stop_guard.assert_not_called()

    def test_saved_route_keeps_every_leg_in_one_receipt(self):
        adapter = SimulatedRift()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            route = root / "route.json"
            route.write_text(json.dumps({"waypoints": [["Ahead", 0, 1], ["Home", 0, 0]]}))
            output = io.StringIO()
            with patch.object(waypoint, "ROOT", root), patch.object(waypoint, "PhysicalAdapter", return_value=adapter), redirect_stdout(output):
                code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                      "--run-route", str(route), "--execute"])
            receipt = json.loads(output.getvalue().splitlines()[-1])
            result = json.loads(Path(receipt["receipt"]).read_text())
            self.assertEqual(0, code)
            self.assertEqual("arrived", result["status"])
            self.assertEqual(2, result["waypointCount"])
            self.assertEqual(2, len(result["legs"]))
            self.assertEqual(["Ahead", "Home"], [leg["name"] for leg in result["legs"]])
            self.assertTrue(result["allPulsesReleased"])
            self.assertLessEqual(result["distance"], .3)
            self.assertEqual(len(adapter.calls), result["pulses"])
            self.stop_guard.return_value.close.assert_called_once()

    def test_bad_route_coordinates_send_no_input(self):
        adapter = SimulatedRift()
        with tempfile.TemporaryDirectory() as directory:
            route = Path(directory) / "route.json"
            route.write_text(json.dumps({"waypoints": [["Bad", float("nan"), 0]]}))
            with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), redirect_stdout(io.StringIO()):
                code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                      "--run-route", str(route), "--execute"])
        self.assertEqual(2, code)
        self.assertFalse(adapter.calls)

    def test_ctrl_c_latches_stop_without_interrupting_active_work(self):
        stop = threading.Event()
        previous = signal.getsignal(signal.SIGINT)
        completed = []
        with waypoint.cli_stop_controls(stop):
            signal.raise_signal(signal.SIGINT)
            completed.append("bounded work finished")
        self.assertTrue(stop.is_set())
        self.assertEqual(["bounded work finished"], completed)
        self.assertIs(previous, signal.getsignal(signal.SIGINT))
        self.stop_guard.return_value.close.assert_called_once()

    def test_ctrl_c_allows_child_cleanup_to_finish(self):
        stop = threading.Event()
        with waypoint.cli_stop_controls(stop):
            timer = threading.Timer(.05, lambda: signal.raise_signal(signal.SIGINT))
            timer.start()
            try:
                child = subprocess.run([sys.executable, "-c",
                    "import time\ntry: time.sleep(.2)\nfinally: print('released',flush=True)"],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            finally:
                timer.join()
        self.assertTrue(stop.is_set())
        self.assertEqual(0, child.returncode)
        self.assertEqual("released", child.stdout.strip())

    def test_unavailable_hotkey_sends_nothing_and_restores_sigint(self):
        adapter = SimulatedRift()
        previous = signal.getsignal(signal.SIGINT)
        self.stop_guard.side_effect = waypoint.WaypointError("F8 is unavailable")
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), redirect_stdout(io.StringIO()):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--go", "0", "1", "--execute"])
        self.assertEqual(2, code)
        self.assertFalse(adapter.calls)
        self.assertIs(previous, signal.getsignal(signal.SIGINT))


if __name__ == "__main__":
    unittest.main()
