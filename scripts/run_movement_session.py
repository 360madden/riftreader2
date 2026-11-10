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
from datetime import datetime, timedelta, timezone
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

from scripts.control_client import ControlClient, MAX_CAPTURE_REVIEW_SECONDS, _action, _arm, _capture
from scripts.control_host import HostConfig, VmEpochGuard
from scripts.movement_controller import (
    Calibration, MovementAction, MovementError, MovementHalted, Position,
    WaypointController, calibrate_displacement, validate_noncollinear,
    planar_distance,
)
from scripts.nav_access_queue import AccessQueue, QueueError
from scripts.nav_control_watchdog import bind_identity, resource_epoch
from scripts.vm_console_native import listener_owner, process_identity


SHA = re.compile(r"[A-F0-9]{64}\Z")
SAFE_KEY = frozenset(("w", "q", "s", "e"))
TURN_KEY = frozenset(("a", "d"))
ALL_KEY = SAFE_KEY | TURN_KEY
INITIAL_FEEDBACK_TIMEOUT_SECONDS = 4.5
ACTION_FEEDBACK_TIMEOUT_SECONDS = 6.0
ACTION_READY_TIMEOUT_SECONDS = 10.0
PREARM_ACTION_READY_TIMEOUT_SECONDS = 20.0
PREARM_FAST_ANCHOR_REMAINING_MILLISECONDS = 6_250.0


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

    def status(self, *, require_idle=True, require_armed=None, require_foreground=True):
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
        if require_foreground:
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



def _require_exact_managed_task(lab: str, receipt_path: Path, receipt: dict, *, inspect_lab2=False, inspect_controller=False,
                                _inspection_task_verifier=None) -> None:
    """Verify task registration and the sole live generation at admission time."""
    from scripts.managed_controller_receipt import (
        ManagedReceiptError, resolve_current_managed_controller, verify_inspection_task,
    )
    require(not inspect_lab2 or lab == "lab2", "Lab 2 inspection task required")
    inspect_controller = inspect_controller or inspect_lab2
    require(not inspect_controller or lab in ("lab1", "lab2"), "inspection lab invalid")
    require(_inspection_task_verifier is None or inspect_controller,
            "prepared task verifier requires inspection")
    try:
        actual_path, actual_receipt, _ = resolve_current_managed_controller(
            lab, expected_receipt_path=receipt_path,
            verify_owner=(_inspection_task_verifier if _inspection_task_verifier is not None
                          else verify_inspection_task) if inspect_controller else None,
            allow_legacy=not inspect_controller)
    except (ManagedReceiptError, OSError, RuntimeError) as error:
        raise MovementSessionError("managed task ownership or generation refused") from error
    require(actual_path == Path(receipt_path).resolve(strict=True)
            and actual_receipt == receipt, "managed task receipt was altered")


class ManagedPinnedHost(PinnedHost):
    """A reviewed movement host bound to one exact managed task generation."""

    _allowed_labs = ("lab1", "lab2")
    _inspect_lab2_task = False
    _inspect_controller_task = False

    def __init__(self, plan_path: Path, *, _inspection_task_verifier=None):
        require(_inspection_task_verifier is None or self._inspect_controller_task or self._inspect_lab2_task,
                "prepared task verifier requires Lab 2 inspection")
        self.plan_path = Path(plan_path).resolve(strict=True)
        self.plan = load(self.plan_path)
        plan = self.plan
        require(plan.get("kind") == "managed-controller/1"
                and plan.get("lab") in self._allowed_labs,
                "managed host plan is invalid")
        from scripts.ensure_controller import CONFIGS, QUEUE
        lab = plan["lab"]
        config_path = CONFIGS[lab].resolve(strict=True)
        self.receipt_path = Path(plan["receiptPath"]).resolve(strict=True)
        task_root = ROOT / "artifacts/controller-tasks" / lab
        require(self.receipt_path.name == "process.json"
                and self.receipt_path.parent.parent == task_root.resolve()
                and not self.receipt_path.is_symlink(),
                "managed host receipt path is not an owned task")
        require(Path(plan["configPath"]).resolve(strict=True) == config_path
                and Path(plan["database"]).resolve(strict=True) == QUEUE.resolve(strict=True)
                and plan["resource"] == "vm:rift-lab-" + lab[-1],
                "managed host plan paths or resource mismatch")
        self.receipt = load(self.receipt_path)
        task_options = ({"inspect_lab2": True} if self._inspect_lab2_task
                        else {"inspect_controller": True} if self._inspect_controller_task
                        else {"inspect_lab2": False})
        if _inspection_task_verifier is not None:
            task_options["_inspection_task_verifier"] = _inspection_task_verifier
        _require_exact_managed_task(lab, self.receipt_path, self.receipt, **task_options)
        self.config = HostConfig.load(config_path)
        self.client = ControlClient(self.config)
        self.target = plan.get("target")
        require(isinstance(self.target, dict) and set(self.target) ==
                {"processId", "processStartUtcTicks", "executableSha256", "windowHandle"},
                "managed host target pin invalid")
        # Even a read-only inspection must establish unique inventory membership on admission.
        ManagedPinnedHost.check(self)

    def _check_managed_owner(self):
        plan, receipt = self.plan, self.receipt
        require(sha(self.receipt_path) == plan.get("receiptSha256"),
                "managed host task receipt changed")
        require(receipt.get("lab") == plan["lab"]
                and receipt.get("task") == "rr2-controller-" + plan["lab"]
                and receipt.get("vmIdentity") == plan.get("vmIdentity")
                and receipt.get("configSha256") == plan.get("configSha256")
                and receipt.get("sourceHashes") == plan.get("sourceHashes")
                and type(receipt.get("pid")) is int and receipt["pid"] > 0
                and isinstance(receipt.get("processIdentity"), dict)
                and type(receipt.get("session")) is int and receipt["session"] > 0,
                "managed host task receipt differs from plan")
        require(not (self.receipt_path.parent / "exited.json").exists()
                and not (self.receipt_path.parent / "failure.json").exists()
                and not (self.receipt_path.parent / "stop.request").exists(),
                "managed host task has exited or failed")
        require(sha(Path(plan["configPath"])) == plan["configSha256"],
                "managed host config changed")
        hashes = plan["sourceHashes"]
        from scripts.ensure_controller import RUNTIME_FILES
        require(isinstance(hashes, dict) and set(hashes) == set(RUNTIME_FILES),
                "managed host source hash set invalid")
        for relative, expected in hashes.items():
            path = Path(relative)
            require(isinstance(relative, str) and not path.is_absolute()
                    and path.parts and path.parts[0] == "scripts"
                    and ".." not in path.parts and SHA.fullmatch(str(expected)),
                    "managed host source path or hash invalid")
            require(sha(ROOT / path) == expected, "managed host runtime changed")
        require(process_identity(receipt["pid"]) == receipt["processIdentity"],
                "managed host process epoch changed")
        require(listener_owner(self.config.ui_port) == receipt["pid"],
                "managed host operator listener owner changed")

    def check(self):
        self._check_managed_owner()
        guard = VmEpochGuard(self.config)
        require(guard.enabled and guard.module.collect_identity(guard.config)
                == self.plan["vmIdentity"], "managed host VM epoch changed")

    def status(self, **kwargs):
        value = super().status(**kwargs)
        host, guest = value["host"], value["guest"]
        coord = host["coordination"]
        supervisor = coord.get("supervisor")
        require(isinstance(supervisor, dict), "managed supervisor status invalid")
        reservation = host.get("consoleReservation", {})
        require(reservation.get("closing") is False
                and coord.get("shutdownRequested") is False
                and supervisor.get("terminationPending") is False,
                "managed controller is closing or terminating")
        require(coord.get("hostInstance") == self.plan["hostInstance"]
                and coord.get("connection") == self.plan["connection"]
                and coord.get("errorCode") is None
                and supervisor.get("epoch") == self.plan["supervisorEpoch"]
                and supervisor.get("state") == "running"
                and supervisor.get("threadAlive") is True
                and supervisor.get("initialCleanupVerified") is True
                and supervisor.get("errorCode") is None
                and host.get("instanceId") == self.plan["guestInstance"]
                and guest.get("instanceId") == self.plan["guestInstance"],
                "managed controller generation or supervisor changed")
        return value


