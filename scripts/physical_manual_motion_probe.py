#!/usr/bin/env python3
"""Read two candidate native positions around a human's manual movement; no input."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift, physical_route_preview


def _identity(selection):
    if selection.get("status") != "ready":
        raise ValueError(selection.get("reason", "physical-selection-failed"))
    target = selection["target"]
    return (target["hostName"].casefold(), target["processId"],
            target["processStartUtcTicks"], target["executablePath"].casefold(),
            target["executableSha256"].casefold(), target["hwnd"])


def _check_capability():
    exe = physical_rift.NATIVE_EXE
    if not exe.is_file():
        raise ValueError("native-reader-not-built")
    try:
        result = subprocess.run([str(exe), "--help"], cwd=ROOT, capture_output=True,
                                text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("native-reader-capability-check-failed") from exc
    if result.returncode != 0 or not any(
            line.startswith("sample-current-position --pid ") for line in result.stdout.splitlines()):
        raise ValueError("native-reader-missing-position-command")


def _capture(selection):
    receipt = physical_rift.read_native(selection, "position", samples=1)
    if receipt.get("status") != "complete":
        raise ValueError(receipt.get("reason", "native-read-failed"))
    native, sha = physical_route_preview._read_native(Path(receipt["nativeOutput"]))
    if native["sampleCount"] != 1:
        raise ValueError("expected-one-sample")
    target = selection["target"]
    source = native["identity"]
    if (source["processId"] != target["processId"] or
            str(source["processStartUtcTicks"]) != target["processStartUtcTicks"] or
            source["executablePath"].casefold() != target["executablePath"].casefold() or
            source["executableSha256"].casefold() != target["executableSha256"].casefold()):
        raise ValueError("native-identity-mismatch")
    return native, sha, receipt["nativeOutput"]


def probe(host, pid, seconds):
    if host != "AMD-DESKTOP" or type(pid) is not int or pid <= 0:
        raise ValueError("explicit-amd-host-and-positive-pid-required")
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 30:
        raise ValueError("wait-seconds-must-be-1-to-30")
    selection = physical_rift.select_physical(host, pid)
    identity = _identity(selection)
    _check_capability()
    first, first_sha, first_path = _capture(selection)
    print(f"First candidate captured. Move the character manually now; waiting {seconds:g} seconds.",
          file=sys.stderr, flush=True)
    time.sleep(seconds)
    second_selection = physical_rift.select_physical(host, pid)
    if _identity(second_selection) != identity:
        raise ValueError("process-identity-changed")
    second, second_sha, second_path = _capture(second_selection)
    if _identity(physical_rift.select_physical(host, pid)) != identity:
        raise ValueError("process-identity-changed")
    if first["unitKey"] != second["unitKey"]:
        raise ValueError("native-owner-changed")
    end_first = datetime.fromisoformat(first["lastSampleUtc"].replace("Z", "+00:00"))
    start_second = datetime.fromisoformat(second["firstSampleUtc"].replace("Z", "+00:00"))
    if start_second <= end_first:
        raise ValueError("native-sample-time-overlap")
    a, b = first["positions"][0], second["positions"][0]
    delta = {axis: getattr(b, axis) - getattr(a, axis) for axis in ("x", "y", "z")}
    planar = math.hypot(delta["x"], delta["z"])
    if not all(math.isfinite(v) for v in (*delta.values(), planar)):
        raise ValueError("nonfinite-delta")
    return {
        "status": "candidate-only", "host": host, "identity": selection["target"],
        "unitKey": first["unitKey"], "waitSeconds": seconds,
        "beforeXYZ": {axis: getattr(a, axis) for axis in ("x", "y", "z")},
        "afterXYZ": {axis: getattr(b, axis) for axis in ("x", "y", "z")},
        "deltaXYZ": delta, "planarDisplacementXZ": planar,
        "beforeSampleUtc": first["lastSampleUtc"], "afterSampleUtc": second["firstSampleUtc"],
        "sourceReports": [{"path": first_path, "sha256": first_sha},
                          {"path": second_path, "sha256": second_sha}],
        "qualification": "candidate cached native values; freshness and player movement semantics unqualified",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=["AMD-DESKTOP"])
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--seconds", required=True, type=float, help="manual movement window, 1 to 30 seconds")
    args = parser.parse_args(argv)
    try:
        result = probe(args.host, args.pid, args.seconds)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
