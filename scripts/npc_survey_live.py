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
from scripts import telemetry_scope_locator as locator
from scripts.capture_physical_telemetry_zone import ReadOnlyWindowsProcess
from scripts.capture_readerbridge_v3 import (
    CaptureError, _loads_json, _read_json, _run_native, _same_target, _target,
    _validate_scout, _validate_seed, _write_json,
)

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


def scout_mapped(target, nonce, player_id, ids, *, page=None,
                 expected_host=None, owner_target=None,
                 reader_factory=ReadOnlyWindowsProcess,
                 selection_reader=physical_rift.select_physical,
                 max_bytes=512 * 1024 * 1024, diagnostics=None):
    """Bounded read-only private-memory scout, without process-specific seed."""
    require(type(max_bytes) is int and 64 * 1024 <= max_bytes <= locator.MAX_SCAN_BYTES,
            "npc-mapped-scout-invalid-byte-budget")
    if diagnostics is not None:
        diagnostics = Path(diagnostics)
        require(diagnostics.parent.is_dir()
                and not diagnostics.exists() and not diagnostics.is_symlink(),
                "npc-mapped-scout-new-diagnostics-file-required")
    host = expected_host if expected_host is not None else target.get("hostName")
    owner = owner_target if owner_target is not None else target
    pid = target.get("processId")
    require(physical_rift.valid_host_name(host)
            and type(pid) is int and pid > 0
            and type(owner) is dict
            and physical_rift.valid_host_name(owner.get("hostName"))
            and owner["hostName"].casefold() == host.casefold()
            and _same_target(owner, target),
            "npc-mapped-scout-invalid-owner-contract")
    first_owner = selection_reader(expected_host=host, physical_pid=pid)
    require(first_owner.get("status") == "ready"
            and first_owner.get("target") == owner,
            "npc-mapped-scout-process-identity-unavailable")
    candidates = []
    with reader_factory(pid) as reader:
        def match(address):
            raw = reader.read(address, 8192)
            require(type(raw) is bytes and len(raw) <= 8192,
                    "npc-mapped-scout-invalid-read")
            end = raw.find(SUFFIX)
            if end < 0:
                return False
            wire = raw[:end + len(SUFFIX)]
            try:
                decode_frame(wire, nonce, player_id, ids, page)
            except (CaptureError, ValueError, UnicodeError, KeyError, TypeError):
                return False
            candidates.append(({"address": f"0x{address:X}",
                                "referenceNames": ["rr2-npc-survey"]}, wire))
            return True
        survey = locator.discover(
            reader, marker=PREFIX, scan_bytes=64 * 1024 * 1024,
            validate_at=match, max_scopes=4, max_bytes=max_bytes)
    last_owner = selection_reader(expected_host=host, physical_pid=pid)
    require(last_owner.get("status") == "ready"
            and last_owner.get("target") == owner,
            "npc-mapped-scout-process-changed")
    if diagnostics is not None:
        with diagnostics.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({
                "schema": "rr2-npc-bounded-map-diagnostics/1",
                "status": ("matching-source-candidates" if candidates
                           else "unqualified-bounded-search"),
                "processId": pid,
                "matchingFrameCandidates": len(candidates),
                "locator": survey,
                "inputSent": False,
                "qualification": "Read-only bounded source-marker survey only; "
                                 "missing candidates do not prove addon absence."
            }, stream, indent=2, allow_nan=False)
            stream.write("\n")
    return candidates


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


def _retain_qualified_source(candidates, source, folder, slot):
    """Persist exact original envelope already decoded by newest, fail closed."""
    require(type(source) is dict and type(source.get("address")) is str
            and type(source.get("sha256")) is str and
            re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None
            and type(slot) is int and 1 <= slot <= 12,
            "npc-survey-retained-wire-source-invalid")
    matches = []
    for row, data in candidates:
        if row.get("address") != source["address"] or type(data) is not bytes:
            continue
        end = data.find(SUFFIX)
        if end < 0:
            continue
        wire = data[:end + len(SUFFIX)]
        if (wire.startswith(PREFIX) and
                hashlib.sha256(wire).hexdigest() == source["sha256"]):
            matches.append(wire)
    require(matches and all(raw == matches[0] for raw in matches),
            "npc-survey-original-wire-unavailable-or-conflicting")
    path = folder / f"frame-{slot:02d}.wire"
    require(not path.exists() and not path.is_symlink(),
            "npc-survey-retained-wire-path-exists")
    with path.open("xb") as out:
        out.write(matches[0])
    require(hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"],
            "npc-survey-retained-wire-hash-mismatch")
    return str(path)


