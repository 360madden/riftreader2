#!/usr/bin/env python3
"""One reviewed, bounded W pulse on a pinned PHYSICAL RIFT client.

No UI/VM service. This is an operator-driven experiment, not autonomous navigation.
The live entry point requires a new capture-bound approval file after displaying
its BMP; missing approval never sends input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import control_host, physical_rift
from scripts.nav_physical_reservation import PhysicalClientReservation
from scripts.physical_reservation_preflight import selected_identity


class PhysicalPulseError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise PhysicalPulseError(reason)


def _same_target(target, pinned):
    return (isinstance(target, dict)
            and isinstance(target.get("machineName"), str)
            and target["machineName"].casefold() == pinned.machine_name.casefold()
            and type(target.get("processId")) is int
            and target["processId"] == pinned.process_id
            and target.get("processStartUtcTicks") == pinned.process_start_utc_ticks
            and isinstance(target.get("executableSha256"), str)
            and target["executableSha256"].casefold() == pinned.executable_sha256.casefold())


def _clean(status, pinned, *, disarmed=True):
    return (isinstance(status, dict)
            and _same_target(status.get("target"), pinned)
            and status.get("recoveryRequired") is False
            and status.get("busy") is False
            and status.get("nativeReadBusy") is False
            and status.get("desktopInputsDown") == []
            and (not disarmed or status.get("armed") is False))


def _agent_config_matches(path, host_config, pinned):
    raw = Path(path).read_bytes()
    require(len(raw) <= 65536, "agent-config-too-large")
    value = control_host.decode_json(raw)
    require(isinstance(value, dict), "agent-config-invalid")
    required = {"schemaVersion": 1, "hostAddress": host_config.bind_address,
                "port": host_config.agent_port, "token": host_config.token,
                "expectedMachineName": pinned.machine_name,
                "processName": "rift_x64", "boundProcessId": pinned.process_id,
                "boundProcessStartUtcTicks": pinned.process_start_utc_ticks,
                "outputDirectory": str(host_config.output_directory)}
    require(all(value.get(k) == v for k, v in required.items())
            and isinstance(value.get("executableSha256"), str)
            and value["executableSha256"].casefold() == pinned.executable_sha256.casefold()
            and isinstance(value.get("executablePath"), str)
            and value["executablePath"].lower().endswith("rift_x64.exe"),
            "agent-config-identity-or-endpoint-mismatch")


def _approval(path, capture, pinned, *, expires_seconds=30, now=time.monotonic,
              sleep=time.sleep):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), "approval-file-must-not-preexist")
    deadline = now() + expires_seconds
    while now() < deadline:
        if path.is_symlink():
            raise PhysicalPulseError("approval-file-is-symbolic")
        if path.is_file():
            require(path.stat().st_size <= 4096, "approval-file-oversized")
            approval = control_host.decode_json(path.read_bytes())
            require(isinstance(approval, dict) and set(approval) == {
                "captureId", "sha256", "machineName", "processId",
                "processStartUtcTicks", "reviewNote"}, "approval-fields-invalid")
            require(approval["captureId"] == capture.get("captureId")
                    and isinstance(approval["sha256"], str)
                    and approval["sha256"].casefold() == capture["sha256"].casefold()
                    and approval["machineName"] == pinned.machine_name
                    and approval["processId"] == pinned.process_id
                    and str(approval["processStartUtcTicks"]) == str(pinned.process_start_utc_ticks),
                    "approval-capture-or-target-mismatch")
            note = approval["reviewNote"]
            require(isinstance(note, str) and 12 <= len(note.strip()) <= 512,
                    "approval-review-note-invalid")
            return note.strip()
        sleep(0.1)
    raise PhysicalPulseError("review-expired-no-game-input")


def _owned_agent(exe, config_path):
    exe = Path(exe)
    require(exe.is_file(), "control-agent-executable-missing")
    return subprocess.Popen([str(exe), "control-agent", "--config", str(Path(config_path).resolve())],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, cwd=str(ROOT))


def _wait_session(gateway, *, clock=time.monotonic, sleep=time.sleep, timeout=8):
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            return gateway.session()
        except control_host.ControlHostError:
            sleep(0.1)
    raise PhysicalPulseError("agent-not-connected")


def run_once(config, agent_config, host, pid, hold_ms, approval_path, *,
             selector=physical_rift.select_physical, gateway_factory=control_host.AgentGateway,
             launch_agent=_owned_agent, wait_session=_wait_session, reviewer=None,
             announce=print):
    require(host.upper() == "AMD-DESKTOP" and socket.gethostname().casefold() == host.casefold(),
            "wrong-physical-host")
    require(type(pid) is int and 0 < pid <= 2147483647
            and type(hold_ms) is int and 20 <= hold_ms <= 100, "invalid-one-pulse-arguments")
    require(config.physical_process_id == pid and config.vmx is None and config.vmrun is None
            and config.vnc_port is None
            and config.expected_machine_name.casefold() == host.casefold()
            and config.bind_address == config.guest_address,
            "physical-host-config-not-pinned")
    def observe():
        selected = selected_identity(selector(expected_host=host, physical_pid=pid), host, pid)
        require(selected.process_start_utc_ticks == config.physical_process_start_utc_ticks
                and selected.executable_sha256 == config.physical_executable_sha256,
                "physical-process-epoch-or-build-changed")
        return selected

    require(not (config.output_directory / "physical-pulse-cleanup-uncertain.json").exists(),
            "physical-input-quarantine-existing")
    pinned = observe()
    _agent_config_matches(agent_config, config, pinned)
    identity_payload = {"machineName": pinned.machine_name, "processId": pinned.process_id,
                        "processStartUtcTicks": pinned.process_start_utc_ticks,
                        "executableSha256": pinned.executable_sha256.upper()}
    with PhysicalClientReservation(pinned, observe) as lease:
        gateway = gateway_factory(config, control_host.EvidenceJournal(config.output_directory),
                                  require_supervisor=False, exclusive_console=False)
        agent = None
        action_attempted = False
        cleanup_failures = []
        try:
            gateway.start()
            agent = launch_agent(physical_rift.NATIVE_EXE, agent_config)
            wait_session(gateway)
            lease.check()
            start = gateway.command("status", {})
            require(_clean(start, pinned), "initial-control-status-not-clean")
            checked = gateway.command("identity", identity_payload)
            require(_same_target(checked.get("target"), pinned), "fresh-identity-mismatch")
            capture = gateway.capture()
            require(_same_target(capture.get("target"), pinned)
                    and isinstance(capture.get("captureId"), str)
                    and re.fullmatch(r"[a-f0-9]{32}", capture["captureId"])
                    and capture.get("imageFormat") == "bmp"
                    and isinstance(capture.get("artifact"), dict)
                    and isinstance(capture["artifact"].get("path"), str)
                    and isinstance(capture["artifact"].get("sha256"), str)
                    and capture["artifact"]["sha256"].casefold() == capture.get("sha256", "").casefold(),
                    "capture-identity-or-image-invalid")
            announce(json.dumps({"status": "awaiting-review", "captureId": capture["captureId"],
                                 "sha256": capture["sha256"], "bmpPath": capture["artifact"]["path"],
                                 "processId": pid, "holdMilliseconds": hold_ms}, sort_keys=True),
                     flush=True)
            note = (reviewer(capture, pinned) if reviewer is not None
                    else _approval(approval_path, capture, pinned))
            lease.check()
            require(_same_target(gateway.command("identity", identity_payload).get("target"), pinned),
                    "identity-changed-before-arm")
            armed = gateway.command("arm", {"captureId": capture["captureId"], "reviewNote": note})
            require(armed.get("expiresInSeconds") == 15
                    and isinstance(armed.get("armToken"), str)
                    and _same_target(armed.get("target"), pinned), "arm-denied-or-target-changed")
            lease.check()
            action_attempted = True
            action = gateway.command("action", {"armToken": armed["armToken"], "action": {
                "keys": ["w"], "holdMilliseconds": hold_ms, "mouseButton": None,
                "deltaX": 0, "deltaY": 0, "wheelNotches": 0}})
            result = action.get("result")
            require(isinstance(result, dict) and result.get("deliverySucceeded") is True
                    and result.get("releaseSucceeded") is True
                    and action.get("recoveryRequired") is False, "action-delivery-or-release-unverified")
            return {"status": "pulse-inserted-unverified-game-response", "key": "w",
                    "holdMilliseconds": hold_ms, "processId": pid,
                    "releaseSucceeded": True, "gameResponseVerified": False}
        finally:
            # Even a timeout after a possibly delivered action must attempt STOP.
            if agent is not None:
                for op in ("release", "stop"):
                    try:
                        receipt = gateway.command(op, {})
                        if receipt.get("recoveryRequired") is not False:
                            cleanup_failures.append(op + "-pending-recovery")
                    except Exception as error:
                        cleanup_failures.append(op + "-" + type(error).__name__)
                try:
                    status = gateway.command("status", {})
                    if not _clean(status, pinned):
                        cleanup_failures.append("final-status-not-clean")
                except Exception as error:
                    cleanup_failures.append("final-status-" + type(error).__name__)
            try:
                gateway.close()
            except Exception:
                cleanup_failures.append("gateway-close-failed")
            if agent is not None:
                try:
                    agent.terminate()
                    agent.wait(timeout=3)
                except Exception:
                    cleanup_failures.append("owned-agent-exit-unverified")
            if cleanup_failures and action_attempted:
                # Durable refusal on the next attempt; never silently erase.
                quarantine = config.output_directory / "physical-pulse-cleanup-uncertain.json"
                with quarantine.open("x", encoding="utf-8") as marker:
                    json.dump({"reason": cleanup_failures, "processId": pid,
                               "startTicks": pinned.process_start_utc_ticks}, marker)
                raise PhysicalPulseError("physical-input-cleanup-uncertain:" +
                                         ",".join(cleanup_failures))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", choices=("AMD-DESKTOP",), required=True)
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--hold-ms", type=int, default=80)
    p.add_argument("--host-config", type=Path, required=True)
    p.add_argument("--agent-config", type=Path, required=True)
    p.add_argument("--approval-file", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        config = control_host.HostConfig.load(a.host_config)
        result = run_once(config, a.agent_config, a.host, a.pid, a.hold_ms,
                          a.approval_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PhysicalPulseError, control_host.ControlHostError, OSError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "gameResponseVerified": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
