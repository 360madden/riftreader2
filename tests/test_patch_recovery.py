"""File-only recovery regression tests; no game installation or processes required."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import patch_recovery as recovery


class PatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.host = socket.gethostname().upper()

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, recovery.digest(path)

    def shared_cycle(self, *, changed=False):
        prefix = "fixture"
        before_sha, old_exe, new_exe = "a" * 64, "b" * 64, "c" * 64
        snapshot = {"schema": "update-helper.game-files.v1", "host": self.host,
                    "root": str(self.root / "game"), "phase": "after", "complete": True,
                    "files": [{"path": "rift_x64.exe", "sha256": new_exe}]}
        _, a_sha = self.save(f"{prefix}-after-a.json", snapshot)
        _, b_sha = self.save(f"{prefix}-after-b.json", snapshot)
        common = {"schema": "update-helper.comparison.v1", "host": self.host,
                  "root": snapshot["root"],
                  "counts": {"added": 0, "removed": 0, "modified": int(changed), "unchanged": 1}}
        _, consistency_sha = self.save(f"{prefix}-consistency.json",
            dict(common, before_manifest_sha256=a_sha, after_manifest_sha256=b_sha))
        _, changes_sha = self.save(f"{prefix}-changes.json",
            dict(common, before_manifest_sha256=before_sha, after_manifest_sha256=b_sha,
                 consistency_manifest_sha256=consistency_sha,
                 before_executable_sha256=old_exe, after_executable_sha256=new_exe))
        return prefix, before_sha, old_exe, new_exe, changes_sha

    def test_rejects_wrong_host_before_creating_output(self):
        cfg, _ = self.save("checkpoint.json", {"schemaVersion": 1, "expectedHost": "NOT-THIS-HOST"})
        with self.assertRaisesRegex(ValueError, "Wrong host"):
            recovery.recover(cfg, "fixture", root=self.root)
        self.assertFalse((self.root / "artifacts").exists())

    def test_rejects_invalid_prefix_and_tampered_json(self):
        with self.assertRaisesRegex(ValueError, "Invalid attempt"):
            recovery.safe_prefix("../bad")
        doc, sha = self.save("pinned.json", {"a": 1})
        doc.write_text('{"a": 2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            recovery.read_json(doc, sha)
        doc.write_text('{"a": 1, "a": 2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            recovery.read_json(doc)

    def test_shared_cycle_pins_and_executable_identity(self):
        prefix, before, old, new, report_sha = self.shared_cycle()
        report, sha, *_ = recovery.read_shared_cycle(self.root, prefix, before, old)
        self.assertEqual(report["after_executable_sha256"], new)
        self.assertEqual(sha, report_sha)
        with self.assertRaisesRegex(ValueError, "baseline link mismatch"):
            recovery.read_shared_cycle(self.root, prefix, "d" * 64, old)
        with self.assertRaisesRegex(ValueError, "old executable mismatch"):
            recovery.read_shared_cycle(self.root, prefix, before, "d" * 64)
        (self.root / f"{prefix}-after-b.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_unstable_shared_capture_is_refused(self):
        prefix, before, old, *_ = self.shared_cycle(changed=True)
        with self.assertRaisesRegex(ValueError, "snapshots disagree"):
            recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_stale_data_only_metadata_is_refused(self):
        game = self.root / "game"
        game.mkdir()
        binary = game / "rift_x64.exe"
        binary.write_bytes(b"unchanged")
        asset = game / "asset.dat"
        asset.write_bytes(b"original")
        manifest = {"files": [
            {"path": p.name, "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
            for p in (binary, asset)]}
        recovery.check_current_metadata(game, manifest)
        added = game / "new.dat"
        added.write_bytes(b"new")
        with self.assertRaisesRegex(ValueError, "take a fresh shared capture"):
            recovery.check_current_metadata(game, manifest)
        added.unlink()
        asset.write_bytes(b"modified asset")
        with self.assertRaisesRegex(ValueError, "take a fresh shared capture"):
            recovery.check_current_metadata(game, manifest)

    def test_installed_addon_baseline_and_line_endings_are_distinct(self):
        backup = self.root / "backup"
        backup.mkdir()
        entries = []
        for name in sorted(recovery.ADDON_FILES):
            path = backup / name
            path.write_bytes(b"original\r\n")
            entries.append({"name": name, "present": True, "pinned": True, "offline": False,
                            "sha256": recovery.digest(path).upper()})
        receipt = {"mode": "check", "machine": self.host, "after": entries,
                   "destination": str(self.root / "installed")}
        before, sha = self.save("backup/receipt.json", receipt)
        cfg = {"installedAddonReceipt": str(before.relative_to(self.root)),
               "installedAddonReceiptSha256": sha}
        baseline, facts, _ = recovery.installed_addon_baseline(cfg, self.root, self.host)
        current, _ = self.save("artifacts/addon-sync/fixture/pc-result.json", receipt)
        result = subprocess.CompletedProcess([], 2, stdout=json.dumps({"targets": {"pc": {
            "report": str(current), "success": False, "lineEndingOnly": ["live.lua"]}}}).encode())
        comparison = recovery.compare_installed_addon(result, self.root, self.host, baseline, facts)
        self.assertEqual(comparison["status"], "unchanged")
        self.assertFalse(comparison["exactRepositoryMatch"])
        self.assertEqual(comparison["lineEndingOnlyVsRepo"], ["live.lua"])

        observed = json.loads(current.read_text(encoding="utf-8"))
        next(item for item in observed["after"] if item["name"] == "live.lua")["sha256"] = "E" * 64
        current.write_text(json.dumps(observed), encoding="utf-8")
        comparison = recovery.compare_installed_addon(result, self.root, self.host, baseline, facts)
        self.assertEqual(comparison["status"], "changed")
        self.assertEqual(comparison["changed"], ["live.lua"])

        (backup / "live.lua").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "baseline copy mismatch"):
            recovery.installed_addon_baseline(cfg, self.root, self.host)

    def test_missing_addon_receipt_is_not_success(self):
        result = subprocess.CompletedProcess([], 2, stdout=b'{"targets":{}}')
        report = recovery.compare_installed_addon(result, self.root, self.host, {}, {})
        self.assertEqual(report["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
