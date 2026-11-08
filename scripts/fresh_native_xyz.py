"""Pinned no-input XYZ candidates through the existing authenticated control agent."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid

from scripts.control_client import ControlClient, ClientError
from scripts.control_host import HostConfig, ControlHostError, validate_identity_payload
from scripts.vm_console_native import Blocked, verify_identity
from scripts import sample_current_native_vitals as pins

EVIDENCE = Path(__file__).resolve().parents[1] / "artifacts/native-current-xyz-agent/runs"
QUALIFICATION = "candidate-only-not-passive-fresh-or-player-semantic-qualified"
REPORT_MAX_BYTES = 65536
MAX_RESPONSE_SECONDS = 3.0

def validate_response_time(report, observed_at_utc, before, after):
    """Validate host bounds and compare guest times at .NET tick precision."""
    def ticks(value):
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?(?:Z|\+00:00)", value)
        if match is None:
            raise ValueError("invalid UTC timestamp")
        parsed = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
        fraction = int((match.group(2) or "").ljust(7, "0"))
        return host_ticks(parsed) + fraction, parsed + timedelta(microseconds=fraction // 10)

    def host_ticks(value):
        epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
        delta = value - epoch
        return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10

    try:
        if (before.utcoffset() != timedelta(0) or after.utcoffset() != timedelta(0)
                or after < before):
            raise Blocked("native-xyz-host-window-invalid")
        lower = host_ticks(before) - 50_000_000
        upper = host_ticks(after) + 50_000_000
        observed_ticks, observed = ticks(observed_at_utc)
        row = report
        start_ticks, _ = ticks(row["startedAtUtc"])
        end_ticks, _ = ticks(row["completedAtUtc"])
        if not lower <= observed_ticks <= upper:
            raise Blocked("native-xyz-response-stale")
        if not lower <= start_ticks <= end_ticks <= upper:
            raise Blocked("native-xyz-acquisition-stale")
        if observed_ticks < end_ticks:
            raise Blocked("native-xyz-response-before-sample")
        return observed
    except Blocked:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise Blocked("native-xyz-unavailable") from None


def validate_report(report, *, pid, ticks):
    fields = {"schemaVersion", "contractVersion", "qualification", "identity",
              "startedAtUtc", "completedAtUtc", "unitKey", "unitIdCandidate",
              "ownerIdentityStatus", "x", "y", "z"}
    if (not isinstance(report, dict) or set(report) != fields
            or type(report["schemaVersion"]) is not int or report["schemaVersion"] != 1
            or report["contractVersion"] != "native-current-position-candidate-sample/1"
            or report["qualification"] != QUALIFICATION
            or report["ownerIdentityStatus"] != "player-component-chain-anchored"):
        raise Blocked("native-xyz-report-contract-invalid")
    identity = report["identity"]
    identity_fields = {"processId", "processStartUtcTicks", "executablePath",
                       "executableSha256", "moduleBaseAddress", "moduleSize"}
    if (not isinstance(identity, dict) or set(identity) != identity_fields
            or type(identity["processId"]) is not int or identity["processId"] != pid
            or type(identity["processStartUtcTicks"]) is not int or identity["processStartUtcTicks"] != ticks
            or not isinstance(identity["executablePath"], str) or not identity["executablePath"]
            or not isinstance(identity["executableSha256"], str)
            or identity["executableSha256"].upper() != pins.GAME_SHA
            or type(identity["moduleBaseAddress"]) is not int
            or not 0x10000 <= identity["moduleBaseAddress"] < 0x800000000000
            or type(identity["moduleSize"]) is not int
            or not 0x2F588A4 <= identity["moduleSize"] <= 0x7FFFFFFF):
        raise Blocked("native-xyz-game-identity-mismatch")
    key = report["unitKey"]
    if (not isinstance(key, str) or re.fullmatch(r"[1-9][0-9]{0,19}", key) is None
            or int(key) > 2**64 - 1 or report["unitIdCandidate"] != f"u{int(key):016X}"):
        raise Blocked("native-xyz-unit-identity-invalid")
    if any(type(report[axis]) not in (int, float) or not math.isfinite(report[axis])
           for axis in ("x", "y", "z")):
        raise Blocked("native-xyz-coordinate-invalid")
    return {"unitKey": key, "unitIdCandidate": report["unitIdCandidate"],
            "ownerIdentityStatus": report["ownerIdentityStatus"],
            "x": report["x"], "y": report["y"], "z": report["z"],
            "zoneStatus": "unavailable-in-source-report", "freshness": "unqualified"}


def query(config, expected_vm, expected_game, host_config_path, *,
          lab="lab2", expected_zone=None, client_factory=ControlClient):
    """One bounded fresh acquisition, no control lease, fallback, or zone inference."""
    started = time.perf_counter()
    try:
        if lab not in ("lab1", "lab2"):
            raise Blocked("native-xyz-lab-invalid")
        if expected_zone is not None:
            raise Blocked("native-xyz-zone-unavailable")
        vm = pins.checked_expected_vm(expected_vm)
        expected = pins.checked_expected_game(lab, expected_game)
        if vm is None or expected is None:
            raise Blocked("native-xyz-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port):
            raise Blocked("native-xyz-host-vm-mismatch")
        if host.expected_machine_name != "RIFT-LAB-" + lab[-1]:
            raise Blocked("native-xyz-host-lab-mismatch")
        payload = {**expected, "machineName": host.expected_machine_name}
        payload["executableSha256"] = payload["executableSha256"].lower()
        validate_identity_payload(payload)
        verify_identity(config, vm)
        try:
            client = client_factory(host)
            status = client.request("/api/status", method="GET")
            current, guest = status.get("host", {}), status.get("guest", {})
            if (current.get("connected") is not True or current.get("vmIdentity") != vm
                    or current.get("machineName") != payload["machineName"]):
                raise Blocked("native-xyz-host-target-mismatch")
            if type(guest.get("nativeXyzVersion")) is not int or guest["nativeXyzVersion"] != 1:
                raise Blocked("native-xyz-unsupported")
            if (type(guest.get("nativeReadLeaseVersion")) is not int
                    or guest["nativeReadLeaseVersion"] != 1):
                raise Blocked("native-xyz-lease-unsupported")
            instance = guest.get("instanceId")
            if (not isinstance(instance, str) or re.fullmatch(r"[0-9a-f]{32}", instance) is None
                    or current.get("instanceId") != instance):
                raise Blocked("native-xyz-instance-invalid")
            before = datetime.now(timezone.utc)
            request_start = time.perf_counter()
            response = client.request("/api/native-xyz", method="POST", payload=payload)
            response_seconds = time.perf_counter() - request_start
            after = datetime.now(timezone.utc)
            if response_seconds >= MAX_RESPONSE_SECONDS:
                raise Blocked("native-xyz-response-too-slow")
            if (not isinstance(response, dict)
                    or set(response) != {"nativeXyzVersion", "instanceId", "hashMode", "observedAtUtc", "report"}
                    or type(response["nativeXyzVersion"]) is not int or response["nativeXyzVersion"] != 1
                    or response["hashMode"] != "fresh-bytes"):
                raise Blocked("native-xyz-response-invalid")
            if response["instanceId"] != instance:
                raise Blocked("native-xyz-instance-changed")
            report = response["report"]
            metrics = validate_report(report, pid=expected["processId"], ticks=expected["processStartUtcTicks"])
            validate_response_time(report, response["observedAtUtc"], before, after)
            raw = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > REPORT_MAX_BYTES:
                raise Blocked("native-xyz-report-too-large")
        finally:
            verify_identity(config, vm)
        output = EVIDENCE / lab / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        source = output / "samples.json"
        with source.open("xb") as stream:
            stream.write(raw)
        summary = {
            "schemaVersion": 1, "status": "candidate-only", "lab": lab, "vmIdentity": vm,
            "gameProcessId": expected["processId"], "gameProcessStartUtcTicks": expected["processStartUtcTicks"],
            "gameSha256": expected["executableSha256"], "transport": "persistent-control-agent",
            "activeAgentInstanceId": instance, "observedAtUtc": response["observedAtUtc"],
            "sourceReport": str(source), "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
            "metrics": metrics, "responseSeconds": response_seconds,
            "wallSecondsBeforeSummaryWrite": time.perf_counter() - started,
            "limitation": QUALIFICATION,
        }
        with (output / "summary.json").open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, indent=2, allow_nan=False)
        return summary
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise Blocked("native-xyz-unavailable") from None
