"""TaskScheduler-owned host-only receiver for one lab, with source/identity receipts.

Uses the RR2-owned read-only receiver; the manager owns this
process directly, with no boot/logon trigger, detached child or gameplay input.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ensure_receiver import (
    BIND, CONFIGS, ENTRY, PORTS, SOURCE, SOURCE_SHA256, TASKS,
    _config, _port_owners, _task_status, sha,
)
from scripts.ensure_controller import _session_id
from scripts.vm_console_native import process_identity


def start(lab):
    if os.name != "nt" or lab not in CONFIGS:
        raise RuntimeError("invalid-lab-or-platform")
    output = TASKS / lab / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    with (output / "stdout.private.log").open("x", encoding="utf-8", buffering=1) as stdout, \
         (output / "stderr.private.log").open("x", encoding="utf-8", buffering=1) as stderr, \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            _task_status(lab)
            config_path = _config(lab)
            if _port_owners(PORTS[lab]):
                raise RuntimeError("receiver-endpoint-already-owned")
            current = process_identity(os.getpid())
            observation_dir = output / "observations"
            observation_dir.mkdir()
            receipt = {
                "lab": lab, "pid": os.getpid(), "session": _session_id(),
                "processIdentity": current, "atUtc": datetime.now(timezone.utc).isoformat(),
                "sourceSha256": SOURCE_SHA256, "entrySha256": sha(ENTRY),
                "configSha256": sha(config_path), "bindAddress": BIND,
                "port": PORTS[lab], "task": "rr2-receiver-" + lab,
                "output": str(observation_dir), "atLogon": False,
            }
            with (output / "process.json").open("x", encoding="utf-8") as file:
                json.dump(receipt, file, indent=2)
            sys.path.insert(0, str(SOURCE.parent))
            sys.argv = [str(SOURCE), "--config", str(config_path),
                        "--output", str(observation_dir)]
            try:
                runpy.run_path(str(SOURCE), run_name="__main__")
            finally:
                with (output / "exited.json").open("x", encoding="utf-8") as file:
                    json.dump({"lab": lab, "pid": os.getpid(),
                               "atUtc": datetime.now(timezone.utc).isoformat()}, file)
        except Exception as error:
            allowed = {"invalid-lab-or-platform", "receiver-endpoint-already-owned"}
            code = str(error) if str(error) in allowed else "startup-failed"
            with (output / "failure.json").open("x", encoding="utf-8") as file:
                json.dump({"lab": lab, "errorType": type(error).__name__,
                           "reason": code,
                           "atUtc": datetime.now(timezone.utc).isoformat()}, file)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    start(parser.parse_args().lab)
