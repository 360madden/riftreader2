"""Offline comparison of two separately source-replayed AMD physical RR2A1 captures.

Rechecks original scan/native receipts, not just saved summaries. Unbound Lua
observations and native XYZ are *candidates*; longitudinal agreement is not
proof of movement causation, nonce authenticity or uninterrupted producer life.
No process or desktop access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts import compare_physical_rr2a1_passes as pair
from scripts import compare_physical_player_brackets as native
from scripts import compare_physical_player_context_pair as source
from scripts.physical_rift import _utc_tick_order_key


def require(condition, reason):
    if not condition:
        raise ValueError("physical-rr2a1-session-" + reason)


def replay_session(summary_path):
    path = Path(summary_path)
    saved, summary_sha = source.load(path)
    require(saved.get("schemaVersion") == 1
            and saved.get("evidenceKind") == "amd-physical-rr2a1-bracketed-two-pass/1"
            and saved.get("status") == "candidate-only"
            and saved.get("ownerHost") == "AMD-DESKTOP",
            "invalid-summary")
    root = path.parent
    fallback = saved["secondPassFocus"]["fallbackUsed"]
    require(type(fallback) is bool, "invalid-fallback")
    first = root / "pass-01" / "scan" / "index.json"
    second = root / ("pass-02-broad" if fallback else "pass-02") / "scan" / "index.json"
    before = root / "native-before" / "summary.json"
    after_candidates = (root / "native-after" / "summary.json",
                        root / "native-after-broad" / "summary.json")
    after = next((candidate for candidate in after_candidates
                  if candidate.is_file() and not candidate.is_symlink()
                  and 0 < candidate.stat().st_size <= source.MAX_BYTES
                  and hashlib.sha256(candidate.read_bytes()).hexdigest().upper() ==
                  saved["nativeBracketSha256"]["after"].upper()), None)
    require(after is not None, "missing-matching-native-after")
    for filename, expected in (
        (first, saved["scanIndexSha256"]["first"]),
        (second, saved["scanIndexSha256"]["second"]),
        (before, saved["nativeBracketSha256"]["before"]),
        (after, saved["nativeBracketSha256"]["after"]),
    ):
        source.load(filename, expected)
    recalculated = pair.compare(first, second, before, after)
    recalculated["captureOrder"] = pair.verify_capture_order(
        first, second, before, after)
    require(recalculated == saved["comparison"], "saved-comparison-mismatch")
    require(recalculated["status"] == "candidate-only"
            and recalculated["coordinateAgreementScreen"]["withinTolerance"]
            and recalculated["identity"]["host"] == "AMD-DESKTOP",
            "unqualified-coordinate-agreement")
    identity = recalculated["identity"]
    target = saved["target"]
    require(target.get("hostName") == identity["host"]
            and target.get("processId") == identity["processId"]
            and str(target.get("processStartUtcTicks")) ==
                str(identity["processStartUtcTicks"])
            and target.get("executableSha256", "").upper() ==
                identity["executableSha256"].upper(),
            "summary-process-mismatch")
    _, _, before_start, _ = native.verified_bracket(before)
    _, _, _, after_end = native.verified_bracket(after)
    return {
        "summarySha256": summary_sha,
        "identity": identity,
        "readerSha256": saved["readerSha256"],
        "comparison": recalculated,
        "firstStartedAtUtc": before_start,
        "lastCompletedAtUtc": after_end,
    }


def compare_sessions(older, newer):
    a, b = older["comparison"], newer["comparison"]
    require(older["summarySha256"] != newer["summarySha256"], "same-source")
    require(older["identity"] == newer["identity"]
            and older["readerSha256"] == newer["readerSha256"]
            and a["luaPlayerIdCandidate"] == b["luaPlayerIdCandidate"],
            "process-player-or-reader-changed")
    require(_utc_tick_order_key(older["lastCompletedAtUtc"]) <
            _utc_tick_order_key(newer["firstStartedAtUtc"]),
            "overlap-or-reversed-captures")
    pa, pb = a["positionCandidates"], b["positionCandidates"]
    native_delta = {k: pb["nativeAfter"][k] - pa["nativeAfter"][k]
                    for k in ("x", "y", "z")}
    lua_delta = {k: pb["lastLua"][k] - pa["lastLua"][k]
                 for k in ("x", "y", "z")}
    residual = {k: abs(lua_delta[k] - native_delta[k])
                for k in ("x", "y", "z")}
    require(all(math.isfinite(v) for group in (native_delta, lua_delta, residual)
                for v in group.values()), "nonfinite-difference")
    consistent = all(v <= pair.MAX_COORDINATE_GAP_CANDIDATE * 2
                     for v in residual.values())
    # Larger than repeated static float32 jitter, but not an action attribution.
    native_travel = math.hypot(native_delta["x"], native_delta["z"])
    lua_travel = math.hypot(lua_delta["x"], lua_delta["z"])
    changed = native_travel > 0.1 and lua_travel > 0.1
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-rr2a1-longitudinal-candidates/1",
        "status": "candidate-only" if consistent else "candidate-disagreement",
        "identity": older["identity"],
        "sourceSummarySha256": [older["summarySha256"], newer["summarySha256"]],
        "oldCompletedAtUtc": older["lastCompletedAtUtc"],
        "newStartedAtUtc": newer["firstStartedAtUtc"],
        "playerIdCandidate": a["luaPlayerIdCandidate"],
        "luaEpochCandidates": [a["luaEpochCandidate"], b["luaEpochCandidate"]],
        "producerSequenceContinuity": (
            "increasing" if b["sequenceWindows"][0][0] >
                            a["sequenceWindows"][-1][-1] else "not-increasing"),
        "producerClockContinuity": (
            "increasing" if b["clockWindows"][0][0] >
                            a["clockWindows"][-1][-1] else "not-increasing"),
        "nativeXYZCandidateDifference": native_delta,
        "luaXYZCandidateDifference": lua_delta,
        "maxPerAxisDeltaDiscrepancy": max(residual.values()),
        "nativePlanarDifference": native_travel,
        "luaPlanarDifference": lua_travel,
        "changedCoordinateScreen": (
            "consistent-candidate-change" if changed and consistent
            else "not-established" if consistent else "disagreement"),
        "qualification": (
            "Separate exact-process source-replayed Lua and native coordinate "
            "candidates. Producer sequence/clock continuity is reported, NOT "
            "assumed from a reused numeric epoch. No nonce-authenticated producer, "
            "atomic freshness, action causation, heading, target or combat meaning."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--older", type=Path, required=True)
    parser.add_argument("--newer", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    try:
        if options.output is not None:
            require(not options.output.exists() and not options.output.is_symlink(),
                    "output-exists")
        result = compare_sessions(replay_session(options.older),
                                  replay_session(options.newer))
        if options.output is not None:
            with options.output.open("x", encoding="utf-8", newline="\n") as out:
                json.dump(result, out, indent=2, allow_nan=False)
                out.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "candidate-only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
