"""Windows PowerShell 5.1 startup contract, with no real guest/startup mutation."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/guest_receiver_startup.ps1'


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell and per-user shortcut contract')
class GuestStartupTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', *map(str, args)], cwd=ROOT, capture_output=True, text=True, timeout=45)

    def test_disposable_install_launch_decision_and_removal_contract(self):
        result = self.invoke('-File', ROOT / 'tests/guest_receiver_startup_contract.ps1', '-Source', SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        record = json.loads(result.stdout)
        self.assertTrue(record['passed'])
        self.assertGreaterEqual(record['checks'], 38)
        self.assertFalse(record['realStartupChanged'])
        self.assertFalse(record['receiverExecuted'])

    def test_wrong_machine_is_refused_before_file_or_shortcut_operations(self):
        result = self.invoke('-File', SOURCE, '-Mode', 'Install', '-ExpectedMachineName', 'IMPOSSIBLE:VM')
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['reason'], 'wrong-guest-machine')

    def test_relative_manifest_is_rejected_without_launch(self):
        result = self.invoke('-File', SOURCE, '-Mode', 'Run', '-Manifest', 'not-absolute.json', '-WaitSeconds', '0')
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        row = json.loads(result.stdout)
        self.assertEqual(row['reason'], 'absolute-manifest-required')
        self.assertFalse(row['connectionVerified'])


if __name__ == '__main__':
    unittest.main()
