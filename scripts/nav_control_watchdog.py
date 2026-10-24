"""Pinned-session expiry and release verification; not automatically live-enabled.

A composition root supplies one registered VM resource, an exact native session,
its policy and a trusted evidence journal. Construction starts no thread and sends
no command. Tests use explicit ticks or an explicitly owned stoppable run loop.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import re
import threading
import time


class WatchdogError(ValueError):
    """Stable, payload-free failure code; no automatic command replay."""


def _finite_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value, name, maximum=4096):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or any(ord(character) < 32 for character in value)):
        raise WatchdogError("invalid-" + name)
    return value


def _integer(value, name, lower=1):
    if type(value) is not int or not lower <= value <= 2**63 - 1:
        raise WatchdogError("invalid-" + name)
    return value


def bind_identity(summary, status):
    """Validate/copy identity only; no live lookup, registration or authorization.

    Foreground is excluded so loss of focus never prevents STOP/release. Geometry,
    process epoch, executable, guest instance and VMware identity remain pinned.
    """
    if not isinstance(summary, dict) or not isinstance(status, dict):
        raise WatchdogError("invalid-identity")
    if summary.get("connected") is not True:
        raise WatchdogError("session-disconnected")
    instance = _text(summary.get("instanceId"), "instance", 128)
    machine = _text(summary.get("machineName"), "machine", 64)
    if status.get("instanceId") != instance:
        raise WatchdogError("guest-instance-mismatch")
    vm = summary.get("vmIdentity")
    target = status.get("target")
    if not isinstance(vm, dict) or not isinstance(target, dict):
        raise WatchdogError("missing-target-identity")
    vm_copy = {name: _text(vm.get(name), name) for name in ("image", "vmx", "logEpoch")}
    for name in ("pid", "listenerPid", "startTicks", "port"):
        vm_copy[name] = _integer(vm.get(name), name)
    if vm_copy["port"] > 65535 or vm_copy["pid"] != vm_copy["listenerPid"]:
        raise WatchdogError("invalid-vm-listener")
    target_copy = {name: _text(target.get(name), name) for name in (
        "machineName", "executablePath", "windowHandle", "executableSha256")}
    if target_copy["machineName"] != machine:
        raise WatchdogError("machine-mismatch")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", target_copy["executableSha256"]):
        raise WatchdogError("invalid-build-hash")
    if not re.fullmatch(r"0x[0-9a-fA-F]+", target_copy["windowHandle"]):
        raise WatchdogError("invalid-window-handle")
    for name in ("processId", "processStartUtcTicks", "clientWidth", "clientHeight"):
        target_copy[name] = _integer(target.get(name), name)
    for name in ("clientX", "clientY"):
        target_copy[name] = _integer(target.get(name), name, -(2**31))
    return {"instanceId": instance, "machineName": machine, "vmIdentity": vm_copy,
            "target": target_copy}


def resource_epoch(identity):
    return "nav-" + hashlib.sha256(_finite_json(identity).encode("utf-8")).hexdigest()


class LeaseWatchdog:
    """One pinned VM/session; cleanup of unrelated/shared-host resources is forbidden.

    tick() performs at most one STOP/verification sequence. Failed cleanup latches
    both this coordinator and the local session; retry=True is an explicit fresh
    cleanup attempt, never a replay of movement. No automatic rebinding/recovery.
    """
    def __init__(self, queue, session, resource, identity, journal, *,
                 monotonic=None, drain_timeout=2.0):
        if not isinstance(resource, str) or not re.fullmatch(r"vm:[a-z0-9][a-z0-9._/-]{0,120}", resource):
            raise WatchdogError("one-vm-resource-required")
        if type(drain_timeout) not in (int, float) or not 0 <= drain_timeout <= 5:
            raise WatchdogError("invalid-drain-timeout")
        self.queue = queue
        self.session = session
        self.resource = resource
        if not isinstance(identity, dict):
            raise WatchdogError("invalid-identity")
        self.identity = deepcopy(identity)
        # Revalidate supplied identity rather than trusting a hand-built dictionary.
        checked = bind_identity({"connected": True, **{key: self.identity.get(key) for key in (
            "instanceId", "machineName", "vmIdentity")}},
            {"instanceId": self.identity.get("instanceId"), "target": self.identity.get("target")})
        if checked != self.identity:
            raise WatchdogError("invalid-binding-fields")
        self.epoch = resource_epoch(checked)
        policy = session.dispatch_policy
        if (policy is None or policy.queue.path != queue.path
                or policy.resource_epochs != {resource: self.epoch}):
            raise WatchdogError("session-policy-mismatch")
        self.journal = journal
        self.monotonic = monotonic or time.monotonic
        self.drain_timeout = drain_timeout
        self._tick_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._fault = None
        self._shutdown = False
        self._local_identity()

    def _local_identity(self):
        summary = self.session.summary()
        policy = self.session.dispatch_policy
        if (policy is None or policy.queue.path != self.queue.path
                or policy.resource_epochs != {self.resource: self.epoch}):
            raise WatchdogError("session-policy-changed")
        if (summary.get("connected") is not True or self.session.closed
                or any(summary.get(key) != self.identity[key]
                       for key in ("instanceId", "machineName", "vmIdentity"))):
            raise WatchdogError("session-identity-changed")
        return summary

    def _snapshot(self):
        snapshot = self.queue.status()
        row = next((item for item in snapshot["resources"] if item["name"] == self.resource), None)
        if row is None or row["epoch"] != self.epoch:
            raise WatchdogError("resource-identity-changed")
        return row

    def _status(self):
        before = self._local_identity()
        status = self.session.request("status", {})
        after = self._local_identity()
        if before["vmIdentity"] != after["vmIdentity"] or bind_identity(after, status) != self.identity:
            raise WatchdogError("target-identity-changed")
        return status

    def _stop_observe(self):
        started = self.monotonic()
        self._status()  # Fresh target identity before sending release-only STOP.
        stopped = self.session.request("stop", {})
        if stopped.get("stopped") is not True or stopped.get("recoveryRequired") is not False:
            raise WatchdogError("stop-unconfirmed")
        if not self.session.wait_controls_idle(self.drain_timeout):
            raise WatchdogError("in-flight-controls-remain")
        status = self._status()
        if (status.get("armed") is not False or status.get("busy") is not False
                or status.get("recoveryRequired") is not False
                or status.get("desktopInputsDown") != []):
            raise WatchdogError("release-not-verified")
        elapsed = self.monotonic() - started
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed > 5:
            raise WatchdogError("cleanup-observation-expired")
        # Evidence concerns the pinned control session and sampled Windows input,
        # not gameplay response or ownership of arbitrary physical keyboard state.
        return {"stopped": True, "recoveryRequired": False, "armed": False,
                "busy": False, "desktopInputsDown": [], "inFlight": False}

    def _receipt(self, row, observed_ms, status, publish):
        record = {"schemaVersion": 1, "decision": "ready-for-queue-cleanup" if publish else "stopped-still-blocked",
                  "resource": self.resource, "epoch": self.epoch,
                  "generation": row["generation"], "holder": row["holder"],
                  "observedMs": observed_ms, "identity": deepcopy(self.identity), "observation": status}
        receipt = "nav-cleanup:" + hashlib.sha256(_finite_json(record).encode("utf-8")).hexdigest()
        self.journal.append("nav-control-cleanup/1", {"receipt": receipt, **record})
        return receipt

    def _fail(self, reason, *, try_stop=False):
        # Do not copy exception messages: they may contain private application data.
        self._fault = reason
        self.session.suspend_controls()
        try:
            self.queue.quarantine_resource(self.resource, self.epoch, "watchdog-fault")
        except Exception:
            pass  # Local suspension remains even when the database is unavailable.
        emergency_stop_verified = False
        if try_stop:
            try:
                with self.session.cleanup_boundary():
                    self._stop_observe()
                    emergency_stop_verified = True
            except Exception:
                pass
        try:
            self.journal.append("nav-control-cleanup-blocked/1", {
                "resource": self.resource, "epoch": self.epoch,
                "reason": reason, "emergencyStopVerified": emergency_stop_verified})
        except Exception:
            pass
        return {"state": "blocked", "reason": reason, "cleanupPublished": False,
                "explicitRetryRequired": True, "emergencyStopVerified": emergency_stop_verified}

    def _cleanup(self, row, *, publish=True):
        try:
            with self.session.cleanup_boundary() as permit:
                observation = self._stop_observe()
                observed_ms = self.queue.clock()
                if type(observed_ms) is not int:
                    raise WatchdogError("invalid-observation-clock")
                receipt = self._receipt(row, observed_ms, observation, publish)
                if not publish:
                    return {"state": "blocked", "reason": "watchdog-shutdown",
                            "cleanupPublished": False, "stopVerified": True, "receipt": receipt}
                self._local_identity()  # Receipt I/O must not hide an intervening disconnect.
                result = self.queue.cleanup(self.resource, self.epoch, row["generation"], observed_ms,
                                            receipt, stopped=True, released=True, in_flight=False)
                permit()
                self._fault = None
                return {"state": "cleaned", "cleanupPublished": True, "receipt": receipt,
                        "generation": result["generation"], "resource": self.resource}
        except Exception as error:
            code = str(error) if isinstance(error, WatchdogError) else "cleanup-failed"
            return self._fail(code)

    def tick(self, *, retry=False):
        if type(retry) is not bool:
            raise WatchdogError("invalid-retry-flag")
        if not self._tick_lock.acquire(blocking=False):
            return {"state": "busy", "cleanupPublished": False}
        try:
            if self._shutdown:
                return {"state": "blocked", "reason": "watchdog-shutdown", "cleanupPublished": False}
            if self._fault and not retry:
                return {"state": "blocked", "reason": self._fault, "cleanupPublished": False,
                        "explicitRetryRequired": True}
            try:
                self._local_identity()
                if self._fault:
                    self.queue.quarantine_resource(self.resource, self.epoch, "watchdog-fault")
                row = self._snapshot()  # Reconciles expiry even without a worker heartbeat.
            except Exception as error:
                code = str(error) if isinstance(error, WatchdogError) else "queue-unavailable"
                return self._fail(code, try_stop=True)
            if not row["blocked"]:
                return {"state": "idle", "cleanupPublished": False, "resource": self.resource}
            return self._cleanup(row)
        finally:
            self._tick_lock.release()

    def shutdown(self):
        # Called by the owned runner in finally. Never advertise a clean free resource
        # when this watchdog is no longer supervising it.
        with self._tick_lock:
            if self._shutdown:
                return {"state": "blocked", "reason": "watchdog-shutdown", "cleanupPublished": False}
            self._shutdown = True
            self.session.suspend_controls()
            try:
                row = self.queue.quarantine_resource(self.resource, self.epoch, "watchdog-shutdown")
                return self._cleanup(row, publish=False)
            except Exception:
                return self._fail("shutdown-unverified", try_stop=True)

    @contextmanager
    def runner_boundary(self):
        """Exclude a second loop; the owning caller must shut down before exit."""
        if not self._run_lock.acquire(blocking=False):
            raise WatchdogError("watchdog-already-running")
        try:
            yield
        finally:
            self._run_lock.release()

    def run(self, stop_event, *, interval_seconds=0.1):
        """Explicit owned loop; never auto-started or detached by this module."""
        if type(interval_seconds) not in (int, float) or not .05 <= interval_seconds <= 1:
            raise WatchdogError("invalid-watchdog-interval")
        if not isinstance(stop_event, threading.Event):
            raise WatchdogError("stop-event-required")
        with self.runner_boundary():
            try:
                while not stop_event.is_set():
                    self.tick()
                    stop_event.wait(interval_seconds)
            finally:
                self.shutdown()
