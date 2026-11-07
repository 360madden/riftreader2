"""Pinned Lab2 candidate vitals through the existing authenticated control agent."""
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


def query(config, expected_vm, expected_game, host_config_path, *, client_factory=ControlClient):
    """Collect one bounded candidate report; never acquire input authority or fall back."""
    started = time.perf_counter()
    try:
        vm = vitals.checked_expected_vm(expected_vm)
        expected = vitals.checked_expected_game("lab2", expected_game)
        if vm is None or expected is None:
            raise Blocked("native-vitals-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port):
            raise Blocked("native-vitals-host-vm-mismatch")
        if host.expected_machine_name != "RIFT-LAB-2":
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
            observed = datetime.fromisoformat(response["observedAtUtc"].replace("Z", "+00:00"))
            if (observed.utcoffset() != timedelta(0) or observed < before - timedelta(seconds=5)
                    or observed > after + timedelta(seconds=5)):
                raise Blocked("native-vitals-response-stale")
            report = response["report"]
            if (not isinstance(report, dict)
                    or report.get("contractVersion") != "native-current-vitals-candidate-sample/2"):
                raise Blocked("native-vitals-report-contract-invalid")
            raw = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > vitals.REPORT_MAX_BYTES:
                raise Blocked("native-vitals-report-too-large")
            metrics = vitals.validate_report(report, pid=expected["processId"], ticks=expected["processStartUtcTicks"])
            row = report["observation"]
            sample_start = datetime.fromisoformat(row["startedAtUtc"].replace("Z", "+00:00"))
            sample_end = datetime.fromisoformat(row["completedAtUtc"].replace("Z", "+00:00"))
            if (sample_start.utcoffset() != timedelta(0) or sample_end.utcoffset() != timedelta(0)
                    or not before - timedelta(seconds=5) <= sample_start <= sample_end <= after + timedelta(seconds=5)):
                raise Blocked("native-vitals-acquisition-stale")
        finally:
            verify_identity(config, vm)
        # Publish only after the final VM check. Each response owns a new report.
        output = vitals.EVIDENCE / "lab2" / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=False)
        source = output / "samples.json"
        with source.open("xb") as stream:
            stream.write(raw)
        summary = {
            "schemaVersion": 1, "status": "candidate-only", "lab": "lab2", "vmIdentity": vm,
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
