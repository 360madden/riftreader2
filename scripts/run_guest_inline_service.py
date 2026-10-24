"""One-use independent Windows host services for the guarded typed-inline guest trial.

Run under signed-in session-two pythonw.exe, never a Workbridge child job.
Only one exact VMnet8 bundle-download, ZIP digest claim, or ZIP upload endpoint
is exposed at a time. Each phase checks the quarantined V14 -> V15 handover,
guest-console step receipts, exact service source hash, and exclusive phase
boundaries before binding port 8765.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_guest_inline_trial as trial
from scripts.vm_console_native import Blocked, process_identity

HOME = trial.HOME
CONFIG = ROOT / "artifacts" / "native-usability-20261020" / "host.json"
SERVER_FILES = {
    "download": ("serve_guest_native_scout.py",
                 "E353D166ED8E56157259832C548558643DC5AF1C39530246B09199F4E4892F34"),
    "claim": ("receive_guest_inline_zip_claim.py",
              "D1F1883BFF3BF7F24DE0920B15E03CCE6E207BAB2CCC6E19306D6AA52B5611D4"),
    "upload": ("receive_guest_memory_report.py",
               "5A85444650D60C78AE9B31F2D41E978ED5C141F7902C53797D5AE21A05D84ED0"),
}
BOUNDARIES = {"download": (2, 3), "claim": (28, 29), "upload": (30, 31)}
CLAIM_RECEIPT = HOME / "rr2-inline-oct24-01-claim-receipt.json"
UPLOAD_RECEIPT = HOME / "rr2-inline-oct24-01-upload-receipt.json"
UPLOAD_ARCHIVE = HOME / "rr2-inline-oct24-01-host.zip"


def phase_steps(phase: str) -> None:
    if phase not in BOUNDARIES:
        raise Blocked("unsupported-inline-service-phase")
    done, not_yet = BOUNDARIES[phase]
    completed = HOME / (trial.PREFIX + f"{done:02}") / "receipt.json"
    future = HOME / (trial.PREFIX + f"{not_yet:02}") / "receipt.json"
    if (not completed.is_file()
            or json.loads(completed.read_text("utf-8")).get("status") != "completed"
            or future.exists()):
        raise Blocked("one-use-service-guest-step-boundary-invalid")
    for other in SERVER_FILES:
        if other == phase:
            continue
        if other == "download" and phase != "download":
            if not (HOME / "rr2-inline-download-exited.json").is_file():
                raise Blocked("guest-bundle-server-not-exited")
        if other == "claim" and phase == "upload":
            if not (HOME / "rr2-inline-claim-exited.json").is_file():
                raise Blocked("guest-claim-server-not-exited")


def upload_digest() -> str:
    if not CLAIM_RECEIPT.is_file() or UPLOAD_ARCHIVE.exists() or UPLOAD_RECEIPT.exists():
        raise Blocked("claim-receipt-missing-or-upload-target-used")
    info = json.loads(CLAIM_RECEIPT.read_text("utf-8"))
    if (info.get("schemaVersion") != 1
            or info.get("evidenceKind") != "guest-typed-inline-zip-claim/1"
            or info.get("source") != "guest-declared-only"
            or info.get("guest") != "192.168.56.128"
            or info.get("target") != {
                "processId": trial.PID, "processStartUtcTicks": trial.TICKS,
                "executableSha256": trial.GAME_SHA}
            or info.get("bundleSha256") != trial.BUNDLE_SHA
            or type(info.get("zipBytes")) is not int
            or not 1 <= info["zipBytes"] <= 16 * 1024 * 1024
            or not isinstance(info.get("zipSha256"), str)
            or len(info["zipSha256"]) != 64
            or any(c not in "0123456789ABCDEF" for c in info["zipSha256"])):
        raise Blocked("guest-declared-zip-provenance-invalid")
    return info["zipSha256"]


def server_args(phase: str) -> tuple[Path, list[str]]:
    filename, expected = SERVER_FILES[phase]
    file = ROOT / "scripts" / filename
    if trial.sha(file.read_bytes()) != expected:
        raise Blocked("pinned-server-source-changed")
    if phase == "download":
        return file, ["--bundle", "typed-inline", "--seconds", "600", "--serve"]
    if phase == "claim":
        if CLAIM_RECEIPT.exists():
            raise Blocked("zip-claim-receipt-already-exists")
        return file, [
            "--output", str(CLAIM_RECEIPT),
            "--process-id", str(trial.PID),
            "--process-start-ticks", str(trial.TICKS),
            "--game-sha256", trial.GAME_SHA, "--bundle-sha256", trial.BUNDLE_SHA,
            "--seconds", "600", "--serve",
        ]
    expected_zip = upload_digest()
    return file, [
        "--config", str(CONFIG), "--output", str(UPLOAD_ARCHIVE),
        "--receipt", str(UPLOAD_RECEIPT),
        "--expected-sha256", expected_zip,
        "--seconds", "600", "--serve",
    ]


def require_independent_windows_user() -> tuple[int, bool]:
    if os.name != "nt" or Path(sys.executable).name.casefold() != "pythonw.exe":
        raise Blocked("independent-signed-in-windows-pythonw-required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    session, in_job = wintypes.DWORD(), wintypes.BOOL()
    if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        raise Blocked("windows-session-unavailable")
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None,
                                ctypes.byref(in_job)):
        raise Blocked("windows-job-check-unavailable")
    if session.value != 2 or in_job.value:
        raise Blocked("service-must-be-outside-command-job")
    return session.value, bool(in_job.value)


def run_phase(phase: str) -> None:
    if phase not in SERVER_FILES:
        raise Blocked("invalid-guest-service-phase")
    stem = "rr2-inline-" + phase
    stdout = HOME / (stem + ".stdout.log")
    stderr = HOME / (stem + ".stderr.log")
    process_file = HOME / (stem + "-process.json")
    exit_file = HOME / (stem + "-exited.json")
    if any(path.exists() for path in (stdout, stderr, process_file, exit_file)):
        raise Blocked("one-use-guest-service-already-started")
    session, in_job = require_independent_windows_user()
    trial.check_request()
    plan = trial.maintenance()
    phase_steps(phase)
    from scripts.control_host import HostConfig, VmEpochGuard
    cfg = HostConfig.load(CONFIG)
    if VmEpochGuard(cfg).collect() != plan["vmIdentity"]:
        raise Blocked("vm-identity-drift-before-service")
    file, args = server_args(phase)
    with stdout.open("x", encoding="utf-8", buffering=1) as out, (
            stderr.open("x", encoding="utf-8", buffering=1)) as err, (
            contextlib.redirect_stdout(out)), contextlib.redirect_stderr(err):
        with process_file.open("x", encoding="utf-8") as receipt:
            json.dump({
                "schemaVersion": 1,
                "purpose": "one-use-typed-inline-" + phase,
                "pid": os.getpid(),
                "processIdentity": process_identity(os.getpid()),
                "windowsSessionId": session, "inJob": in_job,
                "startedUtc": datetime.now(timezone.utc).isoformat(),
                "sourceSha256": trial.sha(file.read_bytes()),
                "requestSha256": trial.REQUEST_SHA,
                "vmIdentity": plan["vmIdentity"],
                "allowedGuest": "192.168.56.128",
                "bind": "192.168.56.1", "port": 8765,
                "phase": phase,
            }, receipt, indent=2)
            receipt.write("\n")
        sys.argv = [str(file)] + args
        try:
            runpy.run_path(str(file), run_name="__main__")
        finally:
            with exit_file.open("x", encoding="utf-8") as receipt:
                json.dump({"pid": os.getpid(), "phase": phase,
                           "atUtc": datetime.now(timezone.utc).isoformat()},
                          receipt, indent=2)
                receipt.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(SERVER_FILES), required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        if args.preview:
            trial.check_request()
            file, command = server_args(args.phase)
            result = {
                "state": "verified-not-serving", "phase": args.phase,
                "sourceSha256": trial.sha(file.read_bytes()),
                "sourceArgs": command, "guestNetworkAccess": False,
                "requiresV14NormalExit": True,
            }
            print(json.dumps(result))
            return 0
        run_phase(args.phase)
        return 0
    except (Blocked, OSError, ValueError, KeyError, AssertionError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
