"""Compare two saved current-build selected-target reports without contacting RIFT.

This is an offline diagnostic for candidate health, energy and mana changes.
A numerical delta is not proof of semantics, passive freshness or restart recovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sample_current_native_selected_target import selected_target_values

MAX_REPORT_BYTES = 8_000_000
FIELDS = ("health", "energy", "mana")


def _fail(code: str):
    raise ValueError("native-target-compare-" + code)


def _utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
            _fail("timestamp-invalid")
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("native-target-compare-timestamp-invalid") from exc


def load_report(path: Path):
    """Load bounded raw evidence; return the untouched report and its byte hash."""
    if path.is_symlink() or not path.is_file():
        _fail("source-unavailable")
    size = path.stat().st_size
    if not 0 < size <= MAX_REPORT_BYTES:
        _fail("source-size-invalid")
    raw = path.read_bytes()
    if len(raw) != size:
        _fail("source-changed")
    try:
        report = json.loads(raw.decode("utf-8-sig"),
                            parse_constant=lambda _: _fail("nonfinite-json"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("native-target-compare-json-invalid") from exc
    return report, hashlib.sha256(raw).hexdigest().upper()


def compare_reports(before: dict, after: dict, *, pid: int, ticks: int,
                    before_sha256: str, after_sha256: str) -> dict:
    """Only same-player, nonoverlapping, same-target candidates yield deltas."""
    if (type(pid) is not int or pid <= 0 or type(ticks) is not int or ticks <= 0):
        _fail("identity-invalid")
    for sha in (before_sha256, after_sha256):
        if not isinstance(sha, str) or re.fullmatch(r"[0-9A-Fa-f]{64}", sha) is None:
            _fail("hash-invalid")
    first = selected_target_values(before, pid=pid, ticks=ticks)
    second = selected_target_values(after, pid=pid, ticks=ticks)
    if before_sha256.upper() == after_sha256.upper():
        _fail("identical-source")
    if first["selfUnitKey"] != second["selfUnitKey"]:
        _fail("player-changed")
    if _utc(first["completedAtUtc"]) >= _utc(second["startedAtUtc"]):
        _fail("observations-overlap")

    first_present = first["status"] == "candidate"
    second_present = second["status"] == "candidate"
    same_target = (first_present and second_present
                   and first["unitKey"] == second["unitKey"])
    if same_target:
        continuity = "same-target-candidate"
    elif first_present and second_present:
        continuity = "different-target-candidate"
    elif not first_present and second_present:
        continuity = "target-acquired-candidate"
    elif first_present and not second_present:
        continuity = "target-lost-candidate"
    else:
        continuity = "target-unavailable"

    resources = {}
    for field in FIELDS:
        b, a = first[field], second[field]
        comparable = (same_target and b["status"] == "calculated-candidate"
                      and a["status"] == "calculated-candidate"
                      and type(b["current"]) is int and type(a["current"]) is int
                      and type(b["maximum"]) is int and type(a["maximum"]) is int)
        resources[field] = {
            "before": b, "after": a,
            "deltaCurrentCandidate": a["current"] - b["current"] if comparable else None,
            "deltaMaximumCandidate": a["maximum"] - b["maximum"] if comparable else None,
            "changedCurrentCandidate": a["current"] != b["current"] if comparable else None,
        }
    return {
        "schemaVersion": 1,
        "status": "candidate-comparison",
        "mode": "offline-saved-report",
        "gameProcessId": pid,
        "gameProcessStartUtcTicks": ticks,
        "samePlayer": True,
        "targetContinuity": continuity,
        "beforeSourceSha256": before_sha256.upper(),
        "afterSourceSha256": after_sha256.upper(),
        "beforeTarget": first,
        "afterTarget": second,
        "resources": resources,
        "qualification": ("source-hashed offline candidate comparison; target/resource "
                          "semantics, passive freshness and restart recovery unqualified"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-ticks", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        before, first_sha = load_report(args.before)
        after, second_sha = load_report(args.after)
        result = compare_reports(before, after, pid=args.pid,
                                 ticks=args.start_ticks,
                                 before_sha256=first_sha, after_sha256=second_sha)
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc)
        if re.fullmatch(r"native-target-compare-[a-z-]+", reason) is None:
            reason = "native-target-compare-invalid-report"
        print(json.dumps({"status": "blocked", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
