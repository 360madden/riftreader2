"""Read-only physical RR2R1 scout exact-build 1179 admission tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import probe_physical_rr2r1 as probe
from tests.test_probe_physical_rr2r1 import HOST, ProbeTests, SELECTION


class UpdatedRr2r1ProbeTests(unittest.TestCase):
    def setUp(self):
        self.selection = deepcopy(SELECTION)
        self.selection["target"]["executableSha256"] = probe.UPDATED_SHA

    def test_exact_1179_can_be_pinned_without_admitting_unknown_shas(self):
        with patch.object(probe.socket, "gethostname", return_value=HOST), \
             patch.object(probe.physical_rift, "select_physical", return_value=self.selection):
            self.assertEqual(probe.pinned_selection(123), self.selection)
        unknown = deepcopy(self.selection)
        unknown["target"]["executableSha256"] = "F" * 64
        with patch.object(probe.socket, "gethostname", return_value=HOST), \
             patch.object(probe.physical_rift, "select_physical", return_value=unknown):
            with self.assertRaisesRegex(ValueError, "physical-build-or-epoch-invalid"):
                probe.pinned_selection(123)

    def test_generic_reader_1179_scans_with_exact_epoch_hash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"test-only-native-reader")
            requests = []

            def scanner(argv, **kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                expected = {
                    "processId": 123,
                    "processStartUtcTicks": int(self.selection["target"]["processStartUtcTicks"]),
                    "executableSha256": probe.UPDATED_SHA,
                }
                self.assertEqual(request["target"], expected)
                self.assertEqual(request["marker"], "RR2R1|")
                self.assertFalse(directory.exists())
                directory.mkdir()
                from tests.test_probe_physical_rr2r1 import ProbeTests
                helper = ProbeTests()
                index = helper.index(request, request_path)
                index["identity"]["executableSha256"] = probe.UPDATED_SHA
                (directory / "index.json").write_text(json.dumps(index), encoding="utf-8")
                requests.append(request)
                return subprocess.CompletedProcess(argv, 0, "", "")

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=self.selection), \
                 patch.object(probe.subprocess, "run", side_effect=scanner):
                path, report = probe.collect(123, root / "scan", max_scans=1,
                                             scan_bytes=1_048_576, gap_seconds=0)
            self.assertEqual(len(requests), 1)
            self.assertEqual(report["target"]["executableSha256"], probe.UPDATED_SHA)
            self.assertEqual(report["status"], "no-copied-candidate-in-bounded-scopes")
            self.assertEqual(report["runs"][0]["sourceVerifiedSnapshots"], 0)
            self.assertEqual(json.loads(path.read_text()), report)

    def test_1179_copied_snapshot_sources_are_verified_without_version_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request = {"target": {"processId": 123,
                                  "processStartUtcTicks": int(self.selection["target"]["processStartUtcTicks"]),
                                  "executableSha256": probe.UPDATED_SHA}}
            request_path.write_text(json.dumps(request), encoding="utf-8")
            helper = ProbeTests()
            index = helper.index(request, request_path, published=1)
            index["identity"]["executableSha256"] = probe.UPDATED_SHA
            helper.copy(root, index)
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            result = probe.check_index(index_path, request, probe.digest(request_path), self.selection)
            self.assertEqual(result["publishedSnapshots"], 1)
            self.assertEqual(result["sourceVerifiedSnapshots"], 1)
            self.assertEqual(result["candidateStatusCounts"], {"complete": 1})

    def test_wrong_version_index_rejected_before_claiming_snapshots(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request = {"target": {"processId": 123,
                                  "processStartUtcTicks": int(self.selection["target"]["processStartUtcTicks"]),
                                  "executableSha256": probe.UPDATED_SHA}}
            request_path.write_text(json.dumps(request), encoding="utf-8")
            index = ProbeTests().index(request, request_path)
            index["identity"]["executableSha256"] = probe.BUILD_SHA
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scan-evidence-identity-mismatch"):
                probe.check_index(index_path, request, probe.digest(request_path), self.selection)

    def test_explicit_current_epoch_cursor_scans_only_requested_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reader = root / "reader.exe"
            reader.write_bytes(b"test-only-reader")
            actual_start = "0x13000000"
            seen = []
            def scanner(argv, **kwargs):
                req_path, scan_dir = Path(argv[3]), Path(argv[5])
                request = json.loads(req_path.read_text(encoding="utf-8"))
                self.assertEqual(request["startAddress"], actual_start)
                self.assertEqual(request["target"]["executableSha256"], probe.UPDATED_SHA)
                scan_dir.mkdir()
                index = ProbeTests().index(request, req_path)
                index["identity"]["executableSha256"] = probe.UPDATED_SHA
                index["scan"]["nextAddress"] = "0x14000000"
                (scan_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
                seen.append(request)
                return subprocess.CompletedProcess(argv, 3, "", "")
            with (patch.object(probe.physical_rift, "NATIVE_EXE", reader),
                  patch.object(probe, "pinned_selection", return_value=self.selection),
                  patch.object(probe.subprocess, "run", side_effect=scanner)):
                _, report = probe.collect(123, root / "out", scan_bytes=1_048_576,
                                          max_scans=1, gap_seconds=0,
                                          start_address=actual_start)
            self.assertEqual(len(seen), 1)
            self.assertEqual(report["initialCursor"], actual_start)
            self.assertEqual(report["runs"][0]["startAddress"], actual_start)
            self.assertEqual(report["scanWork"]["nextResumeCursor"], "0x14000000")

    def test_invalid_or_noncanonical_start_cursor_never_probes_a_process(self):
        with TemporaryDirectory() as tmp, patch.object(probe, "pinned_selection") as selection:
            for idx, start in enumerate(("0x0", "0x1300000a", "0X13000000",
                                         "0x00013000000", "0x800000000000",
                                         "0xgarbage")):
                with self.subTest(start=start), self.assertRaises(ValueError):
                    probe.collect(123, Path(tmp) / f"bad-{idx}", start_address=start)
            selection.assert_not_called()

    def test_custom_start_cannot_override_an_existing_resume_chain(self):
        with patch.object(probe, "pinned_selection") as selection:
            with self.assertRaisesRegex(ValueError, "start-address-conflicts-with-resume"):
                probe.collect(123, Path("unused"), start_address="0x13000000",
                              resume_summary=Path("historical.json"))
            selection.assert_not_called()

    def test_cli_passes_explicit_cursor_to_native_scout(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch.object(probe, "collect", return_value=(
                Path("summary.json"), {"status": "no-copied-candidate-in-bounded-scopes",
                                       "qualification": "bounded coverage only",
                                       "runs": [], "referenceAssessment": None,
                                       "scanWork": {}})) as called, redirect_stdout(StringIO()):
            self.assertEqual(probe.main(["--physical-pid", "123",
                                         "--start-address", "0x13000000"]), 0)
        self.assertEqual(called.call_args.kwargs["start_address"], "0x13000000")

    def test_cross_epoch_saved_summary_cannot_resume_on_new_game(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "summary.json"
            target = {"processId": 123,
                      "processStartUtcTicks": int(self.selection["target"]["processStartUtcTicks"]),
                      "executableSha256": probe.BUILD_SHA}
            summary = {"schemaVersion": 1,
                       "evidenceKind": "amd-physical-rr2r1-prefix-scan/1",
                       "ownerHost": HOST,
                       "target": target,
                       "readerSha256": "0" * 64,
                       "status": "no-copied-candidate-in-bounded-scopes",
                       "runs": [],
                       "initialCursor": "0x10000"}
            path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "resume-epoch-reader-or-status-mismatch"):
                probe.resume_cursor(path, self.selection, "0" * 64)

    def test_new_epoch_report_unknown_sha_fails_saved_audit(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            data = {"schemaVersion": 1,
                    "evidenceKind": "amd-physical-rr2r1-prefix-scan/1",
                    "ownerHost": HOST,
                    "target": {"processId": 123, "processStartUtcTicks": 123,
                               "executableSha256": "E" * 64},
                    "runs": [{"run": 1}]}
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(probe.socket, "gethostname", return_value=HOST):
                with self.assertRaisesRegex(ValueError, "saved-target-invalid"):
                    probe.assess_saved(path, Path(tmp) / "result")


if __name__ == "__main__":
    unittest.main()
