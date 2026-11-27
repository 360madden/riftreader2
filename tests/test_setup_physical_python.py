"""Check setup routing without installing any Python packages."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import setup_physical_python as tool


class PhysicalPythonSetupTests(unittest.TestCase):
    def test_wrong_host_creates_no_environment(self):
        with patch.object(tool.socket, "gethostname", return_value="LOCAL-PC"), \
                patch.object(tool, "setup") as setup, redirect_stdout(StringIO()) as output:
            self.assertEqual(tool.main(["--expected-host", "OTHER-PC", "--output-root", "new environment"]), 2)
        self.assertEqual(json.loads(output.getvalue())["reason"], "physical-host-mismatch")
        setup.assert_not_called()

    def test_never_installs_into_an_existing_root(self):
        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"), \
                patch.object(tool, "_run"), patch.object(tool, "_create_environment") as create:
            with self.assertRaises(FileExistsError):
                tool.setup(Path(temporary).resolve(), extras=("overlay",))
        create.assert_not_called()

    def test_setup_selects_existing_pin_files_and_returns_the_right_interpreters(self):
        def create_interpreter(path, _):
            python = path / "Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            if path.name == "overlay":
                python.with_name("pythonw.exe").touch()
            return python

        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"), \
                patch.object(tool, "_run", return_value="rerun-cli fixture") as run, \
                patch.object(tool, "_create_environment", side_effect=create_interpreter) as create:
            root = Path(temporary).resolve() / "new environments"
            result = tool.setup(root, extras=("overlay", "rerun", "validation"))
            self.assertTrue((root / ".ready").is_file())
        self.assertEqual([call.args[1] for call in create.call_args_list], [
            ("requirements-physical.txt",),
            ("requirements-overlay.txt", "requirements-capture.txt"),
            ("requirements-visualization.txt",),
            ("requirements-validation.txt",),
        ])
        validation = str(root / "validation/Scripts/python.exe")
        self.assertEqual(result, {"RIFTREADER2_PYTHON": str(root / "core/Scripts/python.exe"),
                                  "RR2_OVERLAY_PYTHON": str(root / "overlay/Scripts/pythonw.exe"),
                                  "RR2_DXCAM_PYTHON": str(root / "overlay/Scripts/python.exe"),
                                  "RR2_RERUN_PYTHON": str(root / "rerun/Scripts/python.exe"),
                                  "RIFTREADER2_LUA_PYTHON": validation})
        self.assertEqual([call.args[0] for call in run.call_args_list[-2:]], [
            [validation, "-B", str(tool.ROOT / "scripts/check_validation_python.py")],
            [validation, "-B", str(tool.ROOT / "scripts/check_lua_runtime.py")],
        ])

    def test_failed_optional_install_leaves_the_setup_unmarked(self):
        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"), \
                patch.object(tool, "_run"), patch.object(tool, "_create_environment") as create:
            root = Path(temporary).resolve() / "failed environments"
            create.side_effect = [root / "core/Scripts/python.exe", ValueError("optional install error")]
            with self.assertRaisesRegex(ValueError, "optional install error"):
                tool.setup(root, extras=("overlay",))
            self.assertFalse((root / ".ready").exists())

    def test_registration_refuses_partial_setup_and_preserves_existing_link_path(self):
        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"), \
                patch.object(tool, "_run") as run:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            setup = root / "short setup"
            core = setup / tool.INTERPRETERS["RIFTREADER2_PYTHON"]
            core.parent.mkdir(parents=True)
            core.touch()
            with patch.object(tool, "ROOT", checkout):
                with self.assertRaisesRegex(ValueError, "existing-physical-python-setup-incomplete"):
                    tool.use_existing(setup)
                (setup / ".ready").touch()
                existing = checkout / ".local" / "physical-python-link"
                existing.mkdir(parents=True)
                with self.assertRaisesRegex(ValueError, "Physical Python link already exists"):
                    tool.use_existing(setup)
                marker = existing / "user-file"
                marker.write_bytes(b"preserve directory contents")
                with self.assertRaisesRegex(ValueError, "requires-directory-junction"):
                    tool.use_existing(setup, replace_link=True)
                self.assertEqual(marker.read_bytes(), b"preserve directory contents")
                self.assertTrue(existing.is_dir())
            run.assert_not_called()

    def test_registration_checks_runtimes_before_creating_a_checkout_link(self):
        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"):
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            prepared = root / "copied environment"
            core = prepared / tool.INTERPRETERS["RIFTREADER2_PYTHON"]
            rerun = prepared / tool.INTERPRETERS["RR2_RERUN_PYTHON"]
            for python in (core, rerun):
                python.parent.mkdir(parents=True)
                python.touch()
            (prepared / ".ready").touch()
            with patch.object(tool, "ROOT", checkout):
                with patch.object(tool, "_run", side_effect=ValueError("core runtime unavailable")) as run:
                    with self.assertRaisesRegex(ValueError, "core runtime unavailable"):
                        tool.use_existing(prepared)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[0][0], str(core))
                    self.assertFalse((checkout / ".local").exists())
                with patch.object(tool, "_run", side_effect=["", "unrecognized version"]) as run:
                    with self.assertRaisesRegex(ValueError, "unrecognized version response"):
                        tool.use_existing(prepared)
                    self.assertEqual([call.args[0][0] for call in run.call_args_list], [str(core), str(rerun)])
                    self.assertFalse((checkout / ".local").exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows directory junctions")
    def test_link_replacement_restores_the_original_if_publication_fails(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            link = checkout / ".local/physical-python-link"
            link.parent.mkdir(parents=True)
            original, replacement = root / "old Python", root / "new Python"
            for directory in (original, replacement):
                python = directory / tool.INTERPRETERS["RIFTREADER2_PYTHON"]
                python.parent.mkdir(parents=True)
                python.write_bytes(directory.name.encode())
                (directory / ".ready").touch()
            rename = Path.rename

            def fail_publication(source, target):
                if source.name == "new" and target == link:
                    raise OSError("cannot publish junction")
                return rename(source, target)

            with patch.object(tool, "ROOT", checkout), patch.object(tool, "_check_environment"):
                tool._create_junction(link, original)
                try:
                    with patch.object(Path, "rename", autospec=True, side_effect=fail_publication):
                        with self.assertRaisesRegex(OSError, "cannot publish junction"):
                            tool.use_existing(replacement, replace_link=True)
                    self.assertEqual(link.resolve(strict=True), original)
                    self.assertEqual(list(link.parent.iterdir()), [link])
                    result = tool.use_existing(replacement, replace_link=True)
                    self.assertEqual(result["RIFTREADER2_PYTHON"],
                                     str(replacement / tool.INTERPRETERS["RIFTREADER2_PYTHON"]))
                    self.assertEqual(link.resolve(strict=True), replacement)
                    self.assertEqual(list(link.parent.iterdir()), [link])
                    for directory in (original, replacement):
                        self.assertEqual((directory / tool.INTERPRETERS["RIFTREADER2_PYTHON"]).read_bytes(),
                                         directory.name.encode())
                finally:
                    if tool._is_junction(tool._link_stat(link)):
                        link.rmdir()
