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

from scripts import launch_physical_waypoints as launcher, physical_waypoints as waypoints
from tests.test_physical_move_basis_waypoint import basis


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        root_patcher = patch.object(launcher, "ROOT", self.root)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)
        self.enterContext(patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": "",
                                                   "RR2_NATIVE_READER": "", "RR2_PHYSICAL_TOOLS_ROOT": "debug"}))

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

    def test_published_view_reader_reaches_the_window(self):
        published = self.root / "RiftReader2.Live.exe"
        window, _ = self.run_launcher(["--view-native-reader", str(published)])
        self.assertEqual(window.call_args.args[0].view_native_reader, published)

    def test_check_reports_binding(self):
        with patch.object(launcher.subprocess, "Popen") as spawn:
            window, output = self.run_launcher(["--detach-window", "--physical-pid", "7", "--check"])
        self.assertEqual(json.loads(output)["calibrationBinding"], {"mode": "reused-seed"})
        window.assert_not_called()
        spawn.assert_not_called()

    def test_desktop_launcher_detaches_using_the_selected_interpreter(self):
        route = self.root / "my route.json"
        caller = self.root / "other working directory"
        with patch.object(launcher.subprocess, "Popen") as spawn, \
             patch.object(launcher.Path, "cwd", return_value=caller), \
             patch.object(launcher.physical_rift, "select_physical") as select:
            self.assertEqual(launcher.main(["--detach-window", "--route", str(route)]), 0)
        command = spawn.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[2:], ["--route", str(route)])
        self.assertEqual(spawn.call_args.kwargs["cwd"], caller)
        self.assertEqual(spawn.call_args.kwargs["creationflags"],
                         getattr(launcher.subprocess, "CREATE_NO_WINDOW", 0))
        select.assert_not_called()

    def test_local_doctor_reports_independent_missing_prerequisites(self):
        with patch.object(waypoints, "ROOT", self.root), \
             patch.object(launcher.socket, "gethostname", return_value="rift-station"), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "blocked", "reason": "tkinter-unavailable"}), \
             patch.object(launcher.physical_rift, "NATIVE_EXE", self.root / "missing.exe"), \
             patch.object(launcher.physical_rift, "select_physical",
                          return_value={"status": "blocked", "reason": "not-running"}) as select, \
             patch.object(launcher, "PhysicalAdapter") as adapter, \
             patch.object(launcher, "launch_window") as window:
            report = launcher.check_local_setup()
        self.assertFalse(report["ready"])
        self.assertFalse(report["inputSent"])
        self.assertEqual(report["checks"]["nativeReader"]["reason"], "native-reader-not-built")
        self.assertEqual(report["checks"]["rift"]["reason"], "not-running")
        self.assertEqual(report["checks"]["movementBasis"]["path"],
                         str(self.root / "config" / "physical-movement-basis.rift-station.json"))
        self.assertEqual(report["checks"]["pose"]["status"], "not-checked")
        select.assert_called_once_with("RIFT-STATION", None)
        adapter.assert_not_called()
        window.assert_not_called()

    def test_local_doctor_checks_explicit_calibration_and_exact_process(self):
        basis_path = self.root / "measured basis.json"
        basis_path.touch()
        reader = self.root / "reader.exe"
        reader.touch()
        target = {"processId": 7, "hwnd": 11, "processStartUtcTicks": "123"}
        with patch.object(launcher.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "available"}), \
             patch.object(launcher.physical_rift, "NATIVE_EXE", reader), \
             patch.object(launcher.physical_rift, "select_physical",
                          return_value={"status": "ready", "target": target}) as select, \
             patch.object(launcher, "PhysicalAdapter") as adapter:
            adapter.return_value.target = target
            adapter.return_value.initial_pose.bearing = 12.0
            adapter.return_value.binding = {"mode": "measured-epoch"}
            with patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": str(basis_path)}):
                good = launcher.check_local_setup(7)
            self.assertTrue(good["ready"])
            self.assertEqual(good["checks"]["pose"]["calibrationBinding"], {"mode": "measured-epoch"})
            select.assert_called_once_with("RIFT-STATION", 7)
            adapter.assert_called_once_with("RIFT-STATION", 7, basis_path.resolve())

            adapter.return_value.target = dict(target, processStartUtcTicks="456")
            changed = launcher.check_local_setup(7, basis_path)
            self.assertFalse(changed["ready"])
            self.assertEqual(changed["checks"]["pose"]["reason"], "rift-identity-changed")

    def test_dependency_doctor_checks_local_basis_and_starts_only_native_help(self):
        host = "RIFT-STATION"
        calibration = basis()
        calibration["identity"]["machine"] = host
        basis_path = self.root / "measured.json"
        basis_path.write_text(json.dumps(calibration), encoding="utf-8")
        reader = self.root / "reader.exe"
        reader.touch()
        with patch.object(launcher.socket, "gethostname", return_value=host), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "available"}), \
             patch.object(launcher.physical_rift, "NATIVE_EXE", reader), \
             patch.object(launcher.physical_rift.observe_physical, "_run",
                          return_value=(0, "RiftReader2.Live native tools\nsample-current-facing --pid PID")) as run, \
             patch.object(launcher.physical_rift, "select_physical") as select, \
             patch.object(launcher, "PhysicalAdapter") as adapter:
            good = launcher.check_local_setup(basis=basis_path, dependencies_only=True)
            self.assertTrue(good["ready"])
            self.assertEqual(good["mode"], "dependencies")
            self.assertIsNone(good["target"])
            self.assertFalse(good["inputSent"])
            self.assertEqual(run.call_args.args[0], [reader, "--help"])

            vector = calibration["samples"]["laterW"]
            original_velocity = vector["vxCandidate"]
            for invalid in (None, "not a velocity", 1e308):
                with self.subTest(invalid_velocity=invalid):
                    vector["vxCandidate"] = invalid
                    basis_path.write_text(json.dumps(calibration), encoding="utf-8")
                    unusable = launcher.check_local_setup(basis=basis_path, dependencies_only=True)
                    self.assertFalse(unusable["ready"])
                    self.assertEqual(unusable["checks"]["movementBasis"]["reason"],
                                     "movement-basis-invalid-vectors")
                    self.assertEqual(unusable["checks"]["nativeReader"]["status"], "available")
            vector["vxCandidate"] = original_velocity
            basis_path.write_text(json.dumps(calibration), encoding="utf-8")

            run.return_value = (0, "RiftReader2.Live native tools\nsample-current-vitals")
            mismatched_reader = launcher.check_local_setup(basis=basis_path, dependencies_only=True)
            self.assertFalse(mismatched_reader["ready"])
            self.assertEqual(mismatched_reader["checks"]["nativeReader"]["missingCommands"],
                             ["sample-current-facing"])

            calibration["identity"]["machine"] = "AMD-DESKTOP"
            basis_path.write_text(json.dumps(calibration), encoding="utf-8")
            run.return_value = (2, "missing companion files")
            blocked = launcher.check_local_setup(basis=basis_path, dependencies_only=True)
            self.assertFalse(blocked["ready"])
            self.assertEqual(blocked["checks"]["movementBasis"]["reason"], "movement-basis-host-mismatch")
            self.assertEqual(blocked["checks"]["nativeReader"]["reason"], "native-reader-failed")
            self.assertEqual(blocked["checks"]["nativeReader"]["exitCode"], 2)
            select.assert_not_called()
            adapter.assert_not_called()

    def test_dependency_doctor_reports_invalid_reader_alongside_other_checks(self):
        host = "RIFT-STATION"
        calibration = basis()
        calibration["identity"]["machine"] = host
        basis_path = self.root / "measured.json"
        basis_path.write_text(json.dumps(calibration), encoding="utf-8")
        with patch.dict("os.environ", {"RR2_NATIVE_READER": "relative-reader.exe"}), \
             patch.object(launcher.socket, "gethostname", return_value=host), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "available"}), \
             patch.object(launcher.physical_rift, "select_physical") as select, \
             patch.object(launcher.physical_rift.observe_physical, "_run") as run:
            report = launcher.check_local_setup(basis=basis_path, dependencies_only=True)
        self.assertFalse(report["ready"])
        self.assertIsNone(report["target"])
        self.assertEqual(report["checks"]["tkinter"]["status"], "available")
        self.assertEqual(report["checks"]["movementBasis"]["status"], "present")
        self.assertEqual(report["checks"]["nativeReader"]["reason"], "invalid-native-reader-path")
        select.assert_not_called()
        run.assert_not_called()

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

    def test_check_stays_strict_and_invalid_host_refused(self):
        with patch.object(launcher.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(launcher.physical_rift, "select_physical", return_value={"status": "blocked", "reason": "absent"}), \
             patch.object(launcher, "launch_window") as window, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--check"]), 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], "absent")
            window.assert_not_called()
        with patch.object(launcher.socket, "gethostname", return_value="invalid / host"), \
             patch.object(launcher, "launch_window") as window, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--check"]), 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], "invalid-local-host")
            window.assert_not_called()

    def test_check_uses_only_the_local_default_basis_and_accepts_an_override(self):
        host = "RR2_FIELD-PC"
        config = self.root / "config"
        config.mkdir()
        measurement = basis()
        other_basis = config / "physical-movement-basis.amd-desktop.json"
        other_basis.write_text(json.dumps(measurement), encoding="utf-8")
        identity = measurement["identity"]
        target = {"processId": identity["processId"], "hwnd": 7,
                  "processStartUtcTicks": identity["processStartUtcTicks"],
                  "executableSha256": identity["gameBuildSha256"]}
        expected_basis = config / "physical-movement-basis.rr2_field-pc.json"
        with patch.object(waypoints, "ROOT", self.root), \
             patch.object(launcher.socket, "gethostname", return_value=host.lower()), \
             patch.object(launcher.physical_rift, "select_physical",
                          return_value={"status": "ready", "target": target}), \
             patch.object(waypoints.PhysicalAdapter, "read",
                          return_value=SimpleNamespace(bearing=12)) as read_pose, \
             patch.object(launcher, "launch_window") as window:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(launcher.main(["--check"]), 2)
            self.assertIn(str(expected_basis), json.loads(output.getvalue())["reason"])
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(launcher.main(["--check", "--basis", str(other_basis)]), 2)
            self.assertIn("another host/build", json.loads(output.getvalue())["reason"])
            read_pose.assert_not_called()

            identity["machine"] = host
            custom_basis = self.root / "custom-basis.json"
            for path, configured, args in (
                    (custom_basis, str(other_basis), ["--check", "--basis", str(custom_basis)]),
                    (custom_basis, str(custom_basis), ["--check"]),
                    (expected_basis, "", ["--check"])):
                path.write_text(json.dumps(measurement), encoding="utf-8")
                with patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": configured}), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(launcher.main(args), 0)
                report = json.loads(output.getvalue())
                self.assertEqual(report["calibrationBinding"]["runtimeIdentity"]["machine"], host)
                self.assertIs(report["inputSent"], False)
            window.assert_not_called()

    def test_relative_configured_calibration_path_is_refused(self):
        with patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": "relative/basis.json"}):
            with self.assertRaisesRegex(waypoints.WaypointError, "invalid-waypoints-basis-path"):
                waypoints.movement_basis_path("RIFT-STATION")

    def test_invalid_calibration_does_not_hide_other_checks_or_start_the_adapter(self):
        target = {"processId": 7, "hwnd": 42}
        reader = {"status": "blocked", "reason": "native-reader-not-built"}
        with patch.dict("os.environ", RR2_WAYPOINTS_BASIS="relative/basis.json"), \
             patch.object(launcher.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(launcher, "_check_tkinter", return_value={"status": "available"}), \
             patch.object(launcher, "_check_native_reader", return_value=reader), \
             patch.object(launcher.physical_rift, "select_physical",
                          return_value={"status": "ready", "target": target}) as select, \
             patch.object(launcher, "PhysicalAdapter") as adapter:
            dependencies = launcher.check_local_setup(dependencies_only=True)
            select.assert_not_called()
            live = launcher.check_local_setup(physical_pid=7)
            select.assert_called_once_with("RIFT-STATION", 7)
            adapter.assert_not_called()
        for report in dependencies, live:
            self.assertFalse(report["ready"])
            self.assertFalse(report["inputSent"])
            self.assertEqual(report["checks"]["tkinter"]["status"], "available")
            self.assertEqual(report["checks"]["nativeReader"], reader)
            self.assertEqual(report["checks"]["movementBasis"],
                             {"status": "blocked", "reason": "invalid-waypoints-basis-path"})
        self.assertEqual(live["checks"]["rift"]["status"], "available")
        self.assertEqual(live["checks"]["pose"]["status"], "not-checked")

    def test_local_calibration_folder_takes_precedence_over_packaged_basis(self):
        local = self.root / ".local" / "waypoints-calibration" / "rift-station"
        local.mkdir(parents=True)
        with patch.object(waypoints, "ROOT", self.root):
            self.assertEqual(waypoints.movement_basis_path("RIFT-STATION"), local)
            self.assertEqual(waypoints.movement_basis_path("OTHER-PC"),
                             self.root / "config" / "physical-movement-basis.other-pc.json")
            with patch.dict("os.environ", {"RR2_WAYPOINTS_BASIS": str(self.root / "custom folder")}):
                self.assertEqual(waypoints.movement_basis_path("RIFT-STATION"), self.root / "custom folder")

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