class InspectionHost(ManagedPinnedHost):
    """Recheck the admitted VM epoch between full inventory checks in one read-only run."""

    _inspect_controller_task = True

    def check(self):
        self._check_managed_owner()
        guard = VmEpochGuard(self.config)
        expected = self.plan["vmIdentity"]
        require(guard.enabled and guard.module.verify_identity(guard.config, expected) == expected,
                "managed host VM epoch changed")

    def final_inventory_check(self):
        super().check()


class Lab2InspectionHost(InspectionHost):
    """Compatibility inspection host restricted to Lab 2."""

    _allowed_labs = ("lab2",)
    _inspect_lab2_task = True


def _discover_managed_host_plan(lab: str, output: Path, *, inspect_lab2=False,
                                inspect_controller=False,
                                _inspection_task_verifier=None) -> Path:
    from scripts.ensure_controller import CONFIGS, QUEUE
    require(lab in CONFIGS, "unknown managed lab")
    config_path = CONFIGS[lab].resolve(strict=True)
    config_sha = sha(config_path)
    config = HostConfig.load(config_path)
    listener_pid = listener_owner(config.ui_port)
    status = ControlClient(config).request("/api/status", method="GET")
    host, guest = status.get("host", {}), status.get("guest", {})
    coord = host.get("coordination", {})
    require(host.get("connected") is True and isinstance(host.get("vmIdentity"), dict)
            and coord.get("resource") == "vm:rift-lab-" + lab[-1]
            and coord.get("state") == "ready"
            and isinstance(coord.get("hostInstance"), str)
            and type(coord.get("connection")) is int
            and isinstance(guest.get("instanceId"), str),
            "managed controller is not ready for a pinned plan")
    task_root = ROOT / "artifacts/controller-tasks" / lab
    require(task_root.is_dir() and not task_root.is_symlink(),
            "managed controller task receipts unavailable")
    folders = list(task_root.iterdir())
    require(len(folders) <= 128, "managed controller receipt scan too large")
    matches = []
    for folder in folders:
        if not folder.is_dir() or folder.is_symlink():
            continue
        receipt_path = folder / "process.json"
        if not receipt_path.is_file() or (folder / "exited.json").exists() \
                or (folder / "failure.json").exists():
            continue
        try:
            receipt = load(receipt_path, limit=65536)
            identity = process_identity(receipt["pid"])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            continue
        if (receipt.get("lab") == lab
                and receipt.get("task") == "rr2-controller-" + lab
                and receipt.get("configSha256") == config_sha
                and receipt.get("vmIdentity") == host["vmIdentity"]
                and receipt.get("pid") == listener_pid
                and identity == receipt.get("processIdentity")):
            matches.append((receipt_path, receipt))
    require(len(matches) == 1, "managed controller task receipt missing or ambiguous")
    receipt_path, receipt = matches[0]
    task_options = {"inspect_controller": True} if inspect_controller else {"inspect_lab2": inspect_lab2}
    _require_exact_managed_task(lab, receipt_path, receipt, **task_options,
                                _inspection_task_verifier=_inspection_task_verifier)
    target = guest.get("target", {})
    target_pin = {key: target.get(key) for key in
                  ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")}
    supervisor = coord.get("supervisor", {})
    require(isinstance(supervisor, dict) and isinstance(supervisor.get("epoch"), str),
            "managed controller supervisor has no epoch")
    plan = {
        "kind": "managed-controller/1", "lab": lab,
        "configPath": str(config_path), "configSha256": config_sha,
        "database": str(QUEUE.resolve(strict=True)),
        "resource": "vm:rift-lab-" + lab[-1],
        "vmIdentity": host["vmIdentity"], "hostInstance": coord["hostInstance"],
        "connection": coord["connection"], "supervisorEpoch": supervisor["epoch"],
        "guestInstance": guest["instanceId"], "target": target_pin,
        "receiptPath": str(receipt_path.resolve(strict=True)),
        "receiptSha256": sha(receipt_path), "sourceHashes": receipt["sourceHashes"],
    }
    destination = Path(output) / "managed-host-plan.json"
    save(destination, plan)
    return destination


def admit_managed_host(lab: str, output: Path, *, require_foreground=True) -> ManagedPinnedHost:
    """Write the plan and return the already-ready controller validated against it."""
    admitted = ManagedPinnedHost(_discover_managed_host_plan(lab, output))
    admitted.status(require_armed=False, require_foreground=require_foreground)
    return admitted


def admit_inspection_host_with_status(lab: str, output: Path):
    """Admit one exact already-running controller, with two fresh strict task proofs."""
    require(lab in ("lab1", "lab2"), "inspection lab invalid")
    if lab == "lab2":
        return admit_lab2_inspection_host_with_status(output)
    from scripts.managed_controller_receipt import prepared_inspection_pair
    with prepared_inspection_pair(lab) as (verify_first, verify_second):
        admitted = InspectionHost(
            _discover_managed_host_plan(lab, output, inspect_controller=True,
                                        _inspection_task_verifier=verify_first),
            _inspection_task_verifier=verify_second)
        status = admitted.status(require_armed=False, require_foreground=True)
    return admitted, status


def admit_lab2_inspection_host_with_status(output: Path):
    from scripts.managed_controller_receipt import prepared_lab2_inspection_pair
    # Both queries remain at their original resolver boundaries. Only the
    # interpreter is shared; each callback triggers a fresh complete manager proof.
    with prepared_lab2_inspection_pair() as (verify_first, verify_second):
        admitted = Lab2InspectionHost(
            _discover_managed_host_plan("lab2", output, inspect_lab2=True,
                                        _inspection_task_verifier=verify_first),
            _inspection_task_verifier=verify_second)
        status = admitted.status(require_armed=False, require_foreground=True)
    return admitted, status


def admit_lab2_inspection_host(output: Path) -> Lab2InspectionHost:
    """Compatibility wrapper returning the validated host only."""
    admitted, _ = admit_lab2_inspection_host_with_status(output)
    return admitted


def write_managed_host_plan(lab: str, output: Path, *, require_foreground=True) -> Path:
    """Recover one managed controller and wait for actual idle guest readiness."""
    from scripts.ensure_controller import ensure, ensure_existing
    from scripts.operation_dependencies import DependencyUnavailable
    try:
        state = ensure(lab)
        deadline = time.monotonic() + 25
        while True:
            status = state.get("status") if isinstance(state, dict) else None
            host = status.get("host", {}) if isinstance(status, dict) else {}
            guest = status.get("guest", {}) if isinstance(status, dict) else {}
            target = guest.get("target", {}) if isinstance(guest, dict) else {}
            if (isinstance(host, dict) and isinstance(guest, dict)
                    and isinstance(target, dict) and host.get("connected") is True
                    and host.get("coordination", {}).get("state") == "ready"
                    and host.get("consoleReservation", {}).get("held") is True
                    and type(target.get("processId")) is int and target["processId"] > 0
                    and guest.get("armed") is False and guest.get("busy") is False
                    and guest.get("desktopInputsDown") == []
                    and guest.get("recoveryRequired") is False):
                break
            if time.monotonic() >= deadline:
                raise MovementSessionError("managed controller did not become ready")
            time.sleep(0.35)
            state = ensure_existing(lab)  # read-only: never launch another owner
    except DependencyUnavailable as error:
        raise MovementSessionError(f"managed controller unavailable: {error.code}") from error
    return admit_managed_host(lab, output, require_foreground=require_foreground).plan_path


def open_host(plan_path: Path) -> PinnedHost:
    kind = load(Path(plan_path)).get("kind")
    if kind == "managed-controller/1":
        return ManagedPinnedHost(plan_path)
    require(kind is None, "unknown host plan kind")
    return PinnedHost(plan_path)


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
        changing_scans = 0
        while time.monotonic() < deadline:
            requests, after, resources = [], 0, None
            changed_during_scan = False
            for _ in range(1000):
                page = self.queue.status(after_sequence=after, limit=100)
                batch, current_resources = page.get("requests"), page.get("resources")
                require(isinstance(batch, list) and isinstance(current_resources, list),
                        "queue cleanup response invalid")
                if resources is not None and current_resources != resources:
                    # The supervisor may finalize cleanup between status pages.
                    # Restart to obtain one stable view; never accept mixed pages.
                    changed_during_scan = True
                    break
                resources = current_resources
                require(all(isinstance(row, dict) and type(row.get("sequence")) is int
                            and isinstance(row.get("request_id"), str) for row in batch),
                        "queue cleanup request invalid")
                requests.extend(batch)
                cursor = page.get("next_sequence")
                if cursor is None:
                    break
                require(batch and type(cursor) is int and cursor > after
                        and cursor == batch[-1]["sequence"],
                        "queue cleanup pagination stalled")
                after = cursor
            else:
                raise MovementSessionError("queue cleanup scan incomplete")
            if changed_during_scan:
                changing_scans += 1
                require(changing_scans < 3, "queue resource changed during cleanup")
                time.sleep(.05)
                continue
            changing_scans = 0
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
        resource, after = None, 0
        for _ in range(1000):
            page = queue.status(after_sequence=after, limit=100)
            batch, resources = page.get("requests"), page.get("resources")
            require(isinstance(batch, list) and isinstance(resources, list),
                    "control queue response invalid")
            matches = [row for row in resources if isinstance(row, dict)
                       and row.get("name") == plan["resource"]]
            require(len(matches) == 1, "control resource unavailable")
            if resource is None:
                resource = dict(matches[0])
            require(matches[0] == resource, "control resource changed during queue scan")
            last = after
            for row in batch:
                require(isinstance(row, dict), "control queue request invalid")
                sequence = row.get("sequence")
                require(type(sequence) is int and sequence > last, "control queue sequence invalid")
                last = sequence
                if row.get("state") in ("queued", "active", "cleanup"):
                    specification = row.get("specification")
                    require(isinstance(specification, dict)
                            and isinstance(specification.get("resources"), dict),
                            "control queue request invalid")
                    require(plan["resource"] not in specification["resources"],
                            "control resource has pending work")
            cursor = page.get("next_sequence")
            if cursor is None:
                break
            require(batch and type(cursor) is int and cursor == last and cursor > after,
                    "control queue pagination stalled")
            after = cursor
        else:
            raise MovementSessionError("control queue scan incomplete")
        require(resource is not None and not resource["blocked"] and resource["holder"] is None,
                "control resource unavailable")
        request_id = "movement-" + uuid.uuid4().hex[:16]
        queue.submit(request_id, "movement-session", "C", {plan["resource"]: resource["epoch"]},
                     ttl_ms=30000, max_ms=120000, estimated_ms=12000)
        grant = queue.dispatch(request_id=request_id)
        if not (isinstance(grant, dict) and grant.get("request_id") == request_id
                and isinstance(grant.get("token"), str) and grant["token"]):
            cancelled = queue.cancel(request_id, "movement-session")
            require(cancelled.get("state") in ("cancelled", "cleanup"),
                    "movement lease cancellation unverified")
            raise MovementSessionError("movement lease unavailable")
        queue.check(request_id, grant["token"])
    return LiveQueueLease(queue, request_id, grant["token"], plan["resource"]), grant


def calibrated_relative_goal(calibration_profile: Path, key: str,
                             displacements: float) -> Position:
    require(key in SAFE_KEY, "relative goal requires one measured movement key")
    require(not isinstance(displacements, bool) and isinstance(displacements, (int, float))
            and math.isfinite(float(displacements)) and 1.5 <= float(displacements) <= 2.5,
            "calibrated displacements must be finite and from 1.5 through 2.5")
    profile = load(Path(calibration_profile).resolve(strict=True))
    require(profile.get("schemaVersion") == 1
            and profile.get("evidenceKind") == "empirical-movement-calibration/1"
            and profile.get("mode") == "calibration" and profile.get("status") == "calibrated"
            and profile.get("movementDimension") == "1d"
            and profile.get("calibrationKeys") == [key]
            and isinstance(profile.get("calibrations"), dict)
            and set(profile["calibrations"]) == {key},
            "relative goal requires a matching 1d calibration profile")
    vector = profile["calibrations"][key]
    end = profile.get("calibrationEnd", {}).get("xyz")
    require(isinstance(vector, dict) and vector.get("key") == key
            and isinstance(end, dict) and set(end) == {"x", "y", "z"},
            "relative goal calibration vector or endpoint is invalid")
    try:
        hold = vector["calibration_hold_ms"]
        dx, dz = float(vector["dx_per_ms"]), float(vector["dz_per_ms"])
        endpoint = Position(float(end["x"]), float(end["y"]), float(end["z"]))
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MovementSessionError("relative goal calibration values are invalid") from error
    require(type(hold) is int and 20 <= hold <= 150
            and all(math.isfinite(value) for value in (dx, dz, endpoint.x, endpoint.y, endpoint.z))
            and math.hypot(dx, dz) > 0,
            "relative goal calibration values are invalid")
    alpha = float(displacements)
    return Position(endpoint.x + alpha * dx * hold, endpoint.y,
                    endpoint.z + alpha * dz * hold)


def require_post_turn_calibration(turn_result: Path, calibration_profile: Path) -> None:
    turn = load(Path(turn_result).resolve(strict=True))
    profile = load(Path(calibration_profile).resolve(strict=True))
    require(turn.get("success") is True and turn.get("mode") == "turn"
            and turn.get("status") == "turn-input-completed"
            and turn.get("turnKey") in TURN_KEY and turn.get("headingClaimed") is False,
            "post-turn workflow requires a completed non-heading turn result")
    turn_samples, calibration_samples = turn.get("samples"), profile.get("samples")
    require(isinstance(turn_samples, list) and len(turn_samples) >= 2
            and isinstance(calibration_samples, list) and len(calibration_samples) >= 2,
            "post-turn workflow requires retained turn and calibration samples")
    turn_after, calibration_start = turn_samples[-1], calibration_samples[0]
    require(isinstance(turn_after, dict) and isinstance(calibration_start, dict)
            and _sample_identity(turn_after) == _sample_identity(calibration_start),
            "post-turn calibration identity differs from the turn result")
    try:
        _require_advancing_values(turn_after, calibration_start, require_addon=True)
    except MovementSessionError as error:
        raise MovementSessionError(
            "post-turn calibration did not start on newer producer feedback") from error
    try:
        turn_position = Position(**turn_after["xyz"])
        calibration_position = Position(**calibration_start["xyz"])
    except (KeyError, TypeError) as error:
        raise MovementSessionError("post-turn calibration positions are invalid") from error
    require(planar_distance(turn_position, calibration_position) <= .10,
            "post-turn calibration start moved away from the turn endpoint")


def prepare(host_plan: Path | None, feedback_pin: Path, output: Path, mode: str,
            goal: Position | None = None, calibration_profile: Path | None = None,
            keys: tuple[str, ...] = ("w", "q"), dimension: str = "2d",
            calibrated_displacements: float | None = None,
            turn_hold_ms: int = 100,
            after_turn_result: Path | None = None,
            managed_lab: str | None = None, calibration_hold_ms: int = 150) -> dict:
    require(dimension in ("1d", "2d"), "movement dimension must be 1d or 2d")
    require(mode in ("calibration", "movement", "turn"), "invalid movement mode")
    require(type(calibration_hold_ms) is int and 20 <= calibration_hold_ms <= 150,
            "calibration hold must be an integer from 20 through 150 ms")
    require(mode == "calibration" or calibration_hold_ms == 150,
            "calibration hold override applies only to calibration mode")
    key_count = 1 if dimension == "1d" else 2
    if mode == "turn":
        require(isinstance(keys, (tuple, list)) and len(keys) == 1 and keys[0] in TURN_KEY,
                "turn requires exactly one reviewed a/d key")
        require(type(turn_hold_ms) is int and 20 <= turn_hold_ms <= 150,
                "turn hold must be an integer from 20 through 150 ms")
        require(goal is None and calibration_profile is None and calibrated_displacements is None,
                "turn does not accept a goal or calibration profile")
        require(after_turn_result is None, "turn does not accept a prior turn result")
    else:
        require(isinstance(keys, (tuple, list)) and len(keys) == key_count
                and all(key in SAFE_KEY for key in keys) and len(set(keys)) == len(keys),
                f"{dimension} calibration requires {key_count} distinct w/q/s/e key(s)")
        if calibrated_displacements is not None:
            require(mode == "movement" and dimension == "1d" and calibration_profile is not None
                    and goal is None and len(keys) == 1,
                    "relative goal requires 1d movement, one key, and a calibration profile")
            goal = calibrated_relative_goal(calibration_profile, keys[0], calibrated_displacements)
        if after_turn_result is not None:
            require(mode == "movement" and calibration_profile is not None,
                    "post-turn result applies only to calibrated movement")
            require_post_turn_calibration(after_turn_result, calibration_profile)
        require((mode == "movement") == (goal is not None and calibration_profile is not None),
                "movement requires a goal and calibration profile")
    keys = tuple(keys)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    require((host_plan is None) != (managed_lab is None),
            "select exactly one legacy host plan or managed lab")
    if managed_lab is not None:
        host_plan = write_managed_host_plan(managed_lab, output)
    host = open_host(host_plan)
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
            "allowedKeys": list(keys), "calibrationPulseMs": calibration_hold_ms,
            "turnHoldMs": turn_hold_ms if mode == "turn" else None,
            "budgets": {"maxElapsedSeconds": 12,
                        "maxActions": 1 if mode == "turn" else 6,
                        "maxTotalHoldMs": turn_hold_ms if mode == "turn" else 900,
                        "maxRadius": 6},
            "goal": asdict(goal) if goal else None,
            "goalSource": ({"kind": "calibrated-relative", "key": keys[0],
                            "displacements": float(calibrated_displacements)}
                           if calibrated_displacements is not None else
                           ({"kind": "explicit"} if goal is not None else None)),
            "calibrationProfile": str(Path(calibration_profile).resolve(strict=True))
                if calibration_profile else None,
            "calibrationProfileSha256": sha(Path(calibration_profile).resolve(strict=True))
                if calibration_profile else None,
            "afterTurnResult": str(Path(after_turn_result).resolve(strict=True))
                if after_turn_result else None,
            "afterTurnResultSha256": sha(Path(after_turn_result).resolve(strict=True))
                if after_turn_result else None,
            "preparedAtUtc": iso(utc_now()), "heartbeat": heartbeat,
        }
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


