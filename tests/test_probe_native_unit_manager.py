"""Synthetic tests: no RIFT process, VM, controller, or credentials required."""
import base64
import copy
import struct
import unittest

from scripts.probe_native_unit_manager import (
    BUILD_SHA, encoded, entity_hash, find_entity, inspection_identity, pointer,
    sha, snapshot_bytes,
)


class NativeUnitManagerTests(unittest.TestCase):
    def test_exact_hash_vectors(self):
        vectors = {0: 0, 1: 16807, 2: 33614, 127773: 2147480811,
                   0x7FFFFFFF: 0, 0x80000000: 2147466840,
                   0xFFFFFFFF: 2147466840, 0xFFFE0CE3: 2836}
        for seed, expected in vectors.items():
            with self.subTest(seed=seed):
                self.assertEqual(expected, entity_hash(seed))
                self.assertEqual(expected, entity_hash(0x0354000100000000 | seed))

    @staticmethod
    def table(key=0x035400012FA2D207):
        base, stride, count = 0x20000, 24, 64
        header = struct.pack("<QQQ", base, stride, count)
        bucket = base + (entity_hash(key) % count) * stride
        return header, bucket, key

    def test_inline_exact_full_key(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 0, key, 0x60000)
        calls = []
        def read(address, length):
            calls.append((address, length))
            return raw
        result = find_entity(header, key, read)
        self.assertEqual(0x60000, result["entity"])
        self.assertEqual([(bucket, 24)], calls)
        self.assertEqual(1, result["visitedNodes"])

    def test_same_low32_different_full_key_does_not_match(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 0, key ^ (1 << 48), 0x60000)
        with self.assertRaisesRegex(ValueError, "player-key-not-found"):
            find_entity(header, key, lambda *_: raw)

    def test_tagged_inline_slot_is_not_a_match(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 1, key, 0x60000)
        with self.assertRaisesRegex(ValueError, "player-key-not-found"):
            find_entity(header, key, lambda *_: raw)

    def test_tagged_link_reaches_collision_node(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50001, key, 0xDEAD0),
                 0x50000: struct.pack("<QQQ", 0, key, 0x60000)}
        result = find_entity(header, key, lambda address, _: nodes[address])
        self.assertEqual(0x50000, result["node"])
        self.assertEqual(0x60000, result["entity"])
        self.assertEqual(2, result["visitedNodes"])

    def test_inline_mismatch_follows_untagged_link(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50000, key + 1, 0xDEAD0),
                 0x50000: struct.pack("<QQQ", 0, key, 0x60000)}
        self.assertEqual(0x60000, find_entity(header, key, lambda a, _: nodes[a])["entity"])

    def test_collision_cycle_rejected(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50001, 0, 0),
                 0x50000: struct.pack("<QQQ", 0x50001, 0, 0)}
        with self.assertRaisesRegex(ValueError, "lookup-pointer-cycle"):
            find_entity(header, key, lambda a, _: nodes[a])

    def test_node_budget_rejected(self):
        header, bucket, key = self.table()
        with self.assertRaisesRegex(ValueError, "lookup-node-budget"):
            find_entity(header, key, lambda *_: struct.pack("<QQQ", 0x50001, 0, 0), max_nodes=1)

    def test_short_node_rejected(self):
        header, bucket, key = self.table()
        with self.assertRaisesRegex(ValueError, "lookup-read-hole"):
            find_entity(header, key, lambda *_: b"\0" * 16)

    def test_table_shape_and_payload_bounds_rejected(self):
        header, bucket, key = self.table()
        for bad in (struct.pack("<QQQ", 0x20000, 16, 64),
                    struct.pack("<QQQ", 0x20000, 24, 0),
                    struct.pack("<QQQ", 0x20000, 25, 64)):
            with self.assertRaisesRegex(ValueError, "invalid-table-shape"):
                find_entity(bad, key, lambda *_: b"")
        for value in (0, 0x60001, 0x800000000000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                find_entity(header, key, lambda *_: struct.pack("<QQQ", 0, key, value))

    def test_pointer_bounds(self):
        for value in (0, -1, 0x10001, 0x800000000000, 0x7FFFFFFFFFF8):
            with self.assertRaises(ValueError):
                pointer(value, 24)

    @staticmethod
    def inspection():
        target = {"processId": 1234, "processStartUtcTicks": 123456789,
                  "executableSha256": BUILD_SHA}
        return {"schemaVersion": 1, "contractVersion": "native-target-inspection/1",
                "target": dict(target, executablePath=r"C:\RIFT\rift_x64.exe",
                               moduleBaseAddress="0x140000000", moduleSize=63164416),
                "suggestedRequest": {"target": target}}

    def test_inspection_converts_module_base(self):
        identity, target = inspection_identity(self.inspection())
        self.assertEqual(0x140000000, identity["moduleBaseAddress"])
        self.assertEqual(BUILD_SHA, target["executableSha256"])

    def test_wrong_build_or_inconsistent_inspection_rejected(self):
        report = self.inspection()
        report["target"]["executableSha256"] = "A" * 64
        with self.assertRaisesRegex(ValueError, "wrong-build"):
            inspection_identity(report)
        report = self.inspection()
        report["suggestedRequest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(ValueError, "wrong-build"):
            inspection_identity(report)

    def snapshot(self):
        identity, target = inspection_identity(self.inspection())
        request = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot-request/1",
                   "target": target, "maxDurationMilliseconds": 10000,
                   "ranges": [{"addressKind": "module-relative-rva",
                               "address": "0x100", "byteLength": 8}]}
        raw = struct.pack("<Q", 0x20000)
        report = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
                  "status": "complete", "identity": identity,
                  "source": {"requestSha256": sha(encoded(request))},
                  "chunks": [{"address": "0x140000100", "status": "success",
                              "requestedByteLength": 8, "bytesRead": 8,
                              "bytesBase64": base64.b64encode(raw).decode(),
                              "bytesSha256": sha(raw)}]}
        return report, request, identity, raw

    def test_snapshot_full_identity_and_hashes(self):
        report, request, identity, raw = self.snapshot()
        self.assertEqual({0x140000100: raw}, snapshot_bytes(report, request, identity))

    def test_snapshot_holes_and_corruption_rejected(self):
        original, request, identity, _ = self.snapshot()
        changes = [
            lambda r: r.update(status="partial"),
            lambda r: r["identity"].update(processStartUtcTicks=999),
            lambda r: r["source"].update(requestSha256="A" * 64),
            lambda r: r["chunks"][0].update(bytesSha256="B" * 64),
            lambda r: r["chunks"][0].update(bytesRead=4),
            lambda r: r["chunks"].clear(),
            lambda r: r["chunks"].append(copy.deepcopy(r["chunks"][0])),
        ]
        for change in changes:
            report = copy.deepcopy(original)
            change(report)
            with self.assertRaises(ValueError):
                snapshot_bytes(report, request, identity)


if __name__ == "__main__":
    unittest.main()
