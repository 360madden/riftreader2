"""Read-only AMD physical-RIFT player identity -> XYZ -> identity bracket.

Reuse the existing current-build native readers. No input, window focusing,
addon commands, VM access, or semantic qualification. Every source is retained
with its SHA256; failure leaves any already acquired raw evidence untouched.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_physical_player_context_pair as context
from scripts import physical_rift, project_xyz_track

EXPECTED_HOST = "AMD-DESKTOP"


def require(condition, reason):
    if not condition:
        raise ValueError("physical-player-xyz-" + reason)


def assess(before, position, after, hashes, selection):
    """Validate three caller-SHA-pinned source reports and return candidates only."""
    identity = selection.get("target")
    require(selection.get("status") == "ready" and
            selection.get("ownerHost") == EXPECTED_HOST and
            isinstance(identity, dict), "host-or-selection-unavailable")
    require(all(isinstance(hashes.get(k), str) and len(hashes[k]) == 64
                for k in ("before", "position", "after")) and
            len(set(hashes.values())) == 3, "source-pins-unavailable")
    comparison = context.compare(before, after, hashes["before"], hashes["after"])
    require(comparison["selfKey"]["unchangedCandidate"], "self-key-changed")
    projection = project_xyz_track.project(
        position, max_gap_seconds=300, max_speed_3d=1e100)
    require(projection["unitIdentity"] == "same-sampled-unit-key-candidate" and
            projection["sampledUnitKey"] == comparison["selfKey"]["beforeCandidate"],
            "position-owner-mismatch")

    expected = before["observation"]["identity"]
    for candidate in (after["observation"]["identity"], position["identity"]):
        require(candidate == expected, "process-module-identity-mismatch")
    require(identity.get("processId") == expected["processId"] and
            str(identity.get("processStartUtcTicks")) == str(expected["processStartUtcTicks"]) and
            str(identity.get("executableSha256", "")).upper() == context.BUILD_SHA and
            str(expected["executableSha256"]).upper() == context.BUILD_SHA,
            "selected-process-mismatch")

    # Comparison uses a rounded Python datetime; here preserve full .NET 100ns
    # precision at the three boundaries so touching or overlapping reads fail.
    stamp = physical_rift._utc_tick_order_key
    left_end = stamp(before["observation"]["completedAtUtc"])
    right_start = stamp(after["observation"]["startedAtUtc"])
    rows = position["observations"]
    position_start, position_end = stamp(rows[0]["startedAtUtc"]), stamp(rows[-1]["completedAtUtc"])
    require(left_end < position_start <= position_end < right_start,
            "position-not-bracketed")
    first, last = rows[0], rows[-1]
    planar = math.hypot(last["x"] - first["x"], last["z"] - first["z"])
    require(math.isfinite(planar), "nonfinite-displacement")
    return {
        "schemaVersion": 1, "evidenceKind": "amd-physical-player-xyz-native-bracket/1",
        "status": "candidate-only", "qualification":
            "native same-process self-key/XYZ bracket only; Lua, passive freshness, movement causation and restart unverified",
        "identity": comparison["identity"],
        "sourceSha256": hashes,
        "selfKeyCandidate": comparison["selfKey"]["beforeCandidate"],
        "sampleCount": len(rows),
        "firstPositionCandidate": {a: first[a] for a in ("x", "y", "z")},
        "lastPositionCandidate": {a: last[a] for a in ("x", "y", "z")},
        "withinBracketPlanarDisplacementCandidate": planar,
        "targetCandidate": comparison["target"],
        "observedUtc": {
            "contextBeforeCompleted": before["observation"]["completedAtUtc"],
            "positionFirstStarted": rows[0]["startedAtUtc"],
            "positionLastCompleted": rows[-1]["completedAtUtc"],
            "contextAfterStarted": after["observation"]["startedAtUtc"],
        },
        "limitations": [
            "The native position and player-context readers share game-memory roots, not an independent Lua source.",
            "No proof of unbroken owner identity between non-atomic reads or actual player movement.",
            "Selected-target interpretation, passive refresh and full game restart remain unqualified.",
        ],
    }


def review_files(before, position, after, selection):
    reports = {}
    hashes = {}
    for name, path in (("before", before), ("position", position), ("after", after)):
        reports[name], hashes[name] = context.load(path)
    return assess(reports["before"], reports["position"], reports["after"], hashes, selection)


def collect(pid, output_dir, *, samples=3, interval_ms=250):
    require(socket.gethostname().upper() == EXPECTED_HOST, "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "pid-required")
    require(type(samples) is int and 1 <= samples <= 30 and
            type(interval_ms) is int and 0 <= interval_ms <= 2000,
            "sampling-bounds-invalid")
    selection = physical_rift.select_physical(EXPECTED_HOST, pid)
    require(selection.get("status") == "ready", "initial-selection-" + str(selection.get("reason")))
    require(str(selection["target"].get("executableSha256", "")).upper() == context.BUILD_SHA,
            "unexpected-build")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    names = {"before": output_dir / "context-before.json",
             "position": output_dir / "position.json",
             "after": output_dir / "context-after.json"}
    for name, kind in (("before", "player-context"), ("position", "position"),
                       ("after", "player-context")):
        result = physical_rift.read_native(
            selection, kind, names[name],
            samples=samples if kind == "position" else None,
            interval_ms=interval_ms if kind == "position" else None)
        require(result.get("status") == "complete", name + "-read-" +
                str(result.get("reason", "failed")))
    summary = review_files(names["before"], names["position"], names["after"], selection)
    # Re-select the very same PID/epoch after the reads: an exited/replaced game
    # cannot be described as a complete current-process capture.
    final = physical_rift.select_physical(EXPECTED_HOST, pid)
    require(final.get("status") == "ready" and final.get("target") == selection["target"],
            "final-process-identity-changed")
    receipt = output_dir / "summary.json"
    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return receipt, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid", required=True, type=int)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "artifacts" / ("physical-player-xyz-bracket-" + uuid.uuid4().hex))
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=250)
    args = parser.parse_args(argv)
    try:
        receipt, result = collect(args.physical_pid, args.output_dir,
                                  samples=args.samples, interval_ms=args.interval_ms)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:220]}))
        return 2
    print(json.dumps({"status": result["status"], "receipt": str(receipt),
                      "selfKeyCandidate": result["selfKeyCandidate"],
                      "positionSamples": result["sampleCount"],
                      "planarDisplacementCandidate": result["withinBracketPlanarDisplacementCandidate"],
                      "qualification": result["qualification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
