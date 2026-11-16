#!/usr/bin/env python3
"""Summarize retained survival-route and optional combat telemetry evidence.

This is an offline verifier.  It never opens RIFT, reads process memory, or sends
input.  Missing evidence remains explicitly unavailable rather than inferred.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
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
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _native_health_number(health, field):
    # An unavailable native candidate can still carry a cached numeric slot.
    # Declared availability and source status take precedence over that number.
    if ("available" in health and health["available"] is not True
            or "status" in health and health["status"] != "calculated-candidate"):
        return None
    return _number(health.get(field))


def _native_health_pair(health):
    """Reject unusable native HP before damage or snapshot comparisons."""
    current = _native_health_number(health, "current")
    maximum = _native_health_number(health, "maximum")
    if (current is None or maximum is None or maximum <= 0
            or not 0 <= current <= maximum):
        return None
    return current, maximum


def _native_snapshot_health_pair(native_health, snapshot):
    """Compare two retained HP candidates, without assuming atomic acquisition."""
    native_pair = _native_health_pair(native_health)
    native_current, native_maximum = native_pair if native_pair is not None else (None, None)
    snapshot_current = _number(snapshot.get("health"))
    snapshot_maximum = _number(snapshot.get("healthMax"))
    if any(value is None for value in (
            native_current, native_maximum, snapshot_current, snapshot_maximum)):
        return None
    if (native_maximum <= 0 or snapshot_maximum <= 0
            or not 0 <= native_current <= native_maximum
            or not 0 <= snapshot_current <= snapshot_maximum):
        return None
    return {"nativeCurrent": native_current, "snapshotCurrent": snapshot_current,
            "nativeMaximum": native_maximum, "snapshotMaximum": snapshot_maximum,
            "nativeMinusSnapshotCurrent": native_current - snapshot_current,
            "nativeMinusSnapshotMaximum": native_maximum - snapshot_maximum}


def _utc_seconds(value):
    """Parse an offset-aware native acquisition receipt; never infer a zone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return _number(stamp.timestamp())
    except (ValueError, OverflowError):
        return None


def _native_wrapper_timing(samples):
    """Measure only the native timestamp relative to its retained wrapper.

    Neither the addon frame game clock nor Lua sequence supplies a UTC capture
    timestamp, so these gaps cannot establish addon sampling latency.
    """
    gaps = []
    for sample in samples:
        wall = _number(sample.get("wallTime"))
        native = _utc_seconds(sample.get("nativeSampledAtUtc"))
        # wallTime is a Unix UTC timestamp in the physical capture wrapper;
        # some synthetic/historical fixtures instead use game-clock seconds.
        if (wall is None or native is None
                or wall < 1_000_000_000 or native < 1_000_000_000):
            continue
        gaps.append(wall - native)
    return {
        "scope": "native-utc-vs-wrapper-utc-only",
        "comparableWrappers": len(gaps),
        "unavailableWrappers": len(samples) - len(gaps),
        "nativeAfterWrapperCount": sum(gap < 0 for gap in gaps),
        "minimumSeconds": min(gaps, default=None),
        "maximumSeconds": max(gaps, default=None),
    }


def _host_read_timing(samples):
    """Compare native sample UTC with host read-call bounds, not Lua frame age."""
    result = {
        "scope": "host-read-window-only-not-addon-producer-time",
        "comparableSamples": 0, "missingHostWindows": 0,
        "invalidHostWindows": 0, "missingNativeSamples": 0,
        "nativeAfterHostReadCount": 0, "nativeInsideHostReadCount": 0,
        "nativeBeforeHostReadCount": 0,
        "minimumNativeAfterReadSeconds": None,
        "maximumNativeAfterReadSeconds": None,
    }
    gaps = []
    for sample in samples:
        window = sample.get("hostReadWindow")
        if not isinstance(window, dict):
            result["missingHostWindows"] += 1
            continue
        start = _utc_seconds(window.get("hostReadStartedUtc"))
        end = _utc_seconds(window.get("hostReadCompletedUtc"))
        if (window.get("utcTimingScope") != "host-read-window-not-lua-production-time"
                or start is None or end is None or start > end):
            result["invalidHostWindows"] += 1
            continue
        native = _utc_seconds(sample.get("nativeSampledAtUtc"))
        if native is None:
            result["missingNativeSamples"] += 1
            continue
        result["comparableSamples"] += 1
        if native < start:
            result["nativeBeforeHostReadCount"] += 1
        elif native < end:
            result["nativeInsideHostReadCount"] += 1
        else:
            result["nativeAfterHostReadCount"] += 1
            gaps.append(native - end)
    result["minimumNativeAfterReadSeconds"] = min(gaps, default=None)
    result["maximumNativeAfterReadSeconds"] = max(gaps, default=None)
    return result


