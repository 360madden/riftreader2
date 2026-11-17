"""Bounded offline composite JSON transport: no data loss, overwrite, or input."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from scripts import physical_pixel_composite as composite


def args_for(output=None):
    """Argparse-complete placeholders; source APIs are mocked in transport tests."""
    argv = [
        "--image", "unused.png",
        "--receipt", "unused-receipt.json",
        "--receipt-sha256", "0" * 64,
        "--native-before", "unused-before.json",
        "--native-before-sha256", "0" * 64,
        "--native-after", "unused-after.json",
        "--native-after-sha256", "0" * 64,
        "--expected-host", "AMD-DESKTOP",
        "--terrain-obj", "unused-terrain.obj",
        "--terrain-registration", "unused-registration.json",
        "--temple-obj", "unused-temple.obj",
        "--temple-anchor", "unused-anchor.json",
        "--temple-anchor-sha256", "0" * 64,
        "--pixel", "100", "100",
    ]
    if output is not None:
        argv.extend(("--output-json", str(output)))
    return argv


def candidate_report(extra=None):
    report = {
        "schema": composite.SCHEMA, "status": "candidate-only",
        "pixels": [{"pixel": [100, 100], "surfaceCandidates": {
            "status": "no-candidate-intersection",
            "sourceCoverageComplete": False, "movementEligible": False}}],
        "inputSent": False, "movementEligible": False,
        "visibleSurfaceQualified": False, "physicalBlockingQualified": False,
        "navigationQualified": False,
    }
    if extra:
        report.update(extra)
    return report


def mocked_cli(argv, result):
    """Exercise real main/serialization but bypass unrelated scene loading."""
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(
            composite, "load_frame", return_value={"identity": {}}))
        stack.enter_context(mock.patch.object(
            composite, "load_terrain", return_value={"name": "terrain"}))
        stack.enter_context(mock.patch.object(
            composite, "load_temple", return_value={"name": "temple-render"}))
        stack.enter_context(mock.patch.object(
            composite, "analyze_pixels", return_value=result))
        out = StringIO()
        with redirect_stdout(out):
            code = composite.main(argv)
    return code, out.getvalue()


class CompositeJsonTransportTests(unittest.TestCase):
    def test_small_stdout_remains_exact_legacy_json(self):
        result = candidate_report()
        code, stdout = mocked_cli(args_for(), result)
        self.assertEqual(code, 0)
        self.assertEqual(stdout, json.dumps(result, allow_nan=False) + "\n")

    def test_exclusive_file_contains_full_json_and_receipt_sha(self):
        result = candidate_report({"description": "entire original candidate report",
                                   "largeRetainedFields":
                                       "x" * (composite.MAX_STDOUT_REPORT_BYTES + 1)})
        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "complete-candidates.json"
            code, stdout = mocked_cli(args_for(destination), result)
            self.assertEqual(code, 0)
            receipt = json.loads(stdout)
            raw = destination.read_bytes()
            self.assertEqual(raw, json.dumps(result, allow_nan=False).encode("utf-8"))
            self.assertEqual(json.loads(raw), result)
            self.assertEqual(receipt["schema"], composite.SCHEMA)
            self.assertEqual(receipt["status"], "candidate-only-json-written")
            self.assertEqual(receipt["outputJson"]["status"], "written")
            self.assertEqual(receipt["outputJson"]["path"], str(destination.resolve()))
            self.assertEqual(receipt["outputJson"]["byteCount"], len(raw))
            self.assertFalse(list(Path(tmp).glob(".rr2-composite-json-*.tmp")))
            self.assertEqual(receipt["outputJson"]["sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertLess(len(stdout.encode("utf-8")), 512 * 1024)
            for flag in ("inputSent", "movementEligible", "visibleSurfaceQualified",
                         "physicalBlockingQualified", "navigationQualified"):
                self.assertIs(receipt[flag], False, flag)

    def test_existing_output_never_overwritten_before_source_io(self):
        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "evidence.json"
            sentinel = b'{"untouched":true}\n'
            destination.write_bytes(sentinel)
            out = StringIO()
            with mock.patch.object(composite, "load_frame",
                                   side_effect=AssertionError("unexpected-source-io")):
                with redirect_stdout(out):
                    code = composite.main(args_for(destination))
            self.assertEqual(code, 2)
            blocked = json.loads(out.getvalue())
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(
                blocked["reason"], "output-json-must-be-new-json-in-existing-directory")
            self.assertEqual(destination.read_bytes(), sentinel)

    def test_exclusive_create_still_blocks_late_file_race(self):
        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "late.json"
            original = composite._json_output_target
            sentinel = b"late-writer"
            def arrive_between_preflight_and_write(path):
                checked = original(path)
                checked.write_bytes(sentinel)
                return checked
            with mock.patch.object(composite, "_json_output_target",
                                   side_effect=arrive_between_preflight_and_write):
                code, stdout = mocked_cli(args_for(destination), candidate_report())
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout)["status"], "blocked")
            self.assertEqual(destination.read_bytes(), sentinel)

    def test_short_write_fails_without_final_or_staged_files(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "partial.json"
            original_temp = composite.tempfile.NamedTemporaryFile

            class ShortWriter:
                def __init__(self, actual):
                    self.actual = actual
                    self.name = actual.name

                def __enter__(self):
                    self.actual.__enter__()
                    return self

                def __exit__(self, *exc):
                    return self.actual.__exit__(*exc)

                def write(self, raw):
                    self.actual.write(raw[:7])
                    return len(raw) - 1

            def short_temp(*args, **kwargs):
                return ShortWriter(original_temp(*args, **kwargs))

            with mock.patch.object(composite.tempfile, "NamedTemporaryFile",
                                   side_effect=short_temp):
                code, output = mocked_cli(args_for(target), candidate_report())
            self.assertEqual(code, 2)
            self.assertIn("output-json-stage-short-write",
                          json.loads(output)["reason"])
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(tmp).glob(".rr2-composite-json-*.tmp")))

    def test_fsync_exception_leaves_no_final_or_staging_file(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "no-disk.json"
            with mock.patch.object(composite.os, "fsync",
                                   side_effect=OSError("injected-disk-full")):
                code, output = mocked_cli(args_for(target), candidate_report())
            self.assertEqual(code, 2)
            self.assertIn("injected-disk-full", json.loads(output)["reason"])
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(tmp).glob(".rr2-composite-json-*.tmp")))

    def test_unavailable_atomic_hardlink_fails_without_fallback(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "no-link.json"
            with mock.patch.object(composite.os, "link",
                                   side_effect=OSError("injected-link-unavailable")):
                code, output = mocked_cli(args_for(target), candidate_report())
            self.assertEqual(code, 2)
            self.assertIn("output-json-atomic-publish-failed",
                          json.loads(output)["reason"])
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(tmp).glob(".rr2-composite-json-*.tmp")))

    def test_oversize_stdout_blocks_before_preview_png_creation(self):
        result = candidate_report({"largeRetainedFields":
                                   "x" * (composite.MAX_STDOUT_REPORT_BYTES + 1)})
        with TemporaryDirectory() as tmp:
            preview = Path(tmp) / "never-created.png"
            with mock.patch.object(composite, "render_preview",
                                   side_effect=AssertionError("unexpected-preview-write")):
                code, output = mocked_cli(args_for() +
                                          ["--preview-png", str(preview)], result)
            self.assertEqual(code, 2)
            self.assertIn("--output-json", json.loads(output)["reason"])
            self.assertFalse(preview.exists())

    def test_missing_parent_and_non_json_suffix_rejected(self):
        with TemporaryDirectory() as tmp:
            for destination in (Path(tmp) / "missing" / "report.json",
                                Path(tmp) / "not-json.txt"):
                with self.subTest(destination=destination):
                    code, stdout = mocked_cli(args_for(destination), candidate_report())
                    self.assertEqual(code, 2)
                    self.assertEqual(json.loads(stdout)["reason"],
                                     "output-json-must-be-new-json-in-existing-directory")
                    self.assertFalse(destination.exists())

    def test_oversize_stdout_fails_short_with_actionable_message(self):
        result = candidate_report({"largeRetainedFields":
                                   "x" * (composite.MAX_STDOUT_REPORT_BYTES + 1)})
        code, stdout = mocked_cli(args_for(), result)
        self.assertEqual(code, 2)
        self.assertLess(len(stdout.encode("utf-8")), 1024)
        blocked = json.loads(stdout)
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("--output-json", blocked["reason"])
        self.assertIn("512KiB", blocked["reason"])
        self.assertFalse(blocked["inputSent"])
        self.assertFalse(blocked["movementEligible"])


if __name__ == "__main__":
    unittest.main()
