"""Durable, explicit progress for short recorded waypoint routes.

This module never reads the game or sends input. The caller supplies fresh pose,
confirms settled waypoint arrivals, and stops if a checkpoint cannot be saved.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from scripts.waypoint_limits import MAX_ROUTE_DISTANCE, MAX_WAYPOINTS


class ProgressError(ValueError):
    pass


def _number(value):
    if isinstance(value, bool):
        raise ProgressError("coordinates must be finite numbers")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProgressError("coordinates must be finite numbers") from exc
    if not math.isfinite(value):
        raise ProgressError("coordinates must be finite numbers")
    return value


def _position(value):
    if not isinstance(value, dict) or "x" not in value or "z" not in value:
        raise ProgressError("position requires x and z")
    result = {axis: _number(value[axis]) for axis in ("x", "z")}
    if "y" in value and value["y"] is not None:
        result["y"] = _number(value["y"])
    return result


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ProgressError("invalid checkpoint data") from exc


def write_json_atomic(path, document, *, durable=True):
    """Atomically replace JSON; durable writes also synchronize the temporary file."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical(document) + "\n")
            stream.flush()
            if durable:
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _route(document):
    if not isinstance(document, dict):
        raise ProgressError("route document must be an object")
    rows = document.get("waypoints")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_WAYPOINTS:
        raise ProgressError(f"route must have 1-{MAX_WAYPOINTS} waypoints")
    points = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 3 or not isinstance(row[0], str):
            raise ProgressError("each waypoint needs name, X and Z")
        points.append([row[0], _number(row[1]), _number(row[2])])
    distance = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(points, points[1:]))
    if distance > MAX_ROUTE_DISTANCE:
        raise ProgressError(f"route exceeds {MAX_ROUTE_DISTANCE:g} world units")
    heights = document.get("heights")
    if heights is not None:
        if not isinstance(heights, list) or len(heights) != len(points):
            raise ProgressError("heights must match waypoints")
        heights = [None if y is None else _number(y) for y in heights]
    return points, heights


def _distance(a, b):
    return math.hypot(a["x"] - b["x"], a["z"] - b["z"])


class RouteProgress:
    """Checkpoint cursor over a fixed route and stable machine/build/player identity."""

    def __init__(self, document, direction="forward", identity=None):
        if direction not in ("forward", "reverse"):
            raise ProgressError("direction must be forward or reverse")
        if not isinstance(identity, dict) or not all(isinstance(identity.get(k), str) and identity[k] for k in ("machine", "gameBuildSha256", "unitKey")):
            raise ProgressError("identity requires machine, build and player")
        self.identity = {"machine": identity["machine"].casefold(),
                         "gameBuildSha256": identity["gameBuildSha256"].casefold(),
                         "unitKey": identity["unitKey"]}
        self.points, self.heights = _route(document)
        self.document = json.loads(_canonical(document))
        self.direction = direction
        self.route_hash = hashlib.sha256(_canonical({"waypoints": self.points, "heights": self.heights,
                                                      "direction": direction}).encode("utf-8")).hexdigest()
        self.next_index = 0
        self.start = None

    def _ordered(self):
        indexes = range(len(self.points)) if self.direction == "forward" else range(len(self.points) - 1, -1, -1)
        return list(indexes)

    def _point(self, ordered_index):
        index = self._ordered()[ordered_index]
        _, x, z = self.points[index]
        result = {"x": x, "z": z}
        if self.heights is not None and self.heights[index] is not None:
            result["y"] = self.heights[index]
        return result

    def remaining_points(self):
        return [tuple(self.points[i]) for i in self._ordered()[self.next_index:]]

    @property
    def ordered_points(self):
        return [tuple(self.points[i]) for i in self._ordered()]

    def begin(self, current_position):
        """Admit a fresh stationary pose; no movement starts here."""
        current = _position(current_position)
        if self.next_index >= len(self.points):
            raise ProgressError("route already complete")
        goal = self._point(self.next_index)
        if self.start is None:
            if _distance(current, goal) > 0.30 + 1e-9:
                raise ProgressError("start is too far from the route endpoint")
            start = current
        else:
            start = self.start if self.next_index == 0 else self._point(self.next_index - 1)
            dx, dz = goal["x"] - start["x"], goal["z"] - start["z"]
            length2 = dx * dx + dz * dz
            t = 0.0 if not length2 else ((current["x"] - start["x"]) * dx + (current["z"] - start["z"]) * dz) / length2
            projection = {"x": start["x"] + max(0.0, min(1.0, t)) * dx,
                          "z": start["z"] + max(0.0, min(1.0, t)) * dz}
            if _distance(current, projection) > 0.50 + 1e-9:
                raise ProgressError("position is too far from the unfinished leg")
        if "y" in goal:
            if "y" not in current:
                raise ProgressError("height is required for this route")
            expected_y = goal["y"]
            if "y" in start and self.start is not None:
                dx, dz = goal["x"] - start["x"], goal["z"] - start["z"]
                length2 = dx * dx + dz * dz
                t = 0.0 if not length2 else max(0.0, min(1.0, ((current["x"] - start["x"]) * dx + (current["z"] - start["z"]) * dz) / length2))
                expected_y = start["y"] + t * (goal["y"] - start["y"])
            if abs(current["y"] - expected_y) > 1.0:
                raise ProgressError("position is on a different height")
        remaining = self.remaining_points()
        distance = _distance(current, goal)
        distance += sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(remaining, remaining[1:]))
        if distance > MAX_ROUTE_DISTANCE:
            raise ProgressError(f"remaining route exceeds {MAX_ROUTE_DISTANCE:g} world units")
        if self.start is None:
            self.start = current
        return distance

    def confirm_arrival(self, index, goal):
        """Advance only after the caller has verified a released, settled arrival."""
        if self.start is None or type(index) is not int or index != self.next_index or index >= len(self.points):
            raise ProgressError("arrival does not match unfinished waypoint")
        expected = self.remaining_points()[0]
        if not isinstance(goal, (list, tuple)) or len(goal) != 3 or tuple(goal) != expected:
            raise ProgressError("arrival goal does not match unfinished waypoint")
        self.next_index += 1

    def save(self, path):
        if self.start is None:
            raise ProgressError("begin before saving progress")
        payload = {"version": 1, "route": self.document, "routeHash": self.route_hash, "direction": self.direction,
                   "identity": self.identity, "nextIndex": self.next_index, "start": self.start}
        write_json_atomic(path, payload)

    @classmethod
    def load(cls, path, document, identity):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls._from_payload(payload, document, identity)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ProgressError("cannot load progress") from exc

    @classmethod
    def _from_payload(cls, payload, document, identity):
        if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
            raise ProgressError("invalid progress version")
        result = cls(document, payload.get("direction"), identity)
        stored_route = cls(payload.get("route"), payload.get("direction"), identity)
        if (payload.get("routeHash") != result.route_hash or stored_route.route_hash != result.route_hash
                or payload.get("identity") != result.identity):
            raise ProgressError("route or player/build identity changed")
        index = payload.get("nextIndex")
        if type(index) is not int or not 0 <= index <= len(result.points):
            raise ProgressError("invalid progress cursor")
        result.start = _position(payload.get("start"))
        result.next_index = index
        result.document = stored_route.document
        return result