def _require_advancing_values(before: dict, after: dict, *, require_addon=False):
    require(type(before.get("outerSequence")) is int and type(after.get("outerSequence")) is int
            and after["outerSequence"] > before["outerSequence"], "feedback did not advance")
    for key in ("addonSequence", "addonClock"):
        if require_addon or key in before or key in after:
            require(key in before and key in after and after[key] > before[key],
                    "addon feedback did not advance")


def _require_advancing(prior, current):
    before, after = prior.to_dict(), current.to_dict()
    _require_advancing_values(before, after)
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


def _require_action_ready_sample(prior, ready):
    before, current = prior.to_dict(), ready.to_dict()
    require(_sample_identity(current) == _sample_identity(before),
            "action-ready feedback identity changed")
    require(current["outerSequence"] >= before["outerSequence"]
            and current["addonSequence"] >= before["addonSequence"]
            and current["addonClock"] >= before["addonClock"],
            "action-ready feedback regressed")
    require(planar_distance(_position(ready), _position(prior)) <= .05,
            "action-ready position drifted before input")
    return ready


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
        initial = feedback.wait_initial(timeout_seconds=INITIAL_FEEDBACK_TIMEOUT_SECONDS)
        lease.check(); lease.heartbeat(); host.status(require_armed=False)
        samples.append(initial.to_dict())
        mode = session["mode"]
        require(mode in ("calibration", "movement", "turn"), "session mode is invalid")
        dimension = session.get("movementDimension", "2d")
        require(dimension in ("1d", "2d"), "session movement dimension is invalid")
        profile = calibrations = start = goal = None
        calibration_hold_ms = session.get("calibrationPulseMs", 150)
        if mode == "calibration":
            require(type(calibration_hold_ms) is int and 20 <= calibration_hold_ms <= 150,
                    "session calibration hold is invalid")
        turn_keys = None; turn_hold = None
        if mode == "turn":
            turn_keys = session.get("allowedKeys")
            turn_hold = session.get("turnHoldMs")
            require(isinstance(turn_keys, list) and len(turn_keys) == 1
                    and turn_keys[0] in TURN_KEY,
                    "turn session requires exactly one reviewed a/d key")
            require(type(turn_hold) is int and 20 <= turn_hold <= 150,
                    "turn session hold is invalid")
            require(session.get("goal") is None and session.get("calibrationProfile") is None,
                    "turn session cannot contain a goal or calibration profile")
        elif mode == "movement":
            profile = load(Path(session["calibrationProfile"]))
            if session.get("afterTurnResult") is not None:
                require_post_turn_calibration(
                    Path(session["afterTurnResult"]), Path(session["calibrationProfile"]))
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
                distance = math.hypot(gx, gz)
                require(distance > .30, "1d goal is already within arrival tolerance")
                require(0 < alpha <= 2.5 and residual <= .05 and gx * dx + gz * dz > 0,
                        "1d goal is not a positive aligned bounded calibrated displacement")
                best_after_pulse = min(math.hypot(
                    gx - vector.dx_per_ms * hold,
                    gz - vector.dz_per_ms * hold,
                )
                    for hold in range(20, 151))
                require(distance - best_after_pulse >= .03,
                        "no bounded 1d pulse makes useful progress")
        lease.check(); lease.heartbeat(); host.status(require_armed=False)
        # A fast-scoped reader can spend several seconds waiting for a fresh
        # anchor. Do that while disarmed for the one-pulse 1d calibration, then
        # preserve a short independent post-arm check before any input.
        short_calibration = mode == "calibration" and dimension == "1d"
        if short_calibration:
            prearm_ready = feedback.wait_action_ready(
                timeout_seconds=PREARM_ACTION_READY_TIMEOUT_SECONDS,
                minimum_fast_anchor_remaining_milliseconds=
                    PREARM_FAST_ANCHOR_REMAINING_MILLISECONDS)
            initial = _require_action_ready_sample(initial, prearm_ready)
            samples[-1] = initial.to_dict()
            lease.check(); lease.heartbeat(); host.status(require_armed=False)
        host.arm(session["capture"]["capture"], review["note"], output / "arm.private.json")
        started = clock()
        if mode == "turn":
            require(clock() - started <= 12, "elapsed budget")
            lease.check(); lease.heartbeat()
            ready = feedback.wait_action_ready(timeout_seconds=ACTION_READY_TIMEOUT_SECONDS)
            require(clock() - started <= 12, "elapsed budget")
            lease.check(); lease.heartbeat(); host.status(require_armed=True)
            initial = _require_action_ready_sample(initial, ready)
            samples[-1] = initial.to_dict()
            action = MovementAction(turn_keys[0], turn_hold, 0, 0)
            response = host.action(action, output / "action-1.json")
            _result, completed = _action_result(response)
            observed = _result.get("observedKeyHoldMilliseconds")
            require(type(observed) in (int, float) and math.isfinite(float(observed))
                    and 0 < float(observed) <= 250
                    and abs(float(observed) - turn_hold) <= max(25.0, turn_hold * .25),
                    "turn measured hold is missing or drifted")
            after = _require_advancing(initial,
                feedback.wait_after(completed, initial,
                                    timeout_seconds=ACTION_FEEDBACK_TIMEOUT_SECONDS))
            samples.append(after.to_dict())
            planar = planar_distance(_position(initial), _position(after))
            vertical = abs(_position(after).y - _position(initial).y)
            require(clock() - started <= 12, "elapsed budget")
            require(planar <= .05, "turn produced excessive planar displacement")
            require(vertical <= .75, "turn produced excessive vertical displacement")
            actions.append({"index": 1, "decision": asdict(action), "result": response,
                            "before": initial.to_dict(), "after": after.to_dict()})
            result_payload = {"mode": mode, "status": "turn-input-completed",
                              "turnKey": turn_keys[0], "holdMs": turn_hold,
                              "observedKeyHoldMilliseconds": float(observed),
                              "planarDisplacement": planar,
                              "verticalDisplacement": vertical,
                              "headingClaimed": False,
                              "profileInvalidationScope":
                                  "explicit-after-turn-result-chain-only",
                              "nextStep": "review a fresh screenshot before forward calibration"}
            success = True
        elif mode == "calibration":
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
                lease.check(); lease.heartbeat()
                ready = feedback.wait_action_ready(timeout_seconds=(
                    1.5 if short_calibration and index == 1
                    else ACTION_READY_TIMEOUT_SECONDS))
                require(clock() - started <= 12, "elapsed budget")
                lease.check(); lease.heartbeat(); host.status(require_armed=True)
                prior = _require_action_ready_sample(prior, ready)
                samples[-1] = prior.to_dict()
                action = MovementAction(key, calibration_hold_ms, 0, 0)
                response = host.action(action, output / f"action-{index}.json")
                _result, completed = _action_result(response)
                observed = _result.get("observedKeyHoldMilliseconds")
                require(type(observed) in (int, float) and math.isfinite(float(observed))
                        and abs(float(observed) - calibration_hold_ms)
                        <= max(25.0, calibration_hold_ms * .25),
                        "calibration measured hold is missing or drifted")
                measured_hold_ms = round(float(observed))
                require(20 <= measured_hold_ms <= 150,
                        "calibration measured hold exceeds supported bounds")
                after = _require_advancing(prior,
                    feedback.wait_after(completed, prior,
                                        timeout_seconds=ACTION_FEEDBACK_TIMEOUT_SECONDS))
                samples.append(after.to_dict())
                calibrations[key] = calibrate_displacement(key, _position(prior), _position(after), measured_hold_ms)
                actions.append({"index": index, "decision": asdict(action), "result": response,
                                "before": prior.to_dict(), "after": after.to_dict()})
                prior = after
                # The next iteration checks the 12-second action budget before
                # another input. Accept bounded feedback after the final key
                # has already been released; it cannot extend action authority.
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
                lease.check(); lease.heartbeat()
                ready = feedback.wait_action_ready(timeout_seconds=ACTION_READY_TIMEOUT_SECONDS)
                elapsed = clock() - started
                require(elapsed <= 12, "elapsed budget")
                lease.check(); lease.heartbeat(); host.status(require_armed=True)
                prior = _require_action_ready_sample(prior, ready)
                samples[-1] = prior.to_dict()
                if controller.action_count == 0:
                    # Initial anchor acquisition is no-input waiting; the action
                    # budget begins at the first actual movement decision.
                    started = clock()
                    elapsed = 0.0
                decision = controller.decide(_position(prior), elapsed)
                if decision is None:
                    require(controller.feedback_iterations >= 1,
                            "arrival is not eligible without advancing post-action feedback")
                    require(settles == 0, "arrival requires exactly one no-input confirmation")
                    lease.check(); lease.heartbeat()
                    _stop_and_verify(host, output); released = True
                    settle = _require_advancing(prior,
                        feedback.wait_next(prior, timeout_seconds=3.0))
                    require(planar_distance(_position(settle), goal) <= controller.tolerance,
                            "arrival settle left tolerance")
                    samples.append(settle.to_dict())
                    controller.confirm_released_settle(_position(settle), _position(prior))
                    prior = settle; settles += 1
                    require(controller.status == "arrived", "arrival did not confirm")
                    continue
                response = host.action(decision, output / f"action-{len(actions)+1}.json")
                _result, completed = _action_result(response)
                after = _require_advancing(prior,
                    feedback.wait_after(completed, prior,
                                        timeout_seconds=ACTION_FEEDBACK_TIMEOUT_SECONDS))
                samples.append(after.to_dict()); controller.record_feedback(_position(after), clock() - started)
                actions.append({"index": len(actions)+1, "decision": asdict(decision),
                                "result": response, "before": prior.to_dict(), "after": after.to_dict()})
                prior = after
                if controller.status == "confirming-arrival" and controller.feedback_iterations >= 1:
                    lease.check(); lease.heartbeat()
                    _stop_and_verify(host, output); released = True
                    settle = _require_advancing(prior,
                        feedback.wait_next(prior, timeout_seconds=3.0))
                    require(planar_distance(_position(settle), goal) <= controller.tolerance,
                            "arrival settle left tolerance")
                    samples.append(settle.to_dict())
                    controller.confirm_released_settle(_position(settle), _position(prior))
                    prior = settle; settles += 1
                    require(controller.status == "arrived", "arrival did not confirm")
            require(controller.status == "arrived" and settles == 1
                    and controller.feedback_iterations >= 1,
                    "arrival lacks advancing post-action feedback and a distinct released settle")
            result_payload = {"mode": mode, "status": "arrived",
                              "movementDimension": dimension, "goal": session["goal"],
                              "actions": controller.action_count, "totalHoldMs": controller.total_hold_ms,
                              "feedbackIterations": controller.feedback_iterations,
                              "settles": settles, "arrivalObservations": 2}
            success = True
        return {"success": True, **result_payload, "actionEvidence": actions, "samples": samples}
    finally:
        session_failed = sys.exc_info()[0] is not None
        stop_failed = False
        try:
            if not released:
                _stop_and_verify(host, output); released = True
        except BaseException:
            stop_failed = True
            raise
        finally:
            try:
                lease.finish("succeeded" if success and released else "failed",
                             [str(output.resolve()), "reviewed bounded movement session"])
            except QueueError:
                if not (session_failed or stop_failed):
                    raise


