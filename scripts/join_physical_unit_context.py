"""Join two retained physical native unit scans without reading or controlling RIFT.

This pairs a bounded position scan with a later cache-only name scan under the
same verified PID/start/build/self identity. It is deliberately candidate-only:
neither a base name nor proximity establishes hostility, creature level, safety,
or current live freshness.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_physical_player_context_pair as context
from scripts import physical_rift


def _require(condition, reason):
    if not condition:
        raise ValueError("physical-unit-context-" + reason)


def _gap_seconds(earlier, later):
    left, a = physical_rift._utc_tick_order_key(earlier)
    right, b = physical_rift._utc_tick_order_key(later)
    return (right - left).total_seconds() + (b - a) / 10_000_000


def join(position_file, names_file, *, max_gap_seconds=30.0):
    _require(type(max_gap_seconds) in (int, float)
             and math.isfinite(max_gap_seconds) and 0 <= max_gap_seconds <= 120,
             "invalid-gap-limit")
    positions, pos_sha = context.load(Path(position_file))
    names, name_sha = context.load(Path(names_file))
    _require(pos_sha != name_sha, "same-source")
    position_values = physical_rift._native_values("unit-positions", positions)
    name_values = physical_rift._native_values("unit-names", names)
    pose, naming = positions["observation"], names["observation"]
    owner = pose.get("identity")
    # These native source files do not embed a host name. Independently guard
    # the analysis host; pin their process/module identity without pretending
    # the raw reports independently attest which PC produced them.
    _require(socket.gethostname().upper() == "AMD-DESKTOP", "wrong-analysis-host")
    _require(isinstance(owner, dict) and owner == naming.get("identity")
             and type(owner.get("processId")) is int and owner["processId"] > 0
             and type(owner.get("processStartUtcTicks")) is int
             and owner["processStartUtcTicks"] > 0
             and isinstance(owner.get("executableSha256"), str)
             and len(owner["executableSha256"]) == 64,
             "owner-or-epoch-mismatch")
    _require(position_values["selfKey"] == name_values["selfKey"],
             "self-key-mismatch")
    gap = _gap_seconds(pose["completedAtUtc"], naming["startedAtUtc"])
    _require(0 <= gap <= max_gap_seconds, "captures-overlap-or-too-far-apart")

    # The strict existing native projections validate every row and raw position.
    # Retain the raw entity reference to avoid joining reused unit IDs to a name
    # from a different entity; a name cache miss remains explicitly unavailable.
    by_key = {}
    for row in pose["rows"]:
        key = row["unitKey"]
        _require(key not in by_key, "duplicate-position-owner")
        by_key[key] = row["entityAddressDecimal"]
    named = {}
    for row in name_values["rows"]:
        key = row["unitKey"]
        _require(key in by_key and key not in named,
                 "name-key-outside-position-capture")
        named[key] = row

    units = []
    for position in position_values["units"]:
        key = position["unitKey"]
        name = named.get(key)
        if name is None:
            name_status, reason, label = "unavailable", "not-requested", None
        elif name["entityAddressDecimal"] != by_key[key]:
            name_status, reason, label = "unavailable", "entity-owner-changed", None
        else:
            name_status, reason, label = (name["status"], name["reason"],
                                          name["baseNameCandidate"])
        units.append({
            "unitKey": key, "unitIdCandidate": position["unitIdCandidate"],
            "horizontalDistanceCandidate": position["horizontalDistanceCandidate"],
            "positionXYZCandidate": position["positionXYZCandidate"],
            "screenPointCandidate": position["screenPointCandidate"],
            "nameStatus": name_status, "nameReason": reason,
            "baseNameCandidate": label, "hostility": "unknown",
            "level": None, "eliteOrGroupStatus": "unknown",
        })
    return {
        "schemaVersion": 1, "evidenceKind": "physical-unit-context-candidates/1",
        "status": "candidate-only", "analysisHost": "AMD-DESKTOP",
        "sourceHostProvenance": "not-embedded-in-raw-native-reports",
        "target": owner, "selfKeyCandidate": position_values["selfKey"],
        "sources": {"positionsSha256": pos_sha, "namesSha256": name_sha},
        "nameReadGapSeconds": gap, "maxGapSeconds": max_gap_seconds,
        "unitScan": {"examined": position_values["unitsExamined"],
                     "positionsFound": position_values["positionsFound"],
                     "limitReached": position_values["unitLimitReached"],
                     "worldCoverage": position_values["worldCoverage"]},
        "namedCandidateCount": sum(row["nameStatus"] == "available-candidate" for row in units),
        "units": units,
        "encounter": {"ready": False, "reason": "hostility-level-ability-and-freshness-unqualified"},
        "qualification": "Pinned offline native candidate join; not atomic, hostility/level qualified, "
                         "live fresh, action-associated or restart-qualified.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True, help="Existing native unit-positions JSON")
    parser.add_argument("--names", type=Path, required=True, help="Later native unit-names JSON")
    parser.add_argument("--max-gap-seconds", type=float, default=30.0,
                        help="Maximum end-of-positions to start-of-names gap (default 30)")
    args = parser.parse_args(argv)
    try:
        result = join(args.positions, args.names, max_gap_seconds=args.max_gap_seconds)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
