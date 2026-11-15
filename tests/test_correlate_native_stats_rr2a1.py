"""Focused offline tests for source-replayed native statistics / RR2A1 linkage."""
from __future__ import annotations

from copy import deepcopy
import hashlib
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
            "candidateValues": {"stats": {
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


if __name__ == "__main__":
    unittest.main()
