"""One authenticated, fresh, read-only current-build actor/model pose candidate.

No player-facing claim: actor/model/render transforms may be cached or camera-related.
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

EVIDENCE = Path(__file__).resolve().parents[1] / "artifacts/native-current-actor-pose-agent/runs"
QUALIFICATION = ("actor/model/render-matrix-candidate-only; body-facing, source freshness, "
                 "input response and restart unverified")
MATRIX_FIELDS = {"sourceOffset", "rawBits", "rowMajorF32", "status", "orthonormalError",
                 "determinant", "yPlanarError", "planarAngleRadiansCandidate",
                 "planarAngleDegreesCandidate"}


def _decimal_pointer(value):
    if (not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None
            or not 0x10000 <= int(value) < 0x800000000000
            or int(value) % 8):
        raise Blocked("native-actor-pose-owner-invalid")
    return int(value)


def _matrix(matrix, offset):
    if (not isinstance(matrix, dict) or set(matrix) != MATRIX_FIELDS
            or type(matrix["sourceOffset"]) is not int or matrix["sourceOffset"] != offset
            or not isinstance(matrix["rawBits"], list) or len(matrix["rawBits"]) != 9
            or any(type(bit) is not int or not 0 <= bit <= 0xFFFFFFFF
                   for bit in matrix["rawBits"])
            or matrix["status"] not in ("structural-y-planar-matrix-candidate",
                                         "unqualified-matrix-shape", "nonfinite-matrix")):
        raise Blocked("native-actor-pose-matrix-invalid")
    values = matrix["rowMajorF32"]
    if matrix["status"] == "nonfinite-matrix":
        if values is not None:
            raise Blocked("native-actor-pose-matrix-values-invalid")
        if any(matrix[field] is not None for field in (
                "orthonormalError", "determinant", "yPlanarError",
                "planarAngleRadiansCandidate", "planarAngleDegreesCandidate")):
            raise Blocked("native-actor-pose-matrix-values-invalid")
        return None
    if (not isinstance(values, list) or len(values) != 9
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in values)):
        raise Blocked("native-actor-pose-matrix-values-invalid")
    try:
        bits = [struct.unpack("<I", struct.pack("<f", value))[0] for value in values]
    except (OverflowError, struct.error, ValueError):
        raise Blocked("native-actor-pose-matrix-values-invalid") from None
    if bits != matrix["rawBits"]:
        raise Blocked("native-actor-pose-matrix-raw-mismatch")
    for field in ("orthonormalError", "determinant", "yPlanarError"):
        value = matrix[field]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise Blocked("native-actor-pose-matrix-diagnostics-invalid")
    for field in ("planarAngleRadiansCandidate", "planarAngleDegreesCandidate"):
        value = matrix[field]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise Blocked("native-actor-pose-matrix-values-invalid")
    orthonormal_error = max(
        abs(sum(values[3 * row + col] * values[3 * other + col]
                for col in range(3)) - (1 if row == other else 0))
        for row in range(3) for other in range(3))
    determinant = (values[0] * (values[4] * values[8] - values[5] * values[7])
                   - values[1] * (values[3] * values[8] - values[5] * values[6])
                   + values[2] * (values[3] * values[7] - values[4] * values[6]))
    planar_error = max(abs(values[index]) for index in (1, 3, 5, 7))
    planar_error = max(planar_error, abs(values[4] - 1),
                       abs(values[8] - values[0]), abs(values[2] + values[6]))
    for field, expected in (("orthonormalError", orthonormal_error),
                            ("determinant", determinant), ("yPlanarError", planar_error)):
        if not math.isclose(matrix[field], expected, rel_tol=1e-10, abs_tol=1e-8):
            raise Blocked("native-actor-pose-matrix-diagnostics-invalid")
    structural = max(orthonormal_error, abs(determinant - 1), planar_error) < 0.01
    angle = matrix["planarAngleDegreesCandidate"]
    radians = matrix["planarAngleRadiansCandidate"]
    if (matrix["status"] != "structural-y-planar-matrix-candidate"
            and (angle is not None or radians is not None)):
        raise Blocked("native-actor-pose-angle-unqualified")
    if (matrix["status"] == "structural-y-planar-matrix-candidate") != structural:
        raise Blocked("native-actor-pose-matrix-status-invalid")
    if angle is not None and not -180 <= angle <= 180:
        raise Blocked("native-actor-pose-angle-invalid")
    if matrix["status"] == "structural-y-planar-matrix-candidate":
        computed_radians = math.atan2(values[6], values[0])
        computed_degrees = math.degrees(computed_radians)
        if (angle is None or radians is None
                or abs(angle - computed_degrees) > 0.001
                or abs(radians - computed_radians) > 0.00002):
            raise Blocked("native-actor-pose-angle-invalid")
    return values


def _composition_error(actor, model, render):
    if actor is None or model is None or render is None:
        return None
    return max(abs(sum(actor[3 * row + k] * model[3 * k + col] for k in range(3))
                   - render[3 * row + col])
               for row in range(3) for col in range(3))


def validate_report(report, *, pid, ticks):
    expected = {"identity", "startedAtUtc", "completedAtUtc", "playerKeyDecimal",
                "playerEntityDecimal", "actorComponentDecimal", "positionComponentDecimal",
                "actorFlags", "actorMatrix", "modelMatrix", "renderMatrix",
                "renderStatus", "renderCompositionMaxAbsDelta", "normalRenderBranch",
                "actorHeadingQualified", "qualification"}
    if (not isinstance(report, dict) or set(report) != expected
            or report["qualification"] != QUALIFICATION
            or report["actorHeadingQualified"] is not False):
        raise Blocked("native-actor-pose-contract-invalid")
    identity = report["identity"]
    identity_fields = {"processId", "processStartUtcTicks", "executablePath",
                       "executableSha256", "moduleBaseAddress", "moduleSize"}
    if (not isinstance(identity, dict) or set(identity) != identity_fields
            or type(identity["processId"]) is not int or identity["processId"] != pid
            or type(identity["processStartUtcTicks"]) is not int
            or identity["processStartUtcTicks"] != ticks
            or not isinstance(identity["executablePath"], str) or not identity["executablePath"]
            or not isinstance(identity["executableSha256"], str)
            or identity["executableSha256"].upper() != pins.GAME_SHA
            or type(identity["moduleBaseAddress"]) is not int
            or not 0x10000 <= identity["moduleBaseAddress"] < 0x800000000000
            or type(identity["moduleSize"]) is not int
            or not 0x2F588A4 <= identity["moduleSize"] <= 0x7FFFFFFF):
        raise Blocked("native-actor-pose-game-identity-mismatch")
    unit = report["playerKeyDecimal"]
    if (not isinstance(unit, str) or re.fullmatch(r"[1-9][0-9]{0,19}", unit) is None
            or int(unit) > 2**64 - 1):
        raise Blocked("native-actor-pose-owner-invalid")
    entity = _decimal_pointer(report["playerEntityDecimal"])
    actor_address = _decimal_pointer(report["actorComponentDecimal"])
    position_address = _decimal_pointer(report["positionComponentDecimal"])
    if actor_address == position_address:
        raise Blocked("native-actor-pose-owner-invalid")
    flags = report["actorFlags"]
    if (type(flags) is not int or not 0 <= flags <= 0xFFFFFFFF
            or type(report["normalRenderBranch"]) is not bool
            or report["normalRenderBranch"] != ((flags & 1) == 0)):
        raise Blocked("native-actor-pose-branch-invalid")
    actor = _matrix(report["actorMatrix"], 0x398)
    model = _matrix(report["modelMatrix"], 0x3EC)
    render = None
    if report["normalRenderBranch"]:
        if report["renderMatrix"] is None:
            if report["renderStatus"] != "normal-render-pointer-absent":
                raise Blocked("native-actor-pose-branch-invalid")
        else:
            if report["renderStatus"] != "normal-render-matrix-candidate":
                raise Blocked("native-actor-pose-branch-invalid")
            render = _matrix(report["renderMatrix"], 0xA0)
    elif (report["renderMatrix"] is not None
          or report["renderStatus"] != "alternate-reference-branch-not-followed"):
        raise Blocked("native-actor-pose-branch-invalid")
    delta = report["renderCompositionMaxAbsDelta"]
    actual = _composition_error(actor, model, render)
    if actual is None:
        if delta is not None:
            raise Blocked("native-actor-pose-composition-invalid")
    elif (type(delta) not in (int, float) or not math.isfinite(delta)
          or delta < 0 or abs(actual - delta) > 0.0001):
        raise Blocked("native-actor-pose-composition-invalid")
    return {"playerKeyDecimal": unit, "playerEntityDecimal": str(entity),
            "actorComponentDecimal": str(actor_address),
            "positionComponentDecimal": str(position_address),
            "actorAngleDegreesCandidate": report["actorMatrix"]["planarAngleDegreesCandidate"],
            "modelAngleDegreesCandidate": report["modelMatrix"]["planarAngleDegreesCandidate"],
            "renderAngleDegreesCandidate": report["renderMatrix"]["planarAngleDegreesCandidate"]
            if report["renderMatrix"] is not None else None,
            "renderStatus": report["renderStatus"],
            "renderCompositionMaxAbsDelta": delta,
            "actorHeadingQualified": False, "qualification": QUALIFICATION}


def query(config, expected_vm, expected_game, host_config_path, *,
          lab="lab2", client_factory=ControlClient):
    """One pinned, non-cached read, with raw source report retained by SHA."""
    started = time.perf_counter()
    try:
        if lab not in ("lab1", "lab2"):
            raise Blocked("native-actor-pose-lab-invalid")
        vm = pins.checked_expected_vm(expected_vm)
        game = pins.checked_expected_game(lab, expected_game)
        if vm is None or game is None:
            raise Blocked("native-actor-pose-pins-required")
        host = HostConfig.load(Path(host_config_path))
        if (host.vmx is None or host.vmrun is None
                or host.vmx.resolve() != config.vmx.resolve()
                or host.vmrun.resolve() != config.vmrun.resolve()
                or host.vnc_port != config.port
                or host.expected_machine_name != "RIFT-LAB-" + lab[-1]):
            raise Blocked("native-actor-pose-host-config-mismatch")
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
                    or type(guest.get("nativeActorPoseVersion")) is not int
                    or guest["nativeActorPoseVersion"] != 1
                    or type(guest.get("nativeReadLeaseVersion")) is not int
                    or guest["nativeReadLeaseVersion"] != 1
                    or not isinstance(instance, str) or re.fullmatch(r"[0-9a-f]{32}", instance) is None
                    or current.get("instanceId") != instance):
                raise Blocked("native-actor-pose-endpoint-not-ready")
            before = datetime.now(timezone.utc)
            request_started = time.perf_counter()
            response = client.request("/api/native-actor-pose", method="POST", payload=payload)
            elapsed = time.perf_counter() - request_started
            after = datetime.now(timezone.utc)
            if elapsed >= xyz.MAX_RESPONSE_SECONDS:
                raise Blocked("native-actor-pose-response-too-slow")
            if (not isinstance(response, dict)
                    or set(response) != {"nativeActorPoseVersion", "instanceId", "hashMode",
                                        "observedAtUtc", "report"}
                    or type(response["nativeActorPoseVersion"]) is not int
                    or response["nativeActorPoseVersion"] != 1
                    or response["hashMode"] != "fresh-bytes" or response["instanceId"] != instance):
                raise Blocked("native-actor-pose-response-invalid")
            metrics = validate_report(response["report"], pid=game["processId"],
                                      ticks=game["processStartUtcTicks"])
            try:
                xyz.validate_response_time(response["report"], response["observedAtUtc"], before, after)
            except Blocked as error:
                raise Blocked(str(error).replace("native-xyz", "native-actor-pose")) from None
            raw = (json.dumps(response["report"], sort_keys=True, separators=(",", ":"),
                              allow_nan=False) + "\n").encode("utf-8")
            if len(raw) > xyz.REPORT_MAX_BYTES:
                raise Blocked("native-actor-pose-report-too-large")
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
                   "metrics": dict(metrics, unitKey=metrics["playerKeyDecimal"]),
                   "responseSeconds": elapsed,
                   "wallSecondsBeforeSummaryWrite": time.perf_counter() - started}
        with (folder / "summary.json").open("x", encoding="utf-8") as output:
            json.dump(summary, output, indent=2, allow_nan=False)
        return summary
    except Blocked:
        raise
    except (ClientError, ControlHostError, OSError, ValueError, KeyError, TypeError,
            AttributeError, OverflowError, struct.error):
        raise Blocked("native-actor-pose-unavailable") from None
