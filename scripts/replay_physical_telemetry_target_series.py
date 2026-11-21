"""Offline continuity of source-verified physical RIFT target captures.

Each input must be a successful, independently replayable native/Lua capture.
This does not acquire RIFT input, invent missing target states, or claim that
a user's action caused any observed A->B->A pattern.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import replay_physical_telemetry_target as target_replay

SHA = re.compile(r"[0-9A-F]{64}\Z")
UNIT = re.compile(r"u[0-9A-F]{16}\Z")
SCHEMA = "physical-target-continuity-offline/1"
IDENTITY = ("processId", "processStartUtcTicks", "executableSha256",
            "playerUnitId", "zoneIdCandidate", "sourceEpoch", "sourceSessionId")


def require(condition, reason):
    if not condition:
        raise ValueError("target-continuity-" + reason)


def combine(paths, *, replay=target_replay.replay):
    """Compare independent verified captures; do not extrapolate unseen events."""
    require(type(paths) in (tuple, list) and 2 <= len(paths) <= 16,
            "requires-2-to-16-captures")
    observations, used, baseline = [], set(), None
    for index, value in enumerate(paths, 1):
        path = Path(value)
        require(path.is_file() and not path.is_symlink(),
                "source-file-unavailable")
        result = replay(path)
        require(type(result) is dict and result.get("qualificationStatus") == "candidate-only"
                and result.get("status") in (
                    "no-target-baseline-candidate", "selected-target-observations-candidate",
                    "a-b-a-target-candidate"), "source-not-qualified-for-continuity")
        identity = {name: result.get(name) for name in IDENTITY}
        require(type(identity["processId"]) is int and identity["processId"] > 0
                and isinstance(identity["processStartUtcTicks"], str)
                and identity["processStartUtcTicks"].isdecimal()
                and isinstance(identity["executableSha256"], str)
                and isinstance(identity["playerUnitId"], str)
                and isinstance(identity["zoneIdCandidate"], str)
                and type(identity["sourceEpoch"]) is int and identity["sourceEpoch"] > 0
                and isinstance(identity["sourceSessionId"], str)
                and identity["sourceSessionId"], "source-identity-invalid")
        if baseline is None:
            baseline = identity
        else:
            require(identity == baseline, "process-player-zone-or-publisher-changed")
        sha = result.get("evidenceSummarySha256")
        require(type(sha) is str and SHA.fullmatch(sha) is not None
                and sha not in used, "source-hash-missing-or-reused")
        used.add(sha)
        first, last = result.get("firstSequence"), result.get("lastSequence")
        require(type(first) is int and type(last) is int and 0 < first <= last
                and type(result.get("observedFrameCount")) is int
                and 1 <= result["observedFrameCount"] <= last - first + 1,
                "source-sequences-invalid")
        runs = result.get("runs")
        require(isinstance(runs, list) and runs and
                type(runs[-1]) is dict and runs[-1].get("lastSequence") == last,
                "source-runs-invalid")
        last_target = runs[-1].get("targetUnitIdCandidate")
        require(last_target is None or type(last_target) is str
                and UNIT.fullmatch(last_target) is not None,
                "source-target-id-invalid")
        gap = 0
        if observations:
            prior = observations[-1]
            require(last > prior["lastSequence"],
                    "no-new-advancing-source-sequence")
            gap = max(0, first - prior["lastSequence"] - 1)
        observations.append({
            "capture": index, "evidenceSummarySha256": sha,
            "firstSequence": first, "lastSequence": last,
            "sampledTargetUnitIdCandidate": last_target,
            "observedFrameCount": result["observedFrameCount"],
            "minimumUnobservedSequencesWithinCapture": (
                last - first + 1 - result["observedFrameCount"]),
            "sourceStatus": result["status"],
            "unobservedSequenceGapFromPrior": gap,
            "nativeTargetComparisonStatus": (
                (result.get("nativeTargetComparison") or {}).get("status")
            ),
        })
    runs = []
    for sample in observations:
        ident = sample["sampledTargetUnitIdCandidate"]
        if not runs or runs[-1]["targetUnitIdCandidate"] != ident:
            runs.append({"targetUnitIdCandidate": ident,
                         "firstCapture": sample["capture"],
                         "lastCapture": sample["capture"]})
        else:
            runs[-1]["lastCapture"] = sample["capture"]
    cycles = [
        {"targetACandidate": a["targetUnitIdCandidate"],
         "targetBCandidate": b["targetUnitIdCandidate"],
         "firstCapture": a["firstCapture"],
         "secondCapture": b["firstCapture"],
         "returnCapture": c["firstCapture"]}
        for a, b, c in zip(runs, runs[1:], runs[2:])
        if a["targetUnitIdCandidate"] is not None
        and b["targetUnitIdCandidate"] is not None
        and a["targetUnitIdCandidate"] != b["targetUnitIdCandidate"]
        and a["targetUnitIdCandidate"] == c["targetUnitIdCandidate"]
    ]
    status = ("a-b-a-across-captures-candidate" if cycles
              else "no-target-continuity-candidate"
              if all(x["sampledTargetUnitIdCandidate"] is None for x in observations)
              else "target-continuity-observations-candidate")
    return {
        "schema": SCHEMA, "status": status,
        "qualificationStatus": "candidate-only", "runtimeIdentity": baseline,
        "captureCount": len(observations), "captures": observations,
        "lastObservedTargetRuns": runs, "aBaAcrossCaptures": cycles,
        "unobservedSequenceGapCount": sum(x["unobservedSequenceGapFromPrior"] > 0
                                          for x in observations[1:]),
        "capturesWithInternalSequenceGaps": sum(
            x["minimumUnobservedSequencesWithinCapture"] > 0
            for x in observations),
        "inputSent": False,
        "qualification": ("Each capture independently source-hash-replayed with advancing "
                          "publisher frames; same process, player, zone, session and epoch. "
                          "Only last observed target of each capture is compared. "
                          "Intermediate target changes are unknown; per-capture missing "
                          "sequence counts are lower bounds that may overlap across "
                          "captures, not a global coverage claim. Between-capture gaps "
                          "are separate; "
                          "native endpoints are sequential candidates, not atomic. "
                          "No selection-action causation, full A->B->A history, world "
                          "instance identity, or navigation authority is established.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, action="append", type=Path,
                        help="Source-hashed successful capture (repeat 2-16 times)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            require(not args.output.exists() and not args.output.is_symlink()
                    and args.output.parent.is_dir(),
                    "output-exists-or-parent-unavailable")
        result = combine(args.summary)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.write("\n")
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"],
                      "captureCount": result["captureCount"],
                      "aBaCandidates": len(result["aBaAcrossCaptures"]),
                      "qualificationStatus": result["qualificationStatus"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
