"""Synthetic PE64 tests for offline native API string-to-code references."""
from __future__ import annotations

import hashlib
import struct
import unittest

from scripts.find_native_api_xrefs import scan_image


def fixture() -> bytes:
    data = bytearray(0x800)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", data, 0x84, 0x8664)  # AMD64
    struct.pack_into("<H", data, 0x86, 2)  # section count
    struct.pack_into("<H", data, 0x94, 0xF0)  # optional header length
    struct.pack_into("<H", data, 0x98, 0x20B)  # PE32+
    table = 0x80 + 24 + 0xF0
    for i, (name, rva, raw_at) in enumerate((
        (b".text", 0x1000, 0x200),
        (b".rdata", 0x2000, 0x400),
    )):
        offset = table + 40 * i
        data[offset:offset + 8] = name.ljust(8, b"\x00")
        struct.pack_into("<IIII", data, offset + 8,
                         0x200, rva, 0x200, raw_at)
    code_at, code_rva = 0x230, 0x1030
    target_rva = 0x2020
    data[code_at:code_at + 3] = b"\x4C\x8D\x05"
    struct.pack_into("<i", data, code_at + 3,
                     target_rva - (code_rva + 7))
    data[0x420:0x427] = b"coordX\x00"
    data[0x450:0x45D] = b"prefixcoordX\x00"  # suffix match ignored
    return bytes(data)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class NativeApiXrefTests(unittest.TestCase):
    def test_exact_literal_and_rip_lea(self):
        data = fixture()
        result = scan_image(data, sha(data), ["coordX", "coordY"])
        self.assertEqual("0x2020", result["fields"][0]["literalRvas"][0])
        self.assertEqual([], result["fields"][1]["literalRvas"])
        self.assertEqual(1, len(result["references"]))
        self.assertEqual("0x1030", result["references"][0]["instructionRva"])
        self.assertEqual("4c8d05e90f0000",
                         result["references"][0]["instructionBytes"])
        self.assertIn("static-opcode-candidate", result["qualification"])

    def test_scope_filters_code_not_literal(self):
        data = fixture()
        result = scan_image(data, sha(data), ["coordX"], 0x1031, 0x1100)
        self.assertEqual([], result["references"])
        self.assertEqual(["0x2020"], result["fields"][0]["literalRvas"])

    def test_wrong_hash_rejected_before_analysis(self):
        data = fixture()
        with self.assertRaisesRegex(ValueError, "executable-sha-mismatch"):
            scan_image(data, "0" * 64, ["coordX"])

    def test_bad_file_and_bad_fields_fail_closed(self):
        empty = b"\x00" * 0x800
        with self.assertRaisesRegex(ValueError, "pe-dos-signature-invalid"):
            scan_image(empty, sha(empty), ["coordX"])
        data = fixture()
        for fields in ([], ["coordX", "coordX"], ["coord;X"]):
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    scan_image(data, sha(data), fields)

    def test_bogus_section_bounds_rejected(self):
        data = bytearray(fixture())
        table = 0x80 + 24 + 0xF0
        struct.pack_into("<I", data, table + 40 + 20, len(data) - 1)
        with self.assertRaisesRegex(ValueError, "pe-section-outside-file"):
            scan_image(bytes(data), sha(bytes(data)), ["coordX"])


if __name__ == "__main__":
    unittest.main()
