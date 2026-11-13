import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import launch_physical_waypoints as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        root_patcher = patch.object(launcher, "ROOT", self.root)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)

    def run_launcher(self, args):
        adapter = SimpleNamespace(read=lambda: SimpleNamespace(bearing=12), binding={"mode": "reused-seed"})
        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical", return_value={"status": "ready", "target": {"processId": 7}}), \
             patch.object(launcher, "PhysicalAdapter", return_value=adapter), \
             patch.object(launcher, "launch_window") as window, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(args), 0)
            return window, output.getvalue()

    def test_default_window_reconnects_only_single_client(self):
        window, _ = self.run_launcher([])
        self.assertTrue(window.call_args.args[0].auto_reconnect)
        self.assertEqual(window.call_args.args[0].initial_adapter.binding, {"mode": "reused-seed"})

    def test_explicit_pid_stays_pinned(self):
        window, _ = self.run_launcher(["--physical-pid", "7"])
        self.assertFalse(window.call_args.args[0].auto_reconnect)

    def test_check_reports_binding(self):
        window, output = self.run_launcher(["--check"])
        self.assertEqual(json.loads(output)["calibrationBinding"], {"mode": "reused-seed"})
        window.assert_not_called()

    def test_default_waits_when_absent_or_ambiguous(self):
        for reason in ("not found", "ambiguous"):
            with self.subTest(reason=reason), \
                 patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(launcher.physical_rift, "select_physical", return_value={"status": "blocked", "reason": reason}), \
                 patch.object(launcher, "launch_window") as window:
                self.assertEqual(launcher.main([]), 0)
                args = window.call_args.args[0]
                self.assertIsNone(args.physical_pid)
                self.assertIsNone(args.initial_adapter)
                self.assertTrue(args.auto_reconnect)
                self.assertEqual(args.initial_reason, reason)

    def test_default_discards_pid_if_initial_validation_fails(self):
        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical", return_value={"status": "ready", "target": {"processId": 7}}), \
             patch.object(launcher, "PhysicalAdapter", side_effect=ValueError("loading")), \
             patch.object(launcher, "launch_window") as window:
            self.assertEqual(launcher.main([]), 0)
            self.assertIsNone(window.call_args.args[0].physical_pid)
            self.assertIsNone(window.call_args.args[0].initial_adapter)

    def test_check_stays_strict_and_unsupported_host_refused(self):
        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical", return_value={"status": "blocked", "reason": "absent"}), \
             patch.object(launcher, "launch_window") as window, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--check"]), 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], "absent")
            window.assert_not_called()
        with patch.object(launcher.socket, "gethostname", return_value="UNKNOWN"), \
             patch.object(launcher, "launch_window") as window, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--check"]), 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], "unsupported-host")
            window.assert_not_called()

    def test_explicit_pid_absent_stays_strict(self):
        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical", return_value={"status": "blocked", "reason": "absent"}), \
             patch.object(launcher, "launch_window") as window, \
             patch("tkinter.Tk"), patch("tkinter.messagebox.showerror"):
            self.assertEqual(launcher.main(["--physical-pid", "7"]), 2)
            window.assert_not_called()

    def test_cli_invalid_route_logs_full_stack_without_starting_helper_or_native_reader(self):
        route = self.root / "invalid-route.json"
        route.write_text('{"waypoints": [', encoding="utf-8")
        previous_sys_hook = sys.excepthook
        previous_thread_hook = threading.excepthook

        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical") as select_physical, \
             patch.object(launcher, "PhysicalAdapter") as adapter, \
             patch.object(launcher, "launch_window") as window, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.main(["--cli", "--route", str(route)]), 2)

        self.assertIn("Expecting value", errors.getvalue())
        select_physical.assert_not_called()
        adapter.assert_not_called()
        window.assert_not_called()
        self.assertIs(sys.excepthook, previous_sys_hook)
        self.assertIs(threading.excepthook, previous_thread_hook)

        logs = list((self.root / "artifacts" / "waypoint-logs").glob("waypoints-*.log"))
        self.assertEqual(len(logs), 1)
        records = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
        failure = next(record for record in records if record["message"] == "Waypoint startup failed")
        self.assertEqual(failure["exceptionType"], "JSONDecodeError")
        self.assertIn("Traceback (most recent call last)", failure["traceback"])
        self.assertIn("in main", failure["traceback"])
        self.assertIn("json.loads", failure["traceback"])


if __name__ == "__main__":
    unittest.main()
