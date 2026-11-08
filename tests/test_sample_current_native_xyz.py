"""Offline regressions for the on-demand, read-only current-build XYZ host flow."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import sample_current_native_xyz as module


def report(*, pid=11572, ticks=639293038821710082, samples=3, with_unit=False):
    base = datetime(2026, 11, 5, tzinfo=timezone.utc)
    rows = []
    for index in range(samples):
        started = base + timedelta(milliseconds=index * 500)
        row = {
            "index": index + 1,
            "startedAtUtc": started.isoformat(),
            "completedAtUtc": (started + timedelta(milliseconds=90)).isoformat(),
            "monotonicStartMilliseconds": float(index * 500),
            "monotonicEndMilliseconds": float(index * 500 + 90),
            "x": 7181.801, "y": 820.882, "z": 3135.876
        }
        if with_unit:
            row.update(unitKey="123", unitIdCandidate="u000000000000007B",
                       ownerIdentityStatus="player-component-chain-anchored")
        rows.append(row)
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-position-candidate-samples/1",
        "qualification": "candidate-only-not-passive-fresh-or-player-semantic-qualified",
        "sourceBuildSha256": module.GAME_SHA,
        "status": "complete",
        "completedSamples": samples,
        "requestedSamples": samples,
        "identity": {
            "processId": pid, "processStartUtcTicks": ticks,
            "executableSha256": module.GAME_SHA
        },
        "observations": rows
    }


class FakeGuest:
    def __init__(self, *, installed=True, result=None, game_pid=11572):
        self.installed = installed
        self.result = report(with_unit=True) if result is None else result
        self.game_pid = game_pid
        self.copy_calls = 0
        self.shell_scripts = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def powershell(self, script, *, timeout=60):
        self.shell_scripts.append(script)
        return ""

    def run(self, action, *args, **kwargs):
        if action != "copyFileFromHostToGuest":
            raise AssertionError("unexpected-guest-operation")
        self.copy_calls += 1
        return ""

    def copy_from_guest(self, source, destination, *, timeout=60):
        destination = Path(destination)
        if destination.name == "identity.json":
            payload = {
                "pid": self.game_pid,
                "ticks": 639293038821710082,
                "sha": module.GAME_SHA,
                "installed": self.installed
            }
        elif destination.name == "samples.json":
            payload = self.result
        else:
            raise AssertionError("unknown-guest-file-request")
        destination.write_text(json.dumps(payload), encoding="utf-8")
        return destination


class FakeLab:
    def __init__(self, guest):
        self.guest = guest
        self.run_root = Path("artifacts")

    def _configuration(self, lab):
        return None, None, {"vmrun": "mock"}, {
            "guestRoot": r"C:\Users\Public\Documents",
        }

    def _native(self, config, settings, output):
        return {}

    def collect_identity(self, native):
        return {"pid": 20020}

    def _session(self, config, settings, vm, output):
        return self.guest


class CurrentNativeSampleHostTests(unittest.TestCase):
    def test_bounded_options_reject_bad_types_and_ranges(self):
        for lab, samples, interval in [
            ("bad", 3, 400), ("lab2", True, 400), ("lab2", 0, 400),
            ("lab2", 31, 400), ("lab2", 3, False), ("lab2", 3, -1),
            ("lab2", 3, 2001),
        ]:
            with self.subTest(lab=lab, samples=samples, interval=interval):
                with self.assertRaises(ValueError):
                    module.bounded_options(lab, samples, interval)
        module.bounded_options("lab1", 30, 2000)

    def test_valid_report_retains_candidate_only_status_and_timing(self):
        result = module.validate_report(
            report(), pid=11572, ticks=639293038821710082, samples=3)
        self.assertEqual(3, result["sampleCount"])
        self.assertAlmostEqual(90, result["maxReadMilliseconds"])
        self.assertEqual(500, result["maxStartGapMilliseconds"])
        self.assertEqual(1090, result["acquisitionSpanMilliseconds"])
        self.assertFalse(result["positionChanged"])
        self.assertTrue(result["continuousCadenceUnder4Point5s"])
        self.assertEqual(
            "candidate-only-not-passive-fresh-or-player-semantic-qualified",
            result["qualification"]
        )

    def test_track_preserves_all_rows_and_run_relative_times(self):
        source = report()
        for row in source["observations"]:
            row["monotonicStartMilliseconds"] += 1234
            row["monotonicEndMilliseconds"] += 1234
        # Return to the starting point: first/last alone must not hide the middle.
        source["observations"][1].update(x=-12.5, y=0, z=44.25)
        track = module.project_track(
            source, pid=11572, ticks=639293038821710082, samples=3)
        self.assertEqual("native-current-position-candidate-track/1", track["contractVersion"])
        self.assertEqual("candidate-only", track["status"])
        self.assertEqual(source["qualification"], track["qualification"])
        self.assertEqual("unqualified", track["freshness"])
        self.assertEqual("unavailable-in-source-report", track["unitIdentityStatus"])
        self.assertEqual(source["identity"], track["processIdentity"])
        self.assertEqual([0, 500, 1000],
                         [row["elapsedStartMilliseconds"] for row in track["observations"]])
        self.assertEqual([90, 590, 1090],
                         [row["elapsedEndMilliseconds"] for row in track["observations"]])
        for original, projected in zip(source["observations"], track["observations"]):
            for key in ("index", "startedAtUtc", "completedAtUtc", "x", "y", "z"):
                self.assertEqual(original[key], projected[key])
        self.assertEqual(-12.5, track["observations"][1]["x"])
        self.assertEqual(track["observations"][0]["x"], track["observations"][2]["x"])

    def test_track_single_sample_does_not_fabricate_movement_or_identity(self):
        source = report(samples=1)
        track = module.project_track(
            source, pid=11572, ticks=639293038821710082, samples=1)
        self.assertEqual(1, len(track["observations"]))
        self.assertEqual(0, track["observations"][0]["elapsedStartMilliseconds"])
        self.assertNotIn("unitKey", track["observations"][0])
        self.assertNotIn("speed", track["observations"][0])
        self.assertNotIn("distance", track["observations"][0])
        self.assertEqual("unqualified", track["freshness"])

    def test_track_does_not_mutate_source_report(self):
        source = report()
        original = json.loads(json.dumps(source))
        track = module.project_track(
            source, pid=11572, ticks=639293038821710082, samples=3)
        track["observations"][1]["x"] = 999
        track["processIdentity"]["processId"] = 999
        self.assertEqual(original, source)

    def test_track_reuses_identity_sequence_and_coordinate_validation(self):
        for change in ("epoch", "sequence", "coordinate"):
            source = report()
            if change == "epoch":
                source["identity"]["processStartUtcTicks"] += 1
            elif change == "sequence":
                source["observations"].reverse()
            else:
                source["observations"][1]["x"] = float("nan")
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.project_track(
                    source, pid=11572, ticks=639293038821710082, samples=3)

    def test_sampled_unit_key_is_lossless_but_not_continuity_proof(self):
        source = report()
        key = str((1 << 64) - 1)
        for row in source["observations"]:
            row.update(unitKey=key, unitIdCandidate="uFFFFFFFFFFFFFFFF",
                       ownerIdentityStatus="player-component-chain-anchored")
        summary = module.validate_report(
            source, pid=11572, ticks=639293038821710082, samples=3)
        self.assertEqual(key, summary["sampledUnit"]["unitKey"])
        self.assertIn("not-continuity-qualified", summary["sampledUnit"]["status"])
        track = module.project_track(
            source, pid=11572, ticks=639293038821710082, samples=3)
        self.assertEqual(key, track["unitKey"])
        self.assertEqual("uFFFFFFFFFFFFFFFF", track["unitIdCandidate"])
        self.assertEqual([key] * 3,
                         [row["unitKey"] for row in track["observations"]])
        self.assertEqual("unqualified", track["freshness"])
        self.assertEqual(source["identity"], track["processIdentity"])

    def test_rejects_partial_malformed_or_changed_sampled_unit(self):
        for change in ("partial", "mixed", "changed", "bad-decimal", "bad-hex",
                       "bad-status", "bool-key", "overflow", "leading-zero"):
            source = report()
            for row in source["observations"]:
                row.update(unitKey="123", unitIdCandidate="u000000000000007B",
                           ownerIdentityStatus="player-component-chain-anchored")
            row = source["observations"][1]
            if change == "partial":
                row.pop("ownerIdentityStatus")
            elif change == "mixed":
                for field in ("unitKey", "unitIdCandidate", "ownerIdentityStatus"):
                    row.pop(field)
            elif change == "changed":
                row.update(unitKey="124", unitIdCandidate="u000000000000007C")
            elif change == "bad-decimal":
                row["unitKey"] = "-123"
            elif change == "bad-hex":
                row["unitIdCandidate"] = "u000000000000007b"
            elif change == "bad-status":
                row["ownerIdentityStatus"] = "qualified"
            elif change == "bool-key":
                row["unitKey"] = True
            elif change == "overflow":
                row["unitKey"] = str(1 << 64)
            elif change == "leading-zero":
                row["unitKey"] = "0123"
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.validate_report(
                    source, pid=11572, ticks=639293038821710082, samples=3)

    def test_single_sample_does_not_establish_cadence(self):
        result = module.validate_report(
            report(samples=1), pid=11572, ticks=639293038821710082, samples=1)
        self.assertIsNone(result["maxStartGapMilliseconds"])
        self.assertEqual(90, result["acquisitionSpanMilliseconds"])
        self.assertFalse(result["continuousCadenceUnder4Point5s"])

    def test_rejects_overlapping_monotonic_intervals(self):
        source = report()
        source["observations"][1]["monotonicStartMilliseconds"] = 80.0
        with self.assertRaisesRegex(ValueError, "sample-timing-invalid"):
            module.validate_report(
                source, pid=11572, ticks=639293038821710082, samples=3)

    def test_rejects_stale_pid_epoch_build_or_promoted_qualification(self):
        cases = [
            ("identity", "processId", 1),
            ("identity", "processStartUtcTicks", 123),
            ("identity", "executableSha256", "0" * 64),
            ("", "qualification", "fresh"),
        ]
        for container, key, value in cases:
            with self.subTest(case=key):
                source = report()
                (source[container] if container else source)[key] = value
                with self.assertRaises(ValueError):
                    module.validate_report(
                        source, pid=11572, ticks=639293038821710082, samples=3)

    def test_rejects_timing_regression_and_nonfinite_xyz(self):
        for key, value in [
            ("monotonicStartMilliseconds", 0.0),
            ("monotonicEndMilliseconds", -1.0),
            ("x", float("nan")),
            ("y", float("inf")),
            ("index", 1)
        ]:
            with self.subTest(key=key):
                source = report()
                source["observations"][1][key] = value
                with self.assertRaises(ValueError):
                    module.validate_report(
                        source, pid=11572, ticks=639293038821710082, samples=3)

    def test_slow_gap_is_measured_but_not_falsely_qualified(self):
        source = report()
        row = source["observations"][2]
        row["monotonicStartMilliseconds"] = 7000.0
        row["monotonicEndMilliseconds"] = 7090.0
        row["startedAtUtc"] = datetime(2026, 11, 5, tzinfo=timezone.utc).replace(
            second=7).isoformat()
        row["completedAtUtc"] = datetime(2026, 11, 5, tzinfo=timezone.utc).replace(
            second=7, microsecond=90000).isoformat()
        info = module.validate_report(
            source, pid=11572, ticks=639293038821710082, samples=3)
        self.assertFalse(info["continuousCadenceUnder4Point5s"])

    def _run_fake(self, *, installed=True, expected_report=None, game_pid=11572):
        guest = FakeGuest(installed=installed, result=expected_report, game_pid=game_pid)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            executable = base / "RiftReader2.Live.exe"
            executable.write_bytes(b"FAKE_OFFLINE_TEST_EXE")
            with mock.patch.object(module, "READER", executable), \
                 mock.patch.object(module, "EVIDENCE", base / "runs"), \
                 mock.patch.object(module, "digest", return_value=module.READER_SHA), \
                 mock.patch.object(module, "LabCodex", return_value=FakeLab(guest)):
                result = module.run("lab2", 3, 400)
                self.assertEqual("candidate-only", result["status"])
                self.assertEqual(3, result["metrics"]["sampleCount"])
                self.assertEqual(installed, result["guestReaderReused"])
                self.assertTrue(Path(result["sourceReport"]).is_file())
                summary_path = Path(result["sourceReport"]).parent / "summary.json"
                self.assertTrue(summary_path.is_file())
                self.assertEqual(
                    module.project_track(guest.result, pid=game_pid,
                                         ticks=639293038821710082, samples=3),
                    result["track"])
                self.assertEqual(result["track"],
                                 json.loads(summary_path.read_text(encoding="utf-8"))["track"])
        return guest

    def test_reuses_existing_sha_checked_guest_binary(self):
        guest = self._run_fake(installed=True)
        self.assertEqual(0, guest.copy_calls)
        self.assertTrue(any("game-epoch-changed" in script for script in guest.shell_scripts))

    def test_stages_reader_when_not_yet_installed(self):
        guest = self._run_fake(installed=False)
        self.assertEqual(1, guest.copy_calls)

    def test_refuses_mismatched_guest_report_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            executable = base / "RiftReader2.Live.exe"
            executable.write_bytes(b"FAKE_OFFLINE_TEST_EXE")
            wrong = report()
            wrong["identity"]["processId"] = 999
            guest = FakeGuest(installed=True, result=wrong)
            with mock.patch.object(module, "READER", executable), \
                 mock.patch.object(module, "EVIDENCE", base / "runs"), \
                 mock.patch.object(module, "digest", return_value=module.READER_SHA), \
                 mock.patch.object(module, "LabCodex", return_value=FakeLab(guest)):
                with self.assertRaisesRegex(ValueError, "identity-mismatch"):
                    module.run("lab2", 3, 400)
                self.assertEqual([], list((base / "runs").rglob("summary.json")))


if __name__ == "__main__":
    unittest.main()
