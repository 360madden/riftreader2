"""Synthetic guard track coverage; no live process or game access."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import summarize_native_xyz_guard_track as s
from tests.test_project_xyz_track import fixture


def tagged():
    report = fixture()
    report["identity"]["processStartUtcTicks"] = 639296903905448486
    for row in report["observations"]:
        row.update(unitKey="18446744073709551615", unitIdCandidate="uFFFFFFFFFFFFFFFF",
                   ownerIdentityStatus="player-component-chain-anchored")
        row.update(refreshHandleHex="0x0000000000000000", refreshFlagRaw=0,
                   refreshGuardStatus="guard-ineligible-candidate")
    return report


def summarize(report, gap=5, speed=10):
    return s.summarize(report, max_gap_seconds=gap, max_speed_3d=speed)


class GuardTrackTests(unittest.TestCase):
    def test_exact_identity_raw_guard_and_unknown_semantics(self):
        report = tagged()
        result = summarize(report)
        self.assertEqual(result["processIdentity"]["processStartUtcTicks"], "639296903905448486")
        self.assertEqual(result["sourceBuildSha256"], report["sourceBuildSha256"])
        self.assertEqual(result["sampledUnitKey"], "18446744073709551615")
        self.assertEqual(result["ownerIdentityStatus"], "player-component-chain-anchored")
        self.assertEqual(result["observations"][0]["unitIdCandidate"], "uFFFFFFFFFFFFFFFF")
        self.assertEqual(result["observations"][0]["refreshFlagRaw"], 0)
        self.assertIsNone(result["observations"][0]["guardChanged"])
        self.assertEqual(result["writerExecution"], "unavailable-in-source")
        self.assertEqual(result["passiveFreshness"], "unqualified")
        self.assertEqual(result["facing"], "unqualified")
        self.assertEqual(report, tagged())

    def test_all_four_known_pair_classes(self):
        for xyz_change, guard_change, expected in (
            (False, False, "xyz-and-guard-unchanged"),
            (False, True, "guard-only-change"),
            (True, False, "xyz-only-change"),
            (True, True, "xyz-and-guard-change"),
        ):
            with self.subTest(expected=expected):
                report = tagged()
                if not xyz_change:
                    report["observations"][1].update(x=0, y=0, z=0)
                if guard_change:
                    report["observations"][1].update(refreshFlagRaw=255,
                        refreshGuardStatus="alternate-flag-guard-candidate")
                out = summarize(report)
                self.assertEqual(out["observations"][1]["pairComparison"], expected)
                self.assertEqual(out["pairCounts"][expected], 1)
                self.assertEqual(out["observations"][1]["xyzChanged"], xyz_change)
                self.assertEqual(out["observations"][1]["guardChanged"], guard_change)

    def test_handle_precedes_flag_status_and_lossless_hex(self):
        report = tagged()
        report["observations"][1].update(refreshHandleHex="0xFFFFFFFFFFFFFFFF",
            refreshFlagRaw=255, refreshGuardStatus="handle-present-guard-candidate")
        out = summarize(report)
        self.assertEqual(out["observations"][1]["refreshHandleHex"], "0xFFFFFFFFFFFFFFFF")
        self.assertTrue(out["observations"][1]["guardChanged"])

    def test_legacy_absent_guard_is_not_zero_or_unchanged(self):
        for equal in (False, True):
            report = fixture()
            if equal:
                report["observations"][1].update(x=0, y=0, z=0)
            out = summarize(report)
            self.assertEqual(out["refreshGuardFieldsPresentCount"], 0)
            self.assertIsNone(out["observations"][0]["refreshFlagRaw"])
            self.assertIsNone(out["observations"][1]["guardChanged"])
            self.assertEqual(out["observations"][1]["pairComparison"],
                "xyz-unchanged-guard-unknown" if equal else "xyz-changed-guard-unknown")
            self.assertEqual(out["ownerIdentityStatus"], "unavailable-in-source")

    def test_mixed_guard_availability_is_unknown_not_a_change(self):
        report = tagged()
        for field in s.GUARD_FIELDS:
            del report["observations"][0][field]
        out = summarize(report)
        self.assertEqual(out["refreshGuardFieldsPresentCount"], 1)
        self.assertIsNone(out["observations"][1]["guardChanged"])

    def test_no_guard_comparison_across_gap_or_speed_boundary(self):
        report = tagged()
        report["observations"][1].update(refreshFlagRaw=1,
            refreshGuardStatus="alternate-flag-guard-candidate")
        for kwargs in ({"gap": 1}, {"speed": 1}):
            out = summarize(report, **kwargs)
            row = out["observations"][1]
            self.assertEqual(row["pairComparison"], "unavailable-boundary")
            self.assertIsNone(row["xyzChanged"])
            self.assertIsNone(row["guardChanged"])
            self.assertEqual(sum(out["pairCounts"].values()), 0)

    def test_partial_null_and_invalid_raw_guard_rejected(self):
        changes = (
            {"refreshHandleHex": None}, {"refreshHandleHex": "0xffffffffffffffff"},
            {"refreshHandleHex": "0x0"}, {"refreshHandleHex": 0},
            {"refreshFlagRaw": None}, {"refreshFlagRaw": False}, {"refreshFlagRaw": -1},
            {"refreshFlagRaw": 256}, {"refreshFlagRaw": 0.0},
            {"refreshGuardStatus": None},
            {"refreshGuardStatus": "handle-present-guard-candidate"},
        )
        for change in changes:
            report = tagged()
            report["observations"][1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                summarize(report)
        for field in s.GUARD_FIELDS:
            report = tagged()
            del report["observations"][1][field]
            with self.assertRaises(ValueError):
                summarize(report)

    def test_invalid_epoch_owner_contract_and_negative_timing_rejected(self):
        for change in (
            lambda r: r["identity"].update(processStartUtcTicks=-1),
            lambda r: r["identity"].update(executableSha256="A" * 64),
            lambda r: r.update(sourceBuildSha256="A" * 64),
            lambda r: r["observations"][1].update(unitKey="1", unitIdCandidate="u0000000000000001"),
            lambda r: r["observations"][1].update(monotonicStartMilliseconds=-1),
            lambda r: r["observations"][1].update(startedAtUtc="2026-11-07T00:00:00Z"),
            lambda r: r["observations"][1].update(x=float("nan")),
        ):
            report = tagged()
            change(report)
            with self.assertRaises(ValueError):
                summarize(report)
        with self.assertRaises(ValueError):
            summarize([tagged(), tagged()])

    def test_two_to_thirty_sample_bound(self):
        report = tagged()
        report["observations"].pop()
        report["requestedSamples"] = report["completedSamples"] = 1
        with self.assertRaises(ValueError):
            summarize(report)
        report = tagged()
        template = deepcopy(report["observations"][0])
        report["observations"] = []
        for i in range(30):
            row = deepcopy(template)
            row.update(index=i+1, monotonicStartMilliseconds=1000*i,
                       monotonicEndMilliseconds=1000*i+100,
                       startedAtUtc=f"2026-11-08T00:00:{i:02d}Z",
                       completedAtUtc=f"2026-11-08T00:00:{i:02d}.100Z")
            report["observations"].append(row)
        report["requestedSamples"] = report["completedSamples"] = 30
        self.assertEqual(summarize(report)["pairCounts"]["xyz-and-guard-unchanged"], 29)
        report["requestedSamples"] = report["completedSamples"] = 31
        with self.assertRaises(ValueError):
            summarize(report)

    def test_cli_exact_source_hash_and_fail_closed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "samples.json"
            data = ("\ufeff" + json.dumps(tagged())).encode("utf-8")
            path.write_bytes(data)
            args = [str(path), "--max-gap-seconds", "5", "--max-speed-3d", "10"]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(s.main(args), 0)
            self.assertEqual(json.loads(output.getvalue())["sourceSha256"],
                             hashlib.sha256(data).hexdigest().upper())
            for data in ('{"a":1,"a":2}', '[]', '{'):
                path.write_text(data, encoding="utf-8")
                with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(s.main(args), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(json.loads(error.getvalue())["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
