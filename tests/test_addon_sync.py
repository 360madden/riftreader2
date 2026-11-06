"""Offline regression checks for repository-owned addon synchronization."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("addon_sync", ROOT / "scripts" / "addon_sync.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class ManifestTests(unittest.TestCase):
    def test_current_manifest_is_exact_and_hashed(self):
        result = sync.manifest()
        self.assertEqual(tuple(result["files"]), sync.FILES)
        self.assertEqual(result["files"]["guidance.lua"], sync.sha256(sync.SOURCE / "guidance.lua"))

    def test_incomplete_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "RiftAddon.toc").write_text((sync.SOURCE / "RiftAddon.toc").read_text())
            with self.assertRaisesRegex(sync.AddonSyncError, "invalid-addon-source"):
                sync.manifest(source)

    def test_changed_load_order_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name in sync.FILES:
                shutil.copyfile(sync.SOURCE / name, source / name)
            toc = (source / "RiftAddon.toc")
            toc.write_text(toc.read_text().replace('"guidance.lua", "main.lua"',
                                                   '"main.lua", "guidance.lua"'))
            with self.assertRaisesRegex(sync.AddonSyncError, "load-order-changed"):
                sync.manifest(source)

    def test_guest_recall_flags_block_hash_preflight(self):
        guest = sync.GUEST_SCRIPT.read_text(encoding="utf-8")
        inspect = guest[guest.index("function Inspect-Installed"):guest.index("\ntry {\n", guest.index("function Inspect-Installed"))]
        self.assertIn("recallOnOpen=($flags -band 262144)", inspect)
        self.assertIn("recallOnDataAccess=($flags -band 4194304)", inspect)
        self.assertIn("unpinned=($flags -band 1048576)", inspect)
        self.assertLess(inspect.index("cloud-recall-risk"), inspect.index("Hash-File $p"))

    def test_incomplete_report_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "report.json"
            p.write_text(json.dumps({"schemaVersion": 1, "mode": "verify",
                                     "after": [{"name": "guidance.lua", "matches": True}]}))
            with self.assertRaisesRegex(sync.AddonSyncError, "files-incomplete"):
                sync.report_from_file(p, "lab1", {"mode": "verify"})


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell and attributes required")
class InstalledCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.dest = self.root / "dest"
        self.source.mkdir()
        self.dest.mkdir()
        for name in sync.FILES:
            shutil.copyfile(sync.SOURCE / name, self.source / name)
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(sync.manifest(self.source)))

    def run_script(self, mode):
        output = self.root / (mode + "-" + str(len(list(self.root.glob("*.json")))) + ".json")
        args = [sync.HOST_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(sync.GUEST_SCRIPT),
                "-Mode", mode, "-SourceDirectory", str(self.source), "-Destination", str(self.dest),
                "-ManifestPath", str(self.manifest_path), "-ReportPath", str(output),
                "-BackupDirectory", str(self.root / "backups"), "-NoPin"]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(output.read_text(encoding="utf-8-sig"))

    def test_check_detects_missing_then_sync_installs_and_verify_passes(self):
        before = self.run_script("check")
        self.assertFalse(before["success"])
        self.assertEqual({e["reason"] for e in before["after"]}, {"missing"})
        done = self.run_script("sync")
        self.assertTrue(done["success"], done)
        self.assertEqual(len(done["updated"]), len(sync.FILES))
        self.assertTrue(self.run_script("verify")["success"])

    def test_mismatch_backup_and_repair(self):
        for name in sync.FILES:
            shutil.copyfile(self.source / name, self.dest / name)
        (self.dest / "guidance.lua").write_text("wrong addon")
        done = self.run_script("sync")
        self.assertTrue(done["success"], done)
        self.assertEqual(done["updated"], ["guidance.lua"])
        old = list((self.root / "backups").glob("guidance.lua.*.backup"))
        self.assertEqual(len(old), 1)
        self.assertEqual(old[0].read_text(), "wrong addon")

    def test_invalid_candidate_refuses_changes(self):
        (self.source / "guidance.lua").write_text("bad source")
        done = self.run_script("sync")
        self.assertFalse(done["success"])
        self.assertFalse(any(self.dest.iterdir()))


if __name__ == "__main__":
    unittest.main()
