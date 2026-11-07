"""Extract one player resource from a retained typed API memory snapshot.

This is an offline evidence helper. It verifies every successful native-memory
chunk hash, joins only contiguous chunks, and selects the newest complete frame.
Current RR2R1 use requires the exact reader session ID. Historical RRAPIVAL2
replay requires an explicit CLI switch; it is never selected by omission. This
tool does not read a process or turn the API value into native-field qualification.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
from pathlib import Path
import sys


PREFIX = b"RRAPIVAL2|"
SUFFIX = b"|RRAPIVALEND"
MAX_WIRE_BYTES = 8192
RESOURCE_FIELDS = {"mana": "manaMax", "power": None}
FIELD_NAMES = {
    "coordX", "coordY", "coordZ", "health", "healthMax", "mana", "manaMax",
    "combat", "dead", "mounted", "zone", "power", "combo", "planar", "planarMax",
}
TOP_KEYS = {
    "schemaVersion", "addon", "addonVersion", "source", "sequence", "clock",
    "player", "target", "nativeTextEntryState", "autonomousInputReady",
}


class ResourceInspectionError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResourceInspectionError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _number(value, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ResourceInspectionError(f"{label}-not-finite-number")
    return value


def _field(fields: dict, name: str) -> dict:
    value = fields.get(name)
    if not isinstance(value, dict) or set(value) not in ({"status"}, {"status", "value"}):
        raise ResourceInspectionError(f"field-contract:{name}")
    status = value.get("status")
    if status not in ("ok", "unavailable", "invalid"):
        raise ResourceInspectionError(f"field-status:{name}")
    if status == "ok":
        if set(value) != {"status", "value"}:
            raise ResourceInspectionError(f"field-value-missing:{name}")
        _number(value["value"], name)
    elif set(value) != {"status"}:
        raise ResourceInspectionError(f"unavailable-field-has-value:{name}")
    return value


def _wire(raw: bytes, resource: str) -> dict:
    try:
        root = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceInspectionError("wire-json-invalid") from exc
    if not isinstance(root, dict) or set(root) != TOP_KEYS:
        raise ResourceInspectionError("wire-top-level-contract")
    if (root.get("schemaVersion") != 2 or root.get("addon") != "RiftReaderApiProbe"
            or root.get("addonVersion") != "0.6.0" or root.get("source") != "rift-api"
            or root.get("nativeTextEntryState") != "unknown"
            or root.get("autonomousInputReady") is not False):
        raise ResourceInspectionError("wire-identity-contract")
    sequence = root.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ResourceInspectionError("sequence-invalid")
    clock = root.get("clock")
    if (not isinstance(clock, dict) or set(clock) != {"status", "domain", "value"}
            or clock.get("status") != "ok" or clock.get("domain") != "Inspect.Time.Frame"):
        raise ResourceInspectionError("clock-contract")
    frame_time = _number(clock.get("value"), "frame-time")
    player = root.get("player")
    if (not isinstance(player, dict) or set(player) != {"status", "fields", "unitId"}
            or player.get("status") != "ok" or not isinstance(player.get("unitId"), str)
            or not player["unitId"].startswith("u") or len(player["unitId"]) < 2):
        raise ResourceInspectionError("player-contract")
    fields = player.get("fields")
    if not isinstance(fields, dict) or set(fields) != FIELD_NAMES:
        raise ResourceInspectionError("player-fields-contract")
    for name in FIELD_NAMES:
        value = fields.get(name)
        if not isinstance(value, dict) or value.get("status") not in ("ok", "unavailable", "invalid"):
            raise ResourceInspectionError(f"field-contract:{name}")
    current = _field(fields, resource)
    maximum_name = RESOURCE_FIELDS[resource]
    maximum = _field(fields, maximum_name) if maximum_name else None
    return {
        "sequence": sequence,
        "frameTime": frame_time,
        "playerUnitId": player["unitId"],
        "resource": resource,
        "current": current,
        "maximum": maximum,
    }



REFERENCE_PREFIX = b"RR2R1|"
REFERENCE_SUFFIX = b"|ENDRR2R1"
SESSION_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
REFERENCE_KEYS = {"schemaVersion", "addon", "addonVersion", "source", "sessionId",
                  "sequence", "epoch", "clock", "player", "fields"}


def require_session_id(value: str) -> str:
    if not isinstance(value, str) or not SESSION_PATTERN.fullmatch(value):
        raise ResourceInspectionError("session-id-invalid")
    return value


def require_reference_binding(selected: dict, session_id: str) -> None:
    require_session_id(session_id)
    if (not isinstance(selected, dict) or selected.get("protocol") != "RR2R1"
            or selected.get("addon") != "RiftReader2" or selected.get("source") != "rift-api"
            or selected.get("addonVersion") != "0.2.0"
            or selected.get("sessionId") != session_id
            or type(selected.get("epoch")) is not int
            or not 0 < selected["epoch"] <= 9007199254740991):
        raise ResourceInspectionError("reference-binding-invalid")


def _status(value, label, kind):
    if not isinstance(value, dict) or value.get("status") not in ("ok", "unavailable", "invalid"):
        raise ResourceInspectionError(label + "-contract")
    if value["status"] != "ok":
        if set(value) != {"status"}:
            raise ResourceInspectionError(label + "-unavailable-has-value")
        return value
    if set(value) != {"status", "value"}:
        raise ResourceInspectionError(label + "-value-missing")
    item = value["value"]
    if kind == "number":
        _number(item, label)
    elif kind == "bool":
        if type(item) is not bool:
            raise ResourceInspectionError(label + "-boolean-required")
    elif not isinstance(item, str) or any(ord(char) < 32 or ord(char) > 126 for char in item) or len(item) > 128 or (kind == "player" and not item):
        raise ResourceInspectionError(label + "-ascii-string-required")
    return value


def _reference_wire(raw: bytes, resource: str) -> dict:
    try:
        root = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceInspectionError("reference-json-invalid") from exc
    if not isinstance(root, dict) or set(root) != REFERENCE_KEYS:
        raise ResourceInspectionError("reference-root-contract")
    if (type(root["schemaVersion"]) is not int or root["schemaVersion"] != 1
            or root["addon"] != "RiftReader2" or root["addonVersion"] != "0.2.0"
            or root["source"] != "rift-api"):
        raise ResourceInspectionError("reference-identity-contract")
    require_session_id(root["sessionId"])
    for key in ("sequence", "epoch"):
        if type(root[key]) is not int or not 0 < root[key] <= 9007199254740991:
            raise ResourceInspectionError(key + "-invalid")
    clock = _status(root["clock"], "clock", "number")
    if clock["status"] == "ok" and clock["value"] < 0:
        raise ResourceInspectionError("clock-negative")
    player = _status(root["player"], "player", "player")
    fields = root["fields"]
    if not isinstance(fields, dict) or set(fields) != FIELD_NAMES:
        raise ResourceInspectionError("reference-fields-contract")
    for key, value in fields.items():
        _status(value, key, "bool" if key in ("combat", "dead", "mounted") else "string" if key == "zone" else "number")
    if clock["status"] != "ok" and player != {"status": "unavailable"}:
        raise ResourceInspectionError("nonok-clock-player-must-be-unavailable")
    if (clock["status"] != "ok" or player["status"] != "ok") and any(
            value != {"status": "unavailable"} for value in fields.values()):
        raise ResourceInspectionError("nonok-source-fields-must-be-unavailable")
    return {"protocol": "RR2R1", "addon": root["addon"], "addonVersion": root["addonVersion"],
            "source": root["source"], "sessionId": root["sessionId"], "epoch": root["epoch"],
            "sequence": root["sequence"], "frameTime": clock.get("value"),
            "playerUnitId": player.get("value"), "fields": fields,
            "resource": resource, "current": fields[resource],
            "maximum": fields[RESOURCE_FIELDS[resource]] if RESOURCE_FIELDS[resource] else None}


def inspect(snapshot_path: Path, resource: str, session_id: str | None = None) -> dict:
    if session_id is not None:
        require_session_id(session_id)
    prefix, suffix = (REFERENCE_PREFIX, REFERENCE_SUFFIX) if session_id is not None else (PREFIX, SUFFIX)
    if resource not in RESOURCE_FIELDS:
        raise ResourceInspectionError("unsupported-resource")
    raw_file = snapshot_path.read_bytes()
    try:
        snapshot = json.loads(raw_file.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceInspectionError("snapshot-json-invalid") from exc
    if (not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1
            or snapshot.get("evidenceKind") != "native-memory-snapshot/1"
            or snapshot.get("status") != "complete"):
        raise ResourceInspectionError("snapshot-contract")
    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        raise ResourceInspectionError("snapshot-identity")
    chunks = snapshot.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ResourceInspectionError("snapshot-chunks")

    segments: list[tuple[int, bytes]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict) or chunk.get("status") != "success":
            continue
        try:
            address = int(chunk["address"], 16)
            data = base64.b64decode(chunk["bytesBase64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise ResourceInspectionError("chunk-encoding") from exc
        if len(data) != chunk.get("bytesRead") or len(data) != chunk.get("requestedByteLength"):
            raise ResourceInspectionError("chunk-length")
        if hashlib.sha256(data).hexdigest().upper() != chunk.get("bytesSha256"):
            raise ResourceInspectionError("chunk-sha256")
        segments.append((address, data))
    segments.sort()
    joined: list[tuple[int, bytes]] = []
    for address, data in segments:
        if joined and joined[-1][0] + len(joined[-1][1]) == address:
            joined[-1] = (joined[-1][0], joined[-1][1] + data)
        else:
            joined.append((address, data))

    candidates = []
    malformed = 0
    foreign = False
    for base, data in joined:
        start = 0
        while True:
            offset = data.find(prefix, start)
            if offset < 0:
                break
            start = offset + len(prefix)
            if session_id is not None:
                # Match the capture and .NET plausibility gate. A compiled/static
                # marker without a JSON opening brace is not a frame candidate.
                if start >= len(data) or data[start] != ord("{"):
                    continue
                try:
                    text = data[start:min(len(data), offset + MAX_WIRE_BYTES)].decode("latin-1")
                    _, consumed = json.JSONDecoder().raw_decode(text)
                    end = start + consumed
                    if data[end:end + len(suffix)] != suffix:
                        end = -1
                except (ValueError, UnicodeError):
                    end = -1
            else:
                end = data.find(suffix, start, min(len(data), offset + MAX_WIRE_BYTES))
            if end < 0:
                malformed += 1
                continue
            try:
                if end + len(suffix) - offset > MAX_WIRE_BYTES:
                    raise ResourceInspectionError("frame-too-long")
                wire = (_reference_wire if session_id is not None else _wire)(data[start:end], resource)
                start = end + len(suffix)
                if session_id is not None and wire["sessionId"] != session_id:
                    foreign = True
                    continue
                wire["address"] = f"0x{base + offset:X}"
                wire["wireSha256"] = hashlib.sha256(data[offset:end + len(suffix)]).hexdigest().upper()
                candidates.append(wire)
            except ResourceInspectionError:
                malformed += 1
    if malformed:
        raise ResourceInspectionError("malformed-or-incomplete-frame-in-covered-scope")
    if session_id is not None and foreign:
        raise ResourceInspectionError("reference-session-mismatch")
    if not candidates:
        raise ResourceInspectionError("reference-session-mismatch" if foreign else "no-complete-frame-in-covered-scope")
    if session_id is not None and len({row["epoch"] for row in candidates}) != 1:
        raise ResourceInspectionError("reference-epoch-conflict")
    if session_id is not None and len({row["playerUnitId"] for row in candidates if row["playerUnitId"] is not None}) > 1:
        raise ResourceInspectionError("reference-player-conflict")
    if session_id is not None:
        ordered = sorted(candidates, key=lambda row: row["sequence"])
        if any(first["frameTime"] is not None and second["frameTime"] is not None
               and second["frameTime"] < first["frameTime"] for first, second in zip(ordered, ordered[1:])):
            raise ResourceInspectionError("reference-clock-regression-within-epoch")
    selected = max(candidates, key=lambda row: (row["sequence"] if session_id else row["frameTime"], row["sequence"]))
    conflicts = [row for row in candidates if (session_id is not None or row["frameTime"] == selected["frameTime"])
                 and row["sequence"] == selected["sequence"]
                 and row["wireSha256"] != selected["wireSha256"]]
    if conflicts:
        raise ResourceInspectionError("conflicting-latest-frames")
    return {
        "schemaVersion": 1,
        "evidenceKind": "typed-resource-snapshot-inspection/1",
        "status": "available" if selected["current"]["status"] == "ok" else "unavailable",
        "snapshotSha256": hashlib.sha256(raw_file).hexdigest().upper(),
        "identity": identity,
        "startedAtUtc": snapshot.get("startedAtUtc"),
        "completedAtUtc": snapshot.get("completedAtUtc"),
        "selected": selected,
        "candidateCount": len(candidates),
        "limitations": [
            "This is an offline extraction from bounded retained snapshot bytes.",
            "An API resource value is an independent reference, not native field qualification.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--resource", choices=sorted(RESOURCE_FIELDS), required=True)
    parser.add_argument("--output", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--session-id",
        help="exact RR2R1 reader-session nonce (current runtime path)",
    )
    source.add_argument(
        "--historical-rrapival2",
        action="store_true",
        help="explicitly replay retained legacy RiftReaderApiProbe evidence",
    )
    args = parser.parse_args(argv)
    try:
        result = inspect(args.snapshot, args.resource, args.session_id)
        encoded = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.open("x", encoding="utf-8", newline="\n").write(encoded)
        print(encoded, end="")
        return 0
    except (OSError, ResourceInspectionError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
