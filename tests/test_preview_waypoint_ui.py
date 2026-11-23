"""Exercise the offline gallery against the current withdrawn Waypoints window."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Windows Waypoints gallery")
class WaypointGalleryTests(unittest.TestCase):
    def test_replays_on_another_hostname_without_registering_a_live_helper(self):
        program = """
import sys
from unittest.mock import patch
from scripts import preview_waypoint_ui, waypoint_cli_protocol

default_root = waypoint_cli_protocol._root

def isolated_root(helper, root):
    assert root is not None, 'The fixture must never register as a live helper'
    return default_root(helper, root)

with patch.object(preview_waypoint_ui.socket, 'gethostname', return_value='RIFT-STATION'), \\
     patch.object(waypoint_cli_protocol, '_root', side_effect=isolated_root):
    raise SystemExit(preview_waypoint_ui.main(['--output', sys.argv[1]]))
"""
        with TemporaryDirectory(prefix="rr2-gallery-test-") as temp:
            output = Path(temp)
            result = subprocess.run([sys.executable, "-B", "-c", program, str(output)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            fixture = json.loads((ROOT / "docs/validation/gui-taught-route-2026-11-12.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(manifest["host"], "RIFT-STATION")
            self.assertEqual(manifest["fixtureHost"], fixture["recording"]["identity"]["runtimeIdentity"]["machine"])
            self.assertFalse(manifest["mapped"])
            self.assertEqual(manifest["callbackErrors"], [])
            self.assertIn("Activity", {preview["tab"] for preview in manifest["previews"]})
            for preview in manifest["previews"]:
                svg = output / preview["file"]
                self.assertIn("RIFT-STATION / OFFLINE FIXTURE", svg.read_text(encoding="utf-8"))
                self.assertTrue(svg.with_suffix(".json").is_file())
