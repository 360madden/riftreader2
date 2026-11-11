import copy
import unittest
from unittest.mock import patch

from scripts import physical_manual_motion_probe as probe
from scripts.movement_controller import Position


TARGET = {"hostName": "AMD-DESKTOP", "processId": 123,
          "processStartUtcTicks": "12345", "executablePath": "C:\\RIFT\\rift_x64.exe",
          "executableSha256": "a" * 64, "hwnd": 1}
SELECTION = {"status": "ready", "target": TARGET}
FIRST = {"unitKey": "42", "positions": [Position(1, 2, 3)],
         "lastSampleUtc": "2026-01-01T00:00:01Z"}
SECOND = {"unitKey": "42", "positions": [Position(4, 4, 7)],
          "firstSampleUtc": "2026-01-01T00:00:03Z"}


class ManualMotionTests(unittest.TestCase):
    def run_probe(self, selections=None, captures=None):
        with patch.object(probe.physical_rift, "select_physical", side_effect=selections or [SELECTION] * 3), \
             patch.object(probe, "_check_capability"), \
             patch.object(probe, "_capture", side_effect=captures or [(FIRST, "a", "one"), (SECOND, "b", "two")]), \
             patch.object(probe.time, "sleep") as sleep:
            result = probe.probe("AMD-DESKTOP", 123, 2)
            sleep.assert_called_once_with(2)
            return result

    def test_delta_is_candidate(self):
        result = self.run_probe()
        self.assertEqual(result["deltaXYZ"], {"x": 3, "y": 2, "z": 4})
        self.assertEqual(result["planarDisplacementXZ"], 5)
        self.assertEqual(result["unitKey"], "42")
        self.assertEqual(result["status"], "candidate-only")

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
                    probe.probe("AMD-DESKTOP", 123, seconds)
            with self.assertRaises(ValueError):
                probe.probe("LEGION", 123, 2)
            select.assert_not_called()

    def test_missing_command_fails_closed(self):
        with patch.object(probe.physical_rift.NATIVE_EXE.__class__, "is_file", return_value=True), \
             patch.object(probe.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "sample-current-position-refresh-branch --pid N"
            with self.assertRaisesRegex(ValueError, "missing-position-command"):
                probe._check_capability()


if __name__ == "__main__":
    unittest.main()
