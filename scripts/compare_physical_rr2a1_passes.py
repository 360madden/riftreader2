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


def compare(first_index, second_index, first_native_bracket, second_native_bracket=None):
    """Recheck raw sources rather than trust previously generated replay summaries."""
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-bracketed-order", action="store_true",
                        help="Verify original native→scan→scan→native UTC order")
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(),
                "output-exists")
        result = compare(args.first_index, args.second_index,
                         args.first_native_bracket, args.second_native_bracket)
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
