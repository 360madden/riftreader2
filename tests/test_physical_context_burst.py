"""Offline validation of physical-only native player-context bursts."""
from __future__ import annotations

from copy import deepcopy
import unittest

from scripts.physical_rift import _native_values


QUALIFICATION = "candidate-only; changed-state, API correspondence and restart unverified"


def row(start, key=239816685251645959):
    return {
        "identity": {
            "processId": 44888,
            "processStartUtcTicks": 639299470183328173,
            "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
            "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8",
            "moduleBaseAddress": 140701863903232,
            "moduleSize": 63164416,
        },
        "startedAtUtc": f"2026-11-11T11:33:{start:02d}+00:00",
        "completedAtUtc": f"2026-11-11T11:33:{start:02d}.050+00:00",
        "unitKey": key,
        "rawLevel": 45,
        "levelStatus": "numeric-getter-and-presentation-candidate",
        "rawCombat": 0,
        "combatStatus": "raw-byte-candidate",
        "combatCandidate": False,
        "rawCalling": 1,
        "callingCandidate": "warrior",
        "rawFallbackKey": 0,
        "targetStatus": "raw-getter-zero-candidate",
        "targetKeyCandidate": 0,
        "targetUnitIdCandidate": None,
        "qualification": QUALIFICATION,
    }


def burst():
    rows = [row(3), row(4), row(5)]
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-player-context-candidate-burst/1",
        "status": "complete",
        "qualification": QUALIFICATION,
        "identity": deepcopy(rows[0]["identity"]),
        "requestedSamples": 3,
        "completedSamples": 3,
        "observation": deepcopy(rows[-1]),
        "observations": rows,
    }


def set_target(row_data, key):
    row_data.update({
        "rawFallbackKey": key,
        "targetKeyCandidate": key,
        "targetStatus": "fallback-key-candidate",
        "targetUnitIdCandidate": f"u{key:016X}",
    })


class PhysicalContextBurstTests(unittest.TestCase):
    def test_valid_zero_target_burst_is_not_claimed_as_change(self):
        values = _native_values("player-context", burst())
        self.assertEqual(3, values["sampleCount"])
        self.assertTrue(values["selfKeyStableCandidate"])
        self.assertEqual(0, values["comparableTargetPairs"])
        self.assertEqual(0, values["changedTargetPairsCandidate"])
        self.assertEqual([None, None, None], values["targetIdSeriesCandidate"])
        self.assertEqual("warrior", values["calling"]["nameCandidate"])

    def test_two_nonzero_targets_can_be_compared_without_qualifying_selection(self):
        report = burst()
        for index, key in enumerate((0x1234, 0x1234, 0x5678)):
            set_target(report["observations"][index], key)
        report["observation"] = deepcopy(report["observations"][-1])
        result = _native_values("player-context", report)
        self.assertEqual(2, result["comparableTargetPairs"])
        self.assertEqual(1, result["changedTargetPairsCandidate"])
        self.assertEqual("u0000000000005678", result["target"]["unitIdCandidate"])

    def test_discontinuity_in_target_availability_not_counted_as_change(self):
        report = burst()
        set_target(report["observations"][-1], 0x8888)
        report["observation"] = deepcopy(report["observations"][-1])
        self.assertEqual(0, _native_values("player-context", report)["comparableTargetPairs"])

    def test_rejects_incomplete_or_contradictory_burst(self):
        for mutation in ("count", "last", "epoch", "owner", "overlap", "target"):
            report = burst()
            if mutation == "count":
                report["completedSamples"] = 2
            elif mutation == "last":
                report["observation"]["rawLevel"] = 46
            elif mutation == "epoch":
                report["observations"][1]["identity"]["processId"] = 123
            elif mutation == "owner":
                report["observations"][1]["unitKey"] += 1
            elif mutation == "overlap":
                report["observations"][1]["startedAtUtc"] = "2026-11-11T11:33:02+00:00"
            elif mutation == "target":
                report["observations"][1]["targetUnitIdCandidate"] = "u0000000000009999"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _native_values("player-context", report)


if __name__ == "__main__":
    unittest.main()
