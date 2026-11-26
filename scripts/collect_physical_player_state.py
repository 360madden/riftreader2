"""One no-input physical RIFT state read using existing native readers.

Independent context, XYZ and vitals readings share an exact host/process/module/self
owner. Optional zone reads bracket that acquisition, refusing changed/unavailable
native zone IDs. Not an atomic snapshot, live Lua reference or qualified gameplay telemetry.
"""
from __future__ import annotations
import argparse
import json
import ntpath
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import physical_rift
from scripts import compare_physical_player_context_pair as context
from scripts.compare_physical_player_context_pair import BUILD_SHA

SUPPORTED_BUILDS = frozenset((BUILD_SHA,
    "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"))
KINDS = ("player-context", "position", "vitals")
ONE_SHOT_CONTRACTS = {
    "stats": "native-current-stats-candidate/1",
    "zone-context": "native-current-zone-seed-candidate/1",
    "experience-values": "native-current-experience-values-candidate/1",
}


def source_kinds(*, include_stats, include_zone, include_power, include_experience=False):
    """Shared acquisition/replay ordering for optional source groups."""
    return ((("zone-before",) if include_zone else ()) + KINDS
            + (("stats",) if include_stats else ())
            + (("experience-values",) if include_experience else ())
            + (("power", "player-context-after") if include_power else ())
            + (("zone-after",) if include_zone else ()))


def native_kind(kind):
    if kind.startswith("zone-"):
        return "zone-context"
    return "player-context" if kind == "player-context-after" else kind


def power_context_bracket(values, hashes, self_key):
    """Attribute the process-scoped candidate to matching surrounding context only."""
    before, after = (values[name] for name in ("player-context", "player-context-after"))
    require(all(row.get("unitKey") == self_key
                and row.get("calling", {}).get("nameCandidate") == "warrior"
                for row in (before, after)), "power-player-context-mismatch")
    return {"status": "matching-warrior-context-candidates",
            "selfKeyCandidate": self_key,
            "nativePowerUnitKeyStatus": "unavailable",
            "beforeContextSha256": hashes["player-context"],
            "powerSourceSha256": hashes["power"],
            "afterContextSha256": hashes["player-context-after"],
            "qualification": "Matching sequential player context, not an independent Power unit key."}


def require(ok, reason):
    if not ok:
        raise ValueError("physical-player-state-" + reason)


def source_matches_target(identity, target):
    """Match the executable recorded by the Windows process reader."""
    if not isinstance(identity, dict):
        return False
    source_path = identity.get("executablePath")
    target_path = target.get("executablePath")
    return (isinstance(source_path, str) and bool(source_path)
            and isinstance(target_path, str) and bool(target_path)
            and ntpath.normcase(source_path) == ntpath.normcase(target_path)
            and type(identity.get("processId")) is int
            and identity["processId"] == target["processId"]
            and str(identity.get("processStartUtcTicks")) == target["processStartUtcTicks"]
            and str(identity.get("executableSha256", "")).upper() ==
                str(target["executableSha256"]).upper())


