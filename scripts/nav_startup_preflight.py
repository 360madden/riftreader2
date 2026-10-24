"""Read-only startup identity qualification. Does not create queues or enable controls.

Call only on a freshly authenticated native session. The caller must separately
install a policy, initialize/verify the authority, and supervise its watchdog.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from scripts.nav_control_watchdog import bind_identity, resource_epoch, WatchdogError


class StartupPreflightError(ValueError):
    pass


@dataclass(frozen=True)
class QualifiedStartup:
    resource: str
    epoch: str
    fingerprint: str
    identity: dict


def qualify_startup(session, resource: str) -> QualifiedStartup:
    """Collect two matching fresh status observations without mutating authority.

    A qualified result is only a proposal. It is not permission to arm, to grant
    a lease, or to activate a watchdog.
    """
    if not isinstance(resource, str) or not re.fullmatch(r"vm:[a-z0-9][a-z0-9._/-]{0,120}", resource):
        raise StartupPreflightError("invalid resource name")
    if session.closed or session.dispatch_policy is not None:
        raise StartupPreflightError("startup needs a connected, uncoordinated session")
    try:
        first_summary = session.summary()
        first = session.request("status", {})
        second_summary = session.summary()
        second = session.request("status", {})
        final_summary = session.summary()
        # Sequence counters legitimately advance on every status request.
        # Compare durable session/VM identity, not command sequence or source metadata.
        stable = lambda summary: (summary.get("connected"), summary.get("instanceId"),
                                  summary.get("machineName"), summary.get("vmIdentity"))
        if session.closed or not (stable(first_summary) == stable(second_summary) == stable(final_summary)):
            raise StartupPreflightError("session changed during startup")
        one = bind_identity(first_summary, first)
        two = bind_identity(final_summary, second)
        if one != two:
            raise StartupPreflightError("target changed during startup")
        for value in (first, second):
            if (value.get("armed") is not False or value.get("busy") is not False
                    or value.get("recoveryRequired") is not False
                    or value.get("desktopInputsDown") != []):
                raise StartupPreflightError("guest is not idle and released")
        # A stale target can be observed consistently; this is not independent
        # authentication of VMware, game memory, desktop focus, or guest state.
        epoch = resource_epoch(one)
        fingerprint = hashlib.sha256(json.dumps(one, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return QualifiedStartup(resource, epoch, fingerprint, one)
    except StartupPreflightError:
        raise
    except (WatchdogError, OSError, TimeoutError, ValueError, RuntimeError):
        raise StartupPreflightError("startup identity or status unavailable") from None
