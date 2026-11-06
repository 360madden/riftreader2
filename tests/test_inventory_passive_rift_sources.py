"""Offline safety checks for passive, non-addon RIFT file inventory."""
from __future__ import annotations

import unittest

from scripts.inventory_passive_rift_sources import GUEST, ps_literal, run


GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


class PassiveRiftSourcesTests(unittest.TestCase):
    def test_rejects_wrong_lab_or_identity_without_guest_access(self):
        for lab, pid, ticks in (
            ("lab3", 8164, 639290507142219120),
            ("lab1", 0, 639290507142219120),
            ("lab1", -1, 639290507142219120),
            ("lab1", 8164, 0),
        ):
            with self.subTest(lab=lab, pid=pid, ticks=ticks), self.assertRaisesRegex(
                    ValueError, "invalid-lab-or-game-identity"):
                run(lab, pid, ticks, GAME_SHA)

    def test_sha_must_be_exactly_hex64(self):
        for value in ("", "0" * 63, "g" * 64, GAME_SHA + " trailing"):
            with self.subTest(value=value[:10]), self.assertRaisesRegex(
                    ValueError, "invalid-game-executable-sha"):
                run("lab1", 8164, 639290507142219120, value)

    def test_powershell_literal_quotes_paths_without_expressions(self):
        self.assertEqual("'C:\\RIFT\\foo'", ps_literal("C:\\RIFT\\foo"))
        self.assertEqual("'O''Brien'", ps_literal("O'Brien"))
        self.assertEqual("'$($env:USERNAME)'", ps_literal("$($env:USERNAME)"))

    def test_guest_scopes_only_known_paths_and_config_keys(self):
        self.assertIn("game-identity-mismatch", GUEST)
        self.assertIn("Get-FileHash", GUEST)
        self.assertIn("CombatLog.txt", GUEST)
        self.assertIn("telara.db", GUEST)
        self.assertIn("DocumentsDirectory", GUEST)
        self.assertIn("LogCombatConsole", GUEST)
        self.assertIn("Get-Content -LiteralPath $location.path -TotalCount 500", GUEST)
        self.assertIn("limitation=", GUEST)
        for prohibited in ("WriteProcessMemory", "VirtualProtectEx", "Stop-Process",
                           "Start-Process", "Set-ItemProperty", "SendKeys",
                           "/combatlog", "/reloadui", "/rr2bind", "Get-ChildItem -Recurse"):
            self.assertNotIn(prohibited, GUEST)


if __name__ == "__main__":
    unittest.main()

