"""Offline integration tests for independently SHA-verified native XYZ bracket pairs."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import compare_physical_player_brackets as pair
from scripts import physical_player_xyz_bracket as bracket
from test_physical_player_xyz_bracket import fixture


class BracketPairTests(unittest.TestCase):
    def save(self, root, name, *, later=False, x_offset=0, epoch_offset=0):
        before, position, after, selection = deepcopy(fixture())
        if later:
            for ctx in (before, after):
                for field in ("startedAtUtc", "completedAtUtc"):
                    value = ctx["observation"][field]
                    ctx["observation"][field] = value.replace("T00:", "T01:")
            for row in position["observations"]:
                for field in ("startedAtUtc", "completedAtUtc"):
                    row[field] = row[field].replace("T00:", "T01:")
        if epoch_offset:
            new_epoch = before["observation"]["identity"]["processStartUtcTicks"] + epoch_offset
            for ctx in (before, after):
                ctx["observation"]["identity"]["processStartUtcTicks"] = new_epoch
            position["identity"]["processStartUtcTicks"] = new_epoch
            selection["target"]["processStartUtcTicks"] = str(new_epoch)
        for row in position["observations"]:
            row["x"] += x_offset
        folder = root / name
        folder.mkdir()
        inputs = {"before": ("context-before.json", before),
                  "position": ("position.json", position),
                  "after": ("context-after.json", after)}
        hashes = {}
        for key, (filename, report) in inputs.items():
            path = folder / filename
            path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        summary = bracket.assess(before, position, after, hashes, selection)
        path = folder / "summary.json"
        path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
        return path

    def test_replayed_distinct_brackets_report_candidate_difference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = self.save(root, "a")
            b = self.save(root, "b", later=True, x_offset=8)
            result = pair.compare(a, b)
            self.assertEqual(result["planarDistanceCandidate"], 5)
            self.assertEqual(result["positionDeltaCandidate"], {"x": 5, "y": 0, "z": 0})
            self.assertEqual(result["sampleCounts"], {"before": 2, "after": 2})
            self.assertGreater(result["gapSeconds"], 0)
            self.assertEqual(result["status"], "candidate-only")
            self.assertIn("no Lua correspondence", result["qualification"])

    def test_rejects_tampered_source_or_forged_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = self.save(root, "a")
            b = self.save(root, "b", later=True)
            raw = (b.parent / "position.json").read_bytes()
            (b.parent / "position.json").write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "source-sha-mismatch"):
                pair.compare(a, b)
            (b.parent / "position.json").write_bytes(raw)
            summary = json.loads(b.read_text())
            summary["lastPositionCandidate"]["x"] += 123
            b.write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "summary-replay-mismatch"):
                pair.compare(a, b)

    def test_rejects_reversed_overlap_and_changed_process_epoch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = self.save(root, "a")
            b = self.save(root, "b", later=True)
            with self.assertRaisesRegex(ValueError, "overlapping-or-reversed-captures"):
                pair.compare(b, a)
            with self.assertRaisesRegex(ValueError, "same-source"):
                pair.compare(a, a)
            c = self.save(root, "c", later=True, epoch_offset=1)
            with self.assertRaisesRegex(ValueError, "process-epoch-or-build-changed"):
                pair.compare(a, c)

    def test_rejects_ambiguous_summary_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = self.save(root, "a")
            b = self.save(root, "b", later=True)
            saved = a.read_text()
            a.write_text(saved.replace('"status": "candidate-only"',
                                       '"status": "candidate-only", "status": "complete"'))
            with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
                pair.compare(a, b)
            a.write_text(saved)
            output = root / "report.json"
            output.write_text("keep")
            self.assertEqual(pair.main(["--before", str(a), "--after", str(b),
                                        "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "keep")
            output.unlink()
            self.assertEqual(pair.main(["--before", str(a), "--after", str(b),
                                        "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["status"], "candidate-only")


if __name__ == "__main__":
    unittest.main()
