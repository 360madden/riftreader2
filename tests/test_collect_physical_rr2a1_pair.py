"""No-input tests for the physical RR2A1/native pair acquisition path."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from scripts import collect_physical_rr2a1_pair as capture


TARGET = {
    "processId": 1234,
    "processStartUtcTicks": "639300391441133615",
    "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8",
}
SELECTION = {"status": "ready", "ownerHost": "AMD-DESKTOP",
             "target": TARGET}


def report(tempdir, name):
    path = tempdir / name / "summary.json"
    path.parent.mkdir()
    path.write_text('{"test":"preserved"}\n', encoding="utf-8")
    return path, {"status": "candidate-only"}


def success():
    return {
        "status": "candidate-only",
        "sequenceWindows": [[20, 22], [25, 27]],
        "coordinateAgreementScreen": {"result": "consistent"},
    }


class PhysicalRR2A1PairTests(unittest.TestCase):
    def test_rejects_wrong_host_or_bad_bounds_without_file_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "capture"
            with patch.object(capture.socket, "gethostname", return_value="LEGION"):
                with self.assertRaisesRegex(ValueError, "wrong-host"):
                    capture.collect(1234, dest)
            self.assertFalse(dest.exists())
            with patch.object(capture.socket, "gethostname",
                              return_value="AMD-DESKTOP"):
                with self.assertRaisesRegex(ValueError, "invalid-collection-bounds"):
                    capture.collect(1234, dest, scan_bytes=1023)
            self.assertFalse(dest.exists())

    def test_epoch_change_blocks_before_scan_and_preserves_native_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "reader.exe"
            reader.write_bytes(b"test")
            prior, _ = report(root, "prior")
            target = root / "new-capture"
            with patch.object(capture.socket, "gethostname",
                              return_value="AMD-DESKTOP"), \
                 patch.object(capture.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(capture.probe, "digest", return_value="A"*64), \
                 patch.object(capture.probe, "pinned_selection",
                              side_effect=[SELECTION, dict(SELECTION,
                                  target=dict(TARGET, processId=5678))]), \
                 patch.object(capture.bracket, "collect",
                              return_value=(prior, {"status": "candidate-only"})), \
                 patch.object(capture, "scan_once") as scan:
                with self.assertRaisesRegex(ValueError, "process-epoch-changed"):
                    capture.collect(1234, target)
                scan.assert_not_called()
            self.assertTrue(target.is_dir())
            self.assertTrue(prior.is_file())

    def test_two_pass_collection_replays_and_pins_original_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "reader.exe"
            reader.write_bytes(b"reader")
            a, b = report(root, "before"), report(root, "after")
            i1, i2 = root / "index1", root / "index2"
            first = {"indexSha256": "1"*64, "publishedSnapshots": 3}
            second = {"indexSha256": "2"*64, "publishedSnapshots": 4}
            dest = root / "output"
            with patch.object(capture.socket, "gethostname",
                              return_value="AMD-DESKTOP"), \
                 patch.object(capture.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(capture.probe, "digest", return_value="A"*64), \
                 patch.object(capture.probe, "pinned_selection",
                              return_value=SELECTION), \
                 patch.object(capture.bracket, "collect",
                              side_effect=[a, b]) as brackets, \
                 patch.object(capture, "scan_once",
                              side_effect=[(i1, first), (i2, second)]) as scanner, \
                 patch.object(capture.compare, "compare",
                              return_value=success()) as replay, \
                  patch.object(capture.compare, "verify_capture_order",
                               return_value={"status": "source-verified-order"}) as order:
                path, output = capture.collect(1234, dest, samples=2, interval_ms=100)
                self.assertEqual(brackets.call_count, 2)
                self.assertEqual(scanner.call_count, 2)
                replay.assert_called_once_with(i1, i2, a[0], b[0])
                order.assert_called_once_with(i1, i2, a[0], b[0])
            self.assertTrue(path.is_file())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["target"], TARGET)
            self.assertEqual(saved["scanSnapshots"], [3, 4])
            self.assertEqual(saved["scanIndexSha256"]["first"], "1"*64)
            self.assertEqual(saved["comparison"]["sequenceWindows"],
                             [[20, 22], [25, 27]])
            self.assertEqual(saved["comparison"]["captureOrder"]["status"],
                             "source-verified-order")
            self.assertIn("no nonce", saved["qualification"])
            self.assertEqual(output, saved)

    def test_scan_constructs_rr2a1_request_and_rechecks_epoch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "reader.exe"
            reader.write_bytes(b"reader")
            path = root / "pass"
            lowered = dict(SELECTION, target=dict(
                TARGET, executableSha256=TARGET["executableSha256"].lower()))
            with patch.object(capture.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(capture.probe, "pinned_selection",
                              return_value=lowered) as pinned, \
                 patch.object(capture.probe, "digest",
                              return_value="A"*64), \
                 patch.object(capture.subprocess, "run",
                              return_value=Mock(returncode=0)) as proc, \
                 patch.object(capture.probe, "check_index",
                              return_value={"indexSha256": "B"*64}) as index:
                saved, result = capture.scan_once(
                    1234, lowered, "A"*64, path,
                    scan_bytes=1_048_576, scan_ms=1000)
                request = json.loads((path / "request.json").read_text())
                self.assertEqual(request["marker"], "RR2A1|")
                self.assertEqual(request["target"]["processId"], 1234)
                self.assertEqual(request["target"]["executableSha256"],
                                 TARGET["executableSha256"])
                self.assertEqual(request["maxScanBytes"], 1_048_576)
                self.assertEqual(pinned.call_count, 2)
                self.assertEqual(result["indexSha256"], "B"*64)
                self.assertEqual(saved, path / "scan" / "index.json")
                proc.assert_called_once()
                self.assertEqual(index.call_count, 1)

    def test_focus_uses_only_complete_markers_in_current_pinned_index(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.json"
            path.write_text(json.dumps({"candidates": [
                {"markerAddress": "0x318371E0", "status": "prefix-not-plausible"},
                {"markerAddress": "0x31B05D40", "status": "complete",
                 "snapshotSha256": "A"*64},
                {"markerAddress": "0x31D598E0", "status": "complete",
                 "snapshotSha256": "B"*64}]}))
            with patch.object(capture.probe, "digest", return_value="C"*64):
                self.assertEqual(capture.focused_second_pass(
                    path, {"indexSha256": "C"*64}), ("0x31A05000", 33_554_432))
                with self.assertRaisesRegex(ValueError, "index-changed"):
                    capture.focused_second_pass(path, {"indexSha256": "D"*64})
            path.write_text(json.dumps({"candidates": [
                {"markerAddress": "0x31B05D40", "status": "complete",
                 "snapshotSha256": "A"*64}]}))
            with patch.object(capture.probe, "digest", return_value="C"*64):
                self.assertIsNone(capture.focused_second_pass(
                    path, {"indexSha256": "C"*64}))

    def test_empty_focused_second_pass_falls_back_to_bounded_broad_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "reader.exe"
            reader.write_bytes(b"reader")
            a, b = report(root, "before"), report(root, "after")
            i1, ifocus, ibroad = (root / name for name in
                                   ("index1", "focused-index", "broad-index"))
            first = {"indexSha256": "1"*64, "publishedSnapshots": 3}
            missing = {"indexSha256": "F"*64, "publishedSnapshots": 0}
            recovered = {"indexSha256": "2"*64, "publishedSnapshots": 4}
            dest = root / "output"
            with patch.object(capture.socket, "gethostname",
                              return_value="AMD-DESKTOP"), \
                 patch.object(capture.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(capture.probe, "digest", return_value="A"*64), \
                 patch.object(capture.probe, "pinned_selection",
                              return_value=SELECTION), \
                 patch.object(capture.bracket, "collect",
                              side_effect=[a, b]), \
                 patch.object(capture, "focused_second_pass",
                              return_value=("0x31000000", 33_554_432)), \
                 patch.object(capture, "scan_once", side_effect=[
                     (i1, first), (ifocus, missing), (ibroad, recovered)]) as scan, \
                 patch.object(capture.compare, "compare",
                              return_value=success()) as replay, \
                 patch.object(capture.compare, "verify_capture_order",
                              return_value={"status": "source-verified-order"}):
                path, result = capture.collect(
                    1234, dest, focus_second_pass=True)
            self.assertTrue(path.is_file())
            self.assertEqual(scan.call_count, 3)
            self.assertEqual(scan.call_args_list[1].kwargs["start_address"],
                             "0x31000000")
            self.assertEqual(scan.call_args_list[2].kwargs["start_address"],
                             "0x10000")
            replay.assert_called_once_with(i1, ibroad, a[0], b[0])
            self.assertEqual(result["scanSnapshots"], [3, 4])
            self.assertTrue(result["secondPassFocus"]["fallbackUsed"])
            self.assertEqual(result["secondPassFocus"]["failedFocusedIndexSha256"],
                             "F"*64)
            self.assertEqual(result["scanIndexSha256"]["second"], "2"*64)

    def test_partial_scan_failure_keeps_request_for_diagnosis(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reader = root / "reader.exe"
            reader.write_bytes(b"reader")
            path = root / "pass"
            with patch.object(capture.physical_rift, "NATIVE_EXE", reader), \
                 patch.object(capture.probe, "pinned_selection",
                              return_value=SELECTION), \
                 patch.object(capture.probe, "digest", return_value="A"*64), \
                 patch.object(capture.subprocess, "run",
                              return_value=Mock(returncode=5)):
                with self.assertRaisesRegex(ValueError, "native-scanner-exit-5"):
                    capture.scan_once(1234, SELECTION, "A"*64, path,
                                      scan_bytes=1_048_576, scan_ms=1000)
                self.assertTrue((path / "request.json").is_file())


if __name__ == "__main__":
    unittest.main()
