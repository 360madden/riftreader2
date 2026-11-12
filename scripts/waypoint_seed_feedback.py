"""Compare a reused movement basis with ordinary, settled route pulses.

These checks describe observed consistency, not proof of timing or future motion.
The caller owns identity, freshness, input delivery and stopping on failure.
"""
import math

from scripts.waypoint_heading import heading_error


class SeedFeedbackError(ValueError):
    """A reused calibration did not agree with the observed pulse."""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SeedFeedbackError("nonfinite feedback value")
    return float(value)


def _hold(receipt, key):
    if not isinstance(receipt, dict) or receipt.get("keys") != [key]:
        raise SeedFeedbackError("receipt key mismatch")
    requested = _number(receipt.get("holdMilliseconds"))
    observed = _number(receipt.get("observedMilliseconds"))
    if not 20 <= requested <= 150 or not 20 <= observed <= requested + 50:
        raise SeedFeedbackError("invalid receipt timing")
    windows = receipt.get("keyHoldWindows")
    if windows is None:
        return observed, "executor-observed"
    timing = receipt.get("inputCallTiming")
    if not isinstance(timing, dict) or timing.get("utcOrderValid") is not True or timing.get("wallClockConsistentWithMonotonic") is not True:
        raise SeedFeedbackError("invalid timing envelope")
    if not isinstance(windows, list) or len(windows) != 1 or not isinstance(windows[0], dict):
        raise SeedFeedbackError("invalid hold window")
    window = windows[0]
    low = _number(window.get("minimumMillisecondsCandidate"))
    high = _number(window.get("maximumMillisecondsCandidate"))
    mid = _number(window.get("midpointMillisecondsCandidate"))
    if (window.get("key") != key or window.get("status") != "candidate-sendinput-hold-bounds"
            or window.get("exactKeyDownUpTimesKnown") is not False
            or window.get("gameResponseVerified") is not False
            or not 0 < low <= mid <= high <= observed + 10
            or abs(mid - (low + high) / 2) > .01
            or abs(mid - requested) > 50):
        raise SeedFeedbackError("invalid hold window")
    return mid, "sendinput-window-midpoint"


def _pose(snapshot):
    try:
        return (_number(snapshot.position.x), _number(snapshot.position.y),
                _number(snapshot.position.z), _number(snapshot.bearing))
    except AttributeError as exc:
        raise SeedFeedbackError("invalid pose") from exc


def verify_translation(before, after, calibration, receipt):
    """Check world-space calibration against one ordinary translation pulse."""
    try:
        vx, vz = _number(calibration.dx_per_ms), _number(calibration.dz_per_ms)
        key = calibration.key
    except AttributeError as exc:
        raise SeedFeedbackError("invalid translation calibration") from exc
    keys = receipt.get("keys") if isinstance(receipt, dict) else None
    if key not in ("w", "s", "q", "e") or keys != [key]:
        raise SeedFeedbackError("invalid translation key")
    hold, source = _hold(receipt, key)
    x0, y0, z0, b0 = _pose(before)
    x1, y1, z1, b1 = _pose(after)
    expected = math.hypot(vx, vz) * hold
    if expected < .005:
        raise SeedFeedbackError("translation calibration too small")
    dx, dz = x1 - x0, z1 - z0
    distance = math.hypot(dx, dz)
    along = (dx * vx + dz * vz) / math.hypot(vx, vz)
    cross = abs(dx * vz - dz * vx) / math.hypot(vx, vz)
    if (abs(heading_error(b1, b0)) > 4 or abs(y1 - y0) > .15
            or distance < .005 or along <= 0 or cross > max(.04, expected * .4)
            or along < max(.005, expected * .5 - .03)
            or along > expected * 1.75 + .03):
        raise SeedFeedbackError("translation disagrees with reused calibration")
    return {"holdMilliseconds": hold, "holdSource": source, "expectedDistance": expected,
            "alongDistance": along, "crossDistance": cross, "observedDistance": distance}


def verify_turn(before, after, key, degrees_per_ms, receipt):
    """Check signed turn rate and stationary position after one route turn."""
    if key not in ("a", "d"):
        raise SeedFeedbackError("invalid turn key")
    rate = _number(degrees_per_ms)
    if rate == 0 or (key == "a" and rate < 0) or (key == "d" and rate > 0):
        raise SeedFeedbackError("invalid turn calibration")
    hold, source = _hold(receipt, key)
    x0, y0, z0, b0 = _pose(before)
    x1, y1, z1, b1 = _pose(after)
    actual = heading_error(b1, b0)
    expected = rate * hold
    drift = math.sqrt((x1-x0)**2 + (y1-y0)**2 + (z1-z0)**2)
    if (abs(expected) >= 180 or abs(actual) < .25 or actual * expected <= 0
            or abs(actual) < max(.25, abs(expected) * .5 - 1)
            or abs(actual) > abs(expected) * 1.75 + 1 or drift > .08):
        raise SeedFeedbackError("turn disagrees with reused calibration")
    return {"holdMilliseconds": hold, "holdSource": source, "expectedDegrees": expected,
            "observedDegrees": actual, "positionDrift": drift}
