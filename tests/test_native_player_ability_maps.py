import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_player_ability_maps import read_player_ability_maps
from native_resolver_cache import SnapshotPageReader


class TestPlayerAbilityMaps(unittest.TestCase):
    def run_snapshot(self, *, mutate=False, backwards=False, mismatch=False, cycle=False):
        context, root, clock = 0x100000, 0x200000, 0x300000
        h1, h2, chain = 0x400000, 0x500000, 0x600000
        p = lambda x: struct.pack('<Q', x)
        node = lambda link, key, value: struct.pack('<QIIff', link, key, 0, value, 2.0)
        memory = {
            context + 0x1c0: struct.pack('<QQQQ', h1, 40, 2, 3 if mismatch else 2),
            context + 0x240: struct.pack('<QQQQ', h2, 24, 1, 1),
            root: p(clock), h1: node(chain, 10, 3), h1 + 40: p(1) + bytes(16),
            chain: node(chain if cycle else 0, 11, 4), h2: node(0, 12, 5),
        }
        def read(name, ranges):
            out = {}
            for address, length in ranges:
                if address == clock + 0x18:
                    value = 9.0 if name == 'ability-map-clock' else (8.0 if backwards else 10.0)
                    out[address] = struct.pack('<f', value)
                else:
                    out[address] = memory[address]
                    if mutate and name == 'resolver_verify' and address == h1:
                        out[address] = bytes(length)
            return out
        return read_player_ability_maps(read, context=context, clock_root_address=root)

    def test_both_strides_chain_and_advancing_clock(self):
        result = self.run_snapshot()
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual([m['stride'] for m in result['maps']], [40, 24])
        self.assertEqual([x['key'] for x in result['maps'][0]['entries']], [10, 11])
        self.assertEqual((result['clockBefore'], result['clockAfter']), (9.0, 10.0))

    def test_mismatch_and_cycle_fail_closed(self):
        for kwargs in ({'mismatch': True}, {'cycle': True}):
            result = self.run_snapshot(**kwargs)
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(result['maps'], [])

    def test_mutation_and_backward_clock_fail_closed(self):
        for kwargs in ({'mutate': True}, {'backwards': True}):
            result = self.run_snapshot(**kwargs)
            self.assertEqual(result['status'], 'unavailable')
            self.assertEqual(result['maps'], [])

    def test_real_page_reader_allows_advancing_clock(self):
        context, root, clock, head = 0x100000, 0x200000, 0x300000, 0x400000
        pages = {a: bytearray(4096) for a in (context, root, clock, head)}
        def put(address, data):
            page = address & ~0xfff
            pages[page][address - page:address - page + len(data)] = data
        put(context + 0x1c0, struct.pack('<QQQQ', head, 40, 1, 1))
        put(context + 0x240, struct.pack('<QQQQ', 0, 24, 0, 0))
        put(root, struct.pack('<Q', clock))
        put(head, struct.pack('<QIIff', 0, 7, 0, 4.0, 1.0))
        put(clock + 0x18, struct.pack('<f', 9.0))
        def backend(name, ranges):
            if name == 'resolver_verify_pages':
                put(clock + 0x18, struct.pack('<f', 10.0))
            return {address: bytes(pages[address]) for address, _ in ranges}
        result = read_player_ability_maps(SnapshotPageReader(backend), context=context,
                                          clock_root_address=root)
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual((result['clockBefore'], result['clockAfter']), (9.0, 10.0))
