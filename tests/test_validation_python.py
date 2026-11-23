"""Exercise Windows validation interpreter discovery with local test interpreters."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
RESOLVE = """
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. $env:RR2_VALIDATION_TEST_RESOLVER
try {
    Resolve-ValidationPython -RepositoryRoot $env:RR2_VALIDATION_TEST_REPO `
        -Python $env:RR2_VALIDATION_TEST_OVERRIDE
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
"""


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell 7 validation")
class ValidationPythonTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="rr2-validation-python-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.repository = self.folder / "checkout with spaces"
        scripts = self.repository / "scripts"
        scripts.mkdir(parents=True)
        for name in ("check_validation_python.py", "check_lua_runtime.py"):
            (scripts / name).write_text("pass\n", encoding="ascii")

    def python_stub(self, name, *, fail_lua=False):
        directory = self.folder / name
        directory.mkdir()
        stub = directory / "python.cmd"
        lua_exit = "echo Lua 5.1 unavailable& exit /b 1" if fail_lua else "exit /b 0"
        stub.write_text(
            '@echo off\nif "%~1" neq "-B" exit /b 100\n'
            'if "%~nx2" == "check_validation_python.py" exit /b 0\n'
            f'if "%~nx2" == "check_lua_runtime.py" ({lua_exit})\nexit /b 101\n',
            encoding="ascii",
        )
        return stub

    def resolve(self, tools, *, override="", shared_python=""):
        environment = dict(os.environ)
        environment.update(
            PATH=os.pathsep.join(str(tool.parent) for tool in tools),
            RR2_VALIDATION_TEST_RESOLVER=str(ROOT / "scripts/resolve-validation-python.ps1"),
            RR2_VALIDATION_TEST_REPO=str(self.repository),
            RR2_VALIDATION_TEST_OVERRIDE=str(override),
            RR2_VALIDATION_TEST_PYTHON=sys.executable,
            RIFTREADER2_PYTHON=str(shared_python),
        )
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", RESOLVE],
                              cwd=self.folder, env=environment, capture_output=True,
                              text=True, timeout=30)

    def test_finds_a_later_python_when_the_first_lacks_lua(self):
        wrong = self.python_stub("first Python", fail_lua=True)
        ready = self.python_stub("working Python")
        result = self.resolve([wrong, ready])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), ready)

    def test_explicit_override_reports_its_own_failure(self):
        wrong = self.python_stub("explicit Python", fail_lua=True)
        ready = self.python_stub("automatic Python")
        result = self.resolve([ready], override=wrong, shared_python=ready)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Configured Python", result.stderr)
        self.assertIn("Lua 5.1 unavailable", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_finds_shared_python_outside_path(self):
        shared = self.python_stub("shared Python")
        ready = self.python_stub("working PATH Python")
        result = self.resolve([ready], shared_python=shared)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), shared)

    def test_skips_shared_python_without_validation_dependencies(self):
        shared = self.python_stub("shared Python without Lua", fail_lua=True)
        ready = self.python_stub("working PATH Python")
        result = self.resolve([ready], shared_python=shared)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), ready)

    def test_checkout_venv_precedes_shared_python_and_path(self):
        environment = self.repository / ".venv"
        venv.EnvBuilder(with_pip=False).create(environment)
        shared = self.python_stub("shared Python")
        result = self.resolve([self.python_stub("working PATH Python")], shared_python=shared)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), environment / "Scripts" / "python.exe")

    def test_launcher_lists_installed_python_without_running_install_mode(self):
        launcher = self.folder / "launcher only" / "py.cmd"
        launcher.parent.mkdir()
        launcher.write_text(
            '@echo off\nif "%~1" neq "-0p" exit /b 100\n'
            'echo  -V:3.14 *        %RR2_VALIDATION_TEST_PYTHON%\n', encoding="ascii",
        )
        # The launcher lists an executable whose directory is absent from PATH.
        result = self.resolve([launcher])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), Path(sys.executable))
