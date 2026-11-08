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
                result = launcher.run('unused-config', output, None, 'restart')
            self.assertEqual(guest.run.call_args.args[-1],
                             r'C:\RIFT_TRANSFER\RiftReader2Control\managed\request-' + 'd' * 32 + '.tmp')
            self.assertFalse(result['success'])
            self.assertEqual('failed', queue.finish.call_args.args[2])
            self.assertEqual('failed', json.loads(
                (output / 'maintenance.json').read_text())['operationStatus'])

    def test_maintenance_fence_rejects_pending_after_first_status_page(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            resource = {'name': 'vm:test', 'epoch': 'epoch', 'blocked': False,
                        'holder': None}
            queue = MagicMock()
            queue.status.side_effect = [
                {'resources': [resource], 'requests': [{'state': 'succeeded'}],
                 'next_sequence': 100},
                {'resources': [resource], 'requests': [{'state': 'queued'}],
                 'next_sequence': None},
            ]
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='e' * 32))):
                with self.assertRaisesRegex(ValueError, 'Control queue occupied'):
                    with launcher.maintenance_lease(guard, Path(directory)):
                        self.fail('Failed admission must not yield control')
            queue.status.assert_any_call(after_sequence=100)
            queue.submit.assert_not_called()
            queue.dispatch.assert_not_called()

    def test_maintenance_foreign_grant_cancels_only_its_own_request(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            queue.status.return_value = {
                'resources': [{'name': 'vm:test', 'epoch': 'epoch',
                               'blocked': False, 'holder': None}],
                'requests': [], 'next_sequence': None,
            }
            queue.dispatch.return_value = {'request_id': 'foreign', 'token': 'foreign-token'}
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='f' * 32))):
                with self.assertRaisesRegex(ValueError, 'Maintenance grant unavailable'):
                    with launcher.maintenance_lease(guard, Path(directory)):
                        self.fail('Foreign grant must not be accepted')
            queue.cancel.assert_called_once_with(
                'agent-maintenance-' + 'f' * 12, 'agent-launcher')
            queue.finish.assert_not_called()

    def test_maintenance_grant_is_fenced_until_work_begins(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            held = {'value': False}
            fence = MagicMock()
            fence.__enter__.side_effect = lambda: held.__setitem__('value', True)
            fence.__exit__.side_effect = lambda *_: held.__setitem__('value', False)
            queue.dispatch_fence.return_value = fence

            def status(*, after_sequence=0):
                self.assertTrue(held['value'])
                return {
                    'resources': [{'name': 'vm:test', 'epoch': 'epoch',
                                   'blocked': False, 'holder': None}],
                    'requests': [], 'next_sequence': None,
                }

            def submit(*args, **kwargs):
                self.assertTrue(held['value'])

            def dispatch(*, request_id):
                self.assertTrue(held['value'])
                self.assertEqual(request_id, 'agent-maintenance-' + 'g' * 12)
                return {'request_id': 'agent-maintenance-' + 'g' * 12,
                        'token': 'mock-token'}

            queue.status.side_effect = status
            queue.submit.side_effect = submit
            queue.dispatch.side_effect = dispatch
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='g' * 32))):
                with launcher.maintenance_lease(guard, Path(directory)):
                    self.assertFalse(held['value'])
            self.assertFalse(held['value'])
            self.assertEqual('succeeded', queue.finish.call_args.args[2])

    def test_managed_guard_uses_strict_plan_and_no_legacy_configuration(self):
        host = MagicMock()
        host.plan = {'lab': 'lab2', 'resource': 'vm:rift-lab-2', 'vmIdentity': {'pid': 2}}
        host.config = SimpleNamespace(expected_machine_name='RIFT-LAB-2',
                                      vmx=Path('lab2.vmx'), vmrun=Path('vmrun.exe'), vnc_port=5962)
        with (patch.object(launcher, 'write_managed_host_plan', return_value=Path('plan.json')) as writer,
              patch.object(launcher, 'ManagedPinnedHost', return_value=host) as pinned,
              patch.object(launcher.w, 'validate_config'),
              patch.object(launcher.w, 'read_config') as legacy):
            guard = launcher.ManagedMaintenanceGuard('lab2', Path('output'))
            self.assertEqual(guard.check(), {'pid': 2})
            guard.status()
        writer.assert_called_once_with('lab2', Path('output'), require_foreground=False)
        pinned.assert_called_once_with(Path('plan.json'))
        host.check.assert_called_once_with()
        host.status.assert_called_once_with(require_armed=False, require_foreground=False)
        legacy.assert_not_called()

    def test_managed_guard_refuses_wrong_lab_or_proof_failures(self):
        for reason in ('managed-runtime-changed', 'managed-process-identity-uncertain',
                       'managed-task-ownership-refused'):
            with self.subTest(reason=reason), \
                    patch.object(launcher, 'write_managed_host_plan', side_effect=ValueError(reason)), \
                    patch.object(launcher.w, 'HostGuard') as legacy:
                with self.assertRaisesRegex(ValueError, reason):
                    launcher.ManagedMaintenanceGuard('lab2', Path('output'))
                legacy.assert_not_called()
        with patch.object(launcher, 'write_managed_host_plan') as writer:
            with self.assertRaisesRegex(ValueError, 'Invalid managed lab'):
                launcher.ManagedMaintenanceGuard('all', Path('output'))
            writer.assert_not_called()
        with (patch.object(launcher, 'write_managed_host_plan'),
              patch.object(launcher, 'ManagedPinnedHost') as pinned):
            pinned.return_value.plan = {'lab': 'lab1', 'resource': 'vm:rift-lab-1'}
            with self.assertRaisesRegex(ValueError, 'lab mismatch'):
                launcher.ManagedMaintenanceGuard('lab2', Path('output'))

    def test_managed_check_propagates_changed_runtime_or_process(self):
        guard = launcher.ManagedMaintenanceGuard.__new__(launcher.ManagedMaintenanceGuard)
        guard.host = MagicMock()
        guard.plan = {'vmIdentity': {'pid': 2}}
        for reason in ('managed host runtime changed', 'managed host process epoch changed'):
            guard.host.check.side_effect = RuntimeError(reason)
            with self.assertRaisesRegex(RuntimeError, reason):
                guard.check()

    def test_managed_post_restart_requires_new_guest_and_same_host(self):
        guard = launcher.ManagedMaintenanceGuard.__new__(launcher.ManagedMaintenanceGuard)
        guard.host = MagicMock()
        guard.plan = {'hostInstance': 'host-1', 'connection': 1,
                      'guestInstance': 'guest-1', 'supervisorEpoch': 'old-epoch'}
        valid = {
            'host': {'instanceId': 'guest-2', 'consoleReservation': {'closing': False},
                     'coordination': {'hostInstance': 'host-1', 'connection': 2,
                                      'shutdownRequested': False, 'errorCode': None,
                                      'supervisor': {'state': 'running', 'threadAlive': True,
                                                     'initialCleanupVerified': True,
                                                     'terminationPending': False, 'errorCode': None,
                                                     'epoch': 'new-epoch'}}},
            'guest': {'instanceId': 'guest-2'},
        }
        with patch.object(launcher.PinnedHost, 'status', return_value=valid) as status:
            self.assertEqual(valid, guard.status_after_restart())
            status.assert_called_once_with(guard.host, require_armed=False, require_foreground=False)
        for field, changed in (('hostInstance', 'other-host'), ('connection', 1),
                               ('shutdownRequested', True)):
            value = json.loads(json.dumps(valid))
            value['host']['coordination'][field] = changed
            with self.subTest(field=field), patch.object(launcher.PinnedHost, 'status', return_value=value):
                with self.assertRaisesRegex(ValueError, 'restart or supervisor'):
                    guard.status_after_restart()
        for instance in ('guest-1', '', None):
            value = json.loads(json.dumps(valid))
            value['guest']['instanceId'] = value['host']['instanceId'] = instance
            with self.subTest(instance=instance), patch.object(launcher.PinnedHost, 'status', return_value=value):
                with self.assertRaisesRegex(ValueError, 'restart or supervisor'):
                    guard.status_after_restart()

    def test_managed_post_restart_preserves_common_exact_target_checks(self):
        guard = launcher.ManagedMaintenanceGuard.__new__(launcher.ManagedMaintenanceGuard)
        guard.host = MagicMock()
        with patch.object(launcher.PinnedHost, 'status', side_effect=RuntimeError('game target changed')):
            with self.assertRaisesRegex(RuntimeError, 'game target changed'):
                guard.status_after_restart()

    def test_managed_run_never_loads_legacy_profile_and_checks_restart(self):
        from scripts.ensure_guest_agent import GUEST_ROOT
        self.check_managed_update(None, GUEST_ROOT)

    def test_managed_update_uses_explicit_guest_root(self):
        self.check_managed_update(r'C:\custom\managed', r'C:\custom\managed')

    def test_managed_native_lease_opt_in_accepts_exact_integer_one(self):
        self.check_managed_update(None, None, require_native_read_lease=True,
                                  capabilities={'nativeReadLeaseVersion': 1})
        self.check_managed_update(None, None, require_native_read_lease=True,
                                  capabilities={'nativeReadLeaseVersion': 1}, operation='restart')

    def test_managed_native_lease_opt_in_rejects_missing_or_invalid_advertisement(self):
        for capabilities in ({}, *({'nativeReadLeaseVersion': value}
                                    for value in (None, False, True, '1', 1.0, 0, -1, 2))):
            with self.subTest(capabilities=capabilities):
                self.check_managed_update(None, None, require_native_read_lease=True,
                                          capabilities=capabilities, rejection=True)

    def test_native_lease_opt_in_preserves_exact_graceful_capability(self):
        self.check_managed_update(None, None, require_native_read_lease=True,
                                  capabilities={'nativeReadLeaseVersion': 1,
                                                'gracefulShutdownVersion': True}, rejection=True)

    def test_native_lease_opt_in_needs_managed_target_before_any_operations(self):
        for lab, requirement in ((None, True), ('all', True), ('lab2', 1),
                                 ('lab2', 'true'), ('lab2', None)):
            with self.subTest(lab=lab, requirement=requirement), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'must-not-exist'
                with (patch.object(launcher, 'GuestSession') as session,
                      patch.object(launcher, 'ManagedMaintenanceGuard') as managed,
                      patch.object(launcher.w, 'HostGuard') as legacy):
                    with self.assertRaises(ValueError):
                        launcher.run(None, output, None, 'restart', managed_lab=lab,
                                     require_native_read_lease=requirement)
                self.assertFalse(output.exists())
                session.assert_not_called()
                managed.assert_not_called()
                legacy.assert_not_called()

    def test_native_lease_cli_flag_is_available_without_guest_access(self):
        result = subprocess.run([launcher.sys.executable, str(Path(launcher.__file__)), '--help'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--require-native-read-lease', result.stdout)

    def check_managed_update(self, guest_root, expected_root, *, require_native_read_lease=False,
                             capabilities=None, rejection=False, operation='update'):
        if expected_root is None:
            from scripts.ensure_guest_agent import GUEST_ROOT
            expected_root = GUEST_ROOT
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'managed-run'
            guard = MagicMock()
            guard.plan = {'database': 'queue.json', 'resource': 'vm:rift-lab-2'}
            guard.vmrun = Path('vmrun.exe')
            guard.status.return_value = {'guest': {'gracefulShutdownVersion': 1}}
            guard.status_after_restart.return_value = {
                'guest': {'gracefulShutdownVersion': 1, **(capabilities or {})}}
            guard.client.request.return_value = {'status': 'stopped'}
            queue = MagicMock()
            queue.status.return_value = {
                'resources': [{'name': 'vm:rift-lab-2', 'epoch': 'epoch',
                               'blocked': False, 'holder': None}], 'requests': []}
            queue.dispatch.return_value = {
                'request_id': 'agent-maintenance-' + 'a' * 12, 'token': 'mock-token'}
            guest = MagicMock()

            def copy_result(_, destination):
                destination.write_text(json.dumps(
                    {'id': 'a' * 32, 'success': True} if destination.name == 'result.json' else {}))

            guest.copy_from_guest.side_effect = copy_result
            with (patch.object(launcher, 'ManagedMaintenanceGuard', return_value=guard) as managed,
                  patch.object(launcher.w, 'read_config') as legacy,
                  patch.object(launcher.w, 'HostGuard') as legacy_guard,
                  patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher, 'GuestSession') as session,
                  patch.object(launcher.uuid, 'uuid4', return_value=SimpleNamespace(hex='a' * 32)),
                  patch.object(launcher.time, 'monotonic', side_effect=[0, 31]),
                  patch.object(launcher.time, 'sleep') as sleep):
                session.return_value.__enter__.return_value = guest
                def run():
                    return launcher.run(None, output, guest_root, operation,
                        {'release': 'agent-test', 'sha256': 'A' * 64} if operation == 'update' else None,
                        managed_lab='lab2', require_native_read_lease=require_native_read_lease)
                if rejection:
                    with self.assertRaisesRegex(RuntimeError,
                            'maintenance status uncertain; new release may be active; '
                            'no automatic retry or rollback') as caught:
                        run()
                    self.assertIsInstance(caught.exception.__cause__, ValueError)
                    self.assertIn('capability', str(caught.exception.__cause__))
                    self.assertEqual('failed', queue.finish.call_args.args[2])
                    self.assertEqual('failed', json.loads(
                        (output / 'maintenance.json').read_text())['operationStatus'])
                    self.assertFalse((output / 'after.json').exists())
                    # Guest operation receipt is retained, not rewritten as a rollback.
                    self.assertTrue(json.loads((output / 'result.json').read_text())['success'])
                    guest.run.assert_called_once()
                    guest.powershell.assert_called_once()
                    guard.status_after_restart.assert_called_once()
                    sleep.assert_not_called()
                    return
                result = run()
            self.assertTrue(result['success'])
            self.assertEqual(guest.run.call_args.args[-1], expected_root + '\\request-' + 'a' * 32 + '.tmp')
            managed.assert_called_once_with('lab2', output)
            legacy.assert_not_called()
            legacy_guard.assert_not_called()
            self.assertEqual(guard.status.call_count, 2)
            guard.status_after_restart.assert_called_once_with()
            queue.dispatch.assert_called_once_with(request_id='agent-maintenance-' + 'a' * 12)
            self.assertTrue((output / 'stopped.json').is_file())
            self.assertTrue((output / 'after.json').is_file())

    def test_maintenance_thread_start_failure_releases_failed_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = SimpleNamespace(plan={'database': 'queue.json', 'resource': 'vm:test'})
            queue = MagicMock()
            queue.status.return_value = {
                'resources': [{'name': 'vm:test', 'epoch': 'epoch',
                               'blocked': False, 'holder': None}],
                'requests': [], 'next_sequence': None,
            }
            queue.dispatch.return_value = {
                'request_id': 'agent-maintenance-' + 'h' * 12, 'token': 'mock-token',
            }
            with (patch.object(launcher.w, 'AccessQueue', return_value=queue),
                  patch.object(launcher.uuid, 'uuid4',
                               return_value=SimpleNamespace(hex='h' * 32)),
                  patch.object(launcher.threading.Thread, 'start',
                               side_effect=RuntimeError('thread unavailable'))):
                with self.assertRaisesRegex(RuntimeError, 'thread unavailable'):
                    with launcher.maintenance_lease(guard, Path(directory)):
                        self.fail('Failed heartbeat start must not yield')
            self.assertEqual('failed', queue.finish.call_args.args[2])
            self.assertEqual('failed', json.loads(
                (Path(directory) / 'maintenance.json').read_text())['operationStatus'])

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