def _repeated_frame_evidence(samples):
    """Detect native changes during a repeated addon frame, not their cause."""
    output = {
        "scope": "adjacent-same-owner-retained-wrappers-only",
        "repeatedFrameIntervals": 0,
        "nativeChangedWhileRepeated": {"player": 0, "selectedTarget": 0},
        "firstNativeChange": None,
    }
    for before, after in zip(samples, samples[1:]):
        # A repeated sequence alone is insufficient: require the same producer,
        # player/selected target, and identical game-clock frame.
        if not (all(isinstance(before.get(key), str) and before[key]
                    and _same(before[key], after.get(key))
                    for key in ("sessionId", "playerId", "targetId"))
                and type(before.get("epoch")) is int
                and before["epoch"] == after.get("epoch")
                and type(before.get("sequence")) is int
                and before["sequence"] >= 0
                and before["sequence"] == after.get("sequence")
                and before.get("clock") is not None
                and before["clock"] == after.get("clock")):
            continue
        earlier_wall = _number(before.get("wallTime"))
        later_wall = _number(after.get("wallTime"))
        if (earlier_wall is None or later_wall is None
                or later_wall <= earlier_wall):
            continue
        output["repeatedFrameIntervals"] += 1
        earlier_native = _utc_seconds(before.get("nativeSampledAtUtc"))
        later_native = _utc_seconds(after.get("nativeSampledAtUtc"))
        if (earlier_native is None or later_native is None
                or later_native <= earlier_native):
            continue
        changes = {}
        for key, field in (("player", "nativeSnapshotPlayer"),
                           ("selectedTarget", "nativeSnapshotTarget")):
            old, new = before.get(field), after.get(field)
            if (old is None or new is None
                    or old["snapshotCurrent"] != new["snapshotCurrent"]
                    or old["snapshotMaximum"] != new["snapshotMaximum"]
                    or old["nativeMaximum"] != new["nativeMaximum"]
                    or old["nativeCurrent"] == new["nativeCurrent"]):
                continue
            output["nativeChangedWhileRepeated"][key] += 1
            changes[key] = {
                "nativeBefore": old["nativeCurrent"],
                "nativeAfter": new["nativeCurrent"],
                "snapshotCurrent": new["snapshotCurrent"],
            }
        if changes and output["firstNativeChange"] is None:
            output["firstNativeChange"] = {
                "sequence": after["sequence"], "frameTime": after["clock"],
                "wrapperGapSeconds": later_wall - earlier_wall,
                "nativeCaptureGapSeconds": later_native - earlier_native,
                "changes": changes,
            }
    return output



