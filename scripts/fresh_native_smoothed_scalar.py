"""Pinned, read-only four-scalar candidate from the exact-build self-owned native component.

The selector/vtable bridge is corroborated by historical health-component samples.
These numbers are NOT a qualified heading, camera yaw or movement response.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import uuid

from scripts import fresh_native_xyz as xyz
from scripts import sample_current_native_vitals as pins
from scripts.control_client import ControlClient, ClientError
from scripts.control_host import HostConfig, ControlHostError, validate_identity_payload
from scripts.vm_console_native import Blocked, verify_identity

EVIDENCE = Path(__file__).resolve().parents[1] / "artifacts/native-current-smoothed-scalar-agent/runs"
QUALIFICATION = ("entity-owned-smoothed-scalar-candidate-only; heading/body/camera "
                 "semantics and turn response unverified")
FIELDS = {"identity", "startedAtUtc", "completedAtUtc", "playerKeyDecimal",
          "playerEntityDecimal", "componentAddressDecimal", "rawBits",
          "currentCandidate", "sourceCandidate", "targetCandidate", "factorCandidate",
          "headingQualified", "qualification"}
VALUES = ("currentCandidate", "sourceCandidate", "targetCandidate", "factorCandidate")


def _positive_decimal(value, *, pointer):
    if (not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None
            or not 0 < int(value) <= 0xFFFFFFFFFFFFFFFF
            or (pointer and (int(value) < 0x10000 or int(value) >= 0x800000000000
                             or int(value) % 8))):
        raise Blocked("native-smoothed-scalar-owner-invalid")
    return int(value)


def validate_report(report, *, pid, ticks):
    if (not isinstance(report, dict) or set(report) != FIELDS
            or report["qualification"] != QUALIFICATION
            or report["headingQualified"] is not False):
        raise Blocked("native-smoothed-scalar-contract-invalid")
    identity = report["identity"]
    if (not isinstance(identity, dict)
            or set(identity) != {"processId", "processStartUtcTicks", "executablePath",
                                "executableSha256", "moduleBaseAddress", "moduleSize"}
            or type(identity["processId"]) is not int or identity["processId"] != pid
            or type(identity["processStartUtcTicks"]) is not int
            or identity["processStartUtcTicks"] != ticks
            or not isinstance(identity["executablePath"], str) or not identity["executablePath"]
            or not isinstance(identity["executableSha256"], str)
            or identity["executableSha256"].upper() != pins.GAME_SHA
            or type(identity["moduleBaseAddress"]) is not int
            or not 0x10000 <= identity["moduleBaseAddress"] < 0x800000000000
            or type(identity["moduleSize"]) is not int
            or not 0x2F57854 <= identity["moduleSize"] <= 0x7FFFFFFF):
        raise Blocked("native-smoothed-scalar-game-identity-mismatch")
    key = _positive_decimal(report["playerKeyDecimal"], pointer=False)
    entity = _positive_decimal(report["playerEntityDecimal"], pointer=True)
    component = _positive_decimal(report["componentAddressDecimal"], pointer=True)
    if entity == component:
        raise Blocked("native-smoothed-scalar-owner-invalid")
    raw = report["rawBits"]
    if (not isinstance(raw, list) or len(raw) != 4
            or any(type(bit) is not int or not 0 <= bit <= 0xFFFFFFFF for bit in raw)):
        raise Blocked("native-smoothed-scalar-raw-invalid")
    values = []
    for field, bit in zip(VALUES, raw):
        value = report[field]
        if type(value) not in (float, int):
            raise Blocked("native-smoothed-scalar-value-invalid")
        try:
            if not math.isfinite(value):
                raise Blocked("native-smoothed-scalar-value-invalid")
            encoded = struct.unpack("<I", struct.pack("<f", value))[0]
        except (ValueError, OverflowError, struct.error):
            raise Blocked("native-smoothed-scalar-value-invalid") from None
        if encoded != bit:
            raise Blocked("native-smoothed-scalar-raw-mismatch")
        values.append(value)
    return {"unitKey": str(key), "playerKeyDecimal": str(key), "playerEntityDecimal": str(entity),
            "componentAddressDecimal": str(component),
            **dict(zip(VALUES, values)), "headingQualified": False,
            "qualification": QUALIFICATION}


def query(config, expected_vm, expected_game, host_config_path, *,
          lab="lab2", client_factory=ControlClient):
    """Read only: VM ownership, exact game epoch, guest lease, time and raw-bit pins."""
    started = time.perf_counter()
    try:
        if lab not in ("lab1", "lab2"):
            raise Blocked("native-smoothed-scalar-lab-invalid")
        vm = pins.checked_expected_vm(expected_vm)
        game = pins.checked_expected_game(lab, expected_game)
        if vm is None or game is None:
            raise Blocked("native-smoothed-scalar-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port
                or host.expected_machine_name != "RIFT-LAB-" + lab[-1]):
            raise Blocked("native-smoothed-scalar-host-config-mismatch")
        payload = {**game, "machineName": host.expected_machine_name}
        payload["executableSha256"] = payload["executableSha256"].lower()
        validate_identity_payload(payload)
        verify_identity(config, vm)
        try:
            client = client_factory(host)
            status = client.request("/api/status", method="GET")
            current, guest = status.get("host", {}), status.get("guest", {})
            instance = guest.get("instanceId")
            if (current.get("connected") is not True or current.get("vmIdentity") != vm
                    or current.get("machineName") != payload["machineName"]
                    or type(guest.get("nativeSmoothedScalarVersion")) is not int
                    or guest["nativeSmoothedScalarVersion"] != 1
                    or type(guest.get("nativeReadLeaseVersion")) is not int
                    or guest["nativeReadLeaseVersion"] != 1
                    or not isinstance(instance, str)
                    or re.fullmatch(r"[0-9a-f]{32}", instance) is None
                    or current.get("instanceId") != instance):
                raise Blocked("native-smoothed-scalar-endpoint-not-ready")
            before = datetime.now(timezone.utc)
            request_started = time.perf_counter()
            response = client.request("/api/native-smoothed-scalar", method="POST", payload=payload)
            elapsed = time.perf_counter() - request_started
            after = datetime.now(timezone.utc)
            if elapsed >= xyz.MAX_RESPONSE_SECONDS:
                raise Blocked("native-smoothed-scalar-response-too-slow")
            if (not isinstance(response, dict)
                    or set(response) != {"nativeSmoothedScalarVersion", "instanceId",
                                        "hashMode", "observedAtUtc", "report"}
                    or type(response["nativeSmoothedScalarVersion"]) is not int
                    or response["nativeSmoothedScalarVersion"] != 1
                    or response["hashMode"] != "fresh-bytes"
                    or response["instanceId"] != instance):
                raise Blocked("native-smoothed-scalar-response-invalid")
            metrics = validate_report(response["report"], pid=game["processId"],
                                      ticks=game["processStartUtcTicks"])
            try:
                xyz.validate_response_time(response["report"], response["observedAtUtc"], before, after)
            except Blocked as error:
                raise Blocked(str(error).replace("native-xyz", "native-smoothed-scalar")) from None
            raw = (json.dumps(response["report"], sort_keys=True, separators=(",", ":"),
                              allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > xyz.REPORT_MAX_BYTES:
                raise Blocked("native-smoothed-scalar-report-too-large")
        finally:
            verify_identity(config, vm)
        folder = EVIDENCE / lab / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=False)
        sample = folder / "samples.json"
        with sample.open("xb") as output:
            output.write(raw)
        summary = {"schemaVersion": 1, "status": "candidate-only", "lab": lab,
                   "vmIdentity": vm, "gameProcessId": game["processId"],
                   "gameProcessStartUtcTicks": game["processStartUtcTicks"],
                   "gameSha256": game["executableSha256"],
                   "transport": "persistent-control-agent",
                   "activeAgentInstanceId": instance,
                   "observedAtUtc": response["observedAtUtc"],
                   "sourceReport": str(sample),
                   "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
                   "metrics": metrics, "responseSeconds": elapsed,
                   "wallSecondsBeforeSummaryWrite": time.perf_counter() - started}
        with (folder / "summary.json").open("x", encoding="utf-8") as output:
            json.dump(summary, output, indent=2, allow_nan=False)
        return summary
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError,
            AttributeError, OverflowError, struct.error):
        raise Blocked("native-smoothed-scalar-unavailable") from None
