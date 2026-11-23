"""Offline regression checks for repository-owned addon synchronization."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("addon_sync", ROOT / "scripts" / "addon_sync.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class ManifestTests(unittest.TestCase):
    def test_current_manifest_is_exact_and_hashed(self):
        result = sync.manifest()
        self.assertEqual(tuple(result["files"]), sync.FILES)
        self.assertEqual(result["files"]["guidance.lua"],
                         sync.sha256((sync.SOURCE / "guidance.lua").read_bytes()))

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


class LocalCommandTests(unittest.TestCase):
    def test_check_defaults_to_the_verified_local_pc(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(sync, "ROOT", Path(directory)), \
             patch.object(sync.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(sync, "manifest", return_value={}), \
             patch.object(sync, "run_pc", return_value={
                 "success": True, "updated": [], "after": [], "report": "pc-result.json",
                 "machine": "RIFT-STATION", "destination": "Local addons"}) as pc, \
             patch.object(sync, "run_lab") as lab, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(sync.main(["check", "--expected-host", "rift-station"]), 0)
        self.assertEqual(pc.call_args.args[0], "check")
        lab.assert_not_called()
        result = json.loads(output.getvalue())["targets"]
        self.assertEqual(list(result), ["pc"])
        self.assertEqual(result["pc"]["machine"], "RIFT-STATION")

    def test_wrong_host_refuses_before_creating_a_manifest(self):
        with patch.object(sync.socket, "gethostname", return_value="RIFT-STATION"), \
             patch.object(sync, "manifest") as manifest, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(sync.main(["verify", "--expected-host", "ANOTHER-PC"]), 2)
        manifest.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["targets"]["pc"]["error"], "host-mismatch")

    def test_sync_requires_an_explicit_target(self):
        with patch.object(sync, "manifest") as manifest, redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:
                sync.main(["sync"])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("sync requires an explicit --target", error.getvalue())
        manifest.assert_not_called()


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

    def test_pc_check_uses_redirected_documents_and_verifies_plain_files(self):
        documents = self.root / "Redirected Documents"
        installed = documents / "RIFT" / "Interface" / "AddOns" / "RiftReader2"
        shutil.copytree(self.source, installed)
        with patch.object(sync.observe_physical, "_run", return_value=(0, str(documents) + "\r\n")) as locator:
            result = sync.run_pc("check", self.root, self.source, self.manifest_path)
        self.assertIn("[Environment]::GetFolderPath('MyDocuments')", locator.call_args.args[0][-1])
        self.assertTrue(result["success"], result["after"])
        self.assertEqual(result["updated"], [])
        self.assertEqual(result["destination"], str(installed))
        self.assertTrue(all(not entry["pinned"] and entry["matches"] for entry in result["after"]))

    def test_pc_check_explains_line_endings_without_passing_byte_parity(self):
        for name in sync.FILES:
            shutil.copyfile(self.source / name, self.dest / name)
        toc = self.dest / "RiftAddon.toc"
        line_feeds = toc.read_bytes().replace(b"\r\n", b"\n")
        toc.write_bytes(line_feeds.replace(b"\n", b"\r\n"))
        reference = self.dest / "reference.lua"
        reference.write_bytes(reference.read_bytes() + b"\n-- local edit\n")
        expected = sync.manifest(self.source)
        with patch.object(sync, "ROOT", self.root), patch.object(sync, "SOURCE", self.source), \
             patch.object(sync, "manifest", return_value=expected), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(sync.main(["verify", "--pc-folder", str(self.dest)]), 2)
        result = json.loads(stdout.getvalue())["targets"]["pc"]
        self.assertFalse(result["success"])
        self.assertEqual(result["issues"], [
            {"RiftAddon.toc": "hash-mismatch"}, {"reference.lua": "hash-mismatch"},
        ])
        self.assertEqual(result["lineEndingOnly"], ["RiftAddon.toc"])

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
