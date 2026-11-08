"""Pure pairwise XYZ tracking; no game access or acquisition.

Caller supplies monotonic capture times from one clock domain and current
monotonic time. All distance/speed thresholds are explicit and in the same
coordinate units as the inputs. X/Z are planar; Y is vertical. Output is a
candidate calculation, not proof of source freshness or position semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import re

MIN_NORMAL_FLOAT32 = 2 ** -126


@dataclass(frozen=True)
class TrackIdentity:
    process_id: int
    process_start_ticks: int
    build_sha256: str
    session: str
    world: str


@dataclass(frozen=True)
class TrackSample:
    x: float
    y: float
    z: float
    monotonic: float
    utc: datetime
    identity: TrackIdentity
    zone: str


@dataclass(frozen=True)
class TrackResult:
    status: str
    reason: str | None
    fresh: bool
    age_seconds: float
    displacement: tuple[float, float, float] | None = None
    planar_distance: float | None = None
    distance_3d: float | None = None
    velocity: tuple[float, float, float] | None = None
    planar_speed: float | None = None
    speed_3d: float | None = None


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _sample(sample):
    if not isinstance(sample, TrackSample) or not isinstance(sample.identity, TrackIdentity):
        raise ValueError("invalid sample or identity")
    ident = sample.identity
    if (type(ident.process_id) is not int or ident.process_id <= 0 or
        type(ident.process_start_ticks) is not int or ident.process_start_ticks <= 0 or
        not isinstance(ident.build_sha256, str) or
        re.fullmatch(r"[0-9A-F]{64}", ident.build_sha256) is None or
        any(not isinstance(v, str) or not v.strip() for v in (ident.session, ident.world, sample.zone))):
        raise ValueError("invalid process, build, session, world or zone identity")
    if not isinstance(sample.utc, datetime) or sample.utc.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    _number(sample.monotonic, "monotonic")
    for name in ("x", "y", "z"):
        value = _number(getattr(sample, name), name)
        if 0 < abs(value) < MIN_NORMAL_FLOAT32:
            raise ValueError(f"{name} is float32-subnormal")


def reduce_pair(previous: TrackSample | None, current: TrackSample, *,
                now_monotonic: float, stale_after: float,
                max_gap: float, max_speed_3d: float) -> TrackResult:
    """Reduce one pair. A boundary or stale result contains no motion values.

    The caller decides whether a boundary sample starts a new segment. A
    teleport-like candidate is not proof of teleport, and must not be silently
    joined to the prior segment. Time freshness is receipt age only; it does not
    prove that an underlying producer advanced.
    """
    _sample(current)
    if previous is not None:
        _sample(previous)
    now = _number(now_monotonic, "now_monotonic")
    stale = _number(stale_after, "stale_after")
    gap = _number(max_gap, "max_gap")
    limit = _number(max_speed_3d, "max_speed_3d")
    if stale <= 0 or gap <= 0 or limit <= 0:
        raise ValueError("thresholds must be positive")
    age = now - current.monotonic
    if not math.isfinite(age) or age < 0:
        raise ValueError("current sample is in the monotonic future")
    if age > stale:
        return TrackResult("stale", "receipt-age-exceeded", False, age)
    if previous is None:
        return TrackResult("boundary", "first-sample", True, age)
    if previous.identity != current.identity:
        return TrackResult("boundary", "identity-changed", True, age)
    if previous.zone != current.zone:
        return TrackResult("boundary", "zone-changed", True, age)
    dt = current.monotonic - previous.monotonic
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("monotonic timestamps must strictly advance")
    if current.utc < previous.utc:
        return TrackResult("boundary", "utc-moved-backward", True, age)
    if dt > gap:
        return TrackResult("boundary", "sample-gap", True, age)
    delta = (float(current.x) - float(previous.x), float(current.y) - float(previous.y),
             float(current.z) - float(previous.z))
    planar = math.hypot(delta[0], delta[2])
    distance = math.hypot(*delta)
    speed = distance / dt
    if not all(math.isfinite(v) for v in (*delta, planar, distance, speed)):
        raise ValueError("motion calculation overflow")
    if speed > limit:
        return TrackResult("boundary", "teleport-or-speed-limit", True, age)
    velocity = tuple(v / dt for v in delta)
    return TrackResult("motion-candidate", None, True, age, delta, planar, distance,
                       velocity, planar / dt, speed)
