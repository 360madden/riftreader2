"""Offline SHA-pinned replay of composite physical player-state receipts.

No process access, game input or desktop interaction. Native values are
candidate evidence, not Lua-verified or automatically fresh gameplay state.
"""
from __future__ import annotations

import argparse
import json
import math
import ntpath
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import collect_physical_player_state as state
from scripts import compare_physical_player_context_pair as context
from scripts.physical_rift import _native_values, _utc_tick_order_key, valid_host_name


def require(ok, reason):
    if not ok:
        raise ValueError("physical-state-replay-" + reason)


def _health_candidate(entry):
    """Raw HP candidate only when a recorded sample actually calculated one."""
    current = entry.get("current") if isinstance(entry, dict) else None
    return (current if isinstance(entry, dict)
            and entry.get("status") == "calculated-candidate"
            and type(current) is int and current >= 0 else None)


def verified_state(filename):
    filename = Path(filename)
    receipt, receipt_sha = context.load(filename)
    return verify_receipt(receipt, receipt_sha, filename.parent)


def verify_receipt(receipt, receipt_sha, directory):
    """Validate original sources for both saved replay and prepublication checks."""
    owner = receipt.get("target")
    host = receipt.get("ownerHost")
    build_sha = str(owner.get("executableSha256", "")).upper() if isinstance(owner, dict) else ""
    sources = receipt.get("sources")
    has_zone = (isinstance(sources, dict)
                and ("zone-before" in sources or "zone-after" in sources
                     or "zoneBracketCandidate" in receipt))
    has_power = (isinstance(sources, dict)
                 and ("power" in sources or "player-context-after" in sources
                      or "powerBracketCandidate" in receipt))
    has_experience = isinstance(sources, dict) and "experience-values" in sources
    kinds = state.source_kinds(include_stats=isinstance(sources, dict) and "stats" in sources,
                               include_zone=has_zone, include_power=has_power,
                               include_experience=has_experience)
    require(receipt.get("schemaVersion") == 1
            and receipt.get("evidenceKind") == "amd-physical-player-state-candidate/1"
            and receipt.get("status") == "complete-candidate"
            and valid_host_name(host)
            and isinstance(owner, dict)
            and valid_host_name(owner.get("hostName"))
            and owner["hostName"].casefold() == host.casefold()
            and type(owner.get("processId")) is int and owner["processId"] > 0
            and str(owner.get("processStartUtcTicks", "")).isdecimal()
            and build_sha in state.SUPPORTED_BUILDS
            and isinstance(receipt.get("sources"), dict)
            and set(receipt["sources"]) == set(kinds)
            and isinstance(receipt.get("selfKeyCandidate"), str)
            and receipt["selfKeyCandidate"].isdecimal()
            and int(receipt["selfKeyCandidate"]) > 0,
            "invalid-summary-owner")
    module = (receipt.get("moduleBaseAddress"), receipt.get("moduleSize"))
    require(all(type(v) is int and v > 0 for v in module), "invalid-module")
    values, hashes, health_samples = {}, {}, []
    previous_end, first_time, last_time = None, None, None
    for kind in kinds:
        saved = receipt["sources"][kind]
        read_kind = state.native_kind(kind)
        one_shot = read_kind in state.ONE_SHOT_CONTRACTS
        require(isinstance(saved, dict)
                and type(saved.get("samples")) is int
                and (saved["samples"] == 1 if one_shot
                     else 2 <= saved["samples"] <= 10)
                and isinstance(saved.get("sourceSha256"), str)
                and isinstance(saved.get("path"), str)
                and ntpath.basename(saved["path"]) == kind + ".json",
                kind + "-invalid-source-pin")
        # Resolve fixed local filenames, NOT arbitrary absolute paths from receipts.
        report, actual_sha = context.load(directory / (kind + ".json"),
                                          saved["sourceSha256"])
        # One-shot observations, including experience, carry their own identity.
        if one_shot:
            observation = report.get("observation")
            identity = observation.get("identity") if isinstance(observation, dict) else None
            rows = [observation] if isinstance(observation, dict) else None
        else:
            identity = report.get("identity")
            rows = report.get("samples" if kind == "power" else "observations")
        require(state.source_matches_target(identity, owner)
                and (identity.get("moduleBaseAddress"), identity.get("moduleSize")) == module
                and report.get("status") == "complete"
                and ((one_shot and report.get("contractVersion") ==
                      state.ONE_SHOT_CONTRACTS[read_kind])
                      or (kind == "power" and report.get("contractVersion") == "native-power-samples/1"
                          and report.get("requestedSamples") == saved["samples"])
                      or (not one_shot and kind != "power"
                          and report.get("requestedSamples") == saved["samples"]
                          and report.get("completedSamples") == saved["samples"]))
                and isinstance(rows, list) and len(rows) == saved["samples"]
                 and (report.get("observation") == rows[-1] if kind not in ("position", "power")
                      else report.get("observation") is None),
                kind + "-invalid-source-owner")
        for sample in rows:
            require(isinstance(sample, dict)
                    and (kind in ("position", "power") or sample.get("identity") == identity)
                    and (kind == "power" or
                         str((sample.get("seed") or {}).get("unitKey")
                             if kind == "experience-values" and isinstance(sample.get("seed"), dict)
                             else sample.get("selfKey" if kind.startswith("zone-") else "unitKey"))
                         == receipt["selfKeyCandidate"]),
                    kind + "-sample-owner")
            start = _utc_tick_order_key(sample.get("startedAtUtc"))
            end = _utc_tick_order_key(sample.get("completedAtUtc"))
            require(start <= end and (previous_end is None or previous_end <= start),
                    kind + "-sample-time-order")
            if first_time is None:
                first_time = sample["startedAtUtc"]
            previous_end, last_time = end, sample["completedAtUtc"]
        # A final burst projection can hide a transient HP drop that
        # recovers before the last sample. Keep every pinned candidate.
        if kind == "vitals":
            health_samples = [_health_candidate(_native_values(
                "vitals", {"observation": sample})["health"]) for sample in rows]
        projected = _native_values(state.native_kind(kind), report)
        recorded = saved.get("candidateValues")
        if kind == "vitals" and "unavailableReasonProvenance" in projected and isinstance(recorded, dict):
            # Acquisition context is not part of the native values. A saved receipt
            # may predate this metadata, but can never attest to current acquisition.
            field = "unavailableReasonProvenance"
            if field not in recorded or recorded[field] in (
                    "current-reader-contract-checked", projected[field]):
                recorded = {**recorded, field: projected[field]}
        if kind in ("vitals", "power", "player-context-after", "experience-values") or kind.startswith("zone-"):
            # Ordinary dict equality treats 1, 1.0 and True as interchangeable.
            # Compare typed JSON values regardless of object key order.
            def canonical(value):
                return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            matches = canonical(projected) == canonical(recorded)
        else:
            matches = projected == recorded
        require(matches,
                kind + "-candidate-projection-mismatch")
        if kind == "experience-values":
            require(projected.get("unitKey") == receipt["selfKeyCandidate"],
                    "experience-values-projected-self-key")
        if kind == "vitals" and "burstSummary" in saved:
            burst = saved["burstSummary"]
            require(isinstance(burst, dict)
                    and str(burst.get("sourceReportSha256", "")).upper() == actual_sha
                    and str(burst.get("sourceBuildSha256", "")).upper() == build_sha
                    and burst.get("processId") == owner["processId"]
                    and str(burst.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                    and str(burst.get("unitKey")) == receipt["selfKeyCandidate"]
                    and burst.get("sampleCount") == saved["samples"],
                    "vitals-burst-pin-mismatch")
        values[kind] = projected
        hashes[kind] = {"sha256": actual_sha, "samples": saved["samples"]}
    zone_bracket = None
    if has_zone:
        before, after = values["zone-before"], values["zone-after"]
        require(before["status"] == after["status"] == "available-candidate"
                and isinstance(before.get("zoneIdCandidate"), str)
                and before["zoneIdCandidate"], "zone-candidate-unavailable")
        require(all(before.get(field) == after.get(field)
                    for field in ("selfKey", "rawZoneKey", "childStatus", "childKey", "zoneIdCandidate")),
                "zone-candidates-changed")
        zone_bracket = {"status": "matching-candidates",
                        "rawZoneKey": before["rawZoneKey"],
                        "zoneIdCandidate": before["zoneIdCandidate"],
                        "beforeSourceSha256": hashes["zone-before"]["sha256"],
                        "afterSourceSha256": hashes["zone-after"]["sha256"],
                        "worldInstanceStatus": "unavailable",
                        "qualification": "Matching zone endpoints only; a transient change between samples, "
                                         "independent API agreement and world-instance identity remain unverified."}
        require(json.dumps(receipt.get("zoneBracketCandidate"), sort_keys=True, allow_nan=False)
                == json.dumps(zone_bracket, sort_keys=True, allow_nan=False),
                "zone-bracket-summary-mismatch")
    power_bracket = None
    if has_power:
        power_bracket = state.power_context_bracket(
            values, {k: row["sha256"] for k, row in hashes.items()}, receipt["selfKeyCandidate"])
        require(json.dumps(receipt.get("powerBracketCandidate"), sort_keys=True, allow_nan=False)
                == json.dumps(power_bracket, sort_keys=True, allow_nan=False),
                "power-bracket-summary-mismatch")
    return {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-replay/1",
        "status": "candidate-only", "summarySha256": receipt_sha, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": receipt["selfKeyCandidate"], "sources": hashes,
        **({"zoneBracketCandidate": zone_bracket} if zone_bracket is not None else {}),
        **({"powerBracketCandidate": power_bracket} if power_bracket is not None else {}),
        "firstStartedAtUtc": first_time, "lastCompletedAtUtc": last_time,
        "candidateValues": values, "healthSampleCandidates": health_samples,
        "qualification": "Pinned sequential native replay; not atomic, passive-fresh, Lua-correlated or restart-qualified.",
    }


def _compare_stats(a, b):
    """Compare only raw stat slots with matching selectors in two verified receipts."""
    left = a["candidateValues"].get("stats")
    right = b["candidateValues"].get("stats")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {"status": "not-captured"}
    rows_a, rows_b = left.get("stats"), right.get("stats")
    if (left.get("status") != right.get("status") or
            left.get("status") != "candidate-only" or
            not isinstance(rows_a, list) or not isinstance(rows_b, list) or
            len(rows_a) != len(rows_b) or
            left.get("selectorCount") != right.get("selectorCount") or
            left.get("selectorCount") != len(rows_a) or
            any((x.get("name"), x.get("selector"), x.get("mappedIndex")) !=
                (y.get("name"), y.get("selector"), y.get("mappedIndex"))
                for x, y in zip(rows_a, rows_b))):
        return {"status": "incompatible-selector-layout"}
    changed, compared, unavailable = [], 0, 0
    for old, new in zip(rows_a, rows_b):
        for flavor in ("ordinary", "unbuffed"):
            first, second = old[flavor], new[flavor]
            if (first.get("status") != "raw-candidate" or
                    second.get("status") != "raw-candidate"):
                unavailable += 1
                continue
            before, after = first["rawSigned64"], second["rawSigned64"]
            compared += 1
            if before != after:
                changed.append({"name": old["name"], "variant": flavor,
                                "beforeRawSigned64": before,
                                "afterRawSigned64": after,
                                "rawNumericDifference": after - before})
    return {"status": "comparable-candidate", "selectorCount": len(rows_a),
            "rawValuesCompared": compared, "rawValuesUnavailable": unavailable,
            "rawValuesChanged": len(changed), "changed": changed}


def _power_burst(capture):
    """Summarize the already source-verified Power samples, not inferred regeneration."""
    power = capture["candidateValues"].get("power")
    if power is None:
        return None
    bracket = capture.get("powerBracketCandidate")
    require(isinstance(bracket, dict)
            and bracket.get("status") == "matching-warrior-context-candidates"
            and bracket.get("selfKeyCandidate") == capture["selfKeyCandidate"]
            and bracket.get("nativePowerUnitKeyStatus") == "unavailable",
            "power-context-bracket-unavailable")
    samples = power["samples"]
    currents = [row["current"] for row in samples]
    maxima = [row["maximum"] for row in samples]
    return {
        "status": "context-bracketed-candidate", "recipe": power["recipe"],
        "sampleCount": len(samples),
        "firstCurrentCandidate": currents[0], "lastCurrentCandidate": currents[-1],
        "firstMaximumCandidate": maxima[0], "lastMaximumCandidate": maxima[-1],
        "minimumCurrentCandidate": min(currents), "maximumCurrentCandidate": max(currents),
        "withinBurstCurrentDeltaCandidate": currents[-1] - currents[0],
        "withinBurstChangedPairs": sum(a != b for a, b in zip(currents, currents[1:])),
        "withinBurstMaximumChangedPairs": sum(a != b for a, b in zip(maxima, maxima[1:])),
        "qualification": "Sequential Power samples; no independent unit key, spend or regeneration proof.",
    }


def _compare_power(before, after):
    """Do not bridge a missing capture or compare different Power recipes."""
    a, b = _power_burst(before), _power_burst(after)
    result = {"before": a, "after": b}
    if a is None or b is None:
        return dict(result, status="not-captured" if a is b is None else "partial-candidate")
    if a["recipe"] != b["recipe"]:
        return dict(result, status="incompatible-recipe")
    return dict(result, status="comparable-candidate",
                endpointCurrentDeltaCandidate=b["lastCurrentCandidate"] - a["lastCurrentCandidate"],
                boundaryCurrentDeltaCandidate=b["firstCurrentCandidate"] - a["lastCurrentCandidate"],
                boundaryMaximumDeltaCandidate=b["firstMaximumCandidate"] - a["lastMaximumCandidate"],
                qualification="Numeric differences across a sampling gap; cause and freshness unverified.")


def _power_history(captures, edges):
    """Preserve burst extrema and gaps; never infer a continuous resource trace."""
    bursts = [_power_burst(capture) for capture in captures]
    available = [row for row in bursts if row is not None]
    comparable = [edge["nativePowerComparison"] for edge in edges
                  if edge["nativePowerComparison"]["status"] == "comparable-candidate"]
    complete = len(comparable) == len(edges)
    return {
        "status": ("comparable-candidate" if complete else
                   "partial-candidate" if available else "not-captured"),
        "capturesWithPower": len(available),
        "capturesWithoutPower": len(captures) - len(available),
        "sampleCount": sum(row["sampleCount"] for row in available),
        "minimumCurrentCandidate": min((row["minimumCurrentCandidate"] for row in available), default=None),
        "maximumCurrentCandidate": max((row["maximumCurrentCandidate"] for row in available), default=None),
        "withinBurstChangedPairs": sum(row["withinBurstChangedPairs"] for row in available),
        "withinBurstMaximumChangedPairs": sum(row["withinBurstMaximumChangedPairs"] for row in available),
        "comparableSegments": len(comparable),
        "changedBoundaryPairs": sum(row["boundaryCurrentDeltaCandidate"] != 0 for row in comparable),
        "maximumChangedBoundaryPairs": sum(row["boundaryMaximumDeltaCandidate"] != 0 for row in comparable),
        "netEndpointCurrentDeltaCandidate": (
            bursts[-1]["lastCurrentCandidate"] - bursts[0]["lastCurrentCandidate"] if complete else None),
        "qualification": "Sampled numeric candidates only; no continuous trace or inferred regeneration.",
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
        "target": a["target"],
        "beforeCompletedAtUtc": a["lastCompletedAtUtc"],
        "afterStartedAtUtc": b["firstStartedAtUtc"],
        "processId": a["target"]["processId"],
        "selfKeyCandidate": a["selfKeyCandidate"],
        "positionDeltaCandidate": delta,
        "planarDistanceCandidate": math.hypot(delta["x"], delta["z"]),
        "healthDeltaCandidate": health_delta,
        "nativeStatsComparison": _compare_stats(a, b),
        "nativePowerComparison": _compare_power(a, b),
        "qualification": "Same-epoch candidate change only; no movement causation, Lua validation or freshness proof.",
    }


def compare(before, after):
    return _compare_states(verified_state(before), verified_state(after))


def history(summaries):
    """Ordered, same-process trajectory of offline native evidence."""
    require(2 <= len(summaries) <= 24, "history-count-out-of-bounds")
    captures = [verified_state(path) for path in summaries]
    edges = [_compare_states(a, b) for a, b in zip(captures, captures[1:])]
    health_points = [_health_candidate(capture["candidateValues"]["vitals"]["health"])
                     for capture in captures]
    # Include intermediate burst samples, not just each final projected HP.
    # The fallback supports older in-memory verified-state shapes.
    health_samples = [value for capture, endpoint in zip(captures, health_points)
                      for value in capture.get("healthSampleCandidates", [endpoint])]
    available_health_samples = [v for v in health_samples if type(v) is int]
    # An incomplete stat series cannot be reported as unchanged.
    comparable = [(index, row) for index, edge in enumerate(edges, 1)
                  if (row := edge["nativeStatsComparison"])["status"] == "comparable-candidate"]
    complete_stats = (len(comparable) == len(edges) and
                      all(row["rawValuesUnavailable"] == 0 for _, row in comparable))
    stats_history = {
        "status": ("comparable-candidate" if complete_stats else
                   "partial-candidate" if comparable else "not-comparable"),
        "segmentCount": len(edges),
        "comparableSegments": len(comparable),
        "rawValuesCompared": sum(row["rawValuesCompared"] for _, row in comparable),
        "rawValuesUnavailable": sum(row["rawValuesUnavailable"] for _, row in comparable),
        "rawValuesChanged": sum(row["rawValuesChanged"] for _, row in comparable),
        "changed": [{"segmentIndex": index, **change}
                    for index, row in comparable for change in row["changed"]],
    }
    delta = {axis: captures[-1]["candidateValues"]["position"][axis] -
             captures[0]["candidateValues"]["position"][axis]
             for axis in ("x", "y", "z")}
    require(all(type(v) in (int, float) and math.isfinite(v) for v in delta.values()),
            "invalid-history-position-delta")
    return {
        "schemaVersion": 1, "status": "candidate-only",
        "evidenceKind": "amd-physical-player-state-history/1",
        "target": captures[0]["target"],
        "processId": captures[0]["target"]["processId"],
        "selfKeyCandidate": captures[0]["selfKeyCandidate"],
        "captureCount": len(captures),
        "summarySha256s": [capture["summarySha256"] for capture in captures],
        "firstStartedAtUtc": captures[0]["firstStartedAtUtc"],
        "lastCompletedAtUtc": captures[-1]["lastCompletedAtUtc"],
        "nativeStatsHistory": stats_history,
        "nativePowerHistory": _power_history(captures, edges),
        "segments": [{
            "beforeSummarySha256": edge["beforeSummarySha256"],
            "afterSummarySha256": edge["afterSummarySha256"],
            "beforeCompletedAtUtc": edge["beforeCompletedAtUtc"],
            "afterStartedAtUtc": edge["afterStartedAtUtc"],
            "positionDeltaCandidate": edge["positionDeltaCandidate"],
            "planarDistanceCandidate": edge["planarDistanceCandidate"],
            "healthDeltaCandidate": edge["healthDeltaCandidate"],
            "nativeStatsComparison": edge["nativeStatsComparison"],
            "nativePowerComparison": edge["nativePowerComparison"],
        } for edge in edges],
        "sumPlanarChordsCandidate": sum(e["planarDistanceCandidate"] for e in edges),
        "netPositionDeltaCandidate": delta,
        "healthObservedCount": sum(h is not None for h in health_points),
        "healthMinCandidate": min((h for h in health_points if h is not None), default=None),
        "healthMaxCandidate": max((h for h in health_points if h is not None), default=None),
        "healthSampleCount": len(health_samples),
        "healthSamplesObservedCount": len(available_health_samples),
        "healthSamplesMinCandidate": min(available_health_samples, default=None),
        "healthSamplesMaxCandidate": max(available_health_samples, default=None),
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
    brief = {"status": result["status"], "evidenceKind": result["evidenceKind"],
             "target": result["target"]}
    if "sources" in result:
        brief.update(summarySha256=result["summarySha256"],
                     sourceCount=len(result["sources"]),
                     firstStartedAtUtc=result["firstStartedAtUtc"],
                     lastCompletedAtUtc=result["lastCompletedAtUtc"])
        if "power" in result["candidateValues"]:
            brief["nativePowerCandidate"] = _power_burst(result)
        if "experience-values" in result["candidateValues"]:
            brief["nativeExperienceCandidate"] = result["candidateValues"]["experience-values"]
    elif "segments" in result:
        brief.update(captureCount=result["captureCount"],
                     firstStartedAtUtc=result["firstStartedAtUtc"],
                     lastCompletedAtUtc=result["lastCompletedAtUtc"],
                     sumPlanarChordsCandidate=result["sumPlanarChordsCandidate"],
                     netPositionDeltaCandidate=result["netPositionDeltaCandidate"],
                     healthObservedCount=result["healthObservedCount"],
                      healthSampleCount=result["healthSampleCount"],
                      healthSamplesObservedCount=result["healthSamplesObservedCount"],
                      healthSamplesMinCandidate=result["healthSamplesMinCandidate"],
                      healthSamplesMaxCandidate=result["healthSamplesMaxCandidate"],
                      nativeStatsHistory={k: v for k, v in result["nativeStatsHistory"].items()
                                          if k != "changed"})
        if "nativePowerHistory" in result:
            brief["nativePowerHistory"] = result["nativePowerHistory"]
    else:
        brief.update(beforeCompletedAtUtc=result["beforeCompletedAtUtc"],
                     afterStartedAtUtc=result["afterStartedAtUtc"],
                     positionDeltaCandidate=result["positionDeltaCandidate"],
                     planarDistanceCandidate=result["planarDistanceCandidate"],
                     healthDeltaCandidate=result["healthDeltaCandidate"],
                     nativeStatsComparison=result["nativeStatsComparison"])
        if "nativePowerComparison" in result:
            brief["nativePowerComparison"] = result["nativePowerComparison"]
    if args.output:
        brief["output"] = str(args.output)
    print(json.dumps(brief, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
