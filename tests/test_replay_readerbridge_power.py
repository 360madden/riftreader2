"""Offline replay checks for the retained native/Lua Power bracket."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift
from scripts import replay_readerbridge_v3 as replay

BUILD = "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"


class PowerBracketReplayTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.path = self.root / "comparison.json"
        self.summary = self.root / "bridge" / "result.json"
        self.summary.parent.mkdir()
        self.identity = {
            "processId": 123, "processStartUtcTicks": 638000000000000001,
            "executableSha256": BUILD, "executablePath": r"C:\RIFT\rift_x64.exe",
            "moduleBaseAddress": 123456, "moduleSize": 654321,
        }
        self.target = dict(self.identity, hostName="LEGION")
        self.self_id = "u035400012FA2D207"
        self.observed = {
            "host": "LEGION", "target": self.identity, "selfId": self.self_id,
            "playerLevelComparison": {"status": "matching-native-and-lua-player-level-candidates"},
            "generations": [
                {"sequence": seq, "startedAtUtc": f"2026-11-26T08:00:0{sec}Z",
                 "completedAtUtc": f"2026-11-26T08:00:0{sec}.1Z",
                 "luaPower": {"current": 96, "publishedMaximum": 100,
                              "maximumMayBeAddonDefault": True}}
                for seq, sec in ((10, 2), (11, 3))
            ],
        }
        self.saved = {
            "status": "matching-static-power-candidates", "host": "LEGION",
            "target": self.target, "readerBridgeSelfId": self.self_id,
            "nativeSamples": [[96, 100], [96, 100]],
            "luaSamples": [[96, 100], [96, 100]], "luaMaximumMayBeDefault": True,
            "sequences": [10, 11], "sources": {},
        }
        self.native = {
            "schemaVersion": 1, "contractVersion": "native-power-samples/1",
            "qualification": "candidate-only", "recipe": physical_rift.POWER_RECIPES[BUILD],
            "identity": self.identity, "status": "complete", "requestedSamples": 1,
        }
        for name, sec in (("before.json", 1), ("after.json", 4)):
            report = dict(self.native, samples=[{
                "startedAtUtc": f"2026-11-26T08:00:0{sec}Z",
                "completedAtUtc": f"2026-11-26T08:00:0{sec}.1Z",
                "status": "complete", "reason": None, "power": 96, "maximum": 100,
                "baseValue": 96, "rate": 1200, "sequence": 1,
                "clockSeconds": 100.0, "anchorSeconds": 100.0,
            }])
            self.write_pin(name, report)
        self.write_pin("bridge/result.json", {"fixture": True})
        self.write_summary()

    def write_pin(self, name, value):
        raw = json.dumps(value).encode("utf-8")
        (self.root / name).write_bytes(raw)
        self.saved["sources"][name] = hashlib.sha256(raw).hexdigest()

    def write_summary(self):
        self.path.write_text(json.dumps(self.saved), encoding="utf-8")

    def check(self, observed=None):
        with patch.object(replay, "replay", return_value=self.observed if observed is None else observed) as run:
            value = replay.replay_power_bracket(self.path)
            run.assert_called_once_with(self.summary,
                                        expected_sha256=self.saved["sources"]["bridge/result.json"])
            return value

    def test_rederives_candidate_values(self):
        result = self.check()
        self.assertEqual("matching-static-power-candidates", result["status"])
        self.assertTrue(result["replayVerified"])
        self.assertTrue(result["luaMaximumMayBeDefault"])
        self.assertFalse(result["ready"] or result["inputSent"])
        self.assertEqual([[96, 100], [96, 100]], result["nativeSamples"])

    def test_rejects_changed_source_and_missing_bridge_pin(self):
        before = self.root / "before.json"
        original = before.read_bytes()
        before.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "power-source-sha-mismatch"):
            self.check()
        before.write_bytes(original)
        self.saved["sources"].pop("bridge/result.json")
        self.write_summary()
        with patch.object(replay, "replay") as run:
            with self.assertRaisesRegex(ValueError, "power-source-pins-invalid"):
                replay.replay_power_bracket(self.path)
            run.assert_not_called()

    def test_rejects_unpinned_bridge_summary_before_decode(self):
        with self.assertRaisesRegex(ValueError, "capture-summary-sha-mismatch"):
            replay.replay(self.summary, expected_sha256="A" * 64)

    def test_rejects_owner_or_time_drift_even_when_rehashed(self):
        name = "after.json"
        doc = json.loads((self.root / name).read_bytes())
        changed = deepcopy(doc)
        changed["identity"]["processStartUtcTicks"] += 1
        self.write_pin(name, changed)
        self.write_summary()
        with self.assertRaisesRegex(ValueError, "power-native-owner-mismatch"):
            self.check()
        doc["samples"][0].update(startedAtUtc="2026-11-26T08:00:01Z",
                                 completedAtUtc="2026-11-26T08:00:01.1Z")
        self.write_pin(name, doc)
        self.write_summary()
        with self.assertRaisesRegex(ValueError, "power-native-does-not-bracket-packets"):
            self.check()

    def test_rejects_wrong_lua_player_and_tampered_projection(self):
        changed = dict(self.observed, selfId="u0000000000000001")
        with self.assertRaisesRegex(ValueError, "power-bracket-owner-mismatch"):
            self.check(changed)
        self.saved["nativeSamples"][0][0] = 95
        self.write_summary()
        with self.assertRaisesRegex(ValueError, "power-comparison-projection-mismatch"):
            self.check()

    def test_differing_values_remain_candidate_only(self):
        self.observed["generations"][1]["luaPower"]["current"] = 97
        self.saved["luaSamples"][1][0] = 97
        self.saved["status"] = "differing-power-candidates"
        self.write_summary()
        result = self.check()
        self.assertEqual("differing-power-candidates", result["status"])
        self.assertTrue(result["replayVerified"])
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
