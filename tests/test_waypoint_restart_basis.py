"""Offline restart binding and route feedback tests; no native input."""
import copy
from datetime import datetime, timedelta, timezone
import threading
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as waypoints
from scripts.movement_controller import Position
from tests.test_physical_waypoints import SimulatedRift


class RestartBasisTests(unittest.TestCase):
    def setUp(self):
        self.basis = {"identity": {"machine": "AMD-DESKTOP", "processId": 10,
                     "processStartUtcTicks": "100", "gameBuildSha256": "a" * 64,
                     "unitKey": "123"}}
        self.selection = {"status": "ready", "target": {"processStartUtcTicks": "200",
                          "executableSha256": "a" * 64, "processId": 20, "hwnd": 1234}}
        self.native = {"status": "complete", "nativeOutput": "mock", "nativeValues": {
            "sampledAtUtc": datetime.now(timezone.utc).isoformat(), "playerKey": "123",
            "positionSource": "entity-owned-position-component+0x48",
            "bodyBearingDegreesCandidate": 0, "positionXYZCandidate": {"x": 1, "y": 2, "z": 3}}}

    def make_adapter(self):
        with patch.object(waypoints.physical_rift, "select_physical", return_value=self.selection), \
             patch.object(waypoints.physical_rift, "read_native", return_value=self.native) as read, \
             patch.object(waypoints, "read_basis", return_value=(self.basis, "basis-hash")), \
             patch.object(waypoints.PhysicalAdapter, "pulse", side_effect=AssertionError("unexpected input")) as pulse:
            adapter = waypoints.PhysicalAdapter("AMD-DESKTOP", 20, "mock-basis")
            pulse.assert_not_called()
            return adapter, read

    def test_new_epoch_binds_seed_without_mutating_basis(self):
        original = copy.deepcopy(self.basis)
        adapter, read = self.make_adapter()
        self.assertEqual(self.basis, original)
        self.assertTrue(adapter.basis_reused)
        self.assertEqual(adapter.binding["mode"], "reused-seed")
        self.assertEqual(adapter.binding["basisSha256"], "basis-hash")
        self.assertEqual(adapter.binding["calibrationIdentity"], original["identity"])
        self.assertIn("runtimeIdentity", adapter.binding)
        read.assert_called()

    def test_measured_epoch_is_not_reused(self):
        self.basis["identity"].update(processId=20, processStartUtcTicks="200")
        adapter, _ = self.make_adapter()
        self.assertFalse(adapter.basis_reused)
        self.assertEqual(adapter.binding["mode"], "measured-epoch")

    def test_missing_or_invalid_window_rejected_before_input(self):
        for hwnd in (None, 0, -1, True):
            with self.subTest(hwnd=hwnd):
                self.selection["target"]["hwnd"] = hwnd
                with self.assertRaisesRegex(ValueError, "window"):
                    self.make_adapter()

    def test_mismatched_machine_build_player_or_stale_pose_rejected(self):
        for case in ("machine", "build", "player", "stale"):
            with self.subTest(case=case):
                self.setUp()
                if case == "machine": self.basis["identity"]["machine"] = "OTHER"
                elif case == "build": self.selection["target"]["executableSha256"] = "b" * 64
                elif case == "player": self.native["nativeValues"]["playerKey"] = "999"
                else: self.native["nativeValues"]["sampledAtUtc"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
                with self.assertRaises(ValueError): self.make_adapter()


class ReusedSeedRouteTests(unittest.TestCase):
    def test_no_response_stops_after_first_normal_pulse(self):
        class StuckSeed(SimulatedRift):
            basis_reused = True
            def __init__(self): super().__init__(stuck=True)
            def pulse(self, action, *, focus):
                super().pulse(action, focus=focus)
                return {"keys": [action.key], "holdMilliseconds": action.hold_ms,
                        "observedMilliseconds": action.hold_ms + 5, "releaseSucceeded": True}
        adapter = StuckSeed()
        with self.assertRaises(ValueError):
            waypoints.run_leg(adapter, 2, 0, threading.Event())
        self.assertEqual(len(adapter.calls), 1)

    def test_wrong_direction_stops_after_first_normal_pulse(self):
        class WrongSeed(SimulatedRift):
            basis_reused = True
            def pulse(self, action, *, focus):
                self.calls.append((action, focus))
                cal = self.calibrations(None)[action.key]
                self.position = Position(self.position.x - cal.dx_per_ms * action.hold_ms,
                                         10, self.position.z - cal.dz_per_ms * action.hold_ms)
                return {"keys": [action.key], "holdMilliseconds": action.hold_ms,
                        "observedMilliseconds": action.hold_ms + 5, "releaseSucceeded": True}
        adapter = WrongSeed()
        with self.assertRaises(ValueError):
            waypoints.run_leg(adapter, 2, 0, threading.Event())
        self.assertEqual(len(adapter.calls), 1)


if __name__ == "__main__": unittest.main()
