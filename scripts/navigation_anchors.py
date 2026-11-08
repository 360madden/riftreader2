#!/usr/bin/env python3
"""Validate and resolve persistent RR2 navigation anchors, strictly offline.

A saved XYZ destination is not a live location fix, world-instance match,
freshness qualification, controller lease, or movement authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import re


COORDINATE_FRAME = "rift-addon-xyz-xz-planar-y-vertical"
MAX_CATALOG_BYTES = 1024 * 1024
MAX_ANCHORS = 256
ANCHOR_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
SHA256 = re.compile(r"[0-9A-Fa-f]{64}\Z")
SOURCE_KINDS = frozenset({"addon-feedback-receipt", "native-cache-candidate"})


class AnchorCatalogError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AnchorCatalogError(reason)


def _exact_keys(value: object, keys: set[str], label: str) -> dict:
    require(isinstance(value, dict) and set(value) == keys, f"{label} fields are invalid")
    return value


def _finite(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} must be numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise AnchorCatalogError(f"{label} is not finite") from error
    require(math.isfinite(number), f"{label} is not finite")
    return number


def _digest(value: object, label: str) -> str:
    require(isinstance(value, str) and SHA256.fullmatch(value) is not None,
            f"{label} must be a SHA-256 hex digest")
    return value.upper()


def _captured_utc(value: object) -> str:
    require(isinstance(value, str) and value.strip() == value, "capture UTC is invalid")
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AnchorCatalogError("capture UTC is invalid") from error
    require(when.utcoffset() == timedelta(0), "capture must use UTC")
    # Keep the original source's fractional precision (RIFT receipts may use 100 ns ticks).
    return value


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def validate_catalog(value: object) -> dict:
    raw = _exact_keys(value, {"schemaVersion", "coordinateFrame", "anchors"}, "catalog")
    require(type(raw["schemaVersion"]) is int and raw["schemaVersion"] == 1,
            "unsupported anchor catalog schema")
    require(raw["coordinateFrame"] == COORDINATE_FRAME, "unknown coordinate frame")
    anchors = raw["anchors"]
    require(isinstance(anchors, list) and len(anchors) <= MAX_ANCHORS, "anchor count is invalid")
    seen = set()
    checked = []
    for index, item in enumerate(anchors):
        anchor = _exact_keys(item, {"id", "label", "position", "zoneLabel",
                                    "source", "qualification"}, f"anchor[{index}]")
        anchor_id = anchor["id"]
        require(isinstance(anchor_id, str) and ANCHOR_ID.fullmatch(anchor_id) is not None,
                "anchor id is invalid")
        folded = anchor_id.casefold()
        require(folded not in seen, "duplicate anchor id")
        seen.add(folded)
        label = anchor["label"]
        require(isinstance(label, str) and 0 < len(label.strip()) <= 120
                and all(ord(char) >= 32 for char in label), "anchor label is invalid")
        zone = anchor["zoneLabel"]
        require(zone is None or (isinstance(zone, str) and 0 < len(zone.strip()) <= 120
                                  and all(ord(char) >= 32 for char in zone)),
                "zone label metadata is invalid")
        require(anchor["qualification"] == "offline-reference-only",
                "stored anchors cannot authorize live navigation")
        position = _exact_keys(anchor["position"], {"x", "y", "z"}, "anchor position")
        point = {axis: _finite(position[axis], f"position.{axis}") for axis in ("x", "y", "z")}
        source = _exact_keys(anchor["source"],
                             {"kind", "gameBuildSha256", "evidenceSha256", "capturedAtUtc"},
                             "anchor source")
        require(isinstance(source["kind"], str) and source["kind"] in SOURCE_KINDS,
                "unknown anchor source kind")
        provenance = {"kind": source["kind"],
                      "gameBuildSha256": _digest(source["gameBuildSha256"], "game build"),
                      "evidenceSha256": _digest(source["evidenceSha256"], "capture evidence"),
                      "capturedAtUtc": _captured_utc(source["capturedAtUtc"])}
        checked.append({"id": anchor_id, "label": label.strip(), "position": point,
                        "zoneLabel": zone.strip() if isinstance(zone, str) else None,
                        "source": provenance, "qualification": "offline-reference-only"})
    return {"schemaVersion": 1, "coordinateFrame": COORDINATE_FRAME, "anchors": checked}


def load_catalog(path: Path) -> dict:
    path = Path(path)
    require(not path.is_symlink(), "symbolic catalog path is not allowed")
    require(path.is_file() and path.stat().st_size <= MAX_CATALOG_BYTES,
            "catalog is missing or oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               AnchorCatalogError("nonfinite JSON is invalid")),
                           object_pairs_hook=_unique_json_object)
    except AnchorCatalogError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise AnchorCatalogError("catalog JSON is invalid") from error
    return validate_catalog(value)


def resolve_anchor(catalog: dict, anchor_id: str) -> dict:
    valid = validate_catalog(catalog)
    require(isinstance(anchor_id, str), "anchor id is invalid")
    matches = [item for item in valid["anchors"] if item["id"].casefold() == anchor_id.casefold()]
    require(len(matches) == 1, "anchor not found")
    anchor = matches[0]
    return {"schemaVersion": 1, "status": "offline-reference-only",
            "movementEligible": False, "coordinateFrame": COORDINATE_FRAME,
            "anchor": anchor,
            "planarGoal": {axis: anchor["position"][axis] for axis in ("x", "z")},
            "zoneLabelIsMetadataOnly": True,
            "nextRequired": "independently validated current-session fresh addon position and world compatibility"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--anchor-id", help="resolve one case-insensitive saved ID; omit to list")
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        result = resolve_anchor(catalog, args.anchor_id) if args.anchor_id else {
            "schemaVersion": 1, "status": "offline-reference-only",
            "movementEligible": False, "coordinateFrame": COORDINATE_FRAME,
            "anchors": [{"id": entry["id"], "label": entry["label"],
                         "zoneLabel": entry["zoneLabel"]} for entry in catalog["anchors"]]}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, AnchorCatalogError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
