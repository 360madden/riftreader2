"""Check setup routing without installing any Python packages."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
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
                tool.setup(Path(temporary), extras=("overlay",))
        create.assert_not_called()

    def test_setup_selects_existing_pin_files_and_returns_the_right_interpreters(self):
        with TemporaryDirectory() as temporary, patch.object(tool.sys, "platform", "win32"), \
                patch.object(tool, "_run", return_value="rerun-cli fixture") as run, \
                patch.object(tool, "_create_environment", side_effect=lambda path, _: path / "Scripts/python.exe") as create:
            root = Path(temporary) / "new environments"
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
            root = Path(temporary) / "failed environments"
            create.side_effect = [root / "core/Scripts/python.exe", ValueError("optional install error")]
            with self.assertRaisesRegex(ValueError, "optional install error"):
                tool.setup(root, extras=("overlay",))
            self.assertFalse((root / ".ready").exists())
