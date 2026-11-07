import unittest
from scripts.native_resolver_cache import read_resolver_cache, SnapshotPageReader, lookup_resolver_cache
import struct

C, B = 0x10000, 0x20000

def node(link=1, selector=0, key=0, holder=0):
    return struct.pack('<QH2xIQ', link, selector, key, holder)

def fixture(nodes):
    memory = {C + 0x20: struct.pack('<QQQQ', B, 24, len(nodes), sum(not (struct.unpack_from('<Q', n)[0] & 1) for n in nodes)), B: b''.join(nodes)}
    def read(name, ranges):
        result = {}
        if name == 'resolver_chain_pages':
            for addr, size in ranges:
                data = bytearray(size)
                for start, value in memory.items():
                    lo, hi = max(addr, start), min(addr + size, start + len(value))
                    if lo < hi:
                        data[lo-addr:hi-addr] = value[lo-start:hi-start]
                result[addr] = bytes(data)
            return result
        for addr, size in ranges:
            for start, data in memory.items():
                if start <= addr and addr + size <= start + len(data):
                    result[addr] = data[addr-start:addr-start+size]
                    break
            else:
                raise ValueError('unmapped')
        return result
    return memory, read

def test_tagged_head_still_follows_collision_chain():
    memory, read = fixture([node(0x30001, 83, 1)])
    memory[C + 0x20] = struct.pack('<QQQQ', B, 24, 1, 1)
    memory[0x30000] = node(0, 83, 2, 0x40000)
    memory[0x40018] = struct.pack('<Q', 0)
    result = read_resolver_cache(read, collection=C, selector=83)
    assert result['status'] == 'complete'
    assert [e['key'] for e in result['entries']] == [2]
    assert result['entries'][0]['result_pointer'] == 0
    assert result['inventory']['chain_nodes'] == 1

def test_available_head_wrong_selector_and_null_holder():
    _, read = fixture([node(0, 83, 7), node(0, 84, 8)])
    result = read_resolver_cache(read, collection=C, selector=83)
    assert result['status'] == 'complete'
    assert [e['key'] for e in result['entries']] == [7]
    assert result['entries'][0]['result_pointer'] is None
    assert result['inventory']['available_heads'] == 2

def test_torn_bucket_discards_candidates():
    _, read = fixture([node(0, 83, 7)])
    def torn(name, ranges):
        result = read(name, ranges)
        if name == 'resolver_verify' and B in result:
            result[B] = node(0, 83, 8)
        return result
    result = read_resolver_cache(torn, collection=C, selector=83)
    assert result['reason'] == 'changed_during_walk'
    assert result['entries'] == []

def test_bucket_limit_is_explicit():
    _, read = fixture([node()] * 3)
    result = read_resolver_cache(read, collection=C, selector=83, max_buckets=2)
    assert result['status'] == 'partial' and result['reason'] == 'bucket_budget'

def test_cycle_is_explicit():
    memory, read = fixture([node(0x30001)])
    memory[0x30000] = node(0x30000, 84)
    result = read_resolver_cache(read, collection=C, selector=83)
    assert result['status'] == 'partial' and result['reason'] == 'chain_cycle'


