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
    require(first["lastSequence"] < second["firstSequence"]
            and first["lastClockCandidate"] < second["firstClockCandidate"],
            "nonadvancing-or-overlapping-passes")
    require(not ({f["frameSha256"] for f in first["frameEvidence"]} &
                 {f["frameSha256"] for f in second["frameEvidence"]}),
            "reused-frame")
    require(first["luaFrameCount"] >= 2 and second["luaFrameCount"] >= 2,
            "insufficient-independent-frames")
    first_end = first["luaPositionCandidates"][-1]
    second_start = second["luaPositionCandidates"][0]
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
        "frameCounts": [first["luaFrameCount"], second["luaFrameCount"]],
        "sequenceWindows": [[first["firstSequence"], first["lastSequence"]],
                            [second["firstSequence"], second["lastSequence"]]],
        "clockWindows": [[first["firstClockCandidate"], first["lastClockCandidate"]],
                         [second["firstClockCandidate"], second["lastClockCandidate"]]],
        "betweenPassLuaXYZDifferenceCandidate": lua_delta,
        "betweenPassNativeXYZDifferenceCandidate": native_delta,
        "maxAbsLuaNativeCoordinateDifferenceCandidate": across_max,
        "sourceSha256": {
            "first": first["sourceSha256"],
            "second": second["sourceSha256"],
        },
        "qualification": ("Two independently source-verified RR2A1 Lua baseline passes "
                          "have increasing sequence and clock values within one candidate "
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-index", type=Path, required=True)
    parser.add_argument("--second-index", type=Path, required=True)
    parser.add_argument("--first-native-bracket", type=Path, required=True)
    parser.add_argument("--second-native-bracket", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(),
                "output-exists")
        result = compare(args.first_index, args.second_index,
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
