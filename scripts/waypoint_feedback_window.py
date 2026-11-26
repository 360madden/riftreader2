"""Pure local route-feedback decisions for the existing ordered RouteProgress.

Call only with source-admitted observations from one unfinished leg. This
module never confirms passage, changes checkpoints, sends input, or retries
a route. A stall is a diagnostic candidate, not proof of a collision.
"""
from __future__ import annotations

import math

from scripts.waypoint_progress import ProgressError, _position


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def assess_leg_feedback(cursor, samples, *, translation_expected,
                        min_window_seconds=1.5, max_gap_seconds=.75,
                        min_progress=.15):
    """Assess a bounded, ordered feedback window without advancing the route.

    Each sample carries a caller-validated position, elapsed monotonic seconds,
    route hash and leg index. Translation must actually be expected throughout
    this window (not during a turn, deliberate pause, or combat). Freshness,
    process/owner/STOP checks belong to the acquisition/controller boundary.
    """
    if (type(translation_expected) is not bool
            or not _finite(min_window_seconds) or not .1 <= min_window_seconds <= 10
            or not _finite(max_gap_seconds) or not 0 < max_gap_seconds <= min_window_seconds
            or not _finite(min_progress) or not 0 < min_progress <= 1
            or not isinstance(samples, list) or not 3 <= len(samples) <= 64):
        raise ValueError("invalid feedback window")
    # The initial approach is not part of RouteProgress cumulative geometry.
    # Never use its zero arc distance as evidence that the player is stuck.
    if cursor.start is None or not 0 < cursor.next_index < len(cursor.points):
        raise ValueError("feedback requires an unfinished route leg after the start")
    index, route_hash = cursor.next_index, cursor.route_hash
    times, positions = [], []
    for sample in samples:
        if (not isinstance(sample, dict) or sample.get("routeHash") != route_hash
                or type(sample.get("legIndex")) is not int or sample["legIndex"] != index
                or not _finite(sample.get("elapsedSeconds"))
                or sample["elapsedSeconds"] < 0
                or times and sample["elapsedSeconds"] <= times[-1]):
            raise ValueError("feedback route, leg or timestamp mismatch")
        times.append(sample["elapsedSeconds"])
        pos = _position(sample.get("position"))
        if "y" not in pos:
            raise ValueError("feedback requires measured XYZ")
        positions.append(pos)
    span = times[-1] - times[0]
    result = {"status": "insufficient-feedback", "routeHash": route_hash,
              "legIndex": index, "sampleCount": len(samples),
              "windowSeconds": span, "translationExpected": translation_expected,
              "netProgressCandidate": None, "maxExcursionCandidate": None,
              "replanSuggested": False, "inputSent": False,
              "qualification": "Ordered geometry diagnosis only; no collision, arrival, "
                               "live freshness or movement authority."}
    if span < min_window_seconds or any(b-a > max_gap_seconds for a, b in zip(times, times[1:])):
        return result
    # Require known endpoint heights. This is not proof of measured floor
    # geometry, and planar-only routes cannot support this diagnosis.
    a, goal = cursor.route_view[index-1:index+1]
    if a["y"] is None or goal["y"] is None:
        return dict(result, status="height-context-unavailable")
    # A vertical-only or duplicate leg has no meaningful planar progress.
    if math.hypot(a["x"]-goal["x"], a["z"]-goal["z"]) <= 1e-9:
        return dict(result, status="degenerate-planar-leg")
    projections = []
    off_corridor = False
    for pos in positions:
        try:
            projections.append(cursor.locate(pos))
        except ProgressError as error:
            # Wrong height is a context failure, not a request for a detour.
            if "height" in str(error):
                return dict(result, status="height-context-mismatch")
            if "unfinished leg" in str(error):
                off_corridor = True
            else:
                raise
    if off_corridor:
        # Do not infer a stuck event during a pause or skip a later height refusal.
        return dict(result, status="off-corridor-candidate", replanSuggested=translation_expected)
    distances = [p["distanceAlong"] for p in projections]
    progress = distances[-1] - distances[0]
    origin = positions[0]
    excursion = max(math.hypot(p["x"]-origin["x"], p["z"]-origin["z"]) for p in positions)
    result.update(netProgressCandidate=progress, maxExcursionCandidate=excursion)
    # Use the already examined goal.
    last = positions[-1]
    # Being near a waypoint is not a confirmed arrival and cannot advance it.
    if math.hypot(last["x"]-goal["x"], last["z"]-goal["z"]) <= .30 and abs(last["y"]-goal["y"]) <= .50:
        return dict(result, status="near-waypoint-candidate")
    if not translation_expected:
        return dict(result, status="translation-not-expected")
    if progress >= min_progress:
        return dict(result, status="forward-progress-candidate")
    if excursion < min_progress and max(distances)-min(distances) < min_progress:
        return dict(result, status="stalled-candidate", replanSuggested=True)
    return dict(result, status="no-net-progress-candidate", replanSuggested=True)
