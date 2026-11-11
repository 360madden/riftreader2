#!/usr/bin/env python3
"""Make paired physical-RIFT host/agent configs for one exact local process epoch.

Writes two new private session files only. Does not launch or control anything.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import control_host, physical_rift
from scripts.physical_reservation_preflight import selected_identity


class PhysicalConfigError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PhysicalConfigError(reason)


def _interfaces():
    """Read currently preferred Windows IPv4 assignments, without changing network state."""
    script = ("Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | "
              "Where-Object {$_.AddressState -eq 'Preferred'} | "
              "Select-Object IPAddress,InterfaceAlias | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                             "-Command", script], text=True, capture_output=True,
                            timeout=15, check=False)
    require(result.returncode == 0, "local IPv4 interface discovery unavailable")
    try:
        values = json.loads(result.stdout)
    except ValueError as error:
        raise PhysicalConfigError("local IPv4 interface discovery invalid") from error
    if isinstance(values, dict):
        values = [values]
    require(isinstance(values, list), "local IPv4 interface discovery invalid")
    return values


def _check_ip(ip_text, interfaces):
    try:
        address = ipaddress.IPv4Address(ip_text)
    except (ipaddress.AddressValueError, TypeError) as error:
        raise PhysicalConfigError("physical local IP invalid") from error
    require(control_host._is_rfc1918(str(address)), "physical local IP must be RFC1918")
    require(isinstance(interfaces, list), "physical interfaces invalid")
    allowed = []
    for item in interfaces:
        if not isinstance(item, dict):
            continue
        alias, current = item.get("InterfaceAlias"), item.get("IPAddress")
        if not isinstance(alias, str) or not isinstance(current, str):
            continue
        # Historical VM adapters are not an eligible physical control transport.
        if re.search(r"vmware|vmnet|vEthernet|hyper-v|loopback|vpn|tap-", alias, re.I):
            continue
        allowed.append(current)
    require(str(address) in allowed,
            "physical IP is not assigned to an eligible local interface")
    return str(address)


def create_config(host, pid, local_ip, agent_port, ui_port, output_root,
                  *, selector=None, interface_provider=None):
    require(isinstance(host, str) and host.upper() in physical_rift.SUPPORTED_HOSTS
            and host.casefold() == socket.gethostname().casefold(),
            "physical config host mismatch")
    require(type(pid) is int and 1 <= pid <= 2147483647, "physical PID invalid")
    require(type(agent_port) is int and 1024 <= agent_port <= 65535,
            "agent port must be 1024..65535")
    require(type(ui_port) is int and 1024 <= ui_port <= 65535 and ui_port != agent_port,
            "operator port must differ and be 1024..65535")
    ip = _check_ip(local_ip, (interface_provider or _interfaces)())
    selector = selector or physical_rift.select_physical
    def observe():
        return selector(expected_host=host, physical_pid=pid)
    first = observe()
    identity = selected_identity(first, host, pid)
    target = first["target"]
    executable = target["executablePath"]
    require(isinstance(executable, str), "physical executable path invalid")
    root = Path(output_root)
    require(root.is_absolute() and root.is_dir() and not root.is_symlink(),
            "output root must be an existing absolute directory")
    # Fresh selection before creating any private configuration.
    require(selected_identity(observe(), host, pid) == identity,
            "physical process epoch changed during config creation")

    private_dir = Path(tempfile.mkdtemp(prefix="physical-control-", dir=root))
    # The one-pulse runner pins both programs to the same private session journal.
    host_output = private_dir / "evidence"
    host_output.mkdir()
    token = secrets.token_hex(24)
    operator = secrets.token_hex(24)
    host_config = {
        "schemaVersion": 1,
        "bindAddress": ip,
        "agentPort": agent_port,
        "uiPort": ui_port,
        "guestAddress": ip,
        "expectedMachineName": identity.machine_name,
        "token": token,
        "operatorToken": operator,
        "outputDirectory": str(host_output),
        "physicalProcessId": identity.process_id,
        "physicalProcessStartUtcTicks": identity.process_start_utc_ticks,
        "physicalExecutableSha256": identity.executable_sha256,
    }
    agent_config = {
        "schemaVersion": 1,
        "hostAddress": ip,
        "port": agent_port,
        "token": token,
        "expectedMachineName": identity.machine_name,
        "processName": "rift_x64",
        "executablePath": executable,
        "executableSha256": identity.executable_sha256,
        "outputDirectory": str(host_output),
        "boundProcessId": identity.process_id,
        "boundProcessStartUtcTicks": identity.process_start_utc_ticks,
    }
    host_file, agent_file = private_dir / "physical-host.json", private_dir / "physical-agent.json"
    for destination, data in ((host_file, host_config), (agent_file, agent_config)):
        with destination.open("x", encoding="utf-8") as file:
            json.dump(data, file, separators=(",", ":"), sort_keys=True)
            file.write("\n")
    validated = control_host.HostConfig.load(host_file)
    require(validated.physical_process_id == pid
            and validated.physical_process_start_utc_ticks == identity.process_start_utc_ticks
            and validated.physical_executable_sha256 == identity.executable_sha256
            and validated.bind_address == validated.guest_address == ip,
            "written host config did not validate")
    return {
        "status": "physical-config-pair-created",
        "machineName": identity.machine_name,
        "processId": identity.process_id,
        "processStartUtcTicks": str(identity.process_start_utc_ticks),
        "executableSha256": identity.executable_sha256,
        "bindAddress": ip,
        "agentPort": agent_port,
        "hostConfigPath": str(host_file),
        "agentConfigPath": str(agent_file),
        "gameInputSent": False,
        "serviceStarted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=physical_rift.SUPPORTED_HOSTS)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--local-ip", required=True)
    parser.add_argument("--agent-port", type=int, required=True)
    parser.add_argument("--ui-port", type=int, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args(argv)
    try:
        result = create_config(args.host, args.pid, args.local_ip, args.agent_port,
                               args.ui_port, args.output_root)
    except (PhysicalConfigError, OSError, RuntimeError, ValueError,
            subprocess.TimeoutExpired) as error:
        result = {"status": "blocked", "reason": str(error)[:160],
                  "gameInputSent": False, "serviceStarted": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "physical-config-pair-created" else 2


if __name__ == "__main__":
    raise SystemExit(main())
