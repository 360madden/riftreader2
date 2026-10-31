"""Offline safeguards for planning RIFT's writable PE-image memory scopes."""
from __future__ import annotations

import unittest

from scripts.plan_native_module_scopes import GUEST, run


SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


class NativeModuleScopeTests(unittest.TestCase):
    def test_invalid_lab_and_game_epoch_rejected_pre_guest(self):
        for lab, pid, ticks in (("lab3", 8164, 1), ("lab1", 0, 123),
                                ("lab2", -1, 123), ("lab1", 8164, 0)):
            with self.subTest(lab=lab, pid=pid), self.assertRaisesRegex(
                    ValueError, "invalid-lab-or-game-identity"):
                run(lab, pid, ticks, SHA)

    def test_sha_requires_exact_hex(self):
        for bad in ("0" * 63, "Z" * 64, "", SHA + "x"):
            with self.subTest(bad=bad[:8]), self.assertRaisesRegex(ValueError, "invalid-game-sha"):
                run("lab1", 8164, 639290507142219120, bad)

    def test_guest_reads_pe_headers_only_and_checks_bounds(self):
        self.assertIn("[uint64]", GUEST)
        self.assertNotIn("[ulong]", GUEST)
        for required in ("pe-dos-signature-invalid", "pe-signature-invalid", "pe-not-amd64",
                         "pe-section-table-truncated", "pe-section-outside-running-module",
                         "$virtualSize", "$rva", "$flags", "0x80000000",
                         "[IO.FileAccess]::Read", "game-identity-mismatch"):
            self.assertIn(required, GUEST)

    def test_no_process_memory_mutations_or_game_input(self):
        for prohibited in ("ReadProcessMemory", "WriteProcessMemory", "VirtualProtectEx",
                           "SendKeys", "Stop-Process", "Start-Process", "/combatlog",
                           "/rr2bind", "/reloadui", "Set-ItemProperty"):
            self.assertNotIn(prohibited, GUEST)


if __name__ == "__main__":
    unittest.main()

