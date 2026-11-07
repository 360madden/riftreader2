import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from scripts import migrate_legacy_receiver as m


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / 'receipt.json'
        self.receipt.write_text('{}')
        self.registration_dir = self.root / 'registrations'
        registration = self.registration_dir / 'rr2-receiver-lab1' / 'registration.json'
        registration.parent.mkdir(parents=True)
        registration.write_bytes(b'{"schema":1}')
        self.old = {'pid': 123, 'processStartUtcTicks': 456, 'image': 'pythonw.exe'}
        self.new = {'pid': 987}
        self.snap = {'xml': '<Task/>', 'instances': [{'guid': '{id}', 'pid': 123}]}
        self.calls = []
        def backend(action, lab, **kwargs):
            self.calls.append(action)
            return self.snap if action == 'snapshot' else {}
        self.stack = __import__('contextlib').ExitStack()
        self.addCleanup(self.stack.close)
        for obj, name, val in [(m, 'ROOT', self.root), (m, 'LEGACY_REGISTRATIONS', self.registration_dir), (m, 'backend', backend),
                (m, 'receipt_file', lambda *a: self.receipt),
                (m.receiver, '_config', lambda lab: self.root / 'config'),
                (m.receiver, '_launch_lock', lambda lab: nullcontext()),
                (m.receiver, '_probe', lambda *a: self.old),
                (m.receiver, '_legacy_task_status', lambda *a: {}),
                (m.receiver, '_port_owners', lambda *a: []),
                (m.receiver, 'ensure', lambda lab: {'state': 'started', 'receiver': self.new}),
                (m.receiver, '_task_status', lambda lab, pid: {}),
                (m.receiver, '_matching_receipt', lambda *a: True)]:
            self.stack.enter_context(patch.object(obj, name, val))

    def test_success_preserves_backups_and_orders_mutations(self):
        result = m.migrate('lab1')
        self.assertEqual(['snapshot', 'stop', 'delete'], self.calls)
        folder = Path(result['backup'])
        self.assertEqual('<Task/>', (folder / 'legacy-task.xml').read_text(encoding='utf-8'))
        self.assertEqual('{}', (folder / 'process.json').read_text())
        self.assertEqual(b'{"schema":1}', (folder / 'registration.json').read_bytes())
        import hashlib
        self.assertEqual(hashlib.sha256(b'{"schema":1}').hexdigest().upper(),
                         (folder / 'registration.sha256').read_text().strip())

    def test_wrong_instance_never_stops(self):
        self.snap['instances'][0]['pid'] = 321
        with self.assertRaisesRegex(RuntimeError, 'instance-mismatch'):
            m.migrate('lab1')
        self.assertEqual(['snapshot'], self.calls)

    def test_port_collision_never_deletes(self):
        with patch.object(m.receiver, '_port_owners', return_value=[('0.0.0.0', 8)]):
            with self.assertRaisesRegex(RuntimeError, 'port-not-vacant'):
                m.migrate('lab1')
        self.assertEqual(['snapshot', 'stop'], self.calls)

    def test_stop_failure_never_deletes(self):
        def fail(action, lab, **kwargs):
            self.calls.append(action)
            if action == 'stop':
                raise RuntimeError('refused')
            return self.snap
        with patch.object(m, 'backend', fail):
            with self.assertRaisesRegex(RuntimeError, 'stop: refused'):
                m.migrate('lab1')
        self.assertEqual(['snapshot', 'stop'], self.calls)

    def test_reused_new_receiver_is_not_claimed_as_migrated(self):
        with patch.object(m.receiver, 'ensure', return_value={'state': 'reused', 'receiver': self.new}):
            with self.assertRaisesRegex(RuntimeError, 'not-started-by-migration'):
                m.migrate('lab1')


    def test_backend_guard_refusals_do_not_continue(self):
        for stage, reason, expected in (
                ('stop', 'process-start-changed', ['snapshot', 'stop']),
                ('stop', 'task-xml-changed', ['snapshot', 'stop']),
                ('stop', 'old-process-still-running', ['snapshot', 'stop']),
                ('stop', 'registration-changed', ['snapshot', 'stop']),
                ('delete', 'registration-changed', ['snapshot', 'stop', 'delete']),
                ('delete', 'task-xml-changed', ['snapshot', 'stop', 'delete'])):
            with self.subTest(stage=stage, reason=reason):
                self.calls.clear()
                def fail(action, lab, **kwargs):
                    self.calls.append(action)
                    if action == stage:
                        raise RuntimeError(reason)
                    return self.snap if action == 'snapshot' else {}
                with patch.object(m, 'backend', fail), patch.object(m.receiver, 'ensure') as ensure:
                    with self.assertRaisesRegex(RuntimeError, reason):
                        m.migrate('lab1')
                    ensure.assert_not_called()
                self.assertEqual(expected, self.calls)

    def test_registration_drift_is_refused_by_guard(self):
        def guard(action, lab, **kwargs):
            self.calls.append(action)
            if action == 'snapshot':
                return self.snap
            import hashlib
            current = (self.registration_dir / 'rr2-receiver-lab1' / 'registration.json').read_bytes()
            if hashlib.sha256(current).hexdigest().upper() != kwargs['RegistrationSha256']:
                raise RuntimeError('registration-changed')
            if action == 'stop':
                (self.registration_dir / 'rr2-receiver-lab1' / 'registration.json').write_bytes(b'changed')
            return {}
        with patch.object(m, 'backend', guard), patch.object(m.receiver, 'ensure') as ensure:
            with self.assertRaisesRegex(RuntimeError, 'delete: registration-changed'):
                m.migrate('lab1')
            ensure.assert_not_called()
        self.assertEqual(['snapshot', 'stop', 'delete'], self.calls)

if __name__ == '__main__':
    unittest.main()


class ReceiptShapeTests(unittest.TestCase):
    def test_malformed_receipts_do_not_hide_unique_valid_receipt(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity = {"pid": 1, "processStartUtcTicks": m.receiver.WINDOWS_TICKS_OFFSET + 7, "image": "pythonw.exe"}
            record = {"lab": "lab1", "pid": 1, "configSha256": "hash", "sourceSha256": m.receiver.SOURCE_SHA256, "entrySha256": "hash", "processIdentity": {"startTicks": 7, "image": "pythonw.exe"}}
            paths = []
            for i, value in enumerate((record, dict(record, processIdentity={"startTicks": 7, "image": []}), dict(record, processIdentity=[]))):
                path = root / "lab1" / str(i) / "process.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(value))
                paths.append(path)
            with patch.object(m.receiver, "TASKS", root), patch.object(m.receiver, "sha", return_value="hash"):
                self.assertEqual(m.receipt_file("lab1", identity, root), paths[0])
                paths[1].write_text(json.dumps(record))
                with self.assertRaisesRegex(RuntimeError, "matching-receipt-not-unique"):
                    m.receipt_file("lab1", identity, root)
