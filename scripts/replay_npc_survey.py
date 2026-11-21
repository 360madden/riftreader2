"""Offline source-byte replay of an advancing RR2 NPC API survey.

Uses exact retained Lua envelopes, not summary-only trust. All reported
relation, level and coordinates remain API candidates, not an action permit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import npc_survey_live as survey
from scripts import physical_rift


def require(condition, reason):
    if not condition:
        raise ValueError("npc-survey-replay-" + reason)


def replay(source):
    path = Path(source)
    require(path.is_file() and not path.is_symlink(), "summary-unavailable")
    data = path.read_bytes()
    require(0 < len(data) <= 256 * 1024, "summary-size")
    doc = physical_rift._strict_native_json(data.decode("utf-8-sig"))
    require(type(doc) is dict and doc.get("schemaVersion") == 1
            and doc.get("evidenceKind") == "physical-npc-api-survey/1"
            and doc.get("status") == "advancing" and doc.get("inputSent") is False,
            "summary-status-or-schema")
    snapshot = doc.get("snapshot")
    target = doc.get("target")
    rows = doc.get("sources")
    confirmed = doc.get("confirmedUnitIds")
    require(type(snapshot) is dict and type(target) is dict
            and doc.get("host") == "AMD-DESKTOP"
            and type(target.get("processId")) is int and target["processId"] > 0
            and str(target.get("processStartUtcTicks", "")).isdecimal()
            and type(target.get("executableSha256")) is str
            and len(target["executableSha256"]) == 64,
            "owner-invalid")
    require(type(rows) is list and 2 <= len(rows) <= 12
            and type(confirmed) is list and len(confirmed) <= 12
            and type(doc.get("observedUnits")) is int
            and doc["observedUnits"] == len(confirmed),
            "source-inventory-invalid")
    require(type(doc.get("playerId")) is str
            and survey.unit(doc["playerId"]) == doc["playerId"],
            "player-invalid")
    nonce = snapshot.get("sessionId")
    require(type(nonce) is str and len(nonce) == 32
            and all(c in "0123456789abcdef" for c in nonce),
            "session-invalid")
    mode = snapshot.get("mode")
    require(mode in ("explicit", "visible"), "mode-invalid")
    ids = (list(snapshot.get("units", {})) if mode == "explicit" else None)
    if ids is not None:
        require(1 <= len(ids) <= 12 and
                all(survey.unit(id) == id for id in ids),
                "explicit-ids-invalid")
    else:
        require(type(snapshot.get("page")) is int, "page-invalid")
    decoded, provenance = [], []
    last_seq, last_time, last_epoch = None, None, None
    last_host_tick = None
    for index, receipt in enumerate(rows, 1):
        require(type(receipt) is dict
                and type(receipt.get("address")) is str
                and type(receipt.get("sha256")) is str
                and len(receipt["sha256"]) == 64
                and type(receipt.get("sequence")) is int
                and type(receipt.get("epoch")) is int,
                "receipt-invalid")
        expected = path.parent / f"frame-{index:02d}.wire"
        require(receipt.get("retainedWire") == str(expected)
                and expected.is_file() and not expected.is_symlink(),
                "source-byte-file-unavailable")
        raw = expected.read_bytes()
        require(0 < len(raw) <= 8192 and raw.startswith(survey.PREFIX)
                and raw.endswith(survey.SUFFIX)
                and hashlib.sha256(raw).hexdigest() == receipt["sha256"],
                "source-sha-or-envelope-mismatch")
        frame = survey.decode_frame(
            raw, nonce, doc["playerId"], ids,
            snapshot["page"] if ids is None else None)
        require(frame["sequence"] == receipt["sequence"]
                and frame["epoch"] == receipt["epoch"]
                and frame["frameTime"] == receipt.get("frameTime"),
                "source-receipt-mismatch")
        require(last_seq is None or (frame["epoch"] == last_epoch
                and frame["sequence"] > last_seq
                and frame["frameTime"] > last_time),
                "source-not-advancing")
        host_tick = physical_rift._utc_tick_order_key(
            receipt.get("capturedAtUtc"))
        require(last_host_tick is None or host_tick > last_host_tick,
                "host-capture-order-invalid")
        last_seq, last_time, last_epoch, last_host_tick = (
            frame["sequence"], frame["frameTime"], frame["epoch"], host_tick)
        decoded.append(frame)
        provenance.append({
            "sha256": receipt["sha256"],
            "sequence": frame["sequence"],
            "epoch": frame["epoch"],
            "capturedAtUtc": receipt["capturedAtUtc"]
        })
    require(decoded[-1] == snapshot, "snapshot-not-source-replayed")
    before, after = decoded[-2:]
    require(before["epoch"] == after["epoch"]
            and before["sessionId"] == after["sessionId"],
            "paired-session-changed")
    if mode == "visible":
        require(before["units"].keys() == after["units"].keys(),
                "visible-keyset-changed")
    verified_ids = sorted(
        key for key, row in after["units"].items()
        if row["status"] == "observed"
        and key in before["units"] and
        before["units"][key]["status"] == "observed")
    require(verified_ids == confirmed, "confirmed-id-mismatch")
    lag = doc.get("relativeSourceLagSeconds")
    require(type(lag) in (int, float) and math.isfinite(lag)
            and 0 <= lag <= 2, "relative-lag-invalid")
    return {
        "status": "advancing-source-replayed-candidate",
        "process": target, "host": doc["host"],
        "playerId": doc["playerId"],
        "surveySessionId": nonce, "surveyEpoch": last_epoch,
        "confirmedUnitIds": verified_ids,
        "snapshot": snapshot, "sourceReceipts": provenance,
        "summarySha256": hashlib.sha256(data).hexdigest().upper(),
        "sampledAtUtc": rows[-1]["capturedAtUtc"],
        "inputSent": False,
        "qualification": ("Exact retained NPC Lua frames independently source-hash "
                          "replayed and schema/nonce/player/advancement checked. "
                          "The original producer session is not authenticated "
                          "by its byte hash. Level, relation, and positions are "
                          "API candidates, not combat eligibility, line of sight "
                          "or matching world-instance authority.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = replay(args.summary)
    except (ValueError, TypeError, KeyError, OSError, UnicodeError,
            OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:240]}))
        return 2
    print(json.dumps({
        "status": result["status"],
        "confirmedUnits": len(result["confirmedUnitIds"]),
        "sourceEpoch": result["surveyEpoch"],
        "summarySha256": result["summarySha256"],
        "inputSent": False
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
