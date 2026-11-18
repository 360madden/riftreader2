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

    def test_updated_build_health_only_burst_is_admitted_with_both_resources_unqualified(self):
        report = burst()
        report["sourceBuildSha256"] = tool.UPDATED_GAME_SHA
        report["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
        for row in report["observations"]:
            row["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
            row["energy"] = unavailable("postpatch-energy-type-unqualified")
            row["mana"] = unavailable("postpatch-mana-type-unqualified")
        report["observation"] = copy.deepcopy(report["observations"][-1])
        summary = tool.summarize(report, "d" * 64)
        self.assertEqual(tool.UPDATED_GAME_SHA, summary["sourceBuildSha256"])
        self.assertEqual(-20, summary["resources"]["health"]["deltaCurrentCandidate"])
        self.assertEqual(0, summary["resources"]["mana"]["availableSamples"])
        self.assertEqual(0, summary["resources"]["energy"]["availableSamples"])
        report["identity"]["executableSha256"] = tool.GAME_SHA
        with self.assertRaises(ValueError):
            tool.summarize(report, "d" * 64)

    def test_1179_single_vitals_rejects_impossible_typed_resources(self):
        row = burst()["observation"]
        row["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
        row["resourceKindCandidate"] = 4
        report = {"schemaVersion": 1, "status": "complete",
                  "contractVersion": "native-current-vitals-candidate-sample/2",
                  "source": tool.SOURCE, "qualification": tool.QUALIFICATION,
                  "sourceBuildSha256": tool.UPDATED_GAME_SHA, "observation": row}
        projected = physical._native_values("vitals", report)
        self.assertEqual("calculated-candidate", projected["energy"]["status"])
        for defect in ("both-calculated", "wrong-type", "wrong-kind", "null-kind",
                       "wrong-exclusion", "maximum-overflow", "split-identity"):
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                bad = copy.deepcopy(report)
                observed = bad["observation"]
                if defect == "both-calculated":
                    observed["mana"] = field(40, 50, kind="0x072A")
                elif defect == "wrong-type":
                    observed["energy"]["inputs"]["verifiedTypeCode"] = "0x072A"
                elif defect == "wrong-kind":
                    observed["resourceKindCandidate"] = 3
                elif defect == "null-kind":
                    observed["resourceKindCandidate"] = None
                elif defect == "wrong-exclusion":
                    observed["mana"] = unavailable("unrelated")
                elif defect == "maximum-overflow":
                    observed["energy"]["maximum"] = 2**31
                else:
                    bad["identity"] = copy.deepcopy(observed["identity"])
                    observed["identity"]["executableSha256"] = tool.GAME_SHA
                physical._native_values("vitals", bad)

    def test_1179_burst_requires_observed_kind_for_each_calculated_resource(self):
        for name, kind, code, other, excluded in (
                ("energy", 4, "0x072B", "mana", "not-mana-kind-three"),
                ("mana", 3, "0x072A", "energy", "not-energy-kind-four")):
            report = burst()
            report["sourceBuildSha256"] = tool.UPDATED_GAME_SHA
            report["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
            for row in report["observations"]:
                row["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
                row["resourceKindCandidate"] = kind
                row[name] = field(40, 50, kind=code)
                row[other] = unavailable(excluded)
            report["observation"] = copy.deepcopy(report["observations"][-1])
            self.assertEqual(3, tool.summarize(report, "b"*64)["resources"][name]["availableSamples"])
            for absent in (True, False):
                with self.subTest(resource=name, absent=absent), self.assertRaises(ValueError):
                    bad = copy.deepcopy(report)
                    first = bad["observations"][0]
                    if absent:
                        del first["resourceKindCandidate"]
                    else:
                        first["resourceKindCandidate"] = None
                    tool.summarize(bad, "c"*64)

    def test_1179_burst_allows_kind_change_and_typed_unavailable_inputs(self):
        report = burst()
        report["sourceBuildSha256"] = tool.UPDATED_GAME_SHA
        report["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
        energy, mana, unknown = report["observations"]
        for row in (energy, mana, unknown):
            row["identity"]["executableSha256"] = tool.UPDATED_GAME_SHA
        energy["resourceKindCandidate"] = 4
        mana.update(resourceKindCandidate=3, energy=unavailable("not-energy-kind-four"),
                    mana=unavailable("revision-mismatch-needs-native-cache-write"))
        mana["mana"]["inputs"] = {"verifiedTypeCode": "0x072A"}
        unknown.update(resourceKindCandidate=None, mana=unavailable("resource-kind-unavailable"),
                       energy=unavailable("resource-kind-unavailable"))
        report["observation"] = copy.deepcopy(unknown)
        projected = tool.summarize(report, "d"*64)["resources"]
        self.assertEqual(1, projected["energy"]["availableSamples"])
        self.assertEqual(0, projected["mana"]["availableSamples"])
        self.assertEqual(1, projected["mana"]["unavailableReasons"]["revision-mismatch-needs-native-cache-write"])

    def test_1179_unavailable_reason_and_inputs_match_the_observed_kind(self):
        revision = "revision-mismatch-needs-native-cache-write"
        common = (revision, "outside-normal-integer-domain", "clock-delta-outside-normal-domain",
                  "int32-conversion-overflow-or-sentinel", "signed32-subtraction-overflow")

        def typed_failure(reason, code):
            return {**unavailable(reason), "inputs": {"verifiedTypeCode": code}}

        def check(kind, mana, energy):
            row = {"resourceKindCandidate": kind, "mana": mana, "energy": energy}
            return tool.typed_resources(row, updated=True, current_acquisition=True)

        no_mana = unavailable("not-mana-kind-three")
        no_energy = unavailable("not-energy-kind-four")
        unknown = unavailable("resource-kind-unavailable")
        unverified_mana = unavailable("postpatch-mana-record-unverified")
        unverified_energy = unavailable("postpatch-energy-record-unverified")
        for case in ((None, unknown, unknown), (0, no_mana, no_energy),
                     (3, unverified_mana, no_energy), (4, no_mana, unverified_energy)):
            self.assertEqual({"mana": None, "energy": None}, check(*case))
        for reason in common + ("invalid-float-input",):
            check(3, typed_failure(reason, "0x072A"), no_energy)
        for reason in common:
            check(4, no_mana, typed_failure(reason, "0x072B"))

        for case in ((None, no_mana, no_energy),
                     (None, typed_failure("resource-kind-unavailable", "0x072A"), unknown),
                     (0, typed_failure(revision, "0x072A"), no_energy),
                     (3, typed_failure(revision, "0x072B"), no_energy),
                     (3, unavailable(revision), no_energy),
                     (3, typed_failure("postpatch-mana-record-unverified", "0x072A"), no_energy),
                     (3, typed_failure("unknown-arithmetic-error", "0x072A"), no_energy),
                     (4, no_mana, typed_failure("invalid-float-input", "0x072B")),
                     (4, typed_failure("not-mana-kind-three", "0x072A"), unverified_energy)):
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "resource-unavailable-provenance"):
                check(*case)

    def test_current_cli_rejects_retained_1179_diagnostics_without_inferring_generation(self):
        identity = dict(IDENTITY, executableSha256=tool.UPDATED_GAME_SHA)
        selection = {"status": "ready", "ownerHost": "AMD-DESKTOP", "target": {
            "hostName": "AMD-DESKTOP", "processId": identity["processId"],
            "processStartUtcTicks": str(identity["processStartUtcTicks"]), "executableSha256": tool.UPDATED_GAME_SHA}}
        with TemporaryDirectory() as folder:
            executable = Path(folder) / "RiftReader2.Live.exe"
            executable.write_bytes(b"MZ")
            for i, (mana_reason, energy_reason, expected) in enumerate((
                    ("postpatch-mana-type-unqualified", "postpatch-energy-type-unqualified", "blocked"),
                    ("not-mana-kind-three", "postpatch-energy-type-unqualified", "blocked"),
                    ("not-mana-kind-three", "not-energy-kind-four", "complete"))):
                report = burst()
                report.update(identity=identity, sourceBuildSha256=tool.UPDATED_GAME_SHA)
                for row in report["observations"]:
                    row.update(identity=identity, resourceKindCandidate=1,
                               mana=unavailable(mana_reason), energy=unavailable(energy_reason))
                report["observation"] = copy.deepcopy(report["observations"][-1])
                replay = tool.summarize(report, "a"*64)
                self.assertEqual("reported-only; historical reader generation unknown", replay["unavailableReasonProvenance"])
                self.assertEqual(0, replay["resources"]["mana"]["availableSamples"])
                self.assertEqual(0, replay["resources"]["energy"]["availableSamples"])
                destination = Path(folder) / f"synthetic-{i}.json"

                def fake_run(command, **_):
                    destination.write_text(json.dumps(report), encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, json.dumps({
                        "recordType": physical.NATIVE_RECEIPTS["vitals"],
                        "status": "complete", "output": str(destination)}), "")

                with patch.object(physical, "NATIVE_EXE", executable), \
                     patch.object(physical.socket, "gethostname", return_value="AMD-DESKTOP"), \
                     patch.object(physical.subprocess, "run", side_effect=fake_run):
                    result = physical.read_native(selection, "vitals", destination, samples=3, interval_ms=0)
                with self.subTest(mana=mana_reason, energy=energy_reason):
                    self.assertEqual(expected, result["status"])
                    if expected == "complete":
                        self.assertEqual("current-reader-contract-checked",
                                         result["nativeValues"]["unavailableReasonProvenance"])
                    else:
                        self.assertEqual("invalid-native-reader-report", result["reason"])

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
