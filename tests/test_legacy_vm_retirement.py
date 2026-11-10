"""Offline regression checks: retired VM CLI paths must fail before side effects."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_movement_session as legacy_movement
from scripts import run_targeted_click as legacy_click
from scripts import run_xyz_workflow as legacy_xyz


class RetiredVmEntryPointTests(unittest.TestCase):
    def test_legacy_movement_cli_refuses_before_creating_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "movement"
            commands = (
                ["prepare", "--host-plan", "missing.json", "--feedback-pin", "missing.json",
                 "--output", str(output), "--mode", "calibration"],
                ["run-reviewed", "--session-plan", "missing.json", "--review", "missing.json",
                 "--output", str(output)],
            )
            for arguments in commands:
                with self.subTest(command=arguments[0]):
                    with patch.object(sys, "argv", ["run_movement_session.py", *arguments]):
                        with self.assertRaisesRegex(legacy_movement.MovementSessionError,
                                                    "vmware-retired-use-physical-rift"):
                            legacy_movement.main()
                    self.assertFalse(output.exists())

    def test_all_legacy_click_routes_refuse_before_creating_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "click"
            for lab in (None, "lab1", "lab2"):
                with self.subTest(lab=lab):
                    with self.assertRaisesRegex(ValueError, "vmware-retired-use-physical-rift"):
                        legacy_click.run("missing.json", output, [1, 1, 4, 4], managed_lab=lab)
                    self.assertFalse(output.exists())

    def test_legacy_xyz_live_cli_refuses_before_config_read(self):
        with redirect_stderr(io.StringIO()) as errors:
            code = legacy_xyz.main(["--config", "missing.json", "--run", "--session-id", "a" * 32])
        self.assertEqual(code, 2)
        self.assertIn("vmware-retired-use-physical-rift", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
