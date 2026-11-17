"""One no-input physical RIFT state read using existing native readers.

Independent context, XYZ and vitals readings share an exact host/process/module/self
owner. Not an atomic snapshot, live Lua reference or qualified gameplay telemetry.
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

HOST = "AMD-DESKTOP"
SUPPORTED_BUILDS = frozenset((BUILD_SHA,
    "DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01"))
KINDS = ("player-context", "position", "vitals")


def require(ok, reason):
    if not ok:
        raise ValueError("physical-player-state-" + reason)


def pin(pid):
    require(socket.gethostname().upper() == HOST, "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    selection = physical_rift.select_physical(HOST, pid)
    target = selection.get("target")
    require(selection.get("status") == "ready"
            and selection.get("ownerHost") == HOST and isinstance(target, dict)
            and target.get("hostName") == HOST and target.get("processId") == pid
            and str(target.get("processStartUtcTicks", "")).isdecimal()
            and str(target.get("executableSha256", "")).upper() in SUPPORTED_BUILDS
            and type(target.get("hwnd")) is int and target["hwnd"] > 0,
            "physical-process-identity-unavailable")
    return selection


def collect(pid, output_dir, *, samples=3, interval_ms=200, include_stats=False):
    require(type(samples) is int and 2 <= samples <= 10
            and type(interval_ms) is int and 0 <= interval_ms <= 1000
            and type(include_stats) is bool,
            "invalid-sampling-bounds")
    first = pin(pid)
    owner = first["target"]
    build_sha = str(owner["executableSha256"]).upper()
    # Standalone stats are now separately qualified for both exact builds.
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    require(not output_dir.exists() and output_dir.parent.is_dir(),
            "new-output-directory-required")
    output_dir.mkdir()
    results, module, self_key = {}, None, None
    for kind in KINDS + (("stats",) if include_stats else ()):
        require(pin(pid)["target"] == owner, "epoch-changed-before-read")
        path = output_dir / (kind + ".json")
        # Stats is a one-shot existing native reader, not a burst command.
        options = {} if kind == "stats" else {"samples": samples, "interval_ms": interval_ms}
        result = physical_rift.read_native(first, kind, path, **options)
        require(result.get("status") == "complete"
                and result.get("nativeRead") == kind
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
        identity = (observation.get("identity") if kind == "stats" and isinstance(observation, dict)
                    else report.get("identity"))
        require(isinstance(identity, dict)
                and identity.get("processId") == pid
                and str(identity.get("processStartUtcTicks")) == owner["processStartUtcTicks"]
                and str(identity.get("executableSha256", "")).upper() == build_sha
                and type(identity.get("moduleBaseAddress")) is int
                and type(identity.get("moduleSize")) is int
                and identity["moduleBaseAddress"] > 0 and identity["moduleSize"] > 0
                and report.get("status") == "complete"
                and ((kind == "stats" and report.get("contractVersion") == "native-current-stats-candidate/1"
                      and isinstance(observation, dict)
                      and result.get("nativeSourceSha256", "").upper() == source_sha)
                     or (kind != "stats" and report.get("completedSamples") == samples)),
                kind + "-source-identity-invalid")
        current_module = (identity["moduleBaseAddress"], identity["moduleSize"])
        if module is None:
            module = current_module
        require(current_module == module, "module-owner-changed")
        values = result.get("nativeValues")
        require(isinstance(values, dict) and isinstance(values.get("unitKey"), str)
                and values["unitKey"].isdecimal() and int(values["unitKey"]) > 0,
                kind + "-self-key-unavailable")
        if self_key is None:
            self_key = values["unitKey"]
        require(values["unitKey"] == self_key, "self-key-changed")
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
        require(pin(pid)["target"] == owner, "epoch-changed-after-read")
        results[kind] = {
            "path": str(path), "sourceSha256": source_sha,
            "samples": 1 if kind == "stats" else samples, "candidateValues": values,
            **({"burstSummary": result["nativeBurstSummary"]}
               if "nativeBurstSummary" in result else {}),
        }
    summary = {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-state-candidate/1",
        "status": "complete-candidate", "ownerHost": HOST, "target": owner,
        "moduleBaseAddress": module[0], "moduleSize": module[1],
        "selfKeyCandidate": self_key, "sources": results,
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
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=200)
    parser.add_argument("--include-stats", action="store_true",
                        help="also acquire one source-pinned 20-stat native candidate snapshot")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-state-" + uuid.uuid4().hex))
    args = parser.parse_args(argv)
    try:
        path, report = collect(args.physical_pid, args.output_dir,
                               samples=args.samples, interval_ms=args.interval_ms,
                               include_stats=args.include_stats)
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
        "sources": {k: v["sourceSha256"] for k, v in report["sources"].items()},
        "qualification": report["qualification"],
    }, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
