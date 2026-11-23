"""Offline checks for bounded ApiAtlas hash comparison."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
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
                commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands, [
                ["git", "-C", str(folder), "ls-files", "--error-unmatch", "--", *module.FILES],
                ["git", "-C", str(folder), "rev-parse", "--verify", "HEAD"],
            ])
            self.assertEqual(manifest["sourceGitHead"], "123abc")
            self.assertEqual(list(manifest["files"]), list(module.FILES))
            self.assertEqual(manifest["files"]["UI.lua"]["sha256"],
                             hashlib.sha256(b"UI.lua").hexdigest().upper())

    def test_source_copy_can_be_hashed_without_git_or_tracking(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            for name in module.FILES:
                (folder / name).write_bytes(name.encode())
            with patch.object(module.subprocess, "run", side_effect=FileNotFoundError):
                no_git = module.source_manifest(folder)
            with patch.object(module.subprocess, "run") as run:
                run.return_value.returncode = 1
                untracked = module.source_manifest(folder)
                run.assert_called_once()
            self.assertIsNone(no_git["sourceGitHead"])
            self.assertEqual(len(no_git["files"]), 9)
            self.assertEqual(untracked, no_git)

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

    def test_wrong_cli_host_is_refused_before_source_or_installation_read(self):
        with (patch.object(module.socket, "gethostname", return_value="RIFT-STATION"),
              patch.object(module, "source_manifest") as source,
              patch.object(module, "run_pc") as pc,
              redirect_stdout(StringIO()) as report):
            self.assertEqual(module.main(["--expected-host", "OTHER-HOST"]), 2)
        source.assert_not_called()
        pc.assert_not_called()
        self.assertEqual(json.loads(report.getvalue())["targets"]["pc"]["error"], "host-mismatch")

    def test_cli_defaults_to_one_verified_local_installation(self):
        source = {"files": {name: {"bytes": 1, "sha256": "A" * 64} for name in module.FILES}}
        installed = {"complete": True, "machine": "RIFT-STATION", "files": [
            {"name": name, "status": "hashed", "sha256": "A" * 64} for name in module.FILES]}
        with (tempfile.TemporaryDirectory() as root,
              patch.object(module, "ROOT", Path(root) / "RR2 checkout"),
              patch.dict(module.os.environ, RR2_APIATLAS_SOURCE=""),
              patch.object(module.socket, "gethostname", return_value="RIFT-STATION"),
              patch.object(module, "source_manifest", return_value=source) as manifest,
              patch.object(module, "run_pc", return_value=installed) as pc,
              patch.object(module, "run_lab") as lab,
              redirect_stdout(StringIO()) as report):
            self.assertEqual(module.main(["--expected-host", "rift-station"]), 0)
        manifest.assert_called_once_with(Path(root) / "API Atlas/addon/ApiAtlas")
        pc.assert_called_once()
        lab.assert_not_called()
        result = json.loads(report.getvalue())
        self.assertEqual(list(result["targets"]), ["pc"])
        self.assertTrue(result["comparison"]["allCheckedTargetsMatchSource"])

    def test_configured_source_is_used_until_explicitly_overridden(self):
        with tempfile.TemporaryDirectory() as root:
            configured = Path(root) / "source folder"
            explicit = Path(root) / "explicit source"
            with patch.dict(module.os.environ, RR2_APIATLAS_SOURCE=str(configured)), \
                 patch.object(module, "source_manifest", side_effect=module.HashError("fixture")) as manifest, \
                 redirect_stdout(StringIO()):
                self.assertEqual(module.main([]), 2)
                self.assertEqual(module.main(["--source", str(explicit)]), 2)
            self.assertEqual([call.args for call in manifest.call_args_list], [(configured,), (explicit,)])

    def test_local_helper_uses_registered_folder_and_checks_report_identity(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "Redirected Documents" / "RIFT" / "Interface" / "AddOns"
            data = {"machine": "OTHER-HOST", "addonDirectory": str(folder / "ApiAtlas")}
            with (patch.object(module.observe_physical, "local_rift_addons_root", return_value=folder),
                  patch.object(module.socket, "gethostname", return_value="RIFT-STATION"),
                  patch.object(module.subprocess, "run") as run,
                  patch.object(module, "read_report", return_value=data)):
                run.return_value.returncode = 0
                with self.assertRaisesRegex(module.HashError, "unexpected-local-machine"):
                    module.run_pc(Path(root))
                command = run.call_args.args[0]
                self.assertEqual(command[command.index("-AddonDirectory") + 1], data["addonDirectory"])
                data["machine"] = "RIFT-STATION"
                data["addonDirectory"] = str(folder / "Unrelated")
                with self.assertRaisesRegex(module.HashError, "unexpected-local-addon-directory"):
                    module.run_pc(Path(root))

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell addon hashing")
    def test_local_helper_hashes_copied_files_and_leaves_them_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addons = root / "Redirected Documents" / "RIFT" / "Interface" / "AddOns"
            folder = addons / "ApiAtlas"
            folder.mkdir(parents=True)
            files = {name: name.encode() for name in module.FILES}
            for name, contents in files.items():
                (folder / name).write_bytes(contents)
            with patch.object(module.observe_physical, "local_rift_addons_root", return_value=addons):
                installed = module.run_pc(root)
            self.assertTrue(installed["complete"])
            self.assertEqual(
                {row["name"]: row["sha256"] for row in installed["files"]},
                {name: hashlib.sha256(contents).hexdigest().upper() for name, contents in files.items()},
            )
            self.assertEqual({path.name: path.read_bytes() for path in folder.iterdir()}, files)

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
