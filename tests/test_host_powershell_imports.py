"""Host-only Windows PowerShell module bootstrap regression, no Scheduler calls."""
import os
from pathlib import Path
import subprocess
import unittest

from scripts.launch_live_reader import HOST_POWERSHELL_IMPORTS

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell required")
class HostModuleImportsTests(unittest.TestCase):
    def run_windows_powershell(self, command):
        exe = Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        prefix = "$env:PSModulePath='C:\\rr2-no-such-modules';$PSModuleAutoloadingPreference='None';"
        return subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-Command", prefix + command],
                              capture_output=True, text=True, timeout=20, check=True)

    def test_receiver_host_query_bootstraps_with_invalid_module_path(self):
        result = self.run_windows_powershell(
            HOST_POWERSHELL_IMPORTS +
            "function Get-CimInstance {param($ClassName,$Filter) [pscustomobject]@{ProcessId=123;CommandLine='receiver'}};"
            "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=123';"
            "[pscustomobject]@{pid=$p.ProcessId;receiver=[bool]($p.CommandLine -match 'receiver')}|ConvertTo-Json -Compress")
        import json
        self.assertEqual(json.loads(result.stdout), {"pid": 123, "receiver": True})

    def test_manager_and_legacy_import_their_inbox_modules(self):
        for name in ("Manage-RR2HelperTask.ps1", "Verify-RR2LegacyHelperTask.ps1"):
            source = (ROOT / "scripts" / name).read_text()
            start = source.index("$ErrorActionPreference = 'Stop'")
            end = source.index("}\n", source.index("foreach ($module", start)) + 2
            prefix = source[start:end]
            result = self.run_windows_powershell(prefix +
                ";@(Get-Command Get-FileHash,Get-Item,Get-CimInstance).Count")
            self.assertEqual(result.stdout.strip(), "3", name)
