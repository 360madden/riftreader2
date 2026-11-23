"""Test local dependency checks without starting physical workflow processes."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import check_physical_dependencies as preflight


class PhysicalDependenciesTests(unittest.TestCase):
    def run_cli(self, *args):
        output = StringIO()
        with redirect_stdout(output), patch.object(preflight.socket, "gethostname", return_value="LOCAL-PC"):
            code = preflight.main(args)
        return code, json.loads(output.getvalue())

    def test_wrong_host_refuses_before_any_check(self):
        with patch.object(preflight, "check_workflow") as check:
            code, report = self.run_cli("--expected-host", "other-host")
        self.assertEqual(code, 2)
        self.assertEqual(report["reason"], "physical-host-mismatch")
        self.assertEqual(report["checks"], {})
        check.assert_not_called()

    def test_register_addons_root_uses_host_verification_without_running_checks(self):
        from scripts import observe_physical

        with patch.object(preflight, "check_workflow") as check, \
                patch.object(observe_physical, "register_local_rift_addons_root",
                             return_value={"addonsRoot": "custom"}) as register:
            refused, _ = self.run_cli("--expected-host", "other-host", "--register-addons-root", "custom")
            self.assertEqual(refused, 2)
            register.assert_not_called()
            code, report = self.run_cli("--expected-host", "local-pc", "--register-addons-root", "custom")
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "registered")
            self.assertEqual(report["addonsRoot"], "custom")
            self.assertEqual(str(register.call_args.args[0]), "custom")
            self.assertFalse(report["inputSent"])
            self.assertFalse(report["captureAttempted"])
            check.assert_not_called()

    def test_requested_workflows_run_once_even_after_a_blocked_check(self):
        blocked = {"status": "blocked", "exitCode": 2, "result": {"reason": "missing-capture-runner"}}
        ready = {"status": "ready", "exitCode": 0, "result": {"status": "ready"}}
        with patch.object(preflight, "check_workflow", side_effect=[blocked, ready]) as check:
            code, report = self.run_cli("--expected-host", "local-pc", "--workflow", "workbridge",
                                        "--workflow", "prepared-maps", "--workflow", "workbridge")
        self.assertEqual(code, 2)
        self.assertEqual(report["host"], "LOCAL-PC")
        self.assertEqual(report["checks"], {"workbridge": blocked, "prepared-maps": ready})
        self.assertFalse(report["inputSent"])
        self.assertFalse(report["captureAttempted"])
        workbridge, maps = check.call_args_list
        self.assertEqual(workbridge.args, ("workbridge", ("observe_target.py", "--target", "physical",
                         "--expected-host", "LOCAL-PC", "--check-dependencies", "--physical-capture-backend",
                         "workbridge")))
        self.assertEqual(maps.args, ("prepared-maps", ("waypoint_destination_plan.py", "--check-dependencies")))

    def test_malformed_child_output_and_timeouts_fail_closed(self):
        command = preflight.workflow_commands("LOCAL-PC")["waypoints"]
        for stdout in ("", "[..]", "[]"):
            with self.subTest(stdout=stdout), patch.object(preflight, "run_check", return_value=
                    subprocess.CompletedProcess([], 0, stdout, "")):
                result = preflight.check_workflow("waypoints", command)
                self.assertEqual(result["reason"], "invalid-dependency-check-output")
        with patch.object(preflight, "run_check", side_effect=subprocess.TimeoutExpired([], 45)):
            result = preflight.check_workflow("waypoints", command)
        self.assertEqual(result, {"status": "blocked", "reason": "dependency-check-timed-out"})

    def test_qt_missing_explicit_python_reports_its_path_without_starting_it(self):
        missing_python = preflight.ROOT / "missing-test-overlay-venv/Scripts/pythonw.exe"
        with patch.dict(preflight.os.environ, RR2_OVERLAY_PYTHON=str(missing_python)), \
                patch.object(preflight, "run_check") as run:
            result = preflight.check_workflow("qt", None)
        self.assertEqual(result, {"status": "blocked", "pythonExecutable": str(missing_python),
                                  "reason": "overlay-python-unavailable"})
        run.assert_not_called()

    def test_qt_check_uses_the_platform_plugin_probe_and_reports_its_failure(self):
        with TemporaryDirectory() as directory:
            interpreter = Path(directory) / "pythonw.exe"
            interpreter.touch()
            receipt = {"status": "blocked", "reason": "qt-windows-platform-plugin-missing",
                       "pluginPath": str(Path(directory) / "platforms/qwindows.dll")}
            with patch.object(preflight.physical_view_tools, "overlay_python", return_value=interpreter), \
                    patch.object(preflight, "run_check", return_value=subprocess.CompletedProcess(
                        [], 2, json.dumps(receipt), "")) as run:
                report = preflight.check_workflow("qt", None)
            self.assertEqual(report, dict(receipt, pythonExecutable=str(interpreter), exitCode=2))
            run.assert_called_once_with(interpreter, ("-m", "scripts.qt_waypoint_overlay"), cwd=preflight.ROOT)

    def test_rerun_viewer_availability_does_not_make_export_ready(self):
        with patch.object(preflight.physical_view_tools, "check_rerun_viewer",
                          return_value=(["rerun.exe"], {}, "rerun-cli 0.43.1")), \
                patch.object(preflight.physical_view_tools, "check_rerun_exporter",
                             side_effect=ValueError("visualization-environment-unavailable")):
            result = preflight.check_workflow("rerun", None)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["viewer"]["status"], "ready")
        self.assertEqual(result["exporter"], {"status": "blocked", "reason": "visualization-environment-unavailable"})

    def test_optional_reports_work_without_site_packages_in_the_caller(self):
        missing_python = str(preflight.ROOT / "missing-test-view-venv/Scripts/python.exe")
        env = dict(preflight.os.environ, RR2_DXCAM_PYTHON=missing_python,
                   RR2_OVERLAY_PYTHON=missing_python, RR2_RERUN_PYTHON=missing_python)
        completed = subprocess.run(
            [sys.executable, "-B", "-S", preflight.__file__, "--expected-host", preflight.socket.gethostname(),
             "--workflow", "dxcam", "--workflow", "qt", "--workflow", "rerun"],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual({key: check["reason"] for key, check in json.loads(completed.stdout)["checks"].items()}, {
            "dxcam": "desktop-capture-environment-unavailable",
            "qt": "overlay-python-unavailable",
            "rerun": "optional-rerun-viewer-not-installed",
        })
