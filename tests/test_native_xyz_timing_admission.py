"""Pure offline edge cases for native XYZ timing and report admission."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from scripts import fresh_native_xyz as native


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
START = "2026-01-01T00:00:00.0000000Z"
END = "2026-01-01T00:00:00.0000009Z"


def valid_report():
    return {
        "schemaVersion": 1, "contractVersion": "native-current-position-candidate-sample/1",
        "qualification": native.QUALIFICATION,
        "identity": {"processId": 123, "processStartUtcTicks": 456, "executablePath": "rift_x64.exe",
                     "executableSha256": native.pins.GAME_SHA, "moduleBaseAddress": 0x140000000,
                     "moduleSize": 0x4000000},
        "startedAtUtc": START, "completedAtUtc": END,
        "unitKey": "18446744073709551615", "unitIdCandidate": "uFFFFFFFFFFFFFFFF",
        "ownerIdentityStatus": "player-component-chain-anchored", "x": 1.5, "y": -2, "z": 3}


class NativeXyzTimingTests(unittest.TestCase):
    def test_seventh_fractional_digit_is_not_lost_during_comparison(self):
        report = valid_report()
        for suffix in ("Z", "+00:00"):
            observed = "2026-01-01T00:00:00.0000009" + suffix
            self.assertEqual(BASE, native.validate_response_time(report, observed, BASE, BASE))
            with self.assertRaisesRegex(native.Blocked, "response-before-sample"):
                native.validate_response_time(report, "2026-01-01T00:00:00.0000008" + suffix, BASE, BASE)

    def test_all_supported_fraction_lengths_and_utc_spellings(self):
        for fraction in ("", ".0", ".00", ".123", ".1234", ".12345", ".123456", ".1234567"):
            for suffix in ("Z", "+00:00"):
                stamp = "2026-01-01T00:00:00" + fraction + suffix
                report = {**valid_report(), "startedAtUtc": stamp, "completedAtUtc": stamp}
                with self.subTest(stamp=stamp):
                    value = native.validate_response_time(report, stamp, BASE, BASE)
                    self.assertEqual(timezone.utc, value.tzinfo)

    def test_exact_five_second_bracket_boundaries_are_inclusive(self):
        after = BASE + timedelta(seconds=2)
        lower = "2025-12-31T23:59:55.0000000Z"
        upper = "2026-01-01T00:00:07.0000000Z"
        report = {**valid_report(), "startedAtUtc": lower, "completedAtUtc": upper}
        self.assertEqual(after + timedelta(seconds=5),
                         native.validate_response_time(report, upper, BASE, after))
        report["completedAtUtc"] = lower
        self.assertEqual(BASE - timedelta(seconds=5),
                         native.validate_response_time(report, lower, BASE, after))

    def test_one_tick_outside_response_bracket_is_stale(self):
        report = valid_report()
        after = BASE + timedelta(seconds=2)
        for stamp in ("2025-12-31T23:59:54.9999999Z", "2026-01-01T00:00:07.0000001Z"):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(native.Blocked, "response-stale"):
                native.validate_response_time(report, stamp, BASE, after)

    def test_one_tick_outside_sample_bracket_is_stale(self):
        after = BASE + timedelta(seconds=2)
        for key, stamp in (
                ("startedAtUtc", "2025-12-31T23:59:54.9999999Z"),
                ("completedAtUtc", "2026-01-01T00:00:07.0000001Z")):
            report = {**valid_report(), key: stamp}
            with self.subTest(key=key), self.assertRaisesRegex(native.Blocked, "acquisition-stale"):
                native.validate_response_time(report, "2026-01-01T00:00:07Z", BASE, after)

    def test_sample_tick_inversion_and_observed_before_completed_are_rejected(self):
        report = {**valid_report(), "startedAtUtc": END, "completedAtUtc": START}
        with self.assertRaisesRegex(native.Blocked, "acquisition-stale"):
            native.validate_response_time(report, END, BASE, BASE)
        report = valid_report()
        with self.assertRaisesRegex(native.Blocked, "response-before-sample"):
            native.validate_response_time(report, START, BASE, BASE)

    def test_invalid_host_window_and_timezone_are_rejected(self):
        non_utc = BASE.astimezone(timezone(timedelta(hours=1)))
        for before, after in (
                (BASE + timedelta(microseconds=1), BASE),
                (BASE.replace(tzinfo=None), BASE), (BASE, BASE.replace(tzinfo=None)),
                (non_utc, BASE), (BASE, non_utc), (None, BASE), (BASE, float("nan"))):
            with self.subTest(before=before, after=after), self.assertRaises(native.Blocked):
                native.validate_response_time(valid_report(), END, before, after)

    def test_malformed_missing_and_nonfinite_guest_times_are_rejected(self):
        malformed = (
            None, True, 123, float("nan"), float("inf"), "", "bad",
            "2026-01-01T00:00:00", "2026-01-01T00:00:00-00:00",
            "2026-01-01T01:00:00+01:00", "2026-01-01T00:00:00.00000009Z",
            "2026-01-01T00:00:00.Z", "2026-13-01T00:00:00Z", "2026-01-01T00:00:60Z")
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(native.Blocked):
                native.validate_response_time(valid_report(), value, BASE, BASE)
            for key in ("startedAtUtc", "completedAtUtc"):
                with self.subTest(key=key, value=value), self.assertRaises(native.Blocked):
                    native.validate_response_time({**valid_report(), key: value}, END, BASE, BASE)
        for key in ("startedAtUtc", "completedAtUtc"):
            report = valid_report()
            del report[key]
            with self.assertRaises(native.Blocked):
                native.validate_response_time(report, END, BASE, BASE)
        for report in (None, {}, [], 123):
            with self.assertRaises(native.Blocked):
                native.validate_response_time(report, END, BASE, BASE)

    def test_old_sample_cannot_be_masked_by_fresh_observation_envelope(self):
        report = {**valid_report(), "startedAtUtc": "2025-12-31T23:59:00Z",
                  "completedAtUtc": "2025-12-31T23:59:00Z"}
        with self.assertRaisesRegex(native.Blocked, "acquisition-stale"):
            native.validate_response_time(report, END, BASE, BASE)


class NativeXyzReportAdmissionTests(unittest.TestCase):
    def validate(self, report):
        return native.validate_report(report, pid=123, ticks=456)

    def test_maximum_unit_key_remains_lossless_and_zone_unavailable(self):
        result = self.validate(valid_report())
        self.assertEqual("18446744073709551615", result["unitKey"])
        self.assertEqual("uFFFFFFFFFFFFFFFF", result["unitIdCandidate"])
        self.assertEqual("unavailable-in-source-report", result["zoneStatus"])
        self.assertEqual("unqualified", result["freshness"])

    def test_unit_key_noncanonical_overflow_boolean_and_wrong_id_rejected(self):
        for value in ("0", "01", "+1", "-1", "18446744073709551616", "9" * 21,
                      "１", True, False, 123, None, float("nan")):
            with self.subTest(value=value), self.assertRaises(native.Blocked):
                self.validate({**valid_report(), "unitKey": value})
        for value in ("uffffffffffffffff", "uFFFFFFFFFFFFFFFE", "u1", None, True):
            with self.subTest(value=value), self.assertRaises(native.Blocked):
                self.validate({**valid_report(), "unitIdCandidate": value})

    def test_bool_nonfinite_missing_and_non_numeric_coordinates_rejected(self):
        for axis in ("x", "y", "z"):
            for value in (True, False, float("nan"), float("inf"), -float("inf"), None, "1", []):
                with self.subTest(axis=axis, value=value), self.assertRaises(native.Blocked):
                    self.validate({**valid_report(), axis: value})
            report = valid_report()
            del report[axis]
            with self.assertRaises(native.Blocked): self.validate(report)

    def test_schema_qualification_owner_and_identity_never_promoted(self):
        for key, value in (("schemaVersion", True), ("schemaVersion", 2),
                           ("contractVersion", "native-current-position-candidate-sample/2"),
                           ("qualification", "qualified"), ("ownerIdentityStatus", "unverified"),
                           ("identity", None)):
            with self.subTest(key=key), self.assertRaises(native.Blocked):
                self.validate({**valid_report(), key: value})
        for key, value in (("processId", True), ("processId", 124),
                           ("processStartUtcTicks", True), ("processStartUtcTicks", 457),
                           ("executableSha256", "0" * 64), ("moduleBaseAddress", True),
                           ("moduleBaseAddress", 0), ("moduleSize", True), ("moduleSize", 1)):
            report = copy.deepcopy(valid_report())
            report["identity"][key] = value
            with self.subTest(key=key), self.assertRaises(native.Blocked): self.validate(report)
        report = valid_report()
        report["zone"] = "invented"
        with self.assertRaises(native.Blocked): self.validate(report)


if __name__ == "__main__": unittest.main()
