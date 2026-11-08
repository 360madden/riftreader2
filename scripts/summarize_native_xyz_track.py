"""Summarize a retained current-native XYZ report, offline and candidate-only.

Reuses the existing one-report projector. Segments break at every projector
boundary; no distance is manufactured across gaps or suspected teleport jumps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.project_xyz_track import MAX_BYTES, _pairs, project


def summarize(report, *, max_gap_seconds, max_speed_3d):
    track = project(report, max_gap_seconds=max_gap_seconds, max_speed_3d=max_speed_3d)
    segments = []
    current = None

    def finish():
        if current is None:
            return
        count = current["acceptedPairCount"]
        current["distanceStatus"] = "candidate" if count else "unavailable-no-accepted-pair"
        planar_steps, steps_3d = current.pop("_planar"), current.pop("_3d")
        current["pathPlanar"] = math.fsum(planar_steps) if count else None
        current["path3d"] = math.fsum(steps_3d) if count else None
        if count:
            current["netDisplacement"] = {
                axis: current["endXyz"][axis] - current["startXyz"][axis] for axis in "xyz"
            }
            current["netPlanar"] = math.hypot(current["netDisplacement"]["x"], current["netDisplacement"]["z"])
            current["net3d"] = math.hypot(*current["netDisplacement"].values())
            values = (current["pathPlanar"], current["path3d"], current["netPlanar"],
                      current["net3d"], *current["netDisplacement"].values())
            if not all(math.isfinite(v) for v in values):
                raise ValueError("segment calculation overflow")
        else:
            current["netDisplacement"] = current["netPlanar"] = current["net3d"] = None
        segments.append(current)

    for point in track["observations"]:
        reduction = point["reduction"]
        if reduction["status"] == "boundary":
            finish()
            current = {"firstIndex": point["index"], "lastIndex": point["index"],
                       "startReason": reduction["reason"], "startXyz": point["xyz"],
                       "endXyz": point["xyz"], "acceptedPairCount": 0, "_planar": [], "_3d": []}
        elif reduction["status"] == "motion-candidate" and current is not None:
            current["lastIndex"] = point["index"]
            current["endXyz"] = point["xyz"]
            current["acceptedPairCount"] += 1
            current["_planar"].append(reduction["planar_distance"])
            current["_3d"].append(reduction["distance_3d"])
        else:
            raise ValueError("unexpected projector status; no summary")
    finish()
    identity = dict(track["processIdentity"])
    # .NET UTC ticks exceed the exact integer range of JavaScript/JSON clients.
    identity["processStartUtcTicks"] = str(identity["processStartUtcTicks"])
    return {
        "schemaVersion": 1, "contractVersion": "native-xyz-segment-summary-candidate/1",
        "status": "candidate-only", "processIdentity": identity,
        "unitIdentity": track["unitIdentity"], "sampledUnitKey": track["sampledUnitKey"],
        "sampledUnitIdCandidate": track["sampledUnitIdCandidate"],
        "freshness": track["freshness"], "worldIdentity": track["worldIdentity"],
        "zoneIdentity": track["zoneIdentity"], "zoneBoundaries": track["zoneBoundaries"],
        "coordinateUnits": track["coordinateUnits"], "thresholds": track["thresholds"],
        "segments": segments,
        "overallPathStatus": "available-single-segment-candidate" if len(segments) == 1
                             and segments[0]["acceptedPairCount"] else "unavailable-boundary-or-single-sample",
        "overallPath3d": segments[0]["path3d"] if len(segments) == 1 else None,
        "limitations": ["Sampled straight-line steps are candidate arithmetic, not total actual travel.",
                        "No continuity, movement, source freshness, player semantics, zone or heading proof.",
                        "Speed thresholds are caller supplied in unverified source units.",
                        "No path is inferred across a gap or candidate speed boundary."]
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--max-gap-seconds", type=float, required=True)
    parser.add_argument("--max-speed-3d", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        with args.report.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("input report exceeds size limit")
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
        output = summarize(value, max_gap_seconds=args.max_gap_seconds, max_speed_3d=args.max_speed_3d)
        output["sourceSha256"] = hashlib.sha256(data).hexdigest().upper()
        print(json.dumps(output, allow_nan=False))
        return 0
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