def acquire(host, pid, nonce, ids, output, seed_index=None, scan_mib=16,
            attempts=5, page=None, auto_map=False):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce), "invalid-survey-nonce")
    require(type(auto_map) is bool and not (auto_map and seed_index is not None),
            "invalid-mapped-survey-options")
    require(type(scan_mib) is int and type(attempts) is int
            and 1 <= scan_mib <= 32 and 2 <= attempts <= 12, "invalid-survey-budget")
    if ids is None:
        require(type(page) is int and 1<=page<=342,"invalid-visible-page")
    else:
        require(page is None and ids == requested_ids(",".join(ids)), "invalid-survey-selection")
    selection = physical_rift.select_physical(expected_host=host, physical_pid=pid)
    require(selection.get("status") == "ready", "physical-selection-not-ready")
    owner = selection["target"]
    require(physical_rift.valid_host_name(owner.get("hostName"))
            and owner["hostName"].casefold() == host.casefold(), "survey-host-mismatch")
    host = owner["hostName"]
    target = _target(owner)
    seed = None if auto_map else (Path(seed_index) if seed_index
                                  else survival_live.autodiscover_seed(target))
    if not auto_map:
        base, length = _validate_seed(_read_json(seed), target, scan_mib)
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    player = physical_rift.read_native(selection, "player-context",
                                       output=output / "native-player-context.json")
    require(player.get("status") == "complete" and player.get("target") == owner,
            "survey-player-context-unavailable")
    player_id = survival_live._canonical_unit_key(player["nativeValues"]["unitKey"])
    seen, sources, previous = {}, [], None
    previous_at = previous_utc = None
    for index in range(1, attempts+1):
        start = time.monotonic()
        candidates = (scout_mapped(
            target, nonce, player_id, ids, page=page,
            expected_host=host, owner_target=owner,
            diagnostics=output / f"attempt-{index}.locator.json")
                      if auto_map else
                      scout(target, base, length, output/f"attempt-{index}.scout"))
        if not auto_map:
            require(physical_rift.select_physical(host, pid).get("target") == owner,
                    "survey-process-changed")
        elapsed = time.monotonic()-start
        if elapsed <= (locator.MAX_SECONDS + 1 if auto_map else 5):
            selected = newest(candidates, nonce, player_id, ids, seen, previous, page)
            if selected:
                frame, source = selected
                now = time.monotonic()
                captured_at = datetime.now(timezone.utc)
                retained = _retain_qualified_source(
                    candidates, source, output, len(sources) + 1)
                sources.append(dict(source, epoch=frame["epoch"], sequence=frame["sequence"],
                                    frameTime=frame["frameTime"], attempt=index, readSeconds=elapsed,
                                    capturedAtUtc=captured_at.isoformat(),
                                    retainedWire=retained))
                if previous is not None and (ids is not None or previous["units"].keys()==frame["units"].keys()):
                    host_elapsed = max(now - previous_at, (captured_at - previous_utc).total_seconds())
                    lag = max(0.0, host_elapsed - (frame["frameTime"] - previous["frameTime"]))
                    require(lag<=2, "survey-relative-source-lag")
                    confirmed=sorted(key for key,row in frame["units"].items()
                                     if row["status"]=="observed" and previous["units"][key]["status"]=="observed")
                    report = {"schemaVersion": 1, "evidenceKind": "physical-npc-api-survey/1",
                              "status": "advancing", "inputSent": False, "host":host,
                              "target": dict(target, hostName=host),
                              "playerId": player_id, "seedIndex": str(seed) if seed is not None else None,
                               **({"memoryLocator": "bounded-readable-private-map",
                                   "memorySearchByteBudget": locator.MAX_SCAN_BYTES}
                                  if auto_map else {}),
                               "sources": sources,
                              "relativeSourceLagSeconds":lag,"confirmedUnitIds":confirmed,
                              "snapshot":frame,"observedUnits":len(confirmed),
                              "qualification":"confirmedUnitIds have exact Unit.Detail IDs in both advancing frames. For explicit IDs, list membership is diagnostic; for visible pages, listed membership is required in both lists. Missing relation is unknown; rawAttackable is undocumented. No range, line-of-sight or current-world authority."}
                    _write_json(output/"result.json", report)
                    return report
                previous, previous_at, previous_utc = frame, now, captured_at
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
    parser.add_argument("--auto-map",action="store_true",
                        help="bounded read-only private-memory discovery of exact "
                             "nonce-bound NPC frames without a scout seed")
    parser.add_argument("--scan-mib",type=int,default=16)
    parser.add_argument("--max-attempts",type=int,default=5)
    args=parser.parse_args(argv)
    try:
        ids=requested_ids(args.unit_ids) if args.unit_ids is not None else None
        report=acquire(args.expected_host,args.physical_pid,args.session_id,ids,
                       args.output,args.seed_index,args.scan_mib,args.max_attempts,
                       args.visible_page,auto_map=args.auto_map)
    except (OSError,ValueError,CaptureError,RuntimeError,subprocess.SubprocessError) as error:
        report={"status":"blocked","inputSent":False,"reason":str(error)}
    print(json.dumps(report,ensure_ascii=True,allow_nan=False))
    return 0 if report["status"]=="advancing" else 2


if __name__ == "__main__":
    raise SystemExit(main())
