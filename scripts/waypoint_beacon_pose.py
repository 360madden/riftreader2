"""Owned beacon-reader feedback for the pose header/radar; no input authority."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from scripts.waypoint_progress import write_json_atomic


SOURCE = "native-current-facing"
QUALIFICATION = "native-player-pose-candidate"
TARGET_FIELDS = {"hostName", "processId", "processStartUtcTicks", "executablePath", "executableSha256", "hwnd"}
BASE_FIELDS = {"version", "status", "sessionId", "sequence", "target", "playerKey", "source", "qualification"}
POSE_FIELDS = {"position", "bearing", "sampledAtUtc", "acquiredMonotonic"}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _target(value):
    _require(isinstance(value, dict) and TARGET_FIELDS <= set(value), "beacon-pose-target-required")
    result = {key: value[key] for key in TARGET_FIELDS}
    _require(all(type(result[key]) is int and result[key] > 0 for key in ("processId", "hwnd"))
             and isinstance(result["processStartUtcTicks"], str) and result["processStartUtcTicks"].isdecimal()
             and int(result["processStartUtcTicks"]) > 0
             and all(isinstance(result[key], str) and bool(result[key]) for key in
                     ("hostName", "executablePath", "executableSha256"))
             and len(result["executableSha256"]) == 64
             and all(c in "0123456789abcdefABCDEF" for c in result["executableSha256"]),
             "beacon-pose-target-invalid")
    for key in ("hostName", "executablePath", "executableSha256"):
        result[key] = result[key].casefold()
    return result


def _utc(value):
    _require(isinstance(value, str), "beacon-pose-sample-time-required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("beacon-pose-sample-time-invalid") from None
    _require(stamp.utcoffset() == timezone.utc.utcoffset(stamp), "beacon-pose-sample-time-not-utc")
    return stamp


def _base(path, target, unit_key, sequence, status):
    _target(target)
    _require(isinstance(unit_key, str) and bool(unit_key.strip()), "beacon-pose-player-required")
    _require(type(sequence) is int and sequence > 0, "beacon-pose-sequence-invalid")
    return dict(version=1, status=status, sessionId=Path(path).stem, sequence=sequence,
                target={key: target[key] for key in TARGET_FIELDS}, playerKey=unit_key,
                source=SOURCE, qualification=QUALIFICATION)


def _validate_pose(document):
    point = document.get("position")
    _require(isinstance(point, dict) and set(point) == {"x", "y", "z"}
             and all(type(value) in (int, float) and math.isfinite(value) for value in point.values()),
             "beacon-pose-position-invalid")
    _require(type(document.get("bearing")) in (int, float) and math.isfinite(document["bearing"]),
             "beacon-pose-bearing-invalid")
    acquired = document.get("acquiredMonotonic")
    _require(type(acquired) in (int, float) and math.isfinite(acquired) and acquired >= 0,
             "beacon-pose-acquisition-invalid")
    return _utc(document.get("sampledAtUtc"))


def write_pose(path, frame, sequence):
    pose = frame["playerPose"]
    document = _base(path, frame["target"], pose["playerKey"], sequence, "fresh")
    document.update(position=dict(pose["position"]), bearing=pose["bearing"],
                    sampledAtUtc=pose["sampledAtUtc"], acquiredMonotonic=frame["acquiredMonotonic"])
    _validate_pose(document)
    write_json_atomic(path, document, durable=False)
    return document


def write_unavailable(path, target, unit_key, sequence, reason):
    document = _base(path, target, unit_key, sequence, "unavailable")
    document["reason"] = (str(reason).strip() or "unavailable")[:160]
    write_json_atomic(path, document, durable=False)
    return document


def read_pose(path, target, unit_key, *, now=None, max_age=1., last_sequence=None):
    _require(type(max_age) in (int, float) and math.isfinite(max_age) and max_age > 0,
             "beacon-pose-age-limit-invalid")
    with Path(path).open("r", encoding="utf-8") as stream:
        raw = stream.read(8193)
    _require(len(raw) <= 8192, "beacon-pose-file-too-large")
    document = json.loads(raw)
    _require(isinstance(document, dict) and type(document.get("version")) is int and document["version"] == 1,
             "beacon-pose-schema-invalid")
    status = document.get("status")
    fields = BASE_FIELDS | (POSE_FIELDS if status == "fresh" else {"reason"})
    _require(status in ("fresh", "unavailable") and set(document) == fields, "beacon-pose-schema-invalid")
    _require(isinstance(unit_key, str) and bool(unit_key.strip()), "beacon-pose-player-required")
    _require(isinstance(document["target"], dict) and set(document["target"]) == TARGET_FIELDS,
             "beacon-pose-target-invalid")
    _require(document["sessionId"] == Path(path).stem and _target(document["target"]) == _target(target)
             and document["playerKey"] == unit_key, "beacon-pose-session-or-owner-mismatch")
    _require(document["source"] == SOURCE and document["qualification"] == QUALIFICATION,
             "beacon-pose-source-invalid")
    sequence = document["sequence"]
    _require(type(sequence) is int and sequence > 0 and (last_sequence is None or sequence >= last_sequence),
             "beacon-pose-sequence-regressed")
    if status == "unavailable":
        _require(isinstance(document["reason"], str) and bool(document["reason"]), "beacon-pose-reason-invalid")
        raise ValueError("beacon pose unavailable: " + document["reason"])
    stamp = _validate_pose(document)
    current = datetime.now(timezone.utc) if now is None else now
    _require(isinstance(current, datetime) and current.utcoffset() is not None, "beacon-pose-current-time-invalid")
    age = (current - stamp).total_seconds()
    _require(-.1 <= age <= max_age, "beacon-pose-stale-or-future")
    return document
