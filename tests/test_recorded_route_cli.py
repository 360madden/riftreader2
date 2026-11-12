"""CLI routing tests without game access or input."""
from contextlib import nullcontext, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import physical_waypoints as cli
from scripts import waypoint_playback


class RecordedRouteCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "artifacts").mkdir()
        self.args = ["--expected-host", "AMD-DESKTOP", "--physical-pid", "123", "--execute"]

    def test_existing_record_destination_refused_before_adapter_or_input(self):
        path = self.root / "existing.json"
        path.write_text("original", encoding="utf-8")
        with patch.object(cli, "PhysicalAdapter") as adapter, redirect_stdout(StringIO()):
            code = cli.main(self.args + ["--go", "1", "2", "--record-to", str(path)])
        self.assertEqual(code, 2)
        adapter.assert_not_called()
        self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_reverse_resume_progress_passed_to_playback_helper(self):
        route = self.root / "route.json"
        document = {"waypoints": [["Start", 0, 0], ["End", 1, 0]]}
        route.write_text(json.dumps(document), encoding="utf-8")
        checkpoint = self.root / "checkpoint.json"
        leg = {"position": {"x": 0, "y": 0, "z": 0}, "bearing": 0,
               "distance": 0, "pulses": 1, "totalHoldMs": 100}
        with patch.object(cli, "ROOT", self.root), patch.object(cli, "PhysicalAdapter") as adapter, \
             patch.object(cli, "cli_stop_controls", return_value=nullcontext()), \
             patch.object(waypoint_playback, "play_route", return_value=([leg], None)) as play, \
             redirect_stdout(StringIO()):
            adapter.return_value.binding = {"runtimeIdentity": {}}
            code = cli.main(self.args + ["--play-route", str(route), "--reverse", "--resume",
                                         "--progress", str(checkpoint), "--face-waypoints"])
        self.assertEqual(code, 0)
        self.assertEqual(play.call_args.args[1], document)
        self.assertIs(play.call_args.kwargs["runner"], cli.run_route)
        self.assertEqual(play.call_args.kwargs["checkpoint"], checkpoint)
        self.assertEqual(play.call_args.kwargs["direction"], "reverse")
        self.assertIs(play.call_args.kwargs["resume"], True)
        self.assertIs(play.call_args.kwargs["face_waypoints"], True)


if __name__ == "__main__": unittest.main()
