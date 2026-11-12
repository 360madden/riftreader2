"""Read saved waypoint progress as candidate marker states; never send input."""
from scripts.waypoint_progress import RouteProgress


def read_marker_progress(path, document, identity):
    """Map a validated checkpoint to original route numbers.

    A saved cursor is historical evidence; it does not prove playback is active
    or that the player is near a waypoint.
    """
    try:
        progress = RouteProgress.load(path, document, identity)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"status": "unavailable", "reason": str(exc)}
    count, index = len(progress.points), progress.next_index
    order = list(range(1, count + 1))
    if progress.direction == "reverse":
        order.reverse()
    states = {number: ("completed" if position < index else "next" if position == index else "pending")
              for position, number in enumerate(order)}
    return {"status": "saved-progress-candidate", "direction": progress.direction,
            "nextIndex": index, "pointCount": count,
            "nextNumber": order[index] if index < count else None, "states": states}
