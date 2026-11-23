"""Run one Windows process tree in an atomically assigned, owned Job Object.

This is intentionally narrower than ``subprocess.Popen``.  It exists for long
offline RiftWorld preparation where a launcher can exit before its descendants.
The caller owns only the job created here; no process discovery or global PID
termination is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes as W
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import time


DEFAULT_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
_POLL_SECONDS = 0.025
_CLEANUP_SECONDS = 10.0

_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_CREATE_NO_WINDOW = 0x08000000
_STARTF_USESTDHANDLES = 0x00000100
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
_PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_STILL_ACTIVE = 259
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_CREATE_NEW = 1
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_HANDLE_FLAG_INHERIT = 1
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", W.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", W.BOOL)]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
        ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
        ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
        ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD),
        ("dwFlags", W.DWORD), ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)), ("hStdInput", W.HANDLE),
        ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD),
        ("SchedulingClass", W.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", W.DWORD), ("TotalProcesses", W.DWORD),
        ("ActiveProcesses", W.DWORD), ("TotalTerminatedProcesses", W.DWORD),
    ]


@dataclass(frozen=True)
class OwnedProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    metadata: dict
    confirmed_cleanup: bool


class OwnedProcessError(subprocess.SubprocessError):
    def __init__(self, message: str, *, result: OwnedProcessResult | None, metadata: dict):
        super().__init__(message)
        self.result = result
        self.metadata = metadata


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def _bounded_text(path: Path, limit: int) -> tuple[str, int, bool]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        data = stream.read(limit)
    return data.decode("utf-8", errors="replace"), size, size > len(data)


def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
    kernel.CreateJobObjectW.restype = W.HANDLE
    kernel.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
    kernel.SetInformationJobObject.restype = W.BOOL
    kernel.QueryInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                  W.DWORD, ctypes.POINTER(W.DWORD)]
    kernel.QueryInformationJobObject.restype = W.BOOL
    kernel.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, W.DWORD, W.DWORD,
                                                         ctypes.POINTER(ctypes.c_size_t)]
    kernel.InitializeProcThreadAttributeList.restype = W.BOOL
    kernel.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.c_size_t,
                                                 ctypes.c_void_p, ctypes.c_size_t,
                                                 ctypes.c_void_p, ctypes.c_void_p]
    kernel.UpdateProcThreadAttribute.restype = W.BOOL
    kernel.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                      W.BOOL, W.DWORD, ctypes.c_void_p, W.LPCWSTR,
                                      ctypes.POINTER(_STARTUPINFOW), ctypes.POINTER(_PROCESS_INFORMATION)]
    kernel.CreateProcessW.restype = W.BOOL
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD,
                                   ctypes.POINTER(_SECURITY_ATTRIBUTES), W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.SetHandleInformation.argtypes = [W.HANDLE, W.DWORD, W.DWORD]
    kernel.SetHandleInformation.restype = W.BOOL
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    kernel.GetExitCodeProcess.restype = W.BOOL
    kernel.TerminateJobObject.argtypes = [W.HANDLE, W.UINT]
    kernel.TerminateJobObject.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    return kernel


def _winerror(action: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, f"{action}: {ctypes.FormatError(code).strip()}")


def _active_processes(kernel, job) -> tuple[int, int]:
    value = _JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    if not kernel.QueryInformationJobObject(job, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                                            ctypes.byref(value), ctypes.sizeof(value), None):
        raise _winerror("QueryInformationJobObject failed")
    return value.ActiveProcesses, value.TotalProcesses


def _validate(command, cwd, log_directory, timeout_seconds, max_output_bytes):
    if os.name != "nt":
        raise ValueError("owned process execution requires Windows")
    if isinstance(command, (str, bytes)) or not isinstance(command, (list, tuple)) or not command:
        raise ValueError("command must be a nonempty argument sequence")
    args = []
    for index, value in enumerate(command):
        try:
            item = os.fspath(value)
        except TypeError as exc:
            raise ValueError(f"command[{index}] must be path-like or text") from exc
        if isinstance(item, bytes) or not item or "\x00" in item:
            raise ValueError(f"command[{index}] must be nonempty text without NUL")
        args.append(item)
    work = Path(cwd).resolve()
    if not work.is_dir():
        raise ValueError("cwd must be an existing directory")
    logs = Path(log_directory).resolve()
    if logs.exists():
        raise ValueError("log_directory already exists; choose a fresh path")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) \
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 64 * 1024 * 1024:
        raise ValueError("max_output_bytes must be an integer from 1 through 64 MiB")
    executable = shutil.which(args[0], path=os.environ.get("PATH"))
    if executable is None:
        candidate = Path(args[0])
        candidate = candidate if candidate.is_absolute() else work / candidate
        executable = str(candidate.resolve()) if candidate.is_file() else None
    if executable is None or not Path(executable).is_file():
        raise ValueError("command executable is unavailable")
    args[0] = str(Path(executable).resolve())
    return args, work, logs, float(timeout_seconds), max_output_bytes


def _environment_block(env):
    entries = []
    for key, value in env.items():
        if (not isinstance(key, str) or not key or "=" in key or "\0" in key
                or not isinstance(value, str) or "\0" in value):
            raise ValueError("Invalid owned process environment entry")
        entries.append((key, value))
    block = "\0".join(f"{key}={value}" for key, value in sorted(entries, key=lambda item: item[0].upper()))
    # CreateProcessW expects a value terminator followed by a block terminator.
    return ctypes.create_unicode_buffer(block + "\0")


def run_owned(command, *, cwd, log_directory, timeout_seconds,
              cancel_check=None, max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES, env=None) -> OwnedProcessResult:
    """Run a command and all descendants inside one private Windows Job Object."""
    if cancel_check is not None and not callable(cancel_check):
        raise ValueError("cancel_check must be callable or None")
    args, work, logs, timeout, output_limit = _validate(
        command, cwd, log_directory, timeout_seconds, max_output_bytes)
    environment = _environment_block(env) if env is not None else None
    logs.mkdir(parents=True, exist_ok=False)
    stdout_path, stderr_path = logs / "stdout.log", logs / "stderr.log"
    metadata = {
        "schema": "rr2.owned-process/1", "status": "starting", "startedAtUtc": _utc(),
        "timeoutSeconds": timeout, "maxOutputBytes": output_limit,
        "logs": {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        "launcherPid": None, "rootReturnCode": None, "totalProcesses": 0,
        "peakActiveProcesses": 0, "terminationRequested": False,
    }
    kernel = _kernel32()
    handles: list[int] = []
    attribute_list = None
    attribute_list_initialized = False
    process_info = _PROCESS_INFORMATION()
    status = "failed"
    reason = None
    confirmed = False
    started = time.monotonic()
    close_failures = 0

    def close(handle):
        nonlocal close_failures
        if handle and handle != _INVALID_HANDLE_VALUE:
            if not kernel.CloseHandle(handle):
                close_failures += 1

    try:
        security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
        log_sharing = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
        stdout = kernel.CreateFileW(str(stdout_path), _GENERIC_WRITE, log_sharing,
                                    ctypes.byref(security), _CREATE_NEW, _FILE_ATTRIBUTE_NORMAL, None)
        if stdout == _INVALID_HANDLE_VALUE:
            raise _winerror("creating stdout log failed")
        handles.append(stdout)
        stderr = kernel.CreateFileW(str(stderr_path), _GENERIC_WRITE, log_sharing,
                                    ctypes.byref(security), _CREATE_NEW, _FILE_ATTRIBUTE_NORMAL, None)
        if stderr == _INVALID_HANDLE_VALUE:
            raise _winerror("creating stderr log failed")
        handles.append(stderr)
        stdin = kernel.CreateFileW("NUL", _GENERIC_READ, 0, ctypes.byref(security),
                                   _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None)
        if stdin == _INVALID_HANDLE_VALUE:
            raise _winerror("opening NUL stdin failed")
        handles.append(stdin)

        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise _winerror("CreateJobObjectW failed")
        handles.append(job)
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                              ctypes.byref(limits), ctypes.sizeof(limits)):
            raise _winerror("setting KILL_ON_JOB_CLOSE failed")

        size = ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
        if not size.value:
            raise _winerror("sizing process attribute list failed")
        attribute_buffer = ctypes.create_string_buffer(size.value)
        attribute_list = ctypes.cast(attribute_buffer, ctypes.c_void_p)
        if not kernel.InitializeProcThreadAttributeList(attribute_list, 2, 0, ctypes.byref(size)):
            raise _winerror("initializing process attribute list failed")
        attribute_list_initialized = True
        inherited = (W.HANDLE * 3)(stdin, stdout, stderr)
        jobs = (W.HANDLE * 1)(job)
        if not kernel.UpdateProcThreadAttribute(attribute_list, 0,
                                                _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                                ctypes.cast(inherited, ctypes.c_void_p),
                                                ctypes.sizeof(inherited), None, None):
            raise _winerror("setting inherited handle list failed")
        if not kernel.UpdateProcThreadAttribute(attribute_list, 0,
                                                _PROC_THREAD_ATTRIBUTE_JOB_LIST,
                                                ctypes.cast(jobs, ctypes.c_void_p),
                                                ctypes.sizeof(jobs), None, None):
            raise _winerror("setting creation-time job list failed")

        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin
        startup.StartupInfo.hStdOutput = stdout
        startup.StartupInfo.hStdError = stderr
        startup.lpAttributeList = attribute_list
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
        flags = _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW
        if environment is not None:
            flags |= _CREATE_UNICODE_ENVIRONMENT
        if not kernel.CreateProcessW(args[0], command_line, None, None, True,
                                     flags, environment, str(work), ctypes.byref(startup.StartupInfo),
                                     ctypes.byref(process_info)):
            raise _winerror("CreateProcessW failed")
        handles.extend([process_info.hThread, process_info.hProcess])
        metadata["launcherPid"] = process_info.dwProcessId
        close(process_info.hThread)
        handles.remove(process_info.hThread)
        status = "running"

        while True:
            active, total = _active_processes(kernel, job)
            metadata["peakActiveProcesses"] = max(metadata["peakActiveProcesses"], active)
            metadata["totalProcesses"] = max(metadata["totalProcesses"], total)
            if stdout_path.stat().st_size + stderr_path.stat().st_size > output_limit:
                status, reason = "output-limit-exceeded", "combined output exceeded max_output_bytes"
                break
            if active == 0:
                confirmed = True
                status = "completed"
                break
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                status, reason = "timed-out", "timeout"
                break
            if cancel_check is not None:
                cancellation = cancel_check()
                if cancellation is not None:
                    if not isinstance(cancellation, str) or not cancellation.strip():
                        status, reason = "failed", "cancel_check returned an invalid reason"
                    else:
                        status, reason = "cancelled", cancellation.strip()
                    break
            time.sleep(_POLL_SECONDS)

        if status != "completed":
            metadata["terminationRequested"] = True
            if not kernel.TerminateJobObject(job, 1):
                raise _winerror("TerminateJobObject failed")
            deadline = time.monotonic() + _CLEANUP_SECONDS
            while time.monotonic() < deadline:
                active, total = _active_processes(kernel, job)
                metadata["totalProcesses"] = max(metadata["totalProcesses"], total)
                if active == 0:
                    confirmed = True
                    break
                time.sleep(_POLL_SECONDS)
            if not confirmed:
                status, reason = "cleanup-failed", "owned job retained active processes"

        code = W.DWORD()
        if status == "completed" and process_info.hProcess:
            wait_result = kernel.WaitForSingleObject(process_info.hProcess, 0)
            if wait_result != _WAIT_OBJECT_0:
                status, reason = "exit-code-unavailable", "root process termination was not confirmed"
            elif not kernel.GetExitCodeProcess(process_info.hProcess, ctypes.byref(code)):
                status, reason = "exit-code-unavailable", "GetExitCodeProcess failed"
            else:
                # 259 is documented as STILL_ACTIVE only while the process is
                # running.  The signalled process handle above makes it a valid
                # application exit code here rather than an unknown result.
                metadata["rootReturnCode"] = ctypes.c_int32(code.value).value
        returncode = metadata["rootReturnCode"]
    except KeyboardInterrupt:
        if 'job' in locals() and job:
            metadata["terminationRequested"] = True
            kernel.TerminateJobObject(job, 130)
            deadline = time.monotonic() + _CLEANUP_SECONDS
            while time.monotonic() < deadline:
                try:
                    if _active_processes(kernel, job)[0] == 0:
                        confirmed = True
                        break
                except OSError:
                    break
                time.sleep(_POLL_SECONDS)
        metadata.update(status="interrupted", confirmedCleanup=confirmed,
                        finishedAtUtc=_utc(), elapsedSeconds=time.monotonic() - started)
        raise
    except BaseException as exc:
        if 'job' in locals() and job:
            metadata["terminationRequested"] = True
            kernel.TerminateJobObject(job, 1)
            deadline = time.monotonic() + _CLEANUP_SECONDS
            while time.monotonic() < deadline:
                try:
                    if _active_processes(kernel, job)[0] == 0:
                        confirmed = True
                        break
                except OSError:
                    break
                time.sleep(_POLL_SECONDS)
        status, reason = "failed", str(exc)
        returncode = None
    finally:
        if attribute_list_initialized:
            kernel.DeleteProcThreadAttributeList(attribute_list)
        for handle in reversed(handles):
            close(handle)

    if close_failures:
        status, reason, confirmed = "cleanup-failed", "one or more native handles did not close", False
    stdout_observed = stdout_path.stat().st_size if stdout_path.is_file() else 0
    stderr_observed = stderr_path.stat().st_size if stderr_path.is_file() else 0
    stdout_stored = min(stdout_observed, output_limit)
    stderr_stored = min(stderr_observed, output_limit - stdout_stored)
    if stdout_path.is_file() and stdout_observed != stdout_stored:
        with stdout_path.open("r+b") as stream:
            stream.truncate(stdout_stored)
    if stderr_path.is_file() and stderr_observed != stderr_stored:
        with stderr_path.open("r+b") as stream:
            stream.truncate(stderr_stored)
    stdout_text, _, stdout_truncated = (_bounded_text(stdout_path, stdout_stored)
                                        if stdout_path.is_file() else ("", 0, False))
    stderr_text, _, stderr_truncated = (_bounded_text(stderr_path, stderr_stored)
                                        if stderr_path.is_file() else ("", 0, False))
    stdout_truncated = stdout_truncated or stdout_observed > stdout_stored
    stderr_truncated = stderr_truncated or stderr_observed > stderr_stored
    metadata.update(
        status=status, reason=reason, confirmedCleanup=confirmed, finishedAtUtc=_utc(),
        elapsedSeconds=time.monotonic() - started,
        logs={
            "stdout": str(stdout_path),
            "stdoutSha256": _sha256(stdout_path) if stdout_path.is_file() else None,
            "stdoutBytes": stdout_stored, "stdoutObservedBytes": stdout_observed,
            "stdoutTruncated": stdout_truncated,
            "stderr": str(stderr_path),
            "stderrSha256": _sha256(stderr_path) if stderr_path.is_file() else None,
            "stderrBytes": stderr_stored, "stderrObservedBytes": stderr_observed,
            "stderrTruncated": stderr_truncated,
        })
    result = OwnedProcessResult(returncode, stdout_text, stderr_text, metadata, confirmed)
    if status != "completed":
        raise OwnedProcessError(f"owned process {status}: {reason}", result=result, metadata=metadata)
    return result
