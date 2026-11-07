import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "capture_current_typed_reference_cached",
    Path(__file__).parents[1] / "scripts/capture_current_typed_reference_cached.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class RR2CaptureRoutingTests(unittest.TestCase):
    def test_legacy_cached_capture_is_removed(self):
        with self.assertRaisesRegex(ValueError, "legacy-cached-capture-removed"):
            capture.capture("lab1")
        self.assertFalse(hasattr(capture, "_historical_capture"))

    def test_legacy_cached_reader_is_never_used_for_current_reference(self):
        with self.assertRaisesRegex(ValueError, "reviewed-reader"):
            capture.capture(session_id="a" * 32)

    def test_reviewed_reader_path_and_nonce_are_forwarded(self):
        with patch("scripts.capture_current_typed_reference.capture",
                   return_value={"status": "fixture"}) as staged:
            result = capture.capture(
                "lab2", session_id="a" * 32,
                reader=Path("reviewed.exe"), reader_sha256="A" * 64)
        staged.assert_called_once_with(
            "lab2", Path("reviewed.exe"), "A" * 64, "a" * 32)
        self.assertEqual("fixture", result["status"])

    def test_source_has_no_legacy_runtime_dependencies(self):
        source = Path(capture.__file__).read_text(encoding="utf-8")
        for forbidden in ("LabCodex", "RRAPIVAL2", "EXPECTED_READER_SHA",
                          "_historical_capture", "load_workflow"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
