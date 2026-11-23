"""Replay Telemetry target selections and optional exact-ID level evidence offline.

Reuses the independently source-hashed, host-bracketed native/Lua zone replay,
then projects the Lua publisher's observed selected-target state. A->B->A is
an observed *candidate* sequence, not proof of user input or native target API.
No process attachment, UI, input or source file mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import replay_physical_telemetry_zone as zone
from scripts.compare_physical_player_context_pair import load

UNIT = re.compile(r"u[0-9A-F]{16}\Z")
MAX_BYTES = 32_768


def require(condition, reason):
    if not condition:
        raise ValueError("telemetry-target-replay-" + reason)


def selection_state(frame, *, player):
    """Project one independently verified Lua frame, refusing ambiguous states."""
    require(type(frame) is dict and frame.get("status") == "observed"
            and frame.get("playerId") == player,
            "frame-not-observed-or-wrong-player")
    mode = frame.get("selectionState")
    target_id = frame.get("targetId")
    detail = frame.get("target")
    if mode == "none":
        require(target_id is None and detail == {}, "none-state-has-target")
        return None
    require(mode == "selected" and type(target_id) is str
            and UNIT.fullmatch(target_id) is not None
            and isinstance(detail, dict) and detail.get("id") == target_id,
            "selected-target-id-unqualified")
    require(target_id != player, "selected-player-is-not-target-proof")
    return target_id


def native_target_projection(kind, source, values):
    record = source["observation"]
    if kind == "selected-target":
        return {"nativeRead": kind, "unitKeyCandidate": values["selfUnitKey"],
                "targetStatus": values["status"], "targetUnitIdCandidate": values["unitId"],
                "targetEntity": record.get("targetEntity"), "targetLevelCandidate": values["numericLevelCandidate"],
                "startedAtUtc": record["startedAtUtc"], "completedAtUtc": record["completedAtUtc"]}
    return {"unitKeyCandidate": values["unitKey"], "targetStatus": values["target"]["status"],
            "targetUnitIdCandidate": values["target"]["unitIdCandidate"],
            "startedAtUtc": record["startedAtUtc"], "completedAtUtc": record["completedAtUtc"]}


def native_target_bracket(path, report, verified, first_lua, last_lua):
    """Source-replay optional one-shot native target endpoints without claiming atomicity."""
    exists = [key in report for key in ("nativeTargetBefore", "nativeTargetAfter")]
    require(exists[0] == exists[1], "partial-native-target-bracket")
    if not exists[0]:
        return None
    entries = []
    for suffix, key in (("before", "nativeTargetBefore"),
                        ("after", "nativeTargetAfter")):
        meta = report[key]
        require(isinstance(meta, dict)
                and Path(str(meta.get("source", ""))).name == f"native-target-{suffix}.json",
                "native-target-source-path")
        source, digest = load(path.parent / f"native-target-{suffix}.json",
                              meta.get("sha256"))
        kind = meta.get("nativeRead", "player-context")
        require(kind in ("player-context", "selected-target"), "native-target-source-kind")
        value = zone.physical_rift._native_values(kind, source)
        record = source["observation"]
        identity = record["identity"]
        native_zone, _ = load(
            path.parent / f"native-{suffix}.json",
            report["nativeBefore" if suffix == "before" else "nativeAfter"]["sha256"])
        require(identity == native_zone["observation"]["identity"],
                "native-target-process-module-mismatch")
        projection = native_target_projection(kind, source, value)
        require(projection["unitKeyCandidate"] == str(int(verified["playerUnitId"][1:], 16))
                and all(key in meta and meta[key] == field for key, field in projection.items()),
                "native-target-source-projection")
        begin, end = zone._stamp(record["startedAtUtc"]), zone._stamp(record["completedAtUtc"])
        require(begin <= end, "native-target-reversed-sampling")
        entries.append((meta, digest, begin, end))
    before, after = entries
    require(before[0].get("nativeRead") == after[0].get("nativeRead"), "native-target-source-kind-changed")
    require(zone._stamp(report["nativeBefore"]["completedAtUtc"]) < before[2]
            and before[3] < zone._stamp(report["passes"][0]["startedAtUtc"])
            and zone._stamp(report["passes"][1]["completedAtUtc"]) < after[2]
            and after[3] < zone._stamp(report["nativeAfter"]["startedAtUtc"]),
            "native-target-not-bracketed")
    lua_endpoints = (first_lua, last_lua)
    observed = []
    for (meta, digest, _, _), lua in zip(entries, lua_endpoints):
        kind, native_id = meta["targetStatus"], meta["targetUnitIdCandidate"]
        if kind in ("fallback-key-candidate", "candidate"):
            match = (type(native_id) is str and native_id == lua
                     and lua is not None)
            label = "matched-id-candidate" if match else "different-id-candidate"
        elif kind == "raw-getter-zero-candidate" and native_id is None:
            label = ("lua-none-vs-native-zero-candidate" if lua is None
                     else "different-lua-selected-vs-native-zero")
        else:
            label = "native-target-unavailable"
        endpoint = {"nativeTargetStatus": kind,
                         "nativeTargetUnitIdCandidate": native_id,
                         "luaTargetUnitIdCandidate": lua,
                         "comparison": label,
                         "sourceSha256": digest}
        if meta.get("nativeRead") == "selected-target":
            endpoint.update(nativeTargetEntity=meta["targetEntity"], nativeTargetLevelCandidate=meta["targetLevelCandidate"])
        observed.append(endpoint)
    labels = [v["comparison"] for v in observed]
    status = ("matching-endpoint-candidates"
              if all(v in ("matched-id-candidate", "lua-none-vs-native-zero-candidate")
                     for v in labels)
              else "native-endpoint-unavailable"
              if any(v == "native-target-unavailable" for v in labels)
              else "different-endpoint-candidates")
    return {"status": status, "before": observed[0], "after": observed[1],
            "qualification": (
                "Guarded native selected-target source snapshots and Lua frames share "
                "one process, but are sequential, not atomic. A native zero getter "
                "is only compatible with Lua none, not independent no-target proof; "
                "endpoint agreement is not controlled A->B->A or navigation authority."
            )}


def target_level_bracket(native_comparison, advancing):
    """Compare the exact Lua target ID and its level on advancing frames."""
    first, last = (native_comparison[key] for key in ("before", "after"))
    unit = first["nativeTargetUnitIdCandidate"]
    entity = first["nativeTargetEntity"]
    native_levels = [row["nativeTargetLevelCandidate"] for row in (first, last)]
    lua_levels = [row["targetLevelCandidate"] for row in advancing]
    result = {"nativeUnitIdCandidate": unit, "nativeLevels": native_levels,
              "luaLevels": sorted(set(lua_levels) - {None}), "advancingFrameCount": len(advancing),
              "firstAdvancingSequence": advancing[0]["sequence"], "lastAdvancingSequence": advancing[-1]["sequence"]}
    if (any(row["nativeTargetStatus"] != "candidate" for row in (first, last))
            or unit is None or last["nativeTargetUnitIdCandidate"] != unit or type(entity) is not int or entity <= 0
            or last["nativeTargetEntity"] != entity):
        status = "native-target-unavailable-or-changed"
    elif any(frame["targetUnitIdCandidate"] != unit for frame in advancing):
        status = "different-lua-and-native-target-ids"
    elif any(type(level) is not int or level <= 0 for level in native_levels + lua_levels):
        status = "target-level-candidate-unavailable"
    elif len(set(native_levels + lua_levels)) != 1:
        status = "different-exact-id-target-level-candidates"
    else:
        status = "matching-exact-id-target-level-candidates"
    return dict(result, status=status)


def replay(source, *, include_frames=False):
    """Only source-hashed existing native/Lua zone bundles are admitted."""
    require(type(include_frames) is bool, "invalid-include-frames-option")
    path = Path(source)
    verified = zone.replay(path)  # verifies hashes, player/epoch, clocks and bracket
    report, sha = load(path, verified["evidenceSummarySha256"])
    expected = verified["playerUnitId"]
    require(report["status"] == "matching-candidates" and
            verified["status"] == "matching-candidates", "unqualified-zone-source")
    frames = []
    for number, entry in enumerate(report["passes"], 1):
        for index, row in enumerate(entry["frames"], 1):
            if "sha" not in row:
                continue
            wire_path = path.parent / f"pass-{number:02d}" / f"frame-{index:02d}.wire"
            require(wire_path.is_file() and not wire_path.is_symlink(),
                    "wire-source-unavailable")
            raw = wire_path.read_bytes()
            require(len(zone.PREFIX) + len(zone.SUFFIX) < len(raw) <= MAX_BYTES
                    and zone.digest(raw) == str(row["sha"]).upper(),
                    "wire-source-sha-mismatch")
            # Revalidate the envelope, Lua zone, source schema, and source row
            # after reopening the bytes; do not trust the receipt's target ID.
            source_values = zone._frame(raw, row, expected)
            payload = zone.exact_json(raw[len(zone.PREFIX):-len(zone.SUFFIX)])
            selected = selection_state(payload, player=expected)
            level = payload["target"].get("level") if selected is not None else None
            frames.append({
                "sequence": source_values["seq"],
                "sourceEpoch": source_values["epoch"],
                "sourceClockCandidate": source_values["clock"],
                "targetUnitIdCandidate": selected,
                "targetLevelCandidate": level if type(level) is int and level > 0 else None,
                "sourceSha256": zone.digest(raw),
            })
    unique = {}
    for frame in frames:
        seq = frame["sequence"]
        if seq in unique:
            require(frame == unique[seq], "conflicting-repeated-sequence")
        else:
            unique[seq] = frame
    ordered = [unique[s] for s in sorted(unique)]
    require(len(ordered) == verified["uniqueSourceSequences"]
            and ordered[0]["sequence"] == verified["firstSourceSequence"]
            and ordered[-1]["sequence"] == verified["lastSourceSequence"],
            "source-sequence-correlation")
    require(all(a["sourceClockCandidate"] < b["sourceClockCandidate"]
                for a, b in zip(ordered, ordered[1:])),
            "source-clock-not-monotonic")

    runs = []
    previous = object()
    for frame in ordered:
        key = frame["targetUnitIdCandidate"]
        if key != previous:
            runs.append({"targetUnitIdCandidate": key,
                         "firstSequence": frame["sequence"],
                         "lastSequence": frame["sequence"]})
        else:
            runs[-1]["lastSequence"] = frame["sequence"]
        previous = key
    transitions = [
        {"fromTargetUnitIdCandidate": a["targetUnitIdCandidate"],
         "toTargetUnitIdCandidate": b["targetUnitIdCandidate"],
         "fromLastSequence": a["lastSequence"],
         "toFirstSequence": b["firstSequence"]}
        for a, b in zip(runs, runs[1:])
    ]
    cycles = [
        {"firstTargetUnitIdCandidate": a["targetUnitIdCandidate"],
         "otherTargetUnitIdCandidate": b["targetUnitIdCandidate"],
         "firstSequence": a["firstSequence"],
         "otherSequence": b["firstSequence"],
         "returnedSequence": c["firstSequence"]}
        for a, b, c in zip(runs, runs[1:], runs[2:])
        if a["targetUnitIdCandidate"] is not None
        and b["targetUnitIdCandidate"] is not None
        and a["targetUnitIdCandidate"] != b["targetUnitIdCandidate"]
        and a["targetUnitIdCandidate"] == c["targetUnitIdCandidate"]
    ]
    all_none = all(f["targetUnitIdCandidate"] is None for f in ordered)
    state = ("no-target-baseline-candidate" if all_none
             else "a-b-a-target-candidate" if cycles
             else "selected-target-observations-candidate")
    native_comparison = native_target_bracket(
        path, report, verified, ordered[0]["targetUnitIdCandidate"],
        ordered[-1]["targetUnitIdCandidate"])
    level_comparison = None
    if native_comparison is not None and "nativeTargetLevelCandidate" in native_comparison["before"]:
        first_pass_latest = max(row["seq"] for row in report["passes"][0]["frames"] if "sha" in row)
        advancing = [frame for frame in ordered if frame["sequence"] > first_pass_latest]
        require(advancing, "target-level-advancing-frames-unavailable")
        level_comparison = target_level_bracket(native_comparison, advancing)
    return {
        "schemaVersion": 1,
        "evidenceKind": "physical-telemetry-target-sequence-offline/1",
        "status": state,
        "qualificationStatus": "candidate-only",
        "hostName": verified["hostName"], "processId": verified["processId"],
        "processStartUtcTicks": verified["processStartUtcTicks"],
        "executableSha256": verified["executableSha256"],
        "playerUnitId": expected,
        "zoneIdCandidate": verified["zoneIdCandidate"],
        "zoneLuaNameCandidate": verified["luaZoneNameCandidate"],
        "sourceEpoch": verified["sourceEpoch"],
        "sourceSessionId": verified["sourceSessionId"],
        "observedFrameCount": len(ordered),
        "recordedFrameOccurrences": len(frames),
        "firstSequence": ordered[0]["sequence"],
        "lastSequence": ordered[-1]["sequence"],
        "noTargetFrameCount": sum(f["targetUnitIdCandidate"] is None for f in ordered),
        "selectedTargetFrameCount": sum(f["targetUnitIdCandidate"] is not None for f in ordered),
        "runs": runs,
        "transitions": transitions,
        "aBaCycles": cycles,
        **({"observedTargetFrames": ordered} if include_frames else {}),
        "evidenceSummarySha256": sha,
        "nativeSourceSha256": verified["nativeSourceSha256"],
        **({"nativeTargetComparison": native_comparison}
           if native_comparison is not None else {}),
        **({"targetLevelComparison": level_comparison} if level_comparison is not None else {}),
        "inputSent": False,
        "worldInstanceStatus": "unavailable",
        "qualification": (
            "Source-hashed, same-process, independent Lua publisher selection candidates "
            "from a successful native/Lua zone bracket. "
            + ("Native selected-target endpoints are also source-replayed but "
               "remain sequential candidate comparisons. " if native_comparison else
               "No native selected-target correlation. ")
            + "No controlled input A->B->A proof, action causation, atomic "
              "freshness, world instance, or navigation authority."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True,
                        help="Saved native/Lua zone bracket summary (not a live process)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            require(not args.output.exists() and not args.output.is_symlink()
                    and args.output.parent.is_dir(), "output-exists-or-parent-unavailable")
        result = replay(args.summary)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8", newline="\n") as out:
                json.dump(result, out, indent=2, allow_nan=False)
                out.write("\n")
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({
        "status": result["status"],
        "qualificationStatus": result["qualificationStatus"],
        "processId": result["processId"],
        "playerUnitId": result["playerUnitId"],
        "zoneIdCandidate": result["zoneIdCandidate"],
        "observedFrameCount": result["observedFrameCount"],
        "noTargetFrameCount": result["noTargetFrameCount"],
        "selectedTargetFrameCount": result["selectedTargetFrameCount"],
        "transitions": result["transitions"],
        "aBaCycles": result["aBaCycles"],
        "nativeTargetComparison": result.get("nativeTargetComparison"),
        **({"targetLevelComparison": result["targetLevelComparison"]} if "targetLevelComparison" in result else {}),
        "output": str(args.output) if args.output else None,
    }, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
