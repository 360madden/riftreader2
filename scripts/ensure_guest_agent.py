"""Recover the exact, on-demand guest control agent for one or both RIFT labs.

The main-PC controller is a separate dependency. Guest recovery uses a cached,
identity-pinned VMware Tools login to request an owned, triggerless Scheduled
Task in the already logged-in game user's session. No gameplay input occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS, _launch_lock, ensure as ensure_controller
from scripts.lab_codex import LabCodex
from scripts.operation_dependencies import DependencyUnavailable
from scripts.vmware_guest_session import POWERSHELL, SessionError


SCRIPT = ROOT / "scripts/Ensure-GuestAgentTask.ps1"
GUEST_ROOT = r"C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029"


def _save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _idle(status: dict) -> bool:
    host = status.get("host", {})
    guest = status.get("guest", {})
    coordinator = host.get("coordination", {})
    console = host.get("consoleReservation", {})
    return (host.get("connected") is True and coordinator.get("state") == "ready"
            and console.get("held") is True and console.get("faulted") is False
            and isinstance(guest, dict) and guest.get("armed") is False
            and guest.get("busy") is False and guest.get("recoveryRequired") is False
            and guest.get("desktopInputsDown") == [])


def _check_waiting(status: dict) -> bool:
    """Validate a disconnected or safely starting connection; return connected."""
    host = status.get("host") if isinstance(status, dict) else None
    if not isinstance(host, dict):
        raise DependencyUnavailable("guest-agent", "controller-not-waiting-safely")
    coordination = host.get("coordination")
    console = host.get("consoleReservation")
    if not isinstance(coordination, dict) or not isinstance(console, dict):
        raise DependencyUnavailable("guest-agent", "controller-not-waiting-safely")
    supervisor = coordination.get("supervisor")
    if (console.get("held") is not True or console.get("faulted") is not False
            or console.get("closing", False) is not False
            or console.get("acquiring", False) is not False
            or coordination.get("errorCode") is not None
            or supervisor is not None and not isinstance(supervisor, dict)
            or isinstance(supervisor, dict) and (supervisor.get("state") == "blocked"
                                                  or supervisor.get("errorCode") is not None)):
        raise DependencyUnavailable("guest-agent", "controller-not-waiting-safely")
    connected = host.get("connected")
    if "guest" in status and not isinstance(status["guest"], dict):
        raise DependencyUnavailable("guest-agent", "connected-but-not-idle"
                                    if connected is True else "controller-not-waiting-safely")
    if _idle(status):
        return True
    if connected is False and coordination.get("state") == "waiting":
        return False
    guest = status.get("guest")
    if (connected is True and coordination.get("state") in ("waiting", "starting")
            and isinstance(guest, dict) and guest.get("armed") is False
            and guest.get("busy") is False and guest.get("recoveryRequired") is False
            and guest.get("desktopInputsDown") == []):
        return True
    raise DependencyUnavailable("guest-agent", "connected-but-not-idle"
                                if connected is True else "controller-not-waiting-safely")


def _wait_for_idle(client, timeout_seconds, initial=None):
    deadline = time.monotonic() + timeout_seconds
    status = initial
    while time.monotonic() < deadline:
        if status is None:
            try:
                status = client.request("/api/status", method="GET")
            except Exception:
                time.sleep(0.5)
                continue
        _check_waiting(status)
        if _idle(status):
            return status
        status = None
        time.sleep(0.5)
    raise DependencyUnavailable("guest-agent", "agent-connection-timeout")


def _summary(lab: str, status: dict, state: str) -> dict:
    host = status["host"]
    return {
        "lab": lab, "state": state,
        "hostConnected": host["connected"],
        "coordination": host["coordination"]["state"],
        "consoleHeld": host["consoleReservation"]["held"],
        "guestDisarmedIdle": _idle(status),
        "riftGameProcessId": (status.get("guest") or {}).get("target", {}).get("processId"),
        "utc": datetime.now(timezone.utc).isoformat(),
    }


def _stage_and_request(lab: str, config: HostConfig, output: Path) -> dict:
    lab_codex = LabCodex()
    _, _, global_config, settings = lab_codex._configuration(lab)
    if str(config.vmx).casefold() != str(settings["vmx"]).casefold():
        raise DependencyUnavailable("guest-agent", "vmx-configuration-mismatch")
    native = lab_codex._native(global_config, settings, lab_codex.run_root / ".doctor")
    identity = lab_codex.collect_identity(native)
    nonce = uuid.uuid4().hex
    guest_source = settings["guestRoot"] + "\\rr2-recovery-" + nonce + ".ps1"
    guest_receipt = settings["guestRoot"] + "\\rr2-recovery-" + nonce + ".json"
    source_hash = hashlib.sha256(SCRIPT.read_bytes()).hexdigest().upper()
    local_receipt = output / "task-result.json"
    with lab_codex._session(global_config, settings, identity, lab_codex.run_root / ".doctor") as guest:
        guest.run("copyFileFromHostToGuest", str(SCRIPT), guest_source, timeout=60)
        guest.powershell(
            "if((Get-FileHash -LiteralPath '" + guest_source + "').Hash -ne '"
            + source_hash + "'){throw 'staged-script-hash-mismatch'}", timeout=35,
        )
        failure = None
        try:
            guest.run(
                "runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "RemoteSigned", "-File", guest_source,
                "-Root", GUEST_ROOT, "-ResultPath", guest_receipt,
                "-ExpectedPort", str(config.agent_port),
                "-ExpectedMachine", "RIFT-LAB-" + lab[-1], timeout=90,
            )
        except SessionError:
            failure = "guest-task-command-rejected"
        try:
            guest.copy_from_guest(guest_receipt, local_receipt, timeout=45)
        finally:
            # Remove only the two nonce-named diagnostics just staged by this call.
            try:
                guest.powershell(
                    "Remove-Item -LiteralPath '" + guest_source + "','" + guest_receipt
                    + "' -Force", timeout=30,
                )
            except SessionError:
                pass
    value = json.loads(local_receipt.read_text(encoding="utf-8-sig"))
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or value.get("state") not in ("accepted", "blocked")
            or value.get("noAutomaticTrigger") is not True):
        raise DependencyUnavailable("guest-agent", "invalid-task-receipt")
    if failure is not None or value["state"] != "accepted":
        code = value.get("errorCode")
        if not isinstance(code, str) or not code.isascii() or not code.replace("-", "").isalnum():
            code = failure or "task-request-refused"
        raise DependencyUnavailable("guest-agent", code)
    return value


def ensure(lab: str, *, timeout_seconds: int = 45) -> dict:
    """Reuse an idle connection or recover only its missing guest agent."""
    if lab not in CONFIGS:
        raise DependencyUnavailable("guest-agent", "unknown-lab")
    if not 1 <= timeout_seconds <= 90:
        raise DependencyUnavailable("guest-agent", "invalid-timeout")
    ensure_controller(lab)
    # Serialize agent recovery independently of the controller's own start lock.
    # Re-probe under the lock: a prior caller may already have reconnected it.
    with _launch_lock("guest-" + lab, timeout_seconds=90):
        config = HostConfig.load(CONFIGS[lab])
        client = ControlClient(config)
        status = client.request("/api/status", method="GET")
        connected = _check_waiting(status)
        if _idle(status):
            return _summary(lab, status, "reused")
        if connected:
            # Another agent is already connecting: never dispatch a duplicate.
            return _summary(lab, _wait_for_idle(client, timeout_seconds, status), "reused")

        output = ROOT / "artifacts/guest-agent-recovery" / lab / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        receipt = _stage_and_request(lab, config, output)
        _save(output / "request-summary.json", {
            "taskName": receipt["taskName"],
            "onDemand": receipt["noAutomaticTrigger"],
            "created": receipt["created"], "started": receipt["started"],
        })
        status = _wait_for_idle(client, timeout_seconds)
        summary = _summary(lab, status, "started")
        _save(output / "summary.json", summary)
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2", "all"), required=True)
    args = parser.parse_args()
    labs = ("lab1", "lab2") if args.lab == "all" else (args.lab,)
    failure = False
    for lab in labs:
        try:
            print(json.dumps(ensure(lab)), flush=True)
        except Exception as error:
            failure = True
            code = error.code if isinstance(error, DependencyUnavailable) else "guest-recovery-unavailable"
            print(json.dumps({"lab": lab, "state": "blocked", "reason": code}), flush=True)
    return 2 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
