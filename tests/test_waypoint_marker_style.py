"""Display preferences are persistent and tolerate interrupted/bad local writes."""
from pathlib import Path
import tempfile
import unittest

from scripts.waypoint_marker_style import DEFAULT_STYLE, load_style, normalize_style, save_style


class MarkerStyleTests(unittest.TestCase):
    def test_saved_preferences_round_trip_and_missing_defaults_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appearance.json"
            self.assertEqual(load_style(path), DEFAULT_STYLE)
            wanted = dict(DEFAULT_STYLE, beaconScale=1.5, opacity=.45, labelsVisible=False)
            save_style(path, wanted)
            self.assertEqual(load_style(path), wanted)
            loaded = load_style(path)
            loaded["opacity"] = 0
            self.assertEqual(load_style(path), wanted)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_bad_file_keeps_last_good_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appearance.json"
            previous = dict(DEFAULT_STYLE, opacity=.4)
            for bad in (b"{", b"[]", b"\xff", b" " * 5000,
                        b'{"schemaVersion":1,"beaconScale":1,"opacity":0,"labelsVisible":true}'):
                with self.subTest(bad=bad[:40]):
                    path.write_bytes(bad)
                    self.assertEqual(load_style(path, fallback=previous), previous)

    def test_invalid_preferences_cannot_replace_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appearance.json"
            save_style(path, DEFAULT_STYLE)
            original = path.read_bytes()
            for key, value in (("beaconScale", True), ("beaconScale", float("nan")),
                               ("beaconScale", 3), ("opacity", .1), ("opacity", float("inf")),
                               ("labelsVisible", 1), ("schemaVersion", True), ("schemaVersion", 2)):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    save_style(path, dict(DEFAULT_STYLE, **{key: value}))
                self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError):
                normalize_style({**DEFAULT_STYLE, "unknown": 1})


if __name__ == "__main__":
    unittest.main()
