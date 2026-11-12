"""Idle-only reconnection for a previously pinned physical RIFT client."""
import ctypes
from ctypes import wintypes


def process_epoch_alive(pid, start_ticks):
    """Confirm whether the pinned PID/creation time is still running; fail closed on errors."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # PID no longer exists
            return False
        raise OSError(error, "Cannot establish whether pinned RIFT process ended")
    try:
        creation, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise ctypes.WinError(ctypes.get_last_error())
        # FILETIME is 100 ns since 1601; .NET ticks are since year 1.
        ticks = ((creation.dwHighDateTime << 32) | creation.dwLowDateTime) + 504911232000000000
        if ticks != int(start_ticks):
            return False
        state = kernel.WaitForSingleObject(handle, 0)
        if state == 0:
            return False
        if state == 258:
            return True
        raise OSError(ctypes.get_last_error(), "Cannot establish pinned process state")
    finally:
        kernel.CloseHandle(handle)


def idle_read(adapter, host, basis, selector, factory, *, include_target=False,
              auto_reconnect=False, alive=process_epoch_alive):
    """Read current adapter, replacing it only after its process epoch has ended."""
    try:
        return adapter, adapter.read(include_target=True) if include_target else adapter.read(), False
    except Exception:
        if not auto_reconnect or alive(adapter.pid, adapter.target["processStartUtcTicks"]):
            raise
    selected = selector(host, None)
    if selected.get("status") != "ready":
        raise ValueError(selected.get("reason", "Physical RIFT is unavailable"))
    candidate = factory(host, selected["target"]["processId"], basis)
    pose = candidate.read(include_target=True) if include_target else candidate.read()
    return candidate, pose, True