def _adjacent_frame_hp_candidates(samples, field):
    """Find exact adjacent addon HP values; not a causal or live-latency claim.

    Both frames must belong to the same player/target producer and have
    strictly advancing addon, wrapper and native acquisition timestamps.
    A repeated frame is handled separately by _repeated_frame_evidence.
    """
    result = {
        "scope": "same-owner-advancing-adjacent-frames-candidate-only",
        "priorSnapshotMatches": 0, "nextSnapshotMatches": 0,
        "ambiguousMatches": 0, "firstMatch": None,
    }
    for index, sample in enumerate(samples):
        pair = sample.get(field)
        if (pair is None or pair["nativeMinusSnapshotCurrent"] == 0
                or pair["nativeMinusSnapshotMaximum"] != 0):
            continue
        matches = []
        for direction, other_index in (("prior", index - 1), ("next", index + 1)):
            if not 0 <= other_index < len(samples):
                continue
            adjacent = samples[other_index]
            other_pair = adjacent.get(field)
            if (other_pair is None
                    or other_pair["snapshotMaximum"] != pair["nativeMaximum"]
                    or other_pair["snapshotCurrent"] != pair["nativeCurrent"]):
                continue
            if not all(isinstance(sample.get(key), str) and sample[key]
                       and _same(sample[key], adjacent.get(key))
                       for key in ("sessionId", "playerId", "targetId")):
                continue
            if (type(sample.get("epoch")) is not int
                    or sample["epoch"] != adjacent.get("epoch")):
                continue
            earlier, later = ((adjacent, sample) if direction == "prior"
                              else (sample, adjacent))
            if (type(earlier.get("sequence")) is not int
                    or type(later.get("sequence")) is not int
                    or earlier["sequence"] < 0
                    or earlier["sequence"] >= later["sequence"]):
                continue
            early_clock, late_clock = _number(earlier.get("clock")), _number(later.get("clock"))
            early_wall, late_wall = _number(earlier.get("wallTime")), _number(later.get("wallTime"))
            early_native = _utc_seconds(earlier.get("nativeSampledAtUtc"))
            late_native = _utc_seconds(later.get("nativeSampledAtUtc"))
            if (any(value is None for value in
                    (early_clock, late_clock, early_wall, late_wall,
                     early_native, late_native))
                    or early_clock >= late_clock or early_wall >= late_wall
                    or early_native >= late_native):
                continue
            matches.append((direction, adjacent["sequence"], late_native - early_native))
        if not matches:
            continue
        if len(matches) > 1:
            result["ambiguousMatches"] += 1
            direction, neighbor_sequence, gap = "ambiguous", None, None
        else:
            direction, neighbor_sequence, gap = matches[0]
            result[direction + "SnapshotMatches"] += 1
        if result["firstMatch"] is None:
            result["firstMatch"] = {
                "direction": direction, "sequence": sample["sequence"],
                "matchedSequence": neighbor_sequence,
                "nativeCurrent": pair["nativeCurrent"],
                "snapshotCurrent": pair["snapshotCurrent"],
                "nativeCaptureGapSeconds": gap,
            }
    return result


def _health_concordance(samples):
    """Surface same-wrapper native/addon disagreements, never live qualification."""
    output = {"status": "unavailable", "scope": "retained-wrapper-candidates-only"}
    any_comparison, any_mismatch = False, False
    for key, field in (("player", "nativeSnapshotPlayer"),
                       ("selectedTarget", "nativeSnapshotTarget")):
        pairs = [(sample, sample[field]) for sample in samples
                 if sample.get(field) is not None]
        mismatches = [(sample, pair) for sample, pair in pairs
                      if pair["nativeMinusSnapshotCurrent"] != 0
                      or pair["nativeMinusSnapshotMaximum"] != 0]
        first = mismatches[0] if mismatches else None
        output[key] = {
            "comparableSamples": len(pairs),
            "matchingSamples": len(pairs) - len(mismatches),
            "mismatchedSamples": len(mismatches),
            "nativeHigherCurrentMismatches": sum(
                pair["nativeMinusSnapshotCurrent"] > 0 for _, pair in mismatches),
            "nativeLowerCurrentMismatches": sum(
                pair["nativeMinusSnapshotCurrent"] < 0 for _, pair in mismatches),
            "adjacentFrameValueCandidates": _adjacent_frame_hp_candidates(samples, field),
            "largestAbsoluteCurrentGap": max(
                (abs(pair["nativeMinusSnapshotCurrent"]) for _, pair in pairs),
                default=None),
            "firstMismatch": ({
                "sequence": first[0]["sequence"], "clock": first[0]["clock"],
                **first[1]} if first else None),
        }
        any_comparison |= bool(pairs)
        any_mismatch |= bool(mismatches)
    output["repeatedFrameEvidence"] = _repeated_frame_evidence(samples)
    output["nativeToWrapperTiming"] = _native_wrapper_timing(samples)
    output["hostReadTiming"] = _host_read_timing(samples)
    if any_mismatch:
        output["status"] = "mismatch-observed"
    elif any_comparison:
        output["status"] = "comparison-only"
    return output


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
    self_pair = _native_health_pair(health)
    target_pair = _native_health_pair(target_health)
    self_current, self_maximum = self_pair if self_pair is not None else (None, None)
    target_current, target_maximum = target_pair if target_pair is not None else (None, None)
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
        "nativeSampledAtUtc": native.get("sampledAtUtc"),
        "hostReadWindow": (report.get("acquisition")
                           if isinstance(report.get("acquisition"), dict) else None),
        "sequence": snapshot.get("sequence", report.get("sequence")),
        "epoch": snapshot.get("epoch", report.get("epoch")),
        "sessionId": snapshot.get("sessionId", report.get("sessionId")),
        "playerId": player_id, "targetId": target_id,
        "selfCurrent": self_current, "selfMaximum": self_maximum,
        "selfBasis": self_basis,
        "nativeSnapshotPlayer": _native_snapshot_health_pair(health, raw_player),
        "nativeSnapshotTarget": _native_snapshot_health_pair(target_health, raw_target),
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
                           "sessionId": before.get("sessionId"), "epoch": before.get("epoch"),
                           "playerId": before.get("playerId"),
                           "targetId": before.get("targetId"),
                           "attributionEligible": context_stable})
    return result


