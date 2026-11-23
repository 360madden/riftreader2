import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_manual_motion_probe as probe
from scripts.movement_controller import Position
from tests.test_physical_route_preview import native


HOST = "RIFT-STATION"
TARGET = {"hostName": HOST, "processId": 123,
          "processStartUtcTicks": "12345", "executablePath": "C:\\RIFT\\rift_x64.exe",
          "executableSha256": "a" * 64, "hwnd": 1}
SELECTION = {"status": "ready", "target": TARGET}
FIRST = {"unitKey": "42", "positions": [Position(1, 2, 3)],
         "lastSampleUtc": "2026-01-01T00:00:01Z"}
SECOND = {"unitKey": "42", "positions": [Position(4, 4, 7)],
          "firstSampleUtc": "2026-01-01T00:00:03Z"}


class ManualMotionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(probe.socket, "gethostname", return_value=HOST))

    def run_probe(self, selections=None, captures=None):
        with patch.object(probe.physical_rift, "select_physical", side_effect=selections or [SELECTION] * 3), \
             patch.object(probe, "_check_capability"), \
             patch.object(probe, "_capture", side_effect=captures or [(FIRST, "a", "one"), (SECOND, "b", "two")]), \
             patch.object(probe.time, "sleep") as sleep:
            result = probe.probe(HOST.lower(), 123, 2)
            sleep.assert_called_once_with(2)
            return result

    def test_delta_is_candidate(self):
        result = self.run_probe()
        self.assertEqual(result["deltaXYZ"], {"x": 3, "y": 2, "z": 4})
        self.assertEqual(result["planarDisplacementXZ"], 5)
        self.assertEqual(result["unitKey"], "42")
        self.assertEqual(result["status"], "candidate-only")
        self.assertEqual(result["host"], HOST)

    def test_owner_change_blocks(self):
        second = dict(SECOND, unitKey="43")
        with self.assertRaisesRegex(ValueError, "native-owner-changed"):
            self.run_probe(captures=[(FIRST, "a", "one"), (second, "b", "two")])

    def test_process_change_blocks(self):
        changed = copy.deepcopy(SELECTION)
        changed["target"]["processStartUtcTicks"] = "12346"
        with self.assertRaisesRegex(ValueError, "process-identity-changed"):
            self.run_probe(selections=[SELECTION, changed])

    def test_time_overlap_blocks(self):
        second = dict(SECOND, firstSampleUtc="2026-01-01T00:00:01Z")
        with self.assertRaisesRegex(ValueError, "native-sample-time-overlap"):
            self.run_probe(captures=[(FIRST, "a", "one"), (second, "b", "two")])

    def test_invalid_input_fails_before_selection(self):
        with patch.object(probe.physical_rift, "select_physical") as select:
            for seconds in (0, 31, float("nan")):
                with self.assertRaises(ValueError):
                    probe.probe(HOST, 123, seconds)
            with self.assertRaisesRegex(ValueError, "host-mismatch"):
                probe.probe("LEGION", 123, 2)
            with self.assertRaisesRegex(ValueError, "positive-pid-required"):
                probe.probe(HOST, True, 2)
            select.assert_not_called()

    def create_bundle(self, output, *, stale_hash=False):
        def read(selection, kind, *, output, samples):
            self.assertEqual(selection, SELECTION)
            self.assertEqual((kind, samples), ("position", 1))
            source = native()
            index = probe.SOURCE_NAMES.index(output.name)
            source.update(requestedSamples=1, completedSamples=1, sourceBuildSha256=TARGET["executableSha256"])
            source["identity"] = {**TARGET, "processStartUtcTicks": int(TARGET["processStartUtcTicks"])}
            source["observations"] = [dict(source["observations"][index], index=1)]
            raw = json.dumps(source).encode("utf-8")
            output.write_bytes(raw)
            return {"status": "complete", "target": TARGET, "nativeRead": kind, "nativeOutput": str(output),
                    "nativeSourceSha256": "0" * 64 if stale_hash else hashlib.sha256(raw).hexdigest()}

        with patch.object(probe.physical_rift, "select_physical", return_value=SELECTION), \
             patch.object(probe.physical_rift, "read_native", side_effect=read), \
             patch.object(probe, "_check_capability"), patch.object(probe.time, "sleep"):
            return probe.probe(HOST, 123, 2, output=output)

    def test_moved_bundle_replays_without_a_live_host_and_rejects_edits(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        output = root / "original"
        result = self.create_bundle(output)
        moved = output.rename(root / "moved samples")
        report = moved / probe.REPORT_NAME
        with patch.object(probe.socket, "gethostname", return_value="ANALYSIS-PC"), \
             patch.object(probe.physical_rift, "select_physical") as select:
            replayed = probe.replay(report)
            select.assert_not_called()
        self.assertEqual(replayed["verification"], "source-replayed")
        self.assertEqual(replayed["planarDisplacementXZ"], result["planarDisplacementXZ"])

        saved = json.loads(report.read_text(encoding="utf-8"))
        report.write_text(json.dumps(dict(saved, planarDisplacementXZ=99)), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manual-motion-result-mismatch"):
            probe.replay(report)
        report.write_text(json.dumps(saved), encoding="utf-8")
        with (moved / "before.json").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "native-source-hash-mismatch"):
            probe.replay(report)

    def test_capture_with_stale_source_hash_has_no_completed_bundle(self):
        output = Path(self.enterContext(TemporaryDirectory())) / "stale"
        with self.assertRaisesRegex(ValueError, "native-source-hash-mismatch"):
            self.create_bundle(output, stale_hash=True)
        self.assertTrue((output / "before.json").is_file())
        self.assertFalse((output / probe.REPORT_NAME).exists())

    def test_missing_command_fails_closed(self):
        with patch.object(probe.physical_rift.NATIVE_EXE.__class__, "is_file", return_value=True), \
             patch.object(probe.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "sample-current-position-refresh-branch --pid N"
            with self.assertRaisesRegex(ValueError, "missing-position-command"):
                probe._check_capability()


if __name__ == "__main__":
    unittest.main()
