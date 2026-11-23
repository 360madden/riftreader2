"""Test local dependency checks without starting physical workflow processes."""
from contextlib import redirect_stdout
from io import StringIO
import json
import subprocess
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
