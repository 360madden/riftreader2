"""Offline physical movement calibration: independent native bursts and bounded vectors."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import physical_calibration as calibration
from tests.test_physical_route_preview import native


class PhysicalCalibrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"
        self.write_pair()

    def write_pair(self, before=None, after=None):
        base = native() if before is None else before
        later = deepcopy(base) if after is None else after
        for row in later["observations"]:
            row["startedAtUtc"] = row["startedAtUtc"].replace("07:06:42", "07:06:43")
            row["completedAtUtc"] = row["completedAtUtc"].replace("07:06:42", "07:06:43")
            row["x"] = base["observations"][-1]["x"] + 0.8
            row["z"] = base["observations"][-1]["z"] + 0.6
            row["y"] = base["observations"][-1]["y"]
        self.before.write_text(json.dumps(base), encoding="utf-8")
        self.after.write_text(json.dumps(later), encoding="utf-8")

    def test_w_vector_reports_candidate_not_authority(self):
        result = calibration.calibrate(self.before, self.after, "w", 100)
        self.assertEqual(result["key"], "w")
        self.assertAlmostEqual(result["dx_per_ms"], 0.008)
        self.assertAlmostEqual(result["dz_per_ms"], 0.006)
        self.assertAlmostEqual(result["horizontal_displacement"], 1)
        self.assertEqual(result["calibration_hold_ms"], 100)
        self.assertFalse(result["movementEligible"])
        self.assertFalse(result["actionVerified"])
        self.assertRegex(result["beforeReportSha256"], "^[0-9A-F]{64}$")
        self.assertNotEqual(result["beforeReportSha256"], result["afterReportSha256"])

    def test_mismatched_identity_and_player_rejected(self):
        for field in ("processId", "processStartUtcTicks", "executableSha256"):
            with self.subTest(field=field):
                value = native()
                after = native()
                after["identity"][field] = {"processId": 9999, "processStartUtcTicks": 123456789,
                                           "executableSha256": "B" * 64}[field]
                if field == "executableSha256":
                    after["sourceBuildSha256"] = "B" * 64
                self.write_pair(value, after)
                with self.assertRaises(calibration.PhysicalCalibrationError):
                    calibration.calibrate(self.before, self.after, "w", 100)
        after = native()
        for row in after["observations"]:
            row["unitKey"] = "12345"
        self.write_pair(after=after)
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "player changed"):
            calibration.calibrate(self.before, self.after, "w", 100)

    def test_reject_overlap_duplicate_and_implausible_motion(self):
        self.after.write_bytes(self.before.read_bytes())
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "independent"):
            calibration.calibrate(self.before, self.after, "w", 100)
        later = native()
        for row in later["observations"]:
            row["x"] += 1
        self.before.write_text(json.dumps(native()), encoding="utf-8")
        self.after.write_text(json.dumps(later), encoding="utf-8")
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "overlap"):
            calibration.calibrate(self.before, self.after, "w", 100)
        self.write_pair()
        after = json.loads(self.after.read_text(encoding="utf-8"))
        for row in after["observations"]:
            row["x"] += 100
        self.after.write_text(json.dumps(after), encoding="utf-8")
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "implausible"):
            calibration.calibrate(self.before, self.after, "w", 100)

    def test_physical_longer_observed_hold_reuses_short_pulse_calibration_contract(self):
        # The actual physical helper's W/Q/E experiments used 400-500 ms.
        # Importing those candidates must NOT extend the navigation action budget.
        for key, hold in (("w", 400), ("q", 500), ("e", 500)):
            with self.subTest(key=key, hold=hold):
                result = calibration.calibrate(self.before, self.after, key, hold)
                self.assertEqual(result["calibration_hold_ms"], hold)
                self.assertAlmostEqual(result["dx_per_ms"], 0.8 / hold)
                self.assertAlmostEqual(result["dz_per_ms"], 0.6 / hold)
                self.assertFalse(result["movementEligible"])
                self.assertFalse(result["actionVerified"])
        after = json.loads(self.after.read_text(encoding="utf-8"))
        for row in after["observations"]:
            row["x"] += 15
        self.after.write_text(json.dumps(after), encoding="utf-8")
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "implausible"):
            calibration.calibrate(self.before, self.after, "w", 400)

    def test_key_hold_and_cli_blocked_are_explicit(self):
        record = self.root / "q-calibration.json"
        valid = ["--before", str(self.before), "--after", str(self.after),
                 "--key", "q", "--hold-ms", "100", "--out", str(record)]
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(calibration.main(valid), 0)
        self.assertEqual(json.loads(out.getvalue()), json.loads(record.read_text(encoding="utf-8")))
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(calibration.main(valid), 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "blocked")
        with self.assertRaisesRegex(calibration.PhysicalCalibrationError, "hold_ms"):
            calibration.calibrate(self.before, self.after, "w", 1001)
        with redirect_stdout(io.StringIO()) as out:
            status = calibration.main(["--before", str(self.before), "--after", str(self.after),
                                       "--key", "w", "--hold-ms", "1001"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
