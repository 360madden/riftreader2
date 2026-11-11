#!/usr/bin/env python3
"""Preview signed distance change from a retained physical native XYZ burst to one named anchor.

Offline, read-only arithmetic only: no live process lookup, controls, or navigation authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import navigation_anchors as anchors
from scripts.movement_controller import Position, planar_distance


class RoutePreviewError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RoutePreviewError(reason)


def _read_native(path: Path) -> tuple[dict, str]:
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 16 * 1024 * 1024,
            "native report missing, symbolic, or oversized")
    raw = path.read_bytes()
    try:
        report = json.loads(raw.decode("utf-8-sig"),
                            object_pairs_hook=anchors._unique_json_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                RoutePreviewError("native report contains nonfinite JSON")))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise RoutePreviewError("native report JSON invalid") from error
    require(isinstance(report, dict)
            and report.get("schemaVersion") == 1
            and report.get("contractVersion") == "native-current-position-candidate-samples/1"
            and report.get("status") == "complete"
            and report.get("qualification") ==
            "candidate-only-not-passive-fresh-or-player-semantic-qualified",
            "not a completed native position candidate report")
    identity = report.get("identity")
    require(isinstance(identity, dict)
            and type(identity.get("processId")) is int and identity["processId"] > 0
            and type(identity.get("processStartUtcTicks")) is int
            and 0 < identity["processStartUtcTicks"] < 2**63
            and isinstance(identity.get("executablePath"), str)
            and identity["executablePath"].lower().endswith("rift_x64.exe")
            and isinstance(identity.get("executableSha256"), str)
            and anchors.SHA256.fullmatch(identity["executableSha256"]) is not None
            and isinstance(report.get("sourceBuildSha256"), str)
            and report["sourceBuildSha256"].casefold() ==
            identity["executableSha256"].casefold(),
            "native position process/build identity invalid")
    observations = report.get("observations")
    requested, completed = report.get("requestedSamples"), report.get("completedSamples")
    require(isinstance(observations, list) and 1 <= len(observations) <= 30
            and type(requested) is int and requested == len(observations)
            and type(completed) is int and completed == len(observations),
            "native position burst is incomplete")
    previous_end = None
    unit_key = None
    positions = []
    for index, row in enumerate(observations, start=1):
        require(isinstance(row, dict) and type(row.get("index")) is int
                and row["index"] == index, "native position sample index invalid")
        key = row.get("unitKey")
        require(isinstance(key, str) and key.isdecimal()
                and 0 < int(key) < 2**64 and str(int(key)) == key,
                "native position unit key invalid")
        if unit_key is None:
            unit_key = key
        require(unit_key == key and row.get("ownerIdentityStatus") ==
                "player-component-chain-anchored", "native position owner changed or unanchored")
        position = []
        for axis in ("x", "y", "z"):
            value = row.get(axis)
            require(type(value) in (int, float), "native position XYZ invalid")
            try:
                number = float(value)
            except (ValueError, OverflowError) as error:
                raise RoutePreviewError("native position XYZ invalid") from error
            require(math.isfinite(number), "native position XYZ nonfinite")
            position.append(number)
        try:
            start = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
        except (ValueError, KeyError, AttributeError) as error:
            raise RoutePreviewError("native position sample UTC invalid") from error
        require(start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0)
                and start < end and (previous_end is None or start > previous_end),
                "native position sample times overlap or reorder")
        previous_end = end
        positions.append(Position(*position))
    return {
        "identity": identity, "unitKey": unit_key, "positions": positions,
        "sampleCount": len(positions),
        "firstSampleUtc": observations[0]["startedAtUtc"],
        "lastSampleUtc": observations[-1]["completedAtUtc"],
    }, hashlib.sha256(raw).hexdigest().upper()


def preview(position_path: Path, catalog_path: Path, anchor_id: str) -> dict:
    native, evidence_sha = _read_native(position_path)
    catalog = anchors.load_catalog(catalog_path)
    chosen = anchors.resolve_anchor(catalog, anchor_id)["anchor"]
    require(chosen["source"]["gameBuildSha256"].casefold() ==
            native["identity"]["executableSha256"].casefold(),
            "saved anchor and native sample use different game builds")
    goal = Position(**chosen["position"])
    positions = native["positions"]
    distances = [planar_distance(point, goal) for point in positions]
    segments = [planar_distance(left, right)
                for left, right in zip(positions, positions[1:])]
    path_length = sum(segments)
    net_displacement = planar_distance(positions[0], positions[-1])
    progress = distances[0] - distances[-1]
    require(all(math.isfinite(value) for value in
                (*distances, *segments, path_length, net_displacement, progress)),
            "derived planar metric is nonfinite")
    return {
        "schemaVersion": 1,
        "status": "offline-candidate-preview",
        "movementEligible": False,
        "arrivalQualified": False,
        "worldInstanceMatched": False,
        "coordinateFrame": anchors.COORDINATE_FRAME,
        "anchorId": chosen["id"],
        "anchorLabel": chosen["label"],
        "anchorZoneLabelMetadataOnly": chosen["zoneLabel"],
        "anchorXYZ": chosen["position"],
        "candidateCurrentXYZ": {axis: getattr(positions[-1], axis)
                                for axis in ("x", "y", "z")},
        "planarDistanceStartCandidate": distances[0],
        "planarDistanceEndCandidate": distances[-1],
        "planarProgressTowardAnchorCandidate": progress,
        "planarNetDisplacementCandidate": net_displacement,
        "planarObservedPathLengthCandidate": path_length,
        "sampleCount": native["sampleCount"],
        "lastSampleUtc": native["lastSampleUtc"],
        "unitKey": native["unitKey"],
        "processId": native["identity"]["processId"],
        "processStartUtcTicks": str(native["identity"]["processStartUtcTicks"]),
        "gameBuildSha256": native["identity"]["executableSha256"].upper(),
        "nativeReportSha256": evidence_sha,
        "limitations": [
            "Recorded positions are candidate cached native values, not qualified fresh player movement.",
            "Matching executable hashes do not establish the same zone, shard, or world instance.",
            "Distances are X/Z planar arithmetic only and do not authorize controls or prove arrival.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--position-report", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--anchor-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = preview(args.position_report, args.catalog, args.anchor_id)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, anchors.AnchorCatalogError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
