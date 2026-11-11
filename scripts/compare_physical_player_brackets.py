"""Strict offline comparison of two independently retained AMD physical self->XYZ brackets.

Rechecks every native source and the saved summary, never reads a live process.
A changed coordinate is a *candidate difference*, not movement causation or Lua proof.
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

from scripts import compare_physical_player_context_pair as context
from scripts import physical_player_xyz_bracket as bracket
from scripts.physical_rift import _utc_tick_order_key


def require(condition, reason):
    if not condition:
        raise ValueError("physical-bracket-pair-" + reason)


def verified_bracket(summary_path):
    summary_path = Path(summary_path)
    summary, summary_sha = context.load(summary_path)
    require(summary.get("schemaVersion") == 1
            and summary.get("evidenceKind") == "amd-physical-player-xyz-native-bracket/1"
            and summary.get("status") == "candidate-only"
            and isinstance(summary.get("identity"), dict)
            and isinstance(summary.get("sourceSha256"), dict), "summary-shape-invalid")
    identity = summary["identity"]
    require(identity.get("host") == bracket.EXPECTED_HOST, "wrong-owner")
    selection = {
        "status": "ready", "ownerHost": bracket.EXPECTED_HOST,
        "target": {
            "processId": identity.get("processId"),
            "processStartUtcTicks": identity.get("processStartUtcTicks"),
            "executableSha256": identity.get("executableSha256"),
        },
    }
    sources = {}
    for name, filename in (("before", "context-before.json"),
                           ("position", "position.json"),
                           ("after", "context-after.json")):
        expected_sha = summary["sourceSha256"].get(name)
        require(isinstance(expected_sha, str), "source-pin-missing")
        sources[name], _ = context.load(summary_path.parent / filename, expected_sha)
    recalculated = bracket.assess(
        sources["before"], sources["position"], sources["after"],
        summary["sourceSha256"], selection)
    require(recalculated == summary, "summary-replay-mismatch")
    first = sources["before"]["observation"]["startedAtUtc"]
    last = sources["after"]["observation"]["completedAtUtc"]
    return summary, summary_sha, first, last


def compare(before_path, after_path):
    left, left_sha, left_start, left_end = verified_bracket(before_path)
    right, right_sha, right_start, right_end = verified_bracket(after_path)
    require(left_sha != right_sha, "same-source")
    require(left["identity"] == right["identity"], "process-epoch-or-build-changed")
    require(left["selfKeyCandidate"] == right["selfKeyCandidate"], "self-key-changed")
    before_end_tick = _utc_tick_order_key(left_end)
    after_start_tick = _utc_tick_order_key(right_start)
    require(before_end_tick < after_start_tick, "overlapping-or-reversed-captures")
    a, b = left["lastPositionCandidate"], right["firstPositionCandidate"]
    dx, dy, dz = (b[axis] - a[axis] for axis in ("x", "y", "z"))
    distance = math.hypot(dx, dz)
    gap = ((after_start_tick[0] - before_end_tick[0]).total_seconds()
           + (after_start_tick[1] - before_end_tick[1]) / 10_000_000)
    require(math.isfinite(distance) and math.isfinite(dy) and gap > 0,
            "nonfinite-or-nonpositive-difference")
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-player-native-bracket-pair/1",
        "status": "candidate-only",
        "identity": left["identity"],
        "selfKeyCandidate": left["selfKeyCandidate"],
        "sourceSha256": {"beforeSummary": left_sha, "afterSummary": right_sha},
        "sampleCounts": {"before": left["sampleCount"], "after": right["sampleCount"]},
        "beforeCompletedAtUtc": left_end,
        "afterStartedAtUtc": right_start,
        "gapSeconds": gap,
        "positionDeltaCandidate": {"x": dx, "y": dy, "z": dz},
        "planarDistanceCandidate": distance,
        "qualification": "same-epoch native coordinate difference only; no Lua correspondence, game-input causation, passive refresh, or restart proof",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(),
                "output-exists")
        result = compare(args.before, args.after)
        with args.output.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"],
                      "planarDistanceCandidate": result["planarDistanceCandidate"],
                      "gapSeconds": result["gapSeconds"],
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
