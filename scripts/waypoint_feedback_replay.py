"""Historical, input-free replay of one retained continuous route leg.

Requires hash-pinned route, checkpoint, externally pinned go run receipt and its single-record
native input receipt. No source here establishes current identity or freshness.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.waypoint_feedback_window import assess_leg_feedback
from scripts.waypoint_progress import RouteProgress


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite-or-nonnumeric-value")
    return value


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("invalid-historical-timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("historical-timestamp-requires-timezone")
    return parsed


def _xyz(value):
    if not isinstance(value, dict):
        raise ValueError("measured-XYZ-required")
    return {axis: _number(value.get(axis)) for axis in "xyz"}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-JSON-key")
        result[key] = value
    return result


def _sha256(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("explicit-SHA256-required")
    return value.lower()


def _positive_ticks(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value) and int(value) > 0:
        return int(value)
    raise ValueError("positive-process-start-ticks-required")


def _process_identity(document, machine_key, build_key):
    if not isinstance(document, dict):
        raise ValueError("retained-identity-object-required")
    machine = document.get(machine_key)
    pid = document.get("processId")
    if not isinstance(machine, str) or not machine.strip():
        raise ValueError("retained-machine-required")
    if type(pid) is not int or pid <= 0:
        raise ValueError("positive-integer-process-id-required")
    return (machine.casefold(), _sha256(document.get(build_key)), pid,
            _positive_ticks(document.get("processStartUtcTicks")))


def read_pinned(path, expected_sha256):
    """Read exactly one JSON document (including one-record JSONL)."""
    expected_sha256 = _sha256(expected_sha256)
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError("source-hash-mismatch")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-JSON")))
    if not isinstance(value, dict):
        raise ValueError("source-object-required")
    return value


def assess_retained_leg(route, checkpoint, run, native, *, route_sha256):
    """Pure diagnosis of a single final leg; never changes the supplied cursor."""
    if not all(isinstance(doc, dict) for doc in (route, checkpoint, run, native)):
        raise ValueError("retained-source-objects-required")
    binding = run.get("calibrationBinding")
    if not isinstance(binding, dict):
        raise ValueError("retained-runtime-binding-required")
    runtime = binding.get("runtimeIdentity")
    if not isinstance(runtime, dict):
        raise ValueError("retained-runtime-identity-required")
    runtime_identity = _process_identity(runtime, "machine", "gameBuildSha256")
    cursor = RouteProgress._from_payload(checkpoint, route, runtime)
    if (len(cursor.points) != 2 or cursor.next_index != 1 or cursor.start is None
            or any(p["y"] is None for p in cursor.route_view)):
        raise ValueError("one-unfinished-two-point-XYZ-leg-required")
    if run.get("operation") != "go":
        raise ValueError("externally-pinned-go-receipt-required")
    if (_sha256(run.get("externalRouteSha256")) != _sha256(route_sha256)
            or run.get("movementEngine") != "continuous"
            or run.get("inputReleaseFault") is not False
            or not isinstance(run.get("requestId"), str) or not run["requestId"]):
        raise ValueError("retained-route-operation-binding-required")
    failure = run.get("failure")
    if run.get("status") == "halted":
        if not isinstance(failure, dict) or failure.get("status") != "halted":
            raise ValueError("retained-halt-required")
    elif run.get("status") != "completed" or failure is not None:
        raise ValueError("STOP-or-unqualified-outcome")
    if (native.get("kind") != "native-continuous-move"
            or type(native.get("version")) is not int or native["version"] != 1
            or native.get("status") not in {"arrived", "halted"}
            or (native["status"] == "halted") != (run["status"] == "halted")
            or native.get("releaseSucceeded") is not True
            or native.get("desktopInputsDown") != []
            or native.get("inputSent") is not True
            or native.get("survivalInterrupt") is not False
            or native.get("survivalMode") != "disabled"
            or native.get("controlPauseVersion") is not None
            or native.get("pathTruncated") is not False
            or native.get("passedWaypoints") != []
            or native.get("controlPauseReceipts") not in (None, [])
            or str(native.get("reason", "")).startswith("survival-")):
        raise ValueError("released-single-leg-outcome-required")
    target = native.get("target")
    if not isinstance(target, dict):
        raise ValueError("native-target-required")
    if runtime_identity != _process_identity(target, "machineName", "executableSha256"):
        raise ValueError("retained-target-or-process-epoch-mismatch")
    if (not isinstance(runtime.get("unitKey"), str) or not runtime["unitKey"]
            or not isinstance(native.get("playerKey"), str)
            or runtime["unitKey"] != native["playerKey"]):
        raise ValueError("retained-player-mismatch")
    view = cursor.route_view
    goal = _xyz(native.get("goal"))
    if goal != {a: view[1][a] for a in "xyz"}:
        raise ValueError("native-goal-does-not-match-unfinished-leg")
    events = native.get("keySendEvents")
    if not isinstance(events, list) or len(events) != 2:
        raise ValueError("one-continuous-W-hold-required")
    windows = []
    for event, phase in zip(events, ("key-down", "key-up")):
        if (not isinstance(event, dict) or not isinstance(event.get("key"), str)
                or event["key"].upper() != "W"
                or event.get("phase") != phase or event.get("inserted") is not True):
            raise ValueError("successful-W-only-events-required")
        start, end = _stamp(event.get("callStartedAtUtc")), _stamp(event.get("callCompletedAtUtc"))
        if end < start:
            raise ValueError("invalid-input-call-window")
        windows.append((start, end))
    if windows[0][1] >= windows[1][0]:
        raise ValueError("overlapping-input-call-windows")
    path = native.get("path")
    if (not isinstance(path, list) or not 3 <= len(path) <= 64
            or type(native.get("readCount")) is not int or native["readCount"] != len(path)):
        raise ValueError("complete-bounded-path-required")
    poses = [(_stamp(p.get("observedAtUtc")), _xyz(p)) for p in path if isinstance(p, dict)]
    if len(poses) != len(path) or any(a[0] >= b[0] for a, b in zip(poses, poses[1:])):
        raise ValueError("increasing-historical-path-required")
    for point in path:
        _number(point.get("bearing"))
    # Validate all historical geometry, even observations outside the hold.
    if any(abs(pos["y"] - view[0]["y"]) > 1.0 for _, pos in poses):
        raise ValueError("path-height-context-mismatch")
    # This first slice supports constant-height legs only.
    if view[0]["y"] != view[1]["y"]:
        raise ValueError("constant-height-leg-required")
    if _xyz(native.get("position")) != poses[-1][1]:
        raise ValueError("final-path-position-mismatch")
    if math.dist(tuple(poses[0][1][a] for a in "xyz"),
                 tuple(view[0][a] for a in "xyz")) > .30:
        raise ValueError("path-does-not-start-at-unfinished-leg")
    selected = [(t, p) for t, p in poses if windows[0][1] <= t <= windows[1][0]]
    if len(selected) < 3:
        raise ValueError("insufficient-W-only-observations")
    origin = selected[0][0]
    samples = [{"routeHash": cursor.route_hash, "legIndex": cursor.next_index,
                "elapsedSeconds": (t-origin).total_seconds(), "position": p} for t, p in selected]
    result = assess_leg_feedback(cursor, samples, translation_expected=True)
    return dict(result, schema="rr2.retained-leg-feedback/1", candidateOnly=True,
                automaticRetry=False, requiresExplicitNewRun=True,
                timingBasis="historical-aware-UTC-differences",
                currentIdentityVerified=False, currentFreshnessVerified=False,
                qualification="Historical geometry diagnosis; UTC differences are not monotonic timing proof. "
                              "No current admission, collision proof, route promotion or action authority.")


def replay(*, route, route_sha256, checkpoint, checkpoint_sha256,
           run_receipt, run_receipt_sha256, native_receipt, native_receipt_sha256):
    refs = {"route": (route, route_sha256), "checkpoint": (checkpoint, checkpoint_sha256),
            "runReceipt": (run_receipt, run_receipt_sha256),
            "nativeReceipt": (native_receipt, native_receipt_sha256)}
    docs = {key: read_pinned(*ref) for key, ref in refs.items()}
    retained = docs["runReceipt"].get("inputReceiptPath")
    if not isinstance(retained, str) or Path(retained).resolve() != Path(native_receipt).resolve():
        raise ValueError("native-receipt-reference-mismatch")
    result = assess_retained_leg(docs["route"], docs["checkpoint"], docs["runReceipt"],
                                 docs["nativeReceipt"], route_sha256=route_sha256)
    result["sources"] = {key: {"path": str(Path(path).resolve()), "sha256": sha.lower()}
                         for key, (path, sha) in refs.items()}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("route", "checkpoint", "run-receipt", "native-receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = replay(**vars(args))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc), "inputSent": False,
                          "candidateOnly": True, "automaticRetry": False,
                          "requiresExplicitNewRun": True}, allow_nan=False))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
