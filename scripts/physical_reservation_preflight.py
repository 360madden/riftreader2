"""Read-only physical RIFT PID/start/build admission and Windows reservation probe.

Does not start the control agent, send input, focus windows, or use VMware.
A verified receipt proves only the sampled local process identity and brief
exclusive reservation ownership; it grants no movement/control authority.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import physical_rift
from scripts.nav_physical_reservation import (
    PhysicalClientIdentity, PhysicalClientReservation, PhysicalReservationError,
)


class PhysicalPreflightError(ValueError):
    """Stable fail-closed read-only preflight outcome."""


def selected_identity(selection: object, host: str, pid: int) -> PhysicalClientIdentity:
    if not isinstance(selection, dict) or selection.get("status") != "ready":
        reason = selection.get("reason", "selection-unavailable") if isinstance(selection, dict) else "selection-invalid"
        raise PhysicalPreflightError("physical-selection-blocked:" + str(reason)[:128])
    target = selection.get("target")
    owner_host = selection.get("ownerHost")
    if (selection.get("workflow") != "physical"
            or not isinstance(owner_host, str)
            or owner_host.casefold() != host.casefold()
            or not isinstance(target, dict)):
        raise PhysicalPreflightError("physical-selection-metadata-mismatch")
    try:
        ticks = target["processStartUtcTicks"]
        if (type(ticks) is not str or not ticks.isdecimal() or ticks.startswith("0")
                or str(int(ticks)) != ticks):
            raise ValueError()
        identity = PhysicalClientIdentity(
            target["hostName"], target["processId"], int(ticks),
            target["executableSha256"])
        path = target["executablePath"]
        if (not isinstance(path, str) or not path
                or not re.search(r"[/\\]rift_x64[.]exe\Z", path, re.IGNORECASE)):
            raise ValueError()
        if (identity.machine_name.casefold() != host.casefold()
                or identity.process_id != pid):
            raise ValueError()
        identity.require_local_host()
        return identity
    except (PhysicalReservationError, KeyError, ValueError, TypeError):
        raise PhysicalPreflightError("physical-selection-identity-mismatch") from None


def preflight(host: str, pid: int, *, selector=None, reservation_type=PhysicalClientReservation) -> dict:
    """Acquire, recheck and release one local mutex; never grant input authority."""
    if (not isinstance(host, str) or host.upper() not in physical_rift.SUPPORTED_HOSTS
            or host.casefold() != socket.gethostname().casefold()):
        raise PhysicalPreflightError("physical-preflight-host-mismatch")
    if type(pid) is not int or not 1 <= pid <= 2147483647:
        raise PhysicalPreflightError("physical-preflight-pid-invalid")
    selector = selector or physical_rift.select_physical
    def observe():
        return selected_identity(selector(expected_host=host, physical_pid=pid), host, pid)
    identity = observe()
    lease = reservation_type(identity, observe)
    with lease:
        # Acquire performs first revalidation; repeat under the same owned mutex
        # for the final observed identity. Release happens before reporting success.
        verified = lease.check()
    if lease.held:
        raise PhysicalPreflightError("physical-preflight-reservation-not-released")
    return {
        "status": "verified-read-only",
        "workflow": "physical",
        "recordType": "physical-reservation-preflight/1",
        "identity": {
            "machineName": verified.machine_name,
            "processId": verified.process_id,
            "processStartUtcTicks": str(verified.process_start_utc_ticks),
            "executableSha256": verified.executable_sha256,
        },
        "reservation": "acquired-and-released",
        "movementEligible": False,
        "controlAgentStarted": False,
        "gameInputSent": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--pid", type=int, required=True, help="one exact local rift_x64 process ID")
    args = parser.parse_args(argv)
    try:
        result = preflight(args.host, args.pid)
    except (PhysicalPreflightError, PhysicalReservationError, OSError, RuntimeError) as error:
        result = {"status": "blocked", "workflow": "physical",
                  "reason": str(error)[:160], "gameInputSent": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "verified-read-only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
