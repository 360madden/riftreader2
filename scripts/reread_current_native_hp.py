"""Reread a few current-build HP structures without scanning or game input.

Source must be the SHA-retained current-epoch native scout ZIP. This is
candidate persistence evidence, never authoritative HP qualification.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.vmware_guest_session import POWERSHELL, SessionError
from scripts.scout_current_native_health import BUILD

GUEST = r'''
param([int]$ReaderPid=0,[string]$ReaderExe='',[string]$ReaderSha256='',
      [string]$RequestPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
if($ReaderPid -gt 0){
    $r=Get-Process -Id $ReaderPid -ErrorAction Stop
    if($r.ProcessName -ne 'RiftReader2.Live' -or !(Test-Path -LiteralPath $r.Path)){
        throw 'native-reader-missing'
    }
    $exe=$r.Path
} else {
    if($ReaderSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
       [IO.Path]::GetFileName($ReaderExe) -ne 'RiftReader2.Live.exe' -or
       !(Test-Path -LiteralPath $ReaderExe -PathType Leaf)){
        throw 'native-reader-executable-invalid'
    }
    if((Get-FileHash -LiteralPath $ReaderExe -Algorithm SHA256).Hash -ne $ReaderSha256){
        throw 'native-reader-executable-sha-mismatch'
    }
    $exe=$ReaderExe
}
if(Test-Path -LiteralPath $OutputPath){throw 'output-already-exists'}
& $exe snapshot-native --request $RequestPath --output $OutputPath | Out-Null
if($LASTEXITCODE -ne 0){throw ('native-snapshot-exit-'+$LASTEXITCODE)}
'''


def candidates(archive_path: Path, health: int, level: int, limit: int = 5) -> tuple[dict, list]:
    if not 1 <= limit <= 64 or health <= 0 or level <= 0:
        raise ValueError("invalid-selection")
    if not archive_path.is_file() or archive_path.stat().st_size > 4_000_000:
        raise ValueError("scout-archive-missing-or-oversized")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) > 260 or len(names) != len(set(names)) or "index.json" not in names:
            raise ValueError("scout-archive-layout-invalid")
        index = json.loads(archive.read("index.json"))
        if index.get("evidenceKind") != "native-value-scout/1":
            raise ValueError("scout-evidence-kind-invalid")
        target = index["request"]["target"]
        if target["executableSha256"] != BUILD:
            raise ValueError("scout-build-mismatch")
        selected = {}
        for candidate in index["candidates"]:
            filename = candidate.get("snapshotFile")
            if candidate["status"] != "success" or not isinstance(filename, str):
                continue
            if filename not in names or "/" in filename or "\\" in filename:
                raise ValueError("scout-candidate-file-invalid")
            raw = archive.read(filename)
            if hashlib.sha256(raw).hexdigest().upper() != candidate["snapshotSha256"]:
                raise ValueError("scout-snapshot-sha-mismatch")
            saved = json.loads(raw)
            if (saved["identity"]["processId"], saved["identity"]["processStartUtcTicks"],
                    saved["identity"]["executableSha256"]) != (
                    target["processId"], target["processStartUtcTicks"], BUILD):
                raise ValueError("scout-candidate-identity-mismatch")
            chunk = saved["chunks"][0]
            data = base64.b64decode(chunk["bytesBase64"], validate=True)
            if (chunk["status"] != "success" or len(data) != chunk["requestedByteLength"]
                    or hashlib.sha256(data).hexdigest().upper() != chunk["bytesSha256"]):
                raise ValueError("scout-candidate-bytes-invalid")
            base = int(chunk["address"], 16)
            for at in range(32, len(data) - 16, 4):
                if (struct.unpack_from("<i", data, at - 8)[0] == level
                        and struct.unpack_from("<i", data, at - 4)[0] == 65536
                        and all(struct.unpack_from("<i", data, at + 8 * n)[0] == health
                                for n in range(3))):
                    start = base + at - 32
                    if start == base and start not in selected:
                        selected[start] = data[:100]
        ranges = [(address, selected[address]) for address in sorted(selected)[:limit]]
        if not ranges:
            raise ValueError("no-structural-hp-candidates")
        return target, ranges


def run(lab: str, reader_pid: int | None, reader_exe: str | None,
        reader_sha256: str | None, archive: Path, health: int,
        level: int, limit: int = 5, before: int = 0, after: int = 0,
        addresses: list[str] | None = None) -> dict:
    if lab not in ("lab1", "lab2") or (reader_pid is None) == (reader_exe is None) or (
            reader_pid is not None and reader_pid <= 0):
        raise ValueError("invalid-lab-or-reader")
    if reader_exe is not None and (not reader_sha256 or len(reader_sha256) != 64):
        raise ValueError("guest-reader-executable-sha-required")
    if not 0 <= before <= 1024 or not 0 <= after <= 1024:
        raise ValueError("invalid-context-padding")
    if addresses is not None and (not 1 <= len(addresses) <= 16 or len(addresses) > limit):
        raise ValueError("invalid-explicit-selection")
    target, ranges = candidates(archive, health, level,
                                limit=64 if addresses is not None else limit)
    if addresses is not None:
        try:
            wanted = [int(raw, 16) for raw in addresses]
        except ValueError as error:
            raise ValueError("invalid-explicit-address") from error
        available = {address for address, _ in ranges}
        if len(wanted) != len(set(wanted)) or not set(wanted) <= available:
            raise ValueError("explicit-address-not-in-source-candidates")
        ranges = [(address, data) for address, data in ranges if address in wanted]
    windows = sorted((address - before, len(original) + before + after)
                     for address, original in ranges)
    if any(start < previous_start + previous_size
           for (previous_start, previous_size), (start, _) in zip(windows, windows[1:])):
        raise ValueError("extended-context-overlap")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    native = api._native(config, settings, api.run_root / ".doctor")
    vm_identity = api.collect_identity(native)
    tag = uuid.uuid4().hex
    folder = ROOT / "artifacts/native-current-health" / lab / ("reread-" + tag)
    folder.mkdir(parents=True, exist_ok=False)
    request = {
        "schemaVersion": 1, "evidenceKind": "native-memory-snapshot-request/1",
        "target": target, "maxDurationMilliseconds": 5000,
        "ranges": [{"addressKind": "absolute-session-address",
                    "address": f"0x{address - before:X}",
                    "byteLength": len(data) + before + after}
                   for address, data in ranges],
    }
    req_path = folder / "request.json"
    req_path.write_text(json.dumps(request, separators=(",", ":")), encoding="utf-8")
    guest_root = settings["guestRoot"] + "\\hp-reread-" + tag
    guest_req = guest_root + ".json"
    guest_ps = guest_root + ".ps1"
    guest_output = guest_root + "-snapshot.json"
    with tempfile.TemporaryDirectory() as temporary:
        local_ps = Path(temporary) / "read.ps1"
        local_ps.write_text(GUEST, encoding="utf-8")
        with api._session(config, settings, vm_identity, folder) as guest:
            guest.run("copyFileFromHostToGuest", str(local_ps), guest_ps)
            guest.run("copyFileFromHostToGuest", str(req_path), guest_req)
            try:
                expected = hashlib.sha256(req_path.read_bytes()).hexdigest().upper()
                guest.powershell(
                    "if((Get-FileHash -LiteralPath '" + guest_req +
                    "').Hash -ne '" + expected + "'){throw 'request-sha-mismatch'}")
                reader_args = (["-ReaderPid", str(reader_pid)] if reader_exe is None else
                               ["-ReaderExe", reader_exe, "-ReaderSha256", reader_sha256])
                guest.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                          "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-File", guest_ps, *reader_args,
                          "-RequestPath", guest_req, "-OutputPath", guest_output, timeout=45)
                guest.copy_from_guest(guest_output, folder / "snapshot.json")
            finally:
                try:
                    guest.powershell("Remove-Item -LiteralPath '" + guest_ps + "','" +
                                     guest_req + "' -Force -ErrorAction SilentlyContinue")
                except SessionError:
                    pass
    snapshot_raw = (folder / "snapshot.json").read_bytes()
    snapshot = json.loads(snapshot_raw)
    if snapshot["status"] != "complete" or snapshot["identity"]["processId"] != target["processId"] or \
            snapshot["identity"]["processStartUtcTicks"] != target["processStartUtcTicks"] or \
            snapshot["identity"]["executableSha256"] != BUILD:
        raise ValueError("native-reread-not-complete-or-identity-mismatch")
    if len(snapshot["chunks"]) != len(ranges):
        raise ValueError("native-reread-chunk-count-mismatch")
    compared = []
    for chunk, (address, original) in zip(snapshot["chunks"], ranges):
        data = base64.b64decode(chunk["bytesBase64"], validate=True)
        if (chunk["status"] != "success" or
                int(chunk["address"], 16) != address - before or
                len(data) != len(original) + before + after or
                hashlib.sha256(data).hexdigest().upper() != chunk["bytesSha256"]):
            raise ValueError("native-reread-chunk-invalid")
        core = data[before:before + len(original)]
        marker_ok = (struct.unpack_from("<i", core, 24)[0] == level and
                     struct.unpack_from("<i", core, 28)[0] == 65536)
        hps = [struct.unpack_from("<i", core, 32 + 8 * n)[0] for n in range(3)]
        compared.append({
            "address": f"0x{address:X}",
            "capturedFrom": f"0x{address - before:X}", "capturedBytes": len(data),
            "unchanged": core == original,
            "changedBytes": sum(a != b for a, b in zip(core, original)),
            "layoutPreserved": marker_ok and len(set(hps)) == 1 and hps[0] > 0,
            "rereadHpTriplet": hps if marker_ok else None,
        })
    report = {
        "lab": lab, "gamePid": target["processId"],
        "gameStartUtcTicks": target["processStartUtcTicks"],
        "executableSha256": BUILD, "healthSeed": health, "levelSeed": level,
        "contextBeforeBytes": before, "contextAfterBytes": after,
        "sourceArchiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest().upper(),
        "snapshotSha256": hashlib.sha256(snapshot_raw).hexdigest().upper(),
        "snapshots": compared,
        "counts": {"selected": len(compared),
                   "layoutPreserved": sum(s["layoutPreserved"] for s in compared),
                   "layoutLost": sum(not s["layoutPreserved"] for s in compared)},
        "qualification": "candidate-only; no changed-state or owner proof",
    }
    (folder / "review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    reader = p.add_mutually_exclusive_group(required=True)
    reader.add_argument("--reader-pid", type=int)
    reader.add_argument("--reader-exe")
    p.add_argument("--reader-sha256")
    p.add_argument("--scout-archive", type=Path, required=True)
    p.add_argument("--health", type=int, required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--limit", type=int, default=5, help="Maximum saved contexts to reread (1-64)")
    p.add_argument("--context-before", type=int, default=0, help="Additional prefix bytes (0-1024)")
    p.add_argument("--context-after", type=int, default=0, help="Additional suffix bytes (0-1024)")
    p.add_argument("--address", action="append",
                   help="Repeat for exact saved context addresses; cap 16, with --limit set high enough")
    a = p.parse_args()
    report = run(a.lab, a.reader_pid, a.reader_exe, a.reader_sha256,
                 a.scout_archive, a.health, a.level, limit=a.limit,
                 before=a.context_before, after=a.context_after, addresses=a.address)
    print(json.dumps({k: report[k] for k in
                      ("lab", "gamePid", "healthSeed", "levelSeed", "counts",
                       "qualification")}, indent=2))


if __name__ == "__main__":
    main()
