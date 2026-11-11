"""Offline tests for bounded physical RR2R1 reference discovery (no process access)."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import probe_physical_rr2r1 as probe

TARGET = {
    "processId": 123, "processStartUtcTicks": "639299470183328173",
    "executableSha256": probe.BUILD_SHA, "hostName": probe.HOST,
}
SELECTION = {"status": "ready", "ownerHost": probe.HOST, "target": TARGET}


class ProbeTests(unittest.TestCase):
    def index(self, request, request_path, published=0):
        return {
            "schemaVersion": 1, "evidenceKind": "native-typed-inline-capture/1",
            "status": "complete", "identity": {
                "processId": 123, "processStartUtcTicks": int(TARGET["processStartUtcTicks"]),
                "executableSha256": probe.BUILD_SHA,
            },
            "request": request, "requestSha256": probe.digest(request_path),
            "publishedSnapshots": published,
            "scan": {"status": "partial", "reason": "byte-budget-exceeded",
                     "startAddress": request.get("startAddress", "0x10000"),
                     "nextAddress": "0x20000", "examinedBytes": 1048576,
                     "prefixAddresses": [] if not published else ["0xABCDEF"]},
        }

    def test_two_bounded_scans_reuse_reader_without_claiming_frame(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            calls = []
            def invoke(argv, **kwargs):
                self.assertEqual(argv[1], "scout-copy-typed-native")
                self.assertEqual(argv[2], "--request")
                self.assertEqual(argv[4], "--output")
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                self.assertEqual(request["target"]["processId"], 123)
                self.assertEqual(request["marker"], "RR2R1|")
                self.assertEqual(request["startAddress"], "0x10000" if not calls else "0x20000")
                self.assertFalse(directory.exists())
                directory.mkdir()
                calls.append(directory)
                (directory / "index.json").write_text(json.dumps(
                    self.index(request, request_path, published=len(calls) - 1)))
                return subprocess.CompletedProcess(argv, 0, "", "")
            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION) as select, \
                 patch.object(probe.subprocess, "run", side_effect=invoke) as run, \
                 patch.object(probe.time, "sleep") as sleep:
                receipt, result = probe.collect(123, root / "capture", max_scans=2)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(select.call_count, 5)
            sleep.assert_called_once()
            self.assertEqual(result["status"], "candidate-captures-available")
            self.assertEqual([r["publishedSnapshots"] for r in result["runs"]], [0, 1])
            self.assertEqual([r["startAddress"] for r in result["runs"]],
                             ["0x10000", "0x20000"])
            self.assertIn("no decoded Lua frame", result["qualification"])
            self.assertEqual(json.loads(receipt.read_text()), result)
            self.assertEqual(result["readerSha256"],
                             hashlib.sha256(b"synthetic-reader").hexdigest().upper())

    def test_rejects_wrong_host_without_scanning(self):
        with patch.object(probe.socket, "gethostname", return_value="UNEXPECTED"), \
             patch.object(probe.physical_rift, "select_physical") as select:
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                probe.pinned_selection(123)
            select.assert_not_called()

    def test_rejects_changed_epoch_and_build(self):
        for mutation in ({"executableSha256": "0" * 64},
                         {"processId": 124}):
            selection = deepcopy(SELECTION)
            selection["target"].update(mutation)
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe.physical_rift, "select_physical",
                              return_value=selection):
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    probe.pinned_selection(123)

    def test_check_index_rejects_duplicate_keys_or_wrong_epoch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "request.json"
            request = {"target": TARGET}
            source.write_text(json.dumps(request))
            raw = self.index(request, source)
            raw["identity"]["processStartUtcTicks"] = 1
            index = root / "index.json"
            index.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError, "scan-evidence-identity-mismatch"):
                probe.check_index(index, request, probe.digest(source), SELECTION)
            index.write_text('{"status":"complete","status":"partial"}')
            with self.assertRaisesRegex(ValueError, "duplicate-json-field"):
                probe.check_index(index, request, probe.digest(source), SELECTION)

    def test_epoch_change_before_scan_never_launches_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            changed = deepcopy(SELECTION)
            changed["target"]["processStartUtcTicks"] = "987"
            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", side_effect=(SELECTION, changed)), \
                 patch.object(probe.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "epoch-changed-before-scan"):
                    probe.collect(123, root / "capture")
                run.assert_not_called()

    def test_invalid_pid_or_scanning_bounds_no_process_probe(self):
        with patch.object(probe, "pinned_selection") as select:
            with tempfile.TemporaryDirectory() as temp:
                for pid, bounds in ((0, {}), (123, {"scan_bytes": 12345}),
                                    (123, {"scan_ms": 100}),
                                    (123, {"gap_seconds": -1})):
                    with self.subTest(pid=pid, bounds=bounds), self.assertRaises(ValueError):
                        probe.collect(pid, Path(temp) / "capture", **bounds)
            select.assert_not_called()

    def test_incomplete_or_invalid_scan_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "request.json"
            source.write_text('{"version": 1}')
            req = {"version": 1}
            index = self.index(req, source)
            index["status"] = "identity-invalidated"
            path = root / "index.json"
            path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-evidence-unusable"):
                probe.check_index(path, req, probe.digest(source), SELECTION)


    def test_resume_scans_new_address_ranges_after_verifying_prior_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            starts = []

            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                starts.append(request["startAddress"])
                directory.mkdir()
                index = self.index(request, request_path)
                index["scan"]["nextAddress"] = hex(int(starts[-1], 16) + 0x10000)
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 3, "", "")

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke) as scan:
                prior, _ = probe.collect(123, root / "first", max_scans=2,
                                         gap_seconds=0)
                resumed, result = probe.collect(123, root / "second", max_scans=1,
                                                gap_seconds=0, resume_summary=prior)

            self.assertEqual(starts, ["0x10000", "0x20000", "0x30000"])
            self.assertEqual(scan.call_count, 3)
            self.assertEqual(result["initialCursor"], "0x30000")
            self.assertEqual(result["runs"][0]["startAddress"], "0x30000")
            self.assertEqual(result["resumeSourceSha256"], probe.digest(prior))
            self.assertEqual(json.loads(resumed.read_text()), result)

    def test_resume_rejects_tampered_receipt_changed_epoch_or_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                index = self.index(request, request_path)
                index["scan"]["nextAddress"] = "0x30000"
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 3, "", "")

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke) as scan:
                prior, _ = probe.collect(123, root / "first", max_scans=1,
                                         gap_seconds=0)
                index_path = prior.parent / "run-01" / "index.json"
                original = index_path.read_bytes()
                tampered = json.loads(original)
                tampered["scan"]["nextAddress"] = "0x40000"
                index_path.write_text(json.dumps(tampered))
                with self.assertRaisesRegex(ValueError, "resume-receipt-mismatch"):
                    probe.collect(123, root / "bad-index", resume_summary=prior)
                index_path.write_bytes(original)
                changed = deepcopy(SELECTION)
                changed["target"]["processStartUtcTicks"] = "639299470183328174"
                with patch.object(probe, "pinned_selection", return_value=changed), \
                     self.assertRaisesRegex(ValueError, "resume-epoch-reader-or-status-mismatch"):
                    probe.collect(123, root / "bad-epoch", resume_summary=prior)
                reader.write_bytes(b"changed-reader")
                with self.assertRaisesRegex(ValueError, "resume-epoch-reader-or-status-mismatch"):
                    probe.collect(123, root / "bad-reader", resume_summary=prior)
                self.assertEqual(scan.call_count, 1)
                for name in ("bad-index", "bad-epoch", "bad-reader"):
                    self.assertFalse((root / name).exists())


if __name__ == "__main__":
    unittest.main()
