#!/usr/bin/env python3
"""Evidence-only host acceptance for receiver or guest-Windows restart.

No guest input, lease/grant, VM configuration write, queue maintenance or recovery.
A passing comparison proves new authenticated sessions and fresh supervision,
NOT that a user did not manually launch the receiver or that Windows rebooted.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.control_host import HostConfig
from scripts.control_client import ControlClient
from scripts.nav_access_queue import APPLICATION_ID, SCHEMA_VERSION
from scripts import vm_console_native as vm

SCHEMA = 1
IDENTIFIER = re.compile(r"vm:[a-z0-9][a-z0-9._/-]{0,120}\Z")
REQUIRED_TARGET = ("machineName", "executablePath", "executableSha256",
                   "processId", "processStartUtcTicks", "windowHandle",
                   "clientWidth", "clientHeight", "clientX", "clientY")


class RecoveryCheckError(ValueError):
    """Stable, payload-free refusal reason."""


def require(condition, code):
    if not condition:
        raise RecoveryCheckError(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def queue_snapshot(path: Path, resource: str) -> dict:
    """Read SQLite in mode=ro. Never call AccessQueue.status(): it writes/sweeps."""
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            "authority-path-invalid")
    require(isinstance(resource, str) and IDENTIFIER.fullmatch(resource),
            "resource-name-invalid")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                                     uri=True, timeout=4)) as conn:
            conn.execute("PRAGMA query_only=ON")
            require(conn.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
                    and conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION,
                    "authority-schema-invalid")
            conn.execute("BEGIN")
            rows = conn.execute(
                "SELECT name, epoch, generation, blocked, holder, cleanup_receipt "
                "FROM resources WHERE name=?", (resource,)).fetchall()
            require(len(rows) == 1, "authority-resource-missing")
            name, epoch, generation, blocked, holder, receipt = rows[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE state IN ('queued','active','cleanup')"
            ).fetchone()[0]
            history = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            events = conn.execute("SELECT COALESCE(MAX(sequence),0) FROM events").fetchone()[0]
            conn.execute("COMMIT")
    except (OSError, sqlite3.Error) as error:
        raise RecoveryCheckError("authority-read-unavailable") from None
    require(blocked == 0 and holder is None and isinstance(receipt, str) and receipt,
            "resource-not-cleaned")
    require(pending == 0, "pending-ownership-requests")
    require(isinstance(epoch, str) and epoch.startswith("nav-")
            and type(generation) is int and generation >= 0,
            "authority-epoch-invalid")
    return {"resource": name, "epoch": epoch, "generation": generation,
            "cleanupReceiptHash": digest(receipt.encode("utf-8")),
            "requestHistoryCount": history, "lastEventSequence": events,
            "blocked": False, "holder": None, "pending": pending}


def normalized_observation(status: dict, vm_identity: dict, authority: dict,
                           *, config_sha: str, authority_path: str) -> dict:
    """Fail closed on old/unknown/inconsistent identity; never return tokens."""
    try:
        h, g = status["host"], status["guest"]
        co, supervisor, console = h["coordination"], h["coordination"]["supervisor"], h["consoleReservation"]
        target = g["target"]
    except (TypeError, KeyError) as error:
        raise RecoveryCheckError("native-status-incomplete") from None

    require(h.get("connected") is True and h.get("vmIdentity") == vm_identity,
            "native-vm-not-matched")
    require(co.get("state") == "ready" and co.get("shutdownRequested") is False
            and co.get("safeToClose") is False,
            "supervisor-not-ready")
    require(isinstance(supervisor, dict)
            and supervisor.get("state") == "running"
            and supervisor.get("threadAlive") is True
            and supervisor.get("initialCleanupVerified") is True,
            "supervisor-not-verified")
    require(console.get("held") is True and console.get("required") is True
            and console.get("closing") is False and console.get("faulted") is False,
            "console-not-excluded")
    require(g.get("armed") is False and g.get("busy") is False
            and g.get("recoveryRequired") is False and g.get("desktopInputsDown") == [],
            "guest-input-not-released")
    require(isinstance(target, dict)
            and all(k in target for k in REQUIRED_TARGET),
            "guest-target-incomplete")
    require(type(target["processId"]) is int and target["processId"] > 0
            and type(target["processStartUtcTicks"]) is int and target["processStartUtcTicks"] > 0,
            "guest-process-invalid")
    require(isinstance(g.get("instanceId"), str) and bool(g["instanceId"])
            and h.get("instanceId") == g["instanceId"],
            "receiver-instance-mismatch")
    require(isinstance(co.get("hostInstance"), str) and bool(co["hostInstance"])
            and type(co.get("connection")) is int and co["connection"] > 0,
            "host-instance-invalid")
    require(co.get("resource") == authority["resource"]
            and supervisor.get("resource") == authority["resource"]
            and supervisor.get("epoch") == authority["epoch"],
            "supervisor-queue-epoch-mismatch")
    require(isinstance(h.get("machineName"), str)
            and h["machineName"] == target["machineName"],
            "guest-machine-mismatch")
    require(isinstance(target.get("executableSha256"), str)
            and re.fullmatch(r"[a-fA-F0-9]{64}", target["executableSha256"]),
            "game-build-hash-invalid")

    return {
        "schemaVersion": SCHEMA,
        "kind": "rr2-guest-recovery-observation",
        "observedUtc": datetime.now(timezone.utc).isoformat(),
        "configSha256": config_sha,
        "authorityPath": authority_path,
        "vmIdentity": vm_identity,
        "host": {"hostInstance": co["hostInstance"], "connection": co["connection"]},
        "guest": {"instanceId": g["instanceId"], "target": {
            key: target[key] for key in REQUIRED_TARGET},
                  "foreground": target.get("isForeground")},
        "queue": authority,
        "nativeReady": True,
        "noGameplayInputSent": True,
        "guestWindowsBootVerified": False,
        "unattendedShortcutLaunchVerified": False,
    }


def compare_observations(before: dict, after: dict, mode: str) -> dict:
    """Compare pure snapshots; a positive result is not Windows reboot proof."""
    require(mode in ("receiver", "guest-restart"), "invalid-verification-mode")
    require(before.get("schemaVersion") == SCHEMA and after.get("schemaVersion") == SCHEMA
            and before.get("kind") == after.get("kind") == "rr2-guest-recovery-observation",
            "observation-schema-invalid")
    for field in ("configSha256", "authorityPath", "vmIdentity"):
        require(before.get(field) == after.get(field), field + "-changed")
    require(before["host"]["hostInstance"] == after["host"]["hostInstance"],
            "native-host-restarted")
    require(after["host"]["connection"] > before["host"]["connection"],
            "native-connection-not-advanced")
    require(after["guest"]["instanceId"] != before["guest"]["instanceId"],
            "receiver-not-restarted")
    a, b = before["guest"]["target"], after["guest"]["target"]
    common = ("machineName", "executablePath", "executableSha256")
    require(all(a[k] == b[k] for k in common), "game-build-or-machine-changed")
    if mode == "receiver":
        require(a == b, "game-restarted-in-receiver-only-test")
    else:
        require(b["processStartUtcTicks"] != a["processStartUtcTicks"],
                "guest-game-process-not-restarted")
    qa, qb = before["queue"], after["queue"]
    require(qb["resource"] == qa["resource"]
            and qb["epoch"] != qa["epoch"]
            and qb["generation"] > qa["generation"]
            and qb["cleanupReceiptHash"] != qa["cleanupReceiptHash"]
            and qb["lastEventSequence"] > qa["lastEventSequence"]
            and qb["requestHistoryCount"] >= qa["requestHistoryCount"]
            and qb["pending"] == 0 and qb["blocked"] is False
            and qb["holder"] is None,
            "authority-did-not-reconcile")
    return {"passed": True, "mode": mode,
            "newReceiverAuthenticated": True, "hostIdentityPreserved": True,
            "verifiedSupervisorAndCleanup": True, "oldSessionEpochRevoked": True,
            "guestGameProcessChanged": mode == "guest-restart",
            "windowsBootIndependentlyVerified": False,
            "shortcutAutoLaunchIndependentlyVerified": False,
            "conclusion": "Connection recovery validated; installer/autostart requires separate guest evidence."}


def observe(config: Path, database: Path, resource: str) -> dict:
    """Exact VM is detected before the only network call (GET /api/status)."""
    config, database = Path(config), Path(database)
    require(config.is_absolute() and config.is_file() and not config.is_symlink(),
            "host-config-path-invalid")
    cfg = HostConfig.load(config)
    require(cfg.vmx is not None and cfg.vmrun is not None and cfg.vnc_port is not None,
            "native-vm-guard-missing")
    binding = vm.validate_config(cfg.vmx, cfg.vnc_port, cfg.vmrun,
                                 config.parent / ".rr2-read-only-identity",
                                 require_files=True)
    before = vm.collect_identity(binding)
    # GET status only. No lease, STOP, ARM, screenshot, recovery or control command.
    value = ControlClient(cfg).request("/api/status", method="GET")
    authority = queue_snapshot(database, resource)
    after = vm.collect_identity(binding)
    require(after == before, "vm-identity-drift")
    return normalized_observation(value, before, authority,
                                  config_sha=digest(config.read_bytes()),
                                  authority_path=str(database.resolve()))


def save_once(path: Path, value: dict):
    path = Path(path)
    require(path.is_absolute() and path.parent.is_dir(), "output-directory-invalid")
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")
        file.flush()
        import os
        os.fsync(file.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--resource", required=True)
    sub = parser.add_subparsers(dest="phase", required=True)
    start = sub.add_parser("baseline")
    start.add_argument("--output", type=Path, required=True)
    finish = sub.add_parser("verify")
    finish.add_argument("--baseline", type=Path, required=True)
    finish.add_argument("--mode", choices=("receiver", "guest-restart"), required=True)
    finish.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        live = observe(args.host_config, args.database, args.resource)
        if args.phase == "baseline":
            result = {"passed": True, "phase": "baseline",
                      "guestInstance": live["guest"]["instanceId"],
                      "gamePid": live["guest"]["target"]["processId"],
                      "nativeReady": live["nativeReady"],
                      "observedForeground": live["guest"]["foreground"]}
            save_once(args.output, live)
        else:
            prior_path = args.baseline
            require(prior_path.is_absolute() and prior_path.is_file(),
                    "baseline-file-invalid")
            require(prior_path.stat().st_size <= 16384, "baseline-too-large")
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
            result = compare_observations(prior, live, args.mode)
            result["phase"] = "verify"
            save_once(args.output, {"comparison": result, "observation": live})
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (RecoveryCheckError, OSError, ValueError, KeyError, TypeError,
            sqlite3.Error, json.JSONDecodeError) as error:
        code = str(error) if isinstance(error, RecoveryCheckError) else "verification-failed"
        print(json.dumps({"passed": False, "phase": args.phase, "reason": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
