#!/usr/bin/env python3
"""Read two candidate native positions across a manual observation window; no input."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift, physical_route_preview
from scripts.waypoint_progress import write_json_atomic

SOURCE_NAMES = ("before.json", "after.json")
REPORT_NAME = "manual-motion.json"


def _identity(selection):
    if selection.get("status") != "ready":
        raise ValueError(selection.get("reason", "physical-selection-failed"))
    target = selection["target"]
    return (target["hostName"].casefold(), target["processId"],
            target["processStartUtcTicks"], target["executablePath"].casefold(),
            target["executableSha256"].casefold(), target["hwnd"])


def _check_capability(native_reader=None):
    exe = physical_rift._native_reader_path(native_reader)
    if not exe.is_file():
        raise ValueError("native-reader-not-built")
    try:
        result = subprocess.run([str(exe), "--help"], cwd=ROOT, capture_output=True,
                                text=True, timeout=15, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("native-reader-capability-check-failed") from exc
    if result.returncode != 0 or not any(
            line.startswith("sample-current-position --pid ") for line in result.stdout.splitlines()):
        raise ValueError("native-reader-missing-position-command")


def _read_capture(path, target):
    native, sha = physical_route_preview._read_native(Path(path))
    if native["sampleCount"] != 1:
        raise ValueError("expected-one-sample")
    source = native["identity"]
    if (type(target.get("processId")) is not int or source["processId"] != target["processId"] or
            str(source["processStartUtcTicks"]) != target["processStartUtcTicks"] or
            source["executablePath"].casefold() != str(target["executablePath"]).casefold() or
            source["executableSha256"].casefold() != str(target["executableSha256"]).casefold()):
        raise ValueError("native-identity-mismatch")
    return native, sha, str(path)


def _capture(selection, output, *, read):
    receipt = read(selection, "position", output=output, samples=1)
    if receipt.get("status") != "complete":
        raise ValueError(receipt.get("reason", "native-read-failed"))
    if receipt.get("target") != selection["target"] or receipt.get("nativeRead") != "position":
        raise ValueError("native-receipt-target-mismatch")
    path = Path(receipt["nativeOutput"])
    if output is not None and path != output:
        raise ValueError("native-receipt-output-mismatch")
    captured = _read_capture(path, selection["target"])
    if captured[1].casefold() != str(receipt.get("nativeSourceSha256", "")).casefold():
        raise ValueError("native-source-hash-mismatch")
    return captured


def _validate_wait(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 30:
        raise ValueError("wait-seconds-must-be-1-to-30")


def _summarize(target, seconds, before, after):
    first, first_sha, first_path = before
    second, second_sha, second_path = after
    if first["unitKey"] != second["unitKey"]:
        raise ValueError("native-owner-changed")
    if physical_rift._utc_tick_order_key(second["firstSampleUtc"]) <= physical_rift._utc_tick_order_key(first["lastSampleUtc"]):
        raise ValueError("native-sample-time-overlap")
    a, b = first["positions"][0], second["positions"][0]
    delta = {axis: getattr(b, axis) - getattr(a, axis) for axis in ("x", "y", "z")}
    planar = math.hypot(delta["x"], delta["z"])
    if not all(math.isfinite(v) for v in (*delta.values(), planar)):
        raise ValueError("nonfinite-delta")
    return {
        "recordType": "physical-manual-motion/1", "status": "candidate-only",
        "host": target["hostName"], "identity": target, "inputSent": False, "focusChanged": False,
        "unitKey": first["unitKey"], "waitSeconds": seconds,
        "beforeXYZ": {axis: getattr(a, axis) for axis in ("x", "y", "z")},
        "afterXYZ": {axis: getattr(b, axis) for axis in ("x", "y", "z")},
        "deltaXYZ": delta, "planarDisplacementXZ": planar,
        "beforeSampleUtc": first["lastSampleUtc"], "afterSampleUtc": second["firstSampleUtc"],
        "sourceReports": [{"path": first_path, "sha256": first_sha},
                          {"path": second_path, "sha256": second_sha}],
        "qualification": "candidate cached native values; freshness and player movement semantics unqualified",
    }


def probe(host, pid, seconds, *, output=None, native_reader=None):
    if not physical_rift.valid_host_name(host) or host.casefold() != socket.gethostname().casefold():
        raise ValueError("host-mismatch")
    if type(pid) is not int or not 1 <= pid <= 4294967295:
        raise ValueError("explicit-positive-pid-required")
    _validate_wait(seconds)
    read = physical_rift.bind_native_reader(physical_rift.read_native, native_reader)
    selection = physical_rift.select_physical(host, pid)
    identity = _identity(selection)
    if identity[:2] != (host.casefold(), pid):
        raise ValueError("physical-selection-mismatch")
    _check_capability(native_reader)
    if output is not None:
        output = Path(output).absolute()
        output.mkdir()
    first = _capture(selection, output / SOURCE_NAMES[0] if output else None, read=read)
    print(f"First candidate captured. Waiting {seconds:g} seconds for the next sample.",
          file=sys.stderr, flush=True)
    time.sleep(seconds)
    second_selection = physical_rift.select_physical(host, pid)
    if _identity(second_selection) != identity:
        raise ValueError("process-identity-changed")
    second = _capture(second_selection, output / SOURCE_NAMES[1] if output else None, read=read)
    if _identity(physical_rift.select_physical(host, pid)) != identity:
        raise ValueError("process-identity-changed")
    result = _summarize(selection["target"], seconds, first, second)
    if output is not None:
        for source, name in zip(result["sourceReports"], SOURCE_NAMES):
            source["path"] = name
        report = output / REPORT_NAME
        write_json_atomic(report, result)
        return dict(result, report=str(report))
    return result


def replay(report_path):
    """Recompute a saved candidate pair from the original local evidence only."""
    path = Path(report_path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("manual-motion-report-unavailable")
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("manual-motion-report-oversized")
    report = physical_rift._strict_native_json(data.decode("utf-8"))
    if not isinstance(report, dict) or report.get("recordType") != "physical-manual-motion/1":
        raise ValueError("invalid-manual-motion-report")
    target, seconds, sources = report["identity"], report["waitSeconds"], report["sourceReports"]
    if (not isinstance(target, dict) or not physical_rift.valid_host_name(target.get("hostName"))
            or type(target.get("hwnd")) is not int or target["hwnd"] < 0):
        raise ValueError("invalid-recorded-target")
    _validate_wait(seconds)
    if (not isinstance(sources, list) or len(sources) != len(SOURCE_NAMES)
            or any(not isinstance(source, dict) or source.get("path") != name
                   for source, name in zip(sources, SOURCE_NAMES))):
        raise ValueError("invalid-manual-motion-source-list")
    captures = []
    for source, name in zip(sources, SOURCE_NAMES):
        native, sha, _ = _read_capture(path.parent / name, target)
        if sha != source.get("sha256"):
            raise ValueError("native-source-hash-mismatch")
        captures.append((native, sha, name))
    result = _summarize(target, seconds, *captures)
    if result != report:
        raise ValueError("manual-motion-result-mismatch")
    return dict(result, verification="source-replayed", report=str(path.absolute()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="verified local Windows machine name")
    parser.add_argument("--pid", type=int, help="exact local rift_x64 PID")
    parser.add_argument("--seconds", type=float, help="observation window, 1 to 30 seconds")
    parser.add_argument("--output", type=Path, help="fresh directory for both raw reports and the summary")
    parser.add_argument("--native-reader", type=Path,
                        help="absolute local path to a published RiftReader2.Live.exe")
    parser.add_argument("--replay", type=Path, help="verify a saved manual-motion.json without a live read")
    args = parser.parse_args(argv)
    if args.replay is not None:
        if any(value is not None for value in (args.host, args.pid, args.seconds,
                                               args.output, args.native_reader)):
            parser.error("--replay cannot be combined with capture options")
    elif any(value is None for value in (args.host, args.pid, args.seconds)):
        parser.error("capture requires --host, --pid and --seconds")
    try:
        result = (replay(args.replay) if args.replay is not None
                  else probe(args.host, args.pid, args.seconds, output=args.output,
                             native_reader=args.native_reader))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "inputSent": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
