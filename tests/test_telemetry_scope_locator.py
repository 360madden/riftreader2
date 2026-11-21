"""Offline proofs for bounded, map-aware Telemetry marker location."""
from __future__ import annotations

import unittest

from scripts import telemetry_scope_locator as locate

CHUNK = locate.CHUNK
BASE = 0x13000000
MARKER = b"RIFTTLM1|{"


class FakeReader:
    def __init__(self, areas):
        # Areas are (start, bytearray); gaps must never be bridged.
        self.areas = sorted(areas)
        self.calls = []

    def readable_private_regions(self):
        return [(start, start + len(raw)) for start, raw in self.areas]

    def read(self, addr, length):
        self.calls.append((addr, length))
        for start, raw in self.areas:
            if start <= addr < start + len(raw):
                return bytes(raw[addr-start:addr-start+length])
        return b""


def area(size, markers):
    raw = bytearray(size)
    for offset in markers:
        raw[offset:offset+len(MARKER)] = MARKER
    return raw


class LocatorTests(unittest.TestCase):
    def test_nonadjacent_valid_scopes_found_without_a_cached_address(self):
        first = BASE
        second = BASE + 4 * CHUNK
        reader = FakeReader([
            (first, area(CHUNK * 2, [64, CHUNK + 97])),
            (second, area(CHUNK * 2, [82, CHUNK + 31])),
        ])
        valid = {first + 64, second + 82, second + CHUNK + 31}
        found = locate.discover(
            reader, marker=MARKER, scan_bytes=CHUNK,
            validate_at=lambda address: address in valid,
            max_scopes=3, max_bytes=4 * CHUNK)
        self.assertEqual(found["status"], "scope-locations-candidate")
        self.assertEqual(found["candidateStartAddresses"],
                         [f"0x{first:X}", f"0x{second:X}",
                          f"0x{second + CHUNK:X}"])
        self.assertEqual(found["scannedBytes"], 4 * CHUNK)
        self.assertEqual(found["markerHits"], 4)
        self.assertEqual(found["validatedMarkerCandidates"], 3)
        self.assertEqual(found["shortReads"], 0)
        self.assertFalse(found["searchExhausted"])
        self.assertIn("candidate location only", found["qualification"])

    def test_cross_chunk_boundary_marker_is_not_lost(self):
        start = BASE
        marker_offset = CHUNK - 4
        reader = FakeReader([(start, area(CHUNK * 2, [marker_offset]))])
        found = locate.discover(
            reader, marker=MARKER, scan_bytes=CHUNK,
            validate_at=lambda address: address == start + marker_offset,
            max_scopes=1, max_bytes=2 * CHUNK)
        self.assertEqual(found["markerHits"], 1)
        self.assertEqual(found["candidateStartAddresses"], [f"0x{start:X}"])

    def test_source_rejected_marker_is_not_promoted(self):
        reader = FakeReader([(BASE, area(CHUNK, [100]))])
        result = locate.discover(reader, marker=MARKER, scan_bytes=CHUNK,
                                 validate_at=lambda address: False, max_bytes=CHUNK)
        self.assertEqual(result["status"], "unqualified")
        self.assertEqual(result["candidateStartAddresses"], [])
        self.assertEqual(result["validatedMarkerCandidates"], 0)

    def test_budget_cutoff_has_no_global_absence_claim(self):
        reader = FakeReader([
            (BASE, area(2 * CHUNK, [])),
            (BASE + 4 * CHUNK, area(CHUNK, [100])),
        ])
        found = locate.discover(reader, marker=MARKER, scan_bytes=CHUNK,
                                validate_at=lambda address: True, max_bytes=CHUNK)
        self.assertEqual(found["status"], "unqualified")
        self.assertEqual(found["scannedBytes"], CHUNK)
        self.assertTrue(found["searchExhausted"])

    def test_invalid_regions_or_limits_fail_closed(self):
        invalid = FakeReader([(BASE, area(CHUNK, [])),
                              (BASE, area(CHUNK, []))])
        with self.assertRaisesRegex(ValueError, "invalid-region"):
            locate.discover(invalid, marker=MARKER, scan_bytes=CHUNK,
                            validate_at=lambda address: True)
        for invalid_max_scopes in (0, 9, True, 1.5):
            with self.subTest(value=invalid_max_scopes):
                with self.assertRaisesRegex(ValueError, "invalid-budget"):
                    locate.discover(FakeReader([]), marker=MARKER, scan_bytes=CHUNK,
                                    validate_at=lambda address: True,
                                    max_scopes=invalid_max_scopes)


if __name__ == "__main__":
    unittest.main()
