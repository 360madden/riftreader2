"""Display-only height comparisons; no terrain or floor identity inference.

Callers admit measurements before assigning ``displayHeightKind='measured'``.
An unlabeled numeric Y is deliberately unknown, never measurement evidence.
"""
import math


HEIGHT_CAUTION_UNITS = 1.0
ESTIMATED_HEIGHT_KINDS = frozenset(("nearest-measured-estimate", "startup-player-estimate"))


def measured_heights(document):
    """Aligned observed Y values from admitted receipts; estimates stay None."""
    from scripts.waypoint_measurements import document_measurements
    return [receipt['position']['y'] if receipt is not None else None
            for receipt in document_measurements(document)]


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def height_context(point, player_y):
    """Compare admitted route XYZ or projected display height to current player Y.

    ``floorWarning`` means measured vertical separation exceeds one unit; it is
    a caution about a *possible* other floor, never evidence of terrain/floor ID.
    Estimated differences remain approximate and never raise that warning.
    """
    point = point if isinstance(point, dict) else {}
    kind = point.get("displayHeightKind")
    if kind not in ESTIMATED_HEIGHT_KINDS and kind != "measured":
        kind = "unknown"
    xyz = point.get("xyz")
    height = xyz.get("y") if isinstance(xyz, dict) else point.get("displayHeightCandidate")
    result = dict(heightKind=kind, deltaY=None, verticalRelation="unknown",
                  floorWarning=False, label="height unknown")
    if kind == "unknown" or not _finite(height):
        result["heightKind"] = "unknown"
        return result
    estimated = kind in ESTIMATED_HEIGHT_KINDS
    prefix = "approx. " if estimated else ""
    if not _finite(player_y):
        result["label"] = f"{prefix}Y {height:.1f} · player height unavailable"
        return result
    delta = height - player_y
    if not _finite(delta):
        return result
    relation = "above" if delta > HEIGHT_CAUTION_UNITS else "below" if delta < -HEIGHT_CAUTION_UNITS else "near"
    warning = not estimated and relation != "near"
    label = (f"{prefix}{relation} {abs(delta):.1f}u" if relation != "near"
             else f"{prefix}near player height ({delta:+.1f}u)")
    if warning:
        label += " · possible other floor"
    result.update(deltaY=delta, verticalRelation=relation, floorWarning=warning, label=label)
    return result


def height_cue(context):
    """Compact marker cue: arrows for separation, tilde for every estimate."""
    prefix = "~" if context.get("heightKind") in ESTIMATED_HEIGHT_KINDS else ""
    return prefix + {"above": "↑", "below": "↓"}.get(context.get("verticalRelation"), "")
