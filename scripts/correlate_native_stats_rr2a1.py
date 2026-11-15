"""Join independently replayed physical RR2A1 Lua/XYZ evidence to native stats.

Offline only: requires an earlier SHA-pinned four-source native state receipt
and later advancing unbound Lua/native brackets on the SAME physical process.
Matching ID/XYZ candidates do NOT qualify raw stat semantics or producer nonce.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_physical_player_context_pair as sources
from scripts import compare_physical_rr2a1_passes as lua
from scripts import probe_physical_rr2r1 as probe
from scripts import replay_physical_player_state as state
from scripts.physical_rift import _utc_tick_order_key

MAX_EVIDENCE_GAP_TICKS = 10 * 60 * 10_000_000


def require(ok, reason):
    if not ok:
        raise ValueError("native-stats-rr2a1-" + reason)


def correlate(state_summary, rr2a1_summary):
    native = state.verified_state(state_summary)
    stats = native["candidateValues"].get("stats")
    require(isinstance(stats, dict)
            and stats.get("status") == "candidate-only"
            and stats.get("selectorCount") == 20
            and isinstance(stats.get("stats"), list)
            and len(stats["stats"]) == 20,
            "four-source-native-stats-required")

    summary_path = Path(rr2a1_summary)
    retained, retained_sha = sources.load(summary_path)
    require(retained.get("schemaVersion") == 1
            and retained.get("evidenceKind") == "amd-physical-rr2a1-bracketed-two-pass/1"
            and retained.get("status") == "candidate-only"
            and retained.get("ownerHost") == "AMD-DESKTOP"
            and isinstance(retained.get("target"), dict),
            "invalid-lua-summary")
    owner = native["target"]
    for field in ("processId", "processStartUtcTicks", "executableSha256"):
        lhs, rhs = owner.get(field), retained["target"].get(field)
        if field == "executableSha256":
            lhs, rhs = str(lhs).upper(), str(rhs).upper()
        require(lhs == rhs, "process-epoch-or-build-mismatch")
    require(owner.get("hostName") == retained["target"].get("hostName") ==
            "AMD-DESKTOP", "wrong-owner-host")

    root = summary_path.parent
    focus = retained.get("secondPassFocus")
    require(isinstance(focus, dict)
            and type(focus.get("fallbackUsed")) is bool,
            "missing-pass-selection")
    second = "pass-02-broad" if focus["fallbackUsed"] else "pass-02"
    last_bracket = "native-after-broad" if focus["fallbackUsed"] and (
        root / "native-after-broad" / "summary.json").is_file() else "native-after"
    first_index = root / "pass-01" / "scan" / "index.json"
    second_index = root / second / "scan" / "index.json"
    before = root / "native-before" / "summary.json"
    after = root / last_bracket / "summary.json"
    pins = ((before, retained.get("nativeBracketSha256"), "before"),
            (after, retained.get("nativeBracketSha256"), "after"),
            (first_index, retained.get("scanIndexSha256"), "first"),
            (second_index, retained.get("scanIndexSha256"), "second"))
    for path, saved, key in pins:
        require(isinstance(saved, dict) and isinstance(saved.get(key), str)
                and path.is_file() and not path.is_symlink()
                and probe.digest(path).upper() == saved[key].upper(),
                "source-pin-mismatch-" + key)

    replayed = lua.compare(first_index, second_index, before, after)
    replayed["captureOrder"] = lua.verify_capture_order(
        first_index, second_index, before, after)
    require(retained.get("comparison") == replayed
            and replayed.get("status") == "candidate-only"
            and replayed.get("coordinateAgreementScreen", {}).get("withinTolerance")
            is True, "lua-native-replay-disagreement")
    peer = replayed["identity"]
    require(peer.get("host") == "AMD-DESKTOP"
            and peer.get("processId") == owner["processId"]
            and str(peer.get("processStartUtcTicks")) ==
            str(owner["processStartUtcTicks"])
            and str(peer.get("executableSha256", "")).upper() ==
            str(owner["executableSha256"]).upper(),
            "lua-native-owner-mismatch")

    expected_id = "u" + format(int(native["selfKeyCandidate"]), "016X")
    require(replayed.get("luaPlayerIdCandidate") == expected_id,
            "native-lua-self-id-mismatch")
    _, _, first_bracket_start, _ = lua.native.verified_bracket(before)
    end_dt, end_tick = _utc_tick_order_key(native["lastCompletedAtUtc"])
    start_dt, start_tick = _utc_tick_order_key(first_bracket_start)
    gap = start_dt - end_dt
    gap_ticks = (gap.days * 86400 + gap.seconds) * 10_000_000 + (
        gap.microseconds * 10 + start_tick - end_tick)
    require(0 < gap_ticks <= MAX_EVIDENCE_GAP_TICKS,
            "native-stats-not-prior-and-near-lua")

    raw_count = sum(
        isinstance(entry.get(variant), dict) and
        entry[variant].get("status") == "raw-candidate"
        for entry in stats["stats"] for variant in ("ordinary", "unbuffed"))
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-native-stats-rr2a1-linked-candidates/1",
        "status": "candidate-only",
        "processId": owner["processId"],
        "processStartUtcTicks": owner["processStartUtcTicks"],
        "executableSha256": owner["executableSha256"],
        "luaPlayerIdCandidate": expected_id,
        "nativeSelfKeyCandidate": native["selfKeyCandidate"],
        "nativeStats": stats,
        "rawStatValuesAvailable": raw_count,
        "nativeSummarySha256": native["summarySha256"],
        "luaSummarySha256": retained_sha,
        "nativeStatsSourceSha256": native["sources"]["stats"]["sha256"],
        "luaSequenceWindows": replayed["sequenceWindows"],
        "coordinateAgreementScreen": replayed["coordinateAgreementScreen"],
        "candidateObservationGapSeconds": gap_ticks / 10_000_000,
        "qualification": ("Independent source-replayed Lua/native self-ID and XYZ candidates "
                          "agree in one process epoch and precede/follow one 20-stat snapshot. "
                          "Lua RR2A1 is unbound; stats are raw candidates, not independently "
                          "verified semantics, nonce-authenticated freshness, atomic state, "
                          "changed-state causality, or a live-control readiness signal."),
    }


def correlate_with_previous(previous_state, current_state, rr2a1_summary):
    """Link a source-verified native stat *change candidate* to a later Lua bracket.

    The native pair is strictly same-process and ordered; Lua only independently
    screens the latest native player's identity/coordinates, not stat semantics.
    """
    linked = correlate(current_state, rr2a1_summary)
    pair = state.compare(previous_state, current_state)
    require(pair.get("status") == "candidate-only"
            and pair.get("afterSummarySha256") == linked["nativeSummarySha256"]
            and pair.get("processId") == linked["processId"]
            and str(pair.get("selfKeyCandidate")) == linked["nativeSelfKeyCandidate"],
            "previous-native-pair-mismatch")
    comparison = pair.get("nativeStatsComparison")
    require(isinstance(comparison, dict)
            and comparison.get("status") == "comparable-candidate"
            and type(comparison.get("rawValuesCompared")) is int
            and comparison["rawValuesCompared"] > 0,
            "previous-native-stats-not-comparable")
    linked["previousNativeSummarySha256"] = pair["beforeSummarySha256"]
    linked["nativeStatsComparison"] = comparison
    linked["qualification"] += (" Pair differences are native raw-value candidates; "
                                "the later Lua bracket does not authenticate or "
                                "independently validate any stat change.")
    return linked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-summary", type=Path, required=True)
    parser.add_argument("--rr2a1-summary", type=Path, required=True)
    parser.add_argument("--previous-state-summary", type=Path,
                        help="Optional earlier same-process four-source native capture")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            require(not args.output.exists() and not args.output.is_symlink(),
                    "output-exists")
        result = (correlate_with_previous(args.previous_state_summary,
                                          args.state_summary, args.rr2a1_summary)
                  if args.previous_state_summary else
                  correlate(args.state_summary, args.rr2a1_summary))
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(result, output, indent=2, allow_nan=False)
                output.write("\n")
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({
        "status": result["status"],
        "processId": result["processId"],
        "luaPlayerIdCandidate": result["luaPlayerIdCandidate"],
        "rawStatValuesAvailable": result["rawStatValuesAvailable"],
        "rawStatValuesChanged": result.get("nativeStatsComparison", {}).get("rawValuesChanged"),
        "candidateObservationGapSeconds": result["candidateObservationGapSeconds"],
        "output": str(args.output) if args.output else None,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
