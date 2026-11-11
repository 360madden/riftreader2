"""Pure offline checks for the physical native vitals burst reducer."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as physical
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
    def test_physical_vitals_read_exposes_existing_offline_burst_summary(self):
        report = burst()
        selection = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": {
            "hostName": "AMD-DESKTOP", "processId": IDENTITY["processId"],
            "processStartUtcTicks": str(IDENTITY["processStartUtcTicks"]),
            "executableSha256": tool.GAME_SHA}}
        with TemporaryDirectory() as folder:
            executable = Path(folder) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            destination = Path(folder) / "vitals-burst.json"

            def fake_run(command, **_):
                destination.write_text(json.dumps(report), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "recordType": physical.NATIVE_RECEIPTS["vitals"],
                    "status": "complete", "output": str(destination)}), "")

            with patch.object(physical, "NATIVE_EXE", executable), \
                 patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
                 patch.object(physical.subprocess, "run", side_effect=fake_run):
                result = physical.read_native(selection, "vitals", destination,
                                              samples=3, interval_ms=0)
                source_sha = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
                report["observations"][1]["resourceKindCandidate"] = 3
                destination = Path(folder) / "vitals-kind-conflict.json"
                invalid = physical.read_native(selection, "vitals", destination,
                                               samples=3, interval_ms=0)
            self.assertEqual("blocked", invalid["status"])
            self.assertEqual("invalid-native-reader-report", invalid["reason"])
            self.assertEqual("complete", result["status"])
            summary = result["nativeBurstSummary"]
            self.assertEqual(-20, summary["resources"]["health"]["deltaCurrentCandidate"])
            self.assertEqual(-20, summary["resources"]["energy"]["deltaCurrentCandidate"])
            self.assertEqual(3, summary["sampleCount"])
            self.assertEqual(source_sha, summary["sourceReportSha256"])
            self.assertIn("not independently qualified", summary["qualification"])

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

    def test_unavailable_resource_reasons_are_counted_without_fabricating_values(self):
        report = burst()
        report["observations"][1]["energy"] = unavailable("native-type-not-decoded")
        result = tool.summarize(report, "a" * 64)
        self.assertEqual({}, result["resources"]["health"]["unavailableReasons"])
        self.assertEqual({"not-mana-kind-three": 3},
                         result["resources"]["mana"]["unavailableReasons"])
        self.assertEqual({"native-type-not-decoded": 1},
                         result["resources"]["energy"]["unavailableReasons"])
        self.assertEqual(2, result["resources"]["energy"]["availableSamples"])

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

    def test_elapsed_stopwatch_must_cover_reported_utc_capture_span(self):
        report = burst()
        # The producer uses one Stopwatch around all observations. A retained
        # burst cannot span minutes of UTC time in only two seconds elapsed.
        last = report["observations"][-1]
        for key in ("startedAtUtc", "completedAtUtc"):
            last[key] = (datetime.fromisoformat(last[key])
                         + timedelta(minutes=10)).isoformat()
        report["observation"] = copy.deepcopy(last)
        with self.assertRaisesRegex(ValueError, "elapsed-window-mismatch"):
            tool.summarize(report, "a"*64)

        report = burst()
        report["captureElapsedMilliseconds"] = 1049.0
        with self.assertRaisesRegex(ValueError, "elapsed-window-mismatch"):
            tool.summarize(report, "b"*64)
        # Allow a bounded UTC/monotonic-clock skew without claiming precision.
        report["captureElapsedMilliseconds"] = 1051.0
        self.assertEqual("candidate-only", tool.summarize(report, "c"*64)["status"])

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

    def test_reported_resource_kind_must_agree_with_typed_resources(self):
        report = burst()
        # The producer records the raw resource kind for every observation.
        for row in report["observations"]:
            row["resourceKindCandidate"] = 4
        report["observation"] = copy.deepcopy(report["observations"][-1])
        self.assertEqual("candidate-only", tool.summarize(report, "a"*64)["status"])

        report["observations"][0]["resourceKindCandidate"] = 3
        with self.assertRaisesRegex(ValueError, "resource-kind-conflict"):
            tool.summarize(report, "b"*64)

        report = burst()
        row = report["observations"][0]
        row["resourceKindCandidate"] = 4
        row["mana"] = field(40, 50, kind="0x072A")
        row["energy"] = unavailable("not-energy-kind-four")
        with self.assertRaisesRegex(ValueError, "resource-kind-conflict"):
            tool.summarize(report, "c"*64)

        report = burst()
        report["observations"][0]["resourceKindCandidate"] = True
        with self.assertRaisesRegex(ValueError, "resource-kind-invalid"):
            tool.summarize(report, "d"*64)

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
