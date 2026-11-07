"""Remove one known stale Lab 1 reader configuration after strict guards.

This helper intentionally has no lab or guest-path option.  It does not read
the configuration, send game input, stop a process, or recursively remove
anything.  The only mutation it can request is disposition of the fixed leaf
below after validating an exclusive native handle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.launch_live_reader import (
    LABS,
    VMRUN,
    collect_identity,
    fail,
    legacy_guest_target,
    no_prompt,
    quote,
    run_guest_script,
    validate_config,
    verify_identity,
    write_new,
)
from scripts.vmware_guest_session import GuestSession
from scripts.guest_staging_cleanup import guest_body as generated_guest_body, validate_receipt


LAB = "lab1"
GUEST_USER = r"RIFT-LAB-1\mrkoo"
GUEST_PARENT = (
    r"C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid"
    r"\lab1-fed73039b1614151bc92bda5b8501641"
)
GUEST_FILE = GUEST_PARENT + r"\riftreader2-live.json"
MAX_LENGTH = 65_536


def guest_body() -> str:
    return generated_guest_body(LAB, "lab1-fed73039b1614151bc92bda5b8501641")



def execute(output: Path) -> dict:
    output = output.resolve(strict=False)
    output.mkdir(parents=True, exist_ok=False)
    lab = LABS[LAB]
    cfg = validate_config(lab["vmx"], lab["port"], VMRUN, output, require_files=True)
    vm_before = collect_identity(cfg)
    write_new(output / "vm-before.json", vm_before)
    check = lambda: verify_identity(cfg, vm_before)
    run_id = f"cleanup-{uuid.uuid4().hex}"

    with GuestSession(
        cfg.vmrun,
        cfg.vmx,
        check,
        cache_guest_credentials=False,
        _guest_prompt=no_prompt,
        legacy_guest_credential_target=legacy_guest_target(LAB),
    ) as session:
        if session.credential_source != "cache":
            fail("noncached-credentials-blocked")
        receipt = validate_receipt(
            run_guest_script(session, output, guest_body(), run_id, "cleanup")
        )

    vm_after = verify_identity(cfg, vm_before)
    write_new(output / "vm-after.json", vm_after)
    summary = {
        **receipt,
        "lab": LAB,
        "vmIdentityStable": vm_after == vm_before,
        "atUtc": datetime.now(timezone.utc).isoformat(),
    }
    write_new(output / "summary.json", summary)
    return summary


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        summary = execute(args.output)
    except Exception as error:
        print(json.dumps({"status": "blocked", "reason": str(error).split(":", 1)[0]}))
        return 2
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
