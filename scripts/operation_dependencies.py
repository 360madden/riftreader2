"""Minimal fail-closed on-demand dependency composition.

Adapters supply read-only health probes and only those recovery actions that
are independently authorized and session-safe. No input or VM lifecycle here.
"""
from dataclasses import dataclass
from typing import Callable


class DependencyUnavailable(RuntimeError):
    def __init__(self, name, code):
        self.name, self.code = name, code
        super().__init__(f"{name}: {code}")


@dataclass(frozen=True)
class Dependency:
    name: str
    healthy: Callable[[], bool]
    recover: Callable[[], None] | None = None


def ensure_ready(dependencies):
    """Check ordered requirements; recover once, then check again, or fail."""
    ready = []
    for dependency in dependencies:
        name = dependency.name
        try:
            state = dependency.healthy()
        except Exception:
            raise DependencyUnavailable(name, "health-check-failed") from None
        if type(state) is not bool:
            raise DependencyUnavailable(name, "invalid-health-result")
        if not state:
            if dependency.recover is None:
                raise DependencyUnavailable(name, "recovery-not-available")
            try:
                dependency.recover()
            except Exception:
                raise DependencyUnavailable(name, "recovery-failed") from None
            try:
                restored = dependency.healthy()
            except Exception:
                raise DependencyUnavailable(name, "post-recovery-health-check-failed") from None
            if restored is not True:
                raise DependencyUnavailable(name, "not-ready-after-recovery")
        ready.append(name)
    return ready
