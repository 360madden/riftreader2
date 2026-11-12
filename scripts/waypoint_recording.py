"""Bounded, input-free recording of observed waypoint poses."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
import time


class RecordingError(ValueError):
    """Recording is incomplete or cannot safely become a route."""


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise RecordingError("Recording pose contains a nonfinite value")
    return float(value)


def _distance(a, b):
    return math.hypot(b["x"] - a["x"], b["z"] - a["z"])


def _deviation(p, a, b):
    dx, dz = b["x"] - a["x"], b["z"] - a["z"]
    length2 = dx * dx + dz * dz
    if not length2:
        return _distance(p, a)
    t = max(0., min(1., ((p["x"] - a["x"]) * dx + (p["z"] - a["z"]) * dz) / length2))
    return math.hypot(p["x"] - (a["x"] + t * dx), p["z"] - (a["z"] + t * dz))


class RouteRecorder:
    """Observe fresh, sequential snapshots; never send input or read a process.

    identity is supplied by the caller and must contain stable machine/build/player
    identity and separate runtime identity. Identity changes require a new recorder.
    The caller owns reservation and validates identity for every observation.
    """
    def __init__(self, identity, *, max_gap_seconds=3.0, max_age_seconds=2.0):
        if not isinstance(identity, dict) or not identity:
            raise RecordingError("Recording identity is required")
        self.identity = deepcopy(identity)
        self.max_gap = _finite(max_gap_seconds)
        self.max_age = _finite(max_age_seconds)
        if self.max_gap <= 0 or self.max_age <= 0:
            raise RecordingError("Recording timing limits must be positive")
        self._points = []
        self._length = 0.
        self._failed = False
        self._finished = False

    def observe(self, snapshot, boundary=False):
        if self._failed or self._finished:
            raise RecordingError("Recording is no longer active")
        try:
            if type(boundary) is not bool:
                raise RecordingError("Invalid boundary flag")
            try:
                point = {axis: _finite(getattr(snapshot.position, axis)) for axis in ("x", "y", "z")}
                point.update(bearing=_finite(snapshot.bearing), acquired=_finite(snapshot.acquired),
                             source=snapshot.source, boundary=boundary,
                             observedAtUtc=datetime.now(timezone.utc).isoformat())
            except AttributeError as exc:
                raise RecordingError("Invalid recording pose") from exc
            if not isinstance(point["source"], str) or not point["source"]:
                raise RecordingError("Recording source is required")
            age = time.monotonic() - point["acquired"]
            if not -.1 <= age <= self.max_age:
                raise RecordingError("Stale or future recording pose")
            if self._points:
                last = self._points[-1]
                dt = point["acquired"] - last["acquired"]
                # A caller can mark the most recently observed pose as a boundary.
                if dt == 0 and boundary and all(point[k] == last[k] for k in ("x", "y", "z", "bearing", "source")):
                    last["boundary"] = True
                    return
                if dt <= 0 or dt > self.max_gap:
                    raise RecordingError("Recording poses are out of order or have a gap")
                distance3 = math.dist((point["x"], point["y"], point["z"]), (last["x"], last["y"], last["z"]))
                if distance3 > 12 * dt + .20:
                    raise RecordingError("Recording pose discontinuity or teleport")
                self._length += _distance(last, point)
                if self._length > 20:
                    raise RecordingError("Recorded path exceeds 20 units")
            if len(self._points) >= 5000:
                raise RecordingError("Recording sample limit reached")
            self._points.append(point)
        except RecordingError:
            self._failed = True
            raise

    def finish(self):
        if self._failed or self._finished:
            raise RecordingError("Recording is incomplete or already finished")
        self._finished = True
        points = self._points
        if len(points) < 2 or self._length < .05:
            raise RecordingError("Recording has no useful movement")
        # Iterative bounded-error simplification between mandatory boundaries.
        keep = {0, len(points) - 1} | {i for i, p in enumerate(points) if p["boundary"]}
        ordered = sorted(keep)
        stack = list(zip(ordered, ordered[1:]))
        while stack:
            first, last = stack.pop()
            if last <= first + 1:
                continue
            index, error = max(((i, _deviation(points[i], points[first], points[last]))
                                for i in range(first + 1, last)), key=lambda pair: pair[1])
            # A collinear reversal has zero perpendicular error but is still a
            # real turn; do not collapse a traversal that doubles back.
            a, b = points[first], points[last]
            dx, dz = b["x"] - a["x"], b["z"] - a["z"]
            length = math.hypot(dx, dz)
            if error <= .05 and length > 0:
                peak, peak_index = 0., first
                for i in range(first + 1, last + 1):
                    projection = ((points[i]["x"] - a["x"]) * dx +
                                  (points[i]["z"] - a["z"]) * dz) / length
                    if projection > peak:
                        peak, peak_index = projection, i
                    elif peak - projection > .05 and peak_index != first:
                        index, error = peak_index, peak - projection
                        break
            if error > .05:
                keep.add(index)
                stack.extend(((first, index), (index, last)))
        retained = [points[i] for i in sorted(keep)]
        # Co-located mandatory boundaries do not need multiple identical waypoints.
        deduped = []
        for point in retained:
            if deduped and _distance(deduped[-1], point) < 1e-6:
                continue
            deduped.append(point)
        if len(deduped) < 2 or len(deduped) > 20:
            raise RecordingError("Recording requires 2–20 distinct waypoints")
        route_length = sum(_distance(a, b) for a, b in zip(deduped, deduped[1:]))
        if route_length > 20:
            raise RecordingError("Recorded route exceeds 20 units")
        return {"waypoints": [[f"Recorded {i + 1}", round(p["x"], 6), round(p["z"], 6)] for i, p in enumerate(deduped)],
                "heights": [round(p["y"], 6) for p in deduped],
                "recording": {"version": 1, "complete": True, "identity": deepcopy(self.identity),
                              "sampleCount": len(points), "retainedCount": len(deduped),
                              "observedPathLength": self._length, "routeLength": route_length,
                              "maxDeviation": .05, "maxGapSeconds": self.max_gap,
                              "firstObservedAtUtc": points[0]["observedAtUtc"],
                              "lastObservedAtUtc": points[-1]["observedAtUtc"],
                              "sources": list(dict.fromkeys(p["source"] for p in points))}}
