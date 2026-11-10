"""Fresh player-owned orientation candidates from the persistent C# guest controller.

One authenticated read-only request per sample. Values are scaffolding: matrix angles
are not yet independently proven to equal actor/body yaw.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid

from scripts import fresh_native_xyz as xyz
from scripts import sample_current_native_vitals as pins
from scripts.control_client import ControlClient, ClientError
from scripts.control_host import HostConfig, ControlHostError, validate_identity_payload
from scripts.vm_console_native import Blocked, verify_identity

EVIDENCE = Path(__file__).resolve().parents[1] / "artifacts/native-current-orientation-agent/runs"
QUALIFICATION = "matrix-descriptor-candidate-only; body-facing/axis/sign/passive-freshness/restart-unverified"


def validate_report(report, *, pid, ticks):
    expected = {"identity", "startedAtUtc", "completedAtUtc", "unitKey",
                "refreshHandleRaw", "refreshFlagRaw", "primary", "secondary", "qualification"}
    if not isinstance(report, dict) or set(report) != expected or report["qualification"] != QUALIFICATION:
        raise Blocked("native-orientation-contract-invalid")
    identity = report["identity"]
    required = {"processId", "processStartUtcTicks", "executablePath", "executableSha256",
                "moduleBaseAddress", "moduleSize"}
    if (not isinstance(identity, dict) or set(identity) != required
            or type(identity["processId"]) is not int or identity["processId"] != pid
            or type(identity["processStartUtcTicks"]) is not int or identity["processStartUtcTicks"] != ticks
            or not isinstance(identity["executablePath"], str) or not identity["executablePath"]
            or not isinstance(identity["executableSha256"], str)
            or identity["executableSha256"].upper() != pins.GAME_SHA
            or type(identity["moduleBaseAddress"]) is not int
            or not 0x10000 <= identity["moduleBaseAddress"] < 0x800000000000
            or type(identity["moduleSize"]) is not int
            or not 0x2F588A4 <= identity["moduleSize"] <= 0x7FFFFFFF):
        raise Blocked("native-orientation-game-identity-mismatch")
    unit = report["unitKey"]
    if (not isinstance(unit, str) or re.fullmatch(r"[1-9][0-9]{0,19}", unit) is None
            or int(unit) > 2**64 - 1
            or not isinstance(report["refreshHandleRaw"], str)
            or re.fullmatch(r"0x[0-9A-F]{16}", report["refreshHandleRaw"]) is None
            or type(report["refreshFlagRaw"]) is not int
            or not 0 <= report["refreshFlagRaw"] <= 255):
        raise Blocked("native-orientation-owner-invalid")
    angles = {}
    matrix_fields = {"sourceOffset", "rawBits", "rowMajorF32", "status", "orthonormalError",
                     "determinant", "yPlanarError", "planarAngleRadiansCandidate", "planarAngleDegreesCandidate"}
    for label, offset in (("primary", 0x60), ("secondary", 0x94)):
        matrix = report[label]
        if (not isinstance(matrix, dict) or set(matrix) != matrix_fields
                or type(matrix["sourceOffset"]) is not int or matrix["sourceOffset"] != offset
                or not isinstance(matrix["rawBits"], list) or len(matrix["rawBits"]) != 9
                or any(type(bit) is not int or not 0 <= bit <= 0xFFFFFFFF for bit in matrix["rawBits"])
                or matrix["status"] not in ("structural-y-planar-matrix-candidate",
                                            "unqualified-matrix-shape", "nonfinite-matrix")):
            raise Blocked("native-orientation-matrix-invalid")
        floats = matrix["rowMajorF32"]
        if floats is not None and (not isinstance(floats, list) or len(floats) != 9
                                   or any(type(value) not in (int, float) or not math.isfinite(value)
                                          for value in floats)):
            raise Blocked("native-orientation-matrix-values-invalid")
        for field in ("orthonormalError", "determinant", "yPlanarError",
                      "planarAngleRadiansCandidate", "planarAngleDegreesCandidate"):
            value = matrix[field]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise Blocked("native-orientation-matrix-values-invalid")
        angle = matrix["planarAngleDegreesCandidate"]
        if angle is not None and not -180 <= angle <= 180:
            raise Blocked("native-orientation-angle-invalid")
        if matrix["status"] != "structural-y-planar-matrix-candidate" and angle is not None:
            raise Blocked("native-orientation-angle-unqualified")
        angles[label] = angle
    return {"unitKey": unit, "candidateAnglesDegrees": angles,
            "qualification": QUALIFICATION, "observedMatrixSource": "current-build-owned-position"}


def query(config, expected_vm, expected_game, host_config_path, *,
          lab="lab2", client_factory=ControlClient):
    """One non-cached, identity-pinned observation; never sends a game input."""
    started = time.perf_counter()
    try:
        if lab not in ("lab1", "lab2"):
            raise Blocked("native-orientation-lab-invalid")
        vm = pins.checked_expected_vm(expected_vm)
        game = pins.checked_expected_game(lab, expected_game)
        if vm is None or game is None:
            raise Blocked("native-orientation-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port
                or host.expected_machine_name != "RIFT-LAB-" + lab[-1]):
            raise Blocked("native-orientation-host-config-mismatch")
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
                    or type(guest.get("nativeOrientationVersion")) is not int
                    or guest["nativeOrientationVersion"] != 1
                    or type(guest.get("nativeReadLeaseVersion")) is not int
                    or guest["nativeReadLeaseVersion"] != 1
                    or not isinstance(instance, str) or re.fullmatch(r"[0-9a-f]{32}", instance) is None
                    or current.get("instanceId") != instance):
                raise Blocked("native-orientation-endpoint-not-ready")
            before = datetime.now(timezone.utc)
            request_started = time.perf_counter()
            response = client.request("/api/native-orientation", method="POST", payload=payload)
            elapsed = time.perf_counter() - request_started
            after = datetime.now(timezone.utc)
            if elapsed >= xyz.MAX_RESPONSE_SECONDS:
                raise Blocked("native-orientation-response-too-slow")
            if (not isinstance(response, dict)
                    or set(response) != {"nativeOrientationVersion", "instanceId", "hashMode",
                                        "observedAtUtc", "report"}
                    or type(response["nativeOrientationVersion"]) is not int
                    or response["nativeOrientationVersion"] != 1
                    or response["hashMode"] != "fresh-bytes" or response["instanceId"] != instance):
                raise Blocked("native-orientation-response-invalid")
            metrics = validate_report(response["report"], pid=game["processId"],
                                      ticks=game["processStartUtcTicks"])
            try:
                xyz.validate_response_time(response["report"], response["observedAtUtc"], before, after)
            except Blocked as error:
                raise Blocked(str(error).replace("native-xyz", "native-orientation")) from None
            raw = (json.dumps(response["report"], sort_keys=True, separators=(",", ":"),
                              allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > xyz.REPORT_MAX_BYTES:
                raise Blocked("native-orientation-report-too-large")
        finally:
            verify_identity(config, vm)
        folder = EVIDENCE / lab / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=False)
        sample = folder / "samples.json"
        with sample.open("xb") as target:
            target.write(raw)
        result = {"schemaVersion": 1, "status": "candidate-only", "lab": lab,
                  "vmIdentity": vm, "gameProcessId": game["processId"],
                  "gameProcessStartUtcTicks": game["processStartUtcTicks"],
                  "gameSha256": game["executableSha256"],
                  "transport": "persistent-control-agent",
                  "activeAgentInstanceId": instance, "observedAtUtc": response["observedAtUtc"],
                  "sourceReport": str(sample),
                  "sourceReportSha256": hashlib.sha256(raw).hexdigest().upper(),
                  "metrics": metrics, "responseSeconds": elapsed,
                  "wallSecondsBeforeSummaryWrite": time.perf_counter() - started}
        with (folder / "summary.json").open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
        return result
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError,
            AttributeError, OverflowError):
        raise Blocked("native-orientation-unavailable") from None
