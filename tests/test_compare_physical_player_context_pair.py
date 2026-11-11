"""Offline regressions for same-epoch physical player-context comparisons."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import compare_physical_player_context_pair as pair


def sample():
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-player-context-candidate-sample/1",
        "status": "complete",
        "qualification": "candidate-only; changed-state, API correspondence and restart unverified",
        "observation": {
            "identity": {
                "processId": 44888, "processStartUtcTicks": 639299470183328173,
                "executablePath": r"C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe",
                "executableSha256": pair.BUILD_SHA,
                "moduleBaseAddress": 140701863903232, "moduleSize": 63164416,
            },
            "startedAtUtc": "2026-11-11T09:25:21.2408305+00:00",
            "completedAtUtc": "2026-11-11T09:25:21.2474764+00:00",
            "unitKey": 239816685251645959, "rawLevel": 45,
            "levelStatus": "numeric-getter-and-presentation-candidate",
            "rawCombat": 0, "combatStatus": "raw-byte-candidate",
            "combatCandidate": False, "rawCalling": 1,
            "callingCandidate": "warrior", "rawFallbackKey": 0,
            "targetStatus": "raw-getter-zero-candidate",
            "targetKeyCandidate": 0, "targetUnitIdCandidate": None,
            "qualification": "candidate-only; changed-state, API correspondence and restart unverified",
        },
    }


def later():
    result = sample()
    result["observation"]["startedAtUtc"] = "2026-11-11T09:52:49.7138254+00:00"
    result["observation"]["completedAtUtc"] = "2026-11-11T09:52:49.7211019+00:00"
    return result


def target(report, key):
    report["observation"].update(rawFallbackKey=key, targetKeyCandidate=key,
                                 targetStatus="fallback-key-candidate",
                                 targetUnitIdCandidate=f"u{key:016X}")


class PhysicalContextPairTests(unittest.TestCase):
    def test_same_epoch_passive_self_key_stability_target_unknown(self):
        result = pair.compare(sample(), later(), "A" * 64, "B" * 64)
        self.assertTrue(result["selfKey"]["unchangedCandidate"])
        self.assertEqual(str(sample()["observation"]["unitKey"]),
                         result["selfKey"]["beforeCandidate"])
        self.assertIsNone(result["target"]["selectionChangedCandidate"])
        self.assertGreater(result["elapsedBetweenSamplesSeconds"], 1600)
        self.assertIn("candidate-only", result["qualification"])
        self.assertNotIn("entity", result)

    def test_changed_selected_target_is_candidate_only(self):
        first, second = sample(), later()
        target(first, 0x1234)
        target(second, 0x2345)
        result = pair.compare(first, second, "A" * 64, "B" * 64)
        self.assertTrue(result["selfKey"]["unchangedCandidate"])
        self.assertTrue(result["target"]["selectionChangedCandidate"])
        self.assertEqual("u0000000000001234", result["target"]["beforeIdCandidate"])

    def test_changed_self_key_is_flagged_not_relabelled_stable(self):
        second = later()
        second["observation"]["unitKey"] += 1
        result = pair.compare(sample(), second, "A" * 64, "B" * 64)
        self.assertFalse(result["selfKey"]["unchangedCandidate"])

    def test_partial_target_does_not_prove_selection_changed(self):
        second = later()
        target(second, 42)
        result = pair.compare(sample(), second, "A" * 64, "B" * 64)
        self.assertIsNone(result["target"]["selectionChangedCandidate"])

    def test_rejects_other_process_epoch_or_module(self):
        for key, new_value in (
            ("processId", 2), ("processStartUtcTicks", 777),
            ("moduleBaseAddress", 3), ("moduleSize", 1000),
            ("executableSha256", "0" * 64),
            ("executablePath", r"C:\Other\rift_x64.exe"),
        ):
            second = later()
            second["observation"]["identity"][key] = new_value
            with self.subTest(key=key), self.assertRaises(ValueError):
                pair.compare(sample(), second, "A" * 64, "B" * 64)

    def test_rejects_overlapping_or_reversed_or_non_utc(self):
        cases = (
            ("startedAtUtc", "2026-11-11T09:25:21.2408305Z"),
            ("startedAtUtc", "2026-11-11T09:25:19Z"),
            ("startedAtUtc", "2026-11-11T09:52:49"),
            ("completedAtUtc", "2026-11-11T09:20:00Z"),
        )
        for key, value in cases:
            second = later()
            second["observation"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                pair.compare(sample(), second, "A" * 64, "B" * 64)

    def test_rejects_inconsistent_target_and_duplicate_source(self):
        with self.assertRaisesRegex(ValueError, "reused-source"):
            pair.compare(sample(), later(), "A" * 64, "A" * 64)
        second = later()
        second["observation"]["targetUnitIdCandidate"] = "u0000000000000001"
        with self.assertRaises(ValueError):
            pair.compare(sample(), second, "A" * 64, "B" * 64)

    def test_rejects_incomplete_receipt_even_with_stale_observation(self):
        first, second = sample(), later()
        for status in ("blocked", "partial", None):
            first["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "incomplete-report"):
                pair.compare(first, second, "A" * 64, "B" * 64)

    def test_cannot_infer_target_selection_when_self_owner_changes(self):
        first, second = sample(), later()
        target(first, 0x1234)
        target(second, 0x2345)
        second["observation"]["unitKey"] += 1
        result = pair.compare(first, second, "A" * 64, "B" * 64)
        self.assertFalse(result["selfKey"]["unchangedCandidate"])
        self.assertIsNone(result["target"]["selectionChangedCandidate"])

    def test_source_hash_pinning_and_cli(self):
        with TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before.json", Path(tmp) / "after.json"
            before.write_text(json.dumps(sample()), encoding="utf-8")
            after.write_text(json.dumps(later()), encoding="utf-8")
            source, sha = pair.load(before)
            self.assertEqual(sample(), source)
            self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest().upper(), sha)
            with self.assertRaisesRegex(ValueError, "sha-mismatch"):
                pair.load(before, "0" * 64)
            self.assertEqual(0, pair.main([str(before), str(after),
                                           "--before-sha256", sha]))
            self.assertEqual(2, pair.main([str(before), str(after),
                                           "--after-sha256", "0" * 64]))


if __name__ == "__main__":
    unittest.main()
