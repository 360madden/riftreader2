"""Focused offline regressions for native physical self->XYZ->self bracket."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_player_xyz_bracket as bracket

ID = {
    "processId": 123, "processStartUtcTicks": 638000000000000001,
    "executablePath": r"C:\Games\RIFT\rift_x64.exe",
    "executableSha256": bracket.context.BUILD_SHA,
    "moduleBaseAddress": 140700000000000, "moduleSize": 63164416,
}
OWNER = "239816685251645959"
QUAL = "candidate-only; changed-state, API correspondence and restart unverified"


def fixture():
    def ctx(start, end):
        row = {
            "identity": deepcopy(ID), "startedAtUtc": start, "completedAtUtc": end,
            "unitKey": int(OWNER), "rawFallbackKey": 0, "targetKeyCandidate": 0,
            "targetStatus": "raw-getter-zero-candidate", "targetUnitIdCandidate": None,
            "rawLevel": 45, "levelStatus": "numeric-getter-and-presentation-candidate",
            "rawCombat": 0, "combatStatus": "raw-byte-candidate", "combatCandidate": False,
            "rawCalling": 1, "callingCandidate": "warrior", "qualification": QUAL,
        }
        return {
            "schemaVersion": 1, "contractVersion": "native-current-player-context-candidate-sample/1",
            "status": "complete", "qualification": QUAL, "observation": row,
        }

    def row(index, begin, end, x, monotonic):
        return {
            "index": index, "startedAtUtc": begin, "completedAtUtc": end,
            "monotonicStartMilliseconds": monotonic,
            "monotonicEndMilliseconds": monotonic + 100,
            "x": x, "y": 2.0, "z": 3.0, "unitKey": OWNER,
            "unitIdCandidate": f"u{int(OWNER):016X}",
            "ownerIdentityStatus": "player-component-chain-anchored",
        }

    before = ctx("2026-11-11T00:00:00Z", "2026-11-11T00:00:00.1000000Z")
    after = ctx("2026-11-11T00:00:03.5000000Z", "2026-11-11T00:00:03.6000000Z")
    position = {
        "schemaVersion": 1, "contractVersion": "native-current-position-candidate-samples/1",
        "status": "complete", "qualification": bracket.project_xyz_track.QUALIFICATION,
        "sourceBuildSha256": bracket.context.BUILD_SHA, "identity": deepcopy(ID),
        "requestedSamples": 2, "completedSamples": 2,
        "observations": [
            row(1, "2026-11-11T00:00:01Z", "2026-11-11T00:00:01.100Z", 1.0, 0),
            row(2, "2026-11-11T00:00:02Z", "2026-11-11T00:00:02.100Z", 4.0, 1000),
        ],
    }
    selection = {"status": "ready", "ownerHost": "AMD-DESKTOP",
                 "target": {"processId": 123, "processStartUtcTicks": str(ID["processStartUtcTicks"]),
                            "executableSha256": bracket.context.BUILD_SHA}}
    return before, position, after, selection


def evaluate(before, position, after, selection):
    return bracket.assess(before, position, after,
                          {"before": "A" * 64, "position": "B" * 64, "after": "C" * 64},
                          selection)


class BracketTests(unittest.TestCase):
    def test_produces_same_epoch_native_candidate_and_limitations(self):
        result = evaluate(*fixture())
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["selfKeyCandidate"], OWNER)
        self.assertEqual(result["sampleCount"], 2)
        self.assertEqual(result["withinBracketPlanarDisplacementCandidate"], 3.0)
        self.assertIsNone(result["targetCandidate"]["afterIdCandidate"])
        self.assertIn("Lua", result["qualification"])
        self.assertNotIn("moduleBaseAddress", result["identity"])

    def test_owner_mismatch_or_changed_context_blocks(self):
        for mutate in (
            lambda a, p, b, s: p["observations"][1].update(unitKey="2", unitIdCandidate="u0000000000000002"),
            lambda a, p, b, s: b["observation"].update(unitKey=3),
            lambda a, p, b, s: p["identity"].update(moduleBaseAddress=19),
            lambda a, p, b, s: s["target"].update(processStartUtcTicks="987"),
            lambda a, p, b, s: s.update(ownerHost="OTHER-HOST"),
        ):
            reports = list(fixture())
            mutate(*reports)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                evaluate(*reports)

    def test_rejects_nonbracketed_or_touching_positions(self):
        for mutate in (
            lambda p: p["observations"][0].update(startedAtUtc="2026-11-11T00:00:00.1000000Z"),
            lambda p: p["observations"][1].update(completedAtUtc="2026-11-11T00:00:03.5000000Z"),
            lambda p: p["observations"][1].update(startedAtUtc="2026-11-11T00:00:03.6000000Z"),
        ):
            a, p, b, s = fixture()
            mutate(p)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                evaluate(a, p, b, s)

    def test_rejects_invalid_contract_and_incomplete_read(self):
        for mutate in (
            lambda a, p, b: p.update(status="blocked"),
            lambda a, p, b: a.update(status="blocked"),
            lambda a, p, b: p["observations"][0].update(unitIdCandidate=None),
        ):
            a, p, b, s = fixture()
            mutate(a, p, b)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                evaluate(a, p, b, s)

    def test_collect_reuses_three_native_reads_and_checks_final_pin(self):
        a, p, b, selection = fixture()
        reports = iter((a, p, b))
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "capture"
            def reader(selected, kind, output, **kwargs):
                self.assertIs(selected, selection)
                Path(output).write_text(json.dumps(next(reports)), encoding="utf-8")
                return {"status": "complete"}
            with patch.object(bracket.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(bracket.physical_rift, "select_physical", return_value=selection) as probe, \
                 patch.object(bracket.physical_rift, "read_native", side_effect=reader) as read:
                path, result = bracket.collect(123, destination, samples=2, interval_ms=500)
            self.assertEqual(probe.call_count, 2)
            self.assertEqual(read.call_count, 3)
            self.assertEqual(read.call_args_list[1].args[1], "position")
            self.assertEqual(read.call_args_list[1].kwargs["samples"], 2)
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text())["sourceSha256"], result["sourceSha256"])

    def test_final_epoch_change_blocks_output_but_retains_raw_evidence(self):
        a, p, b, selection = fixture()
        changed = deepcopy(selection)
        changed["target"]["processStartUtcTicks"] = "999"
        reports = iter((a, p, b))
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "capture"
            def reader(sel, kind, path, **kwargs):
                Path(path).write_text(json.dumps(next(reports)), encoding="utf-8")
                return {"status": "complete"}
            with patch.object(bracket.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(bracket.physical_rift, "select_physical", side_effect=(selection, changed)), \
                 patch.object(bracket.physical_rift, "read_native", side_effect=reader):
                with self.assertRaisesRegex(ValueError, "final-process-identity-changed"):
                    bracket.collect(123, destination, samples=2)
            self.assertFalse((destination / "summary.json").exists())
            self.assertTrue((destination / "position.json").exists())

    def test_wrong_host_or_invalid_pid_never_probes(self):
        with patch.object(bracket.socket, "gethostname", return_value="OTHER-HOST"), \
             patch.object(bracket.physical_rift, "select_physical") as probe, \
             tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                bracket.collect(123, Path(temp) / "x")
            probe.assert_not_called()
        with patch.object(bracket.socket, "gethostname", return_value="AMD-DESKTOP"), \
             patch.object(bracket.physical_rift, "select_physical") as probe, \
             tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "pid-required"):
                bracket.collect(0, Path(temp) / "x")
            probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
