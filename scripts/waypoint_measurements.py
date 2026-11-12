"""Pure admission of recorded routes and independently observed XYZ points."""
from copy import deepcopy
from datetime import datetime, timezone
import math
import re


TARGET_POSITION_QUALIFICATION = (
    "Static selected-target native-position candidate; no live-follow or passive-freshness "
    "qualification; world, terrain and occlusion unverified.")


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _identity(value):
    _require(isinstance(value, dict), "recording-identity-required")
    result = value.get("runtimeIdentity", value)
    _require(isinstance(result, dict) and all(isinstance(result.get(k), str) and result[k]
             for k in ("machine", "gameBuildSha256", "unitKey")), "recording-identity-required")
    return result


def _key(identity):
    value = _identity(identity)
    return value["machine"].casefold(), value["gameBuildSha256"].casefold(), value["unitKey"]


def _utc(value):
    _require(isinstance(value, str) and bool(value), "measurement-utc-required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.utcoffset() == timezone.utc.utcoffset(parsed), "measurement-utc-required")
    except (TypeError, ValueError):
        raise ValueError("measurement-utc-required") from None
    return parsed


def _position(position):
    result = {axis: position.get(axis) if isinstance(position, dict) else getattr(position, axis, None)
              for axis in ("x", "y", "z")}
    _require(all(type(v) in (int, float) and math.isfinite(v) for v in result.values()),
             "finite-recorded-xyz-heights-required")
    return result


def _receipt(receipt, xyz=None):
    _require(isinstance(receipt, dict) and type(receipt.get("version")) is int
             and receipt["version"] == 1 and receipt.get("kind") in
             ("native-player-position", "native-selected-target-position", "recorded-route-point"),
             "point-measurement-required")
    if receipt["kind"] == "native-selected-target-position":
        target_key = receipt.get("targetKey")
        _require(isinstance(target_key, str) and re.fullmatch(r"[1-9][0-9]{0,19}", target_key) is not None
                 and int(target_key) <= 18446744073709551615, "measurement-target-key-required")
        _require(receipt.get("qualification") == TARGET_POSITION_QUALIFICATION,
                 "measurement-target-qualification-required")
    else:
        _require("targetKey" not in receipt, "measurement-target-key-kind-mismatch")
    _identity(receipt.get("identity"))
    measured = _position(receipt.get("position"))
    _require(isinstance(receipt.get("source"), str) and bool(receipt["source"].strip()),
             "measurement-source-required")
    first = _utc(receipt.get("observedAtUtc"))
    if receipt["kind"] == "recorded-route-point":
        interval = receipt.get("observationIntervalUtc", {})
        _require(receipt.get("sourceTimeKind") == "route-observation-interval"
                 and isinstance(interval, dict), "recorded-observation-interval-required")
        _require(_utc(interval.get("first")) == first
                 and _utc(interval.get("last")) >= first, "recorded-observation-interval-required")
    if xyz is not None:
        _require(all(abs(measured[a] - xyz[a]) <= 1e-6 for a in xyz), "measurement-coordinate-mismatch")
    return deepcopy(receipt)


def measurement(position, identity, source, observed_at, *, kind="native-player-position", target_key=None):
    """Build one native-position receipt; no I/O or claims about continuous motion."""
    _require(kind in ("native-player-position", "native-selected-target-position"), "measurement-kind-unsupported")
    receipt = dict(version=1, kind=kind, position=_position(position),
                   identity=deepcopy(identity), source=source, observedAtUtc=observed_at)
    if kind == "native-selected-target-position":
        receipt.update(targetKey=target_key, qualification=TARGET_POSITION_QUALIFICATION)
    else:
        _require(target_key is None, "measurement-target-key-kind-mismatch")
    return _receipt(receipt)


def _points(document):
    _require(isinstance(document, dict), "projection-route-required")
    points, heights = document.get("waypoints"), document.get("heights")
    _require(isinstance(points, list) and 1 <= len(points) <= 20 and isinstance(heights, list)
             and len(points) == len(heights), "recorded-xyz-heights-required")
    parsed = []
    for number, (point, height) in enumerate(zip(points, heights), 1):
        _require(isinstance(point, list) and len(point) == 3 and isinstance(point[0], str),
                 "invalid-recorded-waypoint")
        parsed.append(dict(number=number, label=point[0], xyz=_position(dict(x=point[1], y=height, z=point[2]))))
    return parsed


def parse_projection_route(document):
    """Require a complete recording or a valid measured receipt for every XYZ."""
    _require(isinstance(document, dict), "projection-route-required")
    if "recording" in document:
        recording = document["recording"]
        _require(isinstance(recording, dict) and recording.get("complete") is True
                 and recording.get("version") == 1, "complete-recorded-route-required")
        provenance = recording.get("identity")
        identity = _identity(provenance)
        return dict(points=_points(document), identity=deepcopy(identity),
                    recordingIdentity=deepcopy(provenance), provenanceKind="recorded-route")
    points = _points(document)
    receipts = document.get("pointMeasurements")
    _require(isinstance(receipts, list) and len(receipts) == len(points), "point-measurements-required")
    receipts = [_receipt(receipt, point["xyz"]) for receipt, point in zip(receipts, points)]
    _require(all(_key(r["identity"]) == _key(receipts[0]["identity"]) for r in receipts),
             "measurement-host-build-player-identity-mismatch")
    return dict(points=points, identity=deepcopy(_identity(receipts[0]["identity"])),
                recordingIdentity=dict(kind="independent-point-observations", pointMeasurements=receipts),
                provenanceKind="independent-point-observations")


def document_measurements(document):
    """Return aligned receipts or None per unknown point, for lossless GUI edits.

    Recorded-derived timestamps identify the retained route interval, never an
    invented exact per-point observation time. Weak historical provenance stays unknown.
    """
    waypoints = document.get("waypoints", []) if isinstance(document, dict) else []
    result = [None] * len(waypoints) if isinstance(waypoints, list) else []
    if not isinstance(document, dict):
        return result
    if "recording" in document:
        try:
            points = parse_projection_route(document)["points"]
            recording = document["recording"]
            sources = recording.get("sources")
            _require(isinstance(sources, list) and bool(sources)
                     and all(isinstance(s, str) and bool(s.strip()) for s in sources), "measurement-source-required")
            first, last = recording.get("firstObservedAtUtc"), recording.get("lastObservedAtUtc")
            for i, point in enumerate(points):
                result[i] = _receipt(dict(version=1, kind="recorded-route-point", identity=recording["identity"],
                    position=point["xyz"], source=sources[0], sources=deepcopy(sources), observedAtUtc=first,
                    sourceTimeKind="route-observation-interval", observationIntervalUtc=dict(first=first, last=last)))
        except (ValueError, TypeError, KeyError):
            return result
    else:
        receipts = document.get("pointMeasurements")
        heights = document.get("heights")
        if isinstance(receipts, list) and len(receipts) == len(result) and isinstance(heights, list) and len(heights) == len(result):
            for i, (receipt, point, height) in enumerate(zip(receipts, waypoints, heights)):
                try:
                    xyz = _points(dict(waypoints=[point], heights=[height]))[0]["xyz"]
                    result[i] = _receipt(receipt, xyz)
                except (ValueError, TypeError):
                    pass
    return result
