#!/usr/bin/env python3
"""One reviewed, armed, bounded feedback movement session.

`prepare` acquires one navigation lease and captures the frame that a human
reviews. `run-reviewed` consumes that exact review, arms exactly once, and runs
at most six finite actions.  It never recaptures, rearms, retries ambiguous
input, or invokes recovery.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient, _action, _arm, _capture
from scripts.control_host import HostConfig, VmEpochGuard
from scripts.movement_controller import (
    Calibration, MovementAction, MovementError, MovementHalted, Position,
    WaypointController, calibrate_displacement, validate_noncollinear,
    planar_distance,
)
from scripts.nav_access_queue import AccessQueue
from scripts.nav_control_watchdog import bind_identity, resource_epoch
from scripts.vm_console_native import process_identity


SHA = re.compile(r"[A-F0-9]{64}\Z")
SAFE_KEY = frozenset(("w", "q", "s", "e"))


class MovementSessionError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise MovementSessionError(message)


def load(path: Path, *, limit=16 * 1024 * 1024) -> dict:
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            "missing, symbolic, or oversized JSON input")
    value = json.loads(path.read_text(encoding="utf-8-sig"),
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    require(isinstance(value, dict), "JSON object required")
    return value


def save(path: Path, value, *, private=False):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    require(value.tzinfo is not None, "aware UTC timestamp required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitized(value):
    if isinstance(value, dict):
        return {key: ("[redacted]" if any(word in key.casefold()
                for word in ("token", "secret", "password", "authorization"))
                else sanitized(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    return value


class PinnedHost:
    """Validate one already-running coordinated host without taking its mutex."""

    def __init__(self, plan_path: Path):
        self.plan_path = Path(plan_path).resolve(strict=True)
        self.plan = load(self.plan_path)
        self.receipt_path = self.plan_path.parent / "process.json"
        self.receipt = load(self.receipt_path)
        plan, receipt = self.plan, self.receipt
        require(receipt.get("vmIdentity") == plan.get("vmIdentity")
                and receipt.get("configSha256") == plan.get("configSha256")
                and receipt.get("runtimeHashes") == plan.get("runtimeHashes")
                and str(receipt.get("canonicalDatabase", "")).casefold()
                    == str(Path(plan["database"]).resolve()).casefold()
                and receipt.get("resource") == plan.get("resource")
                and receipt.get("windowsSessionId") == plan.get("expectedWindowsSession")
                and receipt.get("inJob") is False, "host receipt differs from plan")
        self.config = HostConfig.load(Path(plan["configPath"]))
        self.client = ControlClient(self.config)
        self.target = None

    def check(self):
        plan = self.plan
        require(not Path(plan["shutdownFile"]).exists(), "host shutdown requested")
        require(sha(Path(plan["configPath"])) == plan["configSha256"], "host config changed")
        for relative, expected in plan["runtimeHashes"].items():
            require(sha(ROOT / relative) == expected, "host runtime changed")
        require(process_identity(self.receipt["pid"]) == self.receipt["processIdentity"],
                "host process changed")
        guard = VmEpochGuard(self.config)
        require(guard.module.collect_identity(guard.config) == plan["vmIdentity"],
                "VM identity changed")

    def status(self, *, require_idle=True, require_armed=None):
        self.check()
        value = self.client.request("/api/status", method="GET")
        host, guest = value.get("host", {}), value.get("guest", {})
        coordination = host.get("coordination", {})
        require(host.get("connected") is True and host.get("vmIdentity") == self.plan["vmIdentity"]
                and host.get("consoleReservation", {}).get("held") is True
                and host.get("consoleReservation", {}).get("faulted") is False
                and coordination.get("state") == "ready"
                and coordination.get("resource") == self.plan["resource"], "host is not ready")
        require(coordination.get("supervisor", {}).get("epoch") == resource_epoch(bind_identity(host, guest)),
                "supervisor is bound to another game identity")
        target = {key: guest.get("target", {}).get(key) for key in
                  ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")}
        require(guest.get("target", {}).get("isForeground") is True, "RIFT is not foreground")
        if self.target is None:
            self.target = target
        require(target == self.target, "game target changed")
        require(guest.get("recoveryRequired") is False and guest.get("desktopInputsDown") == [],
                "guest requires recovery or reports input down")
        if require_idle:
            require(guest.get("busy") is False, "guest action is busy")
        if require_armed is not None:
            require(guest.get("armed") is require_armed, "unexpected arm state")
            if require_armed:
                require(float(guest.get("expiresInSeconds", 0)) > 0.5, "arm is expiring")
        self.check()
        return value


class LiveQueueLease:
    def __init__(self, queue: AccessQueue, request_id: str, token: str, resource: str):
        self.queue, self.request_id, self.token, self.resource = queue, request_id, token, resource

    def check(self):
        return self.queue.check(self.request_id, self.token)

    def heartbeat(self):
        return self.queue.heartbeat(self.request_id, self.token)

    def finish(self, outcome: str, evidence: list[str]):
        result = self.queue.finish(self.request_id, self.token, outcome, evidence)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            requests, after, resources = [], 0, None
            while True:
                page = self.queue.status(after_sequence=after, limit=100)
                requests.extend(page["requests"]); resources = resources or page["resources"]
                if page["next_sequence"] is None: break
                after = page["next_sequence"]
            request = next((row for row in requests if row["request_id"] == self.request_id), None)
            resource = next((row for row in resources if row["name"] == self.resource), None)
            if (request is not None and request["state"] == outcome and resource is not None
                    and not resource["blocked"] and resource["holder"] is None):
                return result
            time.sleep(.05)
        raise MovementSessionError("watchdog did not verify queue cleanup")


def acquire(plan: dict) -> tuple[LiveQueueLease, dict]:
    queue = AccessQueue(plan["database"])
    with queue.dispatch_fence(timeout=5):
        state = queue.status(limit=100)
        resource = next((row for row in state["resources"] if row["name"] == plan["resource"]), None)
        require(resource is not None and not resource["blocked"] and resource["holder"] is None,
                "control resource unavailable")
        require(not any(row["state"] in ("queued", "active", "cleanup") for row in state["requests"]),
                "control queue occupied")
        request_id = "movement-" + uuid.uuid4().hex[:16]
        queue.submit(request_id, "movement-session", "C", {plan["resource"]: resource["epoch"]},
                     ttl_ms=30000, max_ms=120000, estimated_ms=12000)
        grant = queue.dispatch()
        require(grant and grant["request_id"] == request_id, "movement lease unavailable")
    return LiveQueueLease(queue, request_id, grant["token"], plan["resource"]), grant


def prepare(host_plan: Path, feedback_pin: Path, output: Path, mode: str,
            goal: Position | None = None, calibration_profile: Path | None = None,
            keys: tuple[str, ...] = ("w", "q"), dimension: str = "2d") -> dict:
    require(dimension in ("1d", "2d"), "movement dimension must be 1d or 2d")
    key_count = 1 if dimension == "1d" else 2
    require(isinstance(keys, (tuple, list)) and len(keys) == key_count
            and all(key in SAFE_KEY for key in keys) and len(set(keys)) == len(keys),
            f"{dimension} calibration requires {key_count} distinct w/q/s/e key(s)")
    keys = tuple(keys)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    host = PinnedHost(host_plan)
    before = host.status(require_armed=False)
    pin = Path(feedback_pin).resolve(strict=True)
    pin_value = load(pin)
    _require_feedback_target({"target": before["guest"]["target"]}, pin_value)
    lease, grant = acquire(host.plan)
    client = ControlClient(host.config, access={"request_id": lease.request_id, "token": lease.token})
    succeeded = False
    try:
        capture = _capture(client, output / "capture")
        heartbeat = lease.heartbeat()
        session = {
            "schemaVersion": 1, "evidenceKind": "reviewed-movement-session/1",
            "sessionId": uuid.uuid4().hex, "mode": mode, "movementDimension": dimension,
            "hostPlan": str(host.plan_path), "hostPlanSha256": sha(host.plan_path),
            "hostReceipt": str(host.receipt_path), "hostReceiptSha256": sha(host.receipt_path),
            "feedbackPin": str(pin), "feedbackPinSha256": sha(pin),
            "target": before["guest"]["target"],
            "resource": host.plan["resource"],
            "lease": {key: value for key, value in grant.items() if key != "token"},
            "privateGrant": str((output / "grant.private.json").resolve()),
            "capture": capture,
            "captureMetadataSha256": sha(Path(capture["capture"])),
            "captureImageSha256": sha(Path(capture["image"])),
            "allowedKeys": list(keys), "calibrationPulseMs": 150,
            "budgets": {"maxElapsedSeconds": 12, "maxActions": 6,
                        "maxTotalHoldMs": 900, "maxRadius": 6},
            "goal": asdict(goal) if goal else None,
            "calibrationProfile": str(Path(calibration_profile).resolve(strict=True))
                if calibration_profile else None,
            "calibrationProfileSha256": sha(Path(calibration_profile).resolve(strict=True))
                if calibration_profile else None,
            "preparedAtUtc": iso(utc_now()), "heartbeat": heartbeat,
        }
        require(mode in ("calibration", "movement"), "invalid movement mode")
        require((mode == "movement") == (goal is not None and calibration_profile is not None),
                "movement requires a goal and calibration profile")
        save(output / "grant.private.json", {"request_id": lease.request_id, "token": lease.token}, private=True)
        save(output / "session-plan.json", session)
        save(output / "initial-status.json", sanitized(before))
        succeeded = True
        return {"sessionPlan": str((output / "session-plan.json").resolve()),
                "capture": capture["image"], "requestId": lease.request_id,
                "reviewRequired": True}
    finally:
        if not succeeded:
            try: client.request("/api/stop", method="POST", payload={})
            except Exception: pass
            try: lease.finish("failed", [str(output), "prepare failed"])
            except Exception: pass


def _position(sample) -> Position:
    return Position(float(sample.xyz[0]), float(sample.xyz[1]), float(sample.xyz[2]))


def _target_identity(value: dict) -> dict:
    require(isinstance(value, dict), "game target identity is missing")
    result = {key: value.get(key) for key in
              ("processId", "processStartUtcTicks", "executableSha256")}
    require(type(result["processId"]) is int
            and type(result["processStartUtcTicks"]) is int
            and isinstance(result["executableSha256"], str)
            and SHA.fullmatch(result["executableSha256"].upper()) is not None,
            "game target identity is invalid")
    result["executableSha256"] = result["executableSha256"].upper()
    return result


def _sample_identity(value: dict) -> dict:
    require(isinstance(value, dict), "movement sample identity is missing")
    identity = {key: value.get(key) for key in (
        "lab", "player", "addonEpoch", "sourceAddress", "readerProcessId",
        "readerProcessStartUtcTicks", "readerExecutableSha256", "readerInstance",
        "readerNonce", "receiverInstance")}
    require(all(isinstance(identity[key], str) and identity[key] for key in
                ("lab", "player", "sourceAddress", "readerExecutableSha256",
                 "readerInstance", "readerNonce", "receiverInstance"))
            and type(identity["addonEpoch"]) is int
            and type(identity["readerProcessId"]) is int
            and type(identity["readerProcessStartUtcTicks"]) is int,
            "movement sample identity is invalid")
    identity["readerExecutableSha256"] = identity["readerExecutableSha256"].upper()
    identity["target"] = _target_identity(value.get("target"))
    return identity


def _require_feedback_target(session: dict, pin: dict):
    require(isinstance(pin, dict) and isinstance(pin.get("gameIdentity"), dict),
            "feedback pin game identity is missing")
    require(_target_identity(pin["gameIdentity"]) == _target_identity(session.get("target")),
            "feedback pin targets another game process")


def _require_advancing(prior, current):
    before, after = prior.to_dict(), current.to_dict()
    require(type(before.get("outerSequence")) is int and type(after.get("outerSequence")) is int
            and after["outerSequence"] > before["outerSequence"], "feedback did not advance")
    for key in ("addonSequence", "addonClock"):
        if key in before or key in after:
            require(key in before and key in after and after[key] > before[key],
                    "addon feedback did not advance")
    return current


def _action_result(response: dict) -> tuple[dict, datetime]:
    result = response.get("result", {})
    require(result.get("deliverySucceeded") is True and result.get("releaseSucceeded") is True
            and result.get("cancelled") is False and result.get("targetLost") is False
            and result.get("stateUncertain") is False and response.get("recoveryRequired") is False,
            "action delivery or release is ambiguous")
    completed = datetime.fromisoformat(response["completedAtUtc"].replace("Z", "+00:00"))
    require(completed.tzinfo is not None, "action completion timestamp is invalid")
    return result, completed


def _stop_and_verify(host, output: Path) -> dict:
    stopped = host.stop()
    require(stopped.get("stopped") is True and stopped.get("recoveryRequired") is False,
            "STOP did not verify release")
    final_status = host.status(require_armed=False)
    guest = final_status["guest"]
    require(guest.get("busy") is False and guest.get("desktopInputsDown") == []
            and guest.get("recoveryRequired") is False, "final released state is not idle")
    save(Path(output) / "final-status.json", sanitized(final_status))
    return final_status


def execute_armed_session(*, session: dict, review: dict, output: Path, host, lease,
                          feedback, clock=time.monotonic, now=utc_now,
                          controller_factory=WaypointController) -> dict:
    """Offline-testable orchestration seam; dependencies perform all external I/O."""
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    require(review.get("schemaVersion") == 1 and review.get("decision") == "approve"
            and review.get("sessionId") == session["sessionId"]
            and review.get("sessionPlanSha256") == session["sessionPlanSha256"]
            and review.get("captureId") == session["capture"]["captureId"]
            and review.get("captureImageSha256") == session["captureImageSha256"]
            and isinstance(review.get("note"), str) and 12 <= len(review["note"].strip()) <= 400,
            "review does not approve the exact session and capture")
    actions = []; samples = []; success = False; released = False
    try:
        lease.check(); lease.heartbeat(); host.status(require_armed=False)
        initial = feedback.wait_initial(timeout_seconds=4.5); samples.append(initial.to_dict())
        mode = session["mode"]
        dimension = session.get("movementDimension", "2d")
        require(dimension in ("1d", "2d"), "session movement dimension is invalid")
        profile = calibrations = start = goal = None
        if mode == "movement":
            profile = load(Path(session["calibrationProfile"]))
            profile_dimension = profile.get("movementDimension", "2d")
            require(profile.get("schemaVersion") == 1
                    and profile.get("evidenceKind") == "empirical-movement-calibration/1"
                    and profile.get("mode") == "calibration" and profile.get("status") == "calibrated"
                    and profile_dimension == dimension
                    and profile.get("calibrationKeys") == session.get("allowedKeys")
                    and isinstance(session.get("allowedKeys"), list)
                    and len(session["allowedKeys"]) == (1 if dimension == "1d" else 2)
                    and set(profile.get("calibrations", {})) == set(session["allowedKeys"]),
                    "calibration profile schema, dimension, or reviewed keys are invalid")
            require(profile.get("calibrationIdentity") == _sample_identity(initial.to_dict()),
                    "calibration profile identity differs from current live feedback")
            if dimension == "1d":
                end = profile.get("calibrationEnd", {}).get("xyz")
                require(isinstance(end, dict) and set(end) == {"x", "y", "z"}
                        and planar_distance(Position(**end), _position(initial)) <= .10,
                        "1d calibration endpoint differs from current start")
            calibrations = {key: Calibration(**value) for key, value in profile["calibrations"].items()}
            start = _position(initial); goal = Position(**session["goal"])
            if dimension == "2d":
                cross = validate_noncollinear(calibrations, *session["allowedKeys"])
                require(abs(float(profile.get("normalizedCross")) - cross) <= 1e-12,
                        "calibration profile cross-check differs")
            else:
                require(profile.get("normalizedCross") is None,
                        "1d calibration profile must not claim a cross-check")
                vector = calibrations[session["allowedKeys"][0]]
                dx = vector.dx_per_ms * vector.calibration_hold_ms
                dz = vector.dz_per_ms * vector.calibration_hold_ms
                norm2 = dx * dx + dz * dz
                require(math.isfinite(norm2) and norm2 > 0,
                        "1d calibration vector is invalid")
                gx, gz = goal.x - start.x, goal.z - start.z
                alpha = (gx * dx + gz * dz) / norm2
                residual = abs(gx * dz - gz * dx) / math.sqrt(norm2)
                require(1.5 <= alpha <= 2.5 and residual <= .05 and gx * dx + gz * dz > 0,
                        "1d goal is not a positive 1.5..2.5 calibrated displacement")
                require((alpha - 1) * vector.horizontal_displacement > .35
                        and (alpha - 2) * vector.horizontal_displacement <= .30,
                        "1d goal does not require and permit exactly two calibrated actions")
        host.arm(session["capture"]["capture"], review["note"], output / "arm.private.json")
        started = clock()
        if mode == "calibration":
            calibrations = {}
            prior = initial
            calibration_keys = session.get("allowedKeys")
            require(isinstance(calibration_keys, list)
                    and len(calibration_keys) == (1 if dimension == "1d" else 2)
                    and all(key in SAFE_KEY for key in calibration_keys)
                    and len(set(calibration_keys)) == len(calibration_keys),
                    "session calibration keys are invalid")
            for index, key in enumerate(calibration_keys, 1):
                require(clock() - started <= 12, "elapsed budget")
                lease.check(); lease.heartbeat(); host.status(require_armed=True)
                action = MovementAction(key, 150, 0, 0)
                response = host.action(action, output / f"action-{index}.json")
                _result, completed = _action_result(response)
                after = _require_advancing(prior,
                    feedback.wait_after(completed, prior, timeout_seconds=4.5))
                samples.append(after.to_dict())
                calibrations[key] = calibrate_displacement(key, _position(prior), _position(after), 150)
                actions.append({"index": index, "decision": asdict(action), "result": response,
                                "before": prior.to_dict(), "after": after.to_dict()})
                prior = after
                require(clock() - started <= 12, "elapsed budget")
            cross = (validate_noncollinear(calibrations, calibration_keys[0], calibration_keys[1])
                     if dimension == "2d" else None)
            result_payload = {"mode": mode, "status": "calibrated",
                              "schemaVersion": 1,
                              "evidenceKind": "empirical-movement-calibration/1",
                              "movementDimension": dimension,
                              "calibrationIdentity": _sample_identity(initial.to_dict()),
                              "calibrationEnd": prior.to_dict(),
                              "calibrationKeys": calibration_keys,
                              "calibrations": {key: asdict(value) for key, value in calibrations.items()},
                              "normalizedCross": cross}
            success = True
        else:
            controller = controller_factory(calibrations, start, goal, tolerance=.30,
                max_goal_actions=6, max_elapsed_seconds=12, max_total_hold_ms=900, max_radius=6)
            prior = initial; settles = 0
            while controller.status != "arrived":
                elapsed = clock() - started
                require(elapsed <= 12, "elapsed budget")
                decision = controller.decide(_position(prior), elapsed)
                if decision is None:
                    require(controller.feedback_iterations >= 2,
                            "arrival is not eligible before two action feedback iterations")
                    require(settles == 0, "arrival requires exactly one no-input confirmation")
                    require(clock() - started <= 12, "elapsed budget")
                    settle = _require_advancing(prior,
                        feedback.wait_next(prior, timeout_seconds=3.0))
                    require(planar_distance(_position(settle), goal) <= controller.tolerance,
                            "arrival settle left tolerance")
                    samples.append(settle.to_dict()); controller.observe(_position(settle), clock() - started)
                    prior = settle; settles += 1
                    require(controller.status == "arrived", "arrival did not confirm")
                    continue
                lease.check(); lease.heartbeat(); host.status(require_armed=True)
                response = host.action(decision, output / f"action-{len(actions)+1}.json")
                _result, completed = _action_result(response)
                after = _require_advancing(prior,
                    feedback.wait_after(completed, prior, timeout_seconds=4.5))
                samples.append(after.to_dict()); controller.record_feedback(_position(after), clock() - started)
                actions.append({"index": len(actions)+1, "decision": asdict(decision),
                                "result": response, "before": prior.to_dict(), "after": after.to_dict()})
                prior = after
                if controller.status == "confirming-arrival" and controller.feedback_iterations >= 2:
                    lease.check(); lease.heartbeat()
                    _stop_and_verify(host, output); released = True
                    settle = _require_advancing(prior,
                        feedback.wait_next(prior, timeout_seconds=3.0))
                    require(planar_distance(_position(settle), goal) <= controller.tolerance,
                            "arrival settle left tolerance")
                    samples.append(settle.to_dict())
                    controller.confirm_released_settle(_position(settle))
                    prior = settle; settles += 1
                    require(controller.status == "arrived", "arrival did not confirm")
            require(controller.status == "arrived" and settles == 1
                    and controller.feedback_iterations >= 2,
                    "arrival lacks two action feedback iterations and a distinct confirmation")
            result_payload = {"mode": mode, "status": "arrived",
                              "movementDimension": dimension, "goal": session["goal"],
                              "actions": controller.action_count, "totalHoldMs": controller.total_hold_ms,
                              "feedbackIterations": controller.feedback_iterations,
                              "settles": settles, "arrivalObservations": 2}
            success = True
        return {"success": True, **result_payload, "actionEvidence": actions, "samples": samples}
    finally:
        try:
            if not released:
                _stop_and_verify(host, output); released = True
        finally:
            lease.finish("succeeded" if success and released else "failed",
                         [str(output.resolve()), "reviewed bounded movement session"])


class LiveHostAdapter:
    def __init__(self, pinned: PinnedHost, client: ControlClient):
        self.pinned, self.client = pinned, client
    def status(self, **kwargs): return self.pinned.status(**kwargs)
    def arm(self, capture, note, output): return _arm(self.client, Path(capture), note, Path(output))
    def action(self, decision, output):
        response = _action(self.client, SimpleNamespace(
            arm=Path(output).parent / "arm.private.json", keys=decision.key,
            hold_ms=decision.hold_ms, mouse_button=None, dx=0, dy=0, wheel=0,
            click_target=None, output=Path(output)))
        return response["result"]
    def stop(self): return self.client.request("/api/stop", method="POST", payload={})


def validate_session_pins(session: dict):
    require(sha(Path(session["hostPlan"])) == session["hostPlanSha256"]
            and sha(Path(session["hostReceipt"])) == session["hostReceiptSha256"]
            and sha(Path(session["feedbackPin"])) == session["feedbackPinSha256"], "session pin changed")
    if session["mode"] == "movement":
        require(sha(Path(session["calibrationProfile"])) == session.get("calibrationProfileSha256"),
                "calibration profile changed")


def run_reviewed(session_path: Path, review_path: Path, output: Path) -> dict:
    session_path = Path(session_path).resolve(strict=True); session = load(session_path)
    session["sessionPlanSha256"] = sha(session_path)
    review = load(Path(review_path).resolve(strict=True))
    validate_session_pins(session)
    _require_feedback_target(session, load(Path(session["feedbackPin"])))
    grant = load(Path(session["privateGrant"]), limit=8192)
    require(set(grant) == {"request_id", "token"} and grant["request_id"] == session["lease"]["request_id"],
            "private grant differs from session")
    pinned = PinnedHost(Path(session["hostPlan"])); pinned.target = {
        key: session["target"][key] for key in
        ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")}
    queue = LiveQueueLease(AccessQueue(pinned.plan["database"]), grant["request_id"], grant["token"],
                           pinned.plan["resource"])
    client = ControlClient(pinned.config, access=grant)
    from scripts.movement_feedback import PinnedFeedback
    feedback = PinnedFeedback(load(Path(session["feedbackPin"])), Path(output).resolve() / "feedback")
    result = execute_armed_session(session=session, review=review, output=Path(output),
             host=LiveHostAdapter(pinned, client), lease=queue, feedback=feedback)
    save(Path(output) / "result.json", sanitized(result))
    return sanitized(result)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("--host-plan", type=Path, required=True)
    prep.add_argument("--feedback-pin", type=Path, required=True); prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--mode", choices=("calibration", "movement"), required=True)
    prep.add_argument("--dimension", choices=("1d", "2d"), default="2d")
    prep.add_argument("--keys", nargs="+", choices=tuple(sorted(SAFE_KEY)), default=("w", "q"),
                      metavar="KEY")
    prep.add_argument("--goal", nargs=3, type=float, metavar=("X", "Y", "Z")); prep.add_argument("--calibration-profile", type=Path)
    run = sub.add_parser("run-reviewed"); run.add_argument("--session-plan", type=Path, required=True)
    run.add_argument("--review", type=Path, required=True); run.add_argument("--output", type=Path, required=True)
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "prepare":
        goal = Position(*args.goal) if args.goal else None
        result = prepare(args.host_plan, args.feedback_pin, args.output, args.mode, goal,
                         args.calibration_profile, tuple(args.keys), args.dimension)
    else: result = run_reviewed(args.session_plan, args.review, args.output)
    print(json.dumps(sanitized(result), sort_keys=True)); return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (MovementSessionError, MovementError, MovementHalted) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr); raise SystemExit(1)
