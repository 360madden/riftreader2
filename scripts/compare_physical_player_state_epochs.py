"""Offline cross-restart comparison of SHA-pinned native player-state receipts.

Separate process epochs never prove player identity continuity. This tool
reports only uncorrelated numeric candidates, not actual movement or health change.
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
from scripts import replay_physical_player_state as replay


def require(ok, reason):
    if not ok:
        raise ValueError("cross-epoch-" + reason)


def _epoch(report):
    t = report["target"]
    return {k: t[k] for k in ("hostName", "processId", "processStartUtcTicks", "executableSha256")}


def _xyz(report):
    v = report["candidateValues"]["position"]
    xyz = {k: v[k] for k in ("x", "y", "z")}
    require(all(type(x) in (float, int) and math.isfinite(x) for x in xyz.values()),
            "invalid-position")
    return xyz


def _hp(report):
    h = report["candidateValues"]["vitals"]["health"]
    return (h["current"] if h.get("status") == "calculated-candidate"
            and type(h.get("current")) is int else None)


def _compare_zone_candidates(before, after):
    """Compare guarded endpoint strings only; distinct epochs are not one world."""
    a, b = before.get("zoneBracketCandidate"), after.get("zoneBracketCandidate")
    if a is None or b is None:
        return {"status": "not-comparable", "reason": "one-or-both-zone-brackets-not-captured"}
    require(isinstance(a, dict) and isinstance(b, dict)
            and a.get("status") == b.get("status") == "matching-candidates"
            and isinstance(a.get("zoneIdCandidate"), str)
            and isinstance(b.get("zoneIdCandidate"), str), "invalid-zone-bracket")
    same = (a["zoneIdCandidate"] == b["zoneIdCandidate"]
            and a.get("rawZoneKey") == b.get("rawZoneKey"))
    return {"status": "matching-id-candidates" if same else "different-id-candidates",
            "beforeZoneIdCandidate": a["zoneIdCandidate"],
            "afterZoneIdCandidate": b["zoneIdCandidate"],
            "beforeRawZoneKey": a["rawZoneKey"],
            "afterRawZoneKey": b["rawZoneKey"],
            "worldInstanceStatus": "unavailable",
            "qualification": "Different process epochs: ID strings are native candidates, not "
                             "a continuous world identity or verified zone transition."}


def compare(before_path, after_path):
    a, b = replay.verified_state(before_path), replay.verified_state(after_path)
    require(a["summarySha256"] != b["summarySha256"], "same-source")
    ea, eb = _epoch(a), _epoch(b)
    require(ea["hostName"].casefold() == eb["hostName"].casefold(), "different-host")
    require((ea["processId"], ea["processStartUtcTicks"]) !=
            (eb["processId"], eb["processStartUtcTicks"]),
            "same-epoch-use-history")
    require(ea["executableSha256"].upper() == eb["executableSha256"].upper(),
            "different-build")
    require(replay._utc_tick_order_key(a["lastCompletedAtUtc"]) <
            replay._utc_tick_order_key(b["firstStartedAtUtc"]),
            "captures-overlap-or-reversed")
    xyz1, xyz2 = _xyz(a), _xyz(b)
    diff = {k: xyz2[k] - xyz1[k] for k in xyz1}
    require(all(math.isfinite(v) for v in diff.values()), "nonfinite-difference")
    hp1, hp2 = _hp(a), _hp(b)
    return {
        "schemaVersion": 1,
        "evidenceKind": "amd-physical-player-state-cross-epoch/1",
        "status": "candidate-only",
        "beforeSummarySha256": a["summarySha256"],
        "afterSummarySha256": b["summarySha256"],
        "beforeEpoch": ea, "afterEpoch": eb,
        "beforeCompletedAtUtc": a["lastCompletedAtUtc"],
        "afterStartedAtUtc": b["firstStartedAtUtc"],
        "beforeSelfKeyCandidate": a["selfKeyCandidate"],
        "afterSelfKeyCandidate": b["selfKeyCandidate"],
        "selfKeysNumericallyEqual": a["selfKeyCandidate"] == b["selfKeyCandidate"],
        "crossEpochZoneCandidateComparison": _compare_zone_candidates(a, b),
        "beforePositionCandidate": xyz1, "afterPositionCandidate": xyz2,
        "uncorrelatedNumericXYZDifference": diff,
        "uncorrelatedNumericPlanarDifference": math.hypot(diff["x"], diff["z"]),
        "beforeHealthCandidate": hp1, "afterHealthCandidate": hp2,
        "uncorrelatedNumericHealthDifference": (
            hp2 - hp1 if hp1 is not None and hp2 is not None else None),
        "qualification": ("Separate SHA-pinned exact-build epochs; no cross-restart "
                          "player-identity continuity, live freshness, independent Lua "
                          "comparison or action-causation established. Numeric "
                          "differences are NOT verified movement/health changes."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            require(not args.output.exists() and not args.output.is_symlink(),
                    "output-exists")
        result = compare(args.before, args.after)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as f:
                json.dump(result, f, indent=2, allow_nan=False)
                f.write("\n")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
