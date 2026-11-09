from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import navigation_anchors as anchors
from scripts import plan_anchor_route as route
from scripts.plan_anchor_route import main, plan_route
from scripts.plan_steered_waypoint import SteeringPlanError
from tests.test_plan_steered_waypoint import calibration


class AnchorRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calibration = self._write("calibration.json",
                                       calibration((0, 4, 0), (1, 4, 0), 1, (1, 0)))

    def _write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _catalog(self, first=(1, 4, 0), second=(3, 4, 0.03), second_build="A" * 64):
        entries = []
        for anchor_id, point, build in (("Start", first, "A" * 64),
                                         ("Dock", second, second_build)):
            entries.append({
                "id": anchor_id, "label": anchor_id,
                "position": dict(zip(("x", "y", "z"), point)),
                "zoneLabel": "Test Zone",
                "source": {"kind": "addon-feedback-receipt",
                           "gameBuildSha256": build, "evidenceSha256": "B" * 64,
                           "capturedAtUtc": "2026-11-08T13:00:00Z"},
                "qualification": "offline-reference-only"})
        return self._write("catalog.json", {
            "schemaVersion": 1, "coordinateFrame": anchors.COORDINATE_FRAME,
            "anchors": entries})

    def test_advances_past_currently_nearby_anchor_without_runner(self):
        result = plan_route(self.calibration, self._catalog(), ["start", "dock"])
        self.assertEqual(result["decision"], "forward")
        self.assertEqual(result["routeAnchorIds"], ["Start", "Dock"])
        self.assertEqual(result["withinToleranceAtCalibrationIds"], ["Start"])
        self.assertEqual(result["nextAnchorId"], "Dock")
        self.assertEqual(result["nextIndex"], 1)
        self.assertIs(result["movementEligible"], False)
        self.assertEqual(result["step"]["planarGoal"], {"x": 3.0, "z": .03})
        self.assertNotIn("runnerArgumentFragment", result["step"])

    def test_first_pending_not_skipped_when_far(self):
        result = plan_route(self.calibration, self._catalog(first=(3, 4, 0)),
                            ["Start", "Dock"])
        self.assertEqual(result["nextAnchorId"], "Start")
        self.assertEqual(result["withinToleranceAtCalibrationIds"], [])
        self.assertEqual(result["step"]["decision"], "forward")

    def test_completed_prefix_is_explicit_and_ordered(self):
        catalog = self._catalog()
        result = plan_route(self.calibration, catalog, ["Start", "Dock"], ["start"])
        self.assertEqual(result["declaredCompletedIds"], ["Start"])
        self.assertEqual(result["nextAnchorId"], "Dock")
        with self.assertRaisesRegex(SteeringPlanError, "ordered route prefix"):
            plan_route(self.calibration, catalog, ["Start", "Dock"], ["Dock"])
        with self.assertRaisesRegex(SteeringPlanError, "duplicate"):
            plan_route(self.calibration, catalog, ["Start", "start"])

    def test_declared_completion_is_not_a_live_arrival_claim(self):
        result = plan_route(self.calibration, self._catalog(), ["Start", "Dock"],
                            ["Start", "Dock"])
        self.assertEqual(result["decision"], "within-tolerance-or-declared-complete")
        self.assertEqual(result["withinToleranceAtCalibrationIds"], [])
        self.assertEqual(result["declaredCompletedIds"], ["Start", "Dock"])
        self.assertIsNone(result["nextAnchorId"])
        self.assertFalse(result["movementEligible"])

    def test_rejects_foreign_build_even_if_later_in_route(self):
        with self.assertRaisesRegex(SteeringPlanError, "game build differs"):
            plan_route(self.calibration, self._catalog(second_build="C" * 64),
                       ["Start", "Dock"])

    def test_changed_calibration_is_rejected_before_accepting_arrived_step(self):
        catalog = self._catalog(first=(10, 4, 0), second=(12, 4, 0))
        original = calibration((0, 4, 0), (1, 4, 0), 1, (1, 0))
        for changed, nonce, digest in (("hash", "nonce", "E" * 64),
                                       ("identity", "other", "D" * 64)):
            with self.subTest(changed=changed):
                replacement = calibration((9, 4, 0), (10, 4, 0), 101,
                                          (1, 0), nonce=nonce)
                calls = []

                def read_snapshot(path):
                    calls.append(path)
                    if len(calls) == 1:
                        return original, "D" * 64
                    return replacement, digest

                # The later snapshot would report arrival at Start. It must not
                # advance the route pinned to the original calibration at x=1.
                with patch.object(route.steering, "load", side_effect=read_snapshot):
                    with self.assertRaisesRegex(SteeringPlanError,
                                                "calibration changed during route planning"):
                        plan_route(self.calibration, catalog, ["Start", "Dock"])
                self.assertEqual(len(calls), 3)

    def test_cli_writes_one_new_output_and_no_live_runner(self):
        catalog = self._catalog()
        output = self.root / "route.json"
        argv = ["--catalog", str(catalog), "--current-w-calibration",
                str(self.calibration), "--anchor", "Start", "--anchor", "Dock",
                "--output", str(output)]
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(argv), 0)
        saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved["nextAnchorId"], "Dock")
        self.assertEqual(json.loads(stdout.getvalue()), saved)
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(argv), 2)
        self.assertIn("File exists", stdout.getvalue())


    def test_direct_script_entrypoint_displays_help(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "plan_anchor_route.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--help"], cwd=str(script.parent.parent),
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--completed-anchor", completed.stdout)


if __name__ == "__main__":
    unittest.main()
