"""Find and validate one *already-running* on-demand managed controller generation.

Pure filesystem/process inspection plus the existing task-ownership status check.
Never starts a controller, controls the VM, or sends game input.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time


SHA = re.compile(r"[0-9a-fA-F]{64}")
GENERATION = re.compile(r"[0-9a-f]{32}")
EXPECTED = {"lab", "pid", "session", "processIdentity", "vmIdentity",
            "configSha256", "sourceHashes", "task", "atUtc"}


class ManagedReceiptError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise ManagedReceiptError(reason)


def _sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "managed-source-unavailable")
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _read(path, data=None):
    path = Path(path)
    require(path.is_file() and _nonreparse(path)
            and path.stat().st_size <= 65536, "managed-receipt-unavailable")
    data = path.read_bytes() if data is None else data
    require(len(data) <= 65536, "managed-receipt-too-large")
    try:
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate-key")
                value[key] = item
            return value
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError, ValueError) as error:
        raise ManagedReceiptError("managed-receipt-malformed") from error
    require(isinstance(value, dict) and set(value) == EXPECTED,
            "managed-receipt-schema-invalid")
    return value


def _valid_time(text):
    if not isinstance(text, str):
        return False
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return value.tzinfo is not None



def _nonreparse(path):
    stat = path.stat(follow_symlinks=False)
    return not path.is_symlink() and not (getattr(stat, "st_file_attributes", 0) & 0x400)


def _process_absent(pid):
    """Prove absence; access denied and every other error remain uncertain."""
    if os.name != "nt" or type(pid) is not int or not 0 < pid <= 0xffffffff:
        return False
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = api.OpenProcess(0x1000, False, pid)
    if handle:
        api.CloseHandle(handle)
        return False
    return ctypes.get_last_error() == 87


def _absent(checker, pid):
    try:
        return checker(pid) is True
    except Exception:
        return False


def _history_exited(generation, lab, raw, absence_checker):
    """Accept only this generation's producer exit and a fresh absence proof."""
    try:
        marker = generation / "exited.json"
        if not marker.is_file() or not _nonreparse(marker) or not 0 < marker.stat().st_size <= 65536:
            return False
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate-key")
                result[key] = value
            return result
        with marker.open("rb") as stream:
            data = stream.read(65537)
        if not 0 < len(data) <= 65536:
            return False
        exit_record = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        if not isinstance(exit_record, dict) or set(exit_record) != {"lab", "pid", "atUtc"}:
            return False
        pid = exit_record["pid"]
        stamp = exit_record["atUtc"]
        if (exit_record["lab"] != lab or type(pid) is not int or not 0 < pid <= 0xffffffff
                or not _valid_time(stamp) or datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset().total_seconds() != 0):
            return False
        try:
            prior = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        except UnicodeError:
            prior = None
        except ValueError as error:
            if str(error) in ("duplicate-key", "nonfinite"):
                return False
            prior = None
        if isinstance(prior, dict):
            if (("lab" in prior and prior["lab"] != lab)
                    or ("task" in prior and prior["task"] != "rr2-controller-" + lab)
                    or ("pid" in prior and (type(prior["pid"]) is not int or prior["pid"] != pid))
                    or (isinstance(prior.get("processIdentity"), dict)
                        and "pid" in prior["processIdentity"]
                        and (type(prior["processIdentity"]["pid"]) is not int
                             or prior["processIdentity"]["pid"] != pid))):
                return False
        return _absent(absence_checker, pid)
    except (OSError, ValueError, TypeError, OverflowError):
        return False


def _valid_identity(identity, pid):
    return (isinstance(identity, dict) and set(identity) == {"pid", "image", "startTicks"}
            and type(identity["pid"]) is int and identity["pid"] == pid
            and isinstance(identity["image"], str) and bool(identity["image"])
            and type(identity["startTicks"]) is int and identity["startTicks"] > 0)


def _verify_legacy_owner(lab, image, root, expected_pid):
    """Inspect an existing legacy task without invoking its manager."""
    require(isinstance(image, str) and bool(image), "managed-process-image-invalid")
    inspector = root / "scripts" / "Verify-RR2LegacyHelperTask.ps1"
    require(inspector.is_file(), "managed-legacy-inspector-unavailable")
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
             "RemoteSigned", "-File", str(inspector), "-HelperId",
             "rr2-controller-" + lab, "-Executable", image],
            cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True,
            timeout=20, check=False)
        status = json.loads(result.stdout.decode("utf-8-sig")) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        raise ManagedReceiptError("managed-legacy-ownership-refused") from error
    from scripts.ensure_receiver import _valid_instance_guid
    require(isinstance(status, dict) and type(status.get("enginePid")) is int
            and status["enginePid"] == expected_pid and _valid_instance_guid(status.get("instanceGuid"))
            and status.get("helperId") == "rr2-controller-" + lab
            and status.get("ownership") == "verified-legacy-read-only"
            and status.get("state") == "Running" and status.get("atLogon") is False
            and status.get("runLevel") == "Limited", "managed-legacy-ownership-refused")


