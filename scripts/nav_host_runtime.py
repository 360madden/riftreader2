"""Opt-in production composition. One host thread owns one VM and durable queue.

poll() is called by the host loop, not a detached coordinator thread. Only the
existing OwnedSupervisor owns a watchdog thread. Reconnect never replays work.
"""
from copy import deepcopy
import hashlib
import json
import re
import threading
import uuid

from scripts.nav_supervisor_bootstrap import OwnedSupervisor, CompositionError


class HostCoordinator:
    def __init__(self, gateway, queue, resource, journal, *, reconcile_existing=False):
        if type(reconcile_existing) is not bool:
            raise CompositionError("reconcile-existing must be boolean")
        if not isinstance(resource, str) or not re.fullmatch(r"vm:[a-z0-9][a-z0-9._/-]{0,120}", resource):
            raise CompositionError("one exact VM resource is required")
        if not gateway.require_supervisor or not gateway.exclusive_console:
            raise CompositionError("coordinated host requires denied-first console exclusion")
        reservation = gateway.vm_guard.console_status()
        if not reservation["held"] or reservation["closing"] or reservation["faulted"]:
            raise CompositionError("coordinated host requires an acquired console reservation")
        # Validate the authority now. Never silently create, replace or reset it.
        queue.status()
        self.gateway, self.queue, self.resource, self.journal = gateway, queue, resource, journal
        self.reconcile_existing = reconcile_existing
        self._thread = threading.current_thread()
        self._lock = threading.Lock()
        self._owner = None
        self._attempted = None
        self._known_resource = False
        self._stopping = False
        self._shutdown_verified = True  # No supervisor or input has been started yet.
        self._state = "waiting"
        self._error = None
        self._instance = uuid.uuid4().hex
        self._connection = 0

    def _on_thread(self):
        if threading.current_thread() is not self._thread:
            raise CompositionError("host lifecycle must run on its console-owning thread")

    def _set(self, state, error=None):
        with self._lock:
            self._state, self._error = state, error

    def status(self):
        """Read-only local lifecycle view; no guest I/O or grant credentials."""
        with self._lock:
            owner, state, error = self._owner, self._state, self._error
            stopping, shutdown = self._stopping, self._shutdown_verified
            connection = self._connection
        value = owner.status() if owner is not None else None
        if state == "ready" and (value is None or value["state"] != "running"
                or not value["threadAlive"] or owner.session.closed):
            state, error = "blocked", "supervisor-not-running"
        return {"state": state, "resource": self.resource, "hostInstance": self._instance,
                "connection": connection, "errorCode": error, "supervisor": value,
                "shutdownRequested": stopping, "shutdownVerified": shutdown,
                "safeToClose": bool(stopping and shutdown and (value is None or not value["threadAlive"]))}

    def _stop_owner(self, timeout):
        owner = self._owner
        if owner is None:
            return True
        outcome = owner.stop(timeout_seconds=timeout)
        with self._lock:
            self._known_resource |= outcome["epoch"] is not None
            if not outcome["threadAlive"]:
                self._shutdown_verified = outcome["shutdownStopVerified"]
        return not outcome["threadAlive"]

    def poll(self):
        self._on_thread()
        if self._stopping:
            return self.status()
        reservation = self.gateway.vm_guard.console_status()
        if not reservation["held"] or reservation["closing"] or reservation["faulted"]:
            if self._owner is not None:
                self._owner.session.suspend_controls()
                self._stop_owner(.01)
            self._set("blocked", "console-reservation-unavailable")
            return self.status()
        try:
            current = self.gateway.session()
        except RuntimeError:
            current = None
        owner = self._owner
        if owner is not None and current is owner.session and not current.closed:
            status = owner.status()
            if status["state"] == "running" and status["threadAlive"]:
                self._set("ready")
            elif self._state != "blocked":
                self._set("blocked", status["errorCode"] or "supervisor-not-running")
            return self.status()  # Never auto-retry this same session.
        if owner is not None:
            self._set("draining")
            if not self._stop_owner(.01):
                return self.status()
            with self._lock:
                self._owner = None
        if current is None:
            self._set("waiting")
            return self.status()
        if current is self._attempted:
            return self.status()
        self._attempted = current
        current.suspend_controls()
        self._connection += 1
        self._set("starting")
        try:
            # Revalidate host-side VM identity before requesting guest statuses.
            self.gateway.vm_guard.request(current.vm_identity, lambda: None, fast=True)
            snapshot = self.queue.status()
            row = next((item for item in snapshot["resources"] if item["name"] == self.resource), None)
            reconciliation = None
            if row is not None:
                if not self._known_resource and not self.reconcile_existing:
                    raise CompositionError("existing authority requires explicit startup reconciliation")
                transition = {"hostInstance": self._instance, "connection": self._connection,
                              "resource": self.resource, "expected": deepcopy(row),
                              "newSession": current.summary(), "previousSupervisorJoined": self._known_resource,
                              "mode": "reconnect" if self._known_resource else "explicit-startup"}
                receipt = "nav-rebind:" + hashlib.sha256(json.dumps(
                    transition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.journal.append("nav-host-reconciliation/1", {"receipt": receipt, **transition})
                reconciliation = {"expected": row, "receipt": receipt}
            owner = OwnedSupervisor(current, self.queue, self.resource, self.journal,
                                    reconciliation=reconciliation)
            with self._lock:
                self._owner = owner
                self._shutdown_verified = False
            outcome = owner.start()
            # An intervening target/session change must not advertise readiness.
            self.gateway.vm_guard.request(current.vm_identity, lambda: None, fast=True)
            if current.closed or self.gateway.session() is not current:
                raise CompositionError("session changed during supervisor startup")
            with self._lock:
                self._known_resource = True
            self._set("ready")
        except Exception:
            if self._owner is not None:
                self._stop_owner(.01)
            current.suspend_controls()
            self._set("blocked", "startup-reconciliation-refused")
        return self.status()

    def stop(self, *, timeout_seconds=10):
        """Retain ownership on unverified or pending cleanup; caller decides exit."""
        self._on_thread()
        with self._lock:
            self._stopping = True
        self._set("stopping")
        finished = self._stop_owner(timeout_seconds)
        if not finished:
            self._set("stopping", "supervisor-termination-pending")
        elif not self._shutdown_verified:
            self._set("blocked", "shutdown-release-unverified")
        else:
            self._set("stopped")
        return self.status()
