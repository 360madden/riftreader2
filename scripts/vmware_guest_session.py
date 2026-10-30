"""Short-lived authenticated VMware guest commands for reviewed lab workflows.

The VM encryption password comes from the current user's Windows Credential
Manager entry.  The guest Windows account is reused from a VM-specific current-
user entry when present, otherwise it is requested with a non-persisting native
prompt.  A caller must explicitly opt in before a newly verified login is saved.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
from typing import Callable
import uuid


ALLOWED_COMMANDS = frozenset({
    "listProcessesInGuest",
    "runProgramInGuest",
    "copyFileFromGuestToHost",
    "copyFileFromHostToGuest",
})
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
# This vmrun build has crashed on large encoded argv; leave room for VM credentials.
MAX_ENCODED_POWERSHELL_CHARS = 4096
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CREDUI_FLAGS_DO_NOT_PERSIST = 0x00002
CREDUI_FLAGS_ALWAYS_SHOW_UI = 0x00080
CREDUI_FLAGS_GENERIC_CREDENTIALS = 0x40000
ERROR_CANCELLED = 1223
ERROR_NOT_FOUND = 1168


class SessionError(RuntimeError):
    """A deliberately sanitized guest-session failure."""


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME), ("BlobSize", wintypes.DWORD),
        ("Blob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _CredUiInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD), ("parent", wintypes.HWND),
        ("message", wintypes.LPCWSTR), ("caption", wintypes.LPCWSTR),
        ("banner", wintypes.HANDLE),
    ]


def _saved_secret(target: str) -> str:
    if os.name != "nt":
        raise SessionError("windows-required")
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        raise SessionError("saved-vm-credential-unavailable")
    try:
        item = pointer.contents
        raw = ctypes.string_at(item.Blob, item.BlobSize)
        encoding = "utf-16-le" if len(raw) % 2 == 0 and raw[1:2] == b"\x00" else "utf-8"
        value = raw.decode(encoding).rstrip("\x00")
        if not value or "\x00" in value:
            raise ValueError
        return value
    except (UnicodeError, ValueError) as error:
        raise SessionError("saved-vm-credential-invalid") from error
    finally:
        api.CredFree(pointer)


def _saved_guest_credentials(target: str) -> tuple[ctypes.Array, ctypes.Array] | None:
    """Read one VM-specific guest login, returning wipeable buffers when present."""
    if os.name != "nt":
        raise SessionError("windows-required")
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise SessionError("saved-guest-credential-read-failed")
    try:
        item = pointer.contents
        raw = ctypes.string_at(item.Blob, item.BlobSize)
        password = raw.decode("utf-16-le").rstrip("\x00")
        username = item.UserName or ""
        if not username or not password or "\x00" in username or "\x00" in password:
            raise ValueError
        return ctypes.create_unicode_buffer(username), ctypes.create_unicode_buffer(password)
    except (UnicodeError, ValueError):
        raise SessionError("saved-guest-credential-invalid") from None
    finally:
        api.CredFree(pointer)


def _save_guest_credentials(target: str, username: str, password: str) -> None:
    """Write a verified guest login to the current user's Credential Manager."""
    if os.name != "nt":
        raise SessionError("windows-required")
    if not username or not password or "\x00" in username or "\x00" in password:
        raise SessionError("guest-credential-cache-invalid")
    password_buffer = ctypes.create_unicode_buffer(password)
    blob_size = ctypes.sizeof(password_buffer) - ctypes.sizeof(ctypes.c_wchar)
    if blob_size > 512:
        _wipe(password_buffer)
        raise SessionError("guest-credential-cache-too-large")
    credential = _Credential(
        0, CRED_TYPE_GENERIC, target, "RiftReader2 verified VMware guest login",
        wintypes.FILETIME(), blob_size,
        ctypes.cast(password_buffer, ctypes.POINTER(ctypes.c_ubyte)),
        CRED_PERSIST_LOCAL_MACHINE, 0, None, None, username,
    )
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    try:
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise SessionError("guest-credential-cache-write-failed")
    finally:
        _wipe(password_buffer)