def verify_lab2_inspection_task(lab: str, expected_pid: int) -> None:
    """Query fresh Task Scheduler registration and state for the read-only Lab 2 inspection."""
    require(lab == "lab2", "inspection-task-lab-invalid")
    from scripts.controller_task_entry import POWERSHELL
    from scripts.ensure_controller import MANAGER
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
         "-File", str(MANAGER), "-Action", "Status", "-HelperId", "rr2-controller-lab2",
         "-InspectLab2Controller"], cwd=str(root), stdin=subprocess.DEVNULL,
        capture_output=True, timeout=20, check=False)
    _require_lab2_inspection_result(result.returncode, result.stdout, expected_pid)


def _require_lab2_inspection_result(returncode, stdout, expected_pid):
    require(returncode == 0, "inspection-task-ownership-refused")
    status = json.loads(stdout.decode("utf-8-sig"))
    from scripts.ensure_receiver import _valid_instance_guid
    require(isinstance(status, dict) and type(status.get("enginePid")) is int
            and status["enginePid"] == expected_pid and _valid_instance_guid(status.get("instanceGuid"))
            and status.get("helperId") == "rr2-controller-lab2"
            and status.get("taskName") == "RiftReader2 Helper rr2-controller-lab2"
            and status.get("state") == "Running" and status.get("runLevel") == "Limited"
            and status.get("atLogon") is False, "inspection-task-ownership-refused")


_INSPECTION_TIMEOUT = 20


def _pipe_available(stream):
    # HANDLE is pointer-sized: ctypes' default int arguments truncate it on x64.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
    peek.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                     wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPDWORD)
    peek.restype = wintypes.BOOL
    available = wintypes.DWORD()
    if not peek(wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno())), None, 0,
                None, ctypes.byref(available), None):
        if ctypes.get_last_error() == 109:  # EOF after all bytes were drained.
            return 0
        raise ManagedReceiptError("inspection-task-pipe-closed")
    return available.value


def _inspection_frame(child, deadline):
    data = bytearray()
    while True:
        require(time.monotonic() < deadline, "inspection-task-expired")
        available = _pipe_available(child.stdout)
        if available:
            require(len(data) + available <= 65536, "inspection-task-frame-too-large")
            chunk = os.read(child.stdout.fileno(), available)
            require(len(chunk) == available, "inspection-task-partial-frame")
            data.extend(chunk)
            if b"\n" in data:
                frame, trailing = bytes(data).split(b"\n", 1)
                require(not trailing, "inspection-task-extra-frame")
                require(time.monotonic() < deadline, "inspection-task-expired")
                return frame
        else:
            if child.poll() is not None:
                # Exit can race the previous peek: drain a just-written final frame.
                require(_pipe_available(child.stdout) > 0, "inspection-task-partial-frame")
                continue
            time.sleep(min(.01, max(0, deadline - time.monotonic())))


@contextmanager
def prepared_lab2_inspection_pair(*, _proof_count=2):
    """One bounded interpreter; two fresh, separately triggered ownership proofs."""
    from scripts.controller_task_entry import POWERSHELL
    from scripts.ensure_controller import MANAGER
    require(_proof_count in (1, 2), "inspection-task-proof-count-invalid")
    manager = str(MANAGER).replace("'", "''")
    command = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
