"""Run the real batch launchers with a temporary checkout and harmless Python entry points."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = """
import json, os, sys
print(json.dumps({'executable': sys.executable, 'arguments': sys.argv[1:], 'cwd': os.getcwd()}))
raise SystemExit(17)
"""


@unittest.skipUnless(os.name == "nt", "Windows batch launchers")
class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="rr2-launch-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "cloned checkout"
        (self.root / "scripts").mkdir(parents=True)
        for path in ("Waypoints.cmd", "rr2-waypoints.cmd", "rr2-check-dependencies.cmd", "rr2-observe.cmd",
                     "rr2-setup-python.cmd",
                     "scripts/resolve-waypoints-python.cmd"):
            shutil.copyfile(ROOT / path, self.root / path)
        for path in ("launch_physical_waypoints.py", "waypoints_cli.py", "check_physical_dependencies.py",
                     "observe_target.py", "setup_physical_python.py"):
            (self.root / "scripts" / path).write_text(ENTRY_POINT, encoding="utf-8")

    def run_launcher(self, launcher, args=(), *, override=None, environment=None):
        environ = os.environ.copy()
        environ.pop("RIFTREADER2_PYTHON", None)
        if override is not None:
            environ["RIFTREADER2_PYTHON"] = str(override)
        if environment is not None:
            environ.update(environment)
        cmd = environ["COMSPEC"]
        arguments = subprocess.list2cmdline(args)
        command = f'"{cmd}" /d /s /c ""{self.root / launcher}" {arguments}"'
        return subprocess.run(command, cwd=self.root.parent, env=environ, capture_output=True,
                              text=True, timeout=15)

    def test_launchers_preserve_arguments_and_explicit_interpreter(self):
        args = ["--route", "Example route with spaces.json", "--basis", "Calibration folder"]
        for launcher, prefix in (("rr2-waypoints.cmd", []), ("Waypoints.cmd", ["--detach-window"]),
                                 ("rr2-check-dependencies.cmd", []), ("rr2-observe.cmd", [])):
            with self.subTest(launcher=launcher):
                result = self.run_launcher(launcher, args, override=sys.executable)
                self.assertEqual(result.returncode, 17, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(Path(output["executable"]), Path(sys.executable))
                self.assertEqual(output["arguments"], prefix + args)
                self.assertEqual(Path(output["cwd"]), self.root.parent)

    def test_checkout_uses_its_virtual_environment_by_default(self):
        environment = self.root / ".venv"
        venv.create(environment)
        result = self.run_launcher("rr2-waypoints.cmd")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["executable"]),
                         environment / "Scripts" / "python.exe")

    def test_default_setup_is_selected_after_successful_completion(self):
        setup = self.root / ".local" / "physical-python"
        prepared = setup / "core"
        fallback = self.root / ".venv"
        for directory in (prepared, fallback):
            venv.create(directory)
        for expected in (fallback, prepared):
            if expected == prepared:
                (setup / ".ready").touch()
            result = self.run_launcher("Waypoints.cmd", ["--check"])
            self.assertEqual(result.returncode, 17, result.stderr)
            self.assertEqual(Path(json.loads(result.stdout)["executable"]), expected / "Scripts" / "python.exe")
        override = self.run_launcher("Waypoints.cmd", ["--check"], override=sys.executable)
        self.assertEqual(Path(json.loads(override.stdout)["executable"]), Path(sys.executable))

        registered = self.root / ".local" / "physical-python-link"
        venv.create(registered / "core")
        (registered / ".ready").touch()
        for launcher, args in (("Waypoints.cmd", ["--check"]),
                               ("rr2-observe.cmd", ["--target", "physical", "--check-dependencies"])):
            with self.subTest(launcher=launcher):
                result = self.run_launcher(launcher, args)
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(Path(json.loads(result.stdout)["executable"]), registered / "core/Scripts/python.exe")

    def test_invalid_explicit_interpreter_reports_failure(self):
        result = self.run_launcher("Waypoints.cmd", override=self.root / "missing.exe")
        self.assertEqual(result.returncode, 2)
        self.assertIn("RIFTREADER2_PYTHON", result.stderr)
        self.assertEqual(result.stdout, "")

    @staticmethod
    def make_broken_python(environment):
        venv.create(environment)
        (environment / "pyvenv.cfg").write_text(
            f"home = {environment / 'missing Python installation'}\n", encoding="utf-8")
        return environment / "Scripts/python.exe"

    def test_launchers_skip_copied_registration_with_missing_base_python(self):
        registered = self.root / ".local/physical-python-link"
        self.make_broken_python(registered / "core")
        (registered / ".ready").touch()
        prepared = self.root / ".local/physical-python"
        venv.create(prepared / "core")
        (prepared / ".ready").touch()
        for launcher in ("rr2-setup-python.cmd", "rr2-check-dependencies.cmd", "rr2-observe.cmd",
                         "rr2-waypoints.cmd", "Waypoints.cmd"):
            with self.subTest(launcher=launcher):
                result = self.run_launcher(launcher, ["--help"])
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(Path(json.loads(result.stdout)["executable"]),
                                 prepared / "core/Scripts/python.exe")

    def test_system_discovery_skips_broken_virtual_environment_on_path(self):
        broken = self.make_broken_python(self.root / "broken Python")
        installed = self.root / "existing Python"
        venv.create(installed)
        executable = installed / "Scripts/python.exe"
        path = os.pathsep.join(map(str, (broken.parent, executable.parent)))
        result = self.run_launcher("rr2-setup-python.cmd", environment={"PATH": path})
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["executable"]), executable)

        explicit = self.run_launcher("rr2-setup-python.cmd", override=broken, environment={"PATH": path})
        self.assertNotEqual(explicit.returncode, 17)
        self.assertEqual(explicit.stdout, "")

    def test_skips_store_alias_and_finds_python_later_on_path(self):
        local_app_data = self.root / "local data"
        alias = local_app_data / "Microsoft" / "WindowsApps"
        alias.mkdir(parents=True)
        (alias / "python.exe").touch()
        installed = self.root / "existing Python"
        venv.create(installed)
        executable = installed / "Scripts" / "python.exe"
        result = self.run_launcher("rr2-waypoints.cmd", environment={
            "LOCALAPPDATA": str(local_app_data),
            "PATH": os.pathsep.join(map(str, (alias, executable.parent))),
        })
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["executable"]), executable)

    def test_dependency_launcher_can_fall_back_to_windows_py(self):
        launcher = shutil.which("py.exe")
        if launcher is None:
            self.skipTest("Windows Python launcher is unavailable")
        launcher_dir = Path(launcher).parent
        if launcher_dir.name.casefold() != "windowsapps" and (launcher_dir / "python.exe").is_file():
            self.skipTest("Cannot isolate py.exe from the installed python.exe")
        args = ["--expected-host", "LOCAL-PC", "--workflow", "prepared-maps"]
        result = self.run_launcher("rr2-check-dependencies.cmd", args, environment={"PATH": str(launcher_dir)})
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(json.loads(result.stdout)["arguments"], args)