def pin(pid, *, expected_host=None):
    host = socket.gethostname()
    require(physical_rift.valid_host_name(host)
            and (expected_host is None or (physical_rift.valid_host_name(expected_host)
                 and expected_host.casefold() == host.casefold())), "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    selection = physical_rift.select_physical(host, pid)
    target = selection.get("target")
    require(selection.get("status") == "ready"
            and selection.get("ownerHost") == host and isinstance(target, dict)
            and str(target.get("hostName", "")).casefold() == host.casefold()
            and target.get("processId") == pid
            and str(target.get("processStartUtcTicks", "")).isdecimal()
            and str(target.get("executableSha256", "")).upper() in SUPPORTED_BUILDS
            and type(target.get("hwnd")) is int and target["hwnd"] > 0,
            "physical-process-identity-unavailable")
    return selection


def collect(pid, output_dir, *, samples=3, interval_ms=200, include_stats=False,
            include_zone=False, include_power=False, include_experience=False,
            expected_host=None, native_reader=None):
    require(type(samples) is int and 2 <= samples <= 10
            and type(interval_ms) is int and 0 <= interval_ms <= 1000
            and type(include_stats) is bool and type(include_zone) is bool
            and type(include_power) is bool and type(include_experience) is bool,
            "invalid-sampling-bounds")
    read = physical_rift.bind_native_reader(physical_rift.read_native, native_reader)
    first = pin(pid, expected_host=expected_host)
    owner = first["target"]
    host = owner["hostName"]
    build_sha = str(owner["executableSha256"]).upper()
    require(not include_power or build_sha in physical_rift.POWER_RECIPES,
            "power-build-unsupported")
    # Standalone stats are now separately qualified for both exact builds.
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    require(not output_dir.exists() and output_dir.parent.is_dir(),
            "new-output-directory-required")
    output_dir.mkdir()
    results, module, self_key = {}, None, None
    kinds = source_kinds(include_stats=include_stats, include_zone=include_zone,
                         include_power=include_power, include_experience=include_experience)
    for kind in kinds:
        require(pin(pid, expected_host=host)["target"] == owner, "epoch-changed-before-read")
        path = output_dir / (kind + ".json")
        read_kind = native_kind(kind)
        # One-shot sources carry a single observation, not a burst envelope.
        options = ({} if read_kind in ONE_SHOT_CONTRACTS else
                   {"samples": samples, "interval_ms": interval_ms})
        result = read(first, read_kind, path, **options)
        require(result.get("status") == "complete"
                and result.get("nativeRead") == read_kind
                and result.get("target") == owner
                and Path(result.get("nativeOutput", "")) == path,
                kind + "-read-unavailable")
        require(path.is_file() and not path.is_symlink()
                and 0 < path.stat().st_size <= 8_000_000,
                kind + "-source-unavailable")
        # Use the same duplicate-key/nonfinite-rejecting source parser as replay.
        # Never publish a receipt that a subsequent independent replay must refuse.
        report, source_sha = context.load(path)
        observation = report.get("observation")
        identity = (observation.get("identity") if read_kind in ONE_SHOT_CONTRACTS
                    and isinstance(observation, dict) else report.get("identity"))
        require(source_matches_target(identity, owner)
                and type(identity.get("moduleBaseAddress")) is int
                and type(identity.get("moduleSize")) is int
                and identity["moduleBaseAddress"] > 0 and identity["moduleSize"] > 0
                and report.get("status") == "complete"
                and ((read_kind in ONE_SHOT_CONTRACTS
                      and report.get("contractVersion") == ONE_SHOT_CONTRACTS[read_kind]
                      and isinstance(observation, dict)
                      and result.get("nativeSourceSha256", "").upper() == source_sha)
                      or (read_kind == "power"
                          and report.get("contractVersion") == "native-power-samples/1"
                          and report.get("requestedSamples") == samples
                          and result.get("nativeSourceSha256", "").upper() == source_sha)
                      or (read_kind not in ONE_SHOT_CONTRACTS and read_kind != "power"
                          and report.get("completedSamples") == samples)),
                kind + "-source-identity-invalid")
        current_module = (identity["moduleBaseAddress"], identity["moduleSize"])
        if module is None:
            module = current_module
        require(current_module == module, "module-owner-changed")
        values = result.get("nativeValues")
        if read_kind == "power":
            require(physical_rift._native_values("power", report) == values,
                    "power-native-values-mismatch")
        else:
            unit_key = (values.get("selfKey") if read_kind == "zone-context" else values.get("unitKey")) \
                if isinstance(values, dict) else None
            require(isinstance(unit_key, str) and unit_key.isdecimal() and int(unit_key) > 0,
                    kind + "-self-key-unavailable")
            if self_key is None:
                self_key = unit_key
            require(unit_key == self_key, "self-key-changed")
        if read_kind == "zone-context":
            require(observation.get("selfKey") == int(unit_key)
                    and observation.get("rawZoneKey") == values.get("rawZoneKey")
                    and observation.get("zoneIdCandidate") == values.get("zoneIdCandidate"),
                    kind + "-native-zone-values-mismatch")
        if read_kind == "experience-values":
            # The seed carries an independent self key and a source-bound identity.
            # Reproject instead of trusting the wrapper's reported XP arithmetic.
            require(json.dumps(physical_rift._native_values(read_kind, report),
                               sort_keys=True, allow_nan=False)
                    == json.dumps(values, sort_keys=True, allow_nan=False),
                    "experience-values-native-projection-mismatch")
        if kind == "vitals" and "nativeBurstSummary" in result:
            burst = result["nativeBurstSummary"]
            require(isinstance(burst, dict)
                    and str(burst.get("sourceReportSha256", "")).upper() == source_sha
                    and str(burst.get("sourceBuildSha256", "")).upper() == build_sha
                    and burst.get("processId") == pid
                    and str(burst.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                    and str(burst.get("unitKey")) == self_key
                    and burst.get("sampleCount") == samples,
                    "vitals-burst-source-mismatch")
        require(pin(pid, expected_host=host)["target"] == owner, "epoch-changed-after-read")
        results[kind] = {
            "path": str(path), "sourceSha256": source_sha,
            "samples": 1 if read_kind in ONE_SHOT_CONTRACTS else samples,
            "candidateValues": values,
            **({"burstSummary": result["nativeBurstSummary"]}
               if "nativeBurstSummary" in result else {}),
        }
    zone_bracket = None
    if include_zone:
        before = results["zone-before"]["candidateValues"]
        after = results["zone-after"]["candidateValues"]
        require(before.get("status") == after.get("status") == "available-candidate"
                and isinstance(before.get("zoneIdCandidate"), str)
                and before["zoneIdCandidate"], "zone-candidate-unavailable")
        require(all(before.get(field) == after.get(field)
                    for field in ("selfKey", "rawZoneKey", "childStatus", "childKey", "zoneIdCandidate")),
                "zone-changed-during-collection")
        require(physical_rift._utc_tick_order_key(before["sampledAtUtc"])
                <= physical_rift._utc_tick_order_key(after["startedAtUtc"]),
                "zone-bracket-time-invalid")
        zone_bracket = {"status": "matching-candidates", "rawZoneKey": before["rawZoneKey"],
                        "zoneIdCandidate": before["zoneIdCandidate"],
                        "beforeSourceSha256": results["zone-before"]["sourceSha256"],
                        "afterSourceSha256": results["zone-after"]["sourceSha256"],
                        "worldInstanceStatus": "unavailable",
                        "qualification": "Matching zone endpoints only; a transient change between samples, "
                                         "independent API agreement and world-instance identity remain unverified."}
    power_bracket = (power_context_bracket(
        {k: v["candidateValues"] for k, v in results.items()},
        {k: v["sourceSha256"] for k, v in results.items()}, self_key)
        if include_power else None)
    # Preserve the historical evidenceKind token for existing bundle consumers.
    summary = {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-candidate/1",
        "status": "complete-candidate", "ownerHost": host, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": self_key, "sources": results,
        **({"zoneBracketCandidate": zone_bracket} if zone_bracket is not None else {}),
        **({"powerBracketCandidate": power_bracket} if power_bracket is not None else {}),
        "qualification": ("Sequential read-only exact-PID/epoch/build/module/self-key "
                          "candidate correlation; NOT atomic, passive-fresh, independently "
                          "Lua-qualified, changed-state or restart-qualified."
                          + (" Power is process-scoped and context-bracketed, not independently unit-keyed."
                             if include_power else "")),
    }
    if include_power or include_experience:
        # Run the same strict offline verification before publishing the new bundle.
        from scripts.replay_physical_player_state import verify_receipt
        verify_receipt(summary, None, output_dir)
    destination = output_dir / "summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")
    return destination, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--expected-host", help="require this local Windows hostname")
    parser.add_argument("--native-reader", type=Path, help="absolute path to a local published reader")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=200)
    parser.add_argument("--include-stats", action="store_true",
                        help="also acquire one source-pinned 20-stat native candidate snapshot")
    parser.add_argument("--include-zone", action="store_true",
                        help="bracket all other reads with two guarded native zone candidates")
    parser.add_argument("--include-power", action="store_true",
                        help="also acquire supported Warrior Power and recheck player context")
    parser.add_argument("--include-experience", action="store_true",
                        help="also acquire source-pinned native experience candidates")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-state-" + uuid.uuid4().hex))
    args = parser.parse_args(argv)
    try:
        path, report = collect(args.physical_pid, args.output_dir,
                               samples=args.samples, interval_ms=args.interval_ms,
                               include_stats=args.include_stats, include_zone=args.include_zone,
                                include_power=args.include_power,
                                include_experience=args.include_experience,
                               expected_host=args.expected_host, native_reader=args.native_reader)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}))
        return 2
    # Expose the already collected, source-hashed native candidates directly to
    # headless callers. These projections are not independently qualified values.
    values = {kind: source["candidateValues"] for kind, source in report["sources"].items()}
    player = values["player-context"]
    position = values["position"]
    vitals = values["vitals"]
    print(json.dumps({
        "status": report["status"], "summary": str(path),
        "processId": report["target"]["processId"],
        "processStartUtcTicks": report["target"]["processStartUtcTicks"],
        "gameBuildSha256": report["target"]["executableSha256"],
        "selfKeyCandidate": report["selfKeyCandidate"],
        "playerContextCandidate": {k: player.get(k) for k in ("level", "calling", "combat", "target")},
        "positionCandidate": {k: position.get(k) for k in ("x", "y", "z", "refreshGuardStatus")},
        "vitalsCandidate": {
            **{k: vitals.get(k) for k in ("health", "mana", "energy")},
            **{k: vitals[k] for k in ("resourceKindCandidate", "resourceKindSamplesCandidate")
               if k in vitals},
        },
        **({"statsCandidate": values["stats"]} if "stats" in values else {}),
        **({"experienceCandidate": values["experience-values"]}
           if "experience-values" in values else {}),
        **({"powerCandidate": values["power"], "powerBracketCandidate": report["powerBracketCandidate"]}
           if "power" in values else {}),
        **({"zoneBracketCandidate": report["zoneBracketCandidate"]}
           if "zoneBracketCandidate" in report else {}),
        "sources": {k: v["sourceSha256"] for k, v in report["sources"].items()},
        "qualification": report["qualification"],
    }, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
