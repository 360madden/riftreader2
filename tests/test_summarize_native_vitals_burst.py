"""Pure offline checks for the physical native vitals burst reducer."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import summarize_native_vitals_burst as tool

IDENTITY = {
    "processId": 123, "processStartUtcTicks": 639298670575905950,
    "executableSha256": tool.GAME_SHA,
}
UNIT = 18446744073709551615


def field(value, maximum=150, *, kind=None):
    return {"status": "calculated-candidate", "unavailableReason": None,
            "current": value, "maximum": maximum,
            "inputs": {"verifiedTypeCode": kind} if kind else {"baseRaw": value}}


def unavailable(reason):
    return {"status": "unavailable", "unavailableReason": reason,
            "current": None, "maximum": None, "inputs": None}


def burst():
    start = datetime(2026, 11, 10, 17, 0, tzinfo=timezone.utc)
    rows = []
    for i, hp in enumerate((100, 90, 80)):
        when = start + timedelta(seconds=i)
        rows.append({
            "identity": dict(IDENTITY), "unitKey": UNIT,
            "source": tool.SOURCE, "qualification": tool.QUALIFICATION,
            "startedAtUtc": when.isoformat(),
            "completedAtUtc": (when + timedelta(milliseconds=50)).isoformat(),
            "health": field(hp),
            "mana": unavailable("not-mana-kind-three"),
            "energy": field(100 - 10*i, 100, kind="0x072B"),
        })
    return {
        "schemaVersion": 1, "contractVersion": tool.CONTRACT,
        "status": "complete", "sourceBuildSha256": tool.GAME_SHA,
        "identity": dict(IDENTITY), "source": tool.SOURCE,
        "qualification": tool.QUALIFICATION,
        "requestedSamples": 3, "completedSamples": 3,
        "captureElapsedMilliseconds": 2050.25,
        "observation": copy.deepcopy(rows[-1]), "observations": rows,
    }


class VitalsBurstTests(unittest.TestCase):
    def test_valid_health_and_energy_candidates_remain_unqualified(self):
        report = burst()
        original = copy.deepcopy(report)
        result = tool.summarize(report, "a" * 64)
        self.assertEqual("candidate-only", result["status"])
        self.assertEqual("offline-retained-native-vitals-burst", result["mode"])
        self.assertEqual(str(UNIT), result["unitKey"])
        self.assertEqual(str(IDENTITY["processStartUtcTicks"]),
                         result["processStartUtcTicks"])
        hp = result["resources"]["health"]
        self.assertEqual("complete-candidate", hp["status"])
        self.assertEqual(-20, hp["deltaCurrentCandidate"])
        self.assertEqual({"current": 100, "maximum": 150}, hp["firstCandidate"])
        self.assertEqual({"current": 80, "maximum": 150}, hp["lastCandidate"])
        self.assertEqual(80, hp["minimumCurrentCandidate"])
        self.assertEqual(-20, result["resources"]["energy"]["deltaCurrentCandidate"])
        self.assertEqual("incomplete-candidates", result["resources"]["mana"]["status"])
        self.assertIsNone(result["resources"]["mana"]["deltaCurrentCandidate"])
        self.assertIn("not independently qualified", result["qualification"])
        self.assertEqual(report, original)

    def test_missing_middle_hp_never_fabricates_complete_range(self):
        report = burst()
        report["observations"][1]["health"] = unavailable("revision-mismatch")
        result = tool.summarize(report, "a"*64)
        hp = result["resources"]["health"]
        self.assertEqual("incomplete-candidates", hp["status"])
        self.assertEqual(2, hp["availableSamples"])
        self.assertIsNone(hp["minimumCurrentCandidate"])
        self.assertEqual(-20, hp["deltaCurrentCandidate"])

    def test_changed_player_process_and_overlap_rejected(self):
        for alter in (
            lambda r: r["observations"][1].update(unitKey=42),
            lambda r: r["observations"][1]["identity"].update(processId=124),
            lambda r: r["observations"][1].update(startedAtUtc=r["observations"][0]["startedAtUtc"]),
            lambda r: r["observations"][1].update(startedAtUtc="2026-11-10T16:59:00Z"),
            lambda r: r["observations"][1].update(completedAtUtc="2026-11-10T16:59:00Z"),
            lambda r: r["observations"][2].update(unitKey=True),
        ):
            report = burst()
            alter(report)
            with self.subTest(alter=str(alter)), self.assertRaises(ValueError):
                tool.summarize(report, "b"*64)

    def test_missing_and_malformed_resource_state_rejected(self):
        edits = (
            lambda r: r["observations"][0].pop("mana"),
            lambda r: r["observations"][0]["health"].update(current=True),
            lambda r: r["observations"][0]["health"].update(maximum=0),
            lambda r: r["observations"][0]["energy"]["inputs"].update(verifiedTypeCode="0x072A"),
            lambda r: r["observations"][0]["mana"].update(status="calculated-candidate",
                unavailableReason=None, current=40, maximum=50, inputs={"verifiedTypeCode": "0x072A"}),
        )
        for edit in edits:
            report = burst()
            edit(report)
            with self.subTest(edit=str(edit)), self.assertRaises(ValueError):
                tool.summarize(report, "c"*64)

    def test_mismatched_summary_and_sample_counts_rejected(self):
        for edit in (
            lambda r: r.update(completedSamples=2),
            lambda r: r["observation"].update(unitKey=1),
            lambda r: r.update(sourceBuildSha256="0"*64),
            lambda r: r.update(qualification="qualified"),
            lambda r: r.update(captureElapsedMilliseconds=float("nan")),
        ):
            report = burst()
            edit(report)
            with self.subTest(edit=str(edit)), self.assertRaises(ValueError):
                tool.summarize(report, "d"*64)

    def test_cli_preserves_file_sha_and_blocks_duplicate_keys(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "burst.json"
            raw = json.dumps(burst(), separators=(",", ":")).encode()
            path.write_bytes(raw)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, tool.main([str(path)]))
            self.assertEqual(hashlib.sha256(raw).hexdigest().upper(),
                             json.loads(out.getvalue())["sourceReportSha256"])
            duplicated = raw.decode().replace(
                '"status":"complete"', '"status":"qualified","status":"complete"', 1)
            path.write_text(duplicated, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(2, tool.main([str(path)]))
            self.assertEqual("blocked", json.loads(out.getvalue())["status"])

    def test_cli_rejects_truncated_or_missing_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "missing.json"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(2, tool.main([str(path)]))
            path.write_bytes(b"{")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(2, tool.main([str(path)]))


if __name__ == "__main__":
    unittest.main()
