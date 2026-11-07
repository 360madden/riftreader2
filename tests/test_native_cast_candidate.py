import importlib.util
from pathlib import Path
import struct
import unittest

SPEC = importlib.util.spec_from_file_location(
    "native_cast_candidate", Path(__file__).parents[1] / "scripts/native_cast_candidate.py")
cast = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cast)


class CastTopologyTests(unittest.TestCase):
    def setUp(self):
        self.base, self.entity, self.table, self.component = 0x10000000, 0x20000, 0x30000, 0x40000
        self.memory = {
            (self.base + cast.SELECTOR_RVA, 4): struct.pack("<i", 9),
            (self.entity + 0x18 + 9, 1): bytes([3]),
            (self.entity + 0x78, 8): struct.pack("<Q", self.table),
            (self.table + 24, 8): struct.pack("<Q", self.component),
            (self.component + 0x280, 8): struct.pack("<Q", 0x50000),
            (self.component + 0x290, 8): struct.pack("<Q", 0),
            (self.component + 0x2B8, 4): struct.pack("<I", 42),
            (0x50008, 4): struct.pack("<I", 1234),
        }

    def run_read(self, reader=None, sha=cast.BUILD_SHA):
        return cast.read_cast_topology(reader or (lambda a, n: self.memory[(a, n)]),
                                       module_base=self.base, entity=self.entity, build_sha=sha)

    def test_nonzero_is_raw_candidate_without_semantics(self):
        result = self.run_read()
        self.assertEqual(result["status"], "candidate-nonzero-child")
        self.assertEqual(result["children"][0]["rawId"], 1234)
        self.assertEqual(result["rawComponentDword2B8"], 42)
        for field in ("isCasting", "begin", "duration", "remaining", "uninterruptible"):
            self.assertIsNone(result[field])

    def test_zero_is_not_semantic_idle(self):
        self.memory[(0x50008, 4)] = bytes(4)
        result = self.run_read()
        self.assertEqual(result["status"], "candidate-no-nonzero-child")
        self.assertEqual(result["rawComponentDword2B8"], 42)
        self.assertIsNone(result["isCasting"])

    def test_missing_slot_does_not_read_component(self):
        self.memory = {key: value for key, value in self.memory.items()
                       if key in ((self.base + cast.SELECTOR_RVA, 4), (self.entity + 0x21, 1))}
        self.memory[(self.entity + 0x21, 1)] = b"\xff"
        self.assertEqual(self.run_read()["status"], "candidate-component-absent")

    def test_wrong_build_does_not_read(self):
        self.assertEqual(self.run_read(lambda *_: self.fail("unexpected read"), "other")["reason"],
                         "unsupported-build")

    def test_bad_selector_and_bad_pointer_rejected(self):
        for index in (-1, 0x60):
            self.memory[(self.base + cast.SELECTOR_RVA, 4)] = struct.pack("<i", index)
            self.assertEqual(self.run_read()["reason"], "component-index-outside-selector-area")
        self.memory[(self.base + cast.SELECTOR_RVA, 4)] = struct.pack("<i", 9)
        self.memory[(self.component + 0x280, 8)] = struct.pack("<Q", 1)
        self.assertEqual(self.run_read()["reason"], "invalid-user-pointer")

    def test_changed_child_and_owner_fail_and_discard_partial_record(self):
        for changed_key in ((0x50008, 4), (self.entity + 0x78, 8),
                            (self.component + 0x280, 8), (self.component + 0x2B8, 4)):
            seen = set()

            def read(a, n):
                key = (a, n)
                data = self.memory[key]
                if key == changed_key and key in seen:
                    data = bytes(n)
                seen.add(key)
                return data

            result = self.run_read(read)
            self.assertEqual(result["reason"], "mutable-input-changed")
            self.assertEqual(result["children"], [])
            self.assertIsNone(result["rawComponentDword2B8"])

    def test_partial_read_is_explicit(self):
        self.assertEqual(self.run_read(lambda *_: b"")["reason"], "short-or-invalid-read")


if __name__ == "__main__":
    unittest.main()
