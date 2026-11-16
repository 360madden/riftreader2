"""Offline regression checks against retained, SHA-pinned physical AMD evidence."""
from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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

    def attach_stats(self):
        """Make an independent synthetic one-shot fourth receipt after vitals."""
        summary = json.loads(self.summary.read_text())
        vitals = json.loads((self.home / "vitals.json").read_text())
        identity = vitals["identity"]
        last = datetime.fromisoformat(vitals["observations"][-1]["completedAtUtc"].replace("Z", "+00:00"))
        fields = (("armor", 37), ("powerAttack", 24), ("powerSpell", 32),
                  ("critAttack", 26), ("critSpell", 33))
        rows = []
        for i, (name, selector) in enumerate(fields):
            value = {"status": "raw-candidate", "rawSigned64": 100 + i,
                     "doubleCandidate": float(100 + i), "precision": "exact-integer-range"}
            rows.append({"name": name, "selector": selector, "mappedIndex": i,
                         "ordinary": value.copy(), "unbuffed": value.copy()})
        report = {"schemaVersion": 1, "contractVersion": "native-current-stats-candidate/1",
                  "status": "complete", "observation": {
                      "identity": identity,
                      "unitKey": int(summary["selfKeyCandidate"]),
                      "startedAtUtc": (last + timedelta(seconds=1)).isoformat(),
                      "completedAtUtc": (last + timedelta(seconds=2)).isoformat(),
                      "qualification": "raw typed stat candidates; API availability, units, freshness and restart unverified",
                      "stats": rows}}
        path = self.home / "stats.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        self.edit_summary(lambda x: x["sources"].update(stats={
            "path": str(path), "sourceSha256": digest, "samples": 1,
            "candidateValues": replay._native_values("stats", report)}))
        return report

    def test_optional_stats_source_replays_and_original_sources_remain(self):
        self.attach_stats()
        result = replay.verified_state(self.summary)
        self.assertEqual(set(result["sources"]), set(replay.state.KINDS) | {"stats"})
        self.assertEqual(result["sources"]["stats"]["samples"], 1)
        self.assertEqual(result["candidateValues"]["stats"]["selectorCount"], 5)

    def test_optional_stats_source_tamper_refused(self):
        self.attach_stats()
        self.edit_source("stats", lambda r: r["observation"].update(unitKey=12), repin=False)
        with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
            replay.verified_state(self.summary)

    def test_optional_stats_wrong_self_or_time_refused_even_when_rehashed(self):
        for field in ("self", "time"):
            with self.subTest(field=field):
                self.attach_stats()
                if field == "self":
                    self.edit_source("stats", lambda r: r["observation"].update(unitKey=12))
                    message = "stats-sample-owner"
                else:
                    self.edit_source("stats", lambda r: r["observation"].update(
                        startedAtUtc="2026-11-01T00:00:00Z"))
                    message = "stats-sample-time-order"
                with self.assertRaisesRegex(ValueError, message):
                    replay.verified_state(self.summary)

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

    def test_vitals_burst_build_pin_mismatch_rejected(self):
        # The source may be SHA-valid, but its saved derived burst must not
        # claim a different executable build than the exact process epoch.
        self.edit_summary(lambda x: x["sources"]["vitals"]["burstSummary"].update(
            sourceBuildSha256="F" * 64))
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

    def pair(self, *, same=False, overlap=False, changed=False, missing_health=False, stats=None):
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
        if stats is not None:
            row = {"name": "armor", "selector": 37, "mappedIndex": 0,
                   "ordinary": {"status": "raw-candidate", "rawSigned64": 100},
                   "unbuffed": {"status": "raw-candidate", "rawSigned64": 100}}
            first["candidateValues"]["stats"] = {
                "status": "candidate-only", "selectorCount": 1, "stats": [row]}
            second["candidateValues"]["stats"] = json.loads(
                json.dumps(first["candidateValues"]["stats"]))
            if stats == "changed":
                second["candidateValues"]["stats"]["stats"][0]["ordinary"]["rawSigned64"] = 106
            elif stats == "layout":
                second["candidateValues"]["stats"]["stats"][0]["mappedIndex"] = 1
            elif stats == "unavailable":
                second["candidateValues"]["stats"]["stats"][0]["ordinary"] = {
                    "status": "index-unavailable", "rawSigned64": None}
            elif stats == "missing":
                second["candidateValues"].pop("stats")
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



    def test_matching_raw_stat_slots_report_exact_candidate_deltas(self):
        stats = self.pair(stats="changed")["nativeStatsComparison"]
        self.assertEqual(stats["status"], "comparable-candidate")
        self.assertEqual((stats["rawValuesCompared"], stats["rawValuesChanged"]), (2, 1))
        self.assertEqual(stats["changed"], [{
            "name": "armor", "variant": "ordinary", "beforeRawSigned64": 100,
            "afterRawSigned64": 106, "rawNumericDifference": 6}])

    def test_selector_layout_change_never_claims_comparable_stats(self):
        self.assertEqual(self.pair(stats="layout")["nativeStatsComparison"],
                         {"status": "incompatible-selector-layout"})

    def test_missing_stats_or_unavailable_slots_never_invent_delta(self):
        self.assertEqual(self.pair()["nativeStatsComparison"]["status"], "not-captured")
        self.assertEqual(self.pair(stats="missing")["nativeStatsComparison"]["status"],
                         "not-captured")
        unknown = self.pair(stats="unavailable")["nativeStatsComparison"]
        self.assertEqual((unknown["rawValuesCompared"], unknown["rawValuesUnavailable"],
                          unknown["rawValuesChanged"]), (1, 1, 0))


    def test_pair_cli_reports_position_health_and_stats_without_null_placeholders(self):
        with patch.object(replay, "compare", return_value={
            "status": "candidate-only", "evidenceKind": "amd-physical-player-state-pair/1",
            "positionDeltaCandidate": {"x": -2.4, "y": -2.5, "z": 55.7},
            "planarDistanceCandidate": 55.8,
            "healthDeltaCandidate": 0,
            "nativeStatsComparison": {"status": "comparable-candidate",
                                      "rawValuesChanged": 1}}), \
             redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(replay.main([
                "--summary", "offline-before", "--after", "offline-after"]), 0)
        report = json.loads(printed.getvalue())
        self.assertEqual(report["nativeStatsComparison"]["rawValuesChanged"], 1)
        self.assertEqual(report["positionDeltaCandidate"]["z"], 55.7)
        self.assertEqual(report["planarDistanceCandidate"], 55.8)
        self.assertEqual(report["healthDeltaCandidate"], 0)
        for unused in ("sourceCount", "summarySha256", "captureCount"):
            self.assertNotIn(unused, report)


