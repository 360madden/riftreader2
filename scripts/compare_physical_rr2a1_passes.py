"""Replay two independently acquired physical RR2A1 passes against native brackets.

Every pass is re-decoded from SHA-checked scan requests, pages, and source-verified
native self->XYZ->self reports. The RR2A1 producer is UNBOUND: an advancing
sequence is useful candidate evidence, not nonce/session freshness proof.
No process access, VM operation, input or window focus.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import replay_physical_rr2a1 as lua
from scripts import compare_physical_player_brackets as native
from scripts import compare_physical_player_context_pair as context
from scripts.physical_rift import _utc_tick_order_key

# Empirical stationary XYZ screening threshold, NOT a live semantic qualification.
MAX_COORDINATE_GAP_CANDIDATE = 0.05


def require(ok, reason):
    if not ok:
        raise ValueError("physical-rr2a1-pair-" + reason)


def native_lua_capture_chronology(first_index, second_index, first, second,
                                  earlier, later):
    """Screen whether source-pinned native/Lua observations can share a time window.

    Native captures entirely before (or after) both host scans cannot establish
    simultaneous acquisition. Lua frames may have been produced before scanning;
    source-receipt order neither proves nor disproves producer-time alignment.
    """
    scans = []
    for path, replay in ((first_index, first), (second_index, second)):
        raw, digest = context.load(path)
        require(digest.upper() == replay["sourceSha256"]["scanIndex"].upper(),
                "scan-receipt-hash-mismatch")
        require(all(isinstance(raw.get(key), str) and raw[key]
                    for key in ("startedAtUtc", "completedAtUtc")),
                "missing-scan-capture-times")
        scans.append((raw["startedAtUtc"], raw["completedAtUtc"]))
    native_windows = [(earlier["firstStartedAtUtc"], earlier["lastCompletedAtUtc"]),
                      (later["firstStartedAtUtc"], later["lastCompletedAtUtc"])]
    try:
        scan_ticks = [(_utc_tick_order_key(start), _utc_tick_order_key(end))
                      for start, end in scans]
        native_ticks = [(_utc_tick_order_key(start), _utc_tick_order_key(end))
                        for start, end in native_windows]
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("physical-rr2a1-pair-invalid-state-or-scan-times") from exc
    require(all(start <= end for start, end in scan_ticks + native_ticks),
            "reversed-state-or-scan-window")
    if native_ticks[-1][1] < scan_ticks[0][0]:
        status = "native-before-both-scan-receipts"
    elif scan_ticks[-1][1] < native_ticks[0][0]:
        status = "native-after-both-scan-receipts"
    elif scan_ticks[0][1] >= scan_ticks[1][0]:
        status = "overlapping-scan-receipts"
    else:
        status = "interleaved-host-receipts-candidate"
    return {"status": status, "nativeWindowsUtc": native_windows,
            "luaScanWindowsUtc": scans,
            "luaScanIndexSha256": [first["sourceSha256"]["scanIndex"],
                                   second["sourceSha256"]["scanIndex"]],
            "qualification": ("Source-replayed host scan/native acquisition order only. "
                              "Lua production could predate a host scan; disjoint host "
                              "receipts neither prove nor disprove frame-time alignment, "
                              "atomicity or damage causality.")}


def compare(first_index, second_index, first_native_bracket, second_native_bracket=None,
            *, first_native_state=None, second_native_state=None):
    """Recheck raw sources rather than trust previously generated replay summaries."""
    require((first_native_state is None) == (second_native_state is None),
            "both-native-states-required")
    second_native_bracket = (first_native_bracket if second_native_bracket is None
                             else second_native_bracket)
    first = lua.replay(first_index, first_native_bracket)
    second = lua.replay(second_index, second_native_bracket)
    require(first["status"] == second["status"] == "candidate-only"
            and first["luaProtocol"] == second["luaProtocol"] == "RR2A1-unbound",
            "unsupported-protocol")
    require(first["identity"] == second["identity"]
            and first["luaPlayerIdCandidate"] == second["luaPlayerIdCandidate"],
            "process-or-player-identity-changed")
    require(type(first["luaEpochCandidate"]) is int
            and first["luaEpochCandidate"] > 0
            and first["luaEpochCandidate"] == second["luaEpochCandidate"],
            "lua-epoch-changed")
    require(first["sourceSha256"]["scanIndex"] != second["sourceSha256"]["scanIndex"],
            "same-scan-source")
    require(first["lastSequence"] < second["lastSequence"]
            and first["lastClockCandidate"] < second["lastClockCandidate"],
            "nonadvancing-or-overlapping-passes")
    # A focused re-scan can copy still-retained old Lua frames alongside newer
    # frames. Exclude the overlapping prefix, but require two independently
    # advancing frames after the entire first pass, not just a new scan index.
    frames = second["frameEvidence"]
    require(len(frames) == second["luaFrameCount"] ==
            len(second["luaPositionCandidates"]) and frames
            and frames[0]["sequence"] == second["firstSequence"]
            and frames[-1]["sequence"] == second["lastSequence"]
            and frames[0]["clockCandidate"] == second["firstClockCandidate"]
            and frames[-1]["clockCandidate"] == second["lastClockCandidate"],
            "nonadvancing-or-overlapping-passes")
    overlap = sum(f["sequence"] <= first["lastSequence"] for f in frames)
    fresh = frames[overlap:]
    require(len(fresh) >= 2, "insufficient-new-frames")
    require(all(type(f["sequence"]) is int and
                f["sequence"] > first["lastSequence"] and
                type(f["clockCandidate"]) in (int, float) and
                math.isfinite(f["clockCandidate"]) and
                f["clockCandidate"] > first["lastClockCandidate"]
                for f in fresh), "nonadvancing-or-overlapping-passes")
    require(not ({f["frameSha256"] for f in first["frameEvidence"]} &
                 {f["frameSha256"] for f in fresh}), "reused-frame")
    require(first["luaFrameCount"] >= 2, "insufficient-independent-frames")
    first_health = first.get("luaHealthCandidates")
    second_health = second.get("luaHealthCandidates")
    require(isinstance(first_health, list) and isinstance(second_health, list)
            and len(first_health) == first["luaFrameCount"]
            and len(second_health) == second["luaFrameCount"]
            and all(isinstance(row, dict) and row.get("sequence") == evidence["sequence"]
                    for rows, evidence_rows in ((first_health, first["frameEvidence"]),
                                                (second_health, second["frameEvidence"]))
                    for row, evidence in zip(rows, evidence_rows)),
            "health-frame-sequence-mismatch")
    # Recovered old frames are safe to discard only when matching a previously
    # observed sequence retains the same source bytes, clock and HP projection.
    # A counter reused by another unbound producer is not proof of continuity.
    retained_by_sequence = {
        frame["sequence"]: (frame, first_health[i])
        for i, frame in enumerate(first["frameEvidence"])
    }
    for i in range(overlap):
        old = retained_by_sequence.get(frames[i]["sequence"])
        if old is None:
            continue
        prior_frame, prior_health = old
        require(frames[i]["frameSha256"] == prior_frame["frameSha256"]
                and frames[i]["clockCandidate"] == prior_frame["clockCandidate"],
                "overlap-frame-conflict")
        require(second_health[i]["health"] == prior_health["health"],
                "overlap-health-conflict")
    health_trend = lua.lua_health_trend(first_health + second_health[overlap:])

    first_end = first["luaPositionCandidates"][-1]
    second_start = second["luaPositionCandidates"][overlap]
    lua_delta = {axis: second_start[axis] - first_end[axis]
                 for axis in ("x", "y", "z")}
    native_first, native_second = (first["nativePositionCandidate"],
                                    second["nativePositionCandidate"])
    native_delta = {axis: native_second[axis] - native_first[axis]
                    for axis in ("x", "y", "z")}
    require(all(type(p[axis]) in (int, float) and math.isfinite(p[axis])
                and p[axis] >= 0
                for p in (first["maxAbsCoordinateDifferenceCandidate"],
                          second["maxAbsCoordinateDifferenceCandidate"])
                for axis in ("x", "y", "z")), "invalid-coordinate-gap")
    across_max = {axis: max(first["maxAbsCoordinateDifferenceCandidate"][axis],
                            second["maxAbsCoordinateDifferenceCandidate"][axis])
                  for axis in ("x", "y", "z")}
    require(all(math.isfinite(v) for group in (lua_delta, native_delta, across_max)
                for v in group.values()), "nonfinite-comparison")
    result = {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2a1-two-pass-native-comparison/1",
        "status": "candidate-only",
        "identity": first["identity"],
        "luaProtocol": "RR2A1-unbound",
        "luaPlayerIdCandidate": first["luaPlayerIdCandidate"],
        "luaEpochCandidate": first["luaEpochCandidate"],
        "frameCounts": [first["luaFrameCount"], len(fresh)],
        "rawFrameCounts": [first["luaFrameCount"], second["luaFrameCount"]],
        "discardedOverlapFrames": overlap,
        "luaHealthTrendCandidate": health_trend,
        "sequenceWindows": [[first["firstSequence"], first["lastSequence"]],
                            [fresh[0]["sequence"], fresh[-1]["sequence"]]],
        "rawSequenceWindows": [[first["firstSequence"], first["lastSequence"]],
                               [second["firstSequence"], second["lastSequence"]]],
        "clockWindows": [[first["firstClockCandidate"], first["lastClockCandidate"]],
                         [fresh[0]["clockCandidate"], fresh[-1]["clockCandidate"]]],
        # Preserve usable absolute source values alongside the deltas, without
        # promoting unbound RR2A1 to authenticated or current live telemetry.
        "positionCandidates": {
            "firstLua": first["luaPositionCandidates"][0],
            "lastLua": second["luaPositionCandidates"][-1],
            "nativeBefore": native_first,
            "nativeAfter": native_second,
        },
        "betweenPassLuaXYZDifferenceCandidate": lua_delta,
        "betweenPassNativeXYZDifferenceCandidate": native_delta,
        "maxAbsLuaNativeCoordinateDifferenceCandidate": across_max,
        "sourceSha256": {
            "first": first["sourceSha256"],
            "second": second["sourceSha256"],
        },
        "qualification": ("Two independently source-verified RR2A1 Lua baseline passes "
                          "contain at least two new frames with increasing sequence and "
                          "clock after discarding any retained overlap in one candidate "
                          "Lua epoch, matching native player ID and XYZ candidates. "
                          "RR2A1 remains unbound; no nonce, producer authenticity, "
                          "atomic freshness, changed-state causation or restart proof."),
    }


    agreement = all(gap <= MAX_COORDINATE_GAP_CANDIDATE
                    for gap in across_max.values())
    result["coordinateAgreementScreen"] = {
        "result": "consistent" if agreement else "disagreement",
        "withinTolerance": agreement,
        "maximumAxisGapNativeUnits": MAX_COORDINATE_GAP_CANDIDATE,
    }
    if not agreement:
        result["status"] = "candidate-disagreement"
        result["qualification"] = (
            "Two source-verified RR2A1 Lua passes advance with the same player ID, "
            "but close Lua/native XYZ correspondence is not demonstrated at the "
            "0.05-unit empirical screening tolerance. Captures are not time-atomic; "
            "the disagreement may reflect time separation or stale candidate data. "
            "Producer freshness, movement semantics and restart recovery are unqualified.")
    if first_native_state is not None:
        # These are independently acquired, ordered native *state* captures.
        # Do not misrepresent them as time-atomic with the Lua scan windows.
        earlier = lua.native_state.verified_state(first_native_state)
        later = lua.native_state.verified_state(second_native_state)
        state_pair = lua.native_state._compare_states(earlier, later)
        first_screen = lua.compare_native_health(first, earlier)
        second_screen = lua.compare_native_health(second, later)
        native_before = first_screen["nativeHealthCandidate"]
        native_after = second_screen["nativeHealthCandidate"]
        native_delta = (state_pair["healthDeltaCandidate"]
                        if native_before is not None and native_after is not None
                        and native_before["maximum"] == native_after["maximum"]
                        else None)
        first_lua_health = first_health[0]["health"]
        last_lua_health = second_health[-1]["health"]
        lua_delta = (last_lua_health["current"] - first_lua_health["current"]
                     if first_lua_health is not None and last_lua_health is not None
                     and first_lua_health["maximum"] == last_lua_health["maximum"]
                     else None)
        if native_delta is None or lua_delta is None:
            direction = "unavailable"
        elif native_delta == lua_delta == 0:
            direction = "both-unchanged-candidate"
        elif (native_delta > 0 and lua_delta > 0 or
              native_delta < 0 and lua_delta < 0):
            direction = "same-direction-candidate"
        else:
            direction = "different-direction-candidate"
        chronology = native_lua_capture_chronology(
            first_index, second_index, first, second, earlier, later)
        raw_direction = direction
        if (direction != "unavailable" and
                chronology["status"] != "interleaved-host-receipts-candidate"):
            direction = "not-co-timed-host-receipts"
        result["independentNativeHealthTrendCandidate"] = {
            "status": "candidate-only",
            "firstNativeLuaAgreement": first_screen,
            "secondNativeLuaAgreement": second_screen,
            "nativeDeltaCurrentCandidate": native_delta,
            "luaEndpointDeltaCurrentCandidate": lua_delta,
            "directionScreen": direction,
            "rawDirectionScreen": raw_direction,
            "captureChronology": chronology,
            "nativeSourceSha256": [earlier["summarySha256"], later["summarySha256"]],
            "nativeCaptureWindowsUtc": [
                [earlier["firstStartedAtUtc"], earlier["lastCompletedAtUtc"]],
                [later["firstStartedAtUtc"], later["lastCompletedAtUtc"]]],
            "qualification": (
                "Independently SHA-replayed, ordered same-process native health "
                "candidate states versus advancing unbound Lua HP endpoints; "
                "host acquisition windows are not time-locked, and disjoint scan "
                "receipts suppress the displayed direction. Lua production times "
                "remain unknown even for interleaved receipts: no live health "
                "semantics, damage cause or RR2R1 freshness is established."),
        }
    return result


def verify_capture_order(first_index, second_index, first_native_bracket,
                         second_native_bracket):
    """Require bracket → scan → scan → bracket from original UTC receipts.

    Call after compare() has replayed and verified all source hashes. This is
    intentionally opt-in: older independent scans need not be bracketed.
    """
    _, _, _, before_end = native.verified_bracket(first_native_bracket)
    _, _, after_start, _ = native.verified_bracket(second_native_bracket)
    first, _ = context.load(first_index)
    second, _ = context.load(second_index)
    names = ("nativeBeforeCompleted", "firstScanStarted", "firstScanCompleted",
             "secondScanStarted", "secondScanCompleted", "nativeAfterStarted")
    times = (before_end, first.get("startedAtUtc"), first.get("completedAtUtc"),
             second.get("startedAtUtc"), second.get("completedAtUtc"), after_start)
    require(all(isinstance(t, str) and t for t in times),
            "missing-capture-timestamps")
    try:
        ticks = [_utc_tick_order_key(t) for t in times]
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("physical-rr2a1-pair-invalid-capture-timestamps") from exc
    require(all(a < b for a, b in zip(ticks, ticks[1:])),
            "overlapping-or-reordered-capture")
    return {"status": "source-verified-order", "observedUtc": dict(zip(names, times)),
            "qualification": "Strict sequential source receipts only; not atomic Lua/native freshness"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-index", type=Path, required=True)
    parser.add_argument("--second-index", type=Path, required=True)
    parser.add_argument("--first-native-bracket", type=Path, required=True)
    parser.add_argument("--second-native-bracket", type=Path)
    parser.add_argument("--first-native-state", type=Path,
                        help="Optional first SHA-pinned native player-state summary; requires the second")
    parser.add_argument("--second-native-state", type=Path,
                        help="Optional second ordered same-process native player-state summary")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-bracketed-order", action="store_true",
                        help="Verify original native→scan→scan→native UTC order")
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(),
                "output-exists")
        result = compare(args.first_index, args.second_index,
                         args.first_native_bracket, args.second_native_bracket,
                         first_native_state=args.first_native_state,
                         second_native_state=args.second_native_state)
        if args.require_bracketed_order:
            require(args.second_native_bracket is not None,
                    "second-native-bracket-required")
            result["captureOrder"] = verify_capture_order(
                args.first_index, args.second_index,
                args.first_native_bracket, args.second_native_bracket)
        with args.output.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
        print(json.dumps({"status": result["status"],
                          "frameCounts": result["frameCounts"],
                          "sequenceWindows": result["sequenceWindows"],
                          "maxAbsXYZDifference":
                          result["maxAbsLuaNativeCoordinateDifferenceCandidate"],
                          "output": str(args.output)}))
        return 0 if result["status"] == "candidate-only" else 2
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            json.JSONDecodeError, lua.base64.binascii.Error) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
