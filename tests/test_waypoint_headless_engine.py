"""Headless movement-engine selection without opening RIFT or sending input."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import physical_waypoints as app


def leg(name="Point", *, total_hold=...):
    value = {
        "status": "arrived",
        "name": name,
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        "bearing": 90.0,
        "distance": 0.1,
        "pulses": 2,
        "heldInputMilliseconds": 125.0,
        "releaseSucceeded": True,
    }
    if total_hold is not ...:
        value["totalHoldMs"] = total_hold
    return value


class HeadlessMovementEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "artifacts").mkdir()
        self.route = self.root / "route.json"
        self.route.write_text(json.dumps({"waypoints": [["A", 1, 3], ["B", 2, 4]]}),
                              encoding="utf-8")
        self.base = ["--expected-host", "AMD-DESKTOP", "--physical-pid", "123", "--execute"]
        self.adapter = SimpleNamespace(binding={"runtimeIdentity": {"unitKey": "7"}})

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, argv, *, pulse=None, continuous=None, play=None, teach=None):
        pulse = pulse or Mock(return_value=[leg(total_hold=50), leg("B", total_hold=75)])
        continuous = continuous or Mock(return_value=[leg(), leg("B")])
        output = io.StringIO()
        patches = (
            patch.object(app, "ROOT", self.root),
            patch.object(app, "PhysicalAdapter", return_value=self.adapter),
            patch.object(app, "cli_stop_controls", side_effect=lambda stop: contextlib.nullcontext()),
            patch.object(app, "run_route", pulse),
            patch("scripts.continuous_move.run_continuous_route", continuous),
            patch("scripts.waypoint_playback.play_route", play) if play is not None else contextlib.nullcontext(),
            patch("scripts.waypoint_playback.teach_route", teach) if teach is not None else contextlib.nullcontext(),
        )
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            with contextlib.redirect_stdout(output):
                code = app.main(self.base + list(argv))
        lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        receipt = json.loads(Path(lines[-1]["receipt"]).read_text(encoding="utf-8"))
        return code, receipt, pulse, continuous, lines

    def test_run_route_defaults_to_continuous_and_preserves_unknown_hold_metric(self):
        code, receipt, pulse, continuous, _ = self.invoke(["--run-route", str(self.route)])
        self.assertEqual(0, code)
        continuous.assert_called_once()
        pulse.assert_not_called()
        self.assertEqual("continuous", receipt["movementEngine"])
        self.assertEqual(4, receipt["pulses"])
        self.assertIsNone(receipt["totalHoldMs"])
        self.assertEqual([125.0, 125.0],
                         [row["heldInputMilliseconds"] for row in receipt["legs"]])
        self.assertTrue(receipt["allInputsReleased"])

    def test_explicit_pulse_uses_original_runner_and_aggregates_known_hold_time(self):
        code, receipt, pulse, continuous, _ = self.invoke(
            ["--movement-engine", "pulse", "--run-route", str(self.route)])
        self.assertEqual(0, code)
        pulse.assert_called_once()
        continuous.assert_not_called()
        self.assertEqual(("pulse", 125),
                         (receipt["movementEngine"], receipt["totalHoldMs"]))

    def test_play_route_receives_selected_runner(self):
        for engine, expected in (("continuous", "continuous"), ("pulse", "pulse")):
            with self.subTest(engine=engine):
                play = Mock(return_value=([leg()], SimpleNamespace(next_index=1)))
                argv = ["--play-route", str(self.route)]
                if engine == "pulse":
                    argv[0:0] = ["--movement-engine", "pulse"]
                code, receipt, pulse, continuous, _ = self.invoke(argv, play=play)
                self.assertEqual(0, code)
                selected = play.call_args.kwargs["runner"]
                self.assertIs(selected, continuous if expected == "continuous" else pulse)
                self.assertEqual(expected, receipt["movementEngine"])

    def test_record_to_always_teaches_with_pulse_runner(self):
        recorded = self.root / "recorded.json"
        teach = Mock(return_value=([leg(total_hold=40)], {"waypoints": [["Observed", 1, 3]]}))
        code, receipt, pulse, continuous, lines = self.invoke(
            ["--go", "1", "3", "--record-to", str(recorded)], teach=teach)
        self.assertEqual(0, code)
        continuous.assert_not_called()
        self.assertIs(teach.call_args.kwargs["runner"], pulse)
        self.assertEqual("pulse", receipt["movementEngine"])
        self.assertEqual(40, receipt["totalHoldMs"])
        self.assertEqual({"waypoints": [["Observed", 1, 3]]},
                         json.loads(recorded.read_text(encoding="utf-8")))
        self.assertTrue(any(row.get("status") == "recorded" for row in lines[:-1]))


if __name__ == "__main__":
    unittest.main()
