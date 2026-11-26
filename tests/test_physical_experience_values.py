"""Offline physical wrapper checks for partial Experience values."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as reader
from scripts import sample_current_native_experience_values as values
from tests.test_native_experience_values_validation import updated_fixture
from tests.test_postpatch_native_admission import selection


class PhysicalExperienceValuesTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.exe = self.folder / "reader.exe"
        self.exe.touch()
        self.enterContext(patch.object(reader, "NATIVE_EXE", self.exe))
        self.enterContext(patch.object(reader, "_configured_native_reader_path", return_value=None))
        self.enterContext(patch.object(reader.socket, "gethostname", return_value="AMD-DESKTOP"))

    def capture(self, change=None, receipt_change=None):
        path = self.folder / "values.json"
        path.unlink(missing_ok=True)

        def invoke(args, **kwargs):
            self.assertEqual(args[1], "sample-current-experience-values")
            self.assertEqual(args[args.index("--sha256")+1], values.UPDATED_GAME_SHA)
            report = updated_fixture()
            stamp = datetime.now(timezone.utc).isoformat()
            for row in (report["observation"], report["observation"]["seed"]):
                row.update(startedAtUtc=stamp, completedAtUtc=stamp)
                row["identity"].update(processId=12345, processStartUtcTicks=638000000000000001)
            if change:
                change(report)
            path.write_text(json.dumps(report), encoding="utf-8")
            receipt = {"status": "complete", "valueStatus": report["observation"]["valueStatus"],
                       "output": str(path)}
            if receipt_change:
                receipt_change(receipt)
            return subprocess.CompletedProcess(args, 0, json.dumps(receipt), "")

        with patch.object(reader.subprocess, "run", side_effect=invoke):
            return reader.read_native(selection(), "experience-values", path), path

    def test_partial_values_and_source_hash(self):
        result, path = self.capture()
        self.assertEqual("complete", result["status"])
        value = result["nativeValues"]
        self.assertEqual("needed-recipe-unqualified", value["valueStatus"])
        self.assertEqual(1200, value["baselineCandidate"])
        self.assertIsNone(value["neededCandidate"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["nativeSourceSha256"])

    def test_full_values_and_fraction(self):
        def complete(report):
            report["observation"].update(valueStatus="raw-values-candidate", mode=2,
                                         needed=500, accumulatedCandidate=300)
        result, path = self.capture(change=complete)
        self.assertEqual("complete", result["status"])
        observed = result["nativeValues"]
        self.assertEqual(500, observed["neededCandidate"])
        self.assertEqual(300, observed["accumulatedCandidate"])
        self.assertEqual(0.6, observed["progressFractionCandidate"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["nativeSourceSha256"])

    def test_unqualified_type_stale_capture_and_receipt_mismatch(self):
        stale = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        for change in (
            lambda r: r["observation"]["seed"].update(ownerVtableRva=0x1000),
            lambda r: r["observation"].update(startedAtUtc=stale, completedAtUtc=stale),
            lambda r: r["observation"].update(accumulatedCandidate=0),
        ):
            with self.subTest(change=change):
                result, _ = self.capture(change=change)
                self.assertEqual("invalid-native-reader-report", result["reason"])
                self.assertNotIn("nativeValues", result)
        result, _ = self.capture(receipt_change=lambda r: r.update(valueStatus="raw-values-candidate"))
        self.assertEqual("invalid-native-reader-report", result["reason"])

    def test_unknown_build_and_sampling_options_never_launch(self):
        with patch.object(reader.subprocess, "run") as run:
            result = reader.read_native(selection("F"*64), "experience-values")
            self.assertEqual("native-experience-values-build-unqualified", result["reason"])
            result = reader.read_native(selection(), "experience-values", samples=2)
            self.assertEqual("sampling-options-require-supported-native-burst", result["reason"])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
