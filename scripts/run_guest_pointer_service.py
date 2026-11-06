"""One-use independent host services for a V15->V16 native-pointer trial.

Never opens a VM console or controls gameplay. The already tested claim receiver
and exact-content receiver run in two strictly serialized phases only during a
normal V15 shutdown, with a blocked/unheld canonical authority queue.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_guest_pointer_trial as trial
from scripts.run_guest_inline_service import require_independent_windows_user
from scripts.vm_console_native import Blocked, parse_tcp_listener_rows, process_identity

HOME = trial.HOME
CONFIG = ROOT / "artifacts" / "native-usability-20261020" / "host.json"
CLAIM_RECEIPT = HOME / "rr2-v16-pointer-claim-receipt.json"
UPLOAD_ARCHIVE = HOME / "rr2-v16-pointer-originals.zip"
UPLOAD_RECEIPT = HOME / "rr2-v16-pointer-upload-receipt.json"
SERVER_FILES = {
    "claim": ("receive_guest_inline_zip_claim.py",
              "0C2443EA12427CD346B167DDC26704C2B1E75C7B584FF712BAA3E4BA4FFDDF4A"),
    "upload": ("receive_guest_memory_report.py",
               "C3BB17580C83B8B2BBC9D862148B7B897551707B1E47DA92771633D62C377B3F"),
}
BOUNDARIES = {"claim": (30, 31), "upload": (32, 33)}


def paths_for(phase: str) -> dict[str, Path]:
    if phase not in SERVER_FILES:
        raise Blocked("invalid-pointer-one-use-service-phase")
    stem = "rr2-v16-pointer-" + phase
    return {
        "process": HOME / (stem + "-process.json"),
        "exit": HOME / (stem + "-exited.json"),
        "stdout": HOME / (stem + ".stdout.log"),
        "stderr": HOME / (stem + ".stderr.log"),
    }


def phase_steps(phase: str, plan: dict) -> None:
    done, not_yet = BOUNDARIES[phase]
    previous = trial._step_receipt(done)
    future = trial._step_receipt(not_yet)
    if (not previous.is_file() or
            json.loads(previous.read_bytes()).get("status") != "console-action-completed"
            or future.exists()):
        raise Blocked("native-pointer-service-guest-step-boundary-invalid")
    trial.require_previous_step(done + 1, trial.commands(), plan["vmIdentity"])
    if phase == "upload":
        if not paths_for("claim")["exit"].is_file():
            raise Blocked("native-pointer-claim-server-not-exited")


def server_args(phase: str, plan: dict | None = None) -> tuple[Path, list[str]]:
    filename, expected_sha = SERVER_FILES[phase]
    path = ROOT / "scripts" / filename
    if trial.sha(path.read_bytes()) != expected_sha:
        raise Blocked("native-pointer-reused-server-source-drift")
    if phase == "claim":
        if CLAIM_RECEIPT.exists():
            raise Blocked("native-pointer-claim-receipt-already-used")
        return path, [
            "--kind", "pointer", "--output", str(CLAIM_RECEIPT),
            "--process-id", str(trial.PID),
            "--process-start-ticks", str(trial.TICKS),
            "--game-sha256", trial.GAME_SHA,
            "--bundle-sha256", trial.BUNDLE_SHA,
            "--seconds", "600", "--serve",
        ]
    if plan is None:
        raise Blocked("pointer-upload-needs-exact-vm-plan")
    archive_sha, _ = claim_digest(plan)
    return path, [
        "--kind", "pointer", "--config", str(CONFIG),
        "--output", str(UPLOAD_ARCHIVE),
        "--receipt", str(UPLOAD_RECEIPT),
        "--expected-sha256", archive_sha,
        "--seconds", "600", "--serve",
    ]


def _service_owner(phase: str, plan: dict, *, require_exit: bool) -> dict:
    paths = paths_for(phase)
    if not paths["process"].is_file():
        raise Blocked("native-pointer-one-use-service-never-started")
    info = json.loads(paths["process"].read_bytes())
    pid = info.get("pid")
    _, sha = SERVER_FILES[phase]
    if (type(pid) is not int or pid <= 0
            or info.get("schemaVersion") != 1
            or info.get("purpose") != "one-use-v16-native-pointer-" + phase
            or info.get("phase") != phase
            or info.get("sourceSha256") != sha
            or info.get("requestSha256") != trial.REQUEST_SHA
            or info.get("vmIdentity") != plan.get("vmIdentity")
            or info.get("windowsSessionId") != 2
            or info.get("inJob") is not False
            or info.get("bind") != "192.168.56.1"
            or info.get("allowedGuest") != "192.168.56.128"
            or info.get("port") != 8765):
        raise Blocked("native-pointer-one-use-service-process-provenance-invalid")
    if require_exit:
        if not paths["exit"].is_file():
            raise Blocked("native-pointer-one-use-service-still-unfinished")
        exited = json.loads(paths["exit"].read_bytes())
        if exited.get("pid") != pid or exited.get("phase") != phase:
            raise Blocked("native-pointer-one-use-service-exit-owner-differs")
    elif paths["exit"].exists():
        raise Blocked("native-pointer-one-use-service-exited-before-guest-action")
    return info


def _listener_rows(port: int = 8765) -> list[tuple[str, int]]:
    """Read-only Windows TCP ownership; never open a socket to the guest."""
    if os.name != "nt":
        raise Blocked("native-pointer-listener-check-requires-Windows")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
        wintypes.ULONG, ctypes.c_int, wintypes.ULONG,
    ]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if not size.value:
        raise Blocked("native-pointer-listener-table-unavailable")
    buf = ctypes.create_string_buffer(size.value)
    if get_table(buf, ctypes.byref(size), False, socket.AF_INET, 3, 0):
        raise Blocked("native-pointer-listener-table-unavailable")
    return parse_tcp_listener_rows(bytes(buf.raw[:size.value]), port)


def service_started(phase: str, plan: dict) -> None:
    info = _service_owner(phase, plan, require_exit=False)
    if (process_identity(info["pid"]) != info.get("processIdentity")
            or _listener_rows() != [("192.168.56.1", info["pid"])]):
        raise Blocked("native-pointer-service-pid-or-listener-not-ready")


def _claim(plan: dict, *, allow_received: bool) -> tuple[str, int]:
    _service_owner("claim", plan, require_exit=True)
    if not CLAIM_RECEIPT.is_file():
        raise Blocked("native-pointer-guest-zip-claim-missing")
    if not allow_received and (UPLOAD_ARCHIVE.exists() or UPLOAD_RECEIPT.exists()):
        raise Blocked("native-pointer-zip-upload-target-already-used")
    claim = json.loads(CLAIM_RECEIPT.read_bytes())
    if (claim.get("schemaVersion") != 1
            or claim.get("evidenceKind") != "guest-native-pointer-zip-claim/1"
            or claim.get("source") != "guest-declared-only"
            or claim.get("guest") != "192.168.56.128"
            or claim.get("target") != {
                "processId": trial.PID, "processStartUtcTicks": trial.TICKS,
                "executableSha256": trial.GAME_SHA,
            }
            or claim.get("bundleSha256") != trial.BUNDLE_SHA
            or type(claim.get("zipBytes")) is not int
            or not 1 <= claim["zipBytes"] <= 2 * 1024 * 1024
            or type(claim.get("zipSha256")) is not str
            or len(claim["zipSha256"]) != 64
            or any(c not in "0123456789ABCDEF" for c in claim["zipSha256"])):
        raise Blocked("native-pointer-zip-claim-provenance-differs")
    return claim["zipSha256"], claim["zipBytes"]


def claim_digest(plan: dict) -> tuple[str, int]:
    return _claim(plan, allow_received=False)


def upload_received(plan: dict) -> None:
    sha, length = _claim(plan, allow_received=True)
    _service_owner("upload", plan, require_exit=True)
    if not UPLOAD_ARCHIVE.is_file() or not UPLOAD_RECEIPT.is_file():
        raise Blocked("native-pointer-original-zip-or-upload-receipt-missing")
    if UPLOAD_ARCHIVE.stat().st_size != length:
        raise Blocked("native-pointer-received-original-zip-length-differs")
    if hashlib.sha256(UPLOAD_ARCHIVE.read_bytes()).hexdigest().upper() != sha:
        raise Blocked("native-pointer-received-original-zip-hash-differs")
    from scripts.verify_typed_inline_archive import _transfer_proof
    _transfer_proof(
        UPLOAD_ARCHIVE, sha, length, claim_path=CLAIM_RECEIPT,
        upload_path=UPLOAD_RECEIPT, pid=trial.PID, ticks=trial.TICKS,
        game_sha=trial.GAME_SHA, bundle_sha=trial.BUNDLE_SHA,
        expected_guest="192.168.56.128", claim_kind="pointer",
    )


def run_phase(phase: str) -> None:
    paths = paths_for(phase)
    if any(p.exists() for p in paths.values()):
        raise Blocked("native-pointer-one-use-service-already-started")
    session, in_job = require_independent_windows_user()
    plan = trial.maintenance()
    trial.commands()
    phase_steps(phase, plan)
    from scripts.control_host import HostConfig, VmEpochGuard
    cfg = HostConfig.load(CONFIG)
    if VmEpochGuard(cfg).collect() != plan["vmIdentity"]:
        raise Blocked("native-pointer-service-vm-epoch-drift")
    path, args = server_args(phase, plan)
    with paths["stdout"].open("x", encoding="utf-8", buffering=1) as out, (
            paths["stderr"].open("x", encoding="utf-8", buffering=1)) as err, (
            contextlib.redirect_stdout(out)), contextlib.redirect_stderr(err):
        with paths["process"].open("x", encoding="utf-8") as receipt:
            json.dump({
                "schemaVersion": 1,
                "purpose": "one-use-v16-native-pointer-" + phase,
                "pid": os.getpid(),
                "processIdentity": process_identity(os.getpid()),
                "phase": phase, "sourceSha256": trial.sha(path.read_bytes()),
                "requestSha256": trial.REQUEST_SHA, "vmIdentity": plan["vmIdentity"],
                "windowsSessionId": session, "inJob": in_job,
                "allowedGuest": "192.168.56.128", "bind": "192.168.56.1",
                "port": 8765, "startedUtc": datetime.now(timezone.utc).isoformat(),
            }, receipt, indent=2)
            receipt.write("\n")
        sys.argv = [str(path)] + args
        try:
            runpy.run_path(str(path), run_name="__main__")
        finally:
            with paths["exit"].open("x", encoding="utf-8") as receipt:
                json.dump({
                    "pid": os.getpid(), "phase": phase,
                    "atUtc": datetime.now(timezone.utc).isoformat(),
                }, receipt, indent=2)
                receipt.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(SERVER_FILES), required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        if args.preview:
            if args.phase == "claim":
                path, commands = server_args("claim")
            else:
                filename, expected = SERVER_FILES["upload"]
                path = ROOT / "scripts" / filename
                if trial.sha(path.read_bytes()) != expected:
                    raise Blocked("native-pointer-reused-server-source-drift")
                commands = ["--kind", "pointer", "--serve"]  # Preview excludes the unreceived digest.
            print(json.dumps({"state": "verified-no-listener", "phase": args.phase,
                              "scriptSha256": trial.sha(path.read_bytes()),
                              "sourceArgs": commands, "guestServiceStarted": False}))
        else:
            run_phase(args.phase)
        return 0
    except (Blocked, ValueError, OSError, KeyError, TypeError, AssertionError) as error:
        print(json.dumps({"state": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
