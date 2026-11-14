#!/usr/bin/env python3
"""Summarize retained survival-route and optional combat telemetry evidence.

This is an offline verifier.  It never opens RIFT, reads process memory, or sends
input.  Missing evidence remains explicitly unavailable rather than inferred.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 20_000


class AcceptanceError(ValueError):
    pass


def _rows(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise AcceptanceError(f"invalid-or-oversized-input:{path}")
    result = []
    with path.open("r", encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            if len(result) >= MAX_ROWS:
                raise AcceptanceError(f"too-many-input-rows:{path}")
            def unique_keys(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise AcceptanceError(f"duplicate-json-key:{path}:{number}:{key}")
                    result[key] = item
                return result
            try:
                value = json.loads(line, object_pairs_hook=unique_keys,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        AcceptanceError("nonfinite-json:" + value)))
            except json.JSONDecodeError as exc:
                raise AcceptanceError(f"invalid-json:{path}:{number}") from exc
            if not isinstance(value, dict):
                raise AcceptanceError(f"non-object-row:{path}:{number}")
            result.append(value)
    if not result:
        raise AcceptanceError(f"empty-input:{path}")
    return result


def _number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else None


def _same(left, right):
    return isinstance(left, str) and isinstance(right, str) and left.casefold() == right.casefold()


def _nested(value, *names):
    for name in names:
        if not isinstance(value, dict):
            return None
        value = value.get(name)
    return value


def _telemetry_sample(row):
    telemetry = row.get("telemetry") if isinstance(row.get("telemetry"), dict) else row
    report = row.get("report") if isinstance(row.get("report"), dict) else row
    snapshot = report.get("snapshot") if isinstance(report.get("snapshot"), dict) else {}
    player = telemetry.get("player") if isinstance(telemetry.get("player"), dict) else {}
    encounter = telemetry.get("encounter") if isinstance(telemetry.get("encounter"), dict) else {}
    raw_player = snapshot.get("player") if isinstance(snapshot.get("player"), dict) else {}
    raw_target = snapshot.get("target") if isinstance(snapshot.get("target"), dict) else {}
    native = (row.get("nativeValues") if isinstance(row.get("nativeValues"), dict)
              else row.get("native") if isinstance(row.get("native"), dict) else {})
    native_player = native.get("player") if isinstance(native.get("player"), dict) else {}
    native_target = native.get("selectedTarget") if isinstance(native.get("selectedTarget"), dict) else {}

    health = native_player.get("health") if isinstance(native_player.get("health"), dict) else {}
    target_health = native_target.get("health") if isinstance(native_target.get("health"), dict) else {}
    self_current = _number(health.get("current"))
    self_maximum = _number(health.get("maximum"))
    target_current = _number(target_health.get("current"))
    target_maximum = _number(target_health.get("maximum"))
    self_basis = "native-absolute" if self_current is not None else None
    target_basis = "native-absolute" if target_current is not None else None
    # A normalized-only wrapper still provides useful percentage trends, but
    # percentages and absolute HP must never form one apparent damage drop.
    if self_current is None:
        self_current, self_maximum = _number(player.get("healthPct")), 100.0
        if self_current is not None:
            self_basis = "telemetry-percent"
    if self_current is None:
        self_current, self_maximum = _number(raw_player.get("health")), _number(raw_player.get("healthMax"))
        if self_current is not None:
            self_basis = "snapshot-absolute"
    if target_current is None:
        target_current, target_maximum = _number(raw_target.get("health")), _number(raw_target.get("healthMax"))
        if target_current is not None:
            target_basis = "snapshot-absolute"

    incoming = snapshot.get("lastIncoming")
    outgoing = snapshot.get("lastPositiveEvent")
    if not isinstance(outgoing, dict) and isinstance(snapshot.get("positiveEvents"), dict):
        candidates = [event for event in snapshot["positiveEvents"].values()
                      if isinstance(event, dict)]
        outgoing = max(candidates, key=lambda event: _number(event.get("clock")) or -1,
                       default=None)
    policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
    player_id = snapshot.get("playerId") or report.get("playerId") or row.get("playerId")
    target_id = snapshot.get("targetId") or row.get("targetId")
    return {
        "clock": _number(snapshot.get("frameTime") if snapshot else report.get("frameTime")),
        "sequence": snapshot.get("sequence", report.get("sequence")),
        "epoch": snapshot.get("epoch", report.get("epoch")),
        "sessionId": snapshot.get("sessionId", report.get("sessionId")),
        "playerId": player_id, "targetId": target_id,
        "selfCurrent": self_current, "selfMaximum": self_maximum,
        "selfBasis": self_basis,
        "targetCurrent": target_current, "targetMaximum": target_maximum,
        "targetBasis": target_basis,
        "combat": player.get("inCombat", _nested(native_player, "combat", "value")),
        "dead": player.get("dead", _nested(health, "dead")),
        "incoming": incoming if isinstance(incoming, dict) else None,
        "outgoing": outgoing if isinstance(outgoing, dict) else None,
        "incomingValidated": encounter.get("incomingDamageObserved"),
        "policyState": policy.get("state", row.get("policyState")),
        "checkpoint": policy.get("checkpoint", row.get("checkpoint")),
        "pendingLeg": policy.get("pendingLeg", row.get("pendingLeg")),
        "stopSet": row.get("stopSet"), "wallTime": row.get("wallTime"),
    }


def _drops(samples, field):
    result = []
    basis_key = "selfBasis" if field == "selfCurrent" else "targetBasis"
    max_key = "selfMaximum" if field == "selfCurrent" else "targetMaximum"
    for before, after in zip(samples, samples[1:]):
        left, right = before.get(field), after.get(field)
        # A change of native/Lua/normalized source or maximum is not evidence
        # of damage. Avoid comparing 18,208 absolute HP with 90 percent.
        if not before.get(basis_key) or before[basis_key] != after.get(basis_key):
            continue
        left_max, right_max = before.get(max_key), after.get(max_key)
        if left_max != right_max and (left_max is not None or right_max is not None):
            continue
        if left is not None and right is not None and right < left:
            # A health decline remains observable, but is not attributable to
            # one selected opponent across an owner/target switch, epoch
            # boundary or replayed/non-advancing telemetry frame.
            context_stable = (
                all(isinstance(before.get(key), str) and before[key]
                    and _same(before[key], after.get(key))
                    for key in ("sessionId", "playerId", "targetId"))
                and type(before.get("epoch")) is int
                and before["epoch"] == after.get("epoch")
                and type(before.get("sequence")) is int
                and type(after.get("sequence")) is int
                and before["sequence"] < after["sequence"]
                and before.get("clock") is not None
                and after.get("clock") is not None
                and before["clock"] < after["clock"])
            result.append({"amount": left - right, "from": left, "to": right,
                           "basis": before[basis_key],
                           "startClock": before.get("clock"), "endClock": after.get("clock"),
                           "attributionEligible": context_stable})
    return result


def _events(samples, field, incoming):
    result, seen = [], set()
    for sample in samples:
        event = sample.get(field)
        if not isinstance(event, dict):
            continue
        sequence = event.get("sequence")
        identity = (sequence, event.get("clock"), event.get("caster"), event.get("target"))
        if identity in seen:
            continue
        seen.add(identity)
        damage = _number(event.get("damage"))
        selected = event.get("selectedTargetId")
        # Do not synthesize a missing event-time selection from the current
        # target, or mistake a heal/diagnostic event for damage.
        exact_selection = (event.get("kind") == "damage"
                           and isinstance(selected, str)
                           and _same(selected, sample.get("targetId")))
        expected = (exact_selection
                    and _same(event.get("caster"), selected)
                    and _same(event.get("target"), sample.get("playerId")) if incoming else
                    exact_selection
                    and _same(event.get("caster"), sample.get("playerId"))
                    and _same(event.get("target"), selected))
        if damage is not None and damage > 0 and expected:
            result.append({"sequence": sequence, "clock": _number(event.get("clock")),
                           "damage": damage, "abilityName": event.get("abilityName"),
                           "caster": event.get("caster"), "target": event.get("target")})
    return result


def _correlation(drops, events):
    if not drops or not events:
        return {"status": "unavailable", "pairedCount": 0}
    paired = 0
    for drop in drops:
        start, end = drop["startClock"], drop["endClock"]
        if start is None or end is None or not drop["attributionEligible"]:
            continue
        # A later event cannot retrospectively explain an earlier health loss.
        if any(event["clock"] is not None and start <= event["clock"] <= end
               for event in events):
            paired += 1
    return {"status": "correlated" if paired else "observed-unpaired",
            "pairedCount": paired}


def _verified_release(row):
    """Require a positive release receipt without contradictory held-key data."""
    return (row.get("releaseSucceeded") is True
            and row.get("desktopInputsDown") == []
            and ("allInputsReleased" not in row or row["allInputsReleased"] is True))


def _completion_gate(terminal, receipts):
    """Offline admission only; retained route receipts are not live game proof."""
    if terminal is None:
        reason = "terminal-missing"
    elif terminal.get("status") != "arrived":
        reason = "terminal-not-arrived"
    elif not _verified_release(terminal):
        reason = "terminal-release-unverified"
    elif any(not _verified_release(receipt) for receipt in receipts):
        reason = "prior-release-unverified"
    elif (type(terminal.get("waypointCount")) is not int
          or terminal["waypointCount"] < 1
          or type(terminal.get("nextWaypoint")) is not int
          or terminal["nextWaypoint"] != terminal["waypointCount"]):
        reason = "incomplete-waypoint-progress"
    else:
        return {"status": "admitted", "reason": "full-arrival-receipts-only"}
    return {"status": "blocked", "reason": reason}


def summarize(route_rows, telemetry_rows=None):
    terminal = next((row for row in reversed(route_rows)
                     if row.get("status") in {
                         "arrived", "stopped", "halted", "blocked", "failed", "refused"}), None)
    progress = next((row for row in reversed(route_rows)
                     if type(row.get("nextWaypoint")) is int
                     or type(row.get("nextIndex")) is int), {})
    interrupted = [row for row in route_rows if row.get("status") == "encounter-interrupted"]
    receipts = [row for row in route_rows if any(
        key in row for key in ("releaseSucceeded", "allInputsReleased", "desktopInputsDown"))]
    release_ok = bool(receipts) and all(_verified_release(row) for row in receipts)
    summary = {
        "version": 1, "kind": "survival-acceptance-summary",
        "route": {
            "rowCount": len(route_rows), "terminalStatus": terminal.get("status") if terminal else None,
            "encounterInterruptCount": len(interrupted),
            "encounterReleaseVerified": bool(interrupted) and all(
                _verified_release(row) for row in interrupted),
            "allRetainedReleasesVerified": release_ok,
            "terminalInputsReleased": bool(terminal and _verified_release(terminal)),
            "completionGate": _completion_gate(terminal, receipts),
            "finalNextIndex": (progress.get("nextWaypoint")
                               if type(progress.get("nextWaypoint")) is int
                               else progress.get("nextIndex")),
        },
        "telemetry": {"status": "unavailable", "sampleCount": 0},
        "acceptance": {"incomingDamage": False, "outgoingDamage": False,
                       "checkpointInvariant": "unavailable",
                       "recoveryResumeInvariant": "unavailable",
                       "stopInvariant": "unavailable"},
    }
    if telemetry_rows is None:
        return summary
    samples = [_telemetry_sample(row) for row in telemetry_rows]
    identities = {(sample["sessionId"], sample["epoch"], sample["playerId"])
                  for sample in samples}
    identity_stable = len(identities) == 1 and None not in next(iter(identities), ())
    self_drops, target_drops = _drops(samples, "selfCurrent"), _drops(samples, "targetCurrent")
    incoming, outgoing = _events(samples, "incoming", True), _events(samples, "outgoing", False)
    incoming_correlation = _correlation(self_drops, incoming)
    outgoing_correlation = _correlation(target_drops, outgoing)
    interrupted_checkpoints = {sample["checkpoint"] for sample in samples
                               if sample["policyState"] not in (None, "travel")}
    checkpoint_status = ("unavailable" if not interrupted_checkpoints else
                         "preserved" if len(interrupted_checkpoints) == 1 else "changed-while-interrupted")
    stops = [sample["stopSet"] for sample in samples if type(sample["stopSet"]) is bool]
    stop_status = ("unavailable" if not stops else "latched-throughout" if all(stops)
                   else "clear-throughout" if not any(stops) else "changed")
    states = [sample["policyState"] for sample in samples if sample["policyState"] is not None]
    condensed = [state for index, state in enumerate(states)
                 if index == 0 or state != states[index - 1]]
    if not condensed:
        resume_status = "unavailable"
    elif "retreat" in condensed:
        retreat = condensed.index("retreat")
        rejoin = next((index for index in range(retreat + 1, len(condensed))
                       if condensed[index] == "rejoin"), None)
        travel = (next((index for index in range(rejoin + 1, len(condensed))
                        if condensed[index] == "travel"), None)
                  if rejoin is not None else None)
        resume_status = ("preserved" if rejoin is not None and travel is not None
                         and checkpoint_status == "preserved" else "violated")
    else:
        resume_status = "not-exercised"
    summary["telemetry"] = {
        "status": "observed", "sampleCount": len(samples), "identityStable": identity_stable,
        "selfHealthDrops": self_drops, "targetHealthDrops": target_drops,
        "incomingEvents": incoming, "outgoingEvents": outgoing,
        "incomingCorrelation": incoming_correlation,
        "outgoingCorrelation": outgoing_correlation,
        "policyStates": states,
    }
    summary["acceptance"] = {
        "incomingDamage": identity_stable and incoming_correlation["status"] == "correlated",
        "outgoingDamage": identity_stable and outgoing_correlation["status"] == "correlated",
        "checkpointInvariant": checkpoint_status,
        "recoveryResumeInvariant": resume_status, "stopInvariant": stop_status,
    }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True, help="retained survival route JSONL")
    parser.add_argument("--telemetry", type=Path, help="optional retained telemetry wrapper JSONL")
    parser.add_argument("--output", type=Path, help="optional new summary JSON path")
    parser.add_argument("--require-complete-route", action="store_true",
                        help="exit 2 unless final route arrival, all waypoint progress and input releases are evidenced")
    args = parser.parse_args(argv)
    result = summarize(_rows(args.route), _rows(args.telemetry) if args.telemetry else None)
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if args.output:
        if args.output.exists():
            raise AcceptanceError("output-exists")
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return (2 if args.require_complete_route
            and result["route"]["completionGate"]["status"] != "admitted" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
