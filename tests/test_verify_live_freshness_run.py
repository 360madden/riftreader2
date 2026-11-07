import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.verify_live_freshness_run import Invalid, load_bytes, verify, when

BASE = Path(__file__).resolve().parents[1] / 'artifacts' / 'receiver-migrations'


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        (self.run / 'raw').mkdir(parents=True)
        self.pin_path = self.root / 'pin.json'
        self.reader_path = self.root / 'reader.json'
        self.start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.expiry = (self.start + timedelta(seconds=900)).isoformat()
        self.reader_id = {'processId': 1, 'processStartUtcTicks': 2, 'executableSha256': 'a' * 64,
                          'instanceId': 'reader', 'nonce': '0123456789abcdef0123456789abcdef', 'sourceAddress': 'address'}
        self.game = {'processId': 3, 'processStartUtcTicks': 4, 'executablePath': 'game', 'executableSha256': 'b' * 64}
        self.receiver = {'processId': 5, 'processStartUtcTicks': 6, 'instanceId': 'receiver'}
        self.pin = {'schemaVersion': 1, 'lab': 'lab1', 'reader': self.reader_id, 'gameIdentity': self.game,
                    'receiver': self.receiver, 'receiptSha256': 'c' * 64}
        self.reader = {'status': 'reader-running-postflight-verified', 'vmIdentityStable': True, 'inputSent': False, 'lab': 'lab1', 'nonce': '0123456789abcdef0123456789abcdef', 'readerPid': 1, 'readerStartUtcTicks': '2',
                       'readerSha256': 'a' * 64, 'gamePid': 3, 'gameStartUtcTicks': '4',
                       'gameSha256': 'b' * 64, 'receiver': {'pid': 5, 'processStartUtcTicks': 6}, 'expiresAtUtc': self.expiry}
        self.summary = {'schemaVersion': 1, 'status': 'passed', 'reason': None, 'sourceQualification': 'observer-side-480s',
                        'observerSideNoInputOnly': True, 'acceptedSamples': 121, 'transientUnavailableReads': 0,
                        'durationRequiredSeconds': 480, 'expiryMarginSeconds': 45, 'maxAllowedGapSeconds': 4.5,
                        'expiresAtUtc': self.expiry, 'lab': 'lab1', 'readerNonce': '0123456789abcdef0123456789abcdef', 'readerPid': 1, 'gamePid': 3,
                        'observedSeconds': 480, 'maximumGapSeconds': 4, 'maximumAcceptanceGapSeconds': 4, 'maximumCaptureGapSeconds': 4}
        self.rows = []
        for i in range(121):
            at = (self.start + timedelta(seconds=i * 4)).isoformat()
            selected = {'schemaVersion': 1, 'sequence': i + 1, 'epoch': 1, 'clock': {'status': 'ok', 'value': i + 1},
                        'player': {'status': 'ok', 'value': 'player'},
                        'fields': {'coord' + axis: {'status': 'ok', 'value': val} for axis, val in zip('XYZ', (1, 2, 3))}}
            block = {'schemaVersion': 1, 'bindingStatus': 'bound-scoped', 'freshnessStatus': 'fresh-scoped', 'selectionStatus': 'selected-scoped',
                     'provenance': 'recent-full-scan-anchored-candidate-regions/1', 'observation': selected,
                     'candidateSequence': i + 1, 'candidateEpoch': 1, 'lastAdvanceAgeMilliseconds': 100, 'freshnessTimeoutMilliseconds': 5000,
                     'scan': {'status': 'complete', 'completed': True, 'scope': 'candidate-regions', 'plannedBytes': 10, 'scannedBytes': 10, 'regionCount': 1}}
            obs = {'schemaVersion': 1, 'instanceId': 'reader', 'nonce': '0123456789abcdef0123456789abcdef', 'target': {**self.game, 'readerSessionNonce': '0123456789abcdef0123456789abcdef'},
                   'readerStatus': 'running', 'sequence': i + 1, 'capturedAtUtc': at, 'fastObservation': block}
            raw = {'schemaVersion': 1, 'receivedMonotonicNs': i * 4_000_000_000, 'receiverInstance': 'receiver', 'sourceAddress': 'address', 'receivedAtUtc': at, 'observation': obs}
            path = self.run / 'raw' / f'{i:03}.json'
            data = json.dumps(raw).encode()
            path.write_bytes(data)
            sample = {'rawReceiptPath': str(path), 'rawReceiptSha256': digest(data), 'receiverInstance': 'receiver',
                      'sourceAddress': 'address', 'readerInstance': 'reader', 'readerNonce': '0123456789abcdef0123456789abcdef', 'lab': 'lab1',
                      'readerProcessId': 1, 'readerProcessStartUtcTicks': 2, 'readerExecutableSha256': 'a' * 64,
                      'target': self.game.copy(), 'outerSequence': i + 1, 'capturedAtUtc': at, 'receivedAtUtc': at,
                      'sourceScope': 'candidate-regions', 'sourceProvenance': block['provenance'], 'player': 'player',
                      'addonEpoch': 1, 'addonSequence': i + 1, 'addonClock': i + 1, 'xyz': {'x': 1, 'y': 2, 'z': 3}}
            self.rows.append({'index': i, 'elapsedSeconds': i * 4, 'sample': sample})
        self.save()

    def save(self):
        data = ''.join(json.dumps(row) + '\n' for row in self.rows).encode()
        (self.run / 'samples.jsonl').write_bytes(data)
        self.summary['ledgerSha256'] = digest(data)
        for path, obj in ((self.run / 'summary.json', self.summary), (self.pin_path, self.pin), (self.reader_path, self.reader)):
            path.write_text(json.dumps(obj))

    def check(self):
        self.save()
        return verify(self.run, self.pin_path, self.reader_path)

    def edit_raw(self, index, fn):
        s = self.rows[index]['sample']
        path = Path(s['rawReceiptPath'])
        raw = json.loads(path.read_text())
        fn(raw)
        data = json.dumps(raw).encode()
        path.write_bytes(data)
        s['rawReceiptSha256'] = digest(data)

    def test_synthetic_expired_and_bootstrap_hash_differs(self):
        result = self.check()
        self.assertEqual(result['status'], 'consistent-recorded-output')
        self.assertEqual(result['samples'], 121)
        self.assertNotEqual(self.pin['receiptSha256'], self.rows[0]['sample']['rawReceiptSha256'])

    def test_identity_gap_drift_and_hash(self):
        self.pin['reader']['nonce'] = 'bad'
        with self.assertRaises(Invalid): self.check()
        self.pin['reader']['nonce'] = '0123456789abcdef0123456789abcdef'
        self.rows[1]['elapsedSeconds'] = 5
        with self.assertRaises(Invalid): self.check()
        self.rows[1]['elapsedSeconds'] = 4
        self.rows[1]['sample']['xyz']['x'] = 2
        self.edit_raw(1, lambda r: r['observation']['fastObservation']['observation']['fields']['coordX'].update(value=2))
        with self.assertRaisesRegex(Invalid, 'drift'): self.check()
        Path(self.rows[1]['sample']['rawReceiptPath']).write_text('{}')
        with self.assertRaisesRegex(Invalid, 'raw-hash'): self.check()

    def test_types_flags_and_scope(self):
        for key, value in [('schemaVersion', True), ('acceptedSamples', True), ('transientUnavailableReads', -1), ('readerPid', True), ('status', 'failed')]:
            old = self.summary[key]
            self.summary[key] = value
            with self.assertRaises(Invalid): self.check()
            self.summary[key] = old
        self.rows[1]['sample']['addonSequence'] = True
        with self.assertRaises(Invalid): self.check()
        self.rows[1]['sample']['addonSequence'] = 2
        self.edit_raw(1, lambda r: r['observation']['fastObservation']['scan'].update(scope='forged'))
        self.rows[1]['sample']['sourceScope'] = 'forged'
        with self.assertRaisesRegex(Invalid, 'invalid-fast-scope'): self.check()
        with self.assertRaises(Invalid): when(None)

    def test_raw_set_and_ledger_tamper(self):
        extra = self.run / 'raw' / 'extra.json'
        extra.write_text('{}')
        with self.assertRaisesRegex(Invalid, 'raw-file-set'): self.check()
        extra.unlink()
        original = self.rows[1]['sample']['rawReceiptPath']
        self.rows[1]['sample']['rawReceiptPath'] = self.rows[0]['sample']['rawReceiptPath']
        with self.assertRaisesRegex(Invalid, 'duplicate-raw-path'): self.check()
        self.rows[1]['sample']['rawReceiptPath'] = original
        self.save()
        with (self.run / 'samples.jsonl').open('ab') as f: f.write(b' ')
        with self.assertRaisesRegex(Invalid, 'ledger-hash'): verify(self.run, self.pin_path, self.reader_path)

    def test_nonce_and_hash_metadata_formats(self):
        self.pin['reader']['nonce'] = 'invalid'
        with self.assertRaisesRegex(Invalid, 'invalid-nonce'):
            self.check()
        self.pin['reader']['nonce'] = '0123456789abcdef0123456789abcdef'
        self.rows[1]['sample']['rawReceiptSha256'] = 'z' * 64
        with self.assertRaisesRegex(Invalid, 'invalid-sha256'):
            self.check()

    def test_nested_schema_rehashed(self):
        for path in ((), ('observation',), ('observation', 'fastObservation'),
                     ('observation', 'fastObservation', 'observation')):
            def alter(raw):
                obj = raw
                for key in path:
                    obj = obj[key]
                obj['schemaVersion'] = True
            self.edit_raw(1, alter)
            with self.assertRaisesRegex(Invalid, 'invalid-integer'):
                self.check()
            def restore(raw):
                obj = raw
                for key in path:
                    obj = obj[key]
                obj['schemaVersion'] = 1
            self.edit_raw(1, restore)

    def test_middle_expired_and_backwards_receipt(self):
        at = (self.start + timedelta(seconds=900)).isoformat()
        self.edit_raw(1, lambda raw: raw.update(receivedAtUtc=at))
        self.rows[1]['sample']['receivedAtUtc'] = at
        with self.assertRaisesRegex(Invalid, 'receipt-expiry'):
            self.check()
        at = (self.start - timedelta(seconds=1)).isoformat()
        self.edit_raw(1, lambda raw: raw.update(receivedAtUtc=at))
        self.rows[1]['sample']['receivedAtUtc'] = at
        with self.assertRaisesRegex(Invalid, 'receipt-time-gap'):
            self.check()

    def test_fake_480_seconds_rejected(self):
        for i, row in enumerate(self.rows):
            at = (self.start + timedelta(seconds=i)).isoformat()
            self.edit_raw(i, lambda raw, at=at, i=i: raw.update(receivedAtUtc=at, receivedMonotonicNs=i * 1_000_000_000))
            row['sample']['receivedAtUtc'] = at
        with self.assertRaisesRegex(Invalid, 'receipt-elapsed-disagreement'):
            self.check()

    def test_compressed_capture_timeline_rehashed(self):
        for i, row in enumerate(self.rows):
            at = (self.start + timedelta(seconds=i)).isoformat()
            self.edit_raw(i, lambda raw, at=at: raw['observation'].update(capturedAtUtc=at))
            row['sample']['capturedAtUtc'] = at
        self.summary['maximumCaptureGapSeconds'] = 1
        with self.assertRaisesRegex(Invalid, 'capture-span-disagreement'):
            self.check()

    def test_expiry_and_missing_raw(self):
        self.reader['expiresAtUtc'] = self.summary['expiresAtUtc'] = (self.start + timedelta(seconds=500)).isoformat()
        with self.assertRaisesRegex(Invalid, 'initial-expiry'):
            self.check()
        self.reader['expiresAtUtc'] = self.summary['expiresAtUtc'] = self.expiry
        Path(self.rows[2]['sample']['rawReceiptPath']).unlink()
        with self.assertRaises(OSError):
            self.check()

    def test_bounded_read(self):
        path = self.root / 'large'
        path.write_bytes(b'12345')
        with self.assertRaisesRegex(Invalid, 'invalid-file-size'): load_bytes(path, 4)


class RealReplayTests(unittest.TestCase):
    def test_real_run_when_available(self):
        run = BASE / 'lab1-strict480-observer-d'
        pin = BASE / 'lab1-sustained-source-pin-d.json'
        reader = BASE / 'lab1-sustained-reader-c' / 'summary.json'
        if not all(path.exists() for path in (run, pin, reader)):
            self.skipTest('local ignored evidence unavailable')
        result = verify(run, pin, reader)
        self.assertEqual(result['samples'], 515)
        self.assertEqual(result['scopes'], {'candidate-regions': 472, 'whole-readable-private': 43})
