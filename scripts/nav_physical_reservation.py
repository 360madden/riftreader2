"""Offline-capable Windows reservation for one explicitly pinned physical RIFT process.

This is only a local exclusion primitive, NOT permission to send input. A future
supervisor must independently acquire a queue grant, review the target and
verify STOP/key release before releasing this reservation. The Local\\ namespace
excludes competing processes in the same interactive Windows logon session.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import os
import re
import socket
import threading
from typing import Callable


class PhysicalReservationError(ValueError):
    """Stable, non-sensitive refusal reason."""


@dataclass(frozen=True)
class PhysicalClientIdentity:
    machine_name: str
    process_id: int
    process_start_utc_ticks: int
    executable_sha256: str

    def __post_init__(self):
        if (not isinstance(self.machine_name, str)
                or not 1 <= len(self.machine_name) <= 64
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,63}", self.machine_name)):
            raise PhysicalReservationError("physical-identity-machine-invalid")
        if type(self.process_id) is not int or not 1 <= self.process_id <= 2147483647:
            raise PhysicalReservationError("physical-identity-pid-invalid")
        if (type(self.process_start_utc_ticks) is not int
                or not 1 <= self.process_start_utc_ticks <= 3155378975999999999):
            raise PhysicalReservationError("physical-identity-epoch-invalid")
        if (not isinstance(self.executable_sha256, str)
                or re.fullmatch(r"[a-f0-9]{64}", self.executable_sha256) is None):
            raise PhysicalReservationError("physical-identity-build-invalid")

    def require_local_host(self):
        if self.machine_name.casefold() != socket.gethostname().casefold():
            raise PhysicalReservationError("physical-identity-host-mismatch")


def mutex_name(identity: PhysicalClientIdentity) -> str:
    """Stable per host/PID/start epoch; deliberately NOT split by executable hash."""
    if not isinstance(identity, PhysicalClientIdentity):
        raise PhysicalReservationError("physical-identity-required")
    identity.require_local_host()
    scope = f"{identity.machine_name.casefold()}:{identity.process_id}:{identity.process_start_utc_ticks}"
    return "Local\\RiftReader2.PhysicalClient." + hashlib.sha256(scope.encode("utf-8")).hexdigest()[:32]


_registry_lock = threading.Lock()
_owned_names: set[str] = set()


class PhysicalClientReservation:
    """Non-reentrant, fail-closed Windows named mutex for one physical client.

    `revalidate` must independently observe the current host/PID/start/SHA and
    return PhysicalClientIdentity. Checked immediately after acquisition and
    by check() before each caller-controlled dispatch. This module does not
    read process memory, open sockets or send any gameplay input.
    """

    def __init__(self, identity: PhysicalClientIdentity,
                 revalidate: Callable[[], PhysicalClientIdentity]):
        if not isinstance(identity, PhysicalClientIdentity) or not callable(revalidate):
            raise PhysicalReservationError("physical-reservation-arguments-invalid")
        identity.require_local_host()
        self.identity = identity
        self.name = mutex_name(identity)
        self._revalidate = revalidate
        self._handle = None
        self._api = None
        self._owner_thread = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self):
        if os.name != "nt":
            raise PhysicalReservationError("physical-reservation-windows-required")
        if self.held:
            raise PhysicalReservationError("physical-reservation-already-held")
        with _registry_lock:
            if self.name in _owned_names:
                raise PhysicalReservationError("physical-reservation-busy")
            _owned_names.add(self.name)
        try:
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            api.CreateMutexW.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.WaitForSingleObject.restype = wintypes.DWORD
            api.ReleaseMutex.argtypes = [wintypes.HANDLE]
            api.ReleaseMutex.restype = wintypes.BOOL
            api.CloseHandle.argtypes = [wintypes.HANDLE]
            api.CloseHandle.restype = wintypes.BOOL
            handle = api.CreateMutexW(None, False, self.name)
            if not handle:
                raise PhysicalReservationError("physical-reservation-create-failed")
            self._api = api
            self._handle = handle
            outcome = api.WaitForSingleObject(handle, 0)
            if outcome == 0x102:
                raise PhysicalReservationError("physical-reservation-busy")
            if outcome == 0x80:
                # An abandoned owner may have left inputs down; a supervisor
                # must explicitly recover before this mutex is used for control.
                raise PhysicalReservationError("physical-reservation-abandoned")
            if outcome != 0:
                raise PhysicalReservationError("physical-reservation-wait-failed")
            self._owner_thread = threading.current_thread()
            self.check()
            return self
        except BaseException:
            if self._handle is not None:
                if self._owner_thread is not None:
                    self._api.ReleaseMutex(self._handle)
                self._api.CloseHandle(self._handle)
            self._handle = None
            self._api = None
            self._owner_thread = None
            with _registry_lock:
                _owned_names.discard(self.name)
            raise

    def check(self) -> PhysicalClientIdentity:
        if not self.held or threading.current_thread() is not self._owner_thread:
            raise PhysicalReservationError("physical-reservation-not-owned")
        try:
            current = self._revalidate()
        except Exception:
            raise PhysicalReservationError("physical-reservation-identity-unavailable") from None
        if current != self.identity or type(current) is not PhysicalClientIdentity:
            raise PhysicalReservationError("physical-reservation-identity-changed")
        current.require_local_host()
        return current

    def release(self):
        if not self.held:
            raise PhysicalReservationError("physical-reservation-not-owned")
        if threading.current_thread() is not self._owner_thread:
            raise PhysicalReservationError("physical-reservation-wrong-thread")
        if not self._api.ReleaseMutex(self._handle):
            raise PhysicalReservationError("physical-reservation-release-failed")
        self._api.CloseHandle(self._handle)
        self._handle = None
        self._api = None
        self._owner_thread = None
        with _registry_lock:
            _owned_names.discard(self.name)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()
