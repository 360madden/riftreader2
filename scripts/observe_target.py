"""Observe one explicitly selected RR2 target; never fall back to another machine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Target routing only. Runtime identity, credentials and readiness stay in existing adapters.
TARGETS = {
    "lab1": ("AMD-DESKTOP", "vmware"),
    "lab2": ("AMD-DESKTOP", "vmware"),
    "physical-amd-desktop": ("AMD-DESKTOP", "physical"),
    "physical-legion": ("LEGION", "physical"),
}


def _capture_vmware(output, native_vitals):
    from scripts.inspect_lab2_tool import flow, run_inspection
    output = output or flow.OUTPUT_BASE / ("observe-lab2-" + uuid.uuid4().hex)
    return run_inspection(output, capture_only=not native_vitals)[0]


def _capture_physical(expected_host, output, allow_foreground_change):
    from scripts.observe_physical import capture_physical
    output = output or ROOT / "artifacts" / ("observe-physical-" + uuid.uuid4().hex)
    return capture_physical(expected_host, output,
                            allow_foreground_change=allow_foreground_change)


def _preview(result, width):
    from scripts.quick_review_capture import preview
    return preview(Path(result["image"]), result["imageSha256"], width)


def observe(target_id, expected_host, output=None, *, native_vitals=False,
            allow_foreground_change=False, with_preview=False, preview_width=840):
    started = time.perf_counter()
    if target_id not in TARGETS:
        raise ValueError("unknown-target")
    owner_host, workflow = TARGETS[target_id]
    if not isinstance(expected_host, str) or expected_host.casefold() != owner_host.casefold():
        raise ValueError("target-host-mismatch")
    actual_host = socket.gethostname()
    if actual_host.casefold() != owner_host.casefold():
        raise ValueError("host-mismatch")
    if not 500 <= preview_width <= 1600:
        raise ValueError("invalid-preview-width")
    if target_id == "lab1":
        raise ValueError("lab1-managed-capture-not-yet-qualified")
    if workflow == "physical" and native_vitals:
        raise ValueError("physical-native-vitals-not-yet-qualified")

    # Lazy adapters ensure a physical request never loads guest-auth or VMware code.
    if workflow == "vmware":
        result = _capture_vmware(output, native_vitals)
    else:
        result = _capture_physical(owner_host, output, allow_foreground_change)
    if (not isinstance(result, dict) or result.get("targetId") != target_id
            or result.get("workflow") != workflow):
        raise ValueError("adapter-target-mismatch")
    if socket.gethostname().casefold() != actual_host.casefold():
        raise ValueError("host-changed")
    result = dict(result, ownerHost=owner_host)
    if result.get("status") == "blocked":
        return result
    if result.get("status") != "verified-awaiting-visual-review":
        raise ValueError("unexpected-adapter-status")
    if with_preview:
        result["preview"] = _preview(result, preview_width)
    result["elapsedSeconds"] = round(time.perf_counter() - started, 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=tuple(TARGETS))
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--output", type=Path, help="fresh absolute directory; omitted creates a unique artifact path")
    parser.add_argument("--native-vitals", action="store_true", help="Lab 2 only; retain existing candidate qualifications")
    parser.add_argument("--allow-foreground-change", action="store_true",
                        help="physical capture only: explicitly allow the desktop backend to focus RIFT")
    parser.add_argument("--preview", action="store_true", help="include a bounded non-authoritative JPEG in the same result")
    parser.add_argument("--preview-width", type=int, default=840)
    args = parser.parse_args(argv)
    try:
        result = observe(args.target, args.expected_host, args.output,
                         native_vitals=args.native_vitals,
                         allow_foreground_change=args.allow_foreground_change,
                         with_preview=args.preview, preview_width=args.preview_width)
    except Exception as error:
        result = {"status": "blocked", "targetId": args.target,
                  "errorType": type(error).__name__,
                  "reason": str(error) if isinstance(error, ValueError) else "observation-failed"}
        details = getattr(error, "details", None)
        if isinstance(details, dict):
            result["workflowFailure"] = details
    print(json.dumps(result, separators=(",", ":"), allow_nan=False), flush=True)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
