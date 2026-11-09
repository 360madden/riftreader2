"""Deliver a verified Lab 2 screenshot, optionally with native candidate vitals."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import inspect_lab2_workflow as flow


def safe_bytes(path, limit):
    path = Path(path)
    for part in (path, *path.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("reparse artifact ancestry refused")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("artifact too large")
    return data


def delivery(root, console, *, require_native=True):
    root = flow.output_root(root)
    safe_bytes(root / "workflow-owner.json", 1024 * 1024)
    flow.assert_owned(root)
    if (console.get("phase") != "run" or console.get("status") != "verified-awaiting-visual-review"
            or Path(console.get("output", "")).resolve() != root):
        raise ValueError("workflow result mismatch")
    report_path = root / "report.json"
    metadata_path = root / "capture" / "capture.json"
    report_bytes = safe_bytes(report_path, 1024 * 1024)
    receipt_bytes = safe_bytes(root / "capture-receipt.json", 1024 * 1024)
    metadata_bytes = safe_bytes(metadata_path, 1024 * 1024)
    state_bytes = safe_bytes(root / "state.json", 1024 * 1024)
    state_hash_bytes = safe_bytes(root / "state.sha256.json", 1024 * 1024)
    report, receipt, metadata, state, state_hash = (
        json.loads(data.decode("utf-8-sig")) for data in
        (report_bytes, receipt_bytes, metadata_bytes, state_bytes, state_hash_bytes))
    if (not isinstance(report.get("epoch"), str) or not report["epoch"]
            or not isinstance(report.get("captureId"), str) or not report["captureId"]
            or not isinstance(report.get("capturedAtUtc"), str) or not report["capturedAtUtc"]
            or not isinstance(report.get("target"), dict) or not report["target"]):
        raise ValueError("required report binding missing")
    if (hashlib.sha256(state_bytes).hexdigest().upper() != state_hash.get("sha256")
            or state.get("epoch") != report.get("epoch") or receipt.get("epoch") != report.get("epoch")
            or metadata.get("target") != report.get("target") or state.get("target") != report.get("target")
            or metadata.get("captureId") != report.get("captureId")
            or metadata.get("capturedAtUtc") != report.get("capturedAtUtc")
            or hashlib.sha256(metadata_bytes).hexdigest().upper() != receipt.get("metadataSha256")):
        raise ValueError("artifact binding mismatch")
    image = root / "capture" / "image.bmp"
    if (report.get("status") != "verified-awaiting-visual-review" or report.get("lab") != "lab2"
            or report.get("finalInventory", {}).get("status") != "passed"
            or Path(report.get("image", "")) != image or Path(console.get("image", "")) != image
            or Path(console.get("report", "")) != report_path):
        raise ValueError("report or image path mismatch")
    cleanup = receipt.get("watchdogCleanup", {})
    if (receipt.get("status") != "captured-and-released" or cleanup.get("stopVerified") is not True
            or type(cleanup.get("generation")) is not int or cleanup["generation"] < 1
            or not isinstance(cleanup.get("receipt"), str) or not cleanup["receipt"]):
        raise ValueError("capture cleanup proof missing")
    if not image.is_file() or image.is_symlink() or image.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("image missing or unsafe")
    actual = hashlib.sha256(safe_bytes(image, 10 * 1024 * 1024)).hexdigest().upper()
    if (receipt.get("imageSha256") != actual or metadata.get("savedImage", {}).get("sha256") != actual
            or metadata.get("artifact", {}).get("sha256") != actual):
        raise ValueError("image hash mismatch")
    target = dict(report["target"])
    if type(target.get("processStartUtcTicks")) is int:
        target["processStartUtcTicks"] = str(target["processStartUtcTicks"])
    result = {"status": report["status"], "image": str(image), "imageSha256": actual,
              "report": str(report_path), "workflowSeconds": console["elapsedSeconds"],
              "targetId": "lab2", "workflow": "vmware",
              "captureBackend": "managed-controller/guest-agent",
              "captureId": report["captureId"], "capturedAtUtc": report["capturedAtUtc"],
              "target": target, "cleanupVerified": True,
              "foregroundMayChange": False}
    if not require_native:
        if "nativeRequest" in state or "nativeVitals" in report:
            raise ValueError("capture-only artifacts include native telemetry")
        return result
    native = report.get("nativeVitals")
    if (not isinstance(native, dict) or native.get("mode") != "persistent"
            or native.get("qualification") != "candidate-only; semantics/passive-freshness/restart-unverified; UI review required"):
        raise ValueError("native candidate result missing")
    native = dict(native)
    metrics = dict(native["metrics"])
    if type(metrics.get("unitKey")) is int:
        metrics["unitKey"] = str(metrics["unitKey"])
    native["metrics"] = metrics
    result["nativeVitals"] = native
    return result


class WorkflowBlocked(ValueError):
    """Retain only the guarded workflow's already-sanitized failure fields."""
    def __init__(self, failure):
        self.details = {key: failure[key] for key in ("phase", "errorType", "reason")
                        if isinstance(failure.get(key), str) and len(failure[key]) <= 512}
        super().__init__(self.details.get("reason", "guarded workflow failed"))


