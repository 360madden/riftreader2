import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zipfile

from scripts import guest_agent_launcher as launcher
from scripts.prepare_guest_agent import prepare


class GuestAgentLauncherTests(unittest.TestCase):
    def test_maintenance_failure_never_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            queue.status.return_value = {'resources': [{'name': 'vm:test', 'epoch': 'epoch'}]}
            queue.dispatch.return_value = {'request_id': 'agent-maintenance-' + 'a' * 12,
                                           'token': 'mock-token'}
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4', return_value=SimpleNamespace(hex='a' * 32))):
                with self.assertRaisesRegex(RuntimeError, 'guest-copy-failed'):
                    with launcher.maintenance_lease(guard, output):
                        raise RuntimeError('guest-copy-failed')
            self.assertEqual('failed', queue.finish.call_args.args[2])
            self.assertIn('failed', queue.finish.call_args.args[3][0])
            record = json.loads((output / 'maintenance.json').read_text())
            self.assertEqual('failed', record['operationStatus'])
            self.assertEqual('released', record['outcome'])

    def test_maintenance_success_still_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            queue.status.return_value = {'resources': [{'name': 'vm:test', 'epoch': 'epoch'}]}
            queue.dispatch.return_value = {'request_id': 'agent-maintenance-' + 'b' * 12,
                                           'token': 'mock-token'}
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4', return_value=SimpleNamespace(hex='b' * 32))):
                with launcher.maintenance_lease(guard, output):
                    pass
            self.assertEqual('succeeded', queue.finish.call_args.args[2])
            self.assertEqual('succeeded', json.loads(
                (output / 'maintenance.json').read_text())['operationStatus'])

    def test_maintenance_reported_failure_records_failed_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            queue.status.return_value = {
                'resources': [{'name': 'vm:test', 'epoch': 'epoch'}],
                'requests': [],
            }
            queue.dispatch.return_value = {
                'request_id': 'agent-maintenance-' + 'c' * 12, 'token': 'mock-token',
            }
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='c' * 32))):
                with launcher.maintenance_lease(guard, output) as verdict:
                    verdict['succeeded'] = False
            self.assertEqual('failed', queue.finish.call_args.args[2])
            self.assertEqual('failed', json.loads(
                (output / 'maintenance.json').read_text())['operationStatus'])

    def test_run_guest_failure_retains_false_result_and_failed_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'launcher-run'
            guard = MagicMock()
            guard.plan = {'database': 'queue.json', 'resource': 'vm:test'}
            guard.status.return_value = {'guest': {'gracefulShutdownVersion': 1}}
            guard.client.request.return_value = {'status': 'stopped'}
            queue = MagicMock()
            queue.status.return_value = {
                'resources': [{'name': 'vm:test', 'epoch': 'epoch',
                               'blocked': False, 'holder': None}],
                'requests': [],
            }
            queue.dispatch.return_value = {
                'request_id': 'agent-maintenance-' + 'd' * 12, 'token': 'mock-token',
            }
            guest = MagicMock()

            def fake_copy(_, destination):
                if destination.name == 'result.json':
                    destination.write_text(json.dumps({'id': 'd' * 32, 'success': False}))
                else:
                    destination.write_text('{}')

            guest.copy_from_guest.side_effect = fake_copy
            with (patch.object(launcher.w, 'read_config',
                               return_value=({'vmrun': 'vmrun.exe'}, {}, None)),
                  patch.object(launcher.w, 'HostGuard', return_value=guard),
                  patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher, 'GuestSession') as session,
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='d' * 32))):
                session.return_value.__enter__.return_value = guest
                result = launcher.run(
                    'unused-config', output,
                    r'C:\RIFT_TRANSFER\RiftReader2Control\managed', 'restart')
            self.assertFalse(result['success'])
            self.assertEqual('failed', queue.finish.call_args.args[2])
            self.assertEqual('failed', json.loads(
                (output / 'maintenance.json').read_text())['operationStatus'])

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
