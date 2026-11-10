"""Pinned lab candidate vitals through the existing authenticated control agent."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from scripts.control_client import ControlClient, ClientError
from scripts.control_host import HostConfig, ControlHostError, validate_identity_payload
from scripts.vm_console_native import Blocked, verify_identity
from scripts import sample_current_native_vitals as vitals


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
            raise Blocked("native-vitals-host-window-invalid")
        lower = host_ticks(before) - 50_000_000
        upper = host_ticks(after) + 50_000_000
        observed_ticks, observed = ticks(observed_at_utc)
        row = report["observation"]
        start_ticks, _ = ticks(row["startedAtUtc"])
        end_ticks, _ = ticks(row["completedAtUtc"])
        if not lower <= observed_ticks <= upper:
            raise Blocked("native-vitals-response-stale")
        if not lower <= start_ticks <= end_ticks <= upper:
            raise Blocked("native-vitals-acquisition-stale")
        if observed_ticks < end_ticks:
            raise Blocked("native-vitals-response-before-sample")
        return observed
    except Blocked:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise Blocked("native-vitals-unavailable") from None


def query(config, expected_vm, expected_game, host_config_path, *, lab="lab2",
          client_factory=ControlClient):
    """Collect one bounded candidate report; never acquire input authority or fall back."""
    started = time.perf_counter()
    try:
        if lab not in ("lab1", "lab2"):
            raise Blocked("native-vitals-lab-not-supported")
        vm = vitals.checked_expected_vm(expected_vm)
        expected = vitals.checked_expected_game(lab, expected_game)
        if vm is None or expected is None:
            raise Blocked("native-vitals-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port):
            raise Blocked("native-vitals-host-vm-mismatch")
        if host.expected_machine_name != "RIFT-LAB-" + lab[-1]:
            raise Blocked("native-vitals-host-lab-mismatch")
        payload = {**expected, "machineName": host.expected_machine_name}
        payload["executableSha256"] = payload["executableSha256"].lower()
        validate_identity_payload(payload)
        verify_identity(config, vm)
        try:
            client = client_factory(host)
            status = client.request("/api/status", method="GET")
            current = status.get("host", {})
            if (current.get("connected") is not True or current.get("vmIdentity") != vm
                    or current.get("machineName") != payload["machineName"]):
                raise Blocked("native-vitals-host-target-mismatch")
            guest = status.get("guest", {})
            if type(guest.get("nativeVitalsVersion")) is not int or guest["nativeVitalsVersion"] != 1:
                raise Blocked("native-vitals-unsupported")
            instance = guest.get("instanceId")
            if not isinstance(instance, str) or re.fullmatch(r"[0-9a-f]{32}", instance) is None:
                raise Blocked("native-vitals-instance-invalid")
            before = datetime.now(timezone.utc)
            response = client.request("/api/native-vitals", method="POST", payload=payload)
            after = datetime.now(timezone.utc)
            if (set(response) != {"nativeVitalsVersion", "instanceId", "hashMode", "observedAtUtc", "report"}
                    or type(response["nativeVitalsVersion"]) is not int
                    or response["nativeVitalsVersion"] != 1 or response["hashMode"] != "fresh-bytes"):
                raise Blocked("native-vitals-response-invalid")
            if response["instanceId"] != instance:
                raise Blocked("native-vitals-instance-changed")
            report = response["report"]
            if (not isinstance(report, dict)
                    or report.get("contractVersion") != "native-current-vitals-candidate-sample/2"):
                raise Blocked("native-vitals-report-contract-invalid")
            raw = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > vitals.REPORT_MAX_BYTES:
                raise Blocked("native-vitals-report-too-large")
            metrics = vitals.validate_report(report, pid=expected["processId"], ticks=expected["processStartUtcTicks"])
            validate_response_time(report, response["observedAtUtc"], before, after)
        finally:
            verify_identity(config, vm)
        # Publish only after the final VM check. Each response owns a new report.
        output = vitals.EVIDENCE / lab / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        source = output / "samples.json"
        with source.open("xb") as stream:
            stream.write(raw)
        summary = {
            "schemaVersion": 1, "status": "candidate-only", "lab": lab, "vmIdentity": vm,
            "gameProcessId": expected["processId"], "gameProcessStartUtcTicks": expected["processStartUtcTicks"],
            "gameSha256": expected["executableSha256"], "transport": "persistent-control-agent",
            "activeAgentInstanceId": response["instanceId"], "observedAtUtc": response["observedAtUtc"],
            "sourceReport": str(source), "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
            "metrics": metrics, "wallSecondsBeforeSummaryWrite": time.perf_counter() - started,
            "limitation": vitals.QUALIFICATION,
        }
        with (output / "summary.json").open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, indent=2, allow_nan=False)
        return summary
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Blocked("native-vitals-unavailable") from None
