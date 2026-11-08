#!/usr/bin/env python3
"""Extract one offline-only named XYZ anchor from a retained raw RR2 receipt.

This never reads live game state, issues input, verifies a current session, or
grants movement eligibility. A capture-time "fresh-scoped" label is historical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from . import navigation_anchors as anchors
else:
    import navigation_anchors as anchors


MAX_RECEIPT_BYTES = 2 * 1024 * 1024


def _object(value: object, label: str) -> dict:
    anchors.require(isinstance(value, dict), f"{label} is missing or invalid")
    return value


def _schema_one(value: dict, label: str) -> None:
    anchors.require(type(value.get("schemaVersion")) is int
                    and value["schemaVersion"] == 1,
                    f"{label} schema is unsupported")


def _read_receipt(path: Path) -> tuple[dict, str]:
    path = Path(path)
    anchors.require(not path.is_symlink(), "symbolic receipt path is not allowed")
    anchors.require(path.is_file() and path.stat().st_size <= MAX_RECEIPT_BYTES,
                    "receipt is missing or oversized")
    raw = path.read_bytes()
    anchors.require(len(raw) <= MAX_RECEIPT_BYTES, "receipt is oversized")
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _: (_ for _ in ()).throw(
                anchors.AnchorCatalogError("nonfinite JSON is invalid")),
            object_pairs_hook=anchors._unique_json_object,
        )
    except anchors.AnchorCatalogError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise anchors.AnchorCatalogError("receipt JSON is invalid") from error
    return _object(decoded, "raw receipt"), hashlib.sha256(raw).hexdigest().upper()


def catalog_from_receipt(path: Path, anchor_id: str, label: str,
                         zone_label: str | None = None) -> dict:
    """Extract only a valid historical scoped addon XYZ; do not assert liveness."""
    receipt, digest = _read_receipt(path)
    _schema_one(receipt, "receipt")
    outer = _object(receipt.get("observation"), "reader observation")
    _schema_one(outer, "reader observation")
    anchors.require(outer.get("readerStatus") == "running",
                    "reader was not running in this receipt")
    nonce = outer.get("nonce")
    anchors.require(isinstance(nonce, str) and len(nonce) == 32
                    and all(char in "0123456789abcdefABCDEF" for char in nonce),
                    "reader nonce is invalid")
    target = _object(outer.get("target"), "reader target")
    anchors.require(target.get("readerSessionNonce") == nonce,
                    "reader target nonce differs from observation nonce")

    fast = _object(outer.get("fastObservation"), "scoped source")
    _schema_one(fast, "scoped source")
    anchors.require(fast.get("bindingStatus") == "bound-scoped"
                    and fast.get("freshnessStatus") == "fresh-scoped"
                    and fast.get("selectionStatus") == "selected-scoped"
                    and fast.get("provenance")
                    == "recent-full-scan-anchored-candidate-regions/1",
                    "receipt did not report a selected fresh scoped source")
    scan = _object(fast.get("scan"), "scoped scan")
    anchors.require(scan.get("scope") == "candidate-regions"
                    and scan.get("status") == "complete"
                    and scan.get("completed") is True,
                    "scoped scan was not completed")
    snapshot = _object(fast.get("observation"), "scoped addon snapshot")
    _schema_one(snapshot, "scoped addon snapshot")
    anchors.require(type(fast.get("candidateSequence")) is int
                    and type(fast.get("candidateEpoch")) is int
                    and type(snapshot.get("sequence")) is int
                    and type(snapshot.get("epoch")) is int
                    and fast["candidateSequence"] == snapshot["sequence"]
                    and fast["candidateEpoch"] == snapshot["epoch"],
                    "scoped sequence or epoch is inconsistent")
    player = _object(snapshot.get("player"), "scoped addon player")
    anchors.require(player.get("status") == "ok"
                    and isinstance(player.get("value"), str)
                    and bool(player["value"]),
                    "scoped addon player is unavailable")
    fields = _object(snapshot.get("fields"), "scoped addon fields")
    position = {}
    for axis in ("x", "y", "z"):
        field = _object(fields.get("coord" + axis.upper()), f"coord{axis.upper()}")
        anchors.require(field.get("status") == "ok", f"coord{axis.upper()} was unavailable")
        position[axis] = field.get("value")
    result = {"schemaVersion": 1, "coordinateFrame": anchors.COORDINATE_FRAME,
              "anchors": [{"id": anchor_id, "label": label, "position": position,
                           "zoneLabel": zone_label,
                           "source": {"kind": "addon-feedback-receipt",
                                      "gameBuildSha256": target.get("executableSha256"),
                                      "evidenceSha256": digest,
                                      "capturedAtUtc": outer.get("capturedAtUtc")},
                           "qualification": "offline-reference-only"}]}
    return anchors.validate_catalog(result)


def save_new_catalog(path: Path, catalog: dict) -> None:
    """Create one new catalog; never replace a file or merge unreviewed data."""
    path = Path(path)
    anchors.require(not path.is_symlink(), "symbolic output is not allowed")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(catalog, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--zone-label", help="human metadata only; not a zone match")
    parser.add_argument("--output-catalog", type=Path,
                        help="optional new filename; existing files never overwritten")
    args = parser.parse_args(argv)
    try:
        catalog = catalog_from_receipt(args.receipt, args.id, args.label, args.zone_label)
        if args.output_catalog:
            save_new_catalog(args.output_catalog, catalog)
        print(json.dumps({"status": "offline-reference-only", "movementEligible": False,
                          "catalog": catalog,
                          "savedCatalog": str(args.output_catalog) if args.output_catalog else None,
                          "nextRequired": "independent current-session freshness and world compatibility"},
                         sort_keys=True, allow_nan=False))
        return 0
    except (OSError, anchors.AnchorCatalogError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
