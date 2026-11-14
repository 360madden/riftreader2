"""Pure conversion and freshness checks for RR2-owned map clicks.

This module reads no process, window or input state.  The caller supplies a
previously rendered LocalMap and a fresh independently admitted player pose.
"""
from __future__ import annotations

import math

from scripts.waypoint_map import LocalMap, ZOOM_RADII


class ClickMoveError(ValueError):
    """An owned-map click or its cached origin is not safe to use."""


def _finite(value, label):
    if isinstance(value, bool) or type(value) not in (int, float) or not math.isfinite(value):
        raise ClickMoveError(f"{label} must be a finite number")
    return float(value)


def _view_values(view):
    if not isinstance(view, LocalMap):
        raise ClickMoveError("map view must be a LocalMap")
    values = {name: _finite(getattr(view, name), "map " + name)
              for name in ("x", "z", "bearing", "width", "height", "radius")}
    if values["width"] <= 24 or values["height"] <= 24:
        raise ClickMoveError("map view is too small for its 12-pixel inset")
    if values["radius"] not in tuple(float(radius) for radius in ZOOM_RADII):
        raise ClickMoveError("map radius is not a supported preview range")
    if not -180 <= values["bearing"] < 360:
        raise ClickMoveError("map bearing must be in [-180, 360)")
    scale = view.scale
    if isinstance(scale, bool) or type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ClickMoveError("map scale must be finite and positive")
    return values


def project_map_click(view, x, y):
    """Convert one click in the owned preview inset to candidate world X/Z."""
    values = _view_values(view)
    x, y = _finite(x, "canvas X"), _finite(y, "canvas Y")
    if not 12 <= x <= values["width"] - 12 or not 12 <= y <= values["height"] - 12:
        raise ClickMoveError("map click must be inside the 12-pixel preview inset")
    world_x, world_z = view.canvas_to_world(x, y)
    if any(not math.isfinite(value) for value in (world_x, world_z)):
        raise ClickMoveError("map click produced nonfinite world coordinates")
    return {
        "x": world_x,
        "z": world_z,
        "canvasX": x,
        "canvasY": y,
        "kind": "map-world-xz",
        "heightKnown": False,
        "terrainAvailable": False,
        "inputSent": False,
        "mapRadius": values["radius"],
        "qualification": "Player-relative owned-map X/Z projection; height, terrain, obstacles and clearance unavailable.",
    }


def _coordinate(position, name):
    value = position.get(name) if isinstance(position, dict) else getattr(position, name, None)
    return _finite(value, "current " + name)


def validate_map_origin(view, current_position, current_bearing):
    """Reject a click when the player moved or turned since its map was drawn."""
    values = _view_values(view)
    current_x, current_z = _coordinate(current_position, "x"), _coordinate(current_position, "z")
    bearing = _finite(current_bearing, "current bearing")
    if not -180 <= bearing < 360:
        raise ClickMoveError("current bearing must be in [-180, 360)")
    movement = math.hypot(current_x - values["x"], current_z - values["z"])
    heading = abs((bearing - values["bearing"] + 180) % 360 - 180)
    if movement > .05 + 1e-12:
        raise ClickMoveError("player moved since the map was rendered")
    if heading > .5 + 1e-12:
        raise ClickMoveError("player turned since the map was rendered")
    return {"status": "current", "originChange": movement, "headingChange": heading,
            "inputSent": False}
