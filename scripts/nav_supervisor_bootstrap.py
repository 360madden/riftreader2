"""Explicit single-owner navigation supervision; no live startup enable flag.

Construction is inert. start() owns a joinable watchdog thread; stop() requests
verified shutdown and reports a pending termination honestly. No worker input,
service, reconnect, authority migration or retry is automatically launched.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from copy import deepcopy
import math
import re
import threading

from scripts.nav_startup_preflight import qualify_startup
from scripts.nav_access_queue import QueueDispatchPolicy, QueueError
from scripts.nav_control_watchdog import LeaseWatchdog


class CompositionError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedAuthority:
    resource: str
    epoch: str
    fingerprint: str
    watchdog: LeaseWatchdog


def prepare_authority(session, queue, resource, journal, *, reconciliation=None):
    """Prepare one blocked resource from an already initialized authority.

    The session's preparation boundary excludes concurrent cleanup/composition.
    The database registration rejects an existing row in the same transaction,
    not after a separately observed check. Failures never clear suspension.
    """
    try:
        with session.preparation_boundary():
            if not session.wait_controls_idle(2):
                raise CompositionError("prior control requests have not settled")
            proposal = qualify_startup(session, resource)
            if session.closed:
                raise CompositionError("session disconnected during preparation")
            if reconciliation is None:
                registered = queue.register(resource, proposal.epoch, require_absent=True)
            else:
                if not isinstance(reconciliation, dict) or set(reconciliation) != {"expected", "receipt"}:
                    raise CompositionError("invalid reconciliation claim")
                registered = queue.reconcile_resource(resource, proposal.epoch,
                    reconciliation["expected"], reconciliation["receipt"])
            if registered.get("blocked") != 1:
                raise CompositionError("registered resource was not blocked")
            policy = QueueDispatchPolicy(queue, {resource: proposal.epoch})
            session.dispatch_policy = policy
            watchdog = LeaseWatchdog(queue, session, resource, proposal.identity, journal)
            if session.closed:
                raise CompositionError("session disconnected during preparation")
            return PreparedAuthority(resource, proposal.epoch, proposal.fingerprint, watchdog)
    except CompositionError:
        raise
    except Exception:
        # Do not expose transport/database exception payloads. A failed claimant
        # must not suspend somebody else's already installed policy.
        raise CompositionError("authority preparation refused; inspect existing ownership") from None


def _seconds(value, name, low, high):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise CompositionError(name + " is outside the supported finite range")
    return value


class _SupervisedPolicy:
    """Keep send admission closed until verified readiness, and after runner exit."""
    def __init__(self, policy, owner):
        self._policy = policy
        self._owner = owner
        self.queue = policy.queue

    @property
    def resource_epochs(self):
        return self._policy.resource_epochs

    @contextmanager
    def guard(self, operation, access):
        with self._policy.guard(operation, access) as admit:
            if admit is None:  # STOP/release/status remain available at all times.
                yield None
            else:
                def check():
                    if not self._owner._permits_dispatch():
                        raise QueueError("supervisor is not running; no dispatch authorized")
                    return admit()
                yield check


class OwnedSupervisor:
    """One resource and pinned session for one explicit, non-restartable lifecycle.

    Normal host composition does not construct this object yet. The caller must
    integrate every manual/legacy controller before using it for live ownership.
    A start timeout requests shutdown; a stop timeout leaves the thread owned and
    joinable, never pretends the guest is released or the thread has terminated.
    """
    def __init__(self, session, queue, resource, journal, *, interval_seconds=.1, reconciliation=None):
        if not isinstance(resource, str) or not re.fullmatch(r"vm:[a-z0-9][a-z0-9._/-]{0,120}", resource):
            raise CompositionError("one valid VM resource is required")
        self.interval = _seconds(interval_seconds, "interval", .05, 1)
        self._reconciliation = deepcopy(reconciliation)
        self.session = session
        self.queue = queue
        self.resource = resource
        self.journal = journal
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._thread_started = False
        self._prepared = None
        self._state = "new"
        self._failure = None
        self._initial_verified = False
        self._shutdown_verified = False

    def status(self):
        """Read-only process-local lifecycle snapshot, not a fresh guest observation."""
        with self._lock:
            alive = self._thread_started and self._thread.is_alive()
            return {"state": self._state, "resource": self.resource,
                    "epoch": self._prepared.epoch if self._prepared else None,
                    "threadAlive": bool(alive),
                    "terminationPending": bool(alive and self._stop_event.is_set()),
                    "initialCleanupVerified": self._initial_verified,
                    "shutdownStopVerified": self._shutdown_verified,
                    "errorCode": self._failure}

    def _permits_dispatch(self):
        with self._lock:
            return (self._state == "running" and not self._stop_event.is_set()
                    and self._thread_started and self._thread.is_alive())

    def start(self, *, timeout_seconds=10):
        timeout = _seconds(timeout_seconds, "start timeout", .01, 60)
        with self._lock:
            if self._state != "new":
                raise CompositionError("supervisor is single-use; inspect its current state")
            self._state = "starting"
            try:
                self._thread = threading.Thread(target=self._run, name="rr2-navigation-supervisor",
                                                daemon=False)
                self._thread.start()
                self._thread_started = True
            except Exception:
                self._state = "blocked"
                self._failure = "thread-start-failed"
                raise CompositionError("supervisor thread could not start") from None
        if not self._ready.wait(timeout):
            self._request_stop(failure="startup-timeout")
            raise CompositionError("supervisor startup timed out; inspect/join shutdown, do not retry")
        with self._lock:
            if (self._state != "starting" or not self._initial_verified
                    or self._stop_event.is_set() or not self._thread.is_alive()):
                raise CompositionError("supervisor did not reach verified readiness; inspect shutdown")
            # Only this successful start caller opens admission. A late worker
            # completion after the caller timed out cannot publish running.
            self._state = "running"
        return self.status()

    def _request_stop(self, *, failure=None):
        with self._lock:
            if failure is not None and self._failure is None:
                self._failure = failure
            self._stop_event.set()
            if self._state == "new":
                self._state = "stopped"
            elif self._state not in ("stopped", "blocked"):
                self._state = "stopping"
            prepared = self._prepared
        # No global/owner lock across control-state or transport work. An owner
        # that never prepared a session must not interfere with an existing owner.
        if prepared is not None:
            self.session.suspend_controls()

    def stop(self, *, timeout_seconds=10):
        timeout = _seconds(timeout_seconds, "stop timeout", .01, 60)
        self._request_stop()
        with self._lock:
            thread = self._thread if self._thread_started else None
        if thread is not None:
            if thread is threading.current_thread():
                raise CompositionError("supervisor cannot join itself")
            thread.join(timeout)
        return self.status()

    def _run(self):
        prepared = None
        runner_boundary = ExitStack()
        try:
            prepared = prepare_authority(self.session, self.queue, self.resource, self.journal,
                                         reconciliation=self._reconciliation)
            with self._lock:
                self._prepared = prepared
            policy = _SupervisedPolicy(self.session.dispatch_policy, self)
            self.session.dispatch_policy = policy
            # Reuse the watchdog's runner exclusion instead of permitting a second
            # owned loop to call it concurrently. tick/shutdown still serialize I/O.
            runner_boundary.enter_context(prepared.watchdog.runner_boundary())
            if self._stop_event.is_set():
                return
            result = prepared.watchdog.tick()
            if result.get("state") != "cleaned" or result.get("cleanupPublished") is not True:
                with self._lock:
                    self._failure = self._failure or "initial-cleanup-blocked"
                return
            self.journal.append("nav-supervisor-readiness/1", {
                "resource": self.resource, "epoch": prepared.epoch,
                "fingerprint": prepared.fingerprint, "initialCleanupReceipt": result["receipt"],
                "decision": "cleanup-verified-pending-start-admission"})
            with self._lock:
                if self._stop_event.is_set():
                    return
                self._initial_verified = True
            self._ready.set()
            while not self._stop_event.wait(self.interval):
                result = prepared.watchdog.tick()
                if result.get("state") not in ("idle", "cleaned"):
                    with self._lock:
                        self._failure = "watchdog-blocked"
                    break
        except BaseException:
            with self._lock:
                self._failure = self._failure or "supervisor-operation-failed"
        finally:
            with self._lock:
                if self._state not in ("blocked", "stopped"):
                    self._state = "stopping"
                self._stop_event.set()
            if prepared is not None:
                # Exit always closes local admission; the watchdog quarantines the
                # resource and does NOT publish it free when supervision is gone.
                self.session.suspend_controls()
                try:
                    result = prepared.watchdog.shutdown()
                    verified = result.get("stopVerified") is True
                    with self._lock:
                        self._shutdown_verified = verified
                        if not verified:
                            self._failure = self._failure or "shutdown-unverified"
                except BaseException:
                    with self._lock:
                        self._failure = self._failure or "shutdown-unverified"
                finally:
                    runner_boundary.close()
                    self.session.suspend_controls()
            with self._lock:
                self._state = "blocked" if self._failure else "stopped"
            self._ready.set()
