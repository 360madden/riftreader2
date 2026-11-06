"""Deploy and verify the official portable Microsoft Sysinternals Suite in one lab.

Uses exact VMware identity and per-VM cached Windows guest credentials. It does
not restart Windows, VMware or RIFT, and sends no game input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

from lab_codex import LabCodex
from vmware_guest_session import POWERSHELL

ROOT = Path(__file__).resolve().parents[1]
GUEST_SCRIPT = ROOT / "scripts" / "lab_sysinternals_portable_guest.ps1"
ARTIFACTS = ROOT / "artifacts" / "lab-sysinternals-portable"


def install(lab_name: str) -> dict:
    lab = LabCodex()
    _, _, config, settings = lab._configuration(lab_name)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    nonce = uuid.uuid4().hex
    guest_dir = settings["guestRoot"] + "\\sysinternals-install-" + nonce
    guest_script = guest_dir + "\\install.ps1"
    guest_report = guest_dir + "\\result.json"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + nonce[:8]
    local_dir = ARTIFACTS / run_id
    local_dir.mkdir(parents=True, exist_ok=False)
    local_report = local_dir / (lab_name + ".json")

    with lab._session(config, settings, identity, doctor) as guest:
        guest.powershell("[void][IO.Directory]::CreateDirectory('" + guest_dir + "')", timeout=30)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), guest_script, timeout=90)
        guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-File", guest_script,
                  "-ReportPath", guest_report, timeout=600)
        guest.copy_from_guest(guest_report, local_report, timeout=90)

    raw = local_report.read_bytes()
    if not 0 < len(raw) <= 64 * 1024:
        raise ValueError("sysinternals-report-size-invalid")
    report = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(report, dict) or report.get("schemaVersion") != 1:
        raise ValueError("sysinternals-report-schema-invalid")
    if report.get("method") != "official-microsoft-portable-zip":
        raise ValueError("sysinternals-report-method-invalid")
    if str(report.get("machine", "")).casefold() != ("RIFT-LAB-" + lab_name[-1]).casefold():
        raise ValueError("sysinternals-report-machine-invalid")
    if report.get("rebootPerformed") is not False:
        raise ValueError("sysinternals-report-reboot-invalid")
    if report.get("status") not in ("passed", "failed"):
        raise ValueError("sysinternals-report-status-invalid")
    if report["status"] == "passed":
        required = {"Process Explorer", "Process Monitor", "Autoruns", "TCPView", "ProcDump"}
        tools = report.get("tools")
        if not isinstance(tools, list) or {item.get("name") for item in tools} != required:
            raise ValueError("sysinternals-report-tools-incomplete")
        if not all(item.get("signature") == "Valid" and
                   "Microsoft Corporation" in item.get("signer", "") for item in tools):
            raise ValueError("sysinternals-report-signature-invalid")
    return {
        "status": report["status"],
        "machine": report["machine"],
        "target": report.get("target"),
        "reason": report.get("reason"),
        "zipSha256": report.get("zipSha256"),
        "tools": report.get("tools"),
        "report": str(local_report),
        "reportSha256": hashlib.sha256(raw).hexdigest(),
        "vmIdentity": {"vmx": identity["vmx"], "vmPid": identity["pid"]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    args = parser.parse_args(argv)
    if not GUEST_SCRIPT.is_file() or GUEST_SCRIPT.is_symlink():
        parser.error("Sysinternals guest script unavailable")
    try:
        result = install(args.lab)
    except Exception as error:
        result = {"status": "failed", "machine": args.lab, "reason": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
