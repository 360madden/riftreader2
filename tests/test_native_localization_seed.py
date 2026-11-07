import struct
import unittest
from scripts.native_localization_seed import read_localization_seeds
from scripts.native_resolver_cache import SnapshotPageReader

BASE = 0x10000000
M, P, N, H, R, T, D, S = (0x20000000 + n * 0x1000 for n in range(8))
V = BASE + 0x1000

def fixture(locale=2, tree_key=2):
    mem = {}
    def put(a, data):
        for i, b in enumerate(data): mem[a+i] = b
    def q(a, v): put(a, struct.pack('<Q', v))
    q(BASE+0x33623e8, M); q(BASE+0x3373768, P)
    put(M, struct.pack('<B3xi', 0, locale)); q(M+0x98, BASE+0x2f59b20)
    q(BASE+0x2f59b20, BASE+0x26c1e90); q(BASE+0x26c1e90, BASE+0x7d1790)
    put(P+0x40, struct.pack('<H', 99)); put(N, struct.pack('<QH2xIQ', 0, 99, 4, H)); q(H+0x18, R)
    q(R, V); q(V+0x40, BASE+0x2000); q(R+0x28, T); q(R+0x40, 1)
    put(T, bytes(16)+struct.pack('<QQi4xQ', 0, 0, tree_key, D))
    q(D, V); q(D+0x30, S); q(D+0x38, S)
    put(S, 'Hello'.encode('utf-16-le')+bytes(246))
    def read(name, ranges):
        return {a: bytes(mem[x] for x in range(a, a+n)) for a,n in ranges}
    entry = {'node_address': N, 'holder_address': H, 'result_pointer': R, 'selector': 99, 'key': 4}
    return mem, put, read, [entry]

class LocalizationTests(unittest.TestCase):
    def run_inspect(self, read, entries):
        return read_localization_seeds(read, module_base=BASE, module_size=0x3400000, entries=entries)
    def test_current_and_fallback_locale(self):
        for locale, key in ((2,2), (2,1)):
            _, _, read, entries = fixture(locale, key)
            result = self.run_inspect(read, entries)
            self.assertEqual(result['status'], 'complete', result)
            self.assertEqual(result['records'][0]['locale_found'], key)
            self.assertEqual(result['records'][0]['candidate_text'], 'Hello')
            self.assertFalse(result['records'][0]['type_verified'])
    def test_provider_override_and_cycle(self):
        _, put, read, entries = fixture()
        put(M+0x98, struct.pack('<Q', 0x30000000))
        self.assertIn('provider override', self.run_inspect(read, entries)['reason'])
        _, put, read, entries = fixture(locale=2, tree_key=3)
        put(T+0x10, struct.pack('<Q', T))
        self.assertEqual(self.run_inspect(read, entries)['reason'], 'invalid_tree_or_cycle')
    def test_changed_node_or_text_discards(self):
        for changed in (T, S):
            _, _, read, entries = fixture()
            def torn(name, ranges):
                values = read(name, ranges)
                if name == 'resolver_verify' and changed in values:
                    values[changed] = bytes([values[changed][0] ^ 1]) + values[changed][1:]
                return values
            result = self.run_inspect(torn, entries)
            self.assertEqual(result['reason'], 'changed_during_walk')
            self.assertEqual(result['records'], [])

    def test_page_snapshot_checks_only_terminated_two_aligned_text(self):
        for changed, expected in ((S + 2 + 20, 'complete'), (S + 2, 'partial')):
            mem, put, _, entries = fixture()
            put(D + 0x30, struct.pack('<Q', S + 2))
            put(D + 0x38, struct.pack('<Q', S + 2))
            put(S + 2, 'Hello'.encode('utf-16-le') + b'\0\0')
            def backend(name, ranges):
                if name == 'resolver_verify_pages':
                    mem[changed] = mem.get(changed, 0) ^ 1
                return {a: bytes(mem.get(x, 0) for x in range(a, a+n)) for a,n in ranges}
            result = self.run_inspect(SnapshotPageReader(backend), entries)
            self.assertEqual(result['status'], expected, result)
            if expected == 'complete':
                self.assertEqual(result['records'][0]['candidate_text'], 'Hello')
            else:
                self.assertEqual(result['reason'], 'changed_during_walk')
                self.assertEqual(result['records'], [])

    def test_null_provider_dictionary_mode_only(self):
        _, put, read, entries = fixture()
        put(BASE + 0x3373768, struct.pack('<Q', 0))
        self.assertEqual(self.run_inspect(read, entries)['status'], 'partial')
        result = read_localization_seeds(read, module_base=BASE, module_size=0x3400000,
                                         entries=entries, dictionary_mode=True)
        self.assertEqual(result['status'], 'complete', result)
        self.assertIsNone(result['context']['selector'])
        self.assertEqual(result['context']['provider'], 0)
        self.assertEqual(result['records'][0]['selector'], 99)
        self.assertTrue(result['apiRouteUnavailable'])
        self.assertFalse(result['type_verified'])
