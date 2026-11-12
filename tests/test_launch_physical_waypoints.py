import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import launch_physical_waypoints as launcher


class LauncherTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
