"""Bounded, fail-closed native image root selection tests (no VM dependency)."""
import copy
import hashlib
import json
import unittest

from scripts.capture_native_image_roots import (
    MAX_IMAGE_BYTES, inspect_snapshot, select_image_ranges, target_from_scope,
)


def fixture():
    base = 0x7FF600000000
    scope = {
        "schemaVersion": 1, "evidenceKind": "rift-image-scope-plan/1",
        "game": {"processId": 17, "processStartUtcTicks": 123456789,
                 "executableSha256": "A" * 64,
                 "moduleBase": f"0x{base:X}", "moduleSize": 0x10000},
        "writableSections": [
            {"name": ".data", "writable": True, "rva": "0x4000",
             "virtualBytes": 0x3000, "runtimeStart": f"0x{base + 0x4000:X}"}
        ],
    }
    mapping = {
        "schemaVersion": 1, "evidenceKind": "native-memory-map/1", "status": "complete",
        "identity": {"processId": 17, "processStartUtcTicks": 123456789,
                     "executableSha256": "A" * 64,
                     "moduleBaseAddress": base, "moduleSize": 0x10000},
        "regions": [
            {"baseAddress": f"0x{base + 0x3000:X}", "regionSize": 0x2000,
             "protection": "0x4", "type": "0x1000000"},
            {"baseAddress": f"0x{base + 0x5000:X}", "regionSize": 0x1000,
             "protection": "0x4", "type": "0x20000"},
            {"baseAddress": f"0x{base + 0x6000:X}", "regionSize": 0x1000,
             "protection": "0x4", "type": "0x1000000"},
        ],
    }
    return scope, mapping


class ImageRootsTests(unittest.TestCase):
    def test_image_only_intersection_and_hole(self):
        scope, mapping = fixture()
        result = select_image_ranges(scope, mapping)
        self.assertEqual(result["selectedByteCount"], 8192)
        self.assertEqual(result["excludedByteCount"], 4096)
        self.assertEqual(result["ranges"], [
            {"addressKind": "module-relative-rva", "address": "0x4000",
             "byteLength": 4096},
            {"addressKind": "module-relative-rva", "address": "0x6000",
             "byteLength": 4096},
        ])
        self.assertEqual(result["holes"][0]["byteLength"], 4096)

    def test_stale_epoch_and_noncanonical_address_rejected(self):
        scope, mapping = fixture()
        mapping["identity"]["processStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "identity"):
            select_image_ranges(scope, mapping)
        scope, mapping = fixture()
        scope["writableSections"][0]["rva"] = "0x04000"
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            select_image_ranges(scope, mapping)

    def test_guard_pages_never_selected(self):
        scope, mapping = fixture()
        mapping["regions"][0]["protection"] = "0x104"
        result = select_image_ranges(scope, mapping)
        self.assertEqual(result["selectedByteCount"], 4096)
        self.assertEqual(result["excludedByteCount"], 8192)

    def test_missing_pages_and_byte_budget_fail_closed(self):
        scope, mapping = fixture()
        mapping["regions"][0]["type"] = "0x20000"
        mapping["regions"][2]["type"] = "0x20000"
        with self.assertRaisesRegex(ValueError, "no-readable"):
            select_image_ranges(scope, mapping)
        scope, mapping = fixture()
        with self.assertRaisesRegex(ValueError, "exceeds-bounded"):
            select_image_ranges(scope, mapping, max_bytes=4096)

    def test_rejects_unsafe_map_and_section_overlap(self):
        scope, mapping = fixture()
        mapping["status"] = "partial"
        with self.assertRaisesRegex(ValueError, "not-complete"):
            select_image_ranges(scope, mapping)
        scope, mapping = fixture()
        mapping["regions"][1]["baseAddress"] = mapping["regions"][0]["baseAddress"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            select_image_ranges(scope, mapping)
        scope, mapping = fixture()
        scope["writableSections"].append(copy.deepcopy(scope["writableSections"][0]))
        with self.assertRaisesRegex(ValueError, "overlap"):
            target_from_scope(scope)

    def test_snapshot_provenance_and_chunk_hash(self):
        scope, mapping = fixture()
        selection = select_image_ranges(scope, mapping)
        request = {"target": selection["target"], "ranges": selection["ranges"]}
        raw = b"R" * 4096
        chunks = [
            {"address": f"0x{mapping['identity']['moduleBaseAddress'] + int(r['address'],16):X}",
             "requestedByteLength": 4096, "status": "success",
             "bytesBase64": __import__("base64").b64encode(raw).decode(),
             "bytesRead": 4096, "bytesSha256": hashlib.sha256(raw).hexdigest().upper()}
            for r in request["ranges"]
        ]
        snapshot = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
                    "status": "complete", "identity": mapping["identity"],
                    "source": {"requestSha256": hashlib.sha256(
                        json.dumps(request, separators=(",", ":")).encode()).hexdigest().upper()},
                    "chunks": chunks}
        result = inspect_snapshot(
            snapshot, request, mapping, mapping["identity"]["moduleBaseAddress"])
        self.assertEqual(result["successfulByteCount"], 8192)
        snapshot["chunks"][0]["bytesSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            inspect_snapshot(snapshot, request, mapping, mapping["identity"]["moduleBaseAddress"])


if __name__ == "__main__":
    unittest.main()
