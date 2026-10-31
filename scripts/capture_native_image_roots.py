"""Capture exact-build, readable RIFT main-image roots without game input.

The PE section plan and native memory map are separate evidence. Only their
committed/readable MEM_IMAGE intersection is captured; missing pages stay holes.
A pointer found in this snapshot remains a candidate, never proof of player HP.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.vmware_guest_session import POWERSHELL, SessionError

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RANGES = 256
MEM_IMAGE = 0x1000000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

GUEST = r'''
param([string]$Mode,[int]$ReaderPid=0,[string]$ReaderExe='',
      [string]$ReaderSha256,[string]$RequestPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
if($Mode -notin @('map-native','snapshot-native')){throw 'native-mode-invalid'}
if($ReaderSha256 -notmatch '^[0-9a-fA-F]{64}$'){throw 'reader-sha-invalid'}
if($ReaderPid -gt 0){
    $r=Get-Process -Id $ReaderPid -ErrorAction Stop
    if($r.ProcessName -ne 'RiftReader2.Live' -or !(Test-Path -LiteralPath $r.Path -PathType Leaf)){
        throw 'native-reader-identity-invalid'
    }
    $exe=$r.Path
} else {
    if([IO.Path]::GetFileName($ReaderExe) -ne 'RiftReader2.Live.exe' -or
       !(Test-Path -LiteralPath $ReaderExe -PathType Leaf)){
        throw 'native-reader-executable-invalid'
    }
    $exe=$ReaderExe
}
if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ne $ReaderSha256){
    throw 'native-reader-sha-mismatch'
}
if(Test-Path -LiteralPath $OutputPath){throw 'native-output-already-exists'}
& $exe $Mode --request $RequestPath --output $OutputPath | Out-Null
if($LASTEXITCODE -ne 0){throw ('native-mode-exit-'+$LASTEXITCODE)}
'''


def exact_hex(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9A-F]+", value):
        raise ValueError("noncanonical-hex-address")
    parsed = int(value, 16)
    if value != f"0x{parsed:X}":
        raise ValueError("noncanonical-hex-address")
    return parsed


def target_from_scope(scope: dict) -> tuple[dict, int, list[tuple[int, int]]]:
    if scope.get("schemaVersion") != 1 or scope.get("evidenceKind") != "rift-image-scope-plan/1":
        raise ValueError("scope-plan-kind-invalid")
    game = scope["game"]
    pid, ticks, sha = game["processId"], game["processStartUtcTicks"], game["executableSha256"]
    if (not isinstance(pid, int) or pid <= 0 or not isinstance(ticks, int) or ticks <= 0
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9A-F]{64}", sha)):
        raise ValueError("scope-game-identity-invalid")
    base, size = exact_hex(game["moduleBase"]), game["moduleSize"]
    sections = []
    for section in scope["writableSections"]:
        if not section["writable"] or section["virtualBytes"] <= 0:
            raise ValueError("scope-nonwritable-section")
        rva, length = exact_hex(section["rva"]), section["virtualBytes"]
        if rva + length > size or exact_hex(section["runtimeStart"]) != base + rva:
            raise ValueError("scope-section-outside-module")
        sections.append((base + rva, base + rva + length))
    sections.sort()
    if not sections or any(a[0] < b[1] for b, a in zip(sections, sections[1:])):
        raise ValueError("scope-sections-empty-or-overlap")
    return {"processId": pid, "processStartUtcTicks": ticks, "executableSha256": sha}, base, sections


def checked_identity(report: dict, target: dict, module_base: int, module_size: int) -> None:
    identity = report["identity"]
    if (report.get("status") == "identity-invalidated" or
            identity["processId"] != target["processId"] or
            identity["processStartUtcTicks"] != target["processStartUtcTicks"] or
            identity["executableSha256"] != target["executableSha256"] or
            identity["moduleBaseAddress"] != module_base or
            identity["moduleSize"] != module_size):
        raise ValueError("native-report-identity-mismatch")


def select_image_ranges(scope: dict, mapping: dict,
                        max_bytes: int = MAX_IMAGE_BYTES) -> dict:
    target, base, sections = target_from_scope(scope)
    if mapping.get("schemaVersion") != 1 or mapping.get("evidenceKind") != "native-memory-map/1":
        raise ValueError("native-map-kind-invalid")
    if mapping.get("status") != "complete":
        raise ValueError("native-map-not-complete")
    checked_identity(mapping, target, base, scope["game"]["moduleSize"])
    regions = []
    previous_end = 0
    for region in sorted(mapping["regions"], key=lambda item: exact_hex(item["baseAddress"])):
        start = exact_hex(region["baseAddress"])
        end = start + region["regionSize"]
        if start < previous_end or end <= start:
            raise ValueError("native-map-region-overlap")
        previous_end = end
        protection = exact_hex(region["protection"])
        if protection & (PAGE_GUARD | PAGE_NOACCESS):
            continue  # ReadProcessMemory must never touch a one-shot guard page.
        if exact_hex(region["type"]) == MEM_IMAGE:
            regions.append((start, end))
    selected = []
    holes = []
    for section_start, section_end in sections:
        covered = []
        for region_start, region_end in regions:
            lo, hi = max(section_start, region_start), min(section_end, region_end)
            if lo < hi:
                covered.append((lo, hi))
        cursor = section_start
        for lo, hi in covered:
            if lo > cursor:
                holes.append({"address": f"0x{cursor:X}", "byteLength": lo - cursor})
            selected.append((lo, hi))
            cursor = hi
        if cursor < section_end:
            holes.append({"address": f"0x{cursor:X}", "byteLength": section_end - cursor})
    if not selected:
        raise ValueError("native-map-no-readable-image-pages")
    total = sum(hi - lo for lo, hi in selected)
    if (not 1 <= max_bytes <= MAX_IMAGE_BYTES or total > max_bytes or
            len(selected) > MAX_RANGES):
        raise ValueError("native-image-scope-exceeds-bounded-capture")
    ranges = [{"addressKind": "module-relative-rva",
               "address": f"0x{lo - base:X}", "byteLength": hi - lo}
              for lo, hi in selected]
    return {"ranges": ranges, "selectedByteCount": total,
            "sectionByteCount": sum(hi - lo for lo, hi in sections),
            "excludedByteCount": sum(hole["byteLength"] for hole in holes),
            "holes": holes, "target": target}


def inspect_snapshot(snapshot: dict, request: dict, map_report: dict,
                     module_base: int) -> dict:
    target = request["target"]
    if snapshot.get("schemaVersion") != 1 or snapshot.get("evidenceKind") != "native-memory-snapshot/1":
        raise ValueError("native-snapshot-kind-invalid")
    checked_identity(snapshot, target, module_base, map_report["identity"]["moduleSize"])
    if snapshot["source"]["requestSha256"] != hashlib.sha256(
            json.dumps(request, separators=(",", ":")).encode("utf-8")).hexdigest().upper():
        raise ValueError("native-snapshot-request-sha-mismatch")
    expected = []
    for item in request["ranges"]:
        start, length = module_base + exact_hex(item["address"]), item["byteLength"]
        for offset in range(0, length, 4096):
            expected.append((start + offset, min(4096, length - offset)))
    if len(snapshot["chunks"]) != len(expected):
        raise ValueError("native-snapshot-chunk-count-mismatch")
    successes = 0
    failed = 0
    successful_bytes = 0
    for chunk, (address, length) in zip(snapshot["chunks"], expected):
        if exact_hex(chunk["address"]) != address or chunk["requestedByteLength"] != length:
            raise ValueError("native-snapshot-chunk-address-mismatch")
        if chunk["status"] == "success":
            raw = base64.b64decode(chunk["bytesBase64"], validate=True)
            if (len(raw) != length or chunk["bytesRead"] != length or
                    hashlib.sha256(raw).hexdigest().upper() != chunk["bytesSha256"]):
                raise ValueError("native-snapshot-chunk-hash-mismatch")
            successes += 1
            successful_bytes += length
        else:
            failed += 1
    if snapshot["status"] == "identity-invalidated":
        raise ValueError("native-snapshot-identity-invalidated")
    if snapshot["status"] == "complete" and failed:
        raise ValueError("native-snapshot-status-conflict")
    return {"status": snapshot["status"], "successfulChunks": successes,
            "failedChunks": failed, "successfulByteCount": successful_bytes,
            "requestedByteCount": sum(length for _, length in expected)}


def run(lab: str, scope_path: Path, reader_pid: int | None,
        reader_exe: str | None, reader_sha256: str,
        *, map_only: bool = False) -> dict:
    if lab not in ("lab1", "lab2") or (reader_pid is None) == (reader_exe is None):
        raise ValueError("invalid-lab-or-reader-selection")
    if reader_pid is not None and reader_pid <= 0:
        raise ValueError("reader-pid-must-be-positive")
    if not re.fullmatch(r"[0-9A-F]{64}", reader_sha256):
        raise ValueError("reader-sha256-invalid")
    approved_root = (ROOT / "artifacts" / "native-module-scopes" / lab).resolve()
    if not scope_path.resolve().is_relative_to(approved_root):
        raise ValueError("scope-plan-must-be-retained-lab-evidence")
    scope = json.loads(scope_path.read_text(encoding="utf-8-sig"))
    target, module_base, _ = target_from_scope(scope)
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    native = api._native(config, settings, api.run_root / ".doctor")
    vm_identity = api.collect_identity(native)
    tag = uuid.uuid4().hex
    folder = ROOT / "artifacts" / "native-module-roots" / lab / tag
    folder.mkdir(parents=True, exist_ok=False)
    map_request = {"schemaVersion": 1, "evidenceKind": "native-memory-map-request/1",
                   "target": target, "maxRegionCount": 32768,
                   "maxDurationMilliseconds": 20000}
    (folder / "map-request.json").write_text(
        json.dumps(map_request, separators=(",", ":")), encoding="utf-8")
    guest_prefix = settings["guestRoot"] + "\\image-roots-" + tag
    guest_script = guest_prefix + ".ps1"
    local_map = folder / "map.json"
    local_snapshot = folder / "snapshot.json"
    with tempfile.TemporaryDirectory() as temporary:
        source_script = Path(temporary) / "image-roots.ps1"
        source_script.write_text(GUEST, encoding="utf-8")
        source_sha = hashlib.sha256(source_script.read_bytes()).hexdigest().upper()
        with api._session(config, settings, vm_identity, folder) as guest:
            guest.run("copyFileFromHostToGuest", str(source_script), guest_script)
            try:
                guest.powershell("if((Get-FileHash -LiteralPath " + ps_literal(guest_script) +
                                 ").Hash -ne " + ps_literal(source_sha) +
                                 "){throw 'image-roots-script-sha-mismatch'}")
                def capture(mode: str, name: str, output: Path) -> None:
                    host_request = folder / (name + "-request.json")
                    guest_request = guest_prefix + "-" + name + "-request.json"
                    guest_output = guest_prefix + "-" + name + ".json"
                    guest.run("copyFileFromHostToGuest", str(host_request), guest_request)
                    expected_sha = hashlib.sha256(host_request.read_bytes()).hexdigest().upper()
                    guest.powershell(
                        "if((Get-FileHash -LiteralPath " + ps_literal(guest_request) +
                        ").Hash -ne " + ps_literal(expected_sha) +
                        "){throw 'image-roots-request-sha-mismatch'}")
                    reader_args = (["-ReaderPid", str(reader_pid)] if reader_pid is not None else
                                   ["-ReaderExe", reader_exe])
                    guest.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                              "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", guest_script, "-Mode", mode,
                              *reader_args, "-ReaderSha256", reader_sha256,
                              "-RequestPath", guest_request, "-OutputPath", guest_output,
                              timeout=160)
                    guest.copy_from_guest(guest_output, output, timeout=180)
                    try:
                        guest.powershell("Remove-Item -LiteralPath " +
                                         ps_literal(guest_request) +
                                         " -Force -ErrorAction SilentlyContinue")
                    except SessionError:
                        pass

                capture("map-native", "map", local_map)
                mapping = json.loads(local_map.read_text(encoding="utf-8-sig"))
                if mapping["requestSha256"] != hashlib.sha256(
                        (folder / "map-request.json").read_bytes()).hexdigest().upper():
                    raise ValueError("native-map-request-sha-mismatch")
                selection = select_image_ranges(scope, mapping)
                report = {"lab": lab, "game": target,
                          "scopePlanSha256": hashlib.sha256(scope_path.read_bytes()).hexdigest().upper(),
                          "mapSha256": hashlib.sha256(local_map.read_bytes()).hexdigest().upper(),
                          "moduleBase": f"0x{module_base:X}",
                          "selection": selection,
                          "qualification": "candidate-scope-only; no HP/owner semantics"}
                if not map_only:
                    request = {"schemaVersion": 1,
                               "evidenceKind": "native-memory-snapshot-request/1",
                               "target": target, "maxDurationMilliseconds": 30000,
                               "ranges": selection["ranges"]}
                    (folder / "snapshot-request.json").write_text(
                        json.dumps(request, separators=(",", ":")), encoding="utf-8")
                    capture("snapshot-native", "snapshot", local_snapshot)
                    snapshot = json.loads(local_snapshot.read_text(encoding="utf-8-sig"))
                    report["snapshot"] = inspect_snapshot(
                        snapshot, request, mapping, module_base)
                    report["snapshotSha256"] = hashlib.sha256(
                        local_snapshot.read_bytes()).hexdigest().upper()
            finally:
                try:
                    guest.powershell("Remove-Item -LiteralPath " +
                                     ps_literal(guest_script) +
                                     " -Force -ErrorAction SilentlyContinue")
                except SessionError:
                    pass
    (folder / "review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"lab": lab, "game": target, "output": str(folder),
            "selectedBytes": selection["selectedByteCount"],
            "excludedBytes": selection["excludedByteCount"],
            "rangeCount": len(selection["ranges"]),
            "snapshot": report.get("snapshot"),
            "qualification": report["qualification"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", required=True, choices=("lab1", "lab2"))
    parser.add_argument("--scope-plan", type=Path, required=True)
    reader = parser.add_mutually_exclusive_group(required=True)
    reader.add_argument("--reader-pid", type=int)
    reader.add_argument("--reader-exe")
    parser.add_argument("--reader-sha256", required=True)
    parser.add_argument("--map-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.lab, args.scope_plan, args.reader_pid, args.reader_exe,
                         args.reader_sha256, map_only=args.map_only), indent=2))


if __name__ == "__main__":
    main()
