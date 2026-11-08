"""Offline, synthetic checks for the XYZ tracking reducer."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
import unittest

from scripts.xyz_track_reduce import TrackIdentity, TrackSample, reduce_pair

IDENTITY = TrackIdentity(123, 456, "A" * 64, "session-1", "world-1")
START = datetime(2026, 11, 8, tzinfo=timezone.utc)


def sample(t=10, x=0, y=0, z=0, **kwargs):
    return TrackSample(x, y, z, t, START + timedelta(seconds=t), IDENTITY, "zone-1", **kwargs)


def reduce(previous, current, **kwargs):
    options = dict(now_monotonic=current.monotonic, stale_after=2, max_gap=5, max_speed_3d=10)
    options.update(kwargs)
    return reduce_pair(previous, current, **options)


class TrackReducerTests(unittest.TestCase):
    def test_displacement_and_xz_planar_velocity(self):
        result = reduce(sample(), sample(12, 3, 4, 4))
        self.assertEqual(result.status, "motion-candidate")
        self.assertEqual(result.displacement, (3, 4, 4))
        self.assertEqual(result.planar_distance, 5)
        self.assertAlmostEqual(result.distance_3d, math.sqrt(41))
        self.assertEqual(result.velocity, (1.5, 2, 2))
        self.assertEqual(result.planar_speed, 2.5)

    def test_initial_and_stationary(self):
        self.assertEqual(reduce(None, sample()).reason, "first-sample")
        result = reduce(sample(), sample(11))
        self.assertEqual(result.displacement, (0, 0, 0))
        self.assertEqual(result.speed_3d, 0)

    def test_identity_and_zone_boundaries(self):
        original = sample()
        for identity in (replace(IDENTITY, process_id=124),
                         replace(IDENTITY, process_start_ticks=457),
                         replace(IDENTITY, build_sha256="B" * 64),
                         replace(IDENTITY, session="session-2"),
                         replace(IDENTITY, world="world-2")):
            result = reduce(original, replace(sample(11), identity=identity))
            self.assertEqual(result.reason, "identity-changed")
            self.assertIsNone(result.distance_3d)
        result = reduce(original, replace(sample(11), zone="zone-2"))
        self.assertEqual(result.reason, "zone-changed")
        self.assertIsNone(result.velocity)

    def test_gap_teleport_and_freshness_boundaries(self):
        self.assertEqual(reduce(sample(), sample(16)).reason, "sample-gap")
        self.assertEqual(reduce(sample(), sample(11, 11)).reason, "teleport-or-speed-limit")
        self.assertEqual(reduce(sample(), sample(11, 10)).status, "motion-candidate")
        self.assertEqual(reduce(None, sample(), now_monotonic=12).status, "boundary")
        result = reduce(sample(), sample(11), now_monotonic=14)
        self.assertEqual(result.status, "stale")
        self.assertFalse(result.fresh)
        self.assertIsNone(result.displacement)

    def test_bad_clocks_and_order(self):
        with self.assertRaises(ValueError):
            reduce(None, sample(), now_monotonic=9)
        for t in (9, 10):
            with self.assertRaises(ValueError):
                reduce(sample(), sample(t))
        result = reduce(sample(), replace(sample(11), utc=START))
        self.assertEqual(result.reason, "utc-moved-backward")
        with self.assertRaises(ValueError):
            reduce(None, replace(sample(), utc=START.replace(tzinfo=None)))

    def test_reject_invalid_coordinates_and_thresholds(self):
        for value in (float("nan"), float("inf"), -float("inf"), 2**-127, -(2**-127), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reduce(None, replace(sample(), x=value))
        for option in ("stale_after", "max_gap", "max_speed_3d"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                reduce(None, sample(), **{option: 0})
        self.assertEqual(reduce(None, replace(sample(), x=2**-126)).status, "boundary")

    def test_requires_exact_identity(self):
        for ident in (replace(IDENTITY, build_sha256="a" * 64),
                      replace(IDENTITY, process_id=True),
                      replace(IDENTITY, session=""),
                      replace(IDENTITY, world=" ")):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                reduce(None, replace(sample(), identity=ident))


if __name__ == "__main__":
    unittest.main()
