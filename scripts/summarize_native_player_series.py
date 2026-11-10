"""Summarize an ordered series of retained native player reads; strictly offline.

Usage:
  python scripts/summarize_native_player_series.py --reads read1.json read2.json read3.json

Each adjacent pair must belong to the same game, VM, agent and player, contain
the same selected fields, and advance its original report timestamps. Derived
XYZ travel, coordinate-relative travel course and resource deltas are candidates,
not independent movement or character-facing/turn proof.
This tool never contacts RIFT, VMware, control agents or the network.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import compare_native_player_reads as comparison

MAX_READS = 32


def summarize(reads: list[tuple[dict, str]]) -> dict:
    if not 2 <= len(reads) <= MAX_READS:
        raise ValueError("native-player-series-length-invalid")

    # Reuse the stricter existing pair validator rather than maintaining
    # another parser or weakening exact session/owner/source checks.
    pairs = [
        comparison.compare(a, b, a_sha, b_sha)
        for (a, a_sha), (b, b_sha) in zip(reads, reads[1:])
    ]
    endpoints = comparison.compare(reads[0][0], reads[-1][0],
                                   reads[0][1], reads[-1][1])
    fields = endpoints["fieldsCompared"]
    for field in fields:
        report_shas = [
            comparison._sha(readout[field]["sourceReportSha256"])
            for readout, _ in reads
        ]
        if len(set(report_shas)) != len(report_shas):
            raise ValueError("native-player-series-repeated-" + field + "-report")

    segments = []
    lengths = []
    previous_course = None
    for index, result in enumerate(pairs, start=1):
        position = result["comparison"].get("position")
        length = (position.get("horizontalXZDistanceCandidate")
                  if position is not None else None)
        if length is not None:
            lengths.append(length)
        # Travel direction is measured in the XZ coordinate plane: 0 degrees
        # points along +X and 90 along +Z. It is NOT the player's facing/yaw.
        delta = position.get("deltaCandidate") if position is not None else None
        course = (math.degrees(math.atan2(delta["z"], delta["x"])) % 360
                  if delta is not None and length is not None and length > 0
                  else None)
        course_change = ((course - previous_course + 180) % 360 - 180
                         if course is not None and previous_course is not None
                         else None)
        segments.append({
            "index": index,
            "beforeSourceSha256": result["beforeSourceSha256"],
            "afterSourceSha256": result["afterSourceSha256"],
            "sourceProvenance": result["sourceProvenance"],
            "positionStatus": position["status"] if position is not None else "not-selected",
            "horizontalXZDistanceCandidate": length,
            "travelCourseDegreesCandidate": course,
            "travelCourseChangeDegreesCandidate": course_change,
        })
        previous_course = course

    position_summary = None
    if "position" in fields:
        all_valid = len(lengths) == len(pairs)
        total = None
        if all_valid:
            try:
                total = math.fsum(lengths)
                if not math.isfinite(total):
                    total = None
            except (OverflowError, ValueError):
                total = None
        net = endpoints["comparison"]["position"]
        position_summary = {
            "status": ("complete-candidate" if total is not None
                       else "incomplete-segment-candidates"),
            "validSegmentCount": len(lengths),
            "segmentCount": len(pairs),
            "cumulativeHorizontalXZDistanceCandidate": total,
            "netHorizontalXZDistanceCandidate": net["horizontalXZDistanceCandidate"],
            "netDeltaCandidate": net["deltaCandidate"],
            "maximumSegmentXZDistanceCandidate": max(lengths) if lengths else None,
        }

    return {
        "schemaVersion": 1,
        "status": "candidate-only",
        "mode": "offline-retained-native-series",
        "targetId": endpoints["targetId"],
        "unitKey": endpoints["unitKey"],
        "fieldsCompared": fields,
        "readCount": len(reads),
        "firstSourceSha256": endpoints["beforeSourceSha256"],
        "lastSourceSha256": endpoints["afterSourceSha256"],
        "segments": segments,
        "positionSummary": position_summary,
        "vitalsEndpointDeltasCandidate": endpoints["comparison"].get("vitals"),
        "qualification": (
            "same VM/game/agent/player and strictly advancing retained source reports; "
            "candidate arithmetic only; travel course is +X toward +Z, NOT "
            "player-facing yaw; NOT independent movement proof or turn proof, "
            "passive freshness, qualified field semantics, or restart recovery"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reads", type=Path, nargs="+", required=True,
                        help="2-32 retained native player JSON readouts, ordered oldest first")
    args = parser.parse_args(argv)
    try:
        if not 2 <= len(args.reads) <= MAX_READS:
            raise ValueError("native-player-series-length-invalid")
        reads = [comparison.load(path) for path in args.reads]
        result = summarize(reads)
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps({"status": "blocked", "reason": "native-player-series-unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
