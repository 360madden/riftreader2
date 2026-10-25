"""No live access: exports are built from synthetic closed-session fixtures."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import export_xyz_sessions as exporter
from tests import test_review_position_panel as fixture


class ExportXyzSessionsTests(unittest.TestCase):
    def setUp(self):
        self.session = fixture.PositionPanelReviewTests()
        self.session.setUp()
        self.addCleanup(self.session.doCleanups)
        self.session.build()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "export"

    def test_export_roundtrip_is_exact_and_allowlisted(self):
        (self.session.root / "private-host.json").write_text("must not export")
        result = exporter.export_sessions([self.session.root], self.output)
        self.assertEqual(result["status"], "exported-recorded-checks-passed")
        self.assertFalse((self.output / "INCOMPLETE.txt").exists())
        self.assertTrue((self.output / "complete.json").exists())
        with zipfile.ZipFile(self.output / "package.zip") as archive:
            self.assertFalse(any("private-host" in name for name in archive.namelist()))
            for name in ("panel-session.json", "panel-events.jsonl", "read-00001.json"):
                self.assertEqual(archive.read("session-01/originals/" + name),
                                 (self.session.root / name).read_bytes())
            checksums = json.loads(archive.read("checksums.json"))["files"]
            self.assertEqual(set(archive.namelist()), {*checksums, "checksums.json"})
            for name, pin in checksums.items():
                self.assertEqual(exporter.sha(archive.read(name)), pin["sha256"])

    def test_failure_evidence_is_preserved_with_exit_two(self):
        self.session.build(fixture.observation(2 ** -127, 1.0, 2.0))
        with redirect_stdout(io.StringIO()):
            code = exporter.main(["--session-dir", str(self.session.root), "--output", str(self.output)])
        self.assertEqual(code, 2)
        review = json.loads((self.output / "session-01/review.json").read_text())
        self.assertEqual(review["findings"][0]["reason"], "subnormal-published-live")

    def test_existing_output_is_unchanged(self):
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("retained")
        with self.assertRaisesRegex(ValueError, "new directory"):
            exporter.export_sessions([self.session.root], self.output)
        self.assertEqual(marker.read_text(), "retained")

    def test_tampered_input_leaves_no_output(self):
        (self.session.root / "read-00001.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            exporter.export_sessions([self.session.root], self.output)
        self.assertFalse(self.output.exists())

    def test_input_change_after_review_is_rejected(self):
        original_review = exporter.review_session
        def change(directory):
            report = original_review(directory)
            (directory / "read-00001.json").write_text("{}")
            return report
        with patch.object(exporter, "review_session", side_effect=change):
            with self.assertRaisesRegex(ValueError, "changed after"):
                exporter.export_sessions([self.session.root], self.output)
        self.assertFalse(self.output.exists())

    def test_output_cannot_be_within_input(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            exporter.export_sessions([self.session.root], self.session.root / "export")

    def test_new_report_after_audit_is_rejected(self):
        original_review = exporter.review_session
        def change(directory):
            report = original_review(directory)
            (directory / "read-00002.json").write_text("{}")
            return report
        with patch.object(exporter, "review_session", side_effect=change):
            with self.assertRaisesRegex(ValueError, "file set changed"):
                exporter.export_sessions([self.session.root], self.output)
        self.assertFalse(self.output.exists())

    def test_corrupt_completion_does_not_report_success(self):
        original_read = Path.read_bytes
        def corrupt(path):
            return b"corrupt" if path.name == "complete.json" else original_read(path)
        with patch.object(Path, "read_bytes", corrupt):
            with self.assertRaisesRegex(ValueError, "copy differs"):
                exporter.export_sessions([self.session.root], self.output)
        self.assertTrue((self.output / "INCOMPLETE.txt").exists())

    def test_duplicate_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            exporter.export_sessions([self.session.root] * 2, self.output)

    def test_bound_checked_before_review(self):
        with patch.object(exporter, "MAX_INPUT_BYTES", 8):
            with patch.object(exporter, "review_session") as review:
                with self.assertRaisesRegex(ValueError, "64 MiB"):
                    exporter.export_sessions([self.session.root], self.output)
                review.assert_not_called()

    def test_write_failure_does_not_publish_completion(self):
        with patch.object(exporter.zipfile, "ZipFile", side_effect=OSError("disk failure")):
            with redirect_stderr(io.StringIO()):
                code = exporter.main(["--session-dir", str(self.session.root), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertFalse((self.output / "complete.json").exists())
        self.assertTrue((self.output / "INCOMPLETE.txt").exists())

    def test_repeated_export_replays_identically(self):
        first = exporter.export_sessions([self.session.root], self.output)
        second = exporter.export_sessions([self.session.root], self.output.with_name("second"))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
