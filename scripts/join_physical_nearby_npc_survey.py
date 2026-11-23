"""Join source-replayed NPC Lua detail to exact native nearby unit candidates.

Read-only saved-file processing. Exact ID, process, time, name and world XYZ
correlation is a research candidate, never combat authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_nearby_units as nearby
from scripts import physical_rift
from scripts import replay_npc_survey


def require(ok, reason):
    if not ok:
        raise ValueError("nearby-npc-join-" + reason)


def _strict_file(path, max_bytes):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "source-unavailable")
    raw = path.read_bytes()
    require(0 < len(raw) <= max_bytes, "source-size")
    doc = physical_rift._strict_native_json(raw.decode("utf-8-sig"))
    require(type(doc) is dict, "source-not-object")
    return doc, hashlib.sha256(raw).hexdigest().upper()


def original_native_nearby(source):
    """Re-derive nearby candidates from the original native reports."""
    path = Path(source)
    saved, digest = _strict_file(path, 1_000_000)
    require(saved.get("schema") == nearby.SCHEMA
            and saved.get("status") in (
                "nearby-unit-candidates", "no-nearby-position-candidates")
            and saved.get("inputSent") is False, "nearby-summary-invalid")
    host = saved.get("host")
    require("host" not in saved or physical_rift.valid_host_name(host), "nearby-host-invalid")
    pos_path = path.parent / "unit-positions-native.json"
    position_doc, pos_sha = _strict_file(pos_path, 16 * 1024 * 1024)
    source_shas = saved.get("sourceSha256")
    require(type(source_shas) is dict
            and source_shas.get("unitPositions") == pos_sha,
            "position-source-sha-mismatch")
    positions = physical_rift._native_values("unit-positions", position_doc)
    picked, total = nearby.choose_nearby(
        positions, radius=saved.get("radius"), limit=saved.get("nameLimit"))
    if picked:
        names_doc, name_sha = _strict_file(
            path.parent / "unit-names-native.json", 16 * 1024 * 1024)
        require(source_shas.get("unitNames") == name_sha,
                "name-source-sha-mismatch")
        names = physical_rift._native_values("unit-names", names_doc)
        rebuilt = nearby.combine(
            picked, total, position_doc, positions, names_doc, names,
            pos_sha, name_sha, radius=saved["radius"], limit=saved["nameLimit"], host=host)
        last_native = names_doc["observation"]["completedAtUtc"]
        if "unitLevels" in source_shas:
            levels_doc, level_sha = _strict_file(path.parent / "unit-levels-native.json", 16 * 1024 * 1024)
            require(source_shas["unitLevels"] == level_sha, "level-source-sha-mismatch")
            levels = physical_rift._native_values("unit-levels", levels_doc)
            nearby.add_level_candidates(rebuilt, position_doc, names_doc, levels_doc, levels, level_sha)
            last_native = levels_doc["observation"]["completedAtUtc"]
    else:
        require(saved.get("status") == "no-nearby-position-candidates"
                and saved.get("samples") == []
                and saved.get("namedCandidateCount") == 0
                and saved.get("totalNearbyPositionCandidates") == 0
                and "numericLevelCandidateCount" not in saved
                and "unitLevels" not in source_shas
                and source_shas.get("unitNames") is None,
                "empty-nearby-summary-mismatch")
        rebuilt = saved
        last_native = position_doc["observation"]["completedAtUtc"]
    require(saved == rebuilt, "nearby-source-projection-mismatch")
    return saved, digest, (position_doc["observation"]["startedAtUtc"], last_native)


def _seconds(before, after):
    left, a = physical_rift._utc_tick_order_key(before)
    right, b = physical_rift._utc_tick_order_key(after)
    return (right - left).total_seconds() + (b - a) / 10_000_000


def correlate(nearby_report, survey, *, max_gap_seconds=30.0,
              position_tolerance=5.0):
    """Conservative per-unit candidate join. Missing critical fields stay unknown."""
    require(type(max_gap_seconds) in (float, int)
            and not isinstance(max_gap_seconds, bool)
            and math.isfinite(max_gap_seconds)
            and 0 <= max_gap_seconds <= 120
            and type(position_tolerance) in (float, int)
            and not isinstance(position_tolerance, bool)
            and math.isfinite(position_tolerance)
            and 0 < position_tolerance <= 20,
            "invalid-comparison-bounds")
    native, native_sha, (native_started, native_completed) = original_native_nearby(nearby_report)
    api = replay_npc_survey.replay(survey)
    owner, api_owner = native["process"], api["process"]
    native_host = native.get("host")
    require((native_host is None and "hostName" not in api_owner)
            or (native_host is not None and native_host.casefold() == api["host"].casefold()),
            "native-api-host-missing-or-mismatch")
    require(owner["processId"] == api_owner.get("processId")
            and str(owner["processStartUtcTicks"]) ==
                str(api_owner.get("processStartUtcTicks"))
            and owner["executableSha256"].casefold() ==
                str(api_owner.get("executableSha256", "")).casefold()
            and api["playerId"] == f"u{int(native['selfKey']):016X}",
            "native-api-owner-or-player-mismatch")
    gap = _seconds(native_completed, api["sampledAtUtc"])
    source_span = _seconds(native_started, api["sampledAtUtc"])
    require(0 <= gap <= source_span <= max_gap_seconds, "native-api-source-gap")
    approved = set(api["confirmedUnitIds"])
    source_rows = api["snapshot"]["units"]
    rows = []
    for row in native["samples"]:
        unit_id = row["unitIdCandidate"]
        detail = source_rows.get(unit_id)
        confirmed = unit_id in approved and type(detail) is dict and detail.get("status") == "observed"
        apiname = detail.get("name") if confirmed else None
        native_name = row["nameCandidate"] if row["nameStatus"] == "available-candidate" else None
        name_match = (type(apiname) is str and native_name is not None
                      and apiname.casefold() == native_name.casefold())
        axes = ("coordX", "coordY", "coordZ")
        xyz = row["positionXYZCandidate"]
        coordinate_values = ([detail.get(axis) for axis in axes] if confirmed else [])
        complete_xyz = (len(coordinate_values) == 3
                        and all(type(value) in (float, int) and math.isfinite(value)
                                for value in coordinate_values))
        planar = (math.hypot(xyz["x"] - coordinate_values[0],
                              xyz["z"] - coordinate_values[2])
                  if complete_xyz else None)
        height = (abs(xyz["y"] - coordinate_values[1])
                  if complete_xyz else None)
        coordinate_match = (complete_xyz and planar <= position_tolerance
                            and height <= position_tolerance)
        corroborated = confirmed and name_match and coordinate_match
        candidate_level = detail.get("level") if corroborated else None
        valid_level = (type(candidate_level) is int
                       and 1 <= candidate_level <= 1000)
        candidate_relation = detail.get("relation") if corroborated else None
        native_level = row.get("numericLevelCandidate")
        rows.append({
            "unitIdCandidate": unit_id,
            "nativeNameCandidate": native_name,
            "nativeHorizontalDistanceCandidate": row["horizontalDistanceCandidate"],
            "nativeHeightDeltaCandidate": row["heightDeltaCandidate"],
            "apiIdConfirmedInTwoFrames": bool(confirmed),
            "apiNameCandidate": apiname,
            "nameAgreement": ("matches" if name_match else
                              "unavailable" if apiname is None or native_name is None
                              else "conflict"),
            "horizontalPositionDeltaCandidate": planar,
            "verticalPositionDeltaCandidate": height,
            "positionAgreement": ("within-tolerance" if coordinate_match
                                  else "outside-tolerance" if complete_xyz else "unavailable"),
            "apiLevelCandidate": candidate_level if valid_level else None,
            **({"nativeNumericLevelCandidate": native_level,
                "levelAgreement": ("unavailable" if native_level is None or not valid_level
                                   else "matching-candidates" if native_level == candidate_level
                                   else "different-candidates")}
               if "numericLevelCandidate" in row else {}),
            "apiRelationCandidate": candidate_relation
                if type(candidate_relation) is str else None,
            "apiPlayerFlagCandidate": (detail.get("player")
                                       if corroborated and type(detail.get("player")) is bool
                                       else None),
            "correlationStatus": ("cross-source-candidate" if corroborated
                                  else "not-qualified"),
            "combatSuitabilityStatus": "unqualified",
            "castAuthorized": False,
            "moveAuthorized": False
        })
    return {
        "schema": "rr2-nearby-npc-cross-source/1",
        "status": "joined-candidates",
        "nativeReportSha256": native_sha,
        "npcSurveySummarySha256": api["summarySha256"],
        "process": owner,
        "host": api["host"],
        "playerId": api["playerId"],
        "sourceGapSeconds": gap,
        "maximumSourceAgeSeconds": source_span,
        "maximumSourceGapSeconds": max_gap_seconds,
        "maximumPositionDeviation": position_tolerance,
        "nativeNearbyCount": len(rows),
        "apiConfirmedIdCount": len(approved),
        "crossSourceCandidateCount": sum(r["correlationStatus"] ==
                                         "cross-source-candidate" for r in rows),
        "samples": rows,
        "worldInstanceStatus": "unavailable",
        "combatAuthorized": False, "moveAuthorized": False, "inputSent": False,
        "qualification": ("Two original SHA-reverified native reports and two or "
                          "more source-hash-replayed nonce/player-bound Lua NPC frames "
                          "were compared by exact unit ID, owner, relative host "
                          "capture time, displayed name and XYZ. No API producer "
                          "authentication, atomicity, live refresh guarantee, "
                          "zone-instance proof, hostility semantics, LOS, target "
                          "selection response or combat suitability was established.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--nearby", type=Path, required=True)
    parser.add_argument("--npc-survey", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-gap-seconds", type=float, default=30.0)
    parser.add_argument("--position-tolerance", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink()
                and args.output.parent.is_dir(), "new-output-file-required")
        result = correlate(
            args.nearby, args.npc_survey,
            max_gap_seconds=args.max_gap_seconds,
            position_tolerance=args.position_tolerance)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (ValueError, TypeError, KeyError, OSError,
            UnicodeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}))
        return 2
    print(json.dumps({
        "status": result["status"],
        "nativeNearbyCount": result["nativeNearbyCount"],
        "crossSourceCandidateCount": result["crossSourceCandidateCount"],
        "combatAuthorized": False, "inputSent": False,
        "output": str(args.output)
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
