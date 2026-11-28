"""File-only recovery regression tests; no game installation or processes required."""
import copy
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

    def shared_cycle(self, *, changed=False, edit_first=None):
        prefix = "fixture"
        before_sha, old_exe, new_exe = "a" * 64, "b" * 64, "c" * 64
        snapshot = {"schema": "update-helper.game-files.v1", "host": self.host,
                    "root": str(self.root / "game"), "phase": "after", "complete": True,
                    "files": [{"path": "rift_x64.exe", "size": 10, "sha256": new_exe},
                              {"path": "asset.dat", "size": 20, "sha256": "e" * 64}]}
        first = copy.deepcopy(snapshot)
        if edit_first is not None:
            edit_first(first)
        _, a_sha = self.save(f"{prefix}-after-a.json", first)
        _, b_sha = self.save(f"{prefix}-after-b.json", snapshot)
        common = {"schema": "update-helper.comparison.v1", "host": self.host,
                  "root": snapshot["root"],
                  "counts": {"added": 0, "removed": 0, "modified": int(changed), "unchanged": 2}}
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

    def test_shared_zero_counts_do_not_override_actual_snapshot_disagreement(self):
        for edit in (
                lambda s: s["files"][1].update(sha256="f" * 64),
                lambda s: s["files"][1].update(size=21),
                lambda s: s["files"].pop()):
            with self.subTest(edit=edit):
                prefix, before, old, *_ = self.shared_cycle(edit_first=edit)
                with self.assertRaisesRegex(ValueError, "contents disagree"):
                    recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_first_shared_capture_identity_and_completeness_required(self):
        for edit, reason in (
                (lambda s: s.update(host="WRONG-HOST"), "host mismatch"),
                (lambda s: s.update(root="wrong-root"), "root mismatch"),
                (lambda s: s.update(complete=False), "Incomplete"),
                (lambda s: s.update(phase="before"), "Incomplete"),
                (lambda s: s.update(schema="unsupported"), "unsupported")):
            with self.subTest(reason=reason):
                prefix, before, old, *_ = self.shared_cycle(edit_first=edit)
                with self.assertRaisesRegex(ValueError, reason):
                    recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_shared_inventory_rejects_duplicate_paths_and_invalid_fingerprints(self):
        for edit, reason in (
                (lambda s: s["files"].append(copy.deepcopy(s["files"][1])),
                 "duplicate shared file path"),
                (lambda s: s["files"][1].update(size=True), "Invalid shared file fingerprint"),
                (lambda s: s["files"][1].update(size=-1), "Invalid shared file fingerprint"),
                (lambda s: s["files"][1].update(sha256="invalid"), "Invalid shared file fingerprint")):
            with self.subTest(reason=reason):
                prefix, before, old, *_ = self.shared_cycle(edit_first=edit)
                with self.assertRaisesRegex(ValueError, reason):
                    recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_shared_content_comparison_ignores_order_and_mtime(self):
        def edit(s):
            s["files"].reverse()
            s["files"][0]["mtime_ns"] = 123
        prefix, before, old, *_ = self.shared_cycle(edit_first=edit)
        recovery.read_shared_cycle(self.root, prefix, before, old)

    def test_metadata_rejects_duplicate_rows_and_boolean_size(self):
        game = self.root / "game"
        game.mkdir()
        asset = game / "asset.dat"
        asset.write_bytes(b"a")
        row = {"path": asset.name, "size": 1, "mtime_ns": asset.stat().st_mtime_ns}
        recovery.check_current_metadata(game, {"files": [row]})
        with self.assertRaisesRegex(ValueError, "duplicate shared file path"):
            recovery.check_current_metadata(game, {"files": [row, row]})
        with self.assertRaisesRegex(ValueError, "Invalid shared file metadata"):
            recovery.check_current_metadata(game, {"files": [dict(row, size=True)]})

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
