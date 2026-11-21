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


def run(pid, output, *, count=3, interval_ms=500, scope_count=4,
        collect=capture.collect, replay_target=replay.replay,
        combine=continuity.combine, sleep=time.sleep):
    """Preserve all original captures; refuse cross-epoch changes and stale windows."""
    require(type(pid) is int and 0 < pid < 2 ** 31
            and type(count) is int and 2 <= count <= 6
            and type(interval_ms) is int and 0 <= interval_ms <= 2000
            and type(scope_count) is int and 1 <= scope_count <= 8,
            "invalid-bounds")
    output = Path(output)
    if not output.is_absolute():
        output = ROOT / output
    require(not output.exists() and not output.is_symlink()
            and output.parent.is_dir(), "output-must-be-new-directory")
    output.mkdir()
    paths, observations, selected = [], [], None
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
            path, report = collect(pid, destination, **options)
            require(report.get("status") == "matching-candidates",
                    f"capture-{index+1:02d}-unqualified")
            require(report.get("target", {}).get("processId") == pid,
                    f"capture-{index+1:02d}-process-mismatch")
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
        merged = combine(paths)
        require(merged.get("captureCount") == count
                and merged.get("qualificationStatus") == "candidate-only",
                "source-series-replay-refused")
        combined = {
            "schema": SCHEMA, "status": merged["status"],
            "qualificationStatus": merged["qualificationStatus"],
            "processId": pid, "inputSent": False,
            "individualCaptures": observations,
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
    args = parser.parse_args(argv)
    try:
        path, result = run(
            args.physical_pid, args.output_dir,
            count=args.count, interval_ms=args.interval_ms,
            scope_count=args.scope_count)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220],
                          "inputSent": False}))
        return 2
    print(json.dumps({"status": result["status"],
                      "captureCount": len(result["individualCaptures"]),
                      "aBaCandidates": len(result["continuity"]["aBaAcrossCaptures"]),
                      "output": str(path), "inputSent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