def _prompt_guest() -> tuple[ctypes.Array, ctypes.Array]:
    if os.name != "nt":
        raise SessionError("windows-required")
    username = ctypes.create_unicode_buffer(514)
    password = ctypes.create_unicode_buffer(514)
    save = wintypes.BOOL(False)
    info = _CredUiInfo(
        ctypes.sizeof(_CredUiInfo), None,
        "Enter the Windows account inside the VMware guest. Used only for this run; not saved.",
        "RiftReader2 - guest Windows login", None,
    )
    api = ctypes.WinDLL("credui", use_last_error=True)
    prompt = api.CredUIPromptForCredentialsW
    prompt.argtypes = [
        ctypes.POINTER(_CredUiInfo), wintypes.LPCWSTR, ctypes.c_void_p,
        wintypes.DWORD, wintypes.LPWSTR, wintypes.ULONG, wintypes.LPWSTR,
        wintypes.ULONG, ctypes.POINTER(wintypes.BOOL), wintypes.DWORD,
    ]
    prompt.restype = wintypes.DWORD
    flags = (CREDUI_FLAGS_GENERIC_CREDENTIALS | CREDUI_FLAGS_ALWAYS_SHOW_UI |
             CREDUI_FLAGS_DO_NOT_PERSIST)
    code = prompt(ctypes.byref(info), "RiftReader2 VMware guest", None, 0,
                  username, len(username), password, len(password),
                  ctypes.byref(save), flags)
    if code:
        _wipe(username); _wipe(password)
        reason = "guest-credential-prompt-cancelled" if code == ERROR_CANCELLED else "guest-credential-prompt-failed"
        raise SessionError(reason)
    if not username.value or not password.value:
        _wipe(username); _wipe(password)
        raise SessionError("guest-credential-incomplete")
    return username, password


def _wipe(buffer: ctypes.Array | None) -> None:
    if buffer is not None:
        ctypes.memset(ctypes.addressof(buffer), 0, ctypes.sizeof(buffer))


def _failure_category(stdout: str, stderr: str) -> str:
    diagnostic = (stdout + "\n" + stderr).casefold()
    if any(marker in diagnostic for marker in (
        "invalid user name or password", "invalid username or password",
        "logon failure", "login failure", "authentication failure",
        "unable to log in to guest",
    )):
        return "invalid-login"
    if any(marker in diagnostic for marker in (
        "vmware tools are not running", "tools are not running",
        "guest operations agent",
    )):
        return "guest-tools-unavailable"
    if "program exited with" in diagnostic:
        return "guest-program-exit"
    return "command-failed"


def _validation_error(prefix: str, error: SessionError) -> SessionError:
    message = str(error)
    marker = "guest-command-failed:listProcessesInGuest:"
    if not message.startswith(marker):
        return error
    detail = message[len(marker):]
    label = (f"{prefix}-invalid" if "category=invalid-login" in detail
             else f"{prefix}-validation-failed")
    return SessionError(f"{label}:{detail}")


