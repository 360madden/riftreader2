"""Read-only Replay admission summaries built from the playback cursor rules.

This module reads an optional checkpoint but never saves, replaces, or removes it.
Execution must still repeat the same checks against a fresh pose before input.
"""
from pathlib import Path
import math

from scripts.waypoint_progress import ProgressError, RouteProgress


def _summary(cursor, *, ready=False, reason=""):
    remaining = cursor.remaining_points()
    return {
        "ready": bool(ready),
        "reason": str(reason),
        "direction": cursor.direction,
        "nextIndex": cursor.next_index,
        "nextName": remaining[0][0] if remaining else None,
        "remainingDistance": None,
    }


def _assess(cursor, position, unavailable_reason):
    result = _summary(cursor)
    if not cursor.remaining_points():
        result["reason"] = "route already complete"
        result["remainingDistance"] = 0.0
        return result
    if unavailable_reason:
        result["reason"] = str(unavailable_reason)
        return result
    try:
        result["remainingDistance"] = cursor.begin(position)
        result["ready"] = True
        result["reason"] = "ready"
    except (ProgressError, OSError, KeyError, TypeError, ValueError) as exc:
        result["reason"] = str(exc) or "playback readiness unavailable"
        if str(exc) == "start is too far from the route endpoint":
            endpoint = cursor.remaining_points()[0]
            distance = math.hypot(position["x"] - endpoint[1], position["z"] - endpoint[2])
            result["reason"] = f"Move within 0.30u of endpoint ({distance:.2f}u away)"
    return result


def _blocked(direction, reason):
    return {
        "ready": False,
        "reason": str(reason),
        "direction": direction,
        "nextIndex": None,
        "nextName": None,
        "remainingDistance": None,
    }


def replay_readiness(document, identity, position, checkpoint=None, unavailable_reason=None):
    """Return forward, reverse, and resume admission without sending input.

    ``unavailable_reason`` lets a caller represent transient GUI ownership, pose,
    or zone gating while retaining checkpoint direction/cursor details when the
    checkpoint itself can still be validated.
    """
    result = {}
    for direction in ("forward", "reverse"):
        try:
            cursor = RouteProgress(document, direction, identity)
            result[direction] = _assess(cursor, position, unavailable_reason)
        except (ProgressError, OSError, KeyError, TypeError, ValueError) as exc:
            result[direction] = _blocked(direction, unavailable_reason or str(exc) or "invalid route")

    if checkpoint is None:
        result["resume"] = _blocked(None, "no saved playback progress")
        return result
    try:
        path = Path(checkpoint)
        if not path.is_file():
            result["resume"] = _blocked(None, "no saved playback progress")
        else:
            cursor = RouteProgress.load(path, document, identity)
            result["resume"] = _assess(cursor, position, unavailable_reason)
    except (ProgressError, OSError, KeyError, TypeError, ValueError) as exc:
        result["resume"] = _blocked(None, str(exc) or "saved playback progress is unavailable")
    return result
