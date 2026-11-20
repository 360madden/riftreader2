"""Saved native zone-bracket replay regression tests (no RIFT process access).

The retained physical source bundles live under ignored artifacts. If those
machine-local bytes are missing, tests skip rather than fabricate live evidence.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import replay_physical_player_state as replay

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "artifacts" / "physical-state-postrestart-20261119-2226"
OLD = ROOT / "artifacts" / "physical-state-zonebracket-20261118-1629"
NAMES = ("zone-before", "player-context", "position", "vitals", "stats", "zone-after")


class ZoneBracketReplayTests(unittest.TestCase):
    def setUp(self):
        if any(not (NEW / (name + ".json")).is_file() for name in NAMES + ("summary",)):
            self.skipTest("Retained physical post-restart bundle absent; do not synthesize live provenance")
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in NAMES + ("summary",):
            shutil.copyfile(NEW / (name + ".json"), self.root / (name + ".json"))
        self.summary_path = self.root / "summary.json"

    def modify_summary(self, change):
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        change(summary)
        self.summary_path.write_text(json.dumps(summary), encoding="utf-8")

    def modify_source(self, kind, change, *, repin=True, reproject=False):
        source_path = self.root / (kind + ".json")
        source = json.loads(source_path.read_text(encoding="utf-8"))
        change(source)
        source_path.write_text(json.dumps(source), encoding="utf-8")
        if repin:
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
            def set_pin(summary):
                summary["sources"][kind]["sourceSha256"] = digest
                if reproject:
                    summary["sources"][kind]["candidateValues"] = replay._native_values(
                        "zone-context", source)
                if kind in ("zone-before", "zone-after"):
                    summary["zoneBracketCandidate"][
                        "beforeSourceSha256" if kind == "zone-before" else "afterSourceSha256"
                    ] = digest
            self.modify_summary(set_pin)

    def test_replays_real_six_source_restart_bundle(self):
        result = replay.verified_state(self.summary_path)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(set(result["sources"]), set(NAMES))
        self.assertEqual(result["zoneBracketCandidate"]["status"], "matching-candidates")
        self.assertEqual(result["zoneBracketCandidate"]["zoneIdCandidate"], "z0000000CB7B53FD7")
        self.assertEqual(result["zoneBracketCandidate"]["worldInstanceStatus"], "unavailable")
        self.assertEqual(result["candidateValues"]["stats"]["selectorCount"], 20)
        self.assertEqual(result["selfKeyCandidate"], "239816685251645959")

    def test_replays_historical_five_source_zone_bundle(self):
        if any(not (OLD / (name + ".json")).is_file()
               for name in ("zone-before", "player-context", "position", "vitals", "zone-after", "summary")):
            self.skipTest("Earlier physical zone-bracket source bundle absent")
        original = replay.verified_state(OLD / "summary.json")
        self.assertEqual(original["zoneBracketCandidate"]["status"], "matching-candidates")
        self.assertEqual(original["zoneBracketCandidate"]["zoneIdCandidate"], "z487C9102D2EA79BE")
        self.assertNotIn("stats", original["sources"])

    def test_source_hash_tamper_is_refused(self):
        self.modify_source("zone-after", lambda row: row["observation"].update(rawZoneKey=13),
                           repin=False)
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            replay.verified_state(self.summary_path)

    def test_rehashed_other_epoch_is_refused(self):
        self.modify_source("zone-after", lambda row:
                           row["observation"]["identity"].update(processId=100001))
        with self.assertRaisesRegex(ValueError, "zone-after-invalid-source-owner"):
            replay.verified_state(self.summary_path)

    def test_rehashed_wrong_order_is_refused(self):
        self.modify_source("zone-after", lambda row:
                           row["observation"].update(
                               startedAtUtc="2026-11-20T03:00:01Z",
                               completedAtUtc="2026-11-20T03:00:02Z"))
        with self.assertRaisesRegex(ValueError, "zone-after-sample-time-order"):
            replay.verified_state(self.summary_path)

    def test_unqualified_summary_claim_is_refused(self):
        self.modify_summary(lambda row: row["zoneBracketCandidate"].update(
            worldInstanceStatus="qualified"))
        with self.assertRaisesRegex(ValueError, "zone-bracket-summary-mismatch"):
            replay.verified_state(self.summary_path)

    def test_injected_zone_id_into_summary_is_refused(self):
        self.modify_summary(lambda row: row["zoneBracketCandidate"].update(
            zoneIdCandidate="zFFFFFFFF00000000"))
        with self.assertRaisesRegex(ValueError, "zone-bracket-summary-mismatch"):
            replay.verified_state(self.summary_path)

    def test_fake_bracket_without_two_sources_is_refused(self):
        self.modify_summary(lambda row: row["sources"].pop("zone-after"))
        with self.assertRaisesRegex(ValueError, "invalid-summary-owner"):
            replay.verified_state(self.summary_path)

    def test_false_multi_sample_zone_source_is_refused(self):
        self.modify_summary(lambda row: row["sources"]["zone-before"].update(samples=2))
        with self.assertRaisesRegex(ValueError, "zone-before-invalid-source-pin"):
            replay.verified_state(self.summary_path)

    def test_native_source_projection_mismatch_is_refused_even_with_pin(self):
        self.modify_source("zone-after", lambda row: row["observation"].update(
            rawZoneKey=0), repin=True, reproject=False)
        with self.assertRaisesRegex(ValueError, "invalid-native-zone-context-id|zone-after-candidate-projection-mismatch"):
            replay.verified_state(self.summary_path)

    def test_does_not_probe_the_running_game(self):
        with (patch.object(replay.state.physical_rift, "select_physical") as selected,
              patch.object(replay.state.physical_rift, "read_native") as read):
            result = replay.verified_state(self.summary_path)
            self.assertEqual(result["zoneBracketCandidate"]["status"], "matching-candidates")
            selected.assert_not_called()
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
