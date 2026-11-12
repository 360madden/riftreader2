from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as waypoint
from tests.test_physical_waypoints import SimulatedRift


class WaypointCliTests(unittest.TestCase):
    def test_saved_route_requires_explicit_execution(self):
        with patch.object(waypoint, "PhysicalAdapter") as adapter, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                               "--run-route", "route.json"])
        self.assertEqual(2, caught.exception.code)
        adapter.assert_not_called()

    def test_saved_route_keeps_every_leg_in_one_receipt(self):
        adapter = SimulatedRift()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            route = root / "route.json"
            route.write_text(json.dumps({"waypoints": [["Ahead", 0, 1], ["Home", 0, 0]]}))
            output = io.StringIO()
            with patch.object(waypoint, "ROOT", root), patch.object(waypoint, "PhysicalAdapter", return_value=adapter), redirect_stdout(output):
                code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                      "--run-route", str(route), "--execute"])
            receipt = json.loads(output.getvalue().splitlines()[-1])
            result = json.loads(Path(receipt["receipt"]).read_text())
            self.assertEqual(0, code)
            self.assertEqual("arrived", result["status"])
            self.assertEqual(2, result["waypointCount"])
            self.assertEqual(2, len(result["legs"]))
            self.assertEqual(["Ahead", "Home"], [leg["name"] for leg in result["legs"]])
            self.assertTrue(result["allPulsesReleased"])
            self.assertLessEqual(result["distance"], .3)
            self.assertEqual(len(adapter.calls), result["pulses"])

    def test_bad_route_coordinates_send_no_input(self):
        adapter = SimulatedRift()
        with tempfile.TemporaryDirectory() as directory:
            route = Path(directory) / "route.json"
            route.write_text(json.dumps({"waypoints": [["Bad", float("nan"), 0]]}))
            with patch.object(waypoint, "PhysicalAdapter", return_value=adapter), redirect_stdout(io.StringIO()):
                code = waypoint.main(["--expected-host", "AMD-DESKTOP", "--physical-pid", "123",
                                      "--run-route", str(route), "--execute"])
        self.assertEqual(2, code)
        self.assertFalse(adapter.calls)


if __name__ == "__main__":
    unittest.main()