class ResolverCacheTests(unittest.TestCase):
    def test_tagged_head_collision(self):
        test_tagged_head_still_follows_collision_chain()

    def test_selector_and_null(self):
        test_available_head_wrong_selector_and_null_holder()

    def test_torn(self):
        test_torn_bucket_discards_candidates()

    def test_bounds(self):
        test_bucket_limit_is_explicit()

    def test_cycle(self):
        test_cycle_is_explicit()

    def test_boolean_bounds_are_invalid(self):
        _, read = fixture([node()])
        for kwargs in ({"selector": True}, {"selector": 83, "max_buckets": True},
                       {"selector": 83, "max_chain_nodes": True}):
            self.assertIn(read_resolver_cache(read, collection=C, **kwargs)["reason"],
                          ("invalid_selector", "invalid_bounds"))

    def test_long_chain_uses_page_and_checks_only_consumed_nodes(self):
        memory, read = fixture([node(0x30001)])
        for i in range(30):
            address = 0x30000 + i * 24
            memory[address] = node(address + 24 if i < 29 else 0, 83, i)
        memory[C + 0x20] = struct.pack('<QQQQ', B, 24, 1, 30)
        calls = []
        def stable(name, ranges):
            if name == "resolver_chain_pages":
                calls.append(ranges)
            return read(name, ranges)
        result = read_resolver_cache(stable, collection=C, selector=83)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["entries"]), 30)
        self.assertEqual(calls, [[(0x30000, 4096)]])
        def torn(name, ranges):
            values = read(name, ranges)
            if name == "resolver_verify" and 0x30000 in values:
                values[0x30000] = node(0, 83, 123)
            return values
        self.assertEqual(read_resolver_cache(torn, collection=C, selector=83)["reason"], "changed_during_walk")
        # Changing a byte outside every consumed node must not invalidate the walk.
        def unrelated(name, ranges):
            values = read(name, ranges)
            if name == "resolver_verify":
                self.assertFalse(any(addr <= 0x30fff < addr + size for addr, size in ranges))
            return values
        self.assertEqual(read_resolver_cache(unrelated, collection=C, selector=83)["status"], "complete")

    def test_entry_count_mismatch(self):
        memory, read = fixture([node(0, 83, 7)])
        memory[C + 0x20] = struct.pack('<QQQQ', B, 24, 1, 2)
        self.assertEqual(read_resolver_cache(read, collection=C, selector=83)["reason"], "entry_count_mismatch")

    def test_snapshot_page_reader_verifies_fresh_once(self):
        pages = {0x30000: bytearray(4096)}
        calls = []
        def backing(name, ranges):
            calls.append(name)
            return {addr: bytes(pages[addr]) for addr, size in ranges}
        reader = SnapshotPageReader(backing)
        self.assertEqual(reader("forward", [(0x30018, 8)])[0x30018], b"\0" * 8)
        pages[0x30000][0x18] = 7
        self.assertEqual(reader("resolver_verify", [(0x30018, 8)])[0x30018][0], 7)
        pages[0x30000][0x18] = 9
        self.assertEqual(reader("resolver_verify", [(0x30018, 8)])[0x30018][0], 7)
        self.assertEqual(len(calls), 2)

    def test_snapshot_page_reader_rejects_unseen_verification(self):
        reader = SnapshotPageReader(lambda name, ranges: {a: bytes(n) for a, n in ranges})
        reader("forward", [(0x30000, 8)])
        with self.assertRaises(ValueError):
            reader("resolver_verify", [(0x40000, 8)])


    def test_target_head_collision_and_miss(self):
        memory, read = fixture([node(0x30000, 83, 2)])
        memory[0x30000] = node(0, 83, 3, 0x40000)
        memory[0x40018] = struct.pack('<Q', 0)
        result = lookup_resolver_cache(read, collection=C, selector=83, keys=[2, 3, 4], key_hash=lambda x: x)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([row['key'] for row in result['entries']], [2, 3])
        self.assertEqual(result['missingKeys'], [4])
        self.assertFalse(result['fallback_resolved'])

    def test_target_tagged_head_and_wrong_selector(self):
        memory, read = fixture([node(0x30001, 83, 2)])
        memory[0x30000] = node(0, 84, 2)
        result = lookup_resolver_cache(read, collection=C, selector=83, keys=[2], key_hash=lambda x: x)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['missingKeys'], [2])

    def test_target_changed_node_discards_results(self):
        _, read = fixture([node(0, 83, 2)])
        def torn(name, ranges):
            values = read(name, ranges)
            if name == 'resolver_verify' and B in values:
                values[B] = node(0, 83, 3)
            return values
        result = lookup_resolver_cache(torn, collection=C, selector=83, keys=[2], key_hash=lambda x: x)
        self.assertEqual(result['reason'], 'changed_during_walk')
        self.assertEqual(result['entries'], [])

    def test_wildcard_returns_same_key_across_selectors_and_checks_stability(self):
        memory, read = fixture([node(0x30000, 83, 7)])
        memory[0x30000] = node(0, 84, 7)
        args = dict(collection=C, keys=[7], key_hash=lambda x: x)
        result = lookup_resolver_cache(read, selector=None, **args)
        self.assertEqual([e['selector'] for e in result['entries']], [83, 84])
        self.assertEqual(result['scope'], 'requested-keys-any-selector')
        exact = lookup_resolver_cache(read, selector=83, **args)
        self.assertEqual([e['selector'] for e in exact['entries']], [83])
        def torn(name, ranges):
            values = read(name, ranges)
            if name == 'resolver_verify' and 0x30000 in values:
                values[0x30000] = node(0, 85, 7)
            return values
        self.assertEqual(lookup_resolver_cache(torn, selector=None, **args)['reason'], 'changed_during_walk')
