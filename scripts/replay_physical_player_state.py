"""Offline SHA-pinned replay of composite physical player-state receipts.

No process access, game input or desktop interaction. Native values are
candidate evidence, not Lua-verified or automatically fresh gameplay state.
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

from scripts import collect_physical_player_state as state
from scripts import compare_physical_player_context_pair as context
from scripts.physical_rift import _native_values, _utc_tick_order_key


def require(ok, reason):
    if not ok:
        raise ValueError("physical-state-replay-" + reason)


def verified_state(filename):
    filename = Path(filename)
    receipt, receipt_sha = context.load(filename)
    owner = receipt.get("target")
    require(receipt.get("schemaVersion") == 1
            and receipt.get("evidenceKind") == "amd-physical-player-state-candidate/1"
            and receipt.get("status") == "complete-candidate"
            and receipt.get("ownerHost") == state.HOST
            and isinstance(owner, dict)
            and owner.get("hostName") == state.HOST
            and type(owner.get("processId")) is int and owner["processId"] > 0
            and str(owner.get("processStartUtcTicks", "")).isdecimal()
            and str(owner.get("executableSha256", "")).upper() == state.BUILD_SHA
            and isinstance(receipt.get("sources"), dict)
            and set(receipt["sources"]) == set(state.KINDS)
            and isinstance(receipt.get("selfKeyCandidate"), str)
            and receipt["selfKeyCandidate"].isdecimal()
            and int(receipt["selfKeyCandidate"]) > 0,
            "invalid-summary-owner")
    module = (receipt.get("moduleBaseAddress"), receipt.get("moduleSize"))
    require(all(type(v) is int and v > 0 for v in module), "invalid-module")
    values, hashes = {}, {}
    previous_end, first_time, last_time = None, None, None
    for kind in state.KINDS:
        saved = receipt["sources"][kind]
        require(isinstance(saved, dict)
                and type(saved.get("samples")) is int and 2 <= saved["samples"] <= 10
                and isinstance(saved.get("sourceSha256"), str)
                and Path(str(saved.get("path", ""))).name == kind + ".json",
                kind + "-invalid-source-pin")
        # Resolve fixed local filenames, NOT arbitrary absolute paths from receipts.
        report, actual_sha = context.load(filename.parent / (kind + ".json"),
                                          saved["sourceSha256"])
        identity, rows = report.get("identity"), report.get("observations")
        require(isinstance(identity, dict)
                and identity.get("processId") == owner["processId"]
                and str(identity.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                and str(identity.get("executableSha256", "")).upper() == state.BUILD_SHA
                and (identity.get("moduleBaseAddress"), identity.get("moduleSize")) == module
                and report.get("status") == "complete"
                and report.get("requestedSamples") == saved["samples"]
                and report.get("completedSamples") == saved["samples"]
                and isinstance(rows, list) and len(rows) == saved["samples"]
                and (report.get("observation") == rows[-1] if kind != "position"
                     else report.get("observation") is None),
                kind + "-invalid-source-owner")
        for sample in rows:
            require(isinstance(sample, dict)
                    and (kind == "position" or sample.get("identity") == identity)
                    and str(sample.get("unitKey")) == receipt["selfKeyCandidate"],
                    kind + "-sample-owner")
            start = _utc_tick_order_key(sample.get("startedAtUtc"))
            end = _utc_tick_order_key(sample.get("completedAtUtc"))
            require(start <= end and (previous_end is None or previous_end <= start),
                    kind + "-sample-time-order")
            if first_time is None:
                first_time = sample["startedAtUtc"]
            previous_end, last_time = end, sample["completedAtUtc"]
        projected = _native_values(kind, report)
        require(projected == saved.get("candidateValues"),
                kind + "-candidate-projection-mismatch")
        if kind == "vitals" and "burstSummary" in saved:
            burst = saved["burstSummary"]
            require(isinstance(burst, dict)
                    and str(burst.get("sourceReportSha256", "")).upper() == actual_sha
                    and burst.get("processId") == owner["processId"]
                    and str(burst.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                    and str(burst.get("unitKey")) == receipt["selfKeyCandidate"]
                    and burst.get("sampleCount") == saved["samples"],
                    "vitals-burst-pin-mismatch")
        values[kind] = projected
        hashes[kind] = {"sha256": actual_sha, "samples": saved["samples"]}
    return {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-replay/1",
        "status": "candidate-only", "summarySha256": receipt_sha, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": receipt["selfKeyCandidate"], "sources": hashes,
        "firstStartedAtUtc": first_time, "lastCompletedAtUtc": last_time,
        "candidateValues": values,
        "qualification": "Pinned sequential native replay; not atomic, passive-fresh, Lua-correlated or restart-qualified.",
    }


def _compare_states(a, b):
    """Compare two previously verified native observations."""
    require(a["summarySha256"] != b["summarySha256"], "same-source")
    require(a["target"] == b["target"]
            and (a["moduleBaseAddress"], a["moduleSize"]) ==
                (b["moduleBaseAddress"], b["moduleSize"])
            and a["selfKeyCandidate"] == b["selfKeyCandidate"],
            "owner-or-epoch-changed")
    require(_utc_tick_order_key(a["lastCompletedAtUtc"]) <
            _utc_tick_order_key(b["firstStartedAtUtc"]),
            "captures-overlap-or-reversed")
    v1, v2 = a["candidateValues"]["position"], b["candidateValues"]["position"]
    delta = {axis: v2[axis] - v1[axis] for axis in ("x", "y", "z")}
    require(all(type(x) in (int, float) and math.isfinite(x) for x in delta.values()),
            "invalid-position-delta")
    h1 = a["candidateValues"]["vitals"]["health"]
    h2 = b["candidateValues"]["vitals"]["health"]
    health_delta = (h2["current"] - h1["current"]
                    if h1.get("status") == h2.get("status") == "calculated-candidate"
                    and type(h1.get("current")) is int and type(h2.get("current")) is int
                    else None)
    return {
        "schemaVersion": 1, "status": "candidate-only",
        "evidenceKind": "amd-physical-player-state-pair/1",
        "beforeSummarySha256": a["summarySha256"],
        "afterSummarySha256": b["summarySha256"],
        "processId": a["target"]["processId"],
        "selfKeyCandidate": a["selfKeyCandidate"],
        "positionDeltaCandidate": delta,
        "planarDistanceCandidate": math.hypot(delta["x"], delta["z"]),
        "healthDeltaCandidate": health_delta,
        "qualification": "Same-epoch candidate change only; no movement causation, Lua validation or freshness proof.",
    }


def compare(before, after):
    return _compare_states(verified_state(before), verified_state(after))


def history(summaries):
    """Ordered, same-process trajectory of offline native evidence."""
    require(2 <= len(summaries) <= 24, "history-count-out-of-bounds")
    captures = [verified_state(path) for path in summaries]
    edges = [_compare_states(a, b) for a, b in zip(captures, captures[1:])]
    health = [capture["candidateValues"]["vitals"]["health"] for capture in captures]
    health_points = [h["current"] if h.get("status") == "calculated-candidate"
                     and type(h.get("current")) is int else None for h in health]
    delta = {axis: captures[-1]["candidateValues"]["position"][axis] -
             captures[0]["candidateValues"]["position"][axis]
             for axis in ("x", "y", "z")}
    require(all(type(v) in (int, float) and math.isfinite(v) for v in delta.values()),
            "invalid-history-position-delta")
    return {
        "schemaVersion": 1, "status": "candidate-only",
        "evidenceKind": "amd-physical-player-state-history/1",
        "processId": captures[0]["target"]["processId"],
        "selfKeyCandidate": captures[0]["selfKeyCandidate"],
        "captureCount": len(captures),
        "summarySha256s": [capture["summarySha256"] for capture in captures],
        "firstStartedAtUtc": captures[0]["firstStartedAtUtc"],
        "lastCompletedAtUtc": captures[-1]["lastCompletedAtUtc"],
        "segments": [{
            "beforeSummarySha256": edge["beforeSummarySha256"],
            "afterSummarySha256": edge["afterSummarySha256"],
            "positionDeltaCandidate": edge["positionDeltaCandidate"],
            "planarDistanceCandidate": edge["planarDistanceCandidate"],
            "healthDeltaCandidate": edge["healthDeltaCandidate"],
        } for edge in edges],
        "sumPlanarChordsCandidate": sum(e["planarDistanceCandidate"] for e in edges),
        "netPositionDeltaCandidate": delta,
        "healthObservedCount": sum(h is not None for h in health_points),
        "healthMinCandidate": min((h for h in health_points if h is not None), default=None),
        "healthMaxCandidate": max((h for h in health_points if h is not None), default=None),
        "qualification": ("SHA-pinned ordered same-process native candidates; planar chords "
                          "are sampled straight-line distances, NOT actual travel. No "
                          "independent Lua, freshness, movement-causation or restart proof."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--history", nargs="+", type=Path,
                        help="Additional 1-23 ordered summaries for offline history")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        require(not (args.after and args.history), "options-conflict")
        result = (history([args.summary, *args.history]) if args.history else
                  compare(args.summary, args.after) if args.after else
                  verified_state(args.summary))
        if args.output:
            require(not args.output.exists() and not args.output.is_symlink(), "output-exists")
            with args.output.open("x", encoding="utf-8", newline="\n") as out:
                json.dump(result, out, indent=2, allow_nan=False)
                out.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"], "evidenceKind": result["evidenceKind"],
                      "summarySha256": result.get("summarySha256"),
                      "sourceCount": len(result["sources"]) if "sources" in result else None,
                      "captureCount": result.get("captureCount"),
                      "output": str(args.output) if args.output else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
