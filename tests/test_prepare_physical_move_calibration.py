"""Offline checks of exact-target calibration preparation and replay."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from scripts import physical_rift
from scripts import prepare_physical_move_calibration as preflight
from tests.test_physical_facing import report as facing_report
from tests.test_physical_only_selection import IDENTITY


class CalibrationPreflightTests(unittest.TestCase):
    def setUp(self):
        # Use the synthetic reader rather than this machine's registered bundle.
        self.enterContext(patch.dict("os.environ", {
            "RR2_PHYSICAL_TOOLS_ROOT": "debug", "RR2_NATIVE_READER": "",
        }))
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "review"
        self.target = dict(IDENTITY, hostName="RIFT-STATION", executablePath=r"C:\RIFT\rift_x64.exe")
        self.selection = {"status": "ready", "target": self.target}
        self.reader = self.root / "native-reader.exe"
        self.reader.touch()
        self.enterContext(patch.object(physical_rift.socket, "gethostname", return_value="RIFT-STATION"))
        self.enterContext(patch.object(physical_rift, "NATIVE_EXE", self.reader))

    def capture(self, selection, kind, path, *, samples, interval_ms, native_reader=None):
        self.assertEqual((selection, kind, samples, interval_ms), (self.selection, "facing", 3, 150))
        report = facing_report()
        identity = {**report["identity"], "executablePath": self.target["executablePath"]}
        report["identity"] = identity
        for row in report["observations"]:
            row["identity"] = identity
            row["positionOrientationCandidate"]["identity"] = identity
            bits = row["rawBits"][4:]
            row["entityPositionRawBits"] = bits
            row["entityPositionCandidate"] = dict(zip(("x", "y", "z"),
                [struct.unpack("<f", struct.pack("<I", bit))[0] for bit in bits]))
        path.write_text(json.dumps(report), encoding="utf-8")
        return {"status": "complete", "target": self.target, "nativeRead": "facing",
                "nativeOutput": str(path), "nativeSourceSha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_pins_raw_facing_and_rechecks_window_without_input(self):
        published = self.root / "published-reader.exe"
        published.touch()
        inspection = {"target": {"isForeground": False}, "desktopInputsDown": []}
        with patch.object(physical_rift, "select_physical", return_value=self.selection) as select, \
             patch.object(physical_rift, "inspect_movement_target", return_value=inspection) as inspect, \
             patch.object(physical_rift, "read_native", side_effect=self.capture) as read:
            path, report = preflight.prepare("rift-station", self.target["processId"], self.output,
                                             native_reader=published)
        self.assertEqual(path, self.output / preflight.SUMMARY)
        self.assertEqual(select.call_count, 2)
        self.assertEqual(inspect.call_args_list, [call(self.target, native_reader=published)] * 2)
        self.assertEqual(read.call_args.kwargs["native_reader"], published)
        self.assertFalse(report["inputSent"])
        self.assertFalse(report["focusRequested"])
        self.assertEqual(preflight.verify_preflight(path)[:2], (self.target, report["baseline"]))

        pulse = json.loads(path.read_bytes())
        pulse["baseline"]["unitKey"] = "41"
        path.write_text(json.dumps(pulse), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "calibration-preflight-baseline-mismatch"):
            preflight.verify_preflight(path)

    def test_held_input_and_wrong_host_prevent_capture(self):
        with patch.object(physical_rift, "select_physical", return_value=self.selection) as select, \
             patch.object(physical_rift, "inspect_movement_target", return_value={"desktopInputsDown": ["w"]}), \
             patch.object(physical_rift, "read_native") as read:
            with self.assertRaisesRegex(ValueError, "wrong-host"):
                preflight.prepare("OTHER-PC", self.target["processId"], self.output)
            select.assert_not_called()
            with self.assertRaisesRegex(ValueError, "desktop-inputs-held"):
                preflight.prepare("RIFT-STATION", self.target["processId"], self.output)
            read.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_target_after_native_capture_withholds_preflight(self):
        inspection = {"target": {"isForeground": False}, "desktopInputsDown": []}
        changed = dict(self.selection, target=dict(self.target, hwnd=self.target["hwnd"] + 1))
        with patch.object(physical_rift, "select_physical", side_effect=[self.selection, changed]), \
             patch.object(physical_rift, "inspect_movement_target", return_value=inspection), \
             patch.object(physical_rift, "read_native", side_effect=self.capture):
            with self.assertRaisesRegex(ValueError, "calibration-target-changed"):
                preflight.prepare("RIFT-STATION", self.target["processId"], self.output)
        self.assertFalse((self.output / preflight.SUMMARY).exists())

    def test_identity_inspection_cli_has_no_action_or_focus_flags(self):
        target = self.target
        published = self.root / "published-reader.exe"
        native_target = dict(machineName=target["hostName"], processId=target["processId"],
                             processStartUtcTicks=int(target["processStartUtcTicks"]),
                             executablePath=target["executablePath"], executableSha256=target["executableSha256"],
                             windowHandle=hex(target["hwnd"]))
        receipt = {"status": "inspected-target", "target": native_target, "inputSent": False,
                   "focusRequested": False, "desktopInputsDown": []}
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(receipt))
        with patch.object(physical_rift.subprocess, "run", return_value=completed) as run:
            self.assertEqual(physical_rift.inspect_movement_target(target, native_reader=published), receipt)
            self.assertEqual(run.call_args.args[0], [str(published), "move-key", "--inspect", "--pid",
                str(target["processId"]), "--expect-start-ticks", target["processStartUtcTicks"],
                "--expect-sha256", target["executableSha256"], "--expect-hwnd", hex(target["hwnd"]), "--json"])
            changed = deepcopy(receipt)
            changed["target"]["windowHandle"] = "0x10"
            completed.stdout = json.dumps(changed)
            with self.assertRaisesRegex(ValueError, "movement-inspection-identity-mismatch"):
                physical_rift.inspect_movement_target(target)
