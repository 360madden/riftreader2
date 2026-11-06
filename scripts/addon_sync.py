"""Safely compare and deploy the repository Lua addon to the PC and two RIFT labs.

No game input or reload is performed. Live RIFT must be reloaded separately after sync.
Guest access uses the existing VM-specific cached-credential and identity checks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "addon" / "RiftReader2"
GUEST_SCRIPT = ROOT / "scripts" / "addon_sync_guest.ps1"
FILES = ("RiftAddon.toc", "wire.lua", "producer.lua", "reference.lua", "live.lua", "guidance.lua", "main.lua")
GUEST_ADDON = r"C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2"
GUEST_LOCAL = r"C:\Users\mrkoo\AppData\Local\RiftReader2\addon-sync"
HOST_PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


class AddonSyncError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def manifest(source: Path = SOURCE) -> dict:
    toc = (source / "RiftAddon.toc").read_text(encoding="utf-8")
    match = re.search(r'^RunOnStartup\s*=\s*\{([^\r\n}]*)\}\s*$', toc, re.M)
    if not match:
        raise AddonSyncError("addon-manifest-load-list-missing")
    entries = re.findall(r'"([^"]+)"', match.group(1))
    if entries != list(FILES[1:]):
        raise AddonSyncError("addon-manifest-load-order-changed")
    hashes = {}
    for name in FILES:
        path = source / name
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise AddonSyncError("invalid-addon-source:" + name)
        hashes[name] = sha256(path)
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=False)
    return {"schemaVersion": 1, "gitHead": git.stdout.strip() if git.returncode == 0 else None,
            "files": hashes}


def report_from_file(path: Path, target: str, data: dict) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise AddonSyncError("invalid-target-report:" + target) from error
    names = {entry.get("name") for entry in result.get("after", [])}
    if result.get("schemaVersion") != 1 or result.get("mode") != data["mode"]:
        raise AddonSyncError("target-report-identity-invalid:" + target)
    if result.get("error"):
        raise AddonSyncError("target-operation-failed:" + target + ":" + str(result["error"]))
    if result.get("after") and names != set(FILES):
        raise AddonSyncError("target-report-files-incomplete:" + target)
    result["target"] = target
    result["report"] = str(path)
    return result


def run_pc(mode: str, run_root: Path, source: Path, manifest_path: Path,
           *, folder: Path | None = None, no_pin: bool = False) -> dict:
    target = folder or (Path.home() / "OneDrive" / "Documents" / "RIFT"
                        / "Interface" / "AddOns" / "RiftReader2")
    if not target.is_dir():
        raise AddonSyncError("main-pc-addon-directory-missing")
    report = run_root / "pc-result.json"
    backup = run_root / "pc-backups"
    argv = [HOST_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(GUEST_SCRIPT), "-Mode", mode,
            "-SourceDirectory", str(source), "-Destination", str(target),
            "-ManifestPath", str(manifest_path), "-ReportPath", str(report),
            "-BackupDirectory", str(backup)]
    if no_pin:
        argv.append("-NoPin")
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=150)
    if completed.returncode != 0:
        raise AddonSyncError("main-pc-script-exited:" + str(completed.returncode))
    return report_from_file(report, "pc", {"mode": mode})


def run_lab(lab_name: str, mode: str, run_root: Path, source: Path,
            manifest_path: Path, *, guest_folder: str = GUEST_ADDON) -> dict:
    from lab_codex import LabCodex
    from vmware_guest_session import POWERSHELL

    lab = LabCodex()
    _, _, config, settings = lab._configuration(lab_name)
    doctor = lab.run_root / ".doctor"
    native = lab._native(config, settings, doctor)
    identity = lab.collect_identity(native)
    run_id = "rr2-" + uuid.uuid4().hex
    work = GUEST_LOCAL + "\\" + run_id
    guest_script = work + r"\addon_sync_guest.ps1"
    guest_manifest = work + r"\manifest.json"
    guest_report = work + r"\report.json"
    guest_backup = GUEST_LOCAL + r"\backups" + "\\" + run_id
    report = run_root / (lab_name + "-result.json")

    # _session checks this lab's current and legacy VM-specific credential
    # targets afresh on *every* entry; no credentials enter reports or argv here.
    with lab._session(config, settings, identity, doctor) as guest:
        guest.powershell("$ErrorActionPreference='Stop';[void](New-Item -ItemType Directory "
                         "-Path '" + work + "' -Force)", timeout=90)
        guest.run("copyFileFromHostToGuest", str(GUEST_SCRIPT), guest_script, timeout=90)
        guest.run("copyFileFromHostToGuest", str(manifest_path), guest_manifest, timeout=90)
        if mode == "sync":
            for name in FILES:
                guest.run("copyFileFromHostToGuest", str(source / name),
                          work + "\\" + name, timeout=90)
        guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                  "-ExecutionPolicy", "Bypass", "-File", guest_script,
                  "-Mode", mode, "-SourceDirectory", work,
                  "-Destination", guest_folder, "-ManifestPath", guest_manifest,
                  "-ReportPath", guest_report, "-BackupDirectory", guest_backup,
                  timeout=150)
        guest.copy_from_guest(guest_report, report, timeout=90)
    return report_from_file(report, lab_name, {"mode": mode})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "sync", "verify"))
    parser.add_argument("--target", choices=("pc", "lab1", "lab2", "all"), default="all")
    parser.add_argument("--pc-folder", type=Path, help="Override the detected local RIFT addon folder")
    args = parser.parse_args(argv)

    expected = manifest()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_root = ROOT / "artifacts" / "addon-sync" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")

    targets = ("pc", "lab1", "lab2") if args.target == "all" else (args.target,)
    results = {}
    for target in targets:
        try:
            result = (run_pc(args.action, run_root, SOURCE, manifest_path, folder=args.pc_folder)
                      if target == "pc" else run_lab(target, args.action, run_root, SOURCE, manifest_path))
            results[target] = {"success": bool(result["success"]), "updated": result["updated"],
                               "issues": [{e["name"]: e["reason"]} for e in result["after"]
                                          if not e["matches"]], "report": result["report"]}
        except Exception as error:
            # Preserve later targets and do not print VM credentials or raw arguments.
            results[target] = {"success": False, "error": str(error)}
    print(json.dumps({"action": args.action, "run": str(run_root), "targets": results}, indent=2))
    return 0 if all(v["success"] for v in results.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