class GuestSession:
    """One authenticated, identity-pinned ``vmrun`` guest session.

    ``check_identity`` must return a comparable VM identity or raise.  Its value
    at entry is required before and after every command.  Internal dependency
    hooks exist only to make the credential behavior testable without live I/O.
    ``cache_guest_credentials`` authorizes saving a newly prompted login after
    validation; an existing VM-specific saved login is always reused.
    """

    def __init__(self, vmrun: Path, vmx: Path, check_identity: Callable[[], object], *,
                 credential_target: str | None = None,
                 cache_guest_credentials: bool = False,
                 guest_credential_target: str | None = None,
                 legacy_guest_credential_target: str | None = None,
                 _credential_reader=None, _guest_credential_reader=None,
                 _guest_credential_writer=None, _guest_prompt=None, _runner=None):
        self.vmrun = Path(vmrun)
        self.vmx = Path(vmx)
        self.check_identity = check_identity
        self.credential_target = credential_target or "VMware Encrypted VM: " + str(self.vmx)
        canonical_vmx = str(self.vmx.resolve(strict=False))
        self.guest_credential_target = (guest_credential_target or
                                        "RiftReader2 Guest Windows: " + canonical_vmx)
        self.legacy_guest_credential_target = legacy_guest_credential_target
        self.cache_guest_credentials = cache_guest_credentials
        self._credential_reader = _credential_reader or _saved_secret
        self._guest_credential_reader = _guest_credential_reader or _saved_guest_credentials
        self._guest_credential_writer = _guest_credential_writer or _save_guest_credentials
        self._guest_prompt = _guest_prompt or _prompt_guest
        self._runner = _runner or subprocess.run
        self._expected_identity = None
        self._vm_secret: str | None = None
        self._username = None
        self._password = None
        self.credential_source: str | None = None
        self.cache_written = False

    def __enter__(self):
        if self._vm_secret is not None:
            raise SessionError("session-already-open")
        try:
            self._expected_identity = self.check_identity()
            self._vm_secret = self._credential_reader(self.credential_target)
            cached = self._guest_credential_reader(self.guest_credential_target)
            if cached is None and self.legacy_guest_credential_target:
                cached = self._guest_credential_reader(self.legacy_guest_credential_target)
            if cached is not None:
                self._username, self._password = cached
                self.credential_source = "cache"
                self._require_identity()
                try:
                    self.run("listProcessesInGuest")
                except SessionError as error:
                    raise _validation_error("cached-guest-credential", error) from None
                return self
            self._username, self._password = self._guest_prompt()
            self.credential_source = "prompt"
            self._require_identity()
            if self.cache_guest_credentials:
                try:
                    self.run("listProcessesInGuest")
                except SessionError as error:
                    raise _validation_error("guest-credential", error) from None
                self._guest_credential_writer(
                    self.guest_credential_target,
                    self._username.value,
                    self._password.value,
                )
                self.cache_written = True
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        _wipe(self._username); _wipe(self._password)
        self._username = self._password = None
        self._vm_secret = None
        self._expected_identity = None
        self.credential_source = None
        self.cache_written = False

    def _require_identity(self) -> None:
        if self.check_identity() != self._expected_identity:
            raise SessionError("vm-identity-changed")

    def run(self, command: str, *arguments: str, timeout: int = 60) -> str:
        """Run one allowlisted guest command; diagnostic stderr is discarded."""
        if command not in ALLOWED_COMMANDS:
            raise SessionError("guest-command-not-allowed")
        if self._vm_secret is None or self._username is None or self._password is None:
            raise SessionError("session-not-open")
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise SessionError("invalid-command-timeout")
        self._require_identity()
        argv = [str(self.vmrun), "-T", "ws", "-vp", self._vm_secret,
                "-gu", self._username.value, "-gp", self._password.value,
                command, str(self.vmx), *map(str, arguments)]
        try:
            result = self._runner(
                argv, capture_output=True, text=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            # TimeoutExpired retains argv, including credentials, as ``cmd``.
            raise SessionError(f"guest-command-timeout:{command}") from None
        except OSError:
            raise SessionError(f"guest-command-start-failed:{command}") from None
        finally:
            for index in (4, 6, 8):
                argv[index] = "[cleared]"
        self._require_identity()
        if result.returncode:
            category = _failure_category(result.stdout, result.stderr)
            raise SessionError(
                f"guest-command-failed:{command}:exit={result.returncode}:category={category}"
            )
        return result.stdout

    def powershell(self, script: str, *, timeout: int = 150) -> str:
        """Run only short scripts by encoded argv; stage larger scripts as files."""
        if not isinstance(script, str) or not script:
            raise SessionError("powershell-script-required")
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        if len(encoded) > MAX_ENCODED_POWERSHELL_CHARS:
            raise SessionError("guest-powershell-script-too-large")
        return self.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                        "-NonInteractive", "-WindowStyle", "Hidden",
                        "-EncodedCommand", encoded, timeout=timeout)

    def copy_from_guest(self, guest_path: str, destination: Path, *, timeout: int = 60) -> Path:
        """Copy through a unique temporary file, then publish without overwrite."""
        destination = Path(destination)
        if not guest_path or destination.exists() or not destination.parent.is_dir():
            raise SessionError("invalid-copy-destination")
        temporary = destination.with_name(
            destination.name + "." + uuid.uuid4().hex + ".vmrun-part"
        )
        try:
            self.run("copyFileFromGuestToHost", guest_path, str(temporary), timeout=timeout)
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise SessionError("guest-copy-output-missing")
            try:
                os.link(temporary, destination)
            except FileExistsError:
                raise SessionError("copy-destination-raced") from None
            except OSError:
                raise SessionError("copy-publication-failed") from None
            return destination
        except BaseException:
            raise
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
