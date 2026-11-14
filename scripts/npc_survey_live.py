"""Read advancing, nonce-bound RIFT API observations by unit ID or visible page."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift, survival_live
from scripts.capture_readerbridge_v3 import (
    CaptureError, _loads_json, _read_json, _run_native, _same_target, _target,
    _validate_scout, _validate_seed, _write_json,
)
from scripts.physical_waypoints import DEFAULT_BASIS, PhysicalAdapter

PREFIX = b"RR2NPC1|"
SUFFIX = b"|ENDRR2NPC1"
FIELD_TYPES = {
    "string": ("name", "relation", "alliance", "zone", "type"),
    "number": ("level", "coordX", "coordY", "coordZ", "health", "healthMax"),
    "boolean": ("player", "combat", "rawAttackable"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unit(value):
    require(isinstance(value, str) and re.fullmatch(r"u[0-9a-fA-F]{16}", value),
            "invalid-unit-id")
    return "u" + value[1:].upper()


def requested_ids(value):
    ids = [unit(s) for s in value.split(",")]
    require(1 <= len(ids) <= 12 and len(set(ids)) == len(ids), "invalid-unit-selection")
    return ids


def decode_frame(data, nonce, player_id, ids, page=None):
    end = data.find(SUFFIX)
    require(data.startswith(PREFIX) and len(PREFIX) < end
            and end + len(SUFFIX) <= 8192, "invalid-survey-boundaries")
    frame = _loads_json(data[len(PREFIX):end].decode("utf-8"), "npc-survey")
    require(frame.get("addon") == "RiftReader2NpcSurvey" and frame.get("addonVersion") == "0.1.0"
            and type(frame.get("schemaVersion")) is int and frame["schemaVersion"] == 1
            and frame.get("source") == "Inspect.Unit.Detail" and frame.get("status") == "observed",
            "invalid-survey-contract")
    require(frame.get("sessionId") == nonce and unit(frame.get("playerId")) == unit(player_id),
            "survey-binding-mismatch")
    for key in ("epoch", "sequence"):
        require(type(frame.get(key)) is int and frame[key] > 0, "invalid-survey-generation")
    clock = frame.get("frameTime")
    require(type(clock) in (float, int) and math.isfinite(clock) and clock >= 0, "invalid-survey-clock")
    rows = frame.get("units")
    require(isinstance(rows, dict) and len(rows)<=12
            and all(unit(key)==key for key in rows), "invalid-survey-keys")
    require((ids is not None and "keysetStable" not in frame) or type(frame.get("keysetStable")) is bool,
            "invalid-unit-list-comparison")
    for field in ("beforeCount","afterCount"):
        require((ids is not None and field not in frame) or (type(frame.get(field)) is int and 0<=frame[field]<=4096),
                "invalid-visible-count")
    if ids is not None:
        require(frame.get("mode")=="explicit" and frame.get("page") is None
                and frame.get("selectionScope")=="explicit-native-id-detail" and set(rows)==set(ids),
                "survey-selection-mismatch")
    else:
        require(frame.get("mode")=="visible" and type(frame.get("page")) is int and frame["page"]==page
                and frame["keysetStable"] and frame["beforeCount"]==frame["afterCount"]
                and page<=max(1,(frame["beforeCount"]+11)//12)
                and len(rows)==min(12,max(0,frame["beforeCount"]-(page-1)*12)), "unstable-or-wrong-visible-page")
    validators = {
        "string": lambda v: isinstance(v, str) and 0 < len(v.encode("utf-8")) <= 128,
        "number": lambda v: type(v) in (float, int) and math.isfinite(v),
        "boolean": lambda v: type(v) is bool,
    }
    for key, row in rows.items():
        require(isinstance(row, dict), "invalid-survey-row")
        for diagnostic in ("visibleBefore","visibleAfter"):
            require((ids is not None and diagnostic not in row) or type(row.get(diagnostic)) is bool,
                    "invalid-survey-membership")
        if row.get("status") != "observed":
            require(set(row) <= {"status","visibleBefore","visibleAfter"}
                    and row["status"] in ("unavailable", "identity-mismatch","not-visible","visibility-changed"),
                    "invalid-unavailable-survey-row")
            continue
        require((ids is not None or (row["visibleBefore"] and row["visibleAfter"])) and unit(row.get("id")) == key,
                "survey-unit-detail-identity-mismatch")
        if "availability" in row:
            require(any(check(row["availability"]) for check in validators.values()),"invalid-availability-scalar")
        for kind, fields in FIELD_TYPES.items():
            for field in fields:
                require(field not in row or validators[kind](row[field]), "invalid-survey-field-" + field)
    return frame


def scout(target, base, length, attempt):
    request = survival_live._scout_request(target, base, length, 1000)
    request["references"] = [{"name": "rr2-npc-survey", "type": "int32",
                              "value": str(int.from_bytes(PREFIX[:4], "little")), "tolerance": None}]
    request_path = Path(str(attempt) + ".request.json")
    _write_json(request_path, request)
    _run_native("scout-values-native", request_path, attempt, subprocess.run)
    index = _read_json(attempt / "index.json")
    require(index.get("request") == request, "survey-scout-request-mismatch")
    results, addresses = [], []
    for row, data in _validate_scout(index, target, attempt):
        if "rr2-npc-survey" not in row.get("referenceNames", []) or not data.startswith(PREFIX):
            continue
        address = int(row["address"], 16)
        require(base <= address < base + length, "survey-address-outside-seed")
        if SUFFIX in data:
            results.append((row, data))
        elif address + 8192 <= base + length:
            addresses.append(address)
    for offset in range(0, len(addresses), 16):
        results.extend(survival_live._capture_known(target, addresses[offset:offset+16],
                         Path(str(attempt) + f".frames-{offset//16+1}")))
    return results


def newest(candidates, nonce, player_id, ids, seen, previous, page=None):
    decoded = []
    for row, data in candidates:
        try:
            frame = decode_frame(data, nonce, player_id, ids, page)
        except (CaptureError, ValueError, UnicodeError):
            continue
        identity = (frame["epoch"], frame["sequence"])
        digest = hashlib.sha256(data[:data.index(SUFFIX)+len(SUFFIX)]).hexdigest()
        require(seen.setdefault(identity, digest) == digest, "conflicting-survey-generation")
        if previous:
            require(frame["epoch"] == previous["epoch"], "survey-epoch-changed")
            if frame["sequence"] <= previous["sequence"] or frame["frameTime"] <= previous["frameTime"]:
                continue
        decoded.append((frame, {"address": row["address"], "sha256": digest}))
    if not decoded:
        return None
    require(len({frame["epoch"] for frame, _ in decoded}) == 1, "ambiguous-survey-epoch")
    return max(decoded, key=lambda pair: pair[0]["sequence"])


def acquire(host, pid, nonce, ids, output, seed_index=None, scan_mib=16, attempts=5, page=None):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce), "invalid-survey-nonce")
    require(1 <= scan_mib <= 32 and 2 <= attempts <= 12, "invalid-survey-budget")
    if ids is None:
        require(type(page) is int and 1<=page<=342,"invalid-visible-page")
    else:
        require(page is None and ids == requested_ids(",".join(ids)), "invalid-survey-selection")
    selection = physical_rift.select_physical(expected_host=host, physical_pid=pid)
    require(selection.get("status") == "ready", "physical-selection-not-ready")
    target = _target(selection["target"])
    adapter = PhysicalAdapter(host, pid, DEFAULT_BASIS)
    require(_same_target(adapter.target, target), "survey-process-mismatch")
    player_id = survival_live._canonical_unit_key(adapter.unit_key)
    seed = Path(seed_index) if seed_index else survival_live.autodiscover_seed(target)
    base, length = _validate_seed(_read_json(seed), target, scan_mib)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    seen, sources, previous = {}, [], None
    previous_at = None
    for index in range(1, attempts+1):
        start = time.monotonic()
        candidates = scout(target, base, length, output/f"attempt-{index}.scout")
        elapsed = time.monotonic()-start
        if elapsed <= 5:
            selected = newest(candidates, nonce, player_id, ids, seen, previous, page)
            if selected:
                frame, source = selected
                now = time.monotonic()
                sources.append(dict(source, epoch=frame["epoch"], sequence=frame["sequence"],
                                    frameTime=frame["frameTime"], attempt=index, readSeconds=elapsed,
                                    capturedAtUtc=datetime.now(timezone.utc).isoformat()))
                if previous is not None and (ids is not None or previous["units"].keys()==frame["units"].keys()):
                    lag = max(0.0, (now-previous_at)-(frame["frameTime"]-previous["frameTime"]))
                    require(lag<=2, "survey-relative-source-lag")
                    confirmed=sorted(key for key,row in frame["units"].items()
                                     if row["status"]=="observed" and previous["units"][key]["status"]=="observed")
                    report = {"schemaVersion": 1, "evidenceKind": "physical-npc-api-survey/1",
                              "status": "advancing", "inputSent": False, "host":host, "target": target,
                              "playerId": player_id, "seedIndex": str(seed), "sources": sources,
                              "relativeSourceLagSeconds":lag,"confirmedUnitIds":confirmed,
                              "snapshot":frame,"observedUnits":len(confirmed),
                              "qualification":"confirmedUnitIds have exact Unit.Detail IDs in both advancing frames. For explicit IDs, list membership is diagnostic; for visible pages, listed membership is required in both lists. Missing relation is unknown; rawAttackable is undocumented. No range, line-of-sight or current-world authority."}
                    _write_json(output/"result.json", report)
                    return report
                previous, previous_at = frame, now
        if index < attempts:
            time.sleep(.3)
    report = {"status":"blocked", "reason":"no-advancing-survey-pair", "inputSent":False,
              "target":target,"sources":sources}
    _write_json(output/"result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-host",required=True)
    parser.add_argument("--physical-pid",type=int,required=True)
    parser.add_argument("--session-id",required=True)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--unit-ids",help="Comma-separated u-prefixed 16-hex unit IDs supplied to /rr2survey bind")
    selection.add_argument("--visible-page",type=int,help="Page selected with /rr2survey bind NONCE visible and /rr2survey page N")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed-index",type=Path)
    parser.add_argument("--scan-mib",type=int,default=16)
    parser.add_argument("--max-attempts",type=int,default=5)
    args=parser.parse_args(argv)
    try:
        ids=requested_ids(args.unit_ids) if args.unit_ids is not None else None
        report=acquire(args.expected_host,args.physical_pid,args.session_id,ids,
                       args.output,args.seed_index,args.scan_mib,args.max_attempts,args.visible_page)
    except (OSError,ValueError,CaptureError,RuntimeError,subprocess.SubprocessError) as error:
        report={"status":"blocked","inputSent":False,"reason":str(error)}
    print(json.dumps(report,ensure_ascii=True,allow_nan=False))
    return 0 if report["status"]=="advancing" else 2


if __name__ == "__main__":
    raise SystemExit(main())
