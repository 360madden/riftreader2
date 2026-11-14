"""Offline candidate unit/name correlation with explicit refusal of stale owners."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from unittest.mock import patch
import json
import unittest

from scripts import join_physical_unit_context as join


class UnitContextTests(unittest.TestCase):
    def setUp(self):
        self.identity = {
            "processId": 21672, "processStartUtcTicks": 639302305454629980,
            "executableSha256": "A" * 64, "moduleBaseAddress": 0x12345000,
            "moduleSize": 63000000,
        }
        self.positions = {"observation": {
            "identity": self.identity, "completedAtUtc": "2026-11-14T08:25:05.1234567Z",
            "rows": [
                {"unitKey": "10", "entityAddressDecimal": "65536"},
                {"unitKey": "20", "entityAddressDecimal": "131072"},
            ],
        }}
        self.names = {"observation": {
            "identity": deepcopy(self.identity), "startedAtUtc": "2026-11-14T08:25:06.1234568Z",
        }}
        self.position_values = {
            "selfKey": "7", "unitsExamined": 3, "positionsFound": 2,
            "unitLimitReached": True, "worldCoverage": "bounded-unit-manager-subset",
            "units": [
                {"unitKey": "10", "unitIdCandidate": "u000000000000000A",
                 "horizontalDistanceCandidate": 4.0,
                 "positionXYZCandidate": {"x": 1, "y": 2, "z": 3},
                 "screenPointCandidate": {"status": "unavailable"}},
                {"unitKey": "20", "unitIdCandidate": "u0000000000000014",
                 "horizontalDistanceCandidate": 12.0,
                 "positionXYZCandidate": {"x": 4, "y": 5, "z": 6},
                 "screenPointCandidate": {"status": "unavailable"}},
            ],
        }
        self.name_values = {
            "selfKey": "7", "rows": [
                {"unitKey": "10", "entityAddressDecimal": "65536",
                 "status": "available-candidate", "reason": None,
                 "baseNameCandidate": "Guard"},
                {"unitKey": "20", "entityAddressDecimal": "131072",
                 "status": "unavailable", "reason": "cache-miss",
                 "baseNameCandidate": None},
            ],
        }

    def assess(self, **kwargs):
        with (patch.object(join.context, "load", side_effect=[
                  (self.positions, "A" * 64), (self.names, "B" * 64)]),
              patch.object(join.physical_rift, "_native_values",
                           side_effect=[self.position_values, self.name_values]),
              patch.object(join.socket, "gethostname", return_value="AMD-DESKTOP")):
            return join.join("position.json", "names.json", **kwargs)

    def test_join_preserves_source_pins_and_unknown_hostility(self):
        result = self.assess()
        self.assertEqual(result["namedCandidateCount"], 1)
        self.assertEqual(result["sources"], {
            "positionsSha256": "A" * 64, "namesSha256": "B" * 64})
        self.assertAlmostEqual(result["nameReadGapSeconds"], 1.0000001)
        self.assertEqual(result["units"][0]["baseNameCandidate"], "Guard")
        self.assertEqual(result["units"][1]["nameReason"], "cache-miss")
        self.assertEqual(result["units"][1]["baseNameCandidate"], None)
        self.assertFalse(result["encounter"]["ready"])
        self.assertEqual({r["hostility"] for r in result["units"]}, {"unknown"})
        self.assertEqual(result["sourceHostProvenance"], "not-embedded-in-raw-native-reports")

    def test_changed_entity_address_does_not_attach_cached_name(self):
        self.name_values["rows"][0]["entityAddressDecimal"] = "196608"
        result = self.assess()
        self.assertEqual(result["namedCandidateCount"], 0)
        self.assertIsNone(result["units"][0]["baseNameCandidate"])
        self.assertEqual(result["units"][0]["nameReason"], "entity-owner-changed")

    def test_unrequested_key_is_not_invented(self):
        self.name_values["rows"] = self.name_values["rows"][:1]
        result = self.assess()
        self.assertEqual(result["units"][1]["nameReason"], "not-requested")

    def test_extra_or_duplicate_name_owner_refused(self):
        self.name_values["rows"].append(dict(self.name_values["rows"][0]))
        with self.assertRaisesRegex(ValueError, "name-key-outside-position-capture"):
            self.assess()
        self.name_values["rows"][-1]["unitKey"] = "30"
        with self.assertRaisesRegex(ValueError, "name-key-outside-position-capture"):
            self.assess()

    def test_duplicate_position_owner_refused(self):
        self.positions["observation"]["rows"][1]["unitKey"] = "10"
        with self.assertRaisesRegex(ValueError, "duplicate-position-owner"):
            self.assess()

    def test_rejects_changed_pid_start_build_or_module(self):
        for key, value in (("processId", 42),
                           ("processStartUtcTicks", 999),
                           ("executableSha256", "B" * 64),
                           ("moduleBaseAddress", 0x999999)):
            with self.subTest(key=key):
                self.names["observation"]["identity"] = deepcopy(self.identity)
                self.names["observation"]["identity"][key] = value
                with self.assertRaisesRegex(ValueError, "owner-or-epoch-mismatch"):
                    self.assess()

    def test_rejects_changed_self_key(self):
        self.name_values["selfKey"] = "8"
        with self.assertRaisesRegex(ValueError, "self-key-mismatch"):
            self.assess()

    def test_refuses_overlap_and_stale_names(self):
        for start in ("2026-11-14T08:25:04Z", "2026-11-14T08:25:36Z"):
            with self.subTest(start=start):
                self.names["observation"]["startedAtUtc"] = start
                with self.assertRaisesRegex(ValueError, "captures-overlap-or-too-far-apart"):
                    self.assess()

    def test_refuses_nonfinite_or_out_of_range_gap(self):
        for limit in (float("nan"), float("inf"), -1, 121, "30", True):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "invalid-gap-limit"):
                    self.assess(max_gap_seconds=limit)

    def test_requires_local_amd_analysis_host(self):
        with patch.object(join.socket, "gethostname", return_value="OTHER-PC"), \
             patch.object(join.context, "load", side_effect=[
                 (self.positions, "A" * 64), (self.names, "B" * 64)]), \
             patch.object(join.physical_rift, "_native_values",
                          side_effect=[self.position_values, self.name_values]):
            with self.assertRaisesRegex(ValueError, "wrong-analysis-host"):
                join.join("position.json", "names.json")

    def test_cli_returns_structured_failure_without_game_access(self):
        capture = StringIO()
        with redirect_stdout(capture):
            code = join.main(["--positions", "missing-position.json", "--names", "missing-name.json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(capture.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
