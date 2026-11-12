"""Offline regression checks against retained, SHA-pinned physical AMD evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from scripts import replay_physical_player_state as replay

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "artifacts" / "physical-state-20261112-1117-69312"


class StateReplayTests(unittest.TestCase):
    def setUp(self):
        if not (FIXTURE / "summary.json").is_file():
            self.skipTest("Retained local physical artifact unavailable; never substitute another host")
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        for name in ("summary.json", "player-context.json", "position.json", "vitals.json"):
            shutil.copyfile(FIXTURE / name, self.home / name)
        self.summary = self.home / "summary.json"

    def edit_summary(self, update):
        report = json.loads(self.summary.read_text())
        update(report)
        self.summary.write_text(json.dumps(report), encoding="utf-8")
        return report

    def edit_source(self, kind, update, repin=True):
        path = self.home / (kind + ".json")
        report = json.loads(path.read_text())
        update(report)
        path.write_text(json.dumps(report), encoding="utf-8")
        if repin:
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            self.edit_summary(lambda s: s["sources"][kind].update(sourceSha256=digest))
        return report

    def test_original_composite_three_reader_sources_replay(self):
        result = replay.verified_state(self.summary)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(set(result["sources"]), {"player-context", "position", "vitals"})
        self.assertEqual([result["sources"][k]["samples"] for k in replay.state.KINDS],
                         [3, 3, 3])
        self.assertEqual(result["candidateValues"]["position"]["x"], 7421.6724)
        self.assertEqual(result["candidateValues"]["vitals"]["health"]["current"], 18208)
        self.assertIn("not atomic", result["qualification"])

    def test_replay_does_not_select_or_read_running_process(self):
        from unittest.mock import patch
        with (patch.object(replay.state.physical_rift, "select_physical") as select,
              patch.object(replay.state.physical_rift, "read_native") as read):
            replay.verified_state(self.summary)
            select.assert_not_called()
            read.assert_not_called()

    def test_unpinned_source_tamper_rejected(self):
        self.edit_source("position", lambda x: x["observations"][-1].update(x=7444), repin=False)
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            replay.verified_state(self.summary)

    def test_rehashed_source_cannot_disagree_with_saved_projection(self):
        self.edit_source("position", lambda x: x["observations"][-1].update(x=7444))
        with self.assertRaisesRegex(ValueError, "position-candidate-projection-mismatch"):
            replay.verified_state(self.summary)

    def test_rehashed_changed_identity_rejected(self):
        self.edit_source("position", lambda x: x["identity"].update(processId=99111))
        with self.assertRaisesRegex(ValueError, "position-invalid-source-owner"):
            replay.verified_state(self.summary)

    def test_rehashed_changed_sample_owner_rejected(self):
        self.edit_source("position", lambda x: x["observations"][1].update(unitKey="555"))
        with self.assertRaisesRegex(ValueError, "position-sample-owner"):
            replay.verified_state(self.summary)

    def test_rehashed_reordered_time_rejected(self):
        self.edit_source("position", lambda x: x["observations"][1].update(
            startedAtUtc="2026-11-12T16:14:30+00:00"))
        with self.assertRaisesRegex(ValueError, "position-sample-time-order"):
            replay.verified_state(self.summary)

    def test_summary_owner_change_rejected(self):
        self.edit_summary(lambda x: x["target"].update(processStartUtcTicks="11"))
        with self.assertRaisesRegex(ValueError, "player-context-invalid-source-owner"):
            replay.verified_state(self.summary)

    def test_summary_renamed_path_rejected(self):
        self.edit_summary(lambda x: x["sources"]["position"].update(
            path=r"C:\\otherhost\\other.json"))
        with self.assertRaisesRegex(ValueError, "position-invalid-source-pin"):
            replay.verified_state(self.summary)

    def test_rehashed_vitals_burst_pin_rejected(self):
        self.edit_summary(lambda x: x["sources"]["vitals"]["burstSummary"].update(
            sourceReportSha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "vitals-burst-pin-mismatch"):
            replay.verified_state(self.summary)

    def test_saved_candidate_value_tamper_rejected(self):
        self.edit_summary(lambda x: x["sources"]["position"]["candidateValues"].update(x=999))
        with self.assertRaisesRegex(ValueError, "position-candidate-projection-mismatch"):
            replay.verified_state(self.summary)

    def test_duplicate_json_key_rejected(self):
        original = self.summary.read_text()
        self.summary.write_text(original.replace('"schemaVersion": 1,',
                                                '"schemaVersion": 1, "schemaVersion": 1,', 1))
        with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
            replay.verified_state(self.summary)

    def test_identical_pair_refused(self):
        with self.assertRaisesRegex(ValueError, "same-source"):
            replay.compare(self.summary, self.summary)

    def test_missing_summary_is_unavailable(self):
        with self.assertRaisesRegex(ValueError, "source-unavailable"):
            replay.verified_state(self.home / "missing.json")


class ComparisonUnitTests(unittest.TestCase):
    """Synthetic pair mathematics; independent of ignored local artifacts."""

    def pair(self, *, same=False, overlap=False, changed=False, missing_health=False):
        from unittest.mock import patch
        first = {
            "summarySha256": "A", "target": {"processId": 42, "start": 100},
            "moduleBaseAddress": 1000, "moduleSize": 500,
            "selfKeyCandidate": "123",
            "lastCompletedAtUtc": "2026-11-12T12:00:01+00:00",
            "candidateValues": {"position": {"x": 10.0, "y": 3.0, "z": 11.0},
                                "vitals": {"health": {"status": "calculated-candidate", "current": 100}}},
        }
        second = json.loads(json.dumps(first))
        second.update(summarySha256="A" if same else "B",
                      firstStartedAtUtc=("2026-11-12T12:00:01+00:00" if overlap
                                         else "2026-11-12T12:00:02+00:00"))
        if changed:
            second["target"]["start"] = 101
        second["candidateValues"]["position"].update(x=13.0, z=15.0)
        second["candidateValues"]["vitals"]["health"] = (
            {"status": "unavailable", "current": None} if missing_health
            else {"status": "calculated-candidate", "current": 85})
        with patch.object(replay, "verified_state", side_effect=[first, second]):
            return replay.compare("first", "second")

    def test_position_and_health_deltas(self):
        result = self.pair()
        self.assertEqual(result["positionDeltaCandidate"], {"x": 3.0, "y": 0.0, "z": 4.0})
        self.assertEqual(result["planarDistanceCandidate"], 5.0)
        self.assertEqual(result["healthDeltaCandidate"], -15)

    def test_changed_epoch_rejected(self):
        with self.assertRaisesRegex(ValueError, "owner-or-epoch-changed"):
            self.pair(changed=True)

    def test_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "captures-overlap-or-reversed"):
            self.pair(overlap=True)

    def test_unavailable_health_not_invented(self):
        self.assertIsNone(self.pair(missing_health=True)["healthDeltaCandidate"])

    def test_same_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "same-source"):
            self.pair(same=True)


if __name__ == "__main__":
    unittest.main()
