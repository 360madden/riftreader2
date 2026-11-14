"""Export trusted native continuous-movement paths as a measured Waypoints route.

This is an offline conversion.  It never reads RIFT or sends input, and it only
retains positions that are present in the supplied native receipts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.physical_waypoints import validate_route_document
from scripts.waypoint_limits import MAX_WAYPOINTS
from scripts.waypoint_measurements import measurement, parse_projection_route
from scripts.waypoint_progress import write_json_atomic
from scripts.waypoint_route_library import normalize_context


MAX_INPUT_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z")


class ExportError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise ExportError(reason)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-json-field")
        result[key] = value
    return result


def _read(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "receipt-file-required")
    raw = path.read_bytes()
    _require(len(raw) <= MAX_INPUT_BYTES, "receipt-file-too-large")
    try:
        text = raw.decode("utf-8-sig")
        if path.suffix.casefold() == ".jsonl":
            lines = [line for line in text.splitlines() if line.strip()]
            _require(lines, "invalid-json")
            text = lines[-1]
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _value: (_ for _ in ()).throw(
                              ExportError("non-finite-json-number")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError("invalid-json") from exc


def _utc(value, reason):
    _require(isinstance(value, str) and value, reason)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExportError(reason) from exc
    _require(parsed.utcoffset() == timezone.utc.utcoffset(parsed), reason)
    return parsed


def _native_receipts(document):
    if isinstance(document, dict) and isinstance(document.get("legs"), list):
        result = []
        for leg in document["legs"]:
            result.extend(_native_receipts(leg))
        return result
    if isinstance(document, dict) and isinstance(document.get("nativeReceipt"), dict):
        return [document["nativeReceipt"]]
    if isinstance(document, dict) and isinstance(document.get("path"), list):
        return [document]
    if isinstance(document, dict) and isinstance(document.get("result"), dict):
        return _native_receipts(document["result"])
    raise ExportError("native-continuous-receipt-required")


def _identity(receipt):
    target = receipt.get("target")
    _require(isinstance(target, dict), "native-target-required")
    machine = target.get("machineName", target.get("hostName"))
    sha = target.get("executableSha256")
    pid, ticks = target.get("processId"), target.get("processStartUtcTicks")
    player = receipt.get("playerKey")
    _require(isinstance(machine, str) and machine.strip(), "native-target-required")
    _require(isinstance(sha, str) and _SHA.fullmatch(sha), "native-target-required")
    _require(type(pid) is int and pid > 0 and type(ticks) is int and ticks > 0,
             "native-target-required")
    _require(not isinstance(player, bool) and str(player).isdigit()
             and 0 < int(player) < 2**64, "native-player-key-required")
    return {
        "machine": machine.upper(), "gameBuildSha256": sha.upper(),
        "unitKey": str(player), "processId": pid,
        "processStartUtcTicks": str(ticks),
    }


def _angle_delta(left, right):
    return abs((float(right) - float(left) + 180.0) % 360.0 - 180.0)


def _samples(receipt, source, spacing, endpoints_only):
    trusted_partial = (receipt.get("status") == "halted"
                       and receipt.get("reason") == "survival-combat"
                       and receipt.get("survivalInterrupt") is True)
    _require(receipt.get("status") == "arrived" or trusted_partial,
             "native-arrival-or-survival-interrupt-required")
    _require(receipt.get("inputSent") is True
             and receipt.get("releaseSucceeded") is True
             and receipt.get("desktopInputsDown") == [], "native-release-required")
    path = receipt.get("path")
    _require(isinstance(path, list) and len(path) >= 2, "native-path-required")
    parsed = []
    previous_time = None
    for raw in path:
        _require(isinstance(raw, dict), "invalid-native-path-sample")
        values = {axis: raw.get(axis) for axis in "xyz"}
        _require(all(type(value) in (int, float) and math.isfinite(value)
                     for value in values.values()), "invalid-native-path-sample")
        bearing = raw.get("bearing")
        _require(type(bearing) in (int, float) and math.isfinite(bearing),
                 "invalid-native-path-sample")
        observed = _utc(raw.get("observedAtUtc"), "invalid-native-path-time")
        _require(previous_time is None or observed >= previous_time,
                 "native-path-time-regressed")
        previous_time = observed
        parsed.append({**values, "bearing": float(bearing),
                       "observedAtUtc": raw["observedAtUtc"],
                       "observed": observed, "source": str(Path(source).resolve())})

    if endpoints_only:
        return ([parsed[0]] if all(abs(parsed[0][axis] - parsed[-1][axis]) <= 1e-9
                                  for axis in "xyz") else [parsed[0], parsed[-1]])
    retained = [parsed[0]]
    for index, sample in enumerate(parsed[1:-1], 1):
        prior = retained[-1]
        planar = math.hypot(sample["x"] - prior["x"], sample["z"] - prior["z"])
        if (planar >= spacing or abs(sample["y"] - prior["y"]) >= 0.20
                or _angle_delta(prior["bearing"], sample["bearing"]) >= 10.0):
            retained.append(sample)
    last = parsed[-1]
    if any(abs(last[axis] - retained[-1][axis]) > 1e-9 for axis in "xyz"):
        retained.append(last)
    return retained


def _context(document):
    if isinstance(document, dict) and isinstance(document.get("data"), dict):
        document = document["data"].get("context", document["data"])
    if isinstance(document, dict) and isinstance(document.get("context"), dict):
        document = document["context"]
    try:
        value = normalize_context(document)
    except ValueError as exc:
        raise ExportError(str(exc)) from exc
    _require(isinstance(value, dict) and value.get("zoneIdCandidate")
             and value.get("observedAtUtc") and isinstance(value.get("target"), dict)
             and value.get("playerKey"), "fresh-zone-context-required")
    return value


def export_route(receipt_paths, zone_context_path, *, name="Observed continuous corridor",
                 spacing=0.5, maximum_zone_gap_seconds=30.0,
                 endpoints_only=False):
    _require(isinstance(name, str) and name.strip() and len(name.strip()) <= 120,
             "route-name-required")
    _require(type(spacing) in (int, float) and math.isfinite(spacing)
             and 0.05 <= spacing <= 5.0, "invalid-sample-spacing")
    _require(type(maximum_zone_gap_seconds) in (int, float)
             and math.isfinite(maximum_zone_gap_seconds)
             and 0 <= maximum_zone_gap_seconds <= 300, "invalid-zone-gap")
    _require(isinstance(receipt_paths, (list, tuple)) and receipt_paths,
             "receipt-file-required")

    rows, identity = [], None
    for path in receipt_paths:
        for receipt in _native_receipts(_read(path)):
            current = _identity(receipt)
            _require(identity is None or all(current[key] == identity[key]
                     for key in ("machine", "gameBuildSha256", "unitKey",
                                 "processId", "processStartUtcTicks")),
                     "native-receipt-identity-mismatch")
            identity = identity or current
            leg = _samples(receipt, path, float(spacing), endpoints_only)
            if rows and all(abs(rows[-1][axis] - leg[0][axis]) <= 1e-9 for axis in "xyz"):
                leg = leg[1:]
            rows.extend(leg)

    _require(2 <= len(rows) <= MAX_WAYPOINTS, "exported-waypoint-count-out-of-range")
    _require(all(rows[index]["observed"] >= rows[index - 1]["observed"]
                 for index in range(1, len(rows))), "receipt-order-or-time-regressed")
    context = _context(_read(zone_context_path))
    target = context["target"]
    _require(str(target.get("hostName", "")).casefold() == identity["machine"].casefold()
             and str(target.get("executableSha256", "")).casefold()
                 == identity["gameBuildSha256"].casefold()
             and str(target.get("processId")) == str(identity["processId"])
             and str(target.get("processStartUtcTicks")) == identity["processStartUtcTicks"]
             and str(context.get("playerKey")) == identity["unitKey"],
             "zone-context-identity-mismatch")
    zone_time = _utc(context["observedAtUtc"], "invalid-route-context-time")
    gap = (rows[0]["observed"] - zone_time).total_seconds()
    if gap < 0:
        gap = (zone_time - rows[-1]["observed"]).total_seconds()
    _require(gap <= maximum_zone_gap_seconds, "zone-context-too-far-from-route")

    wrapped_identity = {"runtimeIdentity": identity}
    document = {"version": 1, "routeName": name.strip(),
                "waypoints": [], "heights": [], "pointMeasurements": [],
                "routeContext": context}
    for index, row in enumerate(rows, 1):
        position = {axis: row[axis] for axis in "xyz"}
        document["waypoints"].append([f"Observed {index}", row["x"], row["z"]])
        document["heights"].append(row["y"])
        receipt = measurement(position, wrapped_identity, row["source"],
                              row["observedAtUtc"])
        receipt.update(sourceTimeKind="native-follow-route-path-sample",
                       qualification=("Exact retained native follow-route path sample; "
                                      "terrain and collision clearance are not inferred."))
        document["pointMeasurements"].append(receipt)
    validate_route_document(document)
    parse_projection_route(document)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="append", required=True, type=Path,
                        help="trusted native receipt or route-run JSON; repeat in traversal order")
    parser.add_argument("--zone-context", required=True, type=Path,
                        help="fresh `rr2-waypoints zone refresh --json` result")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="Observed continuous corridor")
    parser.add_argument("--spacing", type=float, default=0.5,
                        help="minimum planar spacing between retained actual samples; default 0.5")
    parser.add_argument("--endpoints-only", action="store_true",
                        help="retain only each leg's actual first/final native path samples")
    parser.add_argument("--max-zone-gap-seconds", type=float, default=30.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite:
            raise ExportError("output-exists")
        document = export_route(args.receipt, args.zone_context, name=args.name,
                                spacing=args.spacing,
                                maximum_zone_gap_seconds=args.max_zone_gap_seconds,
                                endpoints_only=args.endpoints_only)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(args.output, document)
        print(json.dumps({"status": "exported", "output": str(args.output.resolve()),
                          "waypointCount": len(document["waypoints"]),
                          "measuredHeightCount": len(document["heights"]),
                          "zoneIdCandidate": document["routeContext"]["zoneIdCandidate"],
                          "inputSent": False}, sort_keys=True))
        return 0
    except (ExportError, ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc),
                          "inputSent": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
