"""Compare two RR2 actor/model/render pose samples from pinned saved reports.

This is an offline numerical candidate comparison, not proof of player heading.
No live game, VM, reader or movement operation is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from scripts.fresh_native_actor_pose import QUALIFICATION, validate_report
from scripts.fresh_native_xyz import REPORT_MAX_BYTES
from scripts.project_xyz_track import _pairs
from scripts.vm_console_native import Blocked

MATRICES = ("actorMatrix", "modelMatrix", "renderMatrix")


def _utc(value):
    try:
        if not isinstance(value, str) or len(value) > 48:
            raise ValueError("invalid timestamp")
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp not UTC")
        return stamp
    except (ValueError, TypeError, OverflowError):
        raise Blocked("pose-turn-time-invalid") from None


def _load(path):
    summary_path = Path(path).resolve(strict=True)
    if summary_path.name != "summary.json":
        raise Blocked("pose-turn-summary-name-invalid")
    if summary_path.stat().st_size > REPORT_MAX_BYTES:
        raise Blocked("pose-turn-summary-too-large")
    summary = json.loads(summary_path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
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
        raise Blocked("pose-turn-summary-invalid")
    source = (summary_path.parent / "samples.json").resolve(strict=True)
    if Path(summary["sourceReport"]).resolve() != source:
        raise Blocked("pose-turn-source-path-invalid")
    if source.stat().st_size > REPORT_MAX_BYTES:
        raise Blocked("pose-turn-source-too-large")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest().upper() != summary["sourceReportSha256"].upper():
        raise Blocked("pose-turn-source-hash-mismatch")
    report = json.loads(raw, object_pairs_hook=_pairs)
    metrics = validate_report(report, pid=summary["gameProcessId"],
                              ticks=summary["gameProcessStartUtcTicks"])
    expected = dict(metrics, unitKey=metrics["playerKeyDecimal"])
    if (summary.get("metrics") != expected
            or summary["gameSha256"].upper() != report["identity"]["executableSha256"].upper()):
        raise Blocked("pose-turn-summary-source-mismatch")
    start, end, observed = (_utc(report["startedAtUtc"]),
                            _utc(report["completedAtUtc"]),
                            _utc(summary["observedAtUtc"]))
    if not start <= end <= observed:
        raise Blocked("pose-turn-time-order-invalid")
    return summary, report, metrics, start, end


def _angle_delta(before, after):
    if before is None or after is None:
        return None
    # Shortest signed circular difference; a wrap at +/-180 is not a large turn.
    return (after - before + 180.0) % 360.0 - 180.0


def compare(before_path, after_path):
    before, first, a, before_start, before_end = _load(before_path)
    after, last, b, after_start, after_end = _load(after_path)
    identity = ("lab", "vmIdentity", "gameProcessId", "gameProcessStartUtcTicks",
                "gameSha256", "activeAgentInstanceId")
    if any(before[field] != after[field] for field in identity):
        raise Blocked("pose-turn-process-or-controller-changed")
    owner = ("playerKeyDecimal", "playerEntityDecimal", "actorComponentDecimal",
             "positionComponentDecimal")
    if any(a[field] != b[field] for field in owner):
        raise Blocked("pose-turn-player-or-component-changed")
    if before["sourceReportSha256"].upper() == after["sourceReportSha256"].upper():
        raise Blocked("pose-turn-identical-sources")
    if after_start <= before_end:
        raise Blocked("pose-turn-capture-order-invalid")

    changes = {}
    for field in MATRICES:
        lhs, rhs = first[field], last[field]
        before_angle = lhs["planarAngleDegreesCandidate"] if lhs is not None else None
        after_angle = rhs["planarAngleDegreesCandidate"] if rhs is not None else None
        changes[field] = {
            "beforeStatus": lhs["status"] if lhs is not None else None,
            "afterStatus": rhs["status"] if rhs is not None else None,
            "beforeAngleDegreesCandidate": before_angle,
            "afterAngleDegreesCandidate": after_angle,
            "deltaDegreesCandidate": _angle_delta(before_angle, after_angle),
            "rawBitsChanged": ((lhs["rawBits"] if lhs is not None else None)
                               != (rhs["rawBits"] if rhs is not None else None)),
        }
    return {
        "schemaVersion": 1, "status": "candidate-only", "lab": before["lab"],
        "vmIdentity": before["vmIdentity"],
        "activeAgentInstanceId": before["activeAgentInstanceId"],
        "gameSha256": before["gameSha256"],
        "gameProcessId": before["gameProcessId"],
        "gameProcessStartUtcTicks": before["gameProcessStartUtcTicks"],
        "playerKeyDecimal": a["playerKeyDecimal"],
        "beforeSourceSha256": before["sourceReportSha256"].upper(),
        "afterSourceSha256": after["sourceReportSha256"].upper(),
        "timeBetweenCaptureEndsSeconds": (after_end - before_end).total_seconds(),
        "changedMatrixCount": sum(row["rawBitsChanged"] for row in changes.values()),
        "renderStatusBefore": first["renderStatus"],
        "renderStatusAfter": last["renderStatus"],
        "matrices": changes, "actorHeadingQualified": False,
        "qualification": QUALIFICATION,
        "limitation": ("numerical matrix changes only; no independently reviewed turn, "
                       "player body-facing, camera or restart qualification"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(compare(args.before, args.after), allow_nan=False))
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        reason = str(error) if isinstance(error, Blocked) else "pose-turn-unavailable"
        if re.fullmatch(r"[a-z0-9-]{1,100}", reason) is None:
            reason = "pose-turn-unavailable"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
