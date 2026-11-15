#!/usr/bin/env python3
"""Offline consistency audit for a completed RR2 hunt-mission checkpoint.

Never opens a game process or authorizes input. A consistent checkpoint is not
independent evidence that gameplay, target death or return movement occurred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import hunt_mission as mission_cli


def _required(condition, reason):
    if not condition:
        raise mission_cli.MissionError(reason)


def _released(receipt):
    return (isinstance(receipt, dict)
            and receipt.get("releaseSucceeded") is True
            and receipt.get("desktopInputsDown") == []
            and receipt.get("allInputsReleased", True) is True)


def audit(mission, route, progress):
    """Reject inconsistent completion claims using retained checkpoint data only."""
    _required(progress.get("schema") == mission_cli.CHECKPOINT_SCHEMA
              and progress.get("mission") == mission["name"]
              and progress.get("missionBinding") == mission["binding"],
              "mission binding is inconsistent")
    _required(progress.get("stage") == "complete"
              and progress.get("completed") is True, "mission is not complete")
    _required(type(progress.get("outboundNextIndex")) is int
              and progress["outboundNextIndex"] == len(route["waypoints"]),
              "outbound route progress is incomplete")
    document = progress.get("returnDocument")
    _required(isinstance(document, dict), "return corridor is missing")
    mission_cli._verified_retreat_seed(document, mission)
    provenance = document["provenance"]
    identity = provenance.get("runtimeIdentity")
    _required(isinstance(identity, dict)
              and identity.get("machine") == "AMD-DESKTOP"
              and isinstance(identity.get("gameBuildSha256"), str)
              and len(identity["gameBuildSha256"]) == 64
              and all(c in "0123456789abcdefABCDEF" for c in identity["gameBuildSha256"])
              and isinstance(identity.get("unitKey"), str) and bool(identity["unitKey"]),
              "return corridor runtime identity is not pinned to AMD-DESKTOP")
    _required(type(provenance.get("retainedPoints")) is int
              and provenance["retainedPoints"] == len(document["waypoints"]),
              "retained return-corridor count is inconsistent")

    encounter = progress.get("encounter")
    _required(_released(encounter), "encounter input release is unverified")
    target = mission["hunt"]["expectedTargetId"]
    selected = encounter.get("selectedTargetId")
    target_matches = isinstance(selected, str) and selected.casefold() == target.casefold()
    _required(target_matches or encounter.get("inputSent") is False,
              "encounter selection is inconsistent")
    encounter_status, reason = encounter.get("status"), encounter.get("reason")
    _required(encounter_status == "completed"
              or encounter_status == "blocked" and reason in {
                  "kill-credit-unverified", "selected-encounter-unsafe",
                  "encounter-deadline"}, "encounter outcome is ineligible")

    proofs = progress.get("killProofs")
    count = progress.get("killCount")
    _required(isinstance(proofs, list) and type(count) is int
              and 0 <= count <= min(1, mission["hunt"]["maximumKills"])
              and len(proofs) == count, "kill count and proof list disagree")
    _required(not count or target_matches,
              "qualified kill lacks matching selected encounter target")
    for proof in proofs:
        _required(isinstance(proof, dict) and proof.get("qualified") is True
                  and proof.get("kind") == "player-kill-confirmed"
                  and isinstance(proof.get("targetId"), str)
                  and proof["targetId"].casefold() == target.casefold(),
                  "kill proof is not qualified for the mission target")
    _required((encounter_status == "completed") == bool(count),
              "encounter completion and qualified kill credit disagree")
    _required((count == 0 and not (isinstance(encounter.get("killProof"), dict)
                                   and encounter["killProof"].get("qualified") is True))
              or (count == 1 and encounter.get("killProof") == proofs[0]),
              "encounter kill proof and checkpoint disagree")

    final = mission_cli._point(progress.get("finalPosition"), "final position")
    safe = mission["safeAnchor"]
    from math import hypot
    _required(hypot(final["x"]-safe["x"], final["z"]-safe["z"])
              <= safe["planarTolerance"]
              and abs(final["y"]-safe["y"]) <= safe["heightTolerance"],
              "final position is outside safe anchor")
    retreat = progress.get("safeRetreat")
    if retreat is not None:
        _required(reason in {"selected-encounter-unsafe", "encounter-deadline"}
                  and isinstance(retreat, dict)
                  and retreat.get("safeRetreat") is True
                  and retreat.get("status") == "arrived"
                  and _released(retreat), "safe-retreat receipt is inconsistent")
        position = mission_cli._point(retreat.get("position"), "safe retreat position")
        _required(position == final, "retreat position differs from checkpoint final")
        _required(progress.get("returnNextIndex") is None,
                  "safe retreat must not borrow normal return progress")
        mode = "safe-retreat"
    else:
        _required(reason not in {"selected-encounter-unsafe", "encounter-deadline"}
                  and type(progress.get("returnNextIndex")) is int
                  and progress["returnNextIndex"] == len(document["waypoints"]),
                  "normal return progress is incomplete")
        mode = "return"

    return {"status": "consistent", "scope": "checkpoint-only-not-live-qualified",
            "mission": mission["name"], "mode": mode, "killCount": count,
            "safeReturnedClaimed": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        mission, route, _ = mission_cli.load_definition(
            args.mission, args.route, args.profile)
        progress = mission_cli._load_json(args.checkpoint, 2 * 1024 * 1024,
                                          "mission checkpoint")
        result = audit(mission, route, progress)
        code = 0
    except (mission_cli.MissionError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "blocked", "scope": "checkpoint-only-not-live-qualified",
                  "reason": str(exc)}
        code = 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
