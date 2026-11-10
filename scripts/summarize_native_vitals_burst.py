"""Summarize a retained current-build native vitals burst; offline, candidate-only.

Usage: python -B scripts/summarize_native_vitals_burst.py path/to/report.json
No process, VM, desktop, controller, network or game access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.project_xyz_track import GAME_SHA

CONTRACT = "native-current-vitals-candidate-burst/1"
QUALIFICATION = "candidate-only; semantics/passive-freshness/restart-unverified"
SOURCE = "native-process-memory"
MAX_BYTES = 2_000_000
FIELDS = ("health", "mana", "energy")


def need(ok, reason):
    if not ok:
        raise ValueError("native-vitals-burst-" + reason)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def utc(value):
    need(isinstance(value, str) and len(value) <= 48, "time-invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        need(result.utcoffset() == timedelta(0), "time-not-utc")
        return result
    except (ValueError, OverflowError, TypeError):
        raise ValueError("native-vitals-burst-time-invalid") from None


def _field(value, name):
    need(type(value) is dict, "field-missing")
    status = value.get("status")
    if status == "calculated-candidate":
        a, b = value.get("current"), value.get("maximum")
        need(type(a) is int and type(b) is int and 0 <= a <= b and b > 0
             and value.get("unavailableReason") is None
             and type(value.get("inputs")) is dict, "field-invalid")
        if name == "mana":
            need(value["inputs"].get("verifiedTypeCode") == "0x072A",
                 "mana-type-invalid")
        if name == "energy":
            need(value["inputs"].get("verifiedTypeCode") == "0x072B",
                 "energy-type-invalid")
        return a, b
    need(status == "unavailable" and isinstance(value.get("unavailableReason"), str)
         and bool(value["unavailableReason"]) and value.get("current") is None
         and value.get("maximum") is None, "field-invalid")
    return None


def summarize(report, source_sha):
    need(type(report) is dict and report.get("schemaVersion") == 1
         and type(report.get("schemaVersion")) is int
         and report.get("contractVersion") == CONTRACT
         and report.get("status") == "complete"
         and report.get("sourceBuildSha256") == GAME_SHA
         and report.get("source") == SOURCE
         and report.get("qualification") == QUALIFICATION, "contract-invalid")
    identity = report.get("identity")
    need(type(identity) is dict and type(identity.get("processId")) is int
         and 0 < identity["processId"] < 2**31
         and type(identity.get("processStartUtcTicks")) is int
         and 0 < identity["processStartUtcTicks"] < 2**63
         and identity.get("executableSha256") == GAME_SHA, "identity-invalid")
    count = report.get("requestedSamples")
    rows = report.get("observations")
    need(type(count) is int and 2 <= count <= 30
         and type(report.get("completedSamples")) is int
         and report["completedSamples"] == count
         and type(rows) is list and len(rows) == count
         and report.get("observation") == rows[-1], "samples-invalid")
    elapsed = report.get("captureElapsedMilliseconds")
    need(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
         "elapsed-invalid")

    unit = None
    last_end = None
    per_field = {name: [] for name in FIELDS}
    for row in rows:
        need(type(row) is dict and row.get("identity") == identity
             and row.get("source") == SOURCE
             and row.get("qualification") == QUALIFICATION, "sample-identity-changed")
        key = row.get("unitKey")
        need(type(key) is int and 0 < key < 2**64, "unit-key-invalid")
        if unit is None:
            unit = key
        need(unit == key, "unit-changed")
        started, completed = utc(row.get("startedAtUtc")), utc(row.get("completedAtUtc"))
        need(started <= completed and (last_end is None or started >= last_end),
             "capture-overlap-or-reversed")
        last_end = completed
        for name in FIELDS:
            per_field[name].append(_field(row.get(name), name))
        if per_field["mana"][-1] is not None:
            need(per_field["energy"][-1] is None
                 and row["energy"].get("unavailableReason") == "not-energy-kind-four",
                 "resource-kind-conflict")
        if per_field["energy"][-1] is not None:
            need(per_field["mana"][-1] is None
                 and row["mana"].get("unavailableReason") == "not-mana-kind-three",
                 "resource-kind-conflict")

    resources = {}
    for name, values in per_field.items():
        first, last = values[0], values[-1]
        complete = all(item is not None for item in values)
        resources[name] = {
            "status": "complete-candidate" if complete else "incomplete-candidates",
            "availableSamples": sum(item is not None for item in values),
            "sampleCount": count,
            "firstCandidate": {"current": first[0], "maximum": first[1]} if first else None,
            "lastCandidate": {"current": last[0], "maximum": last[1]} if last else None,
            "deltaCurrentCandidate": last[0] - first[0] if first and last else None,
            "deltaMaximumCandidate": last[1] - first[1] if first and last else None,
            "minimumCurrentCandidate": min(item[0] for item in values) if complete else None,
            "maximumCurrentCandidate": max(item[0] for item in values) if complete else None,
        }
    return {
        "schemaVersion": 1, "status": "candidate-only",
        "mode": "offline-retained-native-vitals-burst",
        "sourceReportSha256": source_sha.upper(), "sourceBuildSha256": GAME_SHA,
        "processId": identity["processId"],
        "processStartUtcTicks": str(identity["processStartUtcTicks"]),
        "unitKey": str(unit), "sampleCount": count,
        "captureElapsedMilliseconds": elapsed,
        "resources": resources,
        "qualification": "strict same process/build/player and nonoverlapping UTC samples; "
                         "native values are calculated candidates; saved-file host provenance, "
                         "HP/resource semantics, passive freshness and gameplay causality "
                         "are not independently qualified",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        path = args.report
        need(not path.is_symlink() and path.is_file(), "report-unavailable")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        need(0 < len(raw) <= MAX_BYTES, "report-size-invalid")
        report = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                            parse_constant=lambda _: need(False, "nonfinite-json"))
        result = summarize(report, hashlib.sha256(raw).hexdigest())
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps({"status": "blocked", "reason": "native-vitals-burst-unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
