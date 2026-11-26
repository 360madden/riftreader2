"""Offline fixtures for exact-build raw experience seed admission and projection."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as reader
from scripts import sample_current_native_experience_seed as seed
from tests.test_native_experience_values_validation import fixture
from tests.test_postpatch_native_admission import selection


def source(sha=seed.UPDATED_GAME_SHA):
    observation = fixture()["observation"]["seed"]
    stamp = datetime.now(timezone.utc).isoformat()
    observation.update(startedAtUtc=stamp, completedAtUtc=stamp,
                       ownerVtableRva=0x1000, ownerGetterRva=0x2000)
    observation["identity"].update(
        processId=12345, processStartUtcTicks=638000000000000001,
        executableSha256=sha, moduleBaseAddress=0x140000000, moduleSize=0x4000000)
    observation["selected"].update(vtableRva=0x3000, getterRva=0x4000,
                                   rawInt64_18=0)
    return {"schemaVersion": 1, "contractVersion": "native-current-experience-seed-candidate/1",
            "status": "complete", "observation": observation}


class ExperienceSeedPhysicalTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.exe = self.folder / "reader.exe"
        self.exe.touch()
        self.enterContext(patch.object(reader, "NATIVE_EXE", self.exe))
        self.enterContext(patch.object(reader, "_configured_native_reader_path", return_value=None))
        self.enterContext(patch.object(reader.socket, "gethostname", return_value="AMD-DESKTOP"))

    def capture(self, *, sha=seed.UPDATED_GAME_SHA, change=None, change_receipt=None):
        path = self.folder / "seed.json"
        path.unlink(missing_ok=True)

        def invoke(args, **kwargs):
            self.assertEqual(args[:6], [str(self.exe), "sample-current-experience-seed",
                                        "--pid", "12345", "--start-ticks", "638000000000000001"])
            self.assertEqual(args[args.index("--sha256") + 1], sha)
            report = source(sha)
            if change:
                change(report)
            path.write_text(json.dumps(report), encoding="utf-8")
            receipt = {"status": "complete", "recordType": "native-current-experience-seed-summary/1",
                       "branch": report["observation"]["branch"], "qualification": seed.QUALIFICATION,
                       "output": str(path)}
            if change_receipt:
                change_receipt(receipt)
            return subprocess.CompletedProcess(args, 0, json.dumps(receipt), "")

        with patch.object(reader.subprocess, "run", side_effect=invoke):
            return reader.read_native(selection(sha.lower()), "experience-seed", path), path

    def test_current_build_candidate_and_source_digest(self):
        result, path = self.capture()
        self.assertEqual("complete", result["status"])
        values = result["nativeValues"]
        self.assertEqual("raw-seed-candidate", values["status"])
        self.assertEqual("1234", values["unitKey"])
        self.assertEqual(0, values["rawProgressRecordCandidate"])
        self.assertEqual(45, values["rawProgressLevelCandidate"])
        self.assertEqual(0.0, values["rawRecordFloatCandidate"])
        self.assertNotIn("accumulated", values)
        self.assertNotIn("needed", values)
        self.assertNotIn("rested", values)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["nativeSourceSha256"])

    def test_old_build_default_and_explicit_physical_admission(self):
        with self.assertRaises(ValueError):
            seed.validate_report(source(), pid=12345, ticks=638000000000000001)
        result, _ = self.capture(sha=seed.GAME_SHA)
        self.assertEqual("complete", result["status"])

    def test_missing_seed_never_invents_zero(self):
        def unavailable(report):
            report["observation"].update(index=-1, selected=None, branch="index-minus-one")
        result, _ = self.capture(change=unavailable)
        self.assertEqual("complete", result["status"])
        values = result["nativeValues"]
        self.assertEqual("seed-unavailable", values["status"])
        self.assertIsNone(values["rawProgressRecordCandidate"])

    def test_invalid_identity_payload_or_receipt_refused(self):
        stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        changes = [
            lambda r: r["observation"]["identity"].update(processStartUtcTicks=1),
            lambda r: r["observation"]["identity"].update(moduleSize=1),
            lambda r: r["observation"].update(ownerVtableRva=None),
            lambda r: r["observation"]["selected"].update(getterRva=0x4000000),
            lambda r: r["observation"]["selected"].update(rawInt64_18=True),
            lambda r: r["observation"].update(startedAtUtc=stale, completedAtUtc=stale),
        ]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                result, _ = self.capture(change=change)
                self.assertEqual("invalid-native-reader-report", result["reason"])
                self.assertNotIn("nativeValues", result)
        result, _ = self.capture(change_receipt=lambda receipt: receipt.update(branch="index-minus-one"))
        self.assertEqual("invalid-native-reader-report", result["reason"])

    def test_unknown_build_and_sampling_options_refused_before_launch(self):
        with patch.object(reader.subprocess, "run") as run:
            result = reader.read_native(selection("F"*64), "experience-seed")
            self.assertEqual("native-experience-seed-build-unqualified", result["reason"])
            result = reader.read_native(selection(), "experience-seed", samples=2)
            self.assertEqual("sampling-options-require-supported-native-burst", result["reason"])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
