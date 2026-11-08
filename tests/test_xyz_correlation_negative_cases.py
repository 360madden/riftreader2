"""Offline correlation negative cases, including real retained report identity."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import unittest

from scripts import assess_native_xyz_reference_correlation as c
from tests.test_assess_native_xyz_reference_correlation import assess, build

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "artifacts/native-current-sampler-20261105/runs/lab1/d2d11975e54b41bf9155a90269c6703b/samples.json"
TYPED = ROOT / "artifacts/validation/rr2r1-lab1-live-assessment-20261106-b/capture-03-to-capture-07.json"


class CorrelationNegativeTests(unittest.TestCase):
    def test_actual_retained_process_mismatch_is_rejected(self):
        if not NATIVE.is_file() or not TYPED.is_file():
            self.skipTest("retained Lab1 artifacts unavailable")
        n = json.loads(NATIVE.read_text(encoding="utf-8-sig"))
        t = json.loads(TYPED.read_text(encoding="utf-8-sig"))
        self.assertEqual(n["identity"]["processId"], 6820)
        self.assertEqual(t["identity"]["processId"], 11672)
        with self.assertRaisesRegex(ValueError, "process or build identity mismatch"):
            assess(n, t)

    def test_report_hash_mismatch_and_duplicate_keys_rejected(self):
        if not NATIVE.is_file():
            self.skipTest("retained Lab1 artifact unavailable")
        with self.assertRaisesRegex(ValueError, "report SHA256 mismatch"):
            c.read_report(NATIVE, "A" * 64)
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            c._pairs([("x", 1), ("x", 2)])

    def test_tolerance_uses_unrounded_difference(self):
        n, t = build()
        n["observations"][0]["x"] = .010000001
        r = assess(n, t, tolerance=.01)
        self.assertEqual(r["status"], "api-influenced-coordinate-disagreement")
        self.assertGreater(r["pairs"][0]["nativeMinusReference"]["x"], .01)

    def test_dotnet_100ns_precision_is_preserved(self):
        a = c.utc("2026-11-08T00:00:00.0000001Z")
        b = c.utc("2026-11-08T00:00:00.0000009Z")
        self.assertEqual(b - a, 8)
        self.assertEqual(c.utc("2026-11-08T00:00:00.0000009+00:00"), b)
        with self.assertRaises(ValueError):
            c.utc("2026-11-08T00:00:00.00000099Z")

    def test_pure_assess_does_not_claim_it_hashed_original_snapshot_files(self):
        n, t = build()
        r = assess(n, t)
        self.assertNotIn("were hash checked", r["limitations"][0],
                         "assess received strings and no paths, so cannot verify actual files")


if __name__ == "__main__":
    unittest.main()
