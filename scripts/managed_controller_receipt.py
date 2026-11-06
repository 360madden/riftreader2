"""Find and validate one *already-running* on-demand managed controller generation.

Pure filesystem/process inspection plus the existing task-ownership status check.
Never calls ensure(), launches a process, controls the VM, or sends game input.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


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


def _read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink()
            and 0 < path.stat().st_size <= 65536, "managed-receipt-unavailable")
    data = path.read_bytes()
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


def resolve_current_managed_controller(lab: str, *, root=None, configs=None,
                                       queue_path=None, runtime_files=None,
                                       identity_reader=None, verify_owner=None,
                                       expected_receipt_path=None):
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
    if verify_owner is None:
        from scripts.controller_task_entry import _require_owned_task
        verify_owner = _require_owned_task

    config_path = Path(configs[lab]).resolve(strict=True)
    queue_path = Path(queue_path).resolve(strict=True)
    require(queue_path.is_file() and not queue_path.is_symlink(),
            "managed-queue-unavailable")
    sources = tuple(runtime_files)
    require(sources and len(set(sources)) == len(sources)
            and "scripts/controller_task_entry.py" in sources,
            "managed-runtime-file-list-invalid")
    location = root / "artifacts" / "controller-tasks" / lab
    require(location.is_dir() and not location.is_symlink(),
            "managed-generation-directory-unavailable")
    generations = list(location.iterdir())
    require(len(generations) <= 4096, "managed-generation-inventory-too-large")
    live = []
    for generation in sorted(generations):
        require(not generation.is_symlink(), "managed-generation-symlink")
        if not generation.is_dir():
            continue
        receipt_path = generation / "process.json"
        if not receipt_path.exists():
            continue
        require(GENERATION.fullmatch(generation.name) is not None,
                "managed-generation-name-invalid")
        receipt = _read(receipt_path)
        require(receipt["lab"] == lab and receipt["task"] == "rr2-controller-" + lab,
                "managed-receipt-lab-or-task-mismatch")
        pid, session = receipt["pid"], receipt["session"]
        require(type(pid) is int and pid > 0 and type(session) is int and session > 0,
                "managed-receipt-pid-or-session-invalid")
        require(isinstance(receipt["processIdentity"], dict)
                and receipt["processIdentity"].get("pid") == pid
                and isinstance(receipt["vmIdentity"], dict)
                and isinstance(receipt["sourceHashes"], dict)
                and SHA.fullmatch(str(receipt["configSha256"])) is not None
                and _valid_time(receipt["atUtc"]), "managed-receipt-fields-invalid")
        try:
            actual = identity_reader(pid)
        except Exception as error:
            if str(error) == "process-unavailable":
                continue
            raise ManagedReceiptError("managed-process-identity-uncertain") from error
        if actual != receipt["processIdentity"]:
            continue  # Stale receipt or PID reused; never promote the old owner.
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
        verify_owner(lab)
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