class HistoryUnitTests(unittest.TestCase):
    def sample(self, i, *, start=None, pid=42):
        return {
            "summarySha256": str(i), "target": {"processId": pid, "start": 100},
            "moduleBaseAddress": 1000, "moduleSize": 500,
            "selfKeyCandidate": "123",
            "firstStartedAtUtc": start or f"2026-11-12T12:00:{2*i:02d}+00:00",
            "lastCompletedAtUtc": f"2026-11-12T12:00:{2*i+1:02d}+00:00",
            "candidateValues": {
                "position": {"x": float(i * 3), "y": 3.0, "z": float(i * 4)},
                "vitals": {"health": {"status": "calculated-candidate",
                                      "current": 100 - 5 * i}},
            },
        }

    def test_three_capture_history_distance_and_health(self):
        from unittest.mock import patch
        with patch.object(replay, "verified_state",
                          side_effect=[self.sample(i) for i in range(3)]):
            result = replay.history(["one", "two", "three"])
        self.assertEqual(result["captureCount"], 3)
        self.assertEqual([s["planarDistanceCandidate"] for s in result["segments"]], [5, 5])
        self.assertEqual(result["sumPlanarChordsCandidate"], 10)
        self.assertEqual(result["netPositionDeltaCandidate"], {"x": 6, "y": 0, "z": 8})
        self.assertEqual((result["healthObservedCount"], result["healthMinCandidate"],
                          result["healthMaxCandidate"]), (3, 90, 100))
        self.assertIn("NOT actual travel", result["qualification"])
        self.assertEqual(result["nativeStatsHistory"]["status"], "not-comparable")

    def test_history_rolls_up_changed_stats_without_inventing_missing_intervals(self):
        captures = [self.sample(i) for i in range(3)]
        for index, capture in enumerate(captures):
            capture["candidateValues"]["stats"] = {
                "status": "candidate-only", "selectorCount": 1,
                "stats": [{"name": "armor", "selector": 37, "mappedIndex": 20,
                           "ordinary": {"status": "raw-candidate", "rawSigned64": 100 + index * 3},
                           "unbuffed": {"status": "raw-candidate", "rawSigned64": 100}}],
            }
        with patch.object(replay, "verified_state", side_effect=captures):
            complete = replay.history(["a", "b", "c"])["nativeStatsHistory"]
        self.assertEqual(complete["status"], "comparable-candidate")
        self.assertEqual((complete["comparableSegments"], complete["rawValuesCompared"],
                          complete["rawValuesChanged"]), (2, 4, 2))
        self.assertEqual([row["segmentIndex"] for row in complete["changed"]], [1, 2])
        self.assertEqual([row["rawNumericDifference"] for row in complete["changed"]], [3, 3])

        incomplete = json.loads(json.dumps(captures))
        incomplete[2]["candidateValues"].pop("stats")
        with patch.object(replay, "verified_state", side_effect=incomplete):
            partial = replay.history(["a", "b", "c"])["nativeStatsHistory"]
        self.assertEqual(partial["status"], "partial-candidate")
        self.assertEqual((partial["comparableSegments"], partial["rawValuesCompared"],
                          partial["rawValuesChanged"]), (1, 2, 1))
        self.assertEqual([row["segmentIndex"] for row in partial["changed"]], [1])

    def test_history_rejects_overlap(self):
        from unittest.mock import patch
        with patch.object(replay, "verified_state",
                          side_effect=[self.sample(0), self.sample(1),
                                       self.sample(2, start="2026-11-12T12:00:03+00:00")]):
            with self.assertRaisesRegex(ValueError, "captures-overlap-or-reversed"):
                replay.history(["a", "b", "c"])

    def test_history_rejects_changed_process_epoch(self):
        from unittest.mock import patch
        with patch.object(replay, "verified_state",
                          side_effect=[self.sample(0), self.sample(1, pid=99)]):
            with self.assertRaisesRegex(ValueError, "owner-or-epoch-changed"):
                replay.history(["a", "b"])

    def test_history_rejects_replay_and_out_of_bounds(self):
        from unittest.mock import patch
        with self.assertRaisesRegex(ValueError, "history-count-out-of-bounds"):
            replay.history(["a"])
        with patch.object(replay, "verified_state",
                          side_effect=[self.sample(0), self.sample(0)]):
            with self.assertRaisesRegex(ValueError, "same-source"):
                replay.history(["a", "a"])

    def test_history_handles_missing_health_without_fabrication(self):
        from unittest.mock import patch
        missing = self.sample(1)
        missing["candidateValues"]["vitals"]["health"] = {
            "status": "unavailable", "current": None}
        with patch.object(replay, "verified_state",
                          side_effect=[self.sample(0), missing, self.sample(2)]):
            result = replay.history(["a", "b", "c"])
        self.assertEqual(result["healthObservedCount"], 2)
        self.assertEqual(result["healthMinCandidate"], 90)
        self.assertIsNone(result["segments"][0]["healthDeltaCandidate"])
        self.assertIsNone(result["segments"][1]["healthDeltaCandidate"])


if __name__ == "__main__":
    unittest.main()