def _require_key_hold_timing(response: dict, key: str, planned_ms: int) -> float:
    """Reject a completed input whose observed hold differs materially from its plan."""
    action = response.get("action")
    require(isinstance(action, dict) and action.get("keys") == [key]
            and action.get("holdMilliseconds") == planned_ms,
            "action receipt does not match reviewed key and hold")
    events = response.get("inputEvents")
    require(isinstance(events, list), "action key timing evidence is missing")
    downs = [event for event in events if isinstance(event, dict)
             and event.get("kind") == "keyDownInserted"]
    ups = [event for event in events if isinstance(event, dict)
           and event.get("kind") == "keyUpInserted"]
    require(len(downs) == len(ups) == 1
            and downs[0].get("value") == ups[0].get("value") == key,
            "action key timing evidence is incomplete or ambiguous")
    down, up = downs[0].get("elapsedMilliseconds"), ups[0].get("elapsedMilliseconds")
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (down, up)) and 0 <= down < up,
            "action key timing evidence is invalid")
    observed_ms = up - down
    tolerance_ms = max(25.0, planned_ms * .25)
    require(abs(observed_ms - planned_ms) <= tolerance_ms
            and observed_ms <= 250,
            f"action key hold timing drifted: planned={planned_ms}ms observed={observed_ms:.1f}ms")
    return observed_ms