def _archive_path(directory, document, identity):
    # Route selection does not choose a direction; the saved payload owns it.
    forward = RouteProgress(document, "forward", identity)
    key = _canonical([forward.route_hash, forward.identity]).encode("utf-8")
    return Path(directory) / (hashlib.sha256(key).hexdigest() + ".json")


def _read_if_present(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _validated_cursor(raw, document=None, identity=None):
    if raw is None:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if document is None:  # A displaced checkpoint must validate against its own route and owner.
            document, identity = payload.get("route"), payload.get("identity")
        return RouteProgress._from_payload(payload, document, identity)
    except (UnicodeError, ValueError):
        return None


def _require_unchanged(path, original):
    if _read_if_present(path) != original:
        raise ProgressError("Checkpoint changed during route switch")


def select_route_progress(active_path, archive_dir, document, identity):
    """Select an explicit route while its playback writer is idle; return its saved cursor."""
    active = Path(active_path)
    if identity is None:
        _route(document)
    destination = _archive_path(archive_dir, document, identity) if identity is not None else None
    raw = _read_if_present(active)
    old = _validated_cursor(raw)
    if old is not None:
        old_slot = _archive_path(archive_dir, old.document, old.identity)
        if old_slot == destination:
            return old
        old_slot.parent.mkdir(parents=True, exist_ok=True)
        _require_unchanged(active, raw)
        write_json_atomic(old_slot, json.loads(raw))

    incoming = _read_if_present(destination) if destination is not None else None
    selected = _validated_cursor(incoming, document, identity)
    _require_unchanged(active, raw)
    if selected is not None:
        _require_unchanged(destination, incoming)
        os.replace(destination, active)
    elif raw is not None:
        active.unlink()
    return selected


def invalidate_route_progress(active_path, archive_dir, document, identity):
    """Discard this player's cursor for the pre-edit route, including any archived copy."""
    if identity is None:
        return
    slot = _archive_path(archive_dir, document, identity)
    active = Path(active_path)
    for path in (slot, active):
        raw = _read_if_present(path)
        if _validated_cursor(raw, document, identity) is not None:
            _require_unchanged(path, raw)
            path.unlink()
