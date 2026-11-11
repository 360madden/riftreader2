"""Compare two retained AMD-DESKTOP physical-RIFT player-context samples.

Offline only. This compares candidate identities/statuses; it never reads a
process, sends input, or treats a stable key as qualified player identity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.physical_rift import _native_values

BUILD_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"
MAX_BYTES = 8_000_000
QUALIFICATION = "candidate-only; same-epoch passive comparison, not live self/target qualification"


def _require(ok, reason):
    if not ok:
        raise ValueError("physical-context-pair-" + reason)


def load(path, expected_sha256=None):
    """Return a pinned report and its actual source SHA256."""
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "source-unavailable")
    size = path.stat().st_size
    _require(0 < size <= MAX_BYTES, "source-size-invalid")
    raw = path.read_bytes()
    _require(len(raw) == size, "source-changed")
    digest = hashlib.sha256(raw).hexdigest().upper()
    if expected_sha256 is not None:
        _require(type(expected_sha256) is str and
                 expected_sha256.upper() == digest, "source-sha-mismatch")
    try:
        report = json.loads(raw.decode("utf-8-sig"),
                            parse_constant=lambda _: _require(False, "nonfinite-json"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("physical-context-pair-invalid-json") from exc
    _require(type(report) is dict, "invalid-report")
    return report, digest


def _utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.utcoffset() == timedelta(0), "non-utc-observation")
        return parsed
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("physical-context-pair-invalid-time") from exc


def _sample(report):
    _require(report.get("status") == "complete", "incomplete-report")
    # Reuse the current native value-contract validation rather than accepting
    # raw labels without checking their accompanying key/status evidence.
    values = _native_values("player-context", report)
    identity = report.get("observation", {}).get("identity")
    _require(type(identity) is dict, "missing-identity")
    _require(type(identity.get("processId")) is int and 0 < identity["processId"] < 2**31
             and type(identity.get("processStartUtcTicks")) is int
             and 0 < identity["processStartUtcTicks"] < 2**63
             and type(identity.get("moduleBaseAddress")) is int
             and identity["moduleBaseAddress"] > 0
             and type(identity.get("moduleSize")) is int and identity["moduleSize"] > 0
             and isinstance(identity.get("executablePath"), str)
             and identity["executablePath"].replace("/", "\\").lower().endswith("\\rift_x64.exe")
             and isinstance(identity.get("executableSha256"), str)
             and identity["executableSha256"].upper() == BUILD_SHA,
             "invalid-source-identity")
    observation = report["observation"]
    start, end = _utc(observation.get("startedAtUtc")), _utc(observation.get("completedAtUtc"))
    _require(end >= start, "negative-capture-duration")
    return values, identity, start, end


def _target_sequence(before, after):
    """Include within-burst transitions; unavailable IDs never become selections."""
    def rows(report):
        if report.get("contractVersion") == "native-current-player-context-candidate-burst/1":
            return report["observations"]
        return [report["observation"]]

    left, right = rows(before), rows(after)
    edges = list(zip(left, left[1:])) + [(left[-1], right[0])] + list(zip(right, right[1:]))
    comparable = changed = owner_mismatch = 0
    for earlier, later in edges:
        if earlier["unitKey"] != later["unitKey"]:
            owner_mismatch += 1
            continue
        first, second = earlier["targetUnitIdCandidate"], later["targetUnitIdCandidate"]
        if first is not None and second is not None:
            comparable += 1
            changed += first != second
    return {
        "beforeSamples": len(left), "afterSamples": len(right),
        "adjacentPairs": len(edges),
        "comparableAdjacentPairsCandidate": comparable,
        "changedAdjacentPairsCandidate": changed,
        "unavailableOrUnqualifiedPairs": len(edges) - comparable,
        "differentSelfOwnerPairs": owner_mismatch,
    }


def compare(before, after, before_sha256, after_sha256):
    _require(before_sha256 != after_sha256, "reused-source")
    a, a_id, a_start, a_end = _sample(before)
    b, b_id, b_start, b_end = _sample(after)
    _require(a_id == b_id, "different-process-epoch-or-module")
    _require(b_start >= a_end, "overlapping-or-reordered-observations")

    first = a["target"]["unitIdCandidate"]
    second = b["target"]["unitIdCandidate"]
    both_available = first is not None and second is not None
    self_stable = a["unitKey"] == b["unitKey"]
    # A different self owner invalidates a target-selection inference, even
    # when both raw target getters happened to produce nonzero candidates.
    target_changed = first != second if both_available and self_stable else None
    return {
        "status": "complete",
        "qualification": QUALIFICATION,
        "identity": {
            "host": "AMD-DESKTOP", "processId": a_id["processId"],
            "processStartUtcTicks": str(a_id["processStartUtcTicks"]),
            "executableSha256": BUILD_SHA,
        },
        "sourceSha256": {"before": before_sha256, "after": after_sha256},
        "beforeCompletedAtUtc": before["observation"]["completedAtUtc"],
        "afterCompletedAtUtc": after["observation"]["completedAtUtc"],
        "elapsedBetweenSamplesSeconds": (b_end - a_end).total_seconds(),
        "selfKey": {
            "beforeCandidate": a["unitKey"],
            "afterCandidate": b["unitKey"],
            "unchangedCandidate": self_stable,
        },
        "target": {
            "beforeStatus": a["target"]["status"],
            "afterStatus": b["target"]["status"],
            "beforeIdCandidate": first,
            "afterIdCandidate": second,
            "selectionChangedCandidate": target_changed,
        },
        "targetSequenceCandidate": _target_sequence(before, after),
        "level": {"beforeRawCandidate": a["level"]["rawCandidate"],
                  "afterRawCandidate": b["level"]["rawCandidate"]},
        "calling": {"before": a["calling"]["nameCandidate"],
                    "after": b["calling"]["nameCandidate"]},
        "limitations": [
            "Same process epoch and stable native key do not establish Lua/API player identity.",
            "A zero/unknown target getter does not establish that no target was selected.",
            "A changed target candidate alone cannot prove a user-initiated selection change.",
            "No controlled changed-state or restart qualification was performed.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--before-sha256")
    parser.add_argument("--after-sha256")
    args = parser.parse_args(argv)
    try:
        a, sha_a = load(args.before, args.before_sha256)
        b, sha_b = load(args.after, args.after_sha256)
        result = compare(a, b, sha_a, sha_b)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:200]}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