def _events(samples, field, incoming):
    result, seen = [], set()
    for sample in samples:
        event = sample.get(field)
        if not isinstance(event, dict):
            continue
        sequence = event.get("sequence")
        clock = _number(event.get("clock"))
        if clock is None:
            continue
        # Event counters can repeat after a Lua producer restart or a target
        # switch. They identify an event only within its originating context.
        identity = (sample.get("sessionId"), sample.get("epoch"),
                    sample.get("playerId"), sample.get("targetId"),
                    sequence, event.get("clock"), event.get("caster"),
                    event.get("target"))
        # Retained JSON may contain structured/corrupt event identity fields.
        # Reject such events rather than crashing or attributing their damage.
        try:
            if identity in seen:
                continue
        except TypeError:
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
            result.append({"sequence": sequence, "clock": clock,
                           "damage": damage, "abilityName": event.get("abilityName"),
                           "caster": event.get("caster"), "target": event.get("target"),
                           "sessionId": sample.get("sessionId"),
                           "epoch": sample.get("epoch"),
                           "playerId": sample.get("playerId"),
                           "targetId": sample.get("targetId")})
    return result


def _correlation(drops, events):
    if not drops or not events:
        return {"status": "unavailable", "pairedCount": 0}
    paired, consumed = 0, set()
    for drop in drops:
        start, end = drop["startClock"], drop["endClock"]
        if start is None or end is None or not drop["attributionEligible"]:
            continue
        # A single event at a shared sample boundary cannot justify two
        # separate HP declines. Each distinct event supports at most one drop.
        for index, event in enumerate(events):
            if (index not in consumed and event["clock"] is not None
                    and start <= event["clock"] <= end
                    and _same(event.get("sessionId"), drop.get("sessionId"))
                    and type(event.get("epoch")) is int
                    and event["epoch"] == drop.get("epoch")
                    and _same(event.get("playerId"), drop.get("playerId"))
                    and _same(event.get("targetId"), drop.get("targetId"))):
                consumed.add(index)
                paired += 1
                break
    return {"status": "correlated" if paired else "observed-unpaired",
            "pairedCount": paired}


def _verified_release(row):
    """Require a positive release receipt without contradictory held-key data."""
    return (row.get("releaseSucceeded") is True
            and row.get("desktopInputsDown") == []
            and ("allInputsReleased" not in row or row["allInputsReleased"] is True))


def _completion_gate(terminal, receipts, terminal_final):
    """Offline admission only; retained route receipts are not live game proof."""
    if terminal is None:
        reason = "terminal-missing"
    elif not terminal_final:
        reason = "terminal-not-final"
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


