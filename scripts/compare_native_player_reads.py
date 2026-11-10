"""Compare two retained Lab2 native player readouts; strictly offline, candidate-only.

Reads the JSON output of read_native_telemetry.py (--fields position/vitals).
Does not contact VMware, controllers, game, desktop, or the network. Values are
not independent movement proof or evidence of passive field freshness.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

MAX_BYTES = 8_000_000
SHA = re.compile(r"[0-9A-Fa-f]{64}\Z")
KEY = re.compile(r"[1-9][0-9]{0,19}\Z")
FIELDS = ("position", "vitals")
RESOURCES = ("health", "energy", "mana")


def _need(condition, reason):
    if not condition:
        raise ValueError("native-player-compare-" + reason)


def _key(value):
    _need(type(value) is str and KEY.fullmatch(value)
          and int(value) <= 2**64 - 1, "unit-key-invalid")
    return value


def _utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
              "timestamp-invalid")
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("native-player-compare-timestamp-invalid") from exc


def _sha(value):
    _need(isinstance(value, str) and SHA.fullmatch(value) is not None, "sha-invalid")
    return value.upper()


def load(path: Path):
    """Read one saved file with a size bound and preserve its byte-level SHA."""
    path = Path(path)
    _need(not path.is_symlink() and path.is_file(), "source-unavailable")
    size = path.stat().st_size
    _need(0 < size <= MAX_BYTES, "source-size-invalid")
    raw = path.read_bytes()
    _need(len(raw) == size, "source-changed")
    try:
        data = json.loads(raw.decode("utf-8-sig"),
                          parse_constant=lambda _: _need(False, "nonfinite-json"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("native-player-compare-json-invalid") from exc
    _need(type(data) is dict, "root-invalid")
    return data, hashlib.sha256(raw).hexdigest().upper()


def _source(row, field, unit):
    _need(type(row) is dict and row.get("schemaVersion") == 1
          and row.get("status") == "candidate-only" and row.get("lab") == "lab2"
          and row.get("transport") == "persistent-control-agent", "source-invalid")
    _need(type(row.get("vmIdentity")) is dict
          and type(row.get("gameProcessId")) is int and row["gameProcessId"] > 0
          and type(row.get("gameProcessStartUtcTicks")) is int
          and row["gameProcessStartUtcTicks"] > 0
          and type(row.get("activeAgentInstanceId")) is str
          and re.fullmatch(r"[0-9a-f]{32}", row["activeAgentInstanceId"]) is not None,
          "identity-invalid")
    _sha(row.get("gameSha256"))
    _sha(row.get("sourceReportSha256"))
    _utc(row.get("observedAtUtc"))
    metrics = row.get("metrics")
    _need(type(metrics) is dict and _key(metrics.get("unitKey")) == unit,
          "source-unit-mismatch")
    # No source path is opened; only original report SHA pins are retained.
    return (
        row["vmIdentity"], row["gameProcessId"], row["gameProcessStartUtcTicks"],
        row["gameSha256"].upper(), row["activeAgentInstanceId"],
    )


def _check_readout(readout):
    _need(type(readout) is dict and readout.get("schemaVersion") == 1
          and readout.get("status") == "candidate-only"
          and readout.get("targetId") == "lab2"
          and readout.get("ownerHost") == "AMD-DESKTOP"
          and readout.get("mode") == "native-read-only"
          and readout.get("atomic") is False
          and readout.get("luaReaderUsed") is False
          and readout.get("screenshotUsed") is False, "readout-invalid")
    unit = _key(readout.get("unitKey"))
    fields = tuple(field for field in FIELDS if field in readout)
    _need(bool(fields), "no-fields")
    identities = [_source(readout[field], field, unit) for field in fields]
    _need(all(identity == identities[0] for identity in identities),
          "mixed-source-identity")
    return unit, fields, identities[0]


def _position(first, second):
    ma, mb = first["metrics"], second["metrics"]
    anchor = "player-component-chain-anchored"
    xyz = []
    for metrics in (ma, mb):
        point = {}
        for axis in ("x", "y", "z"):
            value = metrics.get(axis)
            if type(value) not in (int, float) or not math.isfinite(value):
                return {"status": "unavailable-xyz", "deltaCandidate": None,
                        "horizontalXZDistanceCandidate": None, "distance3dCandidate": None}
            point[axis] = float(value)
        xyz.append(point)
    if ma.get("ownerIdentityStatus") != anchor or mb.get("ownerIdentityStatus") != anchor:
        return {"status": "unavailable-owner-anchor", "deltaCandidate": None,
                "horizontalXZDistanceCandidate": None, "distance3dCandidate": None}
    delta = {a: xyz[1][a] - xyz[0][a] for a in ("x", "y", "z")}
    horizontal = math.hypot(delta["x"], delta["z"])
    distance = math.hypot(horizontal, delta["y"])
    if not all(math.isfinite(v) for v in (*delta.values(), horizontal, distance)):
        return {"status": "unavailable-overflow", "deltaCandidate": None,
                "horizontalXZDistanceCandidate": None, "distance3dCandidate": None}
    return {"status": "same-owner-displacement-candidate", "deltaCandidate": delta,
            "horizontalXZDistanceCandidate": horizontal, "distance3dCandidate": distance}


def _vitals(first, second):
    result = {}
    for field in RESOURCES:
        a, b = first["metrics"].get(field), second["metrics"].get(field)
        def value(metric):
            if (type(metric) is dict and metric.get("status") == "calculated-candidate"
                    and type(metric.get("current")) is int and metric["current"] >= 0
                    and type(metric.get("maximum")) is int and metric["maximum"] >= 0):
                return metric["current"], metric["maximum"]
            return None
        before, after = value(a), value(b)
        result[field] = {
            "beforeCandidate": before,
            "afterCandidate": after,
            "deltaCurrentCandidate": after[0] - before[0] if before and after else None,
            "deltaMaximumCandidate": after[1] - before[1] if before and after else None,
            "status": "comparable-candidate" if before and after else "unavailable",
        }
    return result


def compare(before: dict, after: dict, before_sha: str, after_sha: str) -> dict:
    _need(_sha(before_sha) != _sha(after_sha), "identical-source")
    unit_a, fields_a, identity_a = _check_readout(before)
    unit_b, fields_b, identity_b = _check_readout(after)
    _need(fields_a == fields_b, "field-selection-mismatch")
    _need(unit_a == unit_b, "unit-changed")
    _need(identity_a == identity_b, "process-vm-or-agent-changed")
    source_info = {}
    for field in fields_a:
        a, b = before[field], after[field]
        before_time, after_time = _utc(a["observedAtUtc"]), _utc(b["observedAtUtc"])
        _need(before_time < after_time, "nonadvancing-" + field)
        _need(_sha(a["sourceReportSha256"]) != _sha(b["sourceReportSha256"]),
              "reused-" + field + "-report")
        source_info[field] = {"beforeObservedAtUtc": before_time.isoformat(),
                              "afterObservedAtUtc": after_time.isoformat(),
                              "beforeReportSha256": a["sourceReportSha256"].upper(),
                              "afterReportSha256": b["sourceReportSha256"].upper()}
    comparison = {}
    if "position" in fields_a:
        comparison["position"] = _position(before["position"], after["position"])
    if "vitals" in fields_a:
        comparison["vitals"] = _vitals(before["vitals"], after["vitals"])
    return {
        "schemaVersion": 1, "status": "candidate-only",
        "mode": "offline-retained-native-readouts",
        "targetId": "lab2", "unitKey": unit_a,
        "fieldsCompared": list(fields_a),
        "beforeSourceSha256": before_sha.upper(),
        "afterSourceSha256": after_sha.upper(),
        "sourceProvenance": source_info, "comparison": comparison,
        "qualification": "strict same game/VM/agent/unit and increasing report times; "
                         "candidate arithmetic only, NOT movement proof, field semantic "
                         "qualification, passive freshness, or restart recovery",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        first, first_sha = load(args.before)
        second, second_sha = load(args.after)
        result = compare(first, second, first_sha, second_sha)
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps({"status": "blocked", "reason": "native-player-compare-unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
