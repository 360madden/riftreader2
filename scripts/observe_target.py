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


def _capture_vmware(target_id, output, native_vitals):
    from scripts.inspect_lab2_tool import flow, run_inspection
    output = output or flow.OUTPUT_BASE / ("observe-" + target_id + "-" + uuid.uuid4().hex)
    return run_inspection(output, capture_only=not native_vitals, lab=target_id)[0]


def _capture_host_preview(target_id, expected_host, output):
    from scripts.preview_vmware_fla_ui import capture
    directory = output or ROOT / "artifacts" / ("flaui-preview-" + target_id + "-" + uuid.uuid4().hex)
    return capture(target_id, expected_host, directory)


def _capture_physical(expected_host, output, allow_foreground_change, physical_pid=None):
    from scripts.observe_physical import capture_physical
    output = output or ROOT / "artifacts" / ("observe-physical-" + uuid.uuid4().hex)
    return capture_physical(expected_host, output,
                            allow_foreground_change=allow_foreground_change,
                            physical_pid=physical_pid)


def _capture_with_native_facing(expected_host, output, physical_pid):
    """Bracket one focus-neutral frame with the existing exact-process readers."""
    from scripts import physical_rift
    from scripts.observe_gpu import capture_gpu
    selection = physical_rift.select_physical(expected_host, physical_pid)
    if selection["status"] != "ready":
        return selection
    started = time.perf_counter()
    before = physical_rift.read_native(selection, "facing", samples=1, include_target=True)
    directory = output or ROOT / "artifacts" / ("observe-wgc-" + uuid.uuid4().hex)
    result = capture_gpu(expected_host, directory, physical_pid=selection["target"]["processId"])
    if result.get("status") == "blocked":
        return result
    bracket = {"status": "unavailable", "beforeOutput": before.get("nativeOutput"),
               "qualification": "sequential native/frame candidates; no occlusion or restart qualification"}
    result["nativeFacing"] = bracket
    if before.get("status") != "complete":
        bracket["reason"] = "native-before-unavailable"
        bracket["nativeReason"] = before.get("reason")
        return result
    after = physical_rift.read_native(selection, "facing", samples=1, include_target=True)
    bracket["afterOutput"] = after.get("nativeOutput")
    if after.get("status") != "complete":
        bracket["reason"] = "native-after-unavailable"
        bracket["nativeReason"] = after.get("reason")
        return result
    try:
        reports = [json.loads(Path(read["nativeOutput"]).read_text(encoding="utf-8")) for read in (before, after)]
        values = [physical_rift._native_values("facing", report) for report in reports]
        first, last = [report["observation"] for report in reports]
        frame = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
        target = result["target"]
        identity = reports[0]["identity"]
        if (reports[1]["identity"] != identity or target["processId"] != identity["processId"]
                or target["processStartUtcTicks"] != str(identity["processStartUtcTicks"])
                or target["executableSha256"].casefold() != identity["executableSha256"].casefold()
                or target["hwnd"] != selection["target"]["hwnd"]
                or frame["imageSha256"].casefold() != result["imageSha256"].casefold()):
            raise ValueError("native-frame-identity-mismatch")
        stamp = physical_rift._utc_tick_order_key
        if not (stamp(first["completedAtUtc"]) <= stamp(frame["capturedStartedAtUtc"])
                <= stamp(frame["capturedCompletedAtUtc"]) <= stamp(last["startedAtUtc"])):
            raise ValueError("native-frame-acquisition-order-mismatch")
        if time.perf_counter() - started > 5:
            raise ValueError("native-frame-acquisition-exceeded-five-seconds")
        for field in ("playerKeyDecimal", "playerEntityDecimal", "playerSystemDecimal", "rawBits", "entityPositionRawBits"):
            if first.get(field) != last.get(field):
                raise ValueError("player-changed-across-frame")
        for source in ("primary", "secondary"):
            if first["positionOrientationCandidate"][source]["rawBits"] != last["positionOrientationCandidate"][source]["rawBits"]:
                raise ValueError("facing-changed-across-frame")
        if (first.get("opticalCameraCandidate", {}).get("status") != "available-candidate"
                or first["opticalCameraCandidate"] != last.get("opticalCameraCandidate")
                or first.get("targetProjectionCameraStableCandidate") is not True
                or last.get("targetProjectionCameraStableCandidate") is not True):
            raise ValueError("camera-unavailable-or-changed-across-frame")
        target_fields = ("status", "reason", "targetKey", "positionXYZCandidate", "screenPointCandidate", "guardStatus")
        target_values = [{key: (value.get("selectedTargetProjectionCandidate") or {}).get(key)
                          for key in target_fields} for value in values]
        if target_values[0] != target_values[1]:
            raise ValueError("target-changed-across-frame")
        bracket.update(status="stable-bracket-candidate", values=values[-1])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        bracket["reason"] = str(error) if isinstance(error, ValueError) else "invalid-native-frame-bracket"
    return result


def _preview(result, width):
    from scripts.quick_review_capture import preview
    return preview(Path(result["image"]), result["imageSha256"], width)


def _paired_preview(result, width, crop):
    from scripts.quick_review_capture import review_pair
    return review_pair(Path(result["image"]), result["imageSha256"], crop, width)