def _survival_completion_gate(summary):
    """Strict offline rejoin-route receipt gate, not proof of live gameplay."""
    route = summary["route"]
    telemetry = summary["telemetry"]
    acceptance = summary["acceptance"]
    if route["completionGate"]["status"] != "admitted":
        reason = "route-incomplete"
    elif telemetry["status"] != "observed":
        reason = "telemetry-missing"
    elif not telemetry["continuityVerified"]:
        reason = "producer-discontinuous"
    elif acceptance["stopInvariant"] != "clear-throughout":
        reason = "stop-unverified"
    elif not telemetry["policyStateComplete"]:
        reason = "policy-state-missing"
    else:
        states = telemetry["policyStates"]
        retreats = sum(state == "retreat" and
                       (index == 0 or states[index - 1] != "retreat")
                       for index, state in enumerate(states))
        if retreats != route["encounterInterruptCount"]:
            reason = "encounter-retreat-count-mismatch"
        elif retreats and acceptance["checkpointInvariant"] != "preserved":
            reason = "checkpoint-unverified"
        elif retreats and acceptance["recoveryResumeInvariant"] != "preserved":
            reason = "recovery-unverified"
        else:
            return {"status": "admitted", "reason": "offline-route-and-rejoin-receipts-only"}
    return {"status": "blocked", "reason": reason}


