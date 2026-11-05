"""Offline checks for bounded ApiAtlas hash comparison."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rift_addon_hash as module


class HashTests(unittest.TestCase):
    def test_source_manifest_has_nine_allowlisted_files_only(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "repo" / "addon" / "ApiAtlas"
            folder.mkdir(parents=True)
            for name in module.FILES:
                (folder / name).write_bytes(name.encode())
            (folder / "fonts").mkdir()
            (folder / "fonts" / "ignored.ttf").write_bytes(b"font")
            with patch.object(module.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "123abc\n"
                manifest = module.source_manifest(folder)
            self.assertEqual(list(manifest["files"]), list(module.FILES))
            self.assertEqual(manifest["files"]["UI.lua"]["sha256"],
                             hashlib.sha256(b"UI.lua").hexdigest().upper())

    def test_source_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            for name in module.FILES:
                (folder / name).write_bytes(b"x")
            (folder / "UI.lua").write_bytes(b"x" * (module.MAX_FILE + 1))
            with self.assertRaisesRegex(module.HashError, "source-size-limit:UI.lua"):
                module.source_manifest(folder)

    def test_reject_wrong_lab_identity(self):
        data = {"schemaVersion": 1, "method": "sha256-read-only", "addon": "ApiAtlas",
                "machine": "RIFT-LAB-2", "timestampUtc": "now", "complete": True,
                "files": [{"name": name, "status": "hashed", "sha256": "A" * 64}
                          for name in module.FILES]}
        with self.assertRaisesRegex(module.HashError, "wrong-guest-machine"):
            module.validate_report(data, "lab1")

    def test_drift_even_when_three_installs_match(self):
        source = {"files": {name: {"bytes": 1, "sha256": "A" * 64}
                            for name in module.FILES}}
        files = [{"name": name, "status": "hashed", "sha256": "B" * 64}
                 for name in module.FILES]
        results = {target: {"files": files} for target in ("pc", "lab1", "lab2")}
        comparison = module.compare(source, results)
        self.assertFalse(comparison["allMachinesMatchSource"])
        self.assertTrue(all(row["threeMachineParity"] for row in comparison["files"]))
        self.assertTrue(all(not any(row["matchesSource"].values()) for row in comparison["files"]))


if __name__ == "__main__":
    unittest.main()
