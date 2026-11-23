"""Pin one local RIFT process for later Waypoints calibration measurements."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import observe_physical, physical_rift
from scripts.collect_physical_player_state import source_matches_target
from scripts.compare_physical_player_context_pair import load
from scripts.physical_turn_calibration_receipts import settled_facing

SCHEMA = "rr2-physical-movement-calibration-preflight/1"
SUMMARY = "calibration-preflight.json"
FACING = "settled-facing.json"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def baseline(path, target):
    sample = settled_facing(path)
    require(source_matches_target(sample["identity"], target), "calibration-baseline-target-mismatch")
    return {"path": FACING, "sha256": sample["sha256"], "unitKey": sample["owner"][0],
            "completedAtUtc": sample["completedAtUtc"], "bodyBearingCandidate": sample["bearing"],
            "positionCandidate": list(sample["position"])}


def prepare(expected_host, pid, output_dir):
    require(physical_rift.is_local_host(expected_host), "wrong-host")
    require(type(pid) is int and 0 < pid <= 2**31 - 1, "explicit-pid-required")
    selection = physical_rift.select_physical(expected_host, pid)
    require(selection.get("status") == "ready", selection.get("reason", "physical-target-unavailable"))
    target = selection["target"]
    require(target.get("processId") == pid, "calibration-target-pid-mismatch")
    require(physical_rift.NATIVE_EXE.is_file(), "native-reader-not-built")
    before = physical_rift.inspect_movement_target(target)
    require(before["desktopInputsDown"] == [], "desktop-inputs-held")

    output_dir = Path(os.path.abspath(ROOT / output_dir))
    observe_physical._plain_path(output_dir)
    require(not output_dir.exists() and output_dir.parent.is_dir(), "new-output-directory-required")
    output_dir.mkdir()
    path = output_dir / FACING
    capture = physical_rift.read_native(selection, "facing", path, samples=3, interval_ms=150)
    require(capture.get("status") == "complete", capture.get("reason", "native-facing-unavailable"))
    require(capture.get("target") == target and capture.get("nativeRead") == "facing"
            and Path(capture.get("nativeOutput", "")) == path, "calibration-baseline-receipt-mismatch")
    observed = baseline(path, target)
    require(str(capture.get("nativeSourceSha256", "")).upper() == observed["sha256"], "calibration-baseline-sha-mismatch")
    current = physical_rift.select_physical(expected_host, pid)
    require(current.get("status") == "ready" and current.get("target") == target, "calibration-target-changed")
    after = physical_rift.inspect_movement_target(target)
    require(after["desktopInputsDown"] == [], "desktop-inputs-held")

    report = {"schema": SCHEMA, "status": "calibration-baseline-ready", "target": target,
              "baseline": observed, "foregroundAtLastInspection": after["target"]["isForeground"],
              "inputSent": False, "focusRequested": False}
    summary = output_dir / SUMMARY
    with summary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return summary, report


def verify_preflight(path):
    path = Path(path)
    report, digest = load(path)
    target = report.get("target")
    require(report.get("schema") == SCHEMA and report.get("status") == "calibration-baseline-ready"
            and report.get("inputSent") is False and report.get("focusRequested") is False
            and isinstance(target, dict) and physical_rift.valid_host_name(target.get("hostName"))
            and type(target.get("hwnd")) is int and target["hwnd"] > 0,
            "invalid-calibration-preflight")
    observed = baseline(path.parent / FACING, target)
    require(observed == report.get("baseline"), "calibration-preflight-baseline-mismatch")
    return target, observed, digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--physical-pid", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary, report = prepare(args.expected_host, args.physical_pid, args.output_dir)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False, "focusRequested": False}))
        return 2
    print(json.dumps({"summary": str(summary), **report}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