def summarize(route_rows, telemetry_rows=None):
    terminal = next((row for row in reversed(route_rows)
                     if row.get("status") in {
                         "arrived", "stopped", "halted", "blocked", "failed", "refused"}), None)
    progress = next((row for row in reversed(route_rows)
                     if type(row.get("nextWaypoint")) is int
                     or type(row.get("nextIndex")) is int), {})
    interrupted = [row for row in route_rows if row.get("status") == "encounter-interrupted"]
    # Every interruption must carry its own release proof. Otherwise a later
    # successful arrival could hide an earlier encounter with unknown held keys.
    receipts = [row for row in route_rows if row.get("status") == "encounter-interrupted"
                or any(key in row for key in
                       ("releaseSucceeded", "allInputsReleased", "desktopInputsDown"))]
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
            "completionGate": _completion_gate(terminal, receipts, terminal is route_rows[-1]),
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
        summary["route"]["survivalCompletionGate"] = _survival_completion_gate(summary)
        return summary
    samples = [_telemetry_sample(row) for row in telemetry_rows]
    # Retained producer fields can be malformed or reset independently of the
    # game process.  A recovery state sequence proves nothing across a producer
    # restart, repeated frame, or reversed timestamp.  This checks internal
    # progression only; it is NOT nonce binding or live-source authentication.
    def valid_identity(sample):
        return (isinstance(sample["sessionId"], str) and bool(sample["sessionId"])
                and type(sample["epoch"]) is int
                and isinstance(sample["playerId"], str) and bool(sample["playerId"]))
    identity_stable = (bool(samples) and all(map(valid_identity, samples))
                       and all((sample["sessionId"], sample["epoch"], sample["playerId"])
                               == (samples[0]["sessionId"], samples[0]["epoch"],
                                   samples[0]["playerId"]) for sample in samples))
    continuity_verified = (identity_stable and len(samples) >= 2
                           and all(type(sample["sequence"]) is int
                                   and sample["sequence"] >= 0
                                   and sample["clock"] is not None for sample in samples)
                           and all(after["sequence"] > before["sequence"]
                                   and after["clock"] > before["clock"]
                                   for before, after in zip(samples, samples[1:])))
    self_drops, target_drops = _drops(samples, "selfCurrent"), _drops(samples, "targetCurrent")
    incoming, outgoing = _events(samples, "incoming", True), _events(samples, "outgoing", False)
    incoming_correlation = _correlation(self_drops, incoming)
    outgoing_correlation = _correlation(target_drops, outgoing)
    interrupted_checkpoints = [sample["checkpoint"] for sample in samples
                               if sample["policyState"] not in (None, "travel")]
    # Missing or empty checkpoints cannot prove preservation. Compare by value,
    # not set membership: a real policy checkpoint may be a JSON object/list.
    def checkpoint_known(value):
        return (value is not None and type(value) is not bool
                and (not isinstance(value, (str, dict, list, tuple)) or
                     bool(value.strip() if isinstance(value, str) else value)))
    if (not continuity_verified or not interrupted_checkpoints
            or not all(map(checkpoint_known, interrupted_checkpoints))):
        checkpoint_status = "unavailable"
    elif all(type(value) is type(interrupted_checkpoints[0])
             and value == interrupted_checkpoints[0] for value in interrupted_checkpoints):
        checkpoint_status = "preserved"
    else:
        checkpoint_status = "changed-while-interrupted"
    # A missing/non-boolean STOP receipt cannot prove STOP was clear throughout.
    stops = [sample["stopSet"] for sample in samples]
    stop_status = ("unavailable" if not continuity_verified or
                   not all(type(stop) is bool for stop in stops)
                   else "latched-throughout" if all(stops)
                   else "clear-throughout" if not any(stops) else "changed")
    states = [sample["policyState"] for sample in samples if sample["policyState"] is not None]
    condensed = [state for index, state in enumerate(states)
                 if index == 0 or state != states[index - 1]]
    if not continuity_verified or not condensed:
        resume_status = "unavailable"
    elif "retreat" in condensed:
        # Every encounter's retreat must independently rejoin and resume travel.
        # A completed earlier cycle cannot validate a later incomplete one,
        # nor can one rejoin be borrowed across two retreat attempts.
        complete = checkpoint_status == "preserved"
        for retreat, state in enumerate(condensed):
            if state != "retreat":
                continue
            next_retreat = next((index for index in range(retreat + 1, len(condensed))
                                if condensed[index] == "retreat"), len(condensed))
            cycle = condensed[retreat + 1:next_retreat]
            # Require each retreat's *ordered* recovery, rejoin and resumed
            # travel; a later recovery cannot retroactively validate a rejoin.
            try:
                recover = cycle.index("recover")
                rejoin = cycle.index("rejoin")
                travel = cycle.index("travel")
            except ValueError:
                complete = False
                break
            if not recover < rejoin < travel:
                complete = False
                break
        resume_status = "preserved" if complete else "violated"
    else:
        resume_status = "not-exercised"
    summary["telemetry"] = {
        "status": "observed", "sampleCount": len(samples), "identityStable": identity_stable,
        "continuityVerified": continuity_verified,
        "selfHealthDrops": self_drops, "targetHealthDrops": target_drops,
        "nativeSnapshotHealthComparison": _health_concordance(samples),
        "incomingEvents": incoming, "outgoingEvents": outgoing,
        "incomingCorrelation": incoming_correlation,
        "outgoingCorrelation": outgoing_correlation,
        "policyStates": states,
        "policyStateComplete": all(isinstance(sample["policyState"], str)
                                   and bool(sample["policyState"]) for sample in samples),
    }
    summary["acceptance"] = {
        "incomingDamage": identity_stable and incoming_correlation["status"] == "correlated",
        "outgoingDamage": identity_stable and outgoing_correlation["status"] == "correlated",
        "checkpointInvariant": checkpoint_status,
        "recoveryResumeInvariant": resume_status, "stopInvariant": stop_status,
    }
    summary["route"]["survivalCompletionGate"] = _survival_completion_gate(summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True, help="retained survival route JSONL")
    parser.add_argument("--telemetry", type=Path, help="optional retained telemetry wrapper JSONL")
    parser.add_argument("--output", type=Path, help="optional new summary JSON path")
    parser.add_argument("--require-complete-route", action="store_true",
                        help="exit 2 unless final route arrival, all waypoint progress and input releases are evidenced")
    parser.add_argument("--require-survival-route", action="store_true",
                        help="exit 2 unless route, producer, STOP and retreat/rejoin receipts are complete; offline only")
    args = parser.parse_args(argv)
    result = summarize(_rows(args.route), _rows(args.telemetry) if args.telemetry else None)
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if args.output:
        if args.output.exists():
            raise AcceptanceError("output-exists")
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return (2 if ((args.require_complete_route
                  and result["route"]["completionGate"]["status"] != "admitted")
                 or (args.require_survival_route
                     and result["route"]["survivalCompletionGate"]["status"] != "admitted"))
            else 0)


if __name__ == "__main__":
    raise SystemExit(main())
