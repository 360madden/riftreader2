"""Offline cross-check of selected-target XYZ against an independent loaded-unit scan.

Both paths ultimately inspect RIFT process memory; equal values are corroborating
candidate evidence, not proof of selection semantics, freshness or visibility.
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
from scripts import physical_rift as physical

MAX_BYTES = 8 * 1024 * 1024
SELECTED_SINGLE = "native-current-selected-position-candidate-sample/1"
SELECTED_BURST = "native-current-selected-position-candidate-burst/1"
UNIT_SAMPLE = "native-current-unit-positions-candidate-sample/1"


def _utc(raw):
    if not isinstance(raw, str):
        raise ValueError("invalid-capture-time")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid-capture-time") from exc
    if value.utcoffset() != timedelta(0):
        raise ValueError("capture-time-must-be-utc")
    return value


def _load(path: Path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("invalid-source-file")
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("invalid-source-size")
    return physical._strict_native_json(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest()


def compare(selected: dict, units: dict, *, max_gap_seconds=120):
    if (type(max_gap_seconds) not in (int, float) or not math.isfinite(max_gap_seconds)
            or not 0 <= max_gap_seconds <= 3600):
        raise ValueError("invalid-gap-limit")
    if selected.get("schemaVersion") != 1 or selected.get("status") != "complete":
        raise ValueError("invalid-selected-report")
    version = selected.get("contractVersion")
    if version not in (SELECTED_SINGLE, SELECTED_BURST):
        raise ValueError("unsupported-selected-contract")
    if (units.get("schemaVersion") != 1 or units.get("status") != "complete"
            or units.get("contractVersion") != UNIT_SAMPLE):
        raise ValueError("invalid-units-report")
    unit_values = physical._native_values("unit-positions", units)
    unit_row = units["observation"]
    identity = unit_row["identity"]
    if version == SELECTED_BURST:
        rows = selected.get("observations")
        if (not isinstance(rows, list) or not 2 <= len(rows) <= 30
                or type(selected.get("requestedSamples")) is not int
                or selected["requestedSamples"] != len(rows)
                or selected.get("completedSamples") != len(rows)
                or selected.get("observation") != rows[-1]
                or selected.get("identity") != identity):
            raise ValueError("invalid-selected-burst")
    else:
        rows = [selected.get("observation")]
    values = []
    previous_end = None
    for row in rows:
        if not isinstance(row, dict) or row.get("identity") != identity:
            raise ValueError("mixed-process-or-build")
        start, end = _utc(row.get("startedAtUtc")), _utc(row.get("completedAtUtc"))
        if start >= end or previous_end is not None and start < previous_end:
            raise ValueError("overlapping-selected-samples")
        previous_end = end
        value = physical._native_values("selected-position", {
            "schemaVersion": 1, "status": "complete",
            "contractVersion": SELECTED_SINGLE, "observation": row})
        if value["selfKey"] != unit_row["selfKey"]:
            raise ValueError("different-player-owner")
        values.append(value)
    unit_start, unit_end = _utc(unit_row["startedAtUtc"]), _utc(unit_row["completedAtUtc"])
    if unit_start >= unit_end:
        raise ValueError("invalid-unit-acquisition")
    first = values[0]
    stable = (first["status"] == "position-candidate" and all(
        v["status"] == "position-candidate"
        and v["targetKey"] == first["targetKey"]
        and v["targetPositionXYZCandidate"] == first["targetPositionXYZCandidate"]
        for v in values))
    matched = next((u for u in unit_values["units"]
                    if stable and u["unitKey"] == first["targetKey"]), None)
    gap = min(max(0.0, (unit_start - _utc(row["completedAtUtc"])).total_seconds(),
                  (_utc(row["startedAtUtc"]) - unit_end).total_seconds())
              for row in rows)
    distance = None
    if matched is not None:
        a, b = first["targetPositionXYZCandidate"], matched["positionXYZCandidate"]
        distance = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
    if not stable:
        status = "selected-candidate-changed-or-unavailable"
    elif matched is None:
        status = "target-not-in-bounded-unit-scan"
    elif gap > max_gap_seconds:
        status = "source-times-too-far-apart"
    elif distance == 0:
        status = "exact-position-agreement-candidate"
    else:
        status = "position-disagreement-candidate"
    return {
        "schemaVersion": 1, "status": status,
        "processId": identity["processId"],
        "processStartUtcTicks": str(identity["processStartUtcTicks"]),
        "executableSha256": identity["executableSha256"],
        "selfKey": first["selfKey"], "selectedSamples": len(values),
        "selectedTargetKeyCandidate": first["targetKey"] if stable else None,
        "selectedPositionCandidate": first["targetPositionXYZCandidate"] if stable else None,
        "loadedUnitPositionCandidate": matched["positionXYZCandidate"] if matched else None,
        "positionDifference": distance, "minimumSourceSeparationSeconds": round(gap, 6),
        "maxAllowedSeparationSeconds": max_gap_seconds,
        "unitsWithPosition": unit_values["positionsFound"],
        "qualification": (
            "two owner-checked native readers under the same process/build epoch; "
            "sequential and potentially cached samples are not atomic; shared game "
            "memory structures, target-selection semantics, changed-state freshness, "
            "occlusion and restart survival remain unverified")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        selected, selected_sha = _load(args.selected)
        units, units_sha = _load(args.units)
        result = compare(selected, units, max_gap_seconds=args.max_gap_seconds)
        result["sources"] = {
            "selected": {"path": str(args.selected.resolve()), "sha256": selected_sha},
            "units": {"path": str(args.units.resolve()), "sha256": units_sha}
        }
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        print(rendered, end="")
        return 0
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
