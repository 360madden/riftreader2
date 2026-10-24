"""Prepare a guarded native-host handover for a restarted or unchanged VM epoch.

The default requires a restarted VM and quarantined queue. --same-epoch only
prepares a successor while the current host is live and its queue is idle,
unheld, and backed by a prior cleanup receipt. Neither mode stops a host,
mutates queue authority, sends VM/guest input, or launches a successor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HOME = ROOT / "artifacts" / "update-recovery-20261023-01"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_launcher(source: str, previous: str, successor: str) -> str:
    if not re.fullmatch(r"v[1-9][0-9]*", previous):
        raise ValueError("invalid previous launch version")
    if not re.fullmatch(r"v[1-9][0-9]*", successor) or successor == previous:
        raise ValueError("invalid successor launch version")
    old = "-"+previous
    new = "-"+successor
    targets = (
        f"coordinated-host{old}.stdout.private.log",
        f"coordinated-host{old}.stderr.log",
        f"coordinated-host-plan{old}.json",
        f"coordinated-host{old}-process.json",
        f"coordinated-host{old}-exited.json",
    )
    for value in targets:
        if source.count(value) != 1:
            raise ValueError("unexpected launcher template")
    result = source
    for value in targets:
        result = result.replace(value, value.replace(old, new))
    if f"coordinated-host{old}" in result:
        raise ValueError("unreplaced versioned launcher field")
    return result


def authority_snapshot(path: Path, resource: str) -> tuple[int, str | None, str | None]:
    """Read only one consistent SQLite authority snapshot; never sweep expiries."""
    import sqlite3
    from contextlib import closing
    from scripts.nav_access_queue import APPLICATION_ID, SCHEMA_VERSION

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("invalid canonical queue path")
    with closing(sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, timeout=4
    )) as conn:
        conn.execute("PRAGMA query_only=ON")
        if (conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
            raise ValueError("canonical queue schema changed")
        conn.execute("BEGIN")
        resources = conn.execute(
            "SELECT blocked,holder,cleanup_receipt FROM resources WHERE name=?",
            (resource,),
        ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE state IN ('queued','active','cleanup')"
        ).fetchone()[0]
        conn.execute("COMMIT")
    if len(resources) != 1:
        raise ValueError("canonical authority resource missing or duplicated")
    if pending != 0:
        raise ValueError("outstanding queue work requires owner review")
    return resources[0]


def require_quarantined_authority(path: Path, resource: str) -> None:
    """Require shutdown quarantine without changing the canonical database."""
    blocked, holder, _ = authority_snapshot(path, resource)
    if blocked != 1 or holder is not None:
        raise ValueError("authority is not exclusively quarantined")


def require_idle_authority(path: Path, resource: str) -> None:
    """Require a live host's free resource and previous verified cleanup receipt."""
    blocked, holder, receipt = authority_snapshot(path, resource)
    if blocked != 0 or holder is not None:
        raise ValueError("authority must be free and unheld for same-epoch preparation")
    if not isinstance(receipt, str) or not receipt:
        raise ValueError("same-epoch preparation requires a cleanup receipt")


def require_epoch_relation(prior: dict, current: dict, *, same_epoch: bool) -> None:
    """Keep resource identity fixed; enforce the selected VM epoch relationship."""
    if current["vmx"] != prior["vmx"] or current["port"] != prior["port"]:
        raise ValueError("VM resource identity changed")
    if same_epoch:
        if current != prior:
            raise ValueError("VM epoch changed; same-epoch handover refused")
    elif current == prior:
        raise ValueError("VM epoch has not changed; no stale-epoch handover")


def successor_plan(prior: dict, current: dict, shutdown: Path) -> dict:
    """Copy Python integer VM identities without JavaScript's 53-bit rounding."""
    from datetime import datetime, timezone
    result = dict(prior)
    result["vmIdentity"] = dict(current)
    result["shutdownFile"] = str(shutdown)
    result["createdUtc"] = datetime.now(timezone.utc).isoformat()
    return result


