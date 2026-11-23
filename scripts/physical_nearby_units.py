"""Read-only nearby named RIFT unit candidates from one exact physical process.

Combines the existing native position, name and optional numeric-level readers.
Each reader samples sequential candidates. Hostility, line of sight, world
instance and attackability remain unqualified.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift

SCHEMA = "rr2-physical-nearby-units/1"
LEVEL_BATCH_LIMIT = 12
LEVEL_SOURCE_MAX_SPAN = timedelta(seconds=30)


def require(value, reason):
    if not value:
        raise ValueError("nearby-native-units-" + reason)


def source_from_receipt(receipt, path, selection, kind):
    """Re-open original bytes, check exact owner, SHA and projected reader values."""
    require(type(receipt) is dict and receipt.get("status") == "complete"
            and receipt.get("nativeRead") == kind
            and receipt.get("target") == selection["target"],
            "source-receipt-unavailable")
    require(Path(receipt.get("nativeOutput", "")) == path,
            "source-output-path-changed")
    require(path.is_file() and not path.is_symlink(), "source-file-unavailable")
    raw = path.read_bytes()
    require(0 < len(raw) <= 16 * 1024 * 1024, "source-bytes-out-of-bounds")
    sha = hashlib.sha256(raw).hexdigest().upper()
    claimed = receipt.get("nativeSourceSha256")
    require(claimed is None or type(claimed) is str and
            claimed.casefold() == sha.casefold(), "source-sha-mismatch")
    document = physical_rift._strict_native_json(raw.decode("utf-8-sig"))
    require(type(document) is dict and type(document.get("observation")) is dict,
            "source-observation-missing")
    identity = document["observation"].get("identity")
    target = selection["target"]
    require(type(identity) is dict
            and identity.get("processId") == target["processId"]
            and str(identity.get("processStartUtcTicks")) ==
                str(target["processStartUtcTicks"])
            and str(identity.get("executableSha256", "")).casefold() ==
                str(target["executableSha256"]).casefold()
            and str(identity.get("executablePath", "")).casefold() ==
                str(target["executablePath"]).casefold(),
            "source-process-identity-mismatch")
    values = physical_rift._native_values(kind, document)
    require(values == receipt.get("nativeValues"), "source-projection-mismatch")
    return document, values, sha


def choose_nearby(positions, *, radius, limit):
    require(type(radius) in (int, float) and math.isfinite(radius)
            and 0 < radius <= 50 and type(limit) is int and 1 <= limit <= 32,
            "invalid-radius-or-limit")
    require(type(positions) is dict and type(positions.get("units")) is list
            and type(positions.get("selfKey")) is str
            and positions.get("worldCoverage") == "bounded-unit-manager-subset",
            "position-inventory-unqualified")
    nearby = [row for row in positions["units"]
              if row["unitKey"] != positions["selfKey"]
              and row["horizontalDistanceCandidate"] <= radius]
    return nearby[:limit], len(nearby)


def combine(selected, total_nearby, position_raw, positions, name_raw, names,
            pos_sha, names_sha, *, radius, limit, host=None):
    """Bind sequential names to exact owner/entity identity; never infer hostility."""
    p, n = position_raw["observation"], name_raw["observation"]
    require(n.get("identity") == p.get("identity")
            and names["selfKey"] == positions["selfKey"]
            and str(p["selfKey"]) == positions["selfKey"],
            "position-name-owner-changed")
    begin = physical_rift._utc_tick_order_key(p["completedAtUtc"])
    later = physical_rift._utc_tick_order_key(n["startedAtUtc"])
    require(begin <= later, "position-name-time-order-reversed")
    require([row["unitKey"] for row in names["rows"]] ==
            [row["unitKey"] for row in selected],
            "name-request-sequence-mismatch")
    original = {row["unitKey"]: row for row in p["rows"]}
    require(len(original) == len(p["rows"]), "duplicate-position-unit-key")
    point = p["selfPositionCandidate"]
    samples = []
    for row, named in zip(selected, names["rows"]):
        source = original.get(row["unitKey"])
        require(type(source) is dict, "position-source-unit-not-found")
        same_entity = (named["entityAddressDecimal"] ==
                       source["entityAddressDecimal"])
        name_available = (same_entity and named["status"] == "available-candidate"
                          and type(named.get("baseNameCandidate")) is str
                          and bool(named["baseNameCandidate"].strip()))
        candidate = {
            "unitKey": row["unitKey"],
            "unitIdCandidate": row["unitIdCandidate"],
            "horizontalDistanceCandidate": row["horizontalDistanceCandidate"],
            "heightDeltaCandidate": (row["positionXYZCandidate"]["y"] - point["y"]),
            "positionXYZCandidate": row["positionXYZCandidate"],
            "screenPointCandidate": row["screenPointCandidate"],
            "nameStatus": ("available-candidate" if name_available else "unavailable"),
            "nameCandidate": (named["baseNameCandidate"] if name_available else None),
            "nameUnavailableReason": (None if name_available else
                                      "entity-changed-between-reads" if not same_entity
                                      else named.get("reason") or "name-not-qualified"),
            "hostilityStatus": "unavailable",
            "levelStatus": "unavailable",
            "combatSuitabilityStatus": "unqualified"
        }
        samples.append(candidate)
    return {
        "schema": SCHEMA, "status": "nearby-unit-candidates",
        **({"host": host} if host is not None else {}),
        "process": {k: p["identity"][k] for k in (
            "processId", "processStartUtcTicks", "executablePath",
            "executableSha256")},
        "selfKey": positions["selfKey"],
        "selfPositionCandidate": point,
        "radius": radius, "nameLimit": limit,
        "unitsExamined": positions["unitsExamined"],
        "positionsFound": positions["positionsFound"],
        "totalNearbyPositionCandidates": total_nearby,
        "namedCandidateCount": sum(row["nameStatus"] == "available-candidate"
                                   for row in samples),
        "samples": samples,
        "sourceSha256": {"unitPositions": pos_sha, "unitNames": names_sha},
        "worldCoverage": "bounded-unit-manager-subset",
        "worldIdentityStatus": "unavailable", "inputSent": False,
        "qualification": ("Two sequential original-SHA pinned native reader reports "
                          "from the same physical process and self key. Name/entity "
                          "matching is a candidate only; positions may have changed "
                          "between reads. Loaded-unit scan is bounded, not world-wide. "
                          "Neither names nor screen points establish hostility, level, "
                          "floor, line-of-sight, attackability or target suitability.")
    }


def level_batch_keys(samples):
    """Prefer named rows so the NPC bind plan can use the same level batch."""
    named = [row["unitKey"] for row in samples if row["nameStatus"] == "available-candidate"]
    unnamed = [row["unitKey"] for row in samples if row["nameStatus"] != "available-candidate"]
    return (named + unnamed)[:LEVEL_BATCH_LIMIT]


def add_level_candidates(report, position_raw, name_raw, level_raw, levels, source_sha):
    """Add a checked level only for the same unit and entity as the position."""
    position, name, level = (raw["observation"] for raw in (position_raw, name_raw, level_raw))
    require(level["identity"] == position["identity"]
            and levels["selfKey"] == report["selfKey"], "position-level-owner-changed")
    stamp = physical_rift._utc_tick_order_key
    start, digit = stamp(position["startedAtUtc"])
    require(stamp(name["completedAtUtc"]) <= stamp(level["startedAtUtc"])
            <= stamp(level["completedAtUtc"]) <= (start + LEVEL_SOURCE_MAX_SPAN, digit),
            "level-source-outside-capture-window")
    samples, rows = report["samples"], levels["rows"]
    require([row["unitKey"] for row in rows] == level_batch_keys(samples),
            "level-request-sequence-mismatch")
    entities = {row["unitKey"]: row["entityAddressDecimal"] for row in position["rows"]}
    by_key = {sample["unitKey"]: sample for sample in samples}
    for row in rows:
        sample = by_key[row["unitKey"]]
        candidate, reason = row["numericLevelCandidate"], row["unavailableReason"]
        if row["entityAddressDecimal"] is not None and row["entityAddressDecimal"] != entities[sample["unitKey"]]:
            candidate, reason = None, "entity-changed-between-reads"
        sample.update(numericLevelCandidate=candidate, levelUnavailableReason=reason,
                      levelStatus="numeric-level-candidate" if candidate is not None else "unavailable")
    report["sourceSha256"]["unitLevels"] = source_sha
    report["numericLevelCandidateCount"] = sum(sample["levelStatus"] == "numeric-level-candidate"
                                               for sample in samples)
    report["qualification"] = ("Sequential original-SHA pinned native positions, names and numeric levels "
                               "from one physical process and player. Matched levels are native candidates. "
                               "Position, displayed level, hostility and combat suitability remain unqualified.")


def capture(expected_host, pid, destination, *, radius=35.0, limit=18, include_levels=False,
            choose=physical_rift.select_physical,
            read=physical_rift.read_native):
    """Acquire read-only native sources and save one joined candidate view."""
    require(physical_rift.valid_host_name(expected_host)
            and type(pid) is int and 0 < pid < 2 ** 31 and type(include_levels) is bool,
            "invalid-explicit-host-or-pid")
    require(type(radius) in (int, float) and math.isfinite(radius)
            and 0 < radius <= 50 and type(limit) is int and 1 <= limit <= 32,
            "invalid-radius-or-limit")
    destination = Path(destination)
    if not destination.is_absolute():
        destination = ROOT / destination
    require(not destination.exists() and not destination.is_symlink()
            and destination.parent.is_dir(),
            "output-must-be-new-directory")
    selected_process = choose(expected_host, pid)
    target = selected_process.get("target", {})
    host = target.get("hostName")
    require(selected_process.get("status") == "ready"
            and target.get("processId") == pid
            and physical_rift.valid_host_name(host)
            and host.casefold() == expected_host.casefold(),
            "physical-process-unavailable")
    destination.mkdir()
    try:
        pos_path = destination / "unit-positions-native.json"
        receipt = read(selected_process, "unit-positions", output=pos_path,
                       unit_limit=512)
        pos_raw, positions, pos_hash = source_from_receipt(
            receipt, pos_path, selected_process, "unit-positions")
        picked, total = choose_nearby(positions, radius=radius, limit=limit)
        if picked:
            names_path = destination / "unit-names-native.json"
            receipt_names = read(selected_process, "unit-names", output=names_path,
                                 unit_keys=[row["unitKey"] for row in picked])
            names_raw, names, name_hash = source_from_receipt(
                receipt_names, names_path, selected_process, "unit-names")
            report = combine(picked, total, pos_raw, positions, names_raw, names,
                             pos_hash, name_hash, radius=radius, limit=limit, host=host)
            if include_levels:
                require(choose(expected_host, pid).get("target") == target,
                        "process-changed-before-levels")
                level_path = destination / "unit-levels-native.json"
                receipt_levels = read(selected_process, "unit-levels", output=level_path,
                                      unit_keys=level_batch_keys(report["samples"]))
                level_raw, levels, level_hash = source_from_receipt(
                    receipt_levels, level_path, selected_process, "unit-levels")
                require(receipt_levels.get("nativeSourceSha256") is not None, "level-source-sha-missing")
                add_level_candidates(report, pos_raw, names_raw, level_raw, levels, level_hash)
        else:
            # A valid bounded scan may legitimately find zero nearby units.
            # Preserve the original source and do not fabricate a name lookup.
            report = {
                "schema": SCHEMA, "status": "no-nearby-position-candidates",
                "host": host,
                "process": {key: pos_raw["observation"]["identity"][key]
                            for key in ("processId", "processStartUtcTicks",
                                        "executablePath", "executableSha256")},
                "selfKey": positions["selfKey"],
                "selfPositionCandidate":
                    pos_raw["observation"]["selfPositionCandidate"],
                "radius": radius, "nameLimit": limit,
                "unitsExamined": positions["unitsExamined"],
                "positionsFound": positions["positionsFound"],
                "totalNearbyPositionCandidates": 0,
                "namedCandidateCount": 0, "samples": [],
                "sourceSha256": {"unitPositions": pos_hash, "unitNames": None},
                "worldCoverage": "bounded-unit-manager-subset",
                "worldIdentityStatus": "unavailable", "inputSent": False,
                "qualification": ("No nearby position candidates in one bounded "
                                  "loaded-unit-manager scan; this is not a "
                                  "world-wide absence claim or gameplay decision.")
            }
        require(choose(expected_host, pid).get("target") ==
                target, "process-changed-after-reads")
        path = destination / "nearby-report.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return path, report
    except Exception as exc:
        with (destination / "failure.json").open("x", encoding="utf-8",
                                                   newline="\n") as stream:
            json.dump({"schema": SCHEMA, "status": "unqualified",
                       "reason": str(exc)[:240],
                       "inputSent": False}, stream, indent=2)
            stream.write("\n")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-host",
                        required=True)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--radius", type=float, default=35.0)
    parser.add_argument("--max-names", type=int, default=18)
    parser.add_argument("--include-levels", action="store_true",
                        help="read up to 12 nearby numeric-level candidates, named units first")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        path, report = capture(args.expected_host, args.physical_pid,
                               args.output_dir, radius=args.radius,
                               limit=args.max_names, include_levels=args.include_levels)
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240],
                          "inputSent": False}))
        return 2
    print(json.dumps({"status": report["status"], "processId": args.physical_pid,
                      "withinRadius": report["totalNearbyPositionCandidates"],
                      "reported": len(report["samples"]),
                      "namedCandidates": report["namedCandidateCount"],
                      **({"numericLevelCandidates": report.get("numericLevelCandidateCount", 0)}
                         if args.include_levels else {}),
                      "output": str(path), "inputSent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
