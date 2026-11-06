"""Offline safety/argument checks for the current-build native HP scout."""
from __future__ import annotations

import unittest

from scripts.scout_current_native_health import BUILD, GUEST, run


class NativeCurrentHealthScoutTests(unittest.TestCase):
    def test_rejects_unsupported_lab_before_guest_access(self):
        with self.assertRaisesRegex(ValueError, "invalid-arguments"):
            run("lab3", 8164, 639290507142219120, 2512, 18208)

    def test_rejects_zero_or_negative_player_reference(self):
        for value in (0, -1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "invalid-arguments"):
                run("lab1", 8164, 639290507142219120, 2512, value)

    def test_rejects_noncanonical_start_address_before_guest_access(self):
        for address in ("0x0", "0x1000", "0x00010000", "0xabcdef",
                        "0x10000;Get-Process", "0xFFFFFFFFFFFFFFFF"):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, "invalid-start-address"):
                run("lab2", 7012, 639290507554340644, 4300, 10635, address)

    def test_script_is_read_only_and_pinned_to_native_scout(self):
        self.assertIn("scout-values-native", GUEST)
        self.assertIn("game-identity-mismatch", GUEST)
        self.assertIn("game-build-mismatch", GUEST)
        self.assertIn("native-reader-unavailable", GUEST)
        self.assertIn("native-value-scout-request/1", GUEST)
        self.assertIn("maxScanBytes=1073741824", GUEST)
        for forbidden in ("WriteProcessMemory", "VirtualProtectEx", "Command.Input",
                          "SendKeys", "SetForegroundWindow", "MoveMouse",
                          " /reloadui", " /rr2bind"):
            self.assertNotIn(forbidden, GUEST)
        self.assertEqual(64, len(BUILD))


if __name__ == "__main__":
    unittest.main()
