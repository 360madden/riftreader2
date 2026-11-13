"""Small persisted display preferences; never reads RIFT or controls input."""
from __future__ import annotations

import json
import math
from pathlib import Path

from scripts.waypoint_progress import write_json_atomic


DEFAULT_STYLE = {"schemaVersion": 1, "beaconScale": 1., "opacity": 1., "labelsVisible": True}


def normalize_style(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT_STYLE)
            or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1
            or type(value.get("labelsVisible")) is not bool):
        raise ValueError("Invalid beacon appearance settings")
    for key, low, high in (("beaconScale", .5, 2.), ("opacity", .2, 1.)):
        number = value.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"Invalid beacon {key}: expected {low} through {high}")
    return {"schemaVersion": 1, "beaconScale": float(value["beaconScale"]),
            "opacity": float(value["opacity"]), "labelsVisible": value["labelsVisible"]}


def load_style(path, fallback=None):
    """Keep the last good preferences if a file is missing, malformed or oversized."""
    previous = normalize_style(DEFAULT_STYLE if fallback is None else fallback)
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return previous
        return normalize_style(json.loads(raw))
    except (OSError, UnicodeError, ValueError, TypeError):
        return previous


def save_style(path, value):
    style = normalize_style(value)
    write_json_atomic(Path(path), style)
    return style
