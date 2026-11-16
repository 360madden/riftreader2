"""Focused offline tests for source-replayed native statistics / RR2A1 linkage."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import correlate_native_stats_rr2a1 as join


PLAYER_KEY = "239816685251645959"
PLAYER_ID = "u035400012FA2D207"
BUILD = "A" * 64


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lua_summary = self.root / "summary.json"
        self.before = self.root / "native-before" / "summary.json"
        self.after = self.root / "native-after" / "summary.json"
        self.first = self.root / "pass-01" / "scan" / "index.json"
        self.second = self.root / "pass-02" / "scan" / "index.json"
        for file in (self.before, self.after, self.first, self.second):
            file.parent.mkdir(parents=True)
            file.write_text(file.name + str(file.parent), encoding="utf-8")

        self.owner = {
            "hostName": "AMD-DESKTOP", "processId": 123,
            "processStartUtcTicks": "638000000000000001",
            "executableSha256": BUILD,
        }
        self.native = {
            "target": self.owner, "selfKeyCandidate": PLAYER_KEY,
            "lastCompletedAtUtc": "2026-11-15T21:03:18.0000000Z",
            "summarySha256": "1" * 64,
            "sources": {"stats": {"sha256": "2" * 64}},
            "candidateValues": {"position": {
                "x": 7191.6084, "y": 873.9848, "z": 3019.1848,
            }, "stats": {
                "status": "candidate-only", "selectorCount": 20,
                "stats": [{"name": f"field{i}",
                           "ordinary": {"status": "raw-candidate"},
                           "unbuffed": {"status": "raw-candidate"}}
                          for i in range(20)],
            }},
        }
        self.paired = {
            "status": "candidate-only",
            "identity": {"host": "AMD-DESKTOP", "processId": 123,
                         "processStartUtcTicks": "638000000000000001",
                         "executableSha256": BUILD},
            "luaPlayerIdCandidate": PLAYER_ID,
            "sequenceWindows": [[1, 2], [3, 4]],
            "coordinateAgreementScreen": {"withinTolerance": True},
            "positionCandidates": {"firstLua": {
                "x": 7191.60986328125, "y": 873.97998046875,
                "z": 3019.179931640625,
            }},
            "captureOrder": {"status": "source-verified-order"},
        }
        self.retained = {
            "schemaVersion": 1,
            "evidenceKind": "amd-physical-rr2a1-bracketed-two-pass/1",
            "status": "candidate-only", "ownerHost": "AMD-DESKTOP",
            "target": deepcopy(self.owner),
            "secondPassFocus": {"fallbackUsed": False},
            "nativeBracketSha256": {
                "before": self.digest(self.before),
                "after": self.digest(self.after),
            },
            "scanIndexSha256": {
                "first": self.digest(self.first),
                "second": self.digest(self.second),
            },
            "comparison": deepcopy(self.paired),
        }
        self.first_bracket_start = "2026-11-15T21:04:30.0000000Z"

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_join(self):
        with patch.object(join.state, "verified_state",
                          return_value=deepcopy(self.native)), \
             patch.object(join.sources, "load",
                          return_value=(deepcopy(self.retained), "3" * 64)), \
             patch.object(join.lua, "compare",
                          return_value=deepcopy(self.paired)), \
             patch.object(join.lua, "verify_capture_order",
                          return_value=deepcopy(self.paired["captureOrder"])), \
             patch.object(join.lua.native, "verified_bracket",
                          return_value=({}, "a" * 64,
                                        self.first_bracket_start,
                                        self.first_bracket_start)):
            return join.correlate("native.json", self.lua_summary)

    def test_linked_composite_and_advancing_lua_still_candidate_only(self):
        result = self.run_join()
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["rawStatValuesAvailable"], 40)
        self.assertEqual(result["luaPlayerIdCandidate"], PLAYER_ID)
        self.assertEqual(result["luaSequenceWindows"], [[1, 2], [3, 4]])
        self.assertAlmostEqual(result["candidateObservationGapSeconds"], 72)
        self.assertTrue(result["nativeStateToLuaPositionScreen"]["withinTolerance"])
        self.assertLess(result["nativeStateToLuaPositionScreen"]["maximumAxisDifference"], 0.05)
        self.assertIn("unbound", result["qualification"])

    def test_refuses_mismatched_player_owner_and_executable(self):
        mutations = (
            ("player", lambda: self.paired.update(
                luaPlayerIdCandidate="u0000000000000001"),
             "native-lua-self-id-mismatch"),
            ("pid", lambda: self.retained["target"].update(processId=124),
             "process-epoch-or-build-mismatch"),
            ("build", lambda: self.retained["target"].update(
                executableSha256="F" * 64),
             "process-epoch-or-build-mismatch"),
        )
        original_retained, original_paired = deepcopy(self.retained), deepcopy(self.paired)
        for label, mutate, reason in mutations:
            with self.subTest(label=label):
                self.retained = deepcopy(original_retained)
                self.paired = deepcopy(original_paired)
                mutate()
                self.retained["comparison"] = deepcopy(self.paired)
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_join()

    def test_rejects_modified_raw_index_even_with_saved_summary(self):
        self.second.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source-pin-mismatch-second"):
            self.run_join()

    def test_rejects_unavailable_native_stats(self):
        self.native["candidateValues"].pop("stats")
        with self.assertRaisesRegex(ValueError, "four-source-native-stats-required"):
            self.run_join()

    def test_rejects_intervening_position_change_even_if_lua_brackets_agree(self):
        # The Lua two-pass screen only compares its OWN native brackets. A
        # different earlier stat-state XYZ must not inherit that agreement.
        self.native["candidateValues"]["position"]["z"] += 55.73
        with self.assertRaisesRegex(ValueError, "native-stats-rr2a1-lua-position-drift"):
            self.run_join()

    def test_rejects_missing_or_nonfinite_original_position(self):
        for malformed in (None, float("nan"), True):
            with self.subTest(malformed=malformed):
                self.native["candidateValues"]["position"]["x"] = malformed
                with self.assertRaisesRegex(ValueError, "native-stats-rr2a1-invalid-position"):
                    self.run_join()

    def test_refuses_lua_native_disagreement(self):
        self.paired["coordinateAgreementScreen"]["withinTolerance"] = False
        self.retained["comparison"] = deepcopy(self.paired)
        with self.assertRaisesRegex(ValueError, "lua-native-replay-disagreement"):
            self.run_join()

    def test_refuses_old_and_reversed_source_windows(self):
        for older in ("2026-11-15T21:13:19.0000000Z",
                      "2026-11-15T21:04:31.0000000Z"):
            with self.subTest(native_completed=older):
                self.native["lastCompletedAtUtc"] = older
                with self.assertRaisesRegex(ValueError, "native-stats-not-prior-and-near-lua"):
                    self.run_join()

    def test_preserves_100ns_ordering(self):
        self.native["lastCompletedAtUtc"] = "2026-11-15T21:04:30.0000000Z"
        self.first_bracket_start = "2026-11-15T21:04:30.0000001Z"
        result = self.run_join()
        self.assertAlmostEqual(result["candidateObservationGapSeconds"], 0.0000001)

    def test_accepts_independently_pinned_fallback_broad(self):
        broad_index = self.root / "pass-02-broad" / "scan" / "index.json"
        broad_after = self.root / "native-after-broad" / "summary.json"
        for file in (broad_index, broad_after):
            file.parent.mkdir(parents=True)
            file.write_text("broad" + str(file), encoding="utf-8")
        self.retained["secondPassFocus"]["fallbackUsed"] = True
        self.retained["scanIndexSha256"]["second"] = self.digest(broad_index)
        self.retained["nativeBracketSha256"]["after"] = self.digest(broad_after)
        result = self.run_join()
        self.assertEqual(result["status"], "candidate-only")

    def test_optional_native_pair_exposes_raw_changes_without_qualifying_semantics(self):
        linked = {"status": "candidate-only", "nativeSummarySha256": "1" * 64,
                  "processId": 123, "nativeSelfKeyCandidate": PLAYER_KEY,
                  "qualification": "Lua unbound; stat values unqualified."}
        pair = {"status": "candidate-only", "beforeSummarySha256": "4" * 64,
                "afterSummarySha256": "1" * 64, "processId": 123,
                "selfKeyCandidate": PLAYER_KEY,
                "positionDeltaCandidate": {"x": -2.4, "y": -2.5, "z": 55.7},
                "planarDistanceCandidate": 55.75,
                "nativeStatsComparison": {"status": "comparable-candidate",
                                          "rawValuesCompared": 40,
                                          "rawValuesChanged": 2,
                                          "changed": [{"name": "armor", "variant": "ordinary"},
                                                      {"name": "armor", "variant": "unbuffed"}]}}
        with patch.object(join, "correlate", return_value=deepcopy(linked)) as correlate, \
             patch.object(join.state, "compare", return_value=deepcopy(pair)) as compare:
            result = join.correlate_with_previous("old.json", "new.json", "lua.json")
            correlate.assert_called_once_with("new.json", "lua.json")
            compare.assert_called_once_with("old.json", "new.json")
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["previousNativeSummarySha256"], "4" * 64)
        self.assertEqual(result["nativeStatsComparison"]["rawValuesChanged"], 2)
        self.assertEqual(result["nativePositionDeltaCandidate"]["z"], 55.7)
        self.assertEqual(result["nativePlanarDistanceCandidate"], 55.75)
        self.assertIn("does not authenticate", result["qualification"])
        pair["nativeStatsComparison"]["rawValuesChanged"] = 0
        with patch.object(join, "correlate", return_value=deepcopy(linked)), \
             patch.object(join.state, "compare", return_value=deepcopy(pair)):
            self.assertEqual(join.correlate_with_previous("old", "new", "lua")
                             ["nativeStatsComparison"]["rawValuesChanged"], 0)

    def test_optional_native_pair_rejects_mismatch_or_incompatible_stats(self):
        linked = {"nativeSummarySha256": "1" * 64, "processId": 123,
                  "nativeSelfKeyCandidate": PLAYER_KEY,
                  "qualification": "Unbound Lua candidates."}
        pair = {"status": "candidate-only", "beforeSummarySha256": "4" * 64,
                "afterSummarySha256": "1" * 64, "processId": 123,
                "selfKeyCandidate": PLAYER_KEY,
                "positionDeltaCandidate": {"x": 0.0, "y": 0.0, "z": 0.0},
                "planarDistanceCandidate": 0.0,
                "nativeStatsComparison": {"status": "comparable-candidate",
                                          "rawValuesCompared": 40,
                                          "rawValuesChanged": 0}}
        for mutation, reason in (
            ({"afterSummarySha256": "f" * 64}, "previous-native-pair-mismatch"),
            ({"processId": 999}, "previous-native-pair-mismatch"),
            ({"selfKeyCandidate": "42"}, "previous-native-pair-mismatch"),
            ({"nativeStatsComparison": {"status": "incompatible-selector-layout"}},
             "previous-native-stats-not-comparable"),
            ({"nativeStatsComparison": {"status": "comparable-candidate",
                                        "rawValuesCompared": 0}},
             "previous-native-stats-not-comparable"),
            ({"positionDeltaCandidate": {"x": 0.0, "y": float("nan"), "z": 0.0}},
             "previous-native-position-not-comparable"),
        ):
            with self.subTest(mutation=mutation):
                altered = deepcopy(pair)
                altered.update(mutation)
                with patch.object(join, "correlate", return_value=deepcopy(linked)), \
                     patch.object(join.state, "compare", return_value=altered):
                    with self.assertRaisesRegex(ValueError, reason):
                        join.correlate_with_previous("old", "new", "lua")

    def reference_rows(self):
        xyz = self.native["candidateValues"]["position"]
        def frame(number, completed):
            return {
                "startedAtUtc": "2026-11-15T21:04:" + completed + ".0000000Z",
                "completedAtUtc": "2026-11-15T21:04:" + completed + ".0500000Z",
                "snapshotSha256": str(number) * 64,
                "selected": {
                    "wireSha256": str(number + 2) * 64,
                    "sequence": number, "epoch": 44, "frameTime": float(number),
                    "fields": {"coord" + axis.upper(): {"status": "ok", "value": xyz[axis]}
                               for axis in "xyz"},
                },
            }
        return [frame(1, "30"), frame(2, "35")]

    def run_reference(self, rows, *, linked=None, native=None):
        linked = linked or self.run_join()
        native = native or deepcopy(self.native)
        with patch.object(join.state, "verified_state", return_value=native), \
             patch.object(join.survival_state, "reference_pair",
                          return_value=rows) as replay:
            result = join.correlate_with_rr2r1(
                linked, "state.json", "before.json", "after.json", "a" * 32)
            replay.assert_called_once_with(
                "before.json", "after.json", "a" * 32, native)
            return result

    def test_optional_rr2r1_nonce_checked_coordinate_pair_is_candidate_only(self):
        result = self.run_reference(self.reference_rows())
        reference = result["rr2r1Reference"]
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(reference["status"], "nonce-checked-stationary-candidates")
        self.assertEqual(reference["sessionId"], "a" * 32)
        self.assertEqual(reference["epoch"], 44)
        self.assertEqual([f["sequence"] for f in reference["frames"]], [1, 2])
        self.assertAlmostEqual(reference["nativeToLastReferenceGapSeconds"], 77.05)
        self.assertEqual(reference["frames"][0]["nativePositionScreen"]
                         ["maximumAxisDifference"], 0)
        self.assertIn("remain unqualified", result["qualification"])

    def test_rr2r1_rejects_mismatched_identity_timing_and_coordinates(self):
        for name, change, reason in (
            ("position", lambda r, n, l: r[1]["selected"]["fields"]["coordZ"]
             .update(value=3000.0), "rr2r1-position-mismatch"),
            ("missing", lambda r, n, l: r[0]["selected"]["fields"]["coordX"]
             .update(status="unavailable"), "rr2r1-coordinates-unavailable"),
            ("nan", lambda r, n, l: r[1]["selected"]["fields"]["coordX"]
             .update(value=float("nan")), "rr2r1-coordinates-unavailable"),
            ("stale", lambda r, n, l: r[1].update(
                completedAtUtc="2026-11-15T21:06:00.0000000Z"), "rr2r1-evidence-window"),
            ("reversed", lambda r, n, l: n.update(
                lastCompletedAtUtc="2026-11-15T21:04:31.0000000Z"), "rr2r1-evidence-window"),
            ("different-build", lambda r, n, l: n["target"].update(
                executableSha256="B" * 64), "rr2r1-native-state-mismatch"),
            ("different-summary", lambda r, n, l: l.update(
                nativeSummarySha256="F" * 64), "rr2r1-native-state-mismatch"),
        ):
            with self.subTest(name=name):
                rows, native, linked = self.reference_rows(), deepcopy(self.native), self.run_join()
                change(rows, native, linked)
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_reference(rows, native=native, linked=linked)


    def test_rr2r1_real_snapshot_decoder_reuses_nonce_and_source_checks(self):
        fixture = json.loads((join.ROOT / "contracts/addon/fixtures/reference-v1.json").read_text())
        nonce = fixture["nonce"]
        paths = []
        for seq, second in ((1, 30), (2, 35)):
            frame = deepcopy(fixture["before"])
            frame["player"] = {"status": "ok", "value": PLAYER_ID}
            frame["sequence"] = seq
            frame["epoch"] = 4
            frame["clock"] = {"status": "ok", "value": 5.0 + seq}
            for axis, value in self.native["candidateValues"]["position"].items():
                frame["fields"]["coord" + axis.upper()] = {"status": "ok", "value": value}
            wire = b"RR2R1|" + json.dumps(frame).encode("ascii") + b"|ENDRR2R1"
            saved = {
                "schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
                "status": "complete", "identity": self.owner,
                "startedAtUtc": f"2026-11-15T21:04:{second:02}.0000000Z",
                "completedAtUtc": f"2026-11-15T21:04:{second:02}.0500000Z",
                "chunks": [{"address": "0x1000", "status": "success",
                            "bytesRead": len(wire), "requestedByteLength": len(wire),
                            "bytesBase64": base64.b64encode(wire).decode("ascii"),
                            "bytesSha256": hashlib.sha256(wire).hexdigest().upper()}],
            }
            path = self.root / f"verified-{seq}.json"
            path.write_text(json.dumps(saved), encoding="utf-8")
            paths.append(path)
        with patch.object(join.state, "verified_state", return_value=deepcopy(self.native)):
            result = join.correlate_with_rr2r1(self.run_join(), "state.json",
                                               paths[0], paths[1], nonce)
            self.assertEqual(result["rr2r1Reference"]["status"],
                             "nonce-checked-stationary-candidates")
            self.assertEqual(len(result["rr2r1Reference"]["frames"]), 2)
            with self.assertRaises(ValueError):
                join.correlate_with_rr2r1(self.run_join(), "state.json",
                                          paths[0], paths[1], "f" * 32)

    def test_reference_arguments_must_be_complete(self):
        output = StringIO()
        with redirect_stdout(output):
            code = join.main([
                "--state-summary", "native.json", "--rr2a1-summary", "lua.json",
                "--session-id", "a" * 32])
        self.assertEqual(code, 2)
        self.assertIn("rr2r1-reference-requires-both-snapshots-and-nonce",
                      json.loads(output.getvalue())["reason"])


if __name__ == "__main__":
    unittest.main()
