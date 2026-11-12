"""Bounded heading decisions for the physical waypoint prototype; no input."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class TurnAction:
    key: str
    hold_ms: int
    error_degrees: float


def heading_error(target, current):
    if not math.isfinite(target) or not math.isfinite(current):
        raise ValueError("Facing must be finite")
    return (target - current + 180) % 360 - 180


def choose_turn(current, target, rates):
    """A increases +Z-to-+X bearing; D decreases it. Leave 1 degree for timing."""
    error = heading_error(target, current)
    if abs(error) <= 4:
        return None
    key = "a" if error > 0 else "d"
    rate = rates[key]
    if not math.isfinite(rate) or not .05 <= abs(rate) <= .5 or rate * error <= 0:
        raise ValueError("Measured turn direction/rate unavailable")
    hold = max(20, min(150, round((abs(error) - 1) / abs(rate))))
    return TurnAction(key, hold, error)
