"""Synthetic PE64 tests for offline native API string-to-code references."""
from __future__ import annotations

import hashlib
import struct
import unittest

from scripts.find_native_api_xrefs import _assign_function_bounds, scan_image


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


def fixture_with_pdata(entries=((0x1020, 0x1040, 0x3010),)) -> bytes:
    data = bytearray(fixture())
    struct.pack_into("<H", data, 0x86, 3)  # Add a bounded .pdata section.
    struct.pack_into("<I", data, 0x98 + 108, 16)  # PE32+ data-directory count.
    struct.pack_into("<II", data, 0x98 + 112 + 3 * 8, 0x3000, len(entries) * 12)
    section_at = 0x80 + 24 + 0xF0 + 2 * 40
    data[section_at:section_at + 8] = b".pdata".ljust(8, bytes([0]))
    struct.pack_into("<IIII", data, section_at + 8, 0x200, 0x3000, 0x200, 0x600)
    for index, entry in enumerate(entries):
        struct.pack_into("<III", data, 0x600 + index * 12, *entry)
    struct.pack_into("<I", data, 0x98 + 56, 0x4000)  # SizeOfImage
    table = 0x80 + 24 + 0xF0
    for index, flags in enumerate((0x60000020, 0x40000040, 0x40000040)):
        struct.pack_into("<I", data, table + 40 * index + 36, flags)
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

    def test_function_bounds_from_actual_exception_directory(self):
        data = fixture_with_pdata()
        result = scan_image(data, sha(data), ["coordX"], include_function_bounds=True)
        self.assertEqual(1, result["exceptionFunctionDirectory"]["entryCount"])
        xref = result["references"][0]
        self.assertEqual("unique", xref["functionBoundaryStatus"])
        self.assertFalse(xref["instructionBoundaryVerified"])
        self.assertEqual([{"beginRva": "0x1020", "endRvaExclusive": "0x1040",
                           "unwindInfoRva": "0x3010", "offsetWithinFunction": 16}],
                         xref["runtimeFunctions"])
        self.assertIn("static-opcode-candidate", result["qualification"])

    def test_missing_exception_directory_does_not_invent_function(self):
        data = fixture()
        result = scan_image(data, sha(data), ["coordX"], include_function_bounds=True)
        self.assertEqual(0, result["exceptionFunctionDirectory"]["entryCount"])
        self.assertEqual("unmapped", result["references"][0]["functionBoundaryStatus"])
        self.assertEqual([], result["references"][0]["runtimeFunctions"])

    def test_overlap_kept_ambiguous_instead_of_selecting_winner(self):
        data = fixture_with_pdata(((0x1020, 0x1040, 0x3010),
                                   (0x1028, 0x1038, 0x3030)))
        result = scan_image(data, sha(data), ["coordX"], include_function_bounds=True)
        self.assertEqual("ambiguous", result["references"][0]["functionBoundaryStatus"])
        self.assertEqual(2, len(result["references"][0]["runtimeFunctions"]))

    def test_exception_directory_bounds_and_padding_rejected(self):
        original = bytearray(fixture_with_pdata())
        bounds = bytearray(original)
        struct.pack_into("<I", bounds, 0x98 + 112 + 3 * 8 + 4, 0x201)
        with self.assertRaisesRegex(ValueError, "pdata-directory-outside"):
            scan_image(bytes(bounds), sha(bytes(bounds)), ["coordX"], include_function_bounds=True)
        padded = bytearray(original)
        struct.pack_into("<I", padded, 0x98 + 112 + 3 * 8 + 4, 13)
        padded[0x60C] = 1
        with self.assertRaisesRegex(ValueError, "pdata-directory-nonzero-padding"):
            scan_image(bytes(padded), sha(bytes(padded)), ["coordX"], include_function_bounds=True)

    def test_unordered_runtime_entries_fail_closed(self):
        data = fixture_with_pdata(((0x1050, 0x1070, 0x3020),
                                   (0x1020, 0x1040, 0x3010)))
        with self.assertRaisesRegex(ValueError, "pdata-function-range-invalid"):
            scan_image(data, sha(data), ["coordX"], include_function_bounds=True)

    def test_invalid_unwind_sections_and_out_of_image_functions_rejected(self):
        cases = [
            (((0, 0xFFFFFFFF, 0),), "pdata-function-range-invalid"),
            (((0x2020, 0x2040, 0x3010),), "pdata-function-outside-executable"),
            (((0x1020, 0x1040, 0),), "pdata-unwind-unmapped"),
            (((0x1020, 0x1040, 0x3FFF),), "pdata-unwind-unmapped"),
        ]
        for entries, reason in cases:
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, reason):
                data = fixture_with_pdata(entries)
                scan_image(data, sha(data), ["coordX"], include_function_bounds=True)

    def test_pdata_directory_cannot_map_virtual_padding(self):
        data = bytearray(fixture_with_pdata())
        section_at = 0x80 + 24 + 0xF0 + 2 * 40
        struct.pack_into("<I", data, section_at + 8, 8)
        with self.assertRaisesRegex(ValueError, "pdata-directory-outside-mapped"):
            scan_image(bytes(data), sha(bytes(data)), ["coordX"], include_function_bounds=True)

    def test_overlapping_virtual_sections_are_rejected(self):
        data = bytearray(fixture_with_pdata())
        section_at = 0x80 + 24 + 0xF0 + 2 * 40
        struct.pack_into("<I", data, section_at + 12, 0x2000)
        struct.pack_into("<I", data, 0x98 + 112 + 3 * 8, 0x2000)
        with self.assertRaisesRegex(ValueError, "pdata-section-virtual-overlap"):
            scan_image(bytes(data), sha(bytes(data)), ["coordX"], include_function_bounds=True)

    def test_pdata_exact_boundaries_and_three_way_overlap(self):
        refs = [{"instructionRva": "0x1020"}, {"instructionRva": "0x1040"}]
        _assign_function_bounds(refs, [(0x1020, 0x1040, 0x3010)])
        self.assertEqual("unique", refs[0]["functionBoundaryStatus"])
        self.assertEqual(0, refs[0]["runtimeFunctions"][0]["offsetWithinFunction"])
        self.assertEqual("unmapped", refs[1]["functionBoundaryStatus"])
        refs = [{"instructionRva": "0x1030"}]
        _assign_function_bounds(refs, [(0x1000, 0x1050, 0x3010),
                                       (0x1010, 0x1020, 0x3020),
                                       (0x1020, 0x1040, 0x3030)])
        self.assertEqual("ambiguous", refs[0]["functionBoundaryStatus"])
        self.assertEqual(2, len(refs[0]["runtimeFunctions"]))

    def test_previous_byte_rex_heuristic_is_explicitly_unverified(self):
        data = bytearray(fixture_with_pdata(((0x1030, 0x1040, 0x3010),)))
        data[0x22F] = 0x48  # Adjacent prior instruction byte, not a REX prefix.
        data[0x230:0x236] = bytes([0x8D, 0x05]) + struct.pack("<i", 0x2020 - 0x1036)
        result = scan_image(bytes(data), sha(bytes(data)), ["coordX"], include_function_bounds=True)
        xref = result["references"][0]
        self.assertEqual("0x102F", xref["instructionRva"])  # Speculative shift.
        self.assertFalse(xref["instructionBoundaryVerified"])
        self.assertEqual("unmapped", xref["functionBoundaryStatus"])

    def test_bogus_section_bounds_rejected(self):
        data = bytearray(fixture())
        table = 0x80 + 24 + 0xF0
        struct.pack_into("<I", data, table + 40 + 20, len(data) - 1)
        with self.assertRaisesRegex(ValueError, "pe-section-outside-file"):
            scan_image(bytes(data), sha(bytes(data)), ["coordX"])


if __name__ == "__main__":
    unittest.main()
