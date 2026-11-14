"""Validation of waypoint traversal semantics in route documents."""

def point_kinds(document):
    """Return declared kinds, defaulting legacy routes to pass-through points.

    The route's destination is always an effective stop in either direction;
    this function deliberately returns the raw declaration.
    """
    points = document.get("waypoints")
    if not isinstance(points, list):
        raise ValueError("Waypoints must be a list")
    kinds = document.get("pointKinds", ["pass"] * len(points))
    if (not isinstance(kinds, list) or len(kinds) != len(points)
            or any(kind not in ("pass", "stop") or not isinstance(kind, str) for kind in kinds)):
        raise ValueError("pointKinds must align with waypoints and contain only pass or stop")
    return list(kinds)