def observe(target_id, expected_host, output=None, *, native_vitals=False,
            allow_foreground_change=False, with_preview=False, preview_width=840,
            preview_detail_crop=None, host_preview=False, physical_pid=None,
            historical_vm=False, physical_capture_backend=None, native_facing=False):
    started = time.perf_counter()
    if target_id not in TARGETS:
        raise ValueError("unknown-target")
    owner_host, workflow = TARGETS[target_id]
    if not isinstance(expected_host, str) or expected_host.casefold() != owner_host.casefold():
        raise ValueError("target-host-mismatch")
    actual_host = socket.gethostname()
    if actual_host.casefold() != owner_host.casefold():
        raise ValueError("host-mismatch")
    if physical_capture_backend is not None:
        if workflow != "physical" or physical_capture_backend != "wgc":
            raise ValueError("invalid-physical-capture-backend")
    if physical_pid is not None:
        if workflow != "physical":
            raise ValueError("physical-pid-incompatible-target")
        if type(physical_pid) is not int or not 1 <= physical_pid <= 4294967295:
            raise ValueError("invalid-physical-pid")
    if type(native_facing) is not bool or (native_facing and
            (workflow != "physical" or allow_foreground_change or host_preview or native_vitals)):
        raise ValueError("native-facing-requires-focus-neutral-physical-capture")
    if type(preview_width) is not int or not 500 <= preview_width <= 1600:
        raise ValueError("invalid-preview-width")
    if preview_detail_crop is not None:
        if not with_preview:
            raise ValueError("detail-crop-requires-preview")
        box = preview_detail_crop
        if (not isinstance(box, (tuple, list)) or len(box) != 4
                or any(type(value) is not int for value in box)
                or not 0 <= box[0] < box[2] <= 8192
                or not 0 <= box[1] < box[3] <= 8192):
            raise ValueError("invalid-preview-crop")
    if workflow == "vmware" and historical_vm is not True:
        raise ValueError("vmware-retired-use-physical-rift")
    if host_preview:
        if workflow != "vmware" or native_vitals or allow_foreground_change or with_preview or preview_detail_crop is not None:
            raise ValueError("host-preview-incompatible-options")
        result = _capture_host_preview(target_id, owner_host, output)
        if (not isinstance(result, dict)
                or result.get("status") != "captured-nonauthoritative"
                or result.get("lab") != target_id
                or result.get("movementEligible") is not False
                or result.get("gameProcessIdentityVerified") is not False):
            raise ValueError("host-preview-invalid-receipt")
        if socket.gethostname().casefold() != actual_host.casefold():
            raise ValueError("host-changed")
        return dict(result, targetId=target_id, workflow=workflow, ownerHost=owner_host,
                    elapsedSeconds=round(time.perf_counter() - started, 3))
    if target_id == "lab1" and native_vitals:
        raise ValueError("lab1-native-vitals-not-yet-qualified")
    if workflow == "physical" and native_vitals:
        raise ValueError("physical-native-vitals-not-yet-qualified")

    # Lazy adapters ensure a physical request never loads guest-auth or VMware code.
    if workflow == "vmware":
        result = _capture_vmware(target_id, output, native_vitals)
    else:
        if native_facing:
            result = _capture_with_native_facing(owner_host, output, physical_pid)
        elif physical_capture_backend == "wgc":
            from scripts.observe_gpu import capture_gpu
            directory = output or ROOT / "artifacts" / ("observe-wgc-" + uuid.uuid4().hex)
            result = capture_gpu(owner_host, directory, physical_pid=physical_pid)
        else:
            result = _capture_physical(owner_host, output, allow_foreground_change, physical_pid)
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
        if preview_detail_crop is None:
            result["preview"] = _preview(result, preview_width)
        else:
            pair = _paired_preview(result, preview_width, tuple(preview_detail_crop))
            result["preview"] = pair["fullFrame"]
            result["detailPreview"] = pair["detail"]
    result["elapsedSeconds"] = round(time.perf_counter() - started, 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=tuple(TARGETS))
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--output", type=Path, help="fresh absolute directory; omitted creates a unique artifact path")
    parser.add_argument("--native-vitals", action="store_true", help="historical Lab 2 only; retain existing candidate qualifications")
    parser.add_argument("--native-facing", action="store_true",
                        help="physical only: bracket a focus-neutral WGC frame with native facing and target reads")
    parser.add_argument("--allow-historical-vm", action="store_true",
                        help="explicit archival diagnostic opt-in for retired VMware lab targets")
    parser.add_argument("--host-preview", action="store_true",
                        help="VMware labs only: fast read-only FlaUI host screenshot, never movement authority")
    parser.add_argument("--allow-foreground-change", action="store_true",
                        help="physical capture only: explicitly allow the desktop backend to focus RIFT")
    parser.add_argument("--physical-capture-backend", choices=("wgc",),
                        help="capture directly with the local GPU probe without changing focus")
    parser.add_argument("--physical-pid", type=int,
                        help="physical capture only: exact rift_x64 process ID for multibox sessions")
    parser.add_argument("--preview", action="store_true", help="include a bounded non-authoritative JPEG in the same result")
    parser.add_argument("--preview-width", type=int, default=840)
    parser.add_argument("--preview-detail-crop", nargs=4, type=int,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="with --preview: one SHA-pinned full-frame WebP plus readable JPEG detail")
    args = parser.parse_args(argv)
    try:
        result = observe(args.target, args.expected_host, args.output,
                         native_vitals=args.native_vitals,
                         allow_foreground_change=args.allow_foreground_change,
                         with_preview=args.preview, preview_width=args.preview_width,
                          preview_detail_crop=args.preview_detail_crop,
                          host_preview=args.host_preview,
                          physical_pid=args.physical_pid,
                          historical_vm=args.allow_historical_vm,
                          physical_capture_backend=args.physical_capture_backend,
                          native_facing=args.native_facing)
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
