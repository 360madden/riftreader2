import struct
import unittest

from scripts.native_ability_record_seed import read_ability_record_seeds


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.mem = {}
        self.slot, self.record, self.child, self.string = 0x20000, 0x30000, 0x40000, 0x50000
        self.base = 0x100000
        self.node, self.holder = 0x60000, self.slot - 0x18
        self.raw_key = struct.pack('<HHI', 83, 0, 7)
        self.put(self.node + 8, self.raw_key + struct.pack('<Q', self.holder))
        self.put(self.slot, struct.pack('<Q', self.record))
        self.put(self.record, struct.pack('<Q', self.base + 0x28A08C0))
        self.put(self.base + 0x28A0900, struct.pack('<Q', self.base + 0x1899BF0))
        self.put(self.record + 0x8e0, struct.pack('<Q', self.child))
        self.put(self.record + 0x958, struct.pack('<Q', 0))
        self.put(self.child, struct.pack('<Q', self.base + 0x27F24F8))
        self.put(self.base + 0x27F2538, struct.pack('<Q', self.base + 0x170C5D0))
        self.put(self.base + 0x344A6B0, struct.pack('<Q', self.base + 0x28A9C38))
        self.put(self.base + 0x28A9C40, struct.pack('<Q', self.base + 0x18C06C0))
        self.put(self.base + 0x3417970, struct.pack('<Q', self.base + 0x2802E40))
        self.put(self.base + 0x2802E48, struct.pack('<Q', self.base + 0x17361E0))
        self.put(self.child + 0x18, struct.pack('<I', 99))
        self.put(self.child + 0x20, struct.pack('<Q', self.string))
        self.put(self.string, 'Example\0'.encode('utf-16-le').ljust(256, b'\0'))
        self.change = None

    def put(self, address, data):
        self.mem.update({address + i: b for i, b in enumerate(data)})

    def read(self, phase, ranges):
        result = {}
        for address, length in ranges:
            data = bytes(self.mem[address + i] for i in range(length))
            if phase == 'resolver_verify' and self.change == address:
                data = bytes([data[0] ^ 1]) + data[1:]
            result[address] = data
        return result

    def inspect(self):
        return read_ability_record_seeds(self.read, entries=[{'key': 7, 'result_pointer': self.record,
            'result_slot_address': self.slot, 'node_address': self.node, 'holder_address': self.holder, 'raw_key': self.raw_key.hex(), 'selector': 83}],
            module_base=self.base, module_size=0x4000000, build_sha='1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8', key_hash=lambda n: n * 2)[0]

    def test_null_child(self):
        self.put(self.record + 0x8e0, bytes(8))
        row = self.inspect()
        self.assertEqual(row['reason'], 'null_child')
        self.assertTrue(row['record_type_verified'])

    def test_fallback_candidate(self):
        row = self.inspect()
        self.assertEqual(row['fallbackNameCandidate'], 'Example')
        self.assertEqual(row['child_getter_rva'], 0x170C5D0)
        self.assertTrue(row['child_type_verified'])

    def test_prewarm_batches_dependent_ranges(self):
        # Fill unused child-header bytes so the prefetch is readable.
        for address in range(self.child, self.child + 0x28):
            self.mem.setdefault(address, 0)
        calls = []
        def recording(phase, ranges):
            calls.append((phase, ranges))
            return self.read(phase, ranges)
        row = read_ability_record_seeds(recording, entries=[{'key': 7,
            'result_pointer': self.record, 'result_slot_address': self.slot, 'node_address': self.node, 'holder_address': self.holder, 'raw_key': self.raw_key.hex(), 'selector': 83}],
            module_base=self.base, module_size=0x4000000, build_sha='1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8', key_hash=lambda n: n * 2)[0]
        warm = [ranges for phase, ranges in calls if phase == 'ability_prewarm']
        self.assertEqual(len(warm), 3)
        self.assertIn((self.child, 0x28), warm[1])
        self.assertIn((self.string, 256), warm[2])
        self.assertEqual(row['fallbackNameCandidate'], 'Example')

    def test_secondary_child_contributes_to_full_id(self):
        secondary = 0x70000
        self.put(self.record + 0x958, struct.pack('<Q', secondary))
        self.put(secondary, struct.pack('<Q', self.base + 0x27F24F8))
        self.put(secondary + 0x18, struct.pack('<I', 23))
        row = self.inspect()
        self.assertEqual(row['fullNewIdCandidate'], 'A00000007000000F4')
        self.assertTrue(row['secondary_child_type_verified'])
        self.change = secondary + 0x18
        self.assertIsNone(self.inspect()['fullNewIdCandidate'])

    def test_unreadable_secondary_is_not_zero(self):
        self.put(self.record + 0x958, struct.pack('<Q', 0x70000))
        row = self.inspect()
        self.assertIsNone(row['fullNewIdCandidate'])
        self.assertTrue(row['reason'].startswith('read_failed'))

    def test_descriptor_not_initialized_or_wrong(self):
        for address, value in ((self.base + 0x344A6B0, 0),
                               (self.base + 0x3417970, self.base + 0x1234)):
            old = bytes(self.mem[address + i] for i in range(8))
            self.put(address, struct.pack('<Q', value))
            row = self.inspect()
            self.assertEqual(row['status'], 'unavailable')
            self.assertEqual(row['reason'], 'descriptor_uninitialized_or_mismatch')
            self.assertIsNone(row['fallbackNameCandidate'])
            self.put(address, old)

    def test_stale_or_changed_consumed_data(self):
        for address in (self.node + 8, self.slot, self.record + 0x8e0, self.string):
            with self.subTest(address=address):
                self.change = address
                row = self.inspect()
                self.assertEqual(row['reason'], 'changed_during_read')
                self.assertIsNone(row['fallbackNameCandidate'])
        self.change = None
        self.put(self.node + 16, struct.pack('<Q', self.holder + 8))
        self.assertEqual(self.inspect()['reason'], 'stale_cache_binding')
        self.put(self.node + 16, struct.pack('<Q', self.holder))
        self.put(self.slot, struct.pack('<Q', self.record + 8))
        self.assertEqual(self.inspect()['reason'], 'stale_result_slot')


if __name__ == '__main__':
    unittest.main()
