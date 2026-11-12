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
            "candidates": [],
        }

    def copy(self, directory, index):
        """Build a synthetic C# copy with independently hashed source files."""
        identity = index["identity"]
        for number in range(1, index["publishedSnapshots"] + 1):
            row = {"status": "complete"}
            request_content = {"schemaVersion": 1,
                               "evidenceKind": "native-memory-snapshot-request/1",
                               "target": index["request"].get("target", identity)}
            for kind, content in (
                ("request", request_content),
                ("snapshot", {"schemaVersion": 1,
                              "evidenceKind": "native-memory-snapshot/1",
                              "status": "complete", "identity": identity,
                              "source": {"requestEvidenceKind": "native-memory-snapshot-request/1",
                                         "requestSha256": row.get("requestSha256")},
                              "chunks": []}),
            ):
                if kind == "snapshot":
                    content["source"]["requestSha256"] = row["requestSha256"]
                name = f"capture-{number:02d}.{kind}.json"
                path = directory / name
                path.write_text(json.dumps(content), encoding="utf-8")
                row[kind + "File"] = name
                row[kind + "Sha256"] = probe.digest(path)
            index["candidates"].append(row)
        return index

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
                index = self.copy(directory, self.index(
                    request, request_path, published=len(calls) - 1))
                (directory / "index.json").write_text(json.dumps(index))
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
            self.assertEqual([r["sourceVerifiedSnapshots"] for r in result["runs"]], [0, 1])
            self.assertEqual([r["publishedSnapshots"] for r in result["runs"]], [0, 1])
            self.assertEqual([r["startAddress"] for r in result["runs"]],
                             ["0x10000", "0x20000"])
            self.assertIn("no decoded Lua frame", result["qualification"])
            self.assertEqual(json.loads(receipt.read_text()), result)
            self.assertEqual(result["readerSha256"],
                             hashlib.sha256(b"synthetic-reader").hexdigest().upper())

    def test_copied_frame_claim_without_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request_path = root / "request.json"
            request_path.write_text('{}', encoding="utf-8")
            index = self.index({}, request_path, published=1)
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-copy-count-mismatch"):
                probe.check_index(index_path, {}, probe.digest(request_path), SELECTION)

    def test_rejects_tampered_or_rebound_copied_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request_path = root / "request.json"
            request_path.write_text('{}', encoding="utf-8")
            index = self.copy(root, self.index({}, request_path, published=1))
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            self.assertEqual(probe.check_index(
                index_path, {}, probe.digest(request_path), SELECTION)["sourceVerifiedSnapshots"], 1)
            source = root / "capture-01.snapshot.json"
            original = source.read_bytes()
            source.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "scan-copy-source-hash-mismatch"):
                probe.check_index(index_path, {}, probe.digest(request_path), SELECTION)
            source.write_bytes(original)
            index["candidates"][0]["snapshotFile"] = "../outside.snapshot.json"
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-copy-binding-invalid"):
                probe.check_index(index_path, {}, probe.digest(request_path), SELECTION)
            index["candidates"][0]["snapshotFile"] = "capture-01.snapshot.json"
            snapshot = json.loads(original)
            snapshot["identity"]["processId"] = 999
            source.write_text(json.dumps(snapshot))
            index["candidates"][0]["snapshotSha256"] = probe.digest(source)
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-copy-snapshot-identity-mismatch"):
                probe.check_index(index_path, {}, probe.digest(request_path), SELECTION)

    def test_copied_request_target_and_snapshot_source_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request_path = root / "request.json"
            request = {"target": {"processId": 123,
                                   "processStartUtcTicks": int(TARGET["processStartUtcTicks"]),
                                   "executableSha256": probe.BUILD_SHA}}
            request_path.write_text(json.dumps(request))
            index = self.copy(root, self.index(request, request_path, published=1))
            index_path = root / "index.json"
            index_path.write_text(json.dumps(index))
            self.assertEqual(probe.check_index(
                index_path, request, probe.digest(request_path), SELECTION)["sourceVerifiedSnapshots"], 1)
            source_path = root / "capture-01.request.json"
            snapshot_path = root / "capture-01.snapshot.json"
            source = json.loads(source_path.read_text())
            source["target"]["processId"] = 999
            source_path.write_text(json.dumps(source))
            index["candidates"][0]["requestSha256"] = probe.digest(source_path)
            snapshot = json.loads(snapshot_path.read_text())
            snapshot["source"]["requestSha256"] = probe.digest(source_path)
            snapshot_path.write_text(json.dumps(snapshot))
            index["candidates"][0]["snapshotSha256"] = probe.digest(snapshot_path)
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-copy-request-target-mismatch"):
                probe.check_index(index_path, request, probe.digest(request_path), SELECTION)
            source["target"]["processId"] = 123
            source_path.write_text(json.dumps(source))
            index["candidates"][0]["requestSha256"] = probe.digest(source_path)
            # Deliberately leave the snapshot pointing to the prior request digest.
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "scan-copy-source-request-mismatch"):
                probe.check_index(index_path, request, probe.digest(request_path), SELECTION)

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

    def test_resume_rejects_false_initial_cursor_before_scanning(self):
        """A valid receipt chain cannot be relabeled to claim a different start."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")

            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                index = self.index(request, request_path)
                index["scan"]["nextAddress"] = "0x20000"
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 3, "", "")

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke) as scan:
                prior, summary = probe.collect(123, root / "first", max_scans=1,
                                               gap_seconds=0)
                self.assertEqual(scan.call_count, 1)
                summary["initialCursor"] = "0x30000"
                prior.write_text(json.dumps(summary), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "resume-request-chain-mismatch"):
                    probe.collect(123, root / "bad-resume", max_scans=1,
                                  gap_seconds=0, resume_summary=prior)
                self.assertEqual(scan.call_count, 1)
            self.assertFalse((root / "bad-resume").exists())

    def test_invalid_session_nonce_fails_before_process_access(self):
        with patch.object(probe, "pinned_selection") as select:
            for invalid in ("abc", "A" * 32, "0" * 31, 123):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    probe.collect(123, Path("ignored"), session_id=invalid)
            select.assert_not_called()

    def test_bound_nonce_strict_assessment_uses_two_source_verified_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            nonce = "a" * 32

            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                self.assertEqual(request["marker"], "RR2R1|")
                directory.mkdir()
                index = self.copy(directory, self.index(request, request_path, published=1))
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 0, "", "")

            def assess(before, after, cli, output, **kwargs):
                self.assertEqual(before.name, "run-01")
                self.assertEqual(after.name, "run-02")
                self.assertEqual(kwargs["session_id"], nonce)
                self.assertEqual(kwargs["maximum_run_gap_seconds"], 120.0)
                self.assertEqual(cli.name, "RiftReader2.Cli.dll")
                output.mkdir()
                (output / "summary.json").write_text('{"status":"advanced"}')
                return {"status": "advancing-reference-in-pairing-window",
                        "diagnostics": {"advancing": 1},
                        "pairingWindow": {"withinWindow": True}}

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke), \
                 patch.object(probe.assess_typed_wire_runs, "assess", side_effect=assess) as strict:
                path, summary = probe.collect(123, root / "capture", max_scans=2,
                                              gap_seconds=0, session_id=nonce)
            strict.assert_called_once()
            reference = summary["referenceAssessment"]
            self.assertEqual(reference["status"], "advancing-reference-in-pairing-window")
            self.assertEqual(reference["runs"], [1, 2])
            self.assertEqual(reference["advancingComparisons"], 1)
            self.assertEqual(reference["summarySha256"],
                             probe.digest(root / "capture/reference-assessment/summary.json"))
            self.assertEqual(json.loads(path.read_text()), summary)

    def test_nonce_without_two_copied_runs_never_calls_decoder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                (directory / "index.json").write_text(json.dumps(self.index(request, request_path)))
                return subprocess.CompletedProcess(argv, 0, "", "")
            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke), \
                 patch.object(probe.assess_typed_wire_runs, "assess") as strict:
                _, summary = probe.collect(123, root / "capture", max_scans=1,
                                           gap_seconds=0, session_id="a" * 32)
            strict.assert_not_called()
            self.assertEqual(summary["referenceAssessment"],
                             {"status": "insufficient-independent-copied-runs",
                              "runsWithCopiedSnapshots": 0})

    def test_replay_retained_runs_never_touches_process_or_rescans(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                index = self.copy(directory, self.index(request, request_path, published=1))
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 0, "", "")
            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke):
                prior, _ = probe.collect(123, root / "source", max_scans=2,
                                         gap_seconds=0)
            def assess(before, after, _cli, output, **kwargs):
                self.assertEqual(before.name, "run-01")
                self.assertEqual(after.name, "run-02")
                self.assertEqual(kwargs["session_id"], "a" * 32)
                output.mkdir()
                (output / "summary.json").write_text('{"status":"advanced"}')
                return {"status": "advancing-reference-in-pairing-window",
                        "diagnostics": {"advancing": 1},
                        "pairingWindow": {"withinWindow": True}}
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe, "pinned_selection") as selection, \
                 patch.object(probe.subprocess, "run") as scanner, \
                 patch.object(probe.assess_typed_wire_runs, "assess", side_effect=assess) as decoder:
                path, result = probe.assess_saved(prior, root / "replayed", "a" * 32)
                selection.assert_not_called()
                scanner.assert_not_called()
                decoder.assert_called_once()
            self.assertEqual(result["sourceVerifiedRuns"], 2)
            self.assertEqual(result["runsWithCopiedSnapshots"], 2)
            self.assertEqual([r["sourceVerifiedSnapshots"] for r in result["runDiagnostics"]], [1, 1])
            self.assertEqual(result["status"], "advancing-reference-in-pairing-window")
            self.assertEqual(result["sourceSummarySha256"], probe.digest(prior))
            self.assertEqual(path.read_text(encoding="utf-8").strip(),
                             json.dumps(result, indent=2))
            # A nonce must never be invented merely to inspect retained sources.
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe, "pinned_selection") as selection, \
                 patch.object(probe.subprocess, "run") as scanner, \
                 patch.object(probe.assess_typed_wire_runs, "assess") as decoder:
                source_only_path, source_only = probe.assess_saved(prior, root / "source-only")
                selection.assert_not_called()
                scanner.assert_not_called()
                decoder.assert_not_called()
            self.assertEqual(source_only["status"], "nonce-unavailable-source-only")
            self.assertEqual(source_only["runsWithCopiedSnapshots"], 2)
            self.assertEqual([r["sourceVerifiedSnapshots"] for r in source_only["runDiagnostics"]], [1, 1])
            self.assertIn("no nonce decoding", source_only["qualification"])
            self.assertEqual(json.loads(source_only_path.read_text()), source_only)
            copied = root / "source/run-01/capture-01.snapshot.json"
            copied.write_bytes(copied.read_bytes() + b" ")
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe.assess_typed_wire_runs, "assess") as decoder:
                with self.assertRaisesRegex(ValueError, "scan-copy-source-hash-mismatch"):
                    probe.assess_saved(prior, root / "tampered", "a" * 32)
                decoder.assert_not_called()
            self.assertFalse((root / "tampered").exists())

    def test_replay_zero_copied_frames_is_explicitly_insufficient(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")
            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                (directory / "index.json").write_text(
                    json.dumps(self.index(request, request_path)))
                return subprocess.CompletedProcess(argv, 3, "", "")
            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke):
                prior, _ = probe.collect(123, root / "source", max_scans=1,
                                         gap_seconds=0)
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe, "pinned_selection") as selection, \
                 patch.object(probe.assess_typed_wire_runs, "assess") as decoder:
                _, result = probe.assess_saved(prior, root / "offline", "a" * 32)
                selection.assert_not_called()
                decoder.assert_not_called()
            self.assertEqual(result["status"], "insufficient-independent-copied-runs")
            self.assertEqual(result["runsWithCopiedSnapshots"], 0)
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe.assess_typed_wire_runs, "assess") as decoder:
                _, no_nonce = probe.assess_saved(prior, root / "source-only")
                decoder.assert_not_called()
            self.assertEqual(no_nonce["status"], "insufficient-independent-copied-runs")
            self.assertEqual(len(no_nonce["runDiagnostics"]), 1)
            self.assertEqual(no_nonce["runDiagnostics"][0]["sourceVerifiedSnapshots"], 0)

    def test_replay_rejects_changed_initial_cursor_despite_valid_scan_sources(self):
        """A source-audited replay cannot silently re-label its scan coverage."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "RiftReader2.Live.exe"
            reader.write_bytes(b"synthetic-reader")

            def invoke(argv, **_kwargs):
                request_path, directory = Path(argv[3]), Path(argv[5])
                request = json.loads(request_path.read_text())
                directory.mkdir()
                index = self.index(request, request_path)
                index["scan"]["nextAddress"] = hex(int(request["startAddress"], 16) + 0x10000)
                (directory / "index.json").write_text(json.dumps(index))
                return subprocess.CompletedProcess(argv, 3, "", "")

            with patch.object(probe.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(probe, "pinned_selection", return_value=SELECTION), \
                 patch.object(probe.subprocess, "run", side_effect=invoke):
                summary_path, summary = probe.collect(123, root / "source", max_scans=2,
                                                     gap_seconds=0)
            self.assertEqual(summary["initialCursor"], "0x10000")
            summary["initialCursor"] = "0x30000"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with patch.object(probe.socket, "gethostname", return_value=probe.HOST), \
                 patch.object(probe, "pinned_selection") as selection, \
                 patch.object(probe.subprocess, "run") as scanner:
                with self.assertRaisesRegex(ValueError, "saved-cursor-chain-mismatch"):
                    probe.assess_saved(summary_path, root / "replay")
                selection.assert_not_called()
                scanner.assert_not_called()
            self.assertFalse((root / "replay").exists())

    def test_replay_bad_nonce_or_wrong_host_fails_before_file_reads(self):
        with patch.object(probe.socket, "gethostname", return_value=probe.HOST):
            with self.assertRaises(ValueError):
                probe.assess_saved("absent.json", "output", "INVALID")
        with patch.object(probe.socket, "gethostname", return_value="WRONG"):
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                probe.assess_saved("absent.json", "output", "a" * 32)


if __name__ == "__main__":
    unittest.main()
