"""Offline motion-summary tests for physical native position bursts; no game I/O."""
import unittest

from scripts.physical_rift import _native_values


class PhysicalPositionMotionTests(unittest.TestCase):
    @staticmethod
    def row(index, x, y, z, unit="239816685251645959"):
        return {"index": index, "unitKey": unit, "x": x, "y": y, "z": z,
                "completedAtUtc": "2026-11-11T07:00:00Z"}

    def test_out_and_back_retains_path_when_net_is_zero(self):
        rows = [self.row(1, 0, 5, 0), self.row(2, 10, 6, 0),
                self.row(3, 0, 7, 0)]
        values = _native_values("position", {"observations": rows})
        self.assertEqual(values["sampleCount"], 3)
        self.assertEqual(values["firstPositionCandidate"], {"x": 0, "y": 5, "z": 0})
        self.assertEqual(values["netPlanarDisplacementCandidate"], 0)
        self.assertEqual(values["observedPlanarPathLengthCandidate"], 20)
        self.assertEqual(values["maxAdjacentPlanarStepCandidate"], 10)
        self.assertEqual(values["verticalDeltaCandidate"], 2)

    def test_diagonal_travel_and_single_sample(self):
        rows = [self.row(1, 1, 2, 3), self.row(2, 4, 2, 7)]
        values = _native_values("position", {"observations": rows})
        self.assertEqual(values["netPlanarDisplacementCandidate"], 5)
        self.assertEqual(values["observedPlanarPathLengthCandidate"], 5)
        self.assertEqual(values["maxAdjacentPlanarStepCandidate"], 5)
        single = _native_values("position", {"observations": [rows[0]]})
        self.assertNotIn("observedPlanarPathLengthCandidate", single)
        self.assertNotIn("maxAdjacentPlanarStepCandidate", single)

    def test_reordered_or_partial_indexes_rejected(self):
        base = [self.row(1, 0, 0, 0), self.row(2, 1, 0, 0)]
        for rows in ([base[1], base[0]],
                     [base[0], {k: v for k, v in base[1].items() if k != "index"}],
                     [{**base[0], "index": True}, base[1]]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "sample-order"):
                _native_values("position", {"observations": rows})

    def test_mixed_owner_or_nonfinite_motion_rejected(self):
        a = self.row(1, 0, 0, 0)
        b = self.row(2, 1, 0, 0, unit="239816685251645958")
        with self.assertRaisesRegex(ValueError, "owner-changed"):
            _native_values("position", {"observations": [a, b]})
        a, b = self.row(1, -1e308, 0, 0), self.row(2, 1e308, 0, 0)
        with self.assertRaisesRegex(ValueError, "motion"):
            _native_values("position", {"observations": [a, b]})
        rows = [self.row(1, 0, 0, 0), self.row(2, 1e308, 0, 0),
                self.row(3, 0, 0, 0), self.row(4, 1e308, 0, 0)]
        with self.assertRaisesRegex(ValueError, "motion"):
            _native_values("position", {"observations": rows})


if __name__ == "__main__":
    unittest.main()
