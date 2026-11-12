"""Optional viewer invocation checks; no SDK, real process or desktop access."""
import os
from pathlib import Path
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
        self.addCleanup(patch.stopall)
        patch.object(saved, "VISUALIZATION_PYTHON", self.python).start()
        self.process = patch.object(saved.subprocess, "Popen", return_value=Mock()).start()

    def test_explicit_viewer_uses_local_binding_and_child_only_analytics_opt_out(self):
        with patch.dict(os.environ, {"CI": "prior", "FORCE_RERUN_ANALYTICS": "1"}):
            child = saved.launch_saved_rerun(self.recording)
            self.assertIs(child, self.process.return_value)
            args, options = self.process.call_args
            self.assertEqual(args[0], [str(self.viewer), "--bind", "127.0.0.1", "--port", "auto", str(self.recording)])
            self.assertEqual(options["env"]["CI"], "1")
            self.assertNotIn("FORCE_RERUN_ANALYTICS", options["env"])
            self.assertEqual(os.environ["CI"], "prior")
            self.assertEqual(os.environ["FORCE_RERUN_ANALYTICS"], "1")
            self.assertEqual(options["stdin"], saved.subprocess.DEVNULL)
            self.assertEqual(options["stdout"], saved.subprocess.DEVNULL)
            self.assertEqual(options["stderr"], saved.subprocess.DEVNULL)
            self.assertNotIn("shell", options)

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


if __name__ == "__main__":
    unittest.main()
