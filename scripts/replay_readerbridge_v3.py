"""Replay retained ReaderBridge packets and their native player-level bracket offline."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_readerbridge_v3 as bridge, physical_rift, readerbridge_v3


def require(ok, reason):
    if not ok:
        raise ValueError("readerbridge-replay-" + reason)


def _read(path, limit):
    require(path.is_file() and not path.is_symlink(), "source-file-unavailable")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "source-size-invalid")
    return raw


def _json(path, limit=1024 * 1024):
    return bridge._loads_json(_read(path, limit), path.name)


def _generation(directory, generation, number, target, self_id):
    report_name = PureWindowsPath(generation["captureReport"]).name
    attempt = re.fullmatch(r"(attempt-[1-3])\.capture\.json", report_name)
    require(attempt is not None, "capture-source-name-invalid")
    stem = attempt[1]
    packet_name = f"generation-{number}.bin"
    require(PureWindowsPath(generation["packetFile"]).name == packet_name, "packet-source-name-invalid")
    address = int(generation["packetAddress"], 16)
    require(0x10000 <= address < 0x7FFF_FFFF_FFFF - readerbridge_v3.PACKET_SIZE, "packet-address-invalid")
    request = _json(directory / f"{stem}.capture.request.json")
    require(request == bridge._capture_request(target, address), "capture-request-mismatch")
    report = _json(directory / report_name)
    packet = bridge._packet_from_capture(report, target, request)
    require(packet == _read(directory / packet_name, readerbridge_v3.PACKET_SIZE), "packet-bytes-mismatch")
    decoded = readerbridge_v3.decode_packet(packet)
    for key in ("sequence", "sourceTimeMs", "packetSha256", "flags", "health", "power"):
        require(decoded[key] == generation[key], "decoded-packet-mismatch")
    player = decoded["sections"]["P"]
    require(player == generation["player"], "player-packet-mismatch")

    scout = directory / f"{stem}.scout"
    require(not scout.is_symlink() and scout.resolve().parent == directory.resolve(), "scout-directory-unavailable")
    candidates = bridge._validate_scout(_json(scout / "index.json"), target, scout)
    require(any(row["address"] == generation["packetAddress"]
                and "readerbridge-prefix" in row.get("referenceNames", [])
                and bridge._packet_control_sequence(data) == decoded["sequence"]
                for row, data in candidates), "scout-packet-mismatch")
    companion = generation["companion"]
    require(companion["playerId"] == self_id and companion["status"] == "pass"
            and companion["sequence"] == decoded["sequence"] and companion["name"] == player["name"]
            and Decimal(companion["sampledAt"]) * 1000 == decoded["sourceTimeMs"], "companion-packet-mismatch")
    for _, data in candidates:
        try:
            found = bridge._companion(data)
        except bridge.CaptureError:
            continue
        if found == companion:
            break
    else:
        raise ValueError("readerbridge-replay-companion-source-unavailable")

    sample = report["capture"]["samples"][0]
    return {"sequence": decoded["sequence"], "sourceTimeMs": decoded["sourceTimeMs"],
            "packetSha256": decoded["packetSha256"], "level": player["level"],
            "targetPublished": decoded["flags"]["hasTarget"],
            "startedAtUtc": sample["startedAtUtc"], "completedAtUtc": sample["completedAtUtc"]}


def _native_levels(directory, references, target, self_id, generations):
    values = []
    for side in ("before", "after"):
        name = f"native-player-{side}.json"
        reference = references[side]
        require(reference["file"] == name, "native-context-source-name-invalid")
        raw = _read(directory / name, 1024 * 1024)
        require(hashlib.sha256(raw).hexdigest().upper() == reference["sha256"], "native-context-sha-mismatch")
        native = bridge._loads_json(raw, name)
        require(bridge._same_target(native["observation"]["identity"], target), "native-context-owner-mismatch")
        value = physical_rift._native_values("player-context", native)
        require(bridge._canonical_unit_key(value["unitKey"]) == self_id, "native-context-player-mismatch")
        values.append(value)

    stamp = physical_rift._utc_tick_order_key
    require(stamp(values[0]["sampledAtUtc"]) <= stamp(generations[0]["startedAtUtc"])
            and stamp(generations[-1]["completedAtUtc"]) <= stamp(values[1]["sampledAtUtc"]),
            "native-context-does-not-bracket-packets")
    native_levels = [value["level"] for value in values]
    levels = [level["rawCandidate"] for level in native_levels] + [row["level"] for row in generations]
    if any(type(level) is not int or level <= 0 for level in levels):
        status = "level-candidate-unavailable"
    elif len(set(levels)) == 1:
        status = "matching-native-and-lua-player-level-candidates"
    else:
        status = "different-native-and-lua-player-level-candidates"
    return {"status": status, "nativeLevels": native_levels,
            "beforeSampledAtUtc": values[0]["sampledAtUtc"], "afterSampledAtUtc": values[1]["sampledAtUtc"]}


def replay(summary, *, native_bracket=None):
    summary = Path(summary)
    doc = _json(summary)
    require(doc.get("schemaVersion") == 1 and doc.get("evidenceKind") == "readerbridge-v3-bounded-acquisition/1"
            and doc.get("status") == "captured" and doc.get("ready") is False and doc.get("inputSent") is False
            and doc.get("guiStateChanged") is False, "capture-summary-unqualified")
    target = bridge._target(doc["target"])
    require(type(target["processId"]) is int and target["processId"] > 0 and target["processStartUtcTicks"] > 0
            and re.fullmatch(r"[0-9A-F]{64}", target["executableSha256"]), "capture-owner-invalid")
    self_id = doc["selfId"]
    require(isinstance(self_id, str) and re.fullmatch(r"u[0-9A-F]{16}", self_id), "capture-player-invalid")
    rows = doc["generations"]
    require(isinstance(rows, list) and len(rows) == 2, "capture-generation-count-invalid")
    directory = summary.parent
    generations = [_generation(directory, row, index, target, self_id) for index, row in enumerate(rows, 1)]
    bridge._require_advancing(generations[1], generations[:1])
    stamp = physical_rift._utc_tick_order_key
    require(stamp(generations[0]["startedAtUtc"]) <= stamp(generations[0]["completedAtUtc"])
            <= stamp(generations[1]["startedAtUtc"]) <= stamp(generations[1]["completedAtUtc"]),
            "capture-time-order-invalid")

    host = doc.get("host")
    references = doc.get("nativePlayerContext")
    if native_bracket is not None:
        require(references is None, "duplicate-native-context-bracket")
        bracket_path = Path(native_bracket)
        bracket = _json(bracket_path)
        require(bracket.get("inputSent") is False and bracket.get("readerBridgeExit") == 0
                and bridge._same_target(bracket["owner"], target), "external-native-context-unqualified")
        host = bracket["host"]
        directory = bracket_path.parent
        references = {side: {"file": PureWindowsPath(bracket[side]["source"]).name,
                             "sha256": bracket[side]["sha256"]} for side in ("before", "after")}
    require(host is None or physical_rift.valid_host_name(host), "capture-host-invalid")
    comparison = (_native_levels(directory, references, target, self_id, generations)
                  if references is not None else None)
    return {"status": "source-replayed-candidate", "host": host, "target": target, "selfId": self_id,
            "generations": generations, "playerLevelComparison": comparison,
            "inputSent": False, "ready": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path, help="retained ReaderBridge result.json")
    parser.add_argument("--native-bracket", type=Path, help="separate native bracket from an older capture")
    args = parser.parse_args(argv)
    try:
        result = replay(args.summary, native_bracket=args.native_bracket)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, InvalidOperation) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "inputSent": False, "ready": False}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
