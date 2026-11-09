"""Read Lab 2 native position and vitals once, without Lua binding or game input.

Reuses the managed controller and existing bounded, identity-checked native
queries. The two reads are sequential, NOT an atomic snapshot or qualified
movement feedback. Each source keeps its own timestamp and hashed raw report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS
from scripts.ensure_guest_agent import ensure, _idle
from scripts.managed_controller_receipt import resolve_current_managed_controller
from scripts.vm_console_native import Blocked, validate_config
from scripts.sample_current_native_vitals import checked_expected_game
from scripts.fresh_native_xyz import query as query_xyz
from scripts.fresh_native_vitals import query as query_vitals

OWNER_HOST = "AMD-DESKTOP"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def target_identity(status):
    require(isinstance(status, dict) and _idle(status), "native-read-controller-not-idle")
    host, guest = status["host"], status["guest"]
    require(host.get("machineName") == "RIFT-LAB-2", "native-read-guest-mismatch")
    instance = guest.get("instanceId")
    require(isinstance(instance, str) and re.fullmatch(r"[0-9a-f]{32}", instance)
            and host.get("instanceId") == instance, "native-read-agent-mismatch")
    target = guest.get("target")
    require(isinstance(target, dict) and target.get("machineName") == "RIFT-LAB-2",
            "native-read-target-unavailable")
    game = checked_expected_game("lab2", {key: target.get(key) for key in
        ("processId", "processStartUtcTicks", "executableSha256")})
    return game, instance


def unit_key(value):
    require(type(value) in (int, str), "native-read-unit-key-invalid")
    text = str(value)
    require(re.fullmatch(r"[1-9][0-9]{0,19}", text) and int(text) <= 2**64 - 1,
            "native-read-unit-key-invalid")
    return text


def validate_pair(position, vitals, game, instance, vm):
    """Do not merge independently acquired values across owners or epochs."""
    for row in (position, vitals):
        require(isinstance(row, dict) and row.get("schemaVersion") == 1
                and row.get("status") == "candidate-only" and row.get("lab") == "lab2"
                and row.get("transport") == "persistent-control-agent"
                and row.get("vmIdentity") == vm
                and row.get("activeAgentInstanceId") == instance
                and type(row.get("gameProcessId")) is int
                and row["gameProcessId"] == game["processId"]
                and type(row.get("gameProcessStartUtcTicks")) is int
                and row["gameProcessStartUtcTicks"] == game["processStartUtcTicks"]
                and row.get("gameSha256", "").upper() == game["executableSha256"].upper(),
                "native-read-source-identity-mismatch")
    key = unit_key(position["metrics"]["unitKey"])
    require(unit_key(vitals["metrics"]["unitKey"]) == key, "native-read-unit-changed")
    return key


def read_once(lab: str, expected_host: str) -> dict:
    # Reject a wrong machine/target before starting any dependency.
    require(lab == "lab2", "native-read-target-not-supported")
    require(isinstance(expected_host, str) and expected_host.casefold() == OWNER_HOST.casefold()
            and socket.gethostname().casefold() == OWNER_HOST.casefold(), "native-read-host-mismatch")
    started = time.perf_counter()
    ensure(lab)
    receipt_path, receipt, _ = resolve_current_managed_controller(lab)
    config = HostConfig.load(CONFIGS[lab])
    require(config.expected_machine_name == "RIFT-LAB-2", "native-read-config-lab-mismatch")
    client = ControlClient(config)
    before = client.request("/api/status", method="GET")
    game, instance = target_identity(before)
    vm = receipt["vmIdentity"]
    require(before["host"].get("vmIdentity") == vm, "native-read-vm-mismatch")
    native = validate_config(config.vmx, config.vnc_port, config.vmrun,
                             config.output_directory, require_files=True)
    position = query_xyz(native, vm, game, CONFIGS[lab], lab=lab)
    vitals = query_vitals(native, vm, game, CONFIGS[lab])
    key = validate_pair(position, vitals, game, instance, vm)
    after = client.request("/api/status", method="GET")
    require(target_identity(after) == (game, instance)
            and after["host"].get("vmIdentity") == vm, "native-read-postflight-changed")
    resolve_current_managed_controller(lab, expected_receipt_path=receipt_path)
    # Keep large unit keys lossless for JavaScript and other JSON consumers.
    vitals = dict(vitals, metrics=dict(vitals["metrics"], unitKey=key))
    return {"schemaVersion": 1, "status": "candidate-only", "targetId": lab,
            "ownerHost": OWNER_HOST, "mode": "native-read-only", "atomic": False,
            "luaReaderUsed": False, "screenshotUsed": False,
            "unitKey": key, "position": position, "vitals": vitals,
            "elapsedSeconds": round(time.perf_counter() - started, 6),
            "qualification": "acquisition-checked; field semantics, passive freshness and restart recovery unqualified"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", required=True, choices=("lab2",))
    parser.add_argument("--expected-host", required=True)
    args = parser.parse_args(argv)
    try:
        result = read_once(args.lab, args.expected_host)
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return 0
    except Exception as error:
        # Never print transport configuration, credentials or arbitrary tracebacks.
        reason = str(error) if isinstance(error, (Blocked, ValueError)) else "native-read-unavailable"
        if re.fullmatch(r"[a-z0-9-]{1,100}", reason or "") is None:
            reason = "native-read-unavailable"
        print(json.dumps({"status": "blocked", "targetId": args.lab, "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
