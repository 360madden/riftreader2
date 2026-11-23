"""Exact 1179 native XYZ bracket tests; no RIFT process or desktop interaction."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_player_xyz_bracket as bracket
from tests.test_physical_player_xyz_bracket import HOST, fixture, evaluate

SHA_1179 = bracket.context.UPDATED_BUILD_SHA


def updated():
    before, position, after, selection = fixture()
    for report in (before, after):
        report["observation"]["identity"]["executableSha256"] = SHA_1179
    position["sourceBuildSha256"] = SHA_1179
    position["identity"]["executableSha256"] = SHA_1179
    selection["target"]["executableSha256"] = SHA_1179
    return before, position, after, selection


class UpdatedBuildNativeBracketTests(unittest.TestCase):
    def test_exact_1179_context_xyz_bracket_stays_candidate_only(self):
        a, p, b, s = updated()
        result = evaluate(a, p, b, s)
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["selfKeyCandidate"], "239816685251645959")
        self.assertEqual(result["identity"]["executableSha256"], SHA_1179)
        self.assertEqual(result["sampleCount"], 2)
        self.assertEqual(result["withinBracketPlanarDisplacementCandidate"], 3.0)
        self.assertIn("Lua", result["qualification"])

    def test_unknown_build_is_refused_even_if_every_source_claims_same_unknown(self):
        a, p, b, s = updated()
        fake = "F" * 64
        for row in (a, b):
            row["observation"]["identity"]["executableSha256"] = fake
        p["identity"]["executableSha256"] = fake
        p["sourceBuildSha256"] = fake
        s["target"]["executableSha256"] = fake
        with self.assertRaises(ValueError):
            evaluate(a, p, b, s)

    def test_mixed_builds_and_selection_are_refused(self):
        for change in (
            lambda a, p, b, s: p["identity"].update(executableSha256=bracket.context.BUILD_SHA),
            lambda a, p, b, s: p.update(sourceBuildSha256=bracket.context.BUILD_SHA),
            lambda a, p, b, s: b["observation"]["identity"].update(executableSha256=bracket.context.BUILD_SHA),
            lambda a, p, b, s: s["target"].update(executableSha256=bracket.context.BUILD_SHA),
        ):
            with self.subTest(change=change):
                values = list(updated())
                change(*values)
                with self.assertRaises(ValueError):
                    evaluate(*values)

    def test_live_collection_only_passes_pinned_exact_updated_game_to_native_readers(self):
        a, p, b, selection = updated()
        source = iter((a, p, b))
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "capture"
            def reader(sel, kind, output, **kwargs):
                self.assertIs(sel, selection)
                self.assertEqual(sel["target"]["executableSha256"], SHA_1179)
                Path(output).write_text(json.dumps(next(source)), encoding="utf-8")
                return {"status": "complete"}
            with (patch.object(bracket.socket, "gethostname", return_value=HOST),
                  patch.object(bracket.physical_rift, "select_physical", return_value=selection) as selected,
                  patch.object(bracket.physical_rift, "read_native", side_effect=reader) as read):
                receipt, result = bracket.collect(123, dest, samples=2, interval_ms=100)
            self.assertTrue(receipt.is_file())
            self.assertEqual(result["identity"]["executableSha256"], SHA_1179)
            self.assertEqual(selected.call_count, 2)
            self.assertEqual(read.call_count, 3)

    def test_unknown_build_selection_refused_before_creating_capture(self):
        a, p, b, selection = updated()
        selection["target"]["executableSha256"] = "F" * 64
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out"
            with (patch.object(bracket.socket, "gethostname", return_value=HOST),
                  patch.object(bracket.physical_rift, "select_physical", return_value=selection),
                  patch.object(bracket.physical_rift, "read_native") as read):
                with self.assertRaisesRegex(ValueError, "unexpected-build"):
                    bracket.collect(123, dest, samples=2)
                self.assertFalse(dest.exists())
                read.assert_not_called()

    def test_existing_real_1179_position_and_context_sources_can_be_validated_offline(self):
        root = Path(__file__).resolve().parents[1] / "artifacts/physical-state-postrestart-20261120-0015"
        if not (root / "position.json").is_file() or not (root / "player-context.json").is_file():
            self.skipTest("Machine-local saved 1179 reports unavailable")
        p, _ = bracket.context.load(root / "position.json")
        c, _ = bracket.context.load(root / "player-context.json")
        position = bracket.project_xyz_track.project(
            p, max_gap_seconds=300, max_speed_3d=1e100)
        context, identity, _, _ = bracket.context._sample(c)
        self.assertEqual(identity["executableSha256"], SHA_1179)
        self.assertEqual(position["processIdentity"]["executableSha256"], SHA_1179)
        self.assertEqual(position["sampledUnitKey"], context["unitKey"])
        self.assertEqual(position["unitIdentity"], "same-sampled-unit-key-candidate")


if __name__ == "__main__":
    unittest.main()
