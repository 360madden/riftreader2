import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.prepare_guest_agent import prepare


class GuestAgentLauncherTests(unittest.TestCase):
    def test_bundle_has_short_entrypoints_and_pinned_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); exe = root / 'fake.exe'; exe.write_bytes(b'offline fixture only')
            bundle = root / 'bundle'
            result = prepare(exe, bundle, r'C:\RIFT_TRANSFER\RiftReader2Control\managed')
            with zipfile.ZipFile(bundle / 'agent.zip') as archive:
                self.assertEqual(json.loads(archive.read('current.json')), result['release'])
                self.assertIn(result['launcherSha256'], archive.read('Launch-Agent.cmd').decode())
                self.assertIn('-InstallStartup', archive.read('Install-Startup.cmd').decode())
                self.assertNotIn('ExecutionPolicy', archive.read('Launch-Agent.cmd').decode())
            self.assertEqual(hashlib.sha256((bundle / 'agent.zip').read_bytes()).hexdigest().upper(), result['archiveSha256'])

    def test_preflight_rejects_changed_binary_without_starting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); exe = root / 'fake.exe'; exe.write_bytes(b'never execute')
            bundle = root / 'bundle'
            result = prepare(exe, bundle, r'C:\RIFT_TRANSFER\RiftReader2Control\managed')
            installed = root / 'installed'
            with zipfile.ZipFile(bundle / 'agent.zip') as archive:
                archive.extractall(installed)
            script = Path(__file__).parents[1] / 'scripts/Start-GuestAgentLauncher.ps1'
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            command = ['powershell.exe', '-NoProfile', '-Command',
                       '& ([scriptblock]::Create([IO.File]::ReadAllText(' + quote(script) +
                       '))) -Root ' + quote(installed) + ' -ValidateOnly']
            success = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(success.returncode, 0, success.stderr)
            target = installed / 'releases' / result['release']['release'] / 'RiftReader2.Live.exe'
            target.write_bytes(b'changed')
            failed = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('release-hash-mismatch', failed.stderr)
            self.assertFalse((installed / 'launcher-state.json').exists())

    def test_guest_root_cannot_inject_launcher_command(self):
        with self.assertRaises(ValueError):
            prepare(Path('unused'), Path('unused'), "C:\\bad';whoami")

    def test_atomic_record_replacement_in_windows_powershell(self):
        source = (Path(__file__).parents[1] / 'scripts/Start-GuestAgentLauncher.ps1').read_text()
        function = source[source.index('function Write-Record'):source.index('function Read-Record')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            quote = "'" + str(path).replace("'", "''") + "'"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                "$ErrorActionPreference='Stop';" + function +
                ';Write-Record ' + quote + ' @{state="starting"};Write-Record ' + quote +
                ' @{state="running"}'], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(path.read_text()), {'state': 'running'})
            self.assertEqual(list(Path(directory).iterdir()), [path])
