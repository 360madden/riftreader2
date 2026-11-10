"""Offline PowerShell contract for disjoint read-only readers and managed control agents."""
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "Ensure-GuestAgentTask.ps1"


def helper_source():
    code = SOURCE.read_text(encoding="utf-8-sig")
    start = code.index("function Test-Rr2ManagedAgentProcess(")
    end = code.index("\ntry {", start)
    return code[start:end], code


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
class GuestAgentProcessGuardTests(unittest.TestCase):
    def _run(self, statement: str):
        helper, _ = helper_source()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference='Stop';" + helper + "\n" + statement],
            capture_output=True, text=True, timeout=30)
        return result

    def test_reader_and_managed_agent_are_distinct(self):
        root = r"C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029"
        statements = (
            # Verified/hashed guest-local read-only reader should not block recovery.
            r'$root="' + root + r'";'
            r'$reader="C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid\lab2-123\RiftReader2.Live.exe";'
            r'$managed="C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029\releases\v1\RiftReader2.Live.exe";'
            r'$nearby="C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029\releases-other\v1\RiftReader2.Live.exe";'
            r'$results=@('
            r'(Test-Rr2ManagedAgentProcess $reader ($reader+" serve") $root),'
            r'(Test-Rr2ManagedAgentProcess $managed ($managed+" serve") $root),'
            r'(Test-Rr2ManagedAgentProcess $reader ($reader+" control-agent --config x") $root),'
            r'(Test-Rr2ManagedAgentProcess $nearby ($nearby+" serve") $root)'
            r');$results|ForEach-Object {Write-Output $_}'
        )
        run = self._run(statements)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip().splitlines(),
                         ["False", "True", "True", "False"])

    def test_unknown_process_identity_is_blocked(self):
        root = r"C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029"
        run = self._run(
            '$null = Test-Rr2ManagedAgentProcess $null "control-agent" "'
            + root + '";')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("agent-process-identity-unavailable", run.stderr)

    def test_task_guard_disallows_blanket_reader_process_count(self):
        _, source = helper_source()
        self.assertIn('Get-CimInstance Win32_Process -Filter "Name=\'RiftReader2.Live.exe\'"', source)
        self.assertIn("$process.ExecutablePath $process.CommandLine $Root", source)
        self.assertIn("'agent-already-present'", source)
        self.assertIn("'agent-process-identity-unavailable'", source)
        self.assertNotIn("@(Get-Process -Name RiftReader2.Live", source)


if __name__ == "__main__":
    unittest.main()
