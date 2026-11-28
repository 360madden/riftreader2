"""Offline Windows SDK discovery tests using harmless version-reporting stubs."""

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
PIN = "99.9.842"
RESOLVE = """
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. $env:RR2_VALIDATION_TEST_RESOLVER
try {
    $resolverArgs = @{
        RepositoryRoot = $env:RR2_VALIDATION_TEST_REPO
        PinnedSdk = $env:RR2_VALIDATION_TEST_PIN
    }
    if (Test-Path Env:RR2_VALIDATION_TEST_OVERRIDE) {
        $resolverArgs.DotNet = $env:RR2_VALIDATION_TEST_OVERRIDE
    }
    Resolve-ValidationDotNet @resolverArgs
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
"""


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell 7 validation")
class ValidationDotNetTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="rr2-validation-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.repository = self.folder / "checkout with spaces"
        self.repository.mkdir()

    def dotnet(self, name, *, version=PIN, code=0):
        directory = self.folder / name
        directory.mkdir(parents=True)
        path = directory / "dotnet.cmd"
        path.write_text(
            '@echo off\nif not "%~1"=="--version" exit /b 100\n'
            'if /i not "%CD%"=="%RR2_VALIDATION_TEST_REPO%" exit /b 101\n'
            f'echo {version}\nexit /b {code}\n', encoding="ascii",
        )
        return path

    def resolve(self, path_hosts, *, override=None, configured=None):
        environment = dict(os.environ)
        for key in ("DOTNET_ROOT", "DOTNET_ROOT_X64", "RIFTREADER2_DOTNET", "RR2_VALIDATION_TEST_OVERRIDE"):
            environment.pop(key, None)
        environment.update(
            PATH=os.pathsep.join(str(path.parent) for path in path_hosts),
            RR2_VALIDATION_TEST_RESOLVER=str(ROOT / "scripts/resolve-validation-dotnet.ps1"),
            RR2_VALIDATION_TEST_REPO=str(self.repository),
            RR2_VALIDATION_TEST_PIN=PIN,
        )
        if override is not None:
            environment["RR2_VALIDATION_TEST_OVERRIDE"] = str(override)
        if configured is not None:
            environment["RIFTREADER2_DOTNET"] = str(configured)
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", RESOLVE],
                              cwd=self.folder, env=environment, capture_output=True,
                              text=True, timeout=30)

    def test_selects_later_path_install_after_native_failure(self):
        wrong = self.dotnet("first SDK", code=1)
        pinned = self.dotnet("second SDK")
        result = self.resolve([wrong, pinned])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), pinned)

    def test_selects_pinned_sibling_of_version_named_host(self):
        wrong = self.dotnet("installations/99.9.999", version="99.9.999")
        pinned = self.dotnet(f"installations/{PIN}")
        result = self.resolve([wrong])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), pinned)

    def test_explicit_wrong_version_refuses_automatic_fallback(self):
        wrong = self.dotnet("wrong SDK", version="99.9.999")
        pinned = self.dotnet("pinned SDK")
        result = self.resolve([pinned], override=wrong)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"does not resolve SDK {PIN}", result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_explicit_missing_path_refuses_automatic_fallback(self):
        pinned = self.dotnet("pinned SDK")
        result = self.resolve([pinned], override=self.folder / "missing dotnet.exe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Configured .NET executable was not found", result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_configured_sdk_resolves_outside_path(self):
        pinned = self.dotnet("pinned SDK")
        result = self.resolve([], configured=pinned)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), pinned)

    def test_wrong_configured_sdk_refuses_a_usable_sdk_on_path(self):
        wrong = self.dotnet("wrong SDK", version="99.9.999")
        pinned = self.dotnet("pinned SDK")
        result = self.resolve([pinned], configured=wrong)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(f"does not resolve SDK {PIN}", result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_explicit_sdk_overrides_the_configured_sdk(self):
        pinned = self.dotnet("pinned SDK")
        result = self.resolve([], override=pinned, configured=self.folder / "missing executable.exe")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), pinned)