class LiveHostAdapter:
    def __init__(self, pinned: PinnedHost, client: ControlClient,
                 expected_capture_id: str | None = None):
        self.pinned, self.client = pinned, client
        self.expected_capture_id = expected_capture_id
    def status(self, **kwargs): return self.pinned.status(**kwargs)
    def arm(self, capture, note, output):
        return _arm(self.client, Path(capture), note, Path(output),
                    expected_capture_id=self.expected_capture_id)
    def action(self, decision, output):
        response = _action(self.client, SimpleNamespace(
            arm=Path(output).parent / "arm.private.json", keys=decision.key,
            hold_ms=decision.hold_ms, mouse_button=None, dx=0, dy=0, wheel=0,
            click_target=None, output=Path(output)))
        result = response["result"]
        if result.get("result", {}).get("deliverySucceeded") is True:
            result["observedKeyHoldMilliseconds"] = _require_key_hold_timing(
                result, decision.key, decision.hold_ms)
        return result
    def stop(self): return self.client.request("/api/stop", method="POST", payload={})


def validate_session_pins(session: dict):
    require(sha(Path(session["hostPlan"])) == session["hostPlanSha256"]
            and sha(Path(session["hostReceipt"])) == session["hostReceiptSha256"]
            and sha(Path(session["feedbackPin"])) == session["feedbackPinSha256"], "session pin changed")
    capture = session.get("capture")
    require(isinstance(capture, dict)
            and isinstance(capture.get("capture"), str)
            and isinstance(capture.get("image"), str)
            and isinstance(session.get("captureMetadataSha256"), str)
            and isinstance(session.get("captureImageSha256"), str),
            "reviewed capture pin missing")
    require(sha(Path(capture["capture"])) == session["captureMetadataSha256"]
            and sha(Path(capture["image"])) == session["captureImageSha256"],
            "reviewed capture artifact changed")
    if session["mode"] == "movement":
        require(sha(Path(session["calibrationProfile"])) == session.get("calibrationProfileSha256"),
                "calibration profile changed")
        if session.get("afterTurnResult") is not None:
            require(sha(Path(session["afterTurnResult"])) == session.get("afterTurnResultSha256"),
                    "turn result changed")


