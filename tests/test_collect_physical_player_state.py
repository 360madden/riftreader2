"""No-process tests for the physical-native composite player-state collector."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import collect_physical_player_state as state

OWNER = {
    "hostName": state.HOST, "processId": 123,
    "processStartUtcTicks": "639300936028818696",
    "executableSha256": state.BUILD_SHA,
    "hwnd": 789, "executablePath": r"C:\Games\RIFT\rift_x64.exe",
}
SELECTION = {"status": "ready", "ownerHost": state.HOST, "target": OWNER}


class StateTests(unittest.TestCase):
    def fake_read(self, selection, kind, path, *, samples, interval_ms,
                  key="239816685251645959", module=123456, epoch=None):
        identity = {
            "processId": OWNER["processId"],
            "processStartUtcTicks": int(epoch or OWNER["processStartUtcTicks"]),
            "executableSha256": state.BUILD_SHA,
            "moduleBaseAddress": module, "moduleSize": 1234567,
        }
        path.write_text(json.dumps({"status": "complete", "identity": identity,
                                    "completedSamples": samples}), encoding="utf-8")
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        burst = {"status": "candidate-only", "sourceReportSha256": source_sha,
                 "sourceBuildSha256": state.BUILD_SHA,
                 "processId": OWNER["processId"],
                 "processStartUtcTicks": OWNER["processStartUtcTicks"],
                 "unitKey": key, "sampleCount": samples}
        return {"status": "complete", "nativeRead": kind, "target": selection["target"],
                "nativeOutput": str(path),
                "nativeValues": {"unitKey": key, "x": 5.2},
                **({"nativeBurstSummary": burst}
                   if kind == "vitals" else {})}

    def test_three_existing_native_readers_produce_hashed_same_owner_receipt(self):
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical",
                          return_value=SELECTION) as select, \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read) as read:
            path, report = state.collect(123, Path(temp) / "result", samples=3)
            self.assertEqual(select.call_count, 7)
            self.assertEqual(read.call_count, 3)
            self.assertEqual([call.args[1] for call in read.call_args_list], list(state.KINDS))
            self.assertEqual(report["status"], "complete-candidate")
            self.assertEqual(report["selfKeyCandidate"], "239816685251645959")
            self.assertIn("NOT atomic", report["qualification"])
            self.assertEqual(json.loads(path.read_text()), report)
            for row in report["sources"].values():
                self.assertEqual(row["samples"], 3)
                self.assertEqual(hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest().upper(),
                                 row["sourceSha256"])

    def test_wrong_host_or_invalid_pid_never_reads_process(self):
        with patch.object(state.socket, "gethostname", return_value="OTHER"), \
             patch.object(state.physical_rift, "select_physical") as select:
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                state.collect(123, Path("unused"))
            select.assert_not_called()
        with patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical") as select:
            with self.assertRaisesRegex(ValueError, "explicit-pid-required"):
                state.collect(0, Path("unused"))
            select.assert_not_called()

    def test_unavailable_or_wrong_build_never_reads(self):
        invalid = deepcopy(SELECTION)
        invalid["target"]["executableSha256"] = "0" * 64
        with patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=invalid), \
             patch.object(state.physical_rift, "read_native") as read:
            with self.assertRaisesRegex(ValueError, "physical-process-identity-unavailable"):
                state.collect(123, Path("unused"))
            read.assert_not_called()

    def test_changed_epoch_between_readers_refused(self):
        changed = deepcopy(SELECTION)
        changed["target"]["processStartUtcTicks"] = "11111"
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical",
                          side_effect=[SELECTION, SELECTION, changed]), \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read) as read:
            with self.assertRaisesRegex(ValueError, "epoch-changed-after-read"):
                state.collect(123, Path(temp) / "out")
            self.assertEqual(read.call_count, 1)

    def test_cross_source_unit_key_change_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            key = "555" if kind == "position" else "444"
            return self.fake_read(selection, kind, path, samples=samples,
                                  interval_ms=interval_ms, key=key)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake) as read:
            with self.assertRaisesRegex(ValueError, "self-key-changed"):
                state.collect(123, Path(temp) / "out")
            self.assertEqual(read.call_count, 2)

    def test_changed_module_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            return self.fake_read(selection, kind, path, samples=samples,
                                  interval_ms=interval_ms,
                                  module=987 if kind == "position" else 123456)
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "module-owner-changed"):
                state.collect(123, Path(temp) / "out")

    def test_duplicate_source_owner_key_is_rejected_before_summary(self):
        def ambiguous(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace('"processId": 123',
                                        '"processId": 999, "processId": 123', 1),
                            encoding="utf-8")
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=ambiguous):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "duplicate-json-key"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_nonfinite_source_json_is_rejected_before_summary(self):
        def nonfinite(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace('"status": "complete"',
                                        '"untrusted": NaN, "status": "complete"', 1),
                            encoding="utf-8")
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=nonfinite):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "nonfinite-json"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_vitals_burst_claiming_another_source_is_rejected_before_summary(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            if kind == "vitals":
                result["nativeBurstSummary"]["sourceReportSha256"] = "0" * 64
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "vitals-burst-source-mismatch"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_vitals_burst_claiming_different_process_epoch_is_rejected(self):
        def fake(selection, kind, path, *, samples, interval_ms):
            result = self.fake_read(selection, kind, path, samples=samples,
                                    interval_ms=interval_ms)
            if kind == "vitals":
                result["nativeBurstSummary"]["processStartUtcTicks"] = "111"
            return result

        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=fake):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "vitals-burst-source-mismatch"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_reader_unavailable_does_not_publish_complete_summary(self):
        with TemporaryDirectory() as temp, \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", return_value={"status": "blocked"}):
            dest = Path(temp) / "out"
            with self.assertRaisesRegex(ValueError, "player-context-read-unavailable"):
                state.collect(123, dest)
            self.assertFalse((dest / "summary.json").exists())

    def test_invalid_bounds_do_not_select_process(self):
        with patch.object(state, "pin") as select:
            for samples, interval in ((1, 0), (11, 0), (3, -1), (3, 1001)):
                with self.subTest(samples=samples, interval=interval):
                    with self.assertRaisesRegex(ValueError, "invalid-sampling-bounds"):
                        state.collect(123, Path("unused"), samples=samples, interval_ms=interval)
            select.assert_not_called()

    def test_relative_output_directory_is_rooted_locally(self):
        with TemporaryDirectory() as temp, \
             patch.object(state, "ROOT", Path(temp)), \
             patch.object(state.socket, "gethostname", return_value=state.HOST), \
             patch.object(state.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(state.physical_rift, "read_native", side_effect=self.fake_read):
            path, report = state.collect(123, Path("result"))
            self.assertEqual(path, Path(temp) / "result" / "summary.json")
            self.assertEqual(report["sources"]["position"]["samples"], 3)


if __name__ == "__main__":
    unittest.main()
