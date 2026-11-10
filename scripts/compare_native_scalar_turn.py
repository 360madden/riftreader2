"""Compare two saved, source-hash-verified native smoothed-scalar captures offline.

No input, game access, heading inference or implicit process/owner fallback.
Each input is a summary.json emitted by fresh_native_smoothed_scalar.query.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from scripts.fresh_native_smoothed_scalar import validate_report, QUALIFICATION
from scripts.fresh_native_xyz import REPORT_MAX_BYTES
from scripts.vm_console_native import Blocked


FIELDS = ("currentCandidate", "sourceCandidate", "targetCandidate", "factorCandidate")


def _utc(value):
    try:
        if not isinstance(value, str) or len(value) > 48:
            raise ValueError("invalid timestamp")
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp not UTC")
        return timestamp
    except (ValueError, TypeError, OverflowError):
        raise Blocked("scalar-turn-time-invalid") from None


def _load(path):
    summary_path = Path(path).resolve(strict=True)
    if summary_path.name != "summary.json":
        raise Blocked("scalar-turn-summary-name-invalid")
    if summary_path.stat().st_size > REPORT_MAX_BYTES:
        raise Blocked("scalar-turn-summary-too-large")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (not isinstance(summary, dict) or summary.get("schemaVersion") != 1
            or summary.get("status") != "candidate-only"
            or summary.get("lab") not in ("lab1", "lab2")
            or summary.get("transport") != "persistent-control-agent"
            or not isinstance(summary.get("vmIdentity"), dict)
            or type(summary.get("gameProcessId")) is not int
            or type(summary.get("gameProcessStartUtcTicks")) is not int
            or not isinstance(summary.get("gameSha256"), str)
            or not isinstance(summary.get("activeAgentInstanceId"), str)
            or re.fullmatch(r"[0-9a-f]{32}", summary["activeAgentInstanceId"]) is None
            or not isinstance(summary.get("sourceReport"), str)
            or not isinstance(summary.get("sourceReportSha256"), str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", summary["sourceReportSha256"]) is None):
        raise Blocked("scalar-turn-summary-invalid")
    source = (summary_path.parent / "samples.json").resolve(strict=True)
    if Path(summary["sourceReport"]).resolve() != source:
        raise Blocked("scalar-turn-source-path-invalid")
    if source.stat().st_size > REPORT_MAX_BYTES:
        raise Blocked("scalar-turn-source-too-large")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest().upper() != summary["sourceReportSha256"].upper():
        raise Blocked("scalar-turn-source-hash-mismatch")
    report = json.loads(raw)
    metrics = validate_report(report, pid=summary["gameProcessId"],
                              ticks=summary["gameProcessStartUtcTicks"])
    if (summary.get("metrics") != metrics
            or summary["gameSha256"].upper() != report["identity"]["executableSha256"].upper()):
        raise Blocked("scalar-turn-summary-source-mismatch")
    start, end = _utc(report["startedAtUtc"]), _utc(report["completedAtUtc"])
    observed = _utc(summary["observedAtUtc"])
    if not start <= end <= observed:
        raise Blocked("scalar-turn-time-order-invalid")
    return summary, report, metrics, start, end


def compare(before_path, after_path):
    before, initial, a, before_start, before_end = _load(before_path)
    after, final, b, after_start, after_end = _load(after_path)
    identity = ("lab", "vmIdentity", "gameProcessId", "gameProcessStartUtcTicks",
                "gameSha256", "activeAgentInstanceId")
    if any(before[k] != after[k] for k in identity):
        raise Blocked("scalar-turn-process-or-controller-changed")
    if (a["unitKey"] != b["unitKey"] or a["playerEntityDecimal"] != b["playerEntityDecimal"]
            or a["componentAddressDecimal"] != b["componentAddressDecimal"]):
        raise Blocked("scalar-turn-player-or-component-changed")
    if after_start < before_end:
        raise Blocked("scalar-turn-capture-order-invalid")
    changes = {}
    for index, name in enumerate(FIELDS):
        left, right = a[name], b[name]
        changes[name] = {
            "before": left, "after": right, "deltaCandidate": right - left,
            "rawBitsBefore": initial["rawBits"][index],
            "rawBitsAfter": final["rawBits"][index],
            "rawBitsChanged": initial["rawBits"][index] != final["rawBits"][index]
        }
    return {"schemaVersion": 1, "status": "candidate-only",
            "lab": before["lab"], "gameProcessId": before["gameProcessId"],
            "gameProcessStartUtcTicks": before["gameProcessStartUtcTicks"],
            "playerKeyDecimal": a["unitKey"],
            "beforeSourceSha256": before["sourceReportSha256"].upper(),
            "afterSourceSha256": after["sourceReportSha256"].upper(),
            "timeBetweenCaptureEndsSeconds": (after_end - before_end).total_seconds(),
            "changedFieldCount": sum(row["rawBitsChanged"] for row in changes.values()),
            "fields": changes, "headingQualified": False,
            "qualification": QUALIFICATION,
            "limitation": "raw numerical change only; no independently verified turn, body facing or camera response"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(compare(args.before, args.after), allow_nan=False))
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        reason = str(error) if isinstance(error, Blocked) else "scalar-turn-unavailable"
        if re.fullmatch(r"[a-z0-9-]{1,100}", reason) is None:
            reason = "scalar-turn-unavailable"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