def run_reviewed(session_path: Path, review_path: Path, output: Path) -> dict:
    session_path = Path(session_path).resolve(strict=True); session = load(session_path)
    session["sessionPlanSha256"] = sha(session_path)
    review = load(Path(review_path).resolve(strict=True))
    validate_session_pins(session)
    _require_feedback_target(session, load(Path(session["feedbackPin"])))
    grant = load(Path(session["privateGrant"]), limit=8192)
    require(set(grant) == {"request_id", "token"} and grant["request_id"] == session["lease"]["request_id"],
            "private grant differs from session")
    pinned = open_host(Path(session["hostPlan"]))
    reviewed_target = {key: session["target"][key] for key in
                       ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")}
    if isinstance(pinned, ManagedPinnedHost):
        require(pinned.plan["target"] == reviewed_target,
                "managed host plan target differs from reviewed session")
    pinned.target = reviewed_target
    queue = LiveQueueLease(AccessQueue(pinned.plan["database"]), grant["request_id"], grant["token"],
                           pinned.plan["resource"])
    client = ControlClient(pinned.config, access=grant)
    from scripts.movement_feedback import PinnedFeedback
    feedback = PinnedFeedback(load(Path(session["feedbackPin"])), Path(output).resolve() / "feedback")
    result = execute_armed_session(session=session, review=review, output=Path(output),
             host=LiveHostAdapter(pinned, client, expected_capture_id=session["capture"]["captureId"]), lease=queue, feedback=feedback)
    save(Path(output) / "result.json", sanitized(result))
    return sanitized(result)


def add_quick_review(result: dict, *, detail_crop: tuple[int, int, int, int] | None = None) -> dict:
    """Attach a non-authoritative image and exact review pins to one prepared session.

    The successful preparation and queue lease remain intact if optional image
    delivery fails. Native arming still rechecks the original capture and age.
    """
    enriched = dict(result)
    try:
        from scripts.quick_review_capture import preview, review_pair
        session_path = Path(result["sessionPlan"])
        session = load(session_path)
        capture = session["capture"]
        metadata = load(Path(capture["capture"]))
        captured_at = datetime.fromisoformat(metadata["capturedAtUtc"].replace("Z", "+00:00"))
        require(captured_at.tzinfo is not None, "invalid-review-capture-time")
        max_age = metadata["reviewExpiresInSeconds"]
        require(type(max_age) is int and 0 < max_age <= MAX_CAPTURE_REVIEW_SECONDS,
                "invalid-review-window")
        deadline = captured_at + timedelta(seconds=max_age)
        remaining = max(0, math.ceil((deadline - utc_now()).total_seconds()))
        screen, digest = Path(capture["image"]), session["captureImageSha256"]
        detail = None
        if detail_crop is not None:
            paired = review_pair(screen, digest, detail_crop)
            image, detail = paired["fullFrame"], paired["detail"]
        else:
            try:
                image = preview(screen, digest, compact=True)
            except TypeError as error:
                if "unexpected keyword argument 'compact'" not in str(error):
                    raise
                image = preview(screen, digest)
            except ValueError as error:
                if str(error) != "preview-too-large":
                    raise
                image = preview(screen, digest)
        enriched["quickReview"] = {
            "status": "ready",
            "sessionId": session["sessionId"],
            "sessionPlanSha256": sha(session_path),
            "captureId": capture["captureId"],
            "captureImageSha256": session["captureImageSha256"],
            "capturedAtUtc": metadata["capturedAtUtc"],
            "reviewMaxAgeSeconds": max_age,
            "reviewDeadlineUtc": iso(deadline),
            "reviewExpiresInSeconds": remaining,
            "preview": image,
        }
        if detail is not None:
            enriched["quickReview"]["detailPreview"] = detail
    except (OSError, ValueError, KeyError, TypeError, MovementSessionError) as error:
        enriched["quickReview"] = {
            "status": "unavailable",
            "reason": str(error)[:160],
        }
    return enriched


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    owner = prep.add_mutually_exclusive_group(required=True)
    owner.add_argument("--host-plan", type=Path, help="existing legacy controller plan")
    owner.add_argument("--managed-lab", choices=("lab1", "lab2"),
                       help="pin an already-ready on-demand managed controller")
    prep.add_argument("--feedback-pin", type=Path, required=True); prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--mode", choices=("calibration", "movement", "turn"), required=True)
    prep.add_argument("--dimension", choices=("1d", "2d"), default="2d")
    prep.add_argument("--keys", nargs="+", choices=tuple(sorted(ALL_KEY)), default=("w", "q"),
                      metavar="KEY")
    prep.add_argument("--goal", nargs=3, type=float, metavar=("X", "Y", "Z")); prep.add_argument("--calibration-profile", type=Path)
    prep.add_argument("--calibrated-displacements", type=float,
                      help="derive a 1d goal 1.5 through 2.5 measured displacements ahead")
    prep.add_argument("--turn-hold-ms", type=int, default=100,
                      help="single reviewed a/d turn pulse, from 20 through 150 ms")
    prep.add_argument("--calibration-hold-ms", type=int, default=150,
                      help="one reviewed w/q/s/e calibration pulse per key, from 20 through 150 ms")
    prep.add_argument("--quick-preview", action="store_true",
                      help="include a SHA-pinned compact full-frame preview and exact review pins")
    prep.add_argument("--review-detail-crop", nargs=4, type=int,
                      metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                      help="with --quick-preview, include one source-pinned readable detail crop")
    prep.add_argument("--after-turn-result", type=Path,
                      help="explicitly require calibration to start after this exact turn result; "
                           "turns outside this chain are not detected")
    run = sub.add_parser("run-reviewed"); run.add_argument("--session-plan", type=Path, required=True)
    run.add_argument("--review", type=Path, required=True); run.add_argument("--output", type=Path, required=True)
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "prepare":
        if args.review_detail_crop is not None and not args.quick_preview:
            raise MovementSessionError("--review-detail-crop requires --quick-preview")
        goal = Position(*args.goal) if args.goal else None
        result = prepare(args.host_plan, args.feedback_pin, args.output, args.mode, goal,
                         args.calibration_profile, tuple(args.keys), args.dimension,
                         args.calibrated_displacements, args.turn_hold_ms,
                         args.after_turn_result, args.managed_lab,
                         calibration_hold_ms=args.calibration_hold_ms)
        if args.quick_preview:
            result = add_quick_review(result, detail_crop=(
                tuple(args.review_detail_crop) if args.review_detail_crop is not None else None))
    else: result = run_reviewed(args.session_plan, args.review, args.output)
    print(json.dumps(sanitized(result), sort_keys=True)); return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (MovementSessionError, MovementError, MovementHalted) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr); raise SystemExit(1)
