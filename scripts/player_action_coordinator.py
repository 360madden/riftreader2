"""Small local handoff state for movement, combat, and recovery actions.

The owning event loop serializes calls. Each action callback retains its
existing subsystem reservation and validates its release receipt against the
exact admitted target before returning it. Route checkpoints belong to playback.
"""
from __future__ import annotations

from copy import deepcopy


class ActionCoordinationError(RuntimeError):
    """The requested transition is not valid for the current local state."""


class PlayerActionCoordinator:
    ACTIONS = {"movement", "combat", "recovery"}
    CRITICAL_LATCHES = {"operator-stop", "death", "critical-unavailable",
                        "uncertain-release", "action-start-failed"}

    def __init__(self):
        self._active = None
        self._release = None
        self._releasing = False
        self._latch = None
        self._last_release = None
        self._run_id = 0
        self._revision = 0

    def snapshot(self):
        """Return CLI/state-friendly data without exposing callbacks."""
        return {
            "version": 1,
            "status": "latched" if self._latch else "active" if self._active else "idle",
            "activeAction": self._active,
            "latchReason": self._latch,
            "lastRelease": deepcopy(self._last_release),
            "runId": self._run_id,
            "revision": self._revision,
            "routeCheckpointPolicy": "external-unchanged",
            "coordinatorInputSent": False,
        }

    @staticmethod
    def _confirmed(receipt):
        if not isinstance(receipt, dict):
            return False
        evidence = [receipt.get(key) for key in ("releaseSucceeded", "allInputsReleased")
                    if key in receipt]
        if not evidence or any(value is not True for value in evidence):
            return False
        desktop = receipt.get("desktopInputsDown", [])
        return isinstance(desktop, list) and not desktop

    def _touch(self):
        self._revision += 1

    def _start(self, action, start, release):
        if action not in self.ACTIONS:
            raise ActionCoordinationError("unknown action owner")
        if self._active is not None:
            raise ActionCoordinationError(f"{self._active} already owns the action slot")
        if self._latch is not None:
            raise ActionCoordinationError(
                f"action coordinator is latched: {self._latch}; use Resume or a new run")
        if not callable(start) or not callable(release):
            raise TypeError("start and release callbacks are required")
        # Publish ownership before calling out: a synchronous callback cannot
        # re-enter and acquire a second logical action slot.
        self._active, self._release = action, release
        self._touch()
        try:
            start()
        except Exception:
            # The callback may have partially acquired its existing subsystem
            # reservation. Keep the owner and release callback available.
            self._latch = "action-start-failed"
            self._touch()
            raise
        return self.snapshot()

    def _release_active(self, reason, replacement=None):
        if self._releasing:
            raise ActionCoordinationError("action release already in progress")
        if self._active is None:
            raise ActionCoordinationError("no active action to release")
        callback = replacement or self._release
        self._releasing = True
        try:
            receipt = callback(reason)
        except Exception as exc:
            receipt = {"releaseSucceeded": False, "reason": str(exc),
                       "action": self._active}
        finally:
            self._releasing = False
        self._last_release = deepcopy(receipt)
        self._touch()
        if not self._confirmed(receipt):
            self._latch = "uncertain-release"
            self._touch()
            return False
        self._active, self._release = None, None
        self._touch()
        return True

    def new_run(self, start_movement, release_movement):
        """Explicitly start a new run; this is allowed to clear an idle latch."""
        if self._active is not None:
            raise ActionCoordinationError("release the active action before starting a new run")
        self._latch = None
        self._run_id += 1
        self._touch()
        return self._start("movement", start_movement, release_movement)

    def resume(self, start_movement, release_movement):
        """Explicitly Resume an idle latched route without touching its checkpoint."""
        if self._active is not None:
            raise ActionCoordinationError("release the active action before Resume")
        self._latch = None
        self._touch()
        return self._start("movement", start_movement, release_movement)

    def encounter(self, start_combat, release_combat):
        """Interrupt movement for an encounter, distinct from operator STOP."""
        if self._active != "movement" or self._latch is not None:
            raise ActionCoordinationError("an interruptible movement action is required")
        if not self._release_active("encounter-interrupt") or self._latch is not None:
            return self.snapshot()
        return self._start("combat", start_combat, release_combat)

    def combat_ready(self, start_movement, release_movement):
        """Finish an ordinary encounter and continue the unchanged route."""
        if self._active != "combat" or self._latch is not None:
            raise ActionCoordinationError("an active ready combat action is required")
        if not self._release_active("combat-complete") or self._latch is not None:
            return self.snapshot()
        return self._start("movement", start_movement, release_movement)

    def combat_needs_recovery(self, start_recovery, release_recovery):
        if self._active != "combat" or self._latch is not None:
            raise ActionCoordinationError("an active combat action is required")
        if not self._release_active("combat-to-recovery") or self._latch is not None:
            return self.snapshot()
        return self._start("recovery", start_recovery, release_recovery)

    def recovery_ready(self, start_movement, release_movement):
        """Continue ordinary travel after a ready, released recovery action."""
        if self._active != "recovery" or self._latch is not None:
            raise ActionCoordinationError("an active ready recovery action is required")
        if not self._release_active("recovery-complete") or self._latch is not None:
            return self.snapshot()
        return self._start("movement", start_movement, release_movement)

    def operator_stop(self):
        """Latch operator STOP; successful release does not implicitly Resume."""
        return self._halt("operator-stop")

    def critical(self, reason):
        """Latch death or unavailable critical state before attempting release."""
        if reason not in {"death", "critical-unavailable"}:
            raise ValueError("critical reason must be death or critical-unavailable")
        return self._halt(reason)

    def _halt(self, reason):
        if not self._releasing or self._latch is None:
            # A later STOP must not erase a confirmed death or missing critical
            # state. Only explicit Resume/new_run can clear that terminal latch.
            if self._latch not in {"death", "critical-unavailable"}:
                self._latch = reason
                self._touch()
        if self._active is not None and not self._releasing:
            self._release_active(reason)
        return self.snapshot()

    def retry_release(self, release):
        """Retry an uncertain release without clearing the latch or resuming."""
        if self._latch != "uncertain-release" or self._active is None:
            raise ActionCoordinationError("no uncertain active release to retry")
        self._release_active("explicit-release-retry", replacement=release)
        # Even successful cleanup remains latched until Resume/new_run.
        return self.snapshot()
