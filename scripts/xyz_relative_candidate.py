"""Pure self-to-selected-target geometry over explicitly bound TrackSamples.

No acquisition or report enrichment is performed. Native reports currently omit
some required unit/world/zone/clock-domain evidence; callers must not fabricate it.
X/Z are horizontal and Y vertical by this candidate coordinate convention.
coordinateAxisBearingDegrees uses atan2(deltaZ, deltaX), degrees [0,360):
+X=0, +Z=90, -X=180, -Z=270; same convention as AddonGuidanceCalculator.
It is NOT compass heading, player-relative facing, navigation readiness or proof
of producer freshness. Receipt age alone cannot establish passive refresh.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from scripts.xyz_track_reduce import TrackSample, reduce_pair


@dataclass(frozen=True)
class UnitPositionSample:
    sample: TrackSample
    unit_key: int
    role: str
    clock_domain: str
    selected_by_unit_key: int | None = None


@dataclass(frozen=True)
class RelativeCandidate:
    status: str
    reason: str | None
    qualification: str = "candidate-only; source semantics and passive freshness unverified"
    self_age_seconds: float | None = None
    target_age_seconds: float | None = None
    sample_skew_seconds: float | None = None
    vector: tuple[float, float, float] | None = None
    horizontal_distance: float | None = None
    vertical_delta: float | None = None
    distance_3d: float | None = None
    coordinateAxisBearingDegrees: float | None = None


def relative_candidate(self_position: UnitPositionSample,
                       selected_target: UnitPositionSample, *,
                       now_monotonic: float, stale_after: float,
                       max_sample_skew: float) -> RelativeCandidate:
    """Return no geometry on missing identity, stale receipts or mismatched clocks.

    All monotonic timestamps and now must share the explicit clock_domain.
    Explicit timing limits must satisfy 0 < max_sample_skew <= stale_after <= 60.
    Invalid caller timing limits raise ValueError; invalid source data is unavailable.
    No historical self/target records are joined implicitly.
    """
    for value in (now_monotonic, stale_after, max_sample_skew):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("timing controls must be finite numbers")
    if not 0 < max_sample_skew <= stale_after <= 60:
        raise ValueError("require 0 < max_sample_skew <= stale_after <= 60")

    def unavailable(reason, a=None, b=None, skew=None):
        return RelativeCandidate("unavailable", reason, self_age_seconds=a,
                                 target_age_seconds=b, sample_skew_seconds=skew)

    def key(value):
        return type(value) is int and 0 < value <= 2**64 - 1

    if not all(isinstance(v, UnitPositionSample)
               for v in (self_position, selected_target)):
        return unavailable("invalid-unit-sample")
    if (self_position.role != "self" or selected_target.role != "selected-target"
            or not key(self_position.unit_key) or not key(selected_target.unit_key)
            or self_position.selected_by_unit_key is not None
            or not key(selected_target.selected_by_unit_key)
            or selected_target.selected_by_unit_key != self_position.unit_key):
        return unavailable("unproven-self-or-selected-target-binding")
    if (not isinstance(self_position.clock_domain, str)
            or not self_position.clock_domain.strip()
            or self_position.clock_domain != selected_target.clock_domain):
        return unavailable("clock-domain-unavailable-or-mismatched")
    first, second = self_position.sample, selected_target.sample
    try:
        # A first-sample reduction validates source/identity/UTC/numbers and age.
        # No displacement/speed is calculated, so these last two limits do not
        # impose a motion model or a speed claim on relative geometry.
        a = reduce_pair(None, first, now_monotonic=now_monotonic,
                        stale_after=stale_after, max_gap=max_sample_skew,
                        max_speed_3d=1)
        b = reduce_pair(None, second, now_monotonic=now_monotonic,
                        stale_after=stale_after, max_gap=max_sample_skew,
                        max_speed_3d=1)
    except (ValueError, TypeError, OverflowError):
        return unavailable("invalid-source-sample")
    if first.identity != second.identity:
        return unavailable("process-build-session-or-world-mismatch")
    if first.zone != second.zone:
        return unavailable("zone-mismatch")
    if not a.fresh or not b.fresh:
        return unavailable("stale-receipt", a.age_seconds, b.age_seconds)
    skew = abs(first.monotonic - second.monotonic)
    utc_skew = abs((first.utc - second.utc).total_seconds())
    if skew > max_sample_skew or utc_skew > max_sample_skew:
        return unavailable("sample-timing-skew", a.age_seconds, b.age_seconds, skew)
    delta = (float(second.x) - float(first.x),
             float(second.y) - float(first.y),
             float(second.z) - float(first.z))
    horizontal = math.hypot(delta[0], delta[2])
    distance = math.hypot(*delta)
    if not all(math.isfinite(v) for v in (*delta, horizontal, distance)):
        return unavailable("geometry-overflow", a.age_seconds, b.age_seconds, skew)
    bearing = None if horizontal == 0 else math.degrees(math.atan2(delta[2], delta[0])) % 360
    return RelativeCandidate("relative-candidate", None, self_age_seconds=a.age_seconds,
                             target_age_seconds=b.age_seconds, sample_skew_seconds=skew,
                             vector=delta, horizontal_distance=horizontal,
                             vertical_delta=delta[1], distance_3d=distance,
                             coordinateAxisBearingDegrees=bearing)