foreach ($module in @('Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {{
    Import-Module ([IO.Path]::Combine($PSHOME, 'Modules', $module, ($module + '.psd1'))) -ErrorAction Stop
}}
$reader = [IO.StreamReader]::new([Console]::OpenStandardInput())
foreach ($ordinal in 1..{_proof_count}) {{
    $signal = $reader.ReadLineAsync()
    if (!$signal.Wait({_INSPECTION_TIMEOUT * 1000})) {{ exit 1 }}
    if ($signal.Result -cnotmatch ('^' + $ordinal + ':([0-9a-f]{{32}})$')) {{ exit 1 }}
    $token = $Matches[1]
    $raw = @(& '{manager}' -Action Status -HelperId rr2-controller-lab2 -InspectLab2Controller)
    $status = ($raw -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
    $frame = [ordered]@{{ordinal=$ordinal; token=$token; status=$status}}
    [Console]::Out.WriteLine(($frame | ConvertTo-Json -Depth 20 -Compress))
    [Console]::Out.Flush()
}}
"""
    deadline = time.monotonic() + _INSPECTION_TIMEOUT
    with subprocess.Popen(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
         "-Command", command], cwd=str(MANAGER.parent.parent), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as child:
        next_ordinal = 1
        active = True
        prior_identity = None

        def callback(ordinal):
            def verify(lab, expected_pid):
                nonlocal next_ordinal, prior_identity, active
                was_active = active
                # Any failed attempt consumes the entire admission, including proof two.
                active = False
                require(was_active and next_ordinal == ordinal, "inspection-task-already-consumed")
                require(lab == "lab2" and type(expected_pid) is int and expected_pid > 0,
                        "inspection-task-target-invalid")
                require(time.monotonic() < deadline, "inspection-task-expired")
                token = secrets.token_hex(16)
                signal = f"{ordinal}:{token}\n".encode("ascii")
                try:
                    require(_pipe_available(child.stdout) == 0, "inspection-task-unsolicited-frame")
                    require(child.stdin.write(signal) == len(signal), "inspection-task-signal-failed")
                    child.stdin.flush()
                    frame = json.loads(_inspection_frame(child, deadline).decode("utf-8"))
                    require(isinstance(frame, dict) and set(frame) == {"ordinal", "token", "status"}
                            and type(frame["ordinal"]) is int and frame["ordinal"] == ordinal
                            and frame["token"] == token, "inspection-task-frame-invalid")
                    status = frame["status"]
                    _require_lab2_inspection_result(0, json.dumps(status).encode("utf-8"), expected_pid)
                    identity = (status["enginePid"], status["instanceGuid"])
                    require(prior_identity is None or identity == prior_identity,
                            "inspection-task-instance-changed")
                    if ordinal == _proof_count:
                        remaining = deadline - time.monotonic()
                        require(remaining > 0, "inspection-task-expired")
                        require(child.wait(timeout=remaining) == 0, "inspection-task-ownership-refused")
                        require(_pipe_available(child.stdout) == 0, "inspection-task-extra-frame")
                        require(time.monotonic() < deadline, "inspection-task-expired")
                except subprocess.TimeoutExpired as error:
                    raise ManagedReceiptError("inspection-task-expired") from error
                except (OSError, UnicodeError, ValueError) as error:
                    if isinstance(error, ManagedReceiptError):
                        raise
                    raise ManagedReceiptError("inspection-task-frame-invalid") from error
                require(time.monotonic() < deadline, "inspection-task-expired")
                prior_identity = identity
                next_ordinal += 1
                active = ordinal < _proof_count
            return verify

        try:
            yield callback(1), callback(2)
        finally:
            active = False
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


@contextmanager
def prepared_lab2_inspection_task():
    """Prewarm one fresh single-use proof and require successful helper exit."""
    with prepared_lab2_inspection_pair(_proof_count=1) as (first, _second):
        yield first


def resolve_current_managed_controller(lab: str, *, root=None, configs=None,
                                       queue_path=None, runtime_files=None,
                                       identity_reader=None, verify_owner=None, verify_legacy=None,
                                       expected_receipt_path=None, allow_legacy=True,
                                       absence_checker=None):
    """Return (exact process receipt path, validated receipt, synthetic host plan).

    Explicit injection arguments exist for offline tests. Production callers
    supply only lab/expected_receipt_path, using canonical repo settings.
    """
    require(lab in ("lab1", "lab2"), "managed-lab-invalid")
    if root is None:
        root = Path(__file__).resolve().parents[1]
    root = Path(root).resolve(strict=True)
    if configs is None or queue_path is None or runtime_files is None:
        from scripts.ensure_controller import CONFIGS, QUEUE, RUNTIME_FILES
        configs = CONFIGS if configs is None else configs
        queue_path = QUEUE if queue_path is None else queue_path
        runtime_files = RUNTIME_FILES if runtime_files is None else runtime_files
    if identity_reader is None:
        from scripts.vm_console_native import process_identity
        identity_reader = process_identity
    if absence_checker is None:
        absence_checker = _process_absent
    if verify_owner is None:
        from scripts.controller_task_entry import _require_owned_task
        verify_owner = _require_owned_task
    if verify_legacy is None:
        verify_legacy = _verify_legacy_owner

    config_path = Path(configs[lab]).resolve(strict=True)
    queue_path = Path(queue_path).resolve(strict=True)
    require(queue_path.is_file() and not queue_path.is_symlink(),
            "managed-queue-unavailable")
    sources = tuple(runtime_files)
    require(sources and len(set(sources)) == len(sources)
            and "scripts/controller_task_entry.py" in sources,
            "managed-runtime-file-list-invalid")
    location = root / "artifacts" / "controller-tasks" / lab
    require(location.is_dir() and _nonreparse(location),
            "managed-generation-directory-unavailable")
    generations = list(location.iterdir())
    require(len(generations) <= 4096, "managed-generation-inventory-too-large")
    live = []
    for generation in sorted(generations):
        require(_nonreparse(generation), "managed-generation-symlink")
        if not generation.is_dir():
            continue
        receipt_path = generation / "process.json"
        # A task that never published cannot have started its control host.
        try:
            receipt_stat = receipt_path.lstat()
        except FileNotFoundError:
            try:
                (generation / "exited.json").lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise ManagedReceiptError("managed-receipt-unavailable") from error
            raise ManagedReceiptError("managed-receipt-unavailable")
        except OSError as error:
            raise ManagedReceiptError("managed-receipt-unavailable") from error
        require(GENERATION.fullmatch(generation.name) is not None,
                "managed-generation-name-invalid")
        require(stat.S_ISREG(receipt_stat.st_mode) and _nonreparse(receipt_path),
                "managed-receipt-unavailable")
        require(receipt_stat.st_size <= 65536, "managed-receipt-too-large")
        try:
            with receipt_path.open("rb") as stream:
                raw = stream.read(65537)
        except OSError as error:
            raise ManagedReceiptError("managed-receipt-unavailable") from error
        require(len(raw) <= 65536, "managed-receipt-too-large")
        try:
            receipt = _read(receipt_path, raw)
        except ManagedReceiptError as error:
            if (str(error) in ("managed-receipt-malformed", "managed-receipt-schema-invalid")
                    and _history_exited(generation, lab, raw, absence_checker)):
                continue
            raise
        require(receipt["lab"] == lab and receipt["task"] == "rr2-controller-" + lab,
                "managed-receipt-lab-or-task-mismatch")
        pid, session = receipt["pid"], receipt["session"]
        require(type(pid) is int and 0 < pid <= 0xffffffff and type(session) is int and session > 0,
                "managed-receipt-pid-or-session-invalid")
        require(_valid_identity(receipt["processIdentity"], pid)
                and isinstance(receipt["vmIdentity"], dict)
                and isinstance(receipt["sourceHashes"], dict)
                and SHA.fullmatch(str(receipt["configSha256"])) is not None
                and _valid_time(receipt["atUtc"]), "managed-receipt-fields-invalid")
        try:
            actual = identity_reader(pid)
        except Exception as error:
            if str(error) == "process-unavailable" and _absent(absence_checker, pid):
                continue
            raise ManagedReceiptError("managed-process-identity-uncertain") from error
        require(_valid_identity(actual, pid), "managed-process-identity-uncertain")
        if actual != receipt["processIdentity"]:
            require(actual["startTicks"] != receipt["processIdentity"]["startTicks"],
                    "managed-process-identity-uncertain")
            continue  # A different process epoch proves PID reuse.
        require(not (generation / "exited.json").exists()
                and not (generation / "failure.json").exists()
                and not (generation / "stop.request").exists(),
                "managed-live-generation-exiting")
        live.append((receipt_path.resolve(strict=True), receipt))

    require(len(live) == 1, "managed-live-generation-not-unique")
    path, receipt = live[0]
    if expected_receipt_path is not None:
        expected = Path(expected_receipt_path)
        require(expected.is_file() and not expected.is_symlink(),
                "managed-reviewed-generation-changed")
        try:
            require(expected.resolve(strict=True) == path, "managed-reviewed-generation-changed")
        except OSError as error:
            raise ManagedReceiptError("managed-reviewed-generation-changed") from error
    require(set(receipt["sourceHashes"]) == set(sources),
            "managed-source-list-changed")
    require(_sha(config_path) == receipt["configSha256"].upper(),
            "managed-config-changed")
    for source in sources:
        expected = receipt["sourceHashes"][source]
        require(isinstance(expected, str) and SHA.fullmatch(expected) is not None,
                "managed-source-hash-invalid")
        require(_sha(root / source) == expected.upper(), "managed-runtime-changed")
    try:
        verify_owner(lab, receipt["pid"])
    except Exception as error:
        if not allow_legacy:
            raise ManagedReceiptError("managed-task-ownership-refused") from error
        try:
            verify_legacy(lab, receipt["processIdentity"].get("image"), root, receipt["pid"])
        except Exception as error:
            raise ManagedReceiptError("managed-task-ownership-refused") from error
    plan = {
        "configPath": str(config_path), "database": str(queue_path),
        "resource": "vm:rift-lab-" + lab[-1],
        "vmIdentity": receipt["vmIdentity"],
        "configSha256": receipt["configSha256"].upper(),
        "runtimeHashes": dict(receipt["sourceHashes"]),
        "shutdownFile": str(path.parent / "stop.request"),
        "expectedWindowsSession": receipt["session"],
    }
    return path, receipt, plan
