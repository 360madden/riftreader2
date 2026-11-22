"""One no-input physical RIFT state read using existing native readers.

Independent context, XYZ and vitals readings share an exact host/process/module/self
owner. Optional zone reads bracket that acquisition, refusing changed/unavailable
native zone IDs. Not an atomic snapshot, live Lua reference or qualified gameplay telemetry.
"""
from __future__ import annotations
import argparse
import json
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


def require(ok, reason):
    if not ok:
        raise ValueError("physical-player-state-" + reason)


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
            include_zone=False, expected_host=None):
    require(type(samples) is int and 2 <= samples <= 10
            and type(interval_ms) is int and 0 <= interval_ms <= 1000
            and type(include_stats) is bool and type(include_zone) is bool,
            "invalid-sampling-bounds")
    first = pin(pid, expected_host=expected_host)
    owner = first["target"]
    host = owner["hostName"]
    build_sha = str(owner["executableSha256"]).upper()
    # Standalone stats are now separately qualified for both exact builds.
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    require(not output_dir.exists() and output_dir.parent.is_dir(),
            "new-output-directory-required")
    output_dir.mkdir()
    results, module, self_key = {}, None, None
    kinds = (("zone-before",) if include_zone else ()) + KINDS + \
            (("stats",) if include_stats else ()) + (("zone-after",) if include_zone else ())
    for kind in kinds:
        require(pin(pid, expected_host=host)["target"] == owner, "epoch-changed-before-read")
        path = output_dir / (kind + ".json")
        read_kind = "zone-context" if kind.startswith("zone-") else kind
        # Zone and stats are one-shot readers; other sources support bursts.
        options = ({} if read_kind in ("stats", "zone-context") else
                   {"samples": samples, "interval_ms": interval_ms})
        result = physical_rift.read_native(first, read_kind, path, **options)
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
        identity = (observation.get("identity") if read_kind in ("stats", "zone-context")
                    and isinstance(observation, dict) else report.get("identity"))
        require(isinstance(identity, dict)
                and identity.get("processId") == pid
                and str(identity.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                and str(identity.get("executableSha256", "")).upper() == build_sha
                and type(identity.get("moduleBaseAddress")) is int
                and type(identity.get("moduleSize")) is int
                and identity["moduleBaseAddress"] > 0 and identity["moduleSize"] > 0
                and report.get("status") == "complete"
                and ((read_kind == "stats" and report.get("contractVersion") == "native-current-stats-candidate/1"
                      and isinstance(observation, dict)
                      and result.get("nativeSourceSha256", "").upper() == source_sha)
                     or (read_kind == "zone-context"
                         and report.get("contractVersion") == "native-current-zone-seed-candidate/1"
                         and isinstance(observation, dict)
                         and result.get("nativeSourceSha256", "").upper() == source_sha)
                     or (read_kind not in ("stats", "zone-context")
                         and report.get("completedSamples") == samples)),
                kind + "-source-identity-invalid")
        current_module = (identity["moduleBaseAddress"], identity["moduleSize"])
        if module is None:
            module = current_module
        require(current_module == module, "module-owner-changed")
        values = result.get("nativeValues")
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
            "samples": 1 if read_kind in ("stats", "zone-context") else samples,
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
    # Preserve the historical evidenceKind token for existing bundle consumers.
    summary = {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-candidate/1",
        "status": "complete-candidate", "ownerHost": host, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": self_key, "sources": results,
        **({"zoneBracketCandidate": zone_bracket} if zone_bracket is not None else {}),
        "qualification": ("Sequential read-only exact-PID/epoch/build/module/self-key "
                          "candidate correlation; NOT atomic, passive-fresh, independently "
                          "Lua-qualified, changed-state or restart-qualified."),
    }
    destination = output_dir / "summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")
    return destination, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--expected-host", help="require this local Windows hostname")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=200)
    parser.add_argument("--include-stats", action="store_true",
                        help="also acquire one source-pinned 20-stat native candidate snapshot")
    parser.add_argument("--include-zone", action="store_true",
                        help="bracket all other reads with two guarded native zone candidates")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-state-" + uuid.uuid4().hex))
    args = parser.parse_args(argv)
    try:
        path, report = collect(args.physical_pid, args.output_dir,
                               samples=args.samples, interval_ms=args.interval_ms,
                               include_stats=args.include_stats, include_zone=args.include_zone,
                               expected_host=args.expected_host)
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
        **({"zoneBracketCandidate": report["zoneBracketCandidate"]}
           if "zoneBracketCandidate" in report else {}),
        "sources": {k: v["sourceSha256"] for k, v in report["sources"].items()},
        "qualification": report["qualification"],
    }, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
