#!/usr/bin/env python3
"""Save one named, offline-only navigation anchor from a retained physical native XYZ burst.

No live process access, gameplay input, or claim that a cached XYZ is fresh.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import navigation_anchors as anchors
from scripts import navigation_anchor_capture
from scripts import physical_route_preview


def from_native_report(report_path: Path, anchor_id: str, label: str,
                       zone_label: str | None = None) -> dict:
    native, digest = physical_route_preview._read_native(report_path)
    last = native["positions"][-1]
    result = {
        "schemaVersion": 1,
        "coordinateFrame": anchors.COORDINATE_FRAME,
        "anchors": [{
            "id": anchor_id,
            "label": label,
            "position": {"x": last.x, "y": last.y, "z": last.z},
            "zoneLabel": zone_label,
            "source": {
                "kind": "native-cache-candidate",
                "gameBuildSha256": native["identity"]["executableSha256"],
                "evidenceSha256": digest,
                "capturedAtUtc": native["lastSampleUtc"],
            },
            "qualification": "offline-reference-only",
        }],
    }
    return anchors.validate_catalog(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--position-report", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--zone-label", help="optional label; not world-instance verification")
    parser.add_argument("--output-catalog", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        catalog = from_native_report(options.position_report, options.id,
                                     options.label, options.zone_label)
        navigation_anchor_capture.save_new_catalog(options.output_catalog, catalog)
        result = {"status": "saved-native-anchor-candidate",
                  "anchorId": catalog["anchors"][0]["id"],
                  "candidateXYZ": catalog["anchors"][0]["position"],
                  "catalogPath": str(options.output_catalog),
                  "movementEligible": False,
                  "gameInputSent": False}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, anchors.AnchorCatalogError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error),
                          "gameInputSent": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