def run_inspection(root, *, capture_only=False):
    stdout, stderr = io.StringIO(), io.StringIO()
    command = ["run"] + ([] if capture_only else ["--native-vitals"]) + ["--output", str(root)]
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = flow.main(command)
    if code != 0:
        try:
            failure = json.loads(stderr.getvalue())
            if not isinstance(failure, dict) or failure.get("status") != "blocked":
                failure = {}
        except (TypeError, ValueError):
            failure = {}
        raise WorkflowBlocked(failure)
    console = json.loads(stdout.getvalue())
    result = (delivery(root, console, require_native=False) if capture_only
              else delivery(root, console))
    return result, console


def confirmation_evidence(root):
    """Rebind the independently verified artifacts used to compare two runs."""
    root = flow.output_root(root)
    flow.assert_owned(root)
    def read(name):
        return json.loads(safe_bytes(root / name, 1024 * 1024).decode("utf-8-sig"))
    state, report, receipt = read("state.json"), read("report.json"), read("capture-receipt.json")
    plan_bytes = safe_bytes(root / "managed-host-plan.json", 1024 * 1024)
    if hashlib.sha256(plan_bytes).hexdigest().upper() != state.get("planSha256"):
        raise ValueError("managed plan binding mismatch")
    plan = json.loads(plan_bytes.decode("utf-8-sig"))
    native_bytes = safe_bytes(root / "native-vitals-receipt.json", 1024 * 1024)
    if hashlib.sha256(native_bytes).hexdigest().upper() != read("native-vitals-receipt.sha256.json").get("sha256"):
        raise ValueError("native receipt binding mismatch")
    native = json.loads(native_bytes.decode("utf-8-sig"))
    def timestamp(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() != timedelta(0):
            raise ValueError("non-UTC observation timestamp")
        return parsed
    before, after = timestamp(native["beforeUtc"]), timestamp(native["afterUtc"])
    metrics, completed = flow.validate_native(native["summary"], state, before, after)
    if (metrics != report["nativeVitals"]["metrics"]
            or completed != timestamp(report["nativeVitals"]["completedAtUtc"])
            or native["summary"]["sourceReportSha256"] != report["nativeVitals"]["sourceReportSha256"]):
        raise ValueError("native report binding mismatch")
    source = Path(native["summary"]["sourceReport"])
    source_bytes = safe_bytes(source, flow.vitals.REPORT_MAX_BYTES)
    if hashlib.sha256(source_bytes).hexdigest().upper() != native["summary"]["sourceReportSha256"]:
        raise ValueError("native source changed")
    sample = json.loads(source_bytes.decode("utf-8-sig"))
    started = timestamp(sample["observation"]["startedAtUtc"])
    captured = timestamp(report["capturedAtUtc"])
    if (not receipt.get("requestId") or not report.get("captureId")
            or started > completed or completed > captured):
        raise ValueError("observation identity or chronology invalid")
    return {"plan": plan, "target": state["target"], "vm": state["vmIdentity"],
            "epoch": state["epoch"], "captureId": report["captureId"],
            "requestId": receipt["requestId"], "source": str(source),
            "started": started, "completed": completed, "captured": captured}


def confirm(first, second, initial=None):
    a, b = confirmation_evidence(first), confirmation_evidence(second)
    if initial is not None and a != initial:
        raise ValueError("first observation changed during confirmation")
    if any(a[key] != b[key] for key in ("plan", "target", "vm", "epoch")):
        raise ValueError("confirmation identity pins changed")
    if any(a[key] == b[key] for key in ("captureId", "requestId", "source")):
        raise ValueError("confirmation observation identity reused")
    if not (a["started"] <= a["completed"] <= a["captured"] < b["started"]
            <= b["completed"] <= b["captured"]):
        raise ValueError("confirmation observation timestamps did not advance")


def reviewed_delivery(root):
    root = flow.output_root(root)
    timing = json.loads(safe_bytes(root / "run-timings.json", 1024 * 1024).decode("utf-8-sig"))
    console = {"phase": "run", "status": "verified-awaiting-visual-review", "output": str(root),
               "image": str(root / "capture" / "image.bmp"), "report": str(root / "report.json"),
               "elapsedSeconds": timing["elapsedSeconds"]}
    return delivery(root, console)


def reviewed_snapshot(root, evidence):
    names = ("workflow-owner.json", "run-timings.json", "report.json", "capture-receipt.json",
             "capture/capture.json", "capture/image.bmp", "state.json", "state.sha256.json",
             "managed-host-plan.json", "native-vitals-receipt.json", "native-vitals-receipt.sha256.json")
    paths = [Path(root) / name for name in names] + [Path(evidence["source"])]
    return tuple(hashlib.sha256(safe_bytes(p, 10 * 1024 * 1024)).hexdigest() for p in paths)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--capture-only", action="store_true",
                        help="capture through the managed controller without a native-vitals read")
    parser.add_argument("--confirm-output", type=Path)
    parser.add_argument("--reviewed-output", type=Path)
    parser.add_argument("--reviewed-image-sha256")
    parser.add_argument("--focus", choices=("health", "energy"))
    args = parser.parse_args(argv)
    current = args.output
    try:
        reviewed_args = (args.reviewed_output, args.reviewed_image_sha256, args.focus)
        if args.capture_only and (args.confirm_output is not None or any(x is not None for x in reviewed_args)):
            raise ValueError("capture-only cannot confirm or review native telemetry")
        if any(x is not None for x in reviewed_args) and (any(x is None for x in reviewed_args) or args.confirm_output is not None):
            raise ValueError("reviewed continuation requires output, SHA and focus without confirmation")
        reviewed = args.reviewed_output is not None
        if reviewed:
            first, second = flow.output_root(args.reviewed_output), flow.output_root(args.output)
            if first == second or os.path.lexists(args.output):
                raise ValueError("continuation requires a distinct fresh output root")
            if not re.fullmatch(r"[0-9A-F]{64}", args.reviewed_image_sha256):
                raise ValueError("invalid reviewed image SHA")
            prior = reviewed_delivery(first)
            if prior["imageSha256"] != args.reviewed_image_sha256:
                raise ValueError("reviewed image SHA mismatch")
            initial = confirmation_evidence(first)
            snapshot = reviewed_snapshot(first, initial)
        if args.confirm_output is not None:
            first, second = flow.output_root(args.output), flow.output_root(args.confirm_output)
            if (first == second or os.path.lexists(args.output)
                    or os.path.lexists(args.confirm_output)):
                raise ValueError("confirmation requires two distinct fresh output roots")
        def run(root):
            return run_inspection(root, capture_only=args.capture_only)
        result, first_console = run(args.output)
        if reviewed:
            if reviewed_delivery(first) != prior or reviewed_snapshot(first, initial) != snapshot:
                raise ValueError("reviewed observation changed during continuation")
            confirm(first, second, initial)
            if delivery(second, first_console) != result:
                raise ValueError("continuation delivery changed during confirmation")
            metric = result["nativeVitals"]["metrics"][args.focus]
            qualification = result["nativeVitals"]["qualification"]
            source_sha = result["nativeVitals"]["sourceReportSha256"]
            result = {key: result[key] for key in ("status", "image", "imageSha256", "report", "workflowSeconds")}
            result.update(focus=args.focus, selectedMetric=metric, reviewedOutput=str(first),
                          reviewedImageSha256=args.reviewed_image_sha256, qualification=qualification,
                          nativeSourceReportSha256=source_sha)
            flow.publish(second / "review-decision.json", {"lab": "lab2", "focus": args.focus,
                         "reviewedOutput": str(first), "reviewedImageSha256": args.reviewed_image_sha256,
                         "output": str(second)})
        if args.confirm_output is not None:
            initial = confirmation_evidence(args.output)
            current = args.confirm_output
            other, second_console = run(args.confirm_output)
            if (delivery(args.output, first_console) != result
                    or delivery(args.confirm_output, second_console) != other):
                raise ValueError("observation delivery changed during confirmation")
            confirm(args.output, args.confirm_output, initial)
            result = {"status": "confirmed-awaiting-visual-review", "confirmation": "passed",
                      "observations": [result, other]}
            flow.publish(second / "confirmation.json", result)
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as exc:
        failure = {"status": "blocked", "reason": str(exc), "output": str(current)}
        if isinstance(exc, WorkflowBlocked):
            failure["workflowFailure"] = exc.details
        print(json.dumps(failure), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
