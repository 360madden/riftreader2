"""Synthetic offline relative-geometry checks; no source acquisition."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
import unittest

from scripts.xyz_track_reduce import TrackIdentity, TrackSample
from scripts.xyz_relative_candidate import UnitPositionSample, relative_candidate

IDENTITY = TrackIdentity(123, 456, "A" * 64, "session-1", "world-1")
UTC = datetime(2026, 11, 8, tzinfo=timezone.utc)


def pair(x=3, y=4, z=4):
    own = TrackSample(0, 0, 0, 10, UTC, IDENTITY, "zone-1")
    target = TrackSample(x, y, z, 10.1, UTC + timedelta(seconds=.1), IDENTITY, "zone-1")
    return (UnitPositionSample(own, 1234, "self", "clock-1"),
            UnitPositionSample(target, 2**63 + 42, "selected-target", "clock-1", 1234))


def calculate(a, b, **kwargs):
    options = dict(now_monotonic=10.2, stale_after=2, max_sample_skew=.25)
    options.update(kwargs)
    return relative_candidate(a, b, **options)


class RelativeCandidateTests(unittest.TestCase):
    def test_vector_planar_vertical_and_3d(self):
        result = calculate(*pair())
        self.assertEqual(result.status, "relative-candidate")
        self.assertEqual(result.vector, (3, 4, 4))
        self.assertEqual(result.horizontal_distance, 5)
        self.assertEqual(result.vertical_delta, 4)
        self.assertAlmostEqual(result.distance_3d, math.sqrt(41))
        self.assertAlmostEqual(result.coordinateAxisBearingDegrees, math.degrees(math.atan2(4, 3)))
        self.assertIn("candidate-only", result.qualification)

    def test_coordinate_bearing_not_compass_or_facing(self):
        for x, z, angle in ((1, 0, 0), (0, 1, 90), (-1, 0, 180), (0, -1, 270)):
            self.assertEqual(calculate(*pair(x, 0, z)).coordinateAxisBearingDegrees, angle)
        self.assertAlmostEqual(calculate(*pair(-3, 0, 4)).coordinateAxisBearingDegrees,
                               126.86989764584402)
        result = calculate(*pair(0, 5, 0))
        self.assertEqual(result.horizontal_distance, 0)
        self.assertIsNone(result.coordinateAxisBearingDegrees)
        self.assertEqual(result.distance_3d, 5)

    def test_mismatched_full_identity_and_zone_have_no_geometry(self):
        a, b = pair()
        for identity in (replace(IDENTITY, process_id=124),
                         replace(IDENTITY, process_start_ticks=457),
                         replace(IDENTITY, build_sha256="B" * 64),
                         replace(IDENTITY, session="other"),
                         replace(IDENTITY, world="other")):
            r = calculate(a, replace(b, sample=replace(b.sample, identity=identity)))
            self.assertEqual(r.status, "unavailable")
            self.assertIsNone(r.vector)
        r = calculate(a, replace(b, sample=replace(b.sample, zone="other")))
        self.assertEqual(r.reason, "zone-mismatch")
        self.assertIsNone(r.distance_3d)

    def test_stale_either_side_or_future_has_no_geometry(self):
        a, b = pair()
        self.assertEqual(calculate(a, b, now_monotonic=12.1).reason, "stale-receipt")
        stale_target = replace(b, sample=replace(b.sample, monotonic=7))
        self.assertEqual(calculate(a, stale_target).reason, "stale-receipt")
        self.assertEqual(calculate(a, b, now_monotonic=9).reason, "invalid-source-sample")

    def test_monotonic_and_utc_skew_independently_bounded(self):
        a, b = pair()
        for altered in (replace(b.sample, monotonic=10.5),
                        replace(b.sample, utc=UTC + timedelta(seconds=1))):
            r = calculate(a, replace(b, sample=altered), now_monotonic=10.6)
            self.assertEqual(r.reason, "sample-timing-skew")
            self.assertIsNone(r.vector)

    def test_binding_and_clock_require_evidence(self):
        a, b = pair()
        for altered in (replace(b, role="target-of-target"),
                        replace(b, selected_by_unit_key=None),
                        replace(b, selected_by_unit_key=999),
                        replace(b, clock_domain="clock-2"),
                        replace(b, clock_domain=""),
                        replace(b, unit_key=True)):
            self.assertEqual(calculate(a, altered).status, "unavailable")
        self.assertEqual(calculate(None, b).reason, "invalid-unit-sample")

    def test_missing_zone_world_session_and_bad_values_unavailable(self):
        a, b = pair()
        for altered in (replace(b.sample, zone=""),
                        replace(b.sample, identity=replace(IDENTITY, world="")),
                        replace(b.sample, identity=replace(IDENTITY, session="")),
                        replace(b.sample, x=float("nan")),
                        replace(b.sample, x=True),
                        replace(b.sample, x=2**-127),
                        replace(b.sample, utc=UTC.replace(tzinfo=None))):
            r = calculate(a, replace(b, sample=altered))
            self.assertEqual(r.reason, "invalid-source-sample")
            self.assertIsNone(r.vector)

    def test_overflow_and_invalid_timing_controls(self):
        a, b = pair()
        r = calculate(replace(a, sample=replace(a.sample, x=-1e308)),
                      replace(b, sample=replace(b.sample, x=1e308)))
        self.assertEqual(r.reason, "geometry-overflow")
        for controls in ({"stale_after": 0}, {"max_sample_skew": 0},
                         {"max_sample_skew": 3}, {"stale_after": 61},
                         {"now_monotonic": True}, {"stale_after": float("inf")}):
            with self.assertRaises(ValueError):
                calculate(a, b, **controls)


if __name__ == "__main__":
    unittest.main()
