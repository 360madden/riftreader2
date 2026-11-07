"""On-demand, persistent Task-Scheduler-owned controller for one RIFT lab.

The RR2 helper manager verifies the Limited/Interactive
registration, disabled logon trigger, unlimited lifetime and IgnoreNew policy.
This process remains owned by that task; it does not spawn an escaping child.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.control_host import HostConfig, VmEpochGuard
from scripts.ensure_controller import CONFIGS, MANAGER, QUEUE, RUNTIME_FILES, _listening, _session_id
from scripts.vm_console_native import process_identity

POWERSHELL = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"


def fail(code):
    raise RuntimeError(code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def now():
    return datetime.now(timezone.utc).isoformat()


def _publish_process_receipt(output: Path, receipt: dict):
    """Publish a complete receipt once, without replacing an existing one."""
    payload = json.dumps(receipt, indent=2, allow_nan=False).encode("utf-8")
    if len(payload) > 65_536:
        raise ValueError("process receipt too large")

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate process receipt key")
            value[key] = item
        return value

    # Check the actual bytes using the resolver's strict object-key policy.
    if not isinstance(json.loads(payload, object_pairs_hook=unique_object), dict):
        raise ValueError("invalid process receipt")
    fd, staging_name = tempfile.mkstemp(prefix=".process-", suffix=".tmp", dir=output)
    staging = Path(staging_name)
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            if stream.write(payload) != len(payload):
                raise OSError("incomplete process receipt write")
            stream.flush()
            os.fsync(stream.fileno())
        # Both names are in the generation directory. Linking fails if the
        # final name already exists and never exposes a partial receipt.
        os.link(staging, output / "process.json")
    finally:
        staging.unlink(missing_ok=True)


def _require_owned_task(lab, expected_pid):
    """Verify the exact on-demand helper registration, not a mere task name."""
    if not MANAGER.is_file():
        fail("managed-helper-unavailable")
    run = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "RemoteSigned", "-File", str(MANAGER), "-Action", "Status",
         "-HelperId", "rr2-controller-" + lab],
        cwd=str(ROOT), stdin=subprocess.DEVNULL,
        capture_output=True, timeout=20, check=False,
    )
    if run.returncode:
        fail("managed-helper-ownership-refused")
    try:
        status = json.loads(run.stdout.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        fail("managed-helper-status-invalid")
    if not isinstance(status, dict):
        fail("managed-helper-status-invalid")
    from scripts.ensure_receiver import _valid_instance_guid
    if (status.get("state") != "Running" or status.get("atLogon") is not False
            or status.get("runLevel") != "Limited"
            or type(status.get("enginePid")) is not int or status["enginePid"] != expected_pid
            or not _valid_instance_guid(status.get("instanceGuid"))):
        fail("managed-helper-not-running-or-not-on-demand")


def start(lab):
    if os.name != "nt" or lab not in CONFIGS:
        fail("invalid-lab-or-platform")
    output = ROOT / "artifacts/controller-tasks" / lab / uuid4().hex
    output.mkdir(parents=True)
    # All startup evidence is private to this local Windows user; no game input.
    with (output / "stdout.private.log").open("x", encoding="utf-8", buffering=1) as stdout, \
         (output / "stderr.private.log").open("x", encoding="utf-8", buffering=1) as stderr, \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            _require_owned_task(lab, os.getpid())
            config_path = CONFIGS[lab]
            config = HostConfig.load(config_path)
            if not QUEUE.is_file():
                fail("coordination-database-missing")
            if _listening(config.ui_port):
                fail("controller-endpoint-already-owned")
            # The live task, not a stale plan, reacquires current VM identity.
            identity = VmEpochGuard(config).collect()
            hashes = {name: sha(ROOT / name) for name in RUNTIME_FILES
                      if name != "scripts/controller_host_entry.py"}
            hashes["scripts/controller_task_entry.py"] = sha(Path(__file__))
            receipt = {"lab": lab, "pid": os.getpid(), "session": _session_id(),
                       "processIdentity": process_identity(os.getpid()),
                       "vmIdentity": identity, "configSha256": sha(config_path),
                       "sourceHashes": hashes, "task": "rr2-controller-" + lab,
                       "atUtc": now()}
            _publish_process_receipt(output, receipt)
            stop_file = output / "stop.request"
            source = ROOT / "scripts/control_host.py"
            sys.argv = [str(source), "--config", str(config_path),
                        "--coordination-db", str(QUEUE),
                        "--coordination-resource", "vm:rift-lab-" + lab[-1],
                        "--reconcile-existing", "--shutdown-file", str(stop_file)]
            try:
                runpy.run_path(str(source), run_name="__main__")
            finally:
                with (output / "exited.json").open("x", encoding="utf-8") as receipt:
                    json.dump({"lab": lab, "pid": os.getpid(), "atUtc": now()}, receipt)
        except Exception as exc:
            # Only stable diagnostics, never private configuration/credential data.
            reasons = {"managed-helper-unavailable", "managed-helper-ownership-refused",
                       "managed-helper-status-invalid", "managed-helper-not-running-or-not-on-demand",
                       "coordination-database-missing", "controller-endpoint-already-owned",
                       "invalid-lab-or-platform"}
            reason = str(exc) if str(exc) in reasons else "startup-failed"
            with (output / "failure.json").open("x", encoding="utf-8") as receipt:
                json.dump({"lab": lab, "atUtc": now(), "errorType": type(exc).__name__,
                           "reason": reason}, receipt)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    start(parser.parse_args().lab)
