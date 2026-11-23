"""Read-only RR2A1 physical build-1179 scan scope regression tests."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import collect_physical_rr2a1_pair as capture
from tests.test_collect_physical_rr2a1_pair import HOST, SELECTION, report, success

UPDATED_SHA = capture.probe.UPDATED_SHA
CURSOR = "0x14000000"


class ScopedRr2a1Tests(unittest.TestCase):
    def setUp(self):
        self.selection = deepcopy(SELECTION)
        self.selection["target"]["executableSha256"] = UPDATED_SHA

    def _mocks(self, root, *, fallback=False):
        reader = root / "reader.exe"
        reader.write_bytes(b"fake-test-reader")
        before, after = report(root, "before"), report(root, "after")
        scans = [(root / "first-index", {"indexSha256": "1" * 64, "publishedSnapshots": 3}),
                 (root / "second-index", {"indexSha256": "2" * 64, "publishedSnapshots": 4})]
        if fallback:
            scans = [(root / "first-index", {"indexSha256": "1" * 64, "publishedSnapshots": 3}),
                     (root / "focused-index", {"indexSha256": "F" * 64, "publishedSnapshots": 0}),
                     (root / "second-index", {"indexSha256": "2" * 64, "publishedSnapshots": 4})]
        return reader, before, after, scans

    def test_custom_start_is_forwarded_to_both_scans_with_1179_identity(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            reader, before, after, scans = self._mocks(root)
            with (patch.object(capture.probe.socket, "gethostname", return_value=HOST),
                  patch.object(capture.physical_rift, "NATIVE_EXE", reader),
                  patch.object(capture.probe, "digest", return_value="A" * 64),
                  patch.object(capture.probe, "pinned_selection", return_value=self.selection),
                  patch.object(capture.bracket, "collect", side_effect=[before, after]),
                  patch.object(capture, "scan_once", side_effect=scans) as scan,
                  patch.object(capture.compare, "compare", return_value=success()),
                  patch.object(capture.compare, "verify_capture_order",
                               return_value={"status": "source-verified-order"})):
                _, result = capture.collect(1234, root / "output", start_address=CURSOR)
            self.assertEqual(result["status"], "candidate-only")
            self.assertEqual(result["target"]["executableSha256"], UPDATED_SHA)
            self.assertEqual(result["secondPassFocus"]["startAddress"], CURSOR)
            self.assertEqual(scan.call_count, 2)
            self.assertTrue(all(call.kwargs["start_address"] == CURSOR
                                for call in scan.call_args_list))

    def test_focused_failure_retries_at_original_custom_scope(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            reader, before, after, scans = self._mocks(root, fallback=True)
            with (patch.object(capture.probe.socket, "gethostname", return_value=HOST),
                  patch.object(capture.physical_rift, "NATIVE_EXE", reader),
                  patch.object(capture.probe, "digest", return_value="A" * 64),
                  patch.object(capture.probe, "pinned_selection", return_value=self.selection),
                  patch.object(capture.bracket, "collect", side_effect=[before, after]),
                  patch.object(capture, "focused_second_pass",
                               return_value=("0x15000000", 33_554_432)),
                  patch.object(capture, "scan_once", side_effect=scans) as scan,
                  patch.object(capture.compare, "compare", return_value=success()),
                  patch.object(capture.compare, "verify_capture_order",
                               return_value={"status": "source-verified-order"})):
                _, result = capture.collect(1234, root / "out", focus_second_pass=True,
                                            start_address=CURSOR)
            self.assertEqual(scan.call_count, 3)
            self.assertEqual([call.kwargs["start_address"] for call in scan.call_args_list],
                             [CURSOR, "0x15000000", CURSOR])
            self.assertTrue(result["secondPassFocus"]["fallbackUsed"])

    def test_bad_start_refused_without_contacting_process(self):
        with TemporaryDirectory() as temp, patch.object(capture.probe, "pinned_selection") as pin:
            for i, bad in enumerate(("0x0", "0x00014000000", "0x1400000f",
                                     "0X14000000", "0xzzzz", "0x800000000000")):
                with self.subTest(start=bad), self.assertRaises(ValueError):
                    capture.collect(1234, Path(temp) / f"bad-{i}", start_address=bad)
            pin.assert_not_called()

    def test_cli_forwards_custom_cursor_without_implicit_input(self):
        output = {"status": "candidate-only", "scanSnapshots": [3, 4],
                  "comparison": dict(success(), luaPlayerIdCandidate="u035400012FA2D207",
                                     positionCandidates={})}
        with patch.object(capture, "collect", return_value=(Path("summary.json"), output)) as method:
            with redirect_stdout(StringIO()):
                result = capture.main(["--physical-pid", "1234",
                                       "--start-address", CURSOR])
        self.assertEqual(result, 0)
        self.assertEqual(method.call_args.kwargs["start_address"], CURSOR)


if __name__ == "__main__":
    unittest.main()
