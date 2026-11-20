"""Read-only physical RR2 native/Telemetry Lua zone bracket acquisition.

Captures source SHA-pinned raw Telemetry RIFTTLM1 frames between two existing
guarded native zone reads. Explicit AMD-DESKTOP PID/start/build is revalidated.
No game input, UI automation, reload, memory writes or sibling-repo changes.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts import replay_physical_telemetry_zone as verify

HOST = "AMD-DESKTOP"
BUILD_SHA = verify.SHA_1179
MARKER = verify.PREFIX + b"{"
SUFFIX = verify.SUFFIX
CHUNK = 64 * 1024
MAX_FRAME_BYTES = 32_768
MAX_MARKERS = 50


def require(ok, reason):
    if not ok:
        raise ValueError("telemetry-zone-capture-" + reason)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical_address(value):
    require(type(value) is str and re.fullmatch(r"0x[1-9A-F][0-9A-F]*", value) is not None,
            "noncanonical-start-address")
    number = int(value[2:], 16)
    require(0x10000 <= number < 0x7FFF_FFFF_FFFF and
            f"0x{number:X}" == value, "invalid-start-address")
    return number


def admission(pid, start_address, scan_bytes, gap_ms):
    require(socket.gethostname().upper() == HOST, "wrong-host")
    require(type(pid) is int and 0 < pid < 2**31, "explicit-pid-required")
    start = canonical_address(start_address)
    require(type(scan_bytes) is int and CHUNK <= scan_bytes <= 128 * 1024 * 1024
            and scan_bytes % CHUNK == 0 and
            start + scan_bytes < 0x7FFF_FFFF_FFFF, "invalid-scan-budget")
    require(type(gap_ms) is int and 0 <= gap_ms <= 2000, "invalid-gap")
    selection = physical_rift.select_physical(HOST, pid)
    t = selection.get("target")
    require(selection.get("status") == "ready"
            and selection.get("ownerHost") == HOST and type(t) is dict
            and t.get("hostName") == HOST and t.get("processId") == pid
            and str(t.get("processStartUtcTicks", "")).isdecimal()
            and str(t.get("executableSha256", "")).upper() == BUILD_SHA,
            "physical-epoch-or-build-unavailable")
    return selection, start


class ReadOnlyWindowsProcess:
    """Only PROCESS_VM_READ | PROCESS_QUERY_INFORMATION; no write privileges."""

    def __init__(self, pid):
        self.pid, self.handle, self.kernel = pid, None, None

    def __enter__(self):
        if sys.platform != "win32":
            raise OSError("Read-only RIFT acquisition requires Windows.")
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.OpenProcess.restype = ctypes.c_void_p
        k.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        k.ReadProcessMemory.restype = ctypes.c_int
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CloseHandle.restype = ctypes.c_int
        handle = k.OpenProcess(0x0410, 0, self.pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess read-only failed")
        self.handle, self.kernel = handle, k
        return self

    def read(self, address, length):
        require(type(address) is int and type(length) is int
                and 0x10000 <= address < 0x7FFF_FFFF_FFFF and
                1 <= length <= CHUNK and address + length < 0x7FFF_FFFF_FFFF,
                "invalid-read-window")
        buffer = ctypes.create_string_buffer(length)
        done = ctypes.c_size_t()
        ok = self.kernel.ReadProcessMemory(self.handle, ctypes.c_void_p(address),
                                           buffer, length, ctypes.byref(done))
        return bytes(buffer.raw[:done.value]) if ok or done.value > 0 else b""

    def __exit__(self, *_):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def find_markers(reader, *, start, scan_bytes):
    """A bounded scope only; a miss never claims process-wide absence."""
    seen, previous, bytes_read, incomplete = [], b"", 0, 0
    for offset in range(0, scan_bytes, CHUNK):
        address = start + offset
        raw = reader.read(address, CHUNK)
        require(type(raw) is bytes and len(raw) <= CHUNK, "invalid-process-read")
        bytes_read += len(raw)
        if len(raw) != CHUNK:
            incomplete += 1
        segment = previous + raw
        cursor = 0
        while len(seen) < MAX_MARKERS:
            found = segment.find(MARKER, cursor)
            if found == -1:
                break
            located = address - len(previous) + found
            if start <= located < start + scan_bytes and located not in seen:
                seen.append(located)
            cursor = found + 1
        previous = raw[-(len(MARKER) - 1):] if len(raw) == CHUNK else b""
        if len(seen) == MAX_MARKERS:
            break
    return seen, bytes_read, incomplete


def scan(reader, directory, *, start, scan_bytes, expected_player):
    """One bounded read-only region scan; never assumes prefix==complete frame."""
    directory.mkdir()
    started = utc()
    seen, bytes_read, incomplete = find_markers(reader, start=start, scan_bytes=scan_bytes)

    rows = []
    for number, addr in enumerate(seen, 1):
        raw = reader.read(addr, MAX_FRAME_BYTES)
        require(type(raw) is bytes and len(raw) <= MAX_FRAME_BYTES,
                "invalid-candidate-read")
        end = raw.find(SUFFIX)
        if end < 0:
            rows.append({"addr": f"0x{addr:x}", "error": "incomplete"})
            continue
        wire = raw[:end + len(SUFFIX)]
        try:
            root = verify.exact_json(wire[len(verify.PREFIX):-len(SUFFIX)])
            detail = root.get("playerTelemetry") or {}
            zone = detail.get("zone") or {}
            row = {"addr": f"0x{addr:x}", "seq": root.get("sequence"),
                   "epoch": root.get("epoch"), "session": root.get("sessionId"),
                   "clock": root.get("frameTime"), "zoneId": zone.get("id")}
            verify._frame(wire, row, expected_player)
        except (ValueError, TypeError, AttributeError):
            rows.append({"addr": f"0x{addr:x}", "error": "schema-or-player-zone"})
            continue
        path = directory / f"frame-{number:02d}.wire"
        path.write_bytes(wire)
        rows.append({**row, "wire": str(path), "sha": verify.digest(wire)})
    return {"startedAtUtc": started, "completedAtUtc": utc(),
            "readBytes": bytes_read, "failedChunks": incomplete,
            "hits": len(seen), "frames": rows}


def survey_scopes(reader, *, start, scan_bytes, scope_count, expected_player, expected_zone):
    """Find a plausible current publisher scope, not authoritative Lua evidence.

    The replay-tested *acquisition* still scans two new passes and requires
    advancing frames. Survey bytes never become trusted source observations.
    """
    require(type(scope_count) is int and 1 <= scope_count <= 8 and
            type(start) is int and type(scan_bytes) is int and scan_bytes >= CHUNK and
            start + scan_bytes * scope_count < 0x7FFF_FFFF_FFFF,
            "invalid-scope-count-or-range")
    started = time.monotonic()
    ranked, inventory = [], []
    for index in range(scope_count):
        require(time.monotonic() - started <= 15, "survey-time-budget-exceeded")
        address = start + index * scan_bytes
        hits, read_bytes, missing = find_markers(reader, start=address,
                                                 scan_bytes=scan_bytes)
        groups = {}
        valid = 0
        for marker_addr in hits:
            raw = reader.read(marker_addr, MAX_FRAME_BYTES)
            require(type(raw) is bytes and len(raw) <= MAX_FRAME_BYTES,
                    "invalid-survey-read")
            end = raw.find(SUFFIX)
            if end < 0:
                continue
            wire = raw[:end + len(SUFFIX)]
            try:
                root = verify.exact_json(wire[len(verify.PREFIX):-len(SUFFIX)])
                detail = root.get("playerTelemetry") or {}
                zone = detail.get("zone") or {}
                row = {"seq": root.get("sequence"), "epoch": root.get("epoch"),
                       "session": root.get("sessionId"), "clock": root.get("frameTime"),
                       "zoneId": zone.get("id")}
                source = verify._frame(wire, row, expected_player)
                if source["zoneId"] != expected_zone:
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
            valid += 1
            key = (source["session"], source["epoch"])
            groups.setdefault(key, []).append(source)
        choices = []
        for (session, epoch), rows in groups.items():
            by_sequence = {}
            conflicted = False
            for row in rows:
                existing = by_sequence.get(row["seq"])
                if existing is not None and existing["clock"] != row["clock"]:
                    conflicted = True
                by_sequence[row["seq"]] = row
            ordered = sorted(by_sequence.values(), key=lambda row: row["seq"])
            if (conflicted or len(ordered) < 2 or any(
                    a["clock"] >= b["clock"] for a, b in zip(ordered, ordered[1:]))):
                continue
            best = max(ordered, key=lambda row: row["seq"])
            choices.append((epoch, best["clock"], best["seq"], len(ordered), session))
        row = {"startAddress": f"0x{address:X}", "readBytes": read_bytes,
               "missingChunks": missing, "markerHits": len(hits),
               "validFrameCandidates": valid,
               "candidateGenerations": len(choices)}
        if choices:
            top = max(choices)
            row.update(topEpoch=top[0], topSourceClock=top[1],
                       topSequence=top[2], topSession=top[4])
            ranked.append((top, address))
        inventory.append(row)
    selected = max(ranked)[1] if ranked else None
    return {"status": "scoped-candidate" if selected is not None else "unqualified",
            "baseStartAddress": f"0x{start:X}",
            "selectedStartAddress": f"0x{selected:X}" if selected is not None else None,
            "surveyedBytes": sum(item["readBytes"] for item in inventory),
            "expectedZoneIdCandidate": expected_zone,
            "scopes": inventory,
            "qualification": ("Survey-only exact-player source-clock candidate ranking; "
                              "not a source-freshness result. Separate new scans, "
                              "native owner brackets and replay still required.")}


def native_zone(selection, directory, which):
    path = directory / f"native-{which}.json"
    result = physical_rift.read_native(selection, "zone-context", output=path)
    require(result.get("status") == "complete"
            and result.get("target") == selection["target"]
            and result.get("nativeRead") == "zone-context"
            and result.get("nativeOutput") == str(path)
            and path.is_file() and not path.is_symlink(),
            "native-zone-read-unavailable")
    values = result["nativeValues"]
    require(values["status"] == "available-candidate", "native-zone-unavailable")
    return {"source": str(path), "sha256": result["nativeSourceSha256"],
            "zoneIdCandidate": values["zoneIdCandidate"],
            "startedAtUtc": values["startedAtUtc"],
            "completedAtUtc": values["sampledAtUtc"]}


def collect(pid, output_dir, *, start_address="0x13000000",
            scan_bytes=64*1024*1024, gap_ms=600, reader_factory=ReadOnlyWindowsProcess,
            auto_scope=False, scope_count=4):
    require(type(auto_scope) is bool and type(scope_count) is int
            and 1 <= scope_count <= 8, "invalid-auto-scope-options")
    selection, start = admission(pid, start_address, scan_bytes, gap_ms)
    require(not auto_scope or start + scan_bytes * scope_count < 0x7FFF_FFFF_FFFF,
            "invalid-auto-scope-range")
    root = Path(output_dir)
    require(not root.exists() and not root.is_symlink() and root.parent.is_dir(),
            "new-output-directory-required")
    root.mkdir()
    target = selection["target"]
    survey = None
    preflight_player = None
    if auto_scope:
        # This owner read precedes the timed native->Lua->native bracket. It
        # supplies the player and zone only for selecting candidate scan scope.
        preflight = native_zone(selection, root, "survey-owner")
        preflight_report, _ = verify.load(root / "native-survey-owner.json",
                                          preflight["sha256"])
        preflight_player = f"u{int(preflight_report['observation']['selfKey']):016X}"
        require(physical_rift.select_physical(HOST, pid).get("target") == target,
                "changed-process-before-survey")
        with reader_factory(pid) as survey_reader:
            survey = survey_scopes(survey_reader, start=start, scan_bytes=scan_bytes,
                                   scope_count=scope_count,
                                   expected_player=preflight_player,
                                   expected_zone=preflight["zoneIdCandidate"])
        survey["nativePreflightSourceSha256"] = preflight["sha256"]
        (root / "scope-survey.json").write_text(
            json.dumps(survey, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        require(survey["status"] == "scoped-candidate",
                "no-current-player-zone-scope-in-survey")
        start = int(survey["selectedStartAddress"], 16)
        require(physical_rift.select_physical(HOST, pid).get("target") == target,
                "changed-process-after-survey")
    player = None
    before = native_zone(selection, root, "before")
    native_data, _ = verify.load(root / "native-before.json", before["sha256"])
    player = f"u{int(native_data['observation']['selfKey']):016X}"
    require(preflight_player is None or preflight_player == player,
            "survey-versus-bracket-player-changed")
    require(physical_rift.select_physical(HOST, pid).get("target") == target,
            "changed-process-before-scan")
    with reader_factory(pid) as reader:
        first = scan(reader, root / "pass-01", start=start, scan_bytes=scan_bytes,
                     expected_player=player)
        require(physical_rift.select_physical(HOST, pid).get("target") == target,
                "changed-process-after-first-scan")
        if gap_ms:
            time.sleep(gap_ms / 1000)
        second = scan(reader, root / "pass-02", start=start, scan_bytes=scan_bytes,
                      expected_player=player)
    require(physical_rift.select_physical(HOST, pid).get("target") == target,
            "changed-process-after-second-scan")
    after = native_zone(selection, root, "after")
    same_epoch = physical_rift.select_physical(HOST, pid).get("target") == target
    report = {
        "schemaVersion":1,
        "evidenceKind":"physical-native-telemetry-zone-bracket-candidate/1",
        "status":"unqualified",
        "target":target,
        "sameProcessEpoch":same_epoch,
        **({"scopeSurvey": survey} if survey is not None else {}),
        "nativeBefore":before, "nativeAfter":after,
        "passes":[first, second],
        "sourceClockProgression":"unqualified",
        "newSourceSequenceCount":None,
        "qualification":("Read-only bounded independent Lua/native candidates only; "
                         "not atomic, source clock not host UTC-synchronized, "
                         "no world-instance identity or action causation.")
    }
    original_zone = before["zoneIdCandidate"]
    observed = [[x for x in p["frames"] if "sha" in x] for p in (first,second)]
    if same_epoch and all(len(rows)>=2 for rows in observed):
        session_epochs={(x["session"],x["epoch"]) for rows in observed for x in rows}
        by_sequence={}
        for row in (x for group in observed for x in group):
            key=row["seq"]
            if key in by_sequence:
                if (by_sequence[key]["sha"],by_sequence[key]["clock"]) != (row["sha"],row["clock"]):
                    session_epochs.add(("conflict",0))
            else:
                by_sequence[key]=row
        order=sorted(by_sequence.values(),key=lambda x:x["seq"])
        newer=[x for x in observed[1] if x["seq"] > max(y["seq"] for y in observed[0])]
        advancing=(len(session_epochs)==1 and bool(newer)
                   and all(a["clock"]<b["clock"] for a,b in zip(order,order[1:])))
        if advancing:
            report["sourceClockProgression"]="advancing"
            report["newSourceSequenceCount"]=len(newer)
            if after["zoneIdCandidate"] == original_zone and all(
                    x["zoneId"]==original_zone for x in order):
                report["status"]="matching-candidates"
    path = root / "summary.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",encoding="utf-8")
    if report["status"]=="matching-candidates":
        # Require independent on-disk source and chronology replay before success.
        accepted = verify.replay(path)
        require(accepted["status"]=="matching-candidates",
                "independent-source-replay-refused")
    return path, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-pid",required=True,type=int)
    parser.add_argument("--start-address",default="0x13000000")
    parser.add_argument("--scan-bytes",type=int,default=64*1024*1024)
    parser.add_argument("--gap-ms",type=int,default=600)
    parser.add_argument("--auto-scope",action="store_true",
                        help="bounded read-only survey selects a current player/zone candidate region before the capture bracket")
    parser.add_argument("--scope-count",type=int,default=4,
                        help="1–8 adjacent regions of --scan-bytes each; only used by --auto-scope")
    parser.add_argument("--output-dir",type=Path,
                        default=ROOT/"artifacts"/("physical-telemetry-zone-"+uuid.uuid4().hex))
    args=parser.parse_args(argv)
    try:
        path, report=collect(args.physical_pid,args.output_dir,
                             start_address=args.start_address,scan_bytes=args.scan_bytes,
                             gap_ms=args.gap_ms, auto_scope=args.auto_scope,
                              scope_count=args.scope_count)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc)[:220]}))
        return 2
    print(json.dumps({"status":report["status"],"summary":str(path),
                      "summarySha256":verify.digest(path.read_bytes()),
                      "processId":report["target"]["processId"],
                      "zoneIdCandidate":report["nativeAfter"]["zoneIdCandidate"],
                      "frames":[sum("sha" in x for x in p["frames"]) for p in report["passes"]],
                      "sourceClockProgression":report["sourceClockProgression"],
                      "surveySelectedStartAddress":(report.get("scopeSurvey") or {}).get("selectedStartAddress"),
                      "qualification":report["qualification"]}))
    return 0 if report["status"]=="matching-candidates" else 2


if __name__=="__main__":
    raise SystemExit(main())
