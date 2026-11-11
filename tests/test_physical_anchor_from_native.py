"""Small checks for named native-XYZ bookmark creation."""
from __future__ import annotations

import contextlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from scripts import physical_anchor_from_native as bookmark
from scripts import navigation_anchors
from scripts.movement_controller import Position


class NativeAnchorTests(unittest.TestCase):
    def sample(self):
        return ({
            "positions": [Position(1.5, 8.0, 3.0), Position(2.5, 8.5, 6.0)],
            "lastSampleUtc": "2026-11-11T10:04:23.5797732+00:00",
            "identity": {"executableSha256": "A" * 64},
        }, "B" * 64)

    def test_keeps_last_candidate_and_evidence_hash(self):
        with mock.patch.object(bookmark.physical_route_preview, "_read_native",
                               return_value=self.sample()):
            catalog = bookmark.from_native_report(Path("unused.json"), "Start_Point",
                                                  "Starting point")
        anchor = catalog["anchors"][0]
        self.assertEqual(anchor["position"], {"x": 2.5, "y": 8.5, "z": 6.0})
        self.assertEqual(anchor["source"]["kind"], "native-cache-candidate")
        self.assertEqual(anchor["source"]["evidenceSha256"], "B" * 64)
        self.assertEqual(anchor["qualification"], "offline-reference-only")

    def test_invalid_anchor_is_rejected(self):
        with mock.patch.object(bookmark.physical_route_preview, "_read_native",
                               return_value=self.sample()):
            with self.assertRaises(navigation_anchors.AnchorCatalogError):
                bookmark.from_native_report(Path("unused.json"), "invalid space", "label")

    def test_cli_saves_once_and_never_overwrites(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "named-anchor.json"
            args = ["--position-report", "unused.json", "--id", "Start",
                    "--label", "Here", "--output-catalog", str(target)]
            with mock.patch.object(bookmark.physical_route_preview, "_read_native",
                                   return_value=self.sample()):
                with contextlib.redirect_stdout(StringIO()):
                    self.assertEqual(bookmark.main(args), 0)
                    self.assertEqual(bookmark.main(args), 2)
            saved = navigation_anchors.load_catalog(target)
            self.assertEqual(saved["anchors"][0]["id"], "Start")
            self.assertEqual(len(saved["anchors"]), 1)


if __name__ == "__main__":
    unittest.main()
