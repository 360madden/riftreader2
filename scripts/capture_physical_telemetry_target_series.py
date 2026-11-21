"""Bounded physical RIFT target observation series without game input.

The first window locates live Lua frames from the process memory map; later
windows reuse only the just-verified same-process scope, rechecking identity,
source-clock advancement and native/Lua evidence each time.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_physical_telemetry_zone as capture
from scripts import replay_physical_telemetry_target as replay
from scripts import replay_physical_telemetry_target_series as continuity

SCHEMA = "physical-telemetry-target-series-capture/1"
ADDRESS = re.compile(r"0x[1-9A-F][0-9A-F]*\Z")


def require(test, reason):
    if not test:
        raise ValueError("target-series-capture-" + reason)


def _stale_scope_candidate(report, target):
    """A failed pass permits exactly one new read-only locator survey."""
    survey = report.get("scopeSurvey") or {}
    return (report.get("status") == "unqualified"
            and report.get("sameProcessEpoch") is True
            and report.get("target") == target
            and report.get("sourceClockProgression") == "unqualified"
            and survey.get("status") == "scoped-candidate")


def run(pid, output, *, count=3, interval_ms=500, scope_count=4,
        recover_stale_scope=False, stop_on_aba=False,
        collect=capture.collect, replay_target=replay.replay,
        combine=continuity.combine, sleep=time.sleep):
    """Preserve all original captures; refuse cross-epoch changes and stale windows."""
    require(type(pid) is int and 0 < pid < 2 ** 31
            and type(count) is int and 2 <= count <= 6
            and type(interval_ms) is int and 0 <= interval_ms <= 2000
            and type(scope_count) is int and 1 <= scope_count <= 8
            and type(recover_stale_scope) is bool
            and type(stop_on_aba) is bool,
            "invalid-bounds")
    output = Path(output)
    if not output.is_absolute():
        output = ROOT / output
    require(not output.exists() and not output.is_symlink()
            and output.parent.is_dir(), "output-must-be-new-directory")
    output.mkdir()
    paths, observations, selected = [], [], None
    pinned_target, recovery_attempts = None, []
    merged, early_stop = None, False
    try:
        for index in range(count):
            if index:
                sleep(interval_ms / 1000)
            destination = output / f"capture-{index+1:02d}"
            options = {
                "auto_scope": True, "include_native_target": True,
                "scope_count": scope_count if index == 0 else 1,
                "discover_scope": index == 0,
            }
            if selected is not None:
                options["start_address"] = selected
            recovery_reason = None
            try:
                path, report = collect(pid, destination, **options)
            except ValueError as exc:
                # A scoped candidate can disappear before survey, leaving a
                # retained partial acquisition. Retry ONLY this exact failure.
                if (recover_stale_scope and index > 0
                        and str(exc) ==
                        "telemetry-zone-capture-no-current-player-zone-scope-in-survey"):
                    recovery_reason = "cached-scope-not-found"
                else:
                    raise
            else:
                require(type(report) is dict
                        and type(report.get("target")) is dict
                        and report["target"].get("processId") == pid,
                        f"capture-{index+1:02d}-process-mismatch")
                if pinned_target is not None:
                    require(report["target"] == pinned_target,
                            f"capture-{index+1:02d}-target-identity-changed")
                if (recover_stale_scope and index > 0 and
                        _stale_scope_candidate(report, pinned_target)):
                    recovery_reason = "cached-scope-source-not-advancing"
            if recovery_reason is not None:
                # Never overwrite the original failed window or repeat a
                # verified game action. Fresh discovery has its own artifact.
                previous = destination
                destination = output / f"capture-{index+1:02d}-rediscovery"
                attempt = {
                    "capture": index + 1, "reason": recovery_reason,
                    "failedWindow": str(previous),
                    "rediscoveryWindow": str(destination),
                    "outcome": "attempted"}
                recovery_attempts.append(attempt)
                path, report = collect(
                    pid, destination, auto_scope=True,
                    include_native_target=True, scope_count=scope_count,
                    discover_scope=True)
                attempt["outcome"] = "completed-candidate"
            require(type(report) is dict
                    and type(report.get("target")) is dict
                    and report["target"].get("processId") == pid,
                    f"capture-{index+1:02d}-process-mismatch")
            if pinned_target is None:
                pinned_target = report["target"]
            else:
                require(report["target"] == pinned_target,
                        f"capture-{index+1:02d}-target-identity-changed")
            require(report.get("status") == "matching-candidates",
                    f"capture-{index+1:02d}-unqualified")
            selected = (report.get("scopeSurvey") or {}).get("selectedStartAddress")
            require(type(selected) is str and ADDRESS.fullmatch(selected) is not None,
                    f"capture-{index+1:02d}-scope-unavailable")
            checked = replay_target(path)
            require(checked.get("qualificationStatus") == "candidate-only",
                    f"capture-{index+1:02d}-replay-refused")
            paths.append(path)
            observations.append({"capture": index + 1, "status": checked["status"],
                                 "lastSequence": checked["lastSequence"],
                                 "scopeCandidate": selected})
            if stop_on_aba and len(paths) >= 2:
                # Each merge independently reopens every original Lua/native
                # source byte. Never stop on the final-target-only shortcut.
                candidate = combine(paths)
                require(type(candidate) is dict
                        and candidate.get("captureCount") == len(paths)
                        and candidate.get("qualificationStatus") == "candidate-only"
                        and type(candidate.get("observedSourceABACycles")) is list,
                        "early-stop-replay-invalid")
                merged = candidate
                if candidate["observedSourceABACycles"]:
                    early_stop = True
                    break
        if merged is None:
            merged = combine(paths)
        require(type(merged) is dict
                and merged.get("captureCount") == len(paths)
                and merged.get("qualificationStatus") == "candidate-only",
                "source-series-replay-refused")
        combined = {
            "schema": SCHEMA, "status": merged["status"],
            "qualificationStatus": merged["qualificationStatus"],
            "processId": pid, "inputSent": False,
            "individualCaptures": observations,
            "requestedCaptureCount": count,
            "completedCaptureCount": len(paths),
            "earlyStopReason": ("observed-source-a-b-a-candidate"
                                if early_stop else None),
            "scopeRediscoveryAttempts": recovery_attempts,
            "continuity": merged,
            "qualification": ("Sequential physical read-only acquisitions. Each has "
                              "native/Lua zone and target source checks, but no "
                              "atomic target state or implied selection action."),
        }
        result = output / "result.json"
        with result.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(combined, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return result, combined
    except BaseException as exc:
        # A failed session retains its original per-window source evidence.
        error = {"schema": SCHEMA, "status": "unqualified",
                 "inputSent": False,
                 "completedCaptures": len(paths),
                 "scopeRediscoveryAttempts": recovery_attempts,
                 "reason": str(exc)[:220]}
        with (output / "failure.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(error, stream, indent=2, allow_nan=False)
            stream.write("\n")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=500)
    parser.add_argument("--scope-count", type=int, default=4)
    parser.add_argument("--recover-stale-scope", action="store_true",
                        help="on an unqualified cached Lua scope, retain original and "
                             "perform one bounded read-only map rediscovery")
    parser.add_argument("--stop-on-aba", action="store_true",
                        help="stop before the requested window limit only after an "
                             "independent source-hashed A-B-A candidate is observed")
    args = parser.parse_args(argv)
    try:
        path, result = run(
            args.physical_pid, args.output_dir,
            count=args.count, interval_ms=args.interval_ms,
            scope_count=args.scope_count,
            recover_stale_scope=args.recover_stale_scope,
            stop_on_aba=args.stop_on_aba)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220],
                          "inputSent": False}))
        return 2
    print(json.dumps({"status": result["status"],
                      "captureCount": len(result["individualCaptures"]),
                      "aBaCandidates": len(result["continuity"]["observedSourceABACycles"]),
                      "lastStateABACandidates": len(result["continuity"]["aBaAcrossCaptures"]),
                      "earlyStopReason": result.get("earlyStopReason"),
                      "output": str(path), "inputSent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
