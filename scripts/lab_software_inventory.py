"""Read-only software baseline for both authenticated RIFT VMware labs.

Uses the existing VM-specific cached-credential and exact-VM identity gates.
No game input, installed-software changes, service changes or VM lifecycle actions.
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
GUEST_SCRIPT = ROOT / "scripts" / "lab_software_inventory_guest.ps1"
ARTIFACTS = ROOT / "artifacts" / "lab-software-inventory"
TOOLS = (
    "powershell51", "pwsh", "python", "python314", "pip", "pyLauncher",
    "dotnetSdk", "dotnetRuntimes", "node", "npm", "git", "ssh", "winapp", "winget",
)


def validate_report(value: dict, lab: str) -> dict:
    expected_machine = "RIFT-LAB-" + lab[-1]
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or value.get("method") != "read-only-software-inventory"
            or str(value.get("machine", "")).casefold() != expected_machine.casefold()):
        raise ValueError("software-report-provenance-invalid:" + lab)
    entries = value.get("tools")
    if not isinstance(entries, dict) or any(
            not isinstance(entries.get(name), dict)
            or type(entries[name].get("present")) is not bool for name in TOOLS):
        raise ValueError("software-report-tool-schema-invalid:" + lab)
    for key in ("memoryGiB", "diskCFreeGiB"):
        if type(value.get(key)) not in (float, int) or value[key] < 0:
            raise ValueError("software-report-capacity-invalid:" + lab)
    if not isinstance(value.get("vmwareTools"), dict):
        raise ValueError("software-report-vmtools-invalid:" + lab)
    return value


def run_lab(lab_name: str, run_root: Path) -> dict:
    lab = LabCodex()
    _, _, config, settings = lab._configuration(lab_name)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    nonce = uuid.uuid4().hex
    guest_folder = settings["guestRoot"] + "\\software-inventory-" + nonce
    guest_script = guest_folder + "\\inventory.ps1"
    guest_result = guest_folder + "\\report.json"
    local_result = run_root / (lab_name + ".json")
    with lab._session(config, settings, identity, doctor) as guest:
        # This short path creation writes only unique scratch files in the guest.
        guest.powershell("[void][IO.Directory]::CreateDirectory('" +
                         guest_folder + "')", timeout=30)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), guest_script, timeout=90)
        try:
            guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                      "-ExecutionPolicy", "Bypass", "-File", guest_script,
                      "-ReportPath", guest_result, timeout=150)
        except Exception as error:
            local_diagnostic = run_root / (lab_name + ".error.txt")
            try:
                guest.copy_from_guest(guest_result + ".error.txt", local_diagnostic, timeout=20)
                diagnostic = local_diagnostic.read_text(encoding="utf-8-sig").strip()
                if diagnostic.startswith("guest-script-error:") and len(diagnostic) < 128:
                    raise ValueError(diagnostic) from error
            except ValueError:
                raise
            except Exception:
                pass
            raise
        guest.copy_from_guest(guest_result, local_result, timeout=90)
    raw = local_result.read_bytes()
    if not 0 < len(raw) < 64 * 1024:
        raise ValueError("software-report-size-invalid:" + lab_name)
    report = validate_report(json.loads(raw.decode("utf-8-sig")), lab_name)
    return {
        "status": "passed", "machine": report["machine"], "os": report["os"],
        "memoryGiB": report["memoryGiB"], "diskCFreeGiB": report["diskCFreeGiB"],
        "vmwareTools": report["vmwareTools"],
        "elevatedToken": report.get("elevatedToken"),
        "tools": report["tools"],
        "report": str(local_result), "reportSha256": hashlib.sha256(raw).hexdigest(),
        "vmIdentity": {"vmx": identity["vmx"], "vmPid": identity["pid"]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=("lab1", "lab2", "all"), default="all")
    args = parser.parse_args(argv)
    if not GUEST_SCRIPT.is_file() or GUEST_SCRIPT.is_symlink():
        parser.error("guest software inventory script is unavailable")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = ARTIFACTS / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    result = {"schemaVersion": 1, "method": "read-only-software-inventory",
              "guestScriptSha256": hashlib.sha256(GUEST_SCRIPT.read_bytes()).hexdigest(),
              "run": str(run_root), "labs": {}}
    selected = ("lab1", "lab2") if args.lab == "all" else (args.lab,)
    for name in selected:
        try:
            result["labs"][name] = run_lab(name, run_root)
        except Exception as error:
            # The guest-session layer returns sanitized error classifications.
            result["labs"][name] = {"status": "failed", "reason": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if all(x["status"] == "passed" for x in result["labs"].values()) else 2


if __name__ == "__main__":
    sys.exit(main())
