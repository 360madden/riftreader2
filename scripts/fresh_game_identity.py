"""Fresh executable-byte identity through the authenticated RR2 control agent.

This read-only operation never starts helpers, acquires a lease or arms input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient, ClientError
from scripts.control_host import HostConfig, ControlHostError, validate_identity_payload
from scripts.vm_console_native import Blocked, validate_config, collect_identity, verify_identity


def query(config, expected_vm, expected_game, host_config_path, *, client_factory=ControlClient):
    """Rehash the exact expected game, bracketed by fresh VM identity checks."""
    try:
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port):
            raise Blocked("identity-host-vm-mismatch")
        expected = {key: expected_game[key] for key in (
            "processId", "processStartUtcTicks", "executableSha256")}
        if isinstance(expected["executableSha256"], str):
            expected["executableSha256"] = expected["executableSha256"].lower()
        expected["machineName"] = host.expected_machine_name
        if (expected_game.get("lab") != "lab2"
                or host.expected_machine_name != "RIFT-LAB-2"):
            raise Blocked("identity-host-lab-mismatch")
        validate_identity_payload(expected)
        verify_identity(config, expected_vm)
        client = client_factory(host)
        try:
            status = client.request("/api/status", method="GET")
            if (status.get("host", {}).get("connected") is not True
                    or status["host"].get("machineName") != expected["machineName"]):
                raise Blocked("identity-host-target-mismatch")
            if status["host"].get("vmIdentity") != expected_vm:
                raise Blocked("identity-host-vm-mismatch")
            version = status.get("guest", {}).get("freshIdentityVersion")
            if type(version) is not int or version != 1:
                raise Blocked("fresh-identity-unsupported")
            before = datetime.now(timezone.utc)
            response = client.request("/api/identity", method="POST", payload=expected)
            after = datetime.now(timezone.utc)
            if (set(response) != {"identityVersion", "hashMode", "observedAtUtc", "target"}
                    or type(response["identityVersion"]) is not int
                    or response["identityVersion"] != 1
                    or response["hashMode"] != "fresh-bytes"):
                raise Blocked("invalid-fresh-identity")
            observed = datetime.fromisoformat(response["observedAtUtc"].replace("Z", "+00:00"))
            if (observed.utcoffset() != timedelta(0)
                    or observed < before - timedelta(seconds=5)
                    or observed > after + timedelta(seconds=5)):
                raise Blocked("stale-fresh-identity")
            target = response["target"]
            if not isinstance(target, dict):
                raise Blocked("invalid-fresh-identity")
            actual = {key: target[key] for key in expected}
            if isinstance(actual["executableSha256"], str):
                actual["executableSha256"] = actual["executableSha256"].lower()
            validate_identity_payload(actual)
            if actual != expected:
                raise Blocked("game-identity-drift")
            return {key: actual[key] for key in (
                "processId", "processStartUtcTicks", "executableSha256")}
        finally:
            verify_identity(config, expected_vm)
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Blocked("fresh-identity-unavailable") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-config", required=True, type=Path)
    parser.add_argument("--expected-machine", required=True, choices=("RIFT-LAB-2",))
    parser.add_argument("--expected-game-pid", required=True, type=int)
    parser.add_argument("--expected-game-start-ticks", required=True, type=int)
    parser.add_argument("--expected-game-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        host = HostConfig.load(args.host_config)
        if host.expected_machine_name != args.expected_machine:
            raise Blocked("identity-host-target-mismatch")
        if host.vmx is None or host.vmrun is None or host.vnc_port is None:
            raise Blocked("identity-host-vm-mismatch")
        config = validate_config(host.vmx, host.vnc_port, host.vmrun,
                                 host.output_directory, require_files=True)
        vm = collect_identity(config)
        start = time.perf_counter()
        result = query(config, vm, {
            "lab": "lab2", "processId": args.expected_game_pid,
            "processStartUtcTicks": args.expected_game_start_ticks,
            "executableSha256": args.expected_game_sha256.lower()}, args.host_config)
        print(json.dumps({"transport": "control-agent-fresh-bytes", "identity": result,
                          "elapsedSeconds": time.perf_counter() - start}))
        return 0
    except (Blocked, ControlHostError, OSError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
