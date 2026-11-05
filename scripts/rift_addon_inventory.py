"""Metadata-only inventory of RIFT AddOns on PC, Lab-1 and Lab-2.

No addon content is opened or hashed, no game input is sent, and no VM/client
restart or UI reload is performed. Guest access reuses VM-specific credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
GUEST_SCRIPT = ROOT / "scripts" / "rift_addon_inventory_guest.ps1"
HOST_PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
GUEST_ADDONS = r"C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns"
GUEST_LOCAL = r"C:\Users\mrkoo\AppData\Local\RiftReader2\addon-inventory"


class InventoryError(RuntimeError):
    pass


def validate_report(data: dict, target: str) -> dict:
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise InventoryError("invalid-report-schema:" + target)
    if data.get("method") != "metadata-only" or data.get("success") is not True:
        raise InventoryError("inventory-failed:" + target + ":" + str(data.get("error")))
    if not isinstance(data.get("machine"), str) or not data["machine"]:
        raise InventoryError("missing-machine-identity:" + target)
    # Lab hostnames are independently bound to the two configured VMware targets.
    if target in ("lab1", "lab2") and data["machine"].casefold() != ("RIFT-LAB-" + target[-1]).casefold():
        raise InventoryError("unexpected-guest-machine:" + target)
    if (not isinstance(data.get("timestampUtc"), str) or not data["timestampUtc"]
            or not isinstance(data.get("addonRoot"), str) or not data["addonRoot"]
            or type(data.get("rootReparse")) is not bool):
        raise InventoryError("invalid-report-provenance:" + target)
    entries = data.get("entries")
    if not isinstance(entries, list) or len(entries) > 300:
        raise InventoryError("invalid-entry-list:" + target)
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise InventoryError("invalid-entry:" + target)
        name = item.get("name")
        if (not isinstance(name, str) or not name or name in (".", "..")
                or any(x in name for x in ("/", "\\", "\x00"))):
            raise InventoryError("invalid-entry-name:" + target)
        key = name.casefold()
        if key in seen:
            raise InventoryError("duplicate-entry-name:" + target)
        seen.add(key)
        if item.get("kind") not in ("file", "directory"):
            raise InventoryError("invalid-entry-kind:" + target)
        if type(item.get("offline")) is not bool or type(item.get("reparse")) is not bool:
            raise InventoryError("invalid-entry-flags:" + target)
        toc = item.get("toc")
        if not isinstance(toc, list) or len(toc) > 20:
            raise InventoryError("invalid-toc-list:" + target)
        seen_toc = set()
        for t in toc:
            if not isinstance(t, dict):
                raise InventoryError("invalid-toc-entry:" + target)
            name = t.get("name")
            if (not isinstance(name, str) or not name or name in (".", "..")
                    or any(x in name for x in ("/", "\\", "\x00"))):
                raise InventoryError("invalid-toc-name:" + target)
            if name.casefold() in seen_toc:
                raise InventoryError("duplicate-toc-name:" + target)
            seen_toc.add(name.casefold())
            if (type(t.get("bytes")) is not int or t["bytes"] < 0
                    or not isinstance(t.get("modifiedUtc"), str) or not t["modifiedUtc"]):
                raise InventoryError("invalid-toc-metadata:" + target)
            if type(t.get("offline")) is not bool or type(t.get("reparse")) is not bool:
                raise InventoryError("invalid-toc-flags:" + target)
    if (type(data.get("complete")) is not bool or not isinstance(data.get("warnings"), list)
            or any(not isinstance(w, str) for w in data["warnings"])):
        raise InventoryError("invalid-completeness:" + target)
    data["target"] = target
    return data


def read_report(path: Path, target: str) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise InventoryError("invalid-report-file:" + target) from error
    return validate_report(raw, target)


def run_pc(run_root: Path, folder: Path | None = None) -> dict:
    addon_root = folder or (Path.home() / "OneDrive" / "Documents" / "RIFT"
                            / "Interface" / "AddOns")
    report = run_root / "pc.json"
    completed = subprocess.run(
        [HOST_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(GUEST_SCRIPT), "-AddonRoot", str(addon_root),
         "-ReportPath", str(report)],
        capture_output=True, text=True, timeout=90, check=False)
    if completed.returncode:
        raise InventoryError("pc-inspector-exited:" + str(completed.returncode))
    return read_report(report, "pc")


def run_lab(target: str, run_root: Path) -> dict:
    from lab_codex import LabCodex
    from vmware_guest_session import POWERSHELL

    lab = LabCodex()
    _, _, config, settings = lab._configuration(target)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    run_id = "inventory-" + uuid.uuid4().hex
    work = GUEST_LOCAL + "\\" + run_id
    script_path = work + r"\rift_addon_inventory_guest.ps1"
    report_path = work + r"\report.json"
    report = run_root / (target + ".json")
    # _session refreshes this exact VM's cached-credential source on every entry.
    with lab._session(config, settings, identity, doctor) as guest:
        guest.powershell("$ErrorActionPreference='Stop';[void](New-Item -ItemType Directory "
                         "-Path '" + work + "' -Force)", timeout=90)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), script_path, timeout=90)
        guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-File", script_path,
                  "-AddonRoot", GUEST_ADDONS, "-ReportPath", report_path,
                  timeout=150)
        guest.copy_from_guest(report_path, report, timeout=90)
    return read_report(report, target)


def compare_names(results: dict) -> list[dict]:
    available = {target: value for target, value in results.items()
                 if value.get("success") is True}
    if not available:
        return []
    keys: dict[str, str] = {}
    for value in available.values():
        for item in value["entries"]:
            keys.setdefault(item["name"].casefold(), item["name"])
    rows = []
    for key in sorted(keys):
        present = [target for target, value in available.items()
                   if any(item["name"].casefold() == key for item in value["entries"])]
        if len(present) != len(available):
            rows.append({"name": keys[key], "presentOn": present,
                         "missingOn": [target for target in available if target not in present]})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("pc", "lab1", "lab2", "all"), default="all")
    parser.add_argument("--pc-folder", type=Path, help="Local test/alternate AddOns directory")
    args = parser.parse_args(argv)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = ROOT / "artifacts" / "addon-inventory" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    targets = ("pc", "lab1", "lab2") if args.target == "all" else (args.target,)
    results = {}
    for target in targets:
        try:
            report = (run_pc(run_root, args.pc_folder) if target == "pc"
                      else run_lab(target, run_root))
            results[target] = {
                "success": True, "complete": report["complete"],
                "machine": report["machine"], "entries": report["entries"],
                "timestampUtc": report["timestampUtc"], "addonRoot": report["addonRoot"],
                "rootReparse": report["rootReparse"],
                "warnings": report["warnings"], "report": str(run_root / (target + ".json"))
            }
        except Exception as error:
            results[target] = {"success": False, "error": str(error)}
    output = {
        "schemaVersion": 1, "method": "metadata-only", "run": str(run_root),
        "targets": {t: {k: v for k, v in row.items() if k != "entries"}
                    | ({"count": len(row["entries"])} if row.get("success") else {})
                    for t, row in results.items()},
        "nameDifferences": compare_names(results),
        "note": "Names and TOC metadata only; no Lua content parity or game-load proof."
    }
    print(json.dumps(output, indent=2))
    if not all(row["success"] for row in results.values()):
        return 2
    return 0 if all(row["complete"] for row in results.values()) else 3


if __name__ == "__main__":
    sys.exit(main())

