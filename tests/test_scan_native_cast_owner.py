from __future__ import annotations

import unittest

from scripts import scan_native_cast_owner as scanner


class CastOwnerScannerTests(unittest.TestCase):
    def test_target_allowlist_separates_mutating_helper(self):
        self.assertEqual(scanner.KNOWN_TARGETS[0x5A9940],
                         "refcounting-smart-reference-copy")
        self.assertEqual(scanner.KNOWN_TARGETS[0x5A75C0], "child-280-id")
        self.assertEqual(scanner.PRODUCER_RVA, 0x91DED0)

    def test_wrong_image_is_rejected_before_pe_parsing(self):
        with self.assertRaisesRegex(ValueError, "executable-sha-mismatch"):
            scanner.scan(b"MZ")


if __name__ == "__main__":
    unittest.main()
