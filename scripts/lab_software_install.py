"""Install one approved development dependency in one verified RIFT VMware lab.

Uses the existing VM-specific credential and identity gates; never sends game input,
restarts RIFT, or requests a VM reboot. Each invocation installs only one allowlisted
WinGet package, saves a provenance-checked JSON result, and exits nonzero on failure.
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
GUEST_SCRIPT = ROOT / "scripts" / "lab_software_install_guest.ps1"
ARTIFACTS = ROOT / "artifacts" / "lab-software-install"
PACKAGES = ("Git.Git", "Python.Python.3.14", "Microsoft.DotNet.SDK.10", "OpenJS.NodeJS.LTS")


def validate_report(report: dict, lab_name: str, package_id: str) -> dict:
    expected = "RIFT-LAB-" + lab_name[-1]
    if not isinstance(report, dict) or report.get("schemaVersion") != 1:
        raise ValueError("installer-report-schema-invalid")
    if report.get("method") != "winget-guest-install" or report.get("packageId") != package_id:
        raise ValueError("installer-report-provenance-invalid")
    if str(report.get("machine", "")).casefold() != expected.casefold():
        raise ValueError("installer-report-machine-invalid")
    if report.get("rebootPerformed") is not False:
        raise ValueError("installer-report-reboot-invalid")
    if report.get("status") not in ("passed", "failed", "blocked"):
        raise ValueError("installer-report-status-invalid")
    return report


def install(lab_name: str, package_id: str) -> dict:
    lab = LabCodex()
    _, _, config, settings = lab._configuration(lab_name)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    nonce = uuid.uuid4().hex
    guest_dir = settings["guestRoot"] + "\\software-install-" + nonce
    guest_script = guest_dir + "\\install.ps1"
    guest_report = guest_dir + "\\result.json"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + nonce[:8]
    local_dir = ARTIFACTS / run_id
    local_dir.mkdir(parents=True, exist_ok=False)
    local_report = local_dir / (lab_name + ".json")
    with lab._session(config, settings, identity, doctor) as guest:
        guest.powershell("[void][IO.Directory]::CreateDirectory('" + guest_dir + "')",
                         timeout=30)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), guest_script, timeout=90)
        try:
            guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                      "-ExecutionPolicy", "Bypass", "-File", guest_script,
                      "-PackageId", package_id, "-ReportPath", guest_report, timeout=600)
        except Exception as error:
            diagnostic_path = local_dir / (lab_name + ".error.txt")
            try:
                guest.copy_from_guest(guest_report + ".error.txt", diagnostic_path, timeout=20)
                diagnostic = diagnostic_path.read_text(encoding="utf-8-sig").strip()
                if diagnostic.startswith("installer-script-error:") and len(diagnostic) < 128:
                    raise ValueError(diagnostic) from error
            except ValueError:
                raise
            except Exception:
                pass
            raise
        guest.copy_from_guest(guest_report, local_report, timeout=90)
    raw = local_report.read_bytes()
    if not 0 < len(raw) <= 64 * 1024:
        raise ValueError("installer-report-size-invalid")
    report = validate_report(json.loads(raw.decode("utf-8-sig")), lab_name, package_id)
    return {
        "status": report["status"],
        "reason": report["reason"],
        "machine": report["machine"],
        "packageId": report["packageId"],
        "exitCode": report["exitCode"],
        "outputTail": report["outputTail"],
        "report": str(local_report),
        "reportSha256": hashlib.sha256(raw).hexdigest(),
        "vmIdentity": {"vmx": identity["vmx"], "vmPid": identity["pid"]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    parser.add_argument("--package", choices=PACKAGES, required=True)
    args = parser.parse_args(argv)
    if not GUEST_SCRIPT.is_file() or GUEST_SCRIPT.is_symlink():
        parser.error("installer guest script unavailable")
    try:
        result = install(args.lab, args.package)
    except Exception as error:
        result = {"status": "failed", "reason": str(error),
                  "machine": args.lab, "packageId": args.package}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
