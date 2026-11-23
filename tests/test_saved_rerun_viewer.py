"""Optional viewer invocation checks; no SDK, real process or desktop access."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from scripts import save_physical_route_view as saved


class SavedRerunViewerTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.recording = self.root / "saved view.rrd"
        self.recording.write_bytes(b"retained-test-recording")
        self.python = self.root / "python.exe"
        self.viewer = self.root / "rerun.exe"
        self.viewer.write_bytes(b"not-executed")
        self.enterContext(patch.object(os, "environ", dict(os.environ, RR2_RERUN_PYTHON="")))
        self.addCleanup(patch.stopall)
        patch.object(saved, "VISUALIZATION_PYTHON", self.python).start()
        self.probe = patch.object(saved.subprocess, "run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="rerun-cli 0.43.1\n", stderr="")).start()
        self.process = patch.object(saved.subprocess, "Popen", return_value=Mock()).start()

    def test_explicit_viewer_uses_local_binding_and_child_only_analytics_opt_out(self):
        with patch.object(os, "environ", dict(os.environ, CI="prior", FORCE_RERUN_ANALYTICS="1")):
            child = saved.launch_saved_rerun(self.recording)
            self.assertIs(child, self.process.return_value)
            args, options = self.process.call_args
            self.assertEqual(args[0], [str(self.viewer), "--bind", "127.0.0.1", "--port", "auto", str(self.recording)])
            self.assertEqual(self.probe.call_args.args[0], [str(self.viewer), "--version"])
            self.assertEqual(self.probe.call_args.kwargs["env"], options["env"])
            self.assertEqual(options["env"]["CI"], "1")
            self.assertNotIn("FORCE_RERUN_ANALYTICS", options["env"])
            self.assertEqual(os.environ["CI"], "prior")
            self.assertEqual(os.environ["FORCE_RERUN_ANALYTICS"], "1")
            self.assertEqual(options["stdin"], saved.subprocess.DEVNULL)
            self.assertEqual(options["stdout"], saved.subprocess.DEVNULL)
            self.assertEqual(options["stderr"], saved.subprocess.DEVNULL)
            self.assertNotIn("shell", options)

    def test_configured_python_runs_its_viewer_module(self):
        python = self.root / "another environment" / "python.exe"
        python.parent.mkdir()
        python.touch()
        with patch.object(os, "environ", dict(os.environ, RR2_RERUN_PYTHON=str(python))):
            saved.launch_saved_rerun(self.recording)
        self.assertEqual(self.probe.call_args.args[0], [str(python), "-m", "rerun", "--version"])
        self.assertEqual(self.process.call_args.args[0],
                         [str(python), "-m", "rerun", "--bind", "127.0.0.1", "--port", "auto",
                          str(self.recording)])

    def test_configured_python_without_rerun_reports_failure_before_launch(self):
        self.python.touch()
        self.probe.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="python.exe: No module named rerun\n")
        with patch.dict(os.environ, RR2_RERUN_PYTHON=str(self.python)):
            with self.assertRaisesRegex(ValueError, "No module named rerun"):
                saved.launch_saved_rerun(self.recording)
        self.process.assert_not_called()

    def test_unresponsive_viewer_reports_timeout_before_launch(self):
        self.probe.side_effect = subprocess.TimeoutExpired([str(self.viewer), "--version"], 8)
        with self.assertRaisesRegex(ValueError, "viewer-startup-timed-out"):
            saved.launch_saved_rerun(self.recording)
        self.process.assert_not_called()

    def test_invalid_configured_python_refuses_before_launch(self):
        with patch.object(os, "environ", dict(os.environ, RR2_RERUN_PYTHON="relative/python.exe")):
            with self.assertRaisesRegex(ValueError, "invalid-rerun-python-path"):
                saved.launch_saved_rerun(self.recording)
        self.process.assert_not_called()
        self.probe.assert_not_called()

    def test_missing_empty_relative_and_wrong_type_recordings_never_launch(self):
        empty = self.root / "empty.rrd"
        empty.touch()
        for path in (self.root / "missing.rrd", empty, Path("relative.rrd"), self.root / "saved.png",
                     Path(r"\\server\share\saved.rrd")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                saved.launch_saved_rerun(path)
        self.process.assert_not_called()

    def test_optional_viewer_absence_is_an_explanation_not_an_install(self):
        self.viewer.unlink()
        with self.assertRaisesRegex(ValueError, "optional-rerun-viewer-not-installed"):
            saved.launch_saved_rerun(self.recording)
        self.process.assert_not_called()

    def test_viewer_dependency_check_needs_no_recording_and_opens_no_window(self):
        self.recording.unlink()
        viewer, _, version = saved.check_rerun_viewer()
        self.assertEqual(viewer, [str(self.viewer)])
        self.assertEqual(version, "rerun-cli 0.43.1")
        self.assertEqual(self.probe.call_args.args[0], [str(self.viewer), "--version"])
        self.process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
