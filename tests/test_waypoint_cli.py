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
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import physical_waypoints as waypoint
from tests.test_physical_waypoints import SimulatedRift


class WaypointCliTests(unittest.TestCase):
    def setUp(self):
        self.stop_guard = self.enterContext(patch.object(waypoint, "ForegroundStop"))
        self.test_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.test_root / "artifacts").mkdir()
        self.enterContext(patch.object(waypoint, "ROOT", self.test_root))

    def failed_playback(self, error, reads):
        source = self.test_root / "route.json"
        source.write_text(json.dumps({"waypoints": [["A", 0, 0], ["B", 1, 0]]}))
        checkpoint = self.test_root / "progress.json"
        checkpoint.write_text('{"nextIndex": 1}')
        adapter = SimpleNamespace(binding={"runtimeIdentity": {"processId": 123}},
                                  input_receipt_path=self.test_root / "native-pulses.jsonl",
                                  read=Mock(side_effect=reads))
        partial = {"status": "arrived", "name": "A", "actions": [{"key": "w"}]}

        def playback(*args, **kwargs):
            args[3](partial)
            raise error

        output = io.StringIO()
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), \
                patch("scripts.waypoint_playback.play_route", side_effect=playback), redirect_stdout(output):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--play-route", str(source), "--reverse", "--resume",
                                  "--progress", str(checkpoint), "--execute"])
        final = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(2, code)
        receipt = json.loads(Path(final["receipt"]).read_text())
        self.assertEqual(str(adapter.input_receipt_path), receipt["inputReceiptPath"])
        self.assertEqual(str(checkpoint), receipt["checkpointPath"])
        self.assertEqual('{"nextIndex": 1}', checkpoint.read_text())
        self.assertEqual([partial], receipt["completedLegs"])
        self.assertEqual([partial], receipt["events"])
        return receipt, adapter

    def test_cli_stop_retains_stationary_sources_and_partial_progress(self):
        first = waypoint.Snapshot(waypoint.Position(1, 2, 3), 4, 10, "first.json")
        second = waypoint.Snapshot(waypoint.Position(1, 2, 3), 4, 11, "second.json")
        receipt, adapter = self.failed_playback(waypoint.Stopped("operator STOP"), [first, second])
        self.assertEqual("stopped", receipt["status"])
        self.assertEqual("operator STOP", receipt["originalReason"])
        evidence = receipt["stopVerification"]
        self.assertEqual("pass", evidence["status"])
        self.assertEqual(["first.json", "second.json"], [s["source"] for s in evidence["samples"]])
        self.assertEqual(2, adapter.read.call_count)

    def test_cli_stop_unavailable_remains_honest(self):
        receipt, adapter = self.failed_playback(waypoint.Stopped("operator STOP"), [ValueError("native unavailable")])
        self.assertEqual("unavailable", receipt["stopVerification"]["status"])
        self.assertEqual("halted", receipt["status"])
        self.assertEqual("operator STOP", receipt["originalReason"])
        self.assertIn("native unavailable", receipt["reason"])
        self.assertEqual(1, adapter.read.call_count)

    def test_cli_ordinary_error_keeps_reason_and_measures_post_halt(self):
        first = waypoint.Snapshot(waypoint.Position(1, 2, 3), 4, 10, "first.json")
        second = waypoint.Snapshot(waypoint.Position(1, 2, 3), 4, 11, "second.json")
        receipt, adapter = self.failed_playback(ValueError("wrong route"), [first, second])
        self.assertEqual("wrong route", receipt["reason"])
        self.assertEqual("halted", receipt["status"])
        self.assertEqual("pass", receipt["stopVerification"]["status"])
        self.assertIn("after halt", receipt["stopVerification"]["qualification"])
        self.assertEqual(2, adapter.read.call_count)

    def test_cli_ordinary_error_preserves_reason_when_measurement_unavailable(self):
        receipt, adapter = self.failed_playback(ValueError("foreground lost"), [ValueError("native unavailable")])
        self.assertEqual("foreground lost", receipt["reason"])
        self.assertEqual("halted", receipt["status"])
        self.assertEqual("unavailable", receipt["stopVerification"]["status"])
        self.assertEqual(1, adapter.read.call_count)

    def test_cli_receipt_write_failure_does_not_mask_action_failure(self):
        adapter = SimpleNamespace(input_receipt_path=self.test_root / "pulses.jsonl")
        output = io.StringIO()
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), \
                patch("scripts.continuous_move.run_continuous_route", side_effect=ValueError("action failed")), \
                patch("scripts.waypoint_progress.write_json_atomic", side_effect=OSError("disk full")), \
                redirect_stdout(output):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--go", "1", "0", "--execute"])
        failure = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(2, code)
        self.assertEqual("action failed", failure["reason"])
        self.assertEqual("disk full", failure["receiptError"])
        self.assertEqual(str(adapter.input_receipt_path), failure["inputReceiptPath"])

    def test_play_route_requires_explicit_execution(self):
        with patch.object(waypoint, "PhysicalAdapter") as adapter, \
                patch.object(waypoint, "launch_window") as window, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                               "--play-route", "route.json"])
        self.assertEqual(2, caught.exception.code)
        adapter.assert_not_called()
        window.assert_not_called()
        self.stop_guard.assert_not_called()

    def test_goal_height_validation_precedes_adapter_and_action(self):
        cases = [
            (["--goal-y", "3", "--execute"], "requires a direct --go"),
            (["--go", "1", "2", "--goal-y", "nan", "--execute"], "must be finite"),
            (["--go", "1", "2", "--goal-y", "3", "--movement-engine", "pulse",
              "--execute"], "requires --movement-engine continuous"),
        ]
        for extra, reason in cases:
            with self.subTest(reason=reason), \
                 patch.object(waypoint, "PhysicalAdapter") as adapter, \
                 redirect_stderr(io.StringIO()) as error, \
                 self.assertRaises(SystemExit) as caught:
                waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                               *extra])
            self.assertEqual(2, caught.exception.code)
            self.assertIn(reason, error.getvalue())
            adapter.assert_not_called()

    def test_direct_continuous_goal_height_calls_height_aware_mover(self):
        adapter = SimpleNamespace(binding={"runtimeIdentity": {"processId": 123}},
                                  input_receipt_path=self.test_root / "inputs.jsonl")
        result = {"status": "arrived", "position": {"x": 1, "y": 3.5, "z": 2},
                  "bearing": 0.0, "distance": 0.0}
        output = io.StringIO()
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), \
             patch("scripts.continuous_move.move_to", return_value=result) as mover, \
             redirect_stdout(output):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--go", "1", "2", "--goal-y", "3.5", "--execute"])
        self.assertEqual(0, code)
        self.assertEqual(3.5, mover.call_args.kwargs["goal_y"])
        self.assertEqual((adapter, 1.0, 2.0), mover.call_args.args[:3])
        saved = json.loads(Path(json.loads(output.getvalue().splitlines()[-1])["receipt"]).read_text())
        self.assertEqual(3.5, saved["position"]["y"])

    def test_window_route_rejects_each_cli_action_before_startup(self):
        actions = [
            ["--go", "1", "2"],
            ["--face-bearing", "0"],
            ["--run-route", "run.json"],
            ["--play-route", "play.json"],
        ]
        for action in actions:
            with self.subTest(action=action), \
                    patch.object(waypoint, "PhysicalAdapter") as adapter, \
                    patch.object(waypoint, "launch_window") as window, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                   "--route", "window.json", *action, "--execute"])
            self.assertEqual(2, caught.exception.code)
            adapter.assert_not_called()
            window.assert_not_called()
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
                                      "--run-route", str(route), "--movement-engine", "pulse", "--execute"])
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

    def test_continuous_run_route_forwards_validated_parallel_heights(self):
        route = self.test_root / "measured-route.json"
        route.write_text(json.dumps({
            "waypoints": [["Slope", 1, 2], ["Camp", 3, 4]],
            "heights": [877.1, None]}), encoding="utf-8")
        adapter = SimpleNamespace(binding={"runtimeIdentity": {"processId": 123}},
                                  input_receipt_path=self.test_root / "inputs.jsonl")
        legs = [
            {"status": "arrived", "name": "Slope", "position": {"x": 1, "y": 877.1, "z": 2},
             "bearing": 0, "distance": 0, "pulses": 1, "totalHoldMs": 10},
            {"status": "arrived", "name": "Camp", "position": {"x": 3, "y": 877.1, "z": 4},
             "bearing": 0, "distance": 0, "pulses": 1, "totalHoldMs": 10},
        ]
        output = io.StringIO()
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), \
             patch("scripts.continuous_move.run_continuous_route", return_value=legs) as runner, \
             redirect_stdout(output):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--run-route", str(route), "--execute"])
        self.assertEqual(0, code)
        self.assertEqual([877.1, None], runner.call_args.kwargs["goal_heights"])

    def test_continuous_play_route_enables_cursor_height_awareness(self):
        route = self.test_root / "play-height-route.json"
        route.write_text(json.dumps({"waypoints": [["Camp", 3, 4]],
                                     "heights": [877.1]}), encoding="utf-8")
        adapter = SimpleNamespace(binding={"runtimeIdentity": {
                                      "machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64,
                                      "unitKey": "1", "processId": 123}},
                                  input_receipt_path=self.test_root / "inputs.jsonl")
        leg = {"status": "arrived", "name": "Camp",
               "position": {"x": 3, "y": 877.1, "z": 4},
               "bearing": 0, "distance": 0, "pulses": 1, "totalHoldMs": 10}
        output = io.StringIO()
        with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), \
             patch("scripts.waypoint_playback.play_route",
                   return_value=([leg], SimpleNamespace(next_index=1))) as playback, \
             redirect_stdout(output):
            code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                  "--play-route", str(route), "--execute"])
        self.assertEqual(0, code)
        self.assertIs(playback.call_args.kwargs["height_aware"], True)

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