def prepare(previous: str, successor: str, *, same_epoch: bool = False) -> dict:
    from scripts.control_host import HostConfig
    from scripts.vm_console_native import (
        collect_identity, process_identity, validate_config,
    )

    plan_path = HOME / f"coordinated-host-plan-{previous}.json"
    source = HOME / f"run-coordinated-host-{previous}.py"
    if not plan_path.is_file() or not source.is_file():
        raise ValueError("previous launch artifact unavailable")
    prior = json.loads(plan_path.read_text(encoding="utf-8"))
    required = {
        "schemaVersion", "configPath", "configSha256", "database", "resource",
        "shutdownFile", "vmIdentity", "runtimeHashes", "expectedWindowsSession"
    }
    if set(prior) not in (required, required | {"createdUtc"}):
        raise ValueError("unexpected previous launch plan schema")
    if prior["schemaVersion"] != 1 or prior["expectedWindowsSession"] != 2:
        raise ValueError("unexpected previous launch parameters")
    config = Path(prior["configPath"])
    queue_path = Path(prior["database"])
    if not config.is_absolute() or not queue_path.is_absolute():
        raise ValueError("plan paths must be absolute")
    if digest(config) != prior["configSha256"]:
        raise ValueError("host configuration changed")
    for relative, expected in prior["runtimeHashes"].items():
        path = (ROOT / relative).resolve()
        if ROOT not in path.parents or not path.is_file() or digest(path) != expected:
            raise ValueError(f"runtime mismatch: {relative}")
    stop_previous = Path(prior["shutdownFile"])
    if stop_previous.exists():
        raise ValueError("previous host already has a shutdown marker")
    receipt = HOME / f"coordinated-host-{previous}-process.json"
    if not receipt.is_file():
        raise ValueError("previous host receipt missing")
    owner = json.loads(receipt.read_text(encoding="utf-8"))
    observed_owner = process_identity(int(owner["pid"]))
    if observed_owner != owner["processIdentity"]:
        raise ValueError("previous host process epoch drift")
    if owner["vmIdentity"] != prior["vmIdentity"]:
        raise ValueError("previous host launch receipt does not match plan")
    if owner["canonicalDatabase"].casefold() != str(queue_path).casefold():
        raise ValueError("canonical queue differs")
    if owner["resource"] != prior["resource"]:
        raise ValueError("resource differs")
    if same_epoch:
        require_idle_authority(queue_path, prior["resource"])
    else:
        require_quarantined_authority(queue_path, prior["resource"])
    host_config = HostConfig.load(config)
    # Do not request a second console mutex while the old host still owns it.
    # This collector reads vmrun inventory/process/log/listener identity only;
    # the successor launcher independently acquires the real mutex at startup.
    native_config = validate_config(
        host_config.vmx, host_config.vnc_port, host_config.vmrun,
        HOME, require_files=True,
    )
    current = collect_identity(native_config)
    require_epoch_relation(prior["vmIdentity"], current, same_epoch=same_epoch)
    output = HOME / f"coordinated-host-plan-{successor}.json"
    launch = HOME / f"run-coordinated-host-{successor}.py"
    shutdown = HOME / f"STOP-NATIVE-20261024-{successor.upper()}.request"
    used = [
        output, launch, shutdown,
        HOME / f"coordinated-host-{successor}.stdout.private.log",
        HOME / f"coordinated-host-{successor}.stderr.log",
        HOME / f"coordinated-host-{successor}-process.json",
        HOME / f"coordinated-host-{successor}-exited.json",
    ]
    if any(path.exists() for path in used):
        raise ValueError("target version has artifacts already; no overwrites")
    rendered = render_launcher(source.read_text(encoding="utf-8"), previous, successor)
    new = successor_plan(prior, current, shutdown)
    # Both creates are exclusive; preserve a partial write for investigation.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(new, stream, indent=2)
        stream.write("\n")
    with launch.open("x", encoding="utf-8") as stream:
        stream.write(rendered)
    return {
        "state": "handover-prepared-not-executed",
        "mode": "same-vm-epoch" if same_epoch else "restarted-vm-epoch",
        "previousOwnerPid": owner["pid"],
        "previousShutdownMarker": str(stop_previous),
        "newLauncher": str(launch),
        "newPlan": str(output),
        "newVmPid": current["pid"],
        "newVmLogEpoch": current["logEpoch"],
        "queueStatePreserved": True,
        "queueBlockedAtPreparation": not same_epoch,
        "shutdownMarkerNotCreated": True,
        "guestInputSent": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", default="v7")
    parser.add_argument("--successor", default="v8")
    parser.add_argument(
        "--same-epoch", action="store_true",
        help="prepare only: require the same VM epoch and free, cleaned queue",
    )
    args = parser.parse_args()
    try:
        report = prepare(args.previous, args.successor, same_epoch=args.same_epoch)
    except (ValueError, KeyError, OSError, TypeError, AssertionError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
