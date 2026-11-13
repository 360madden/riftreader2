import json
from pathlib import Path
import tempfile
import unittest

from scripts import waypoint_route_library as library
from scripts.waypoint_measurements import measurement


class RouteLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "library"
        self.route = {"waypoints": [["A", 1, 2], ["B", 3, 4]], "heights": [5, None]}
        self.ctx = {"version": 1, "zoneIdCandidate": "z00000001abcdef00", "rawZoneKey": 1,
                    "source": "native observation", "observedAtUtc": "2026-01-01T00:00:00Z",
                    "target": {"hostName": "AMD-DESKTOP", "executableSha256": "a" * 64,
                               "processId": 100, "processStartUtcTicks": "123", "hwnd": "9",
                               "executablePath": "C:/game/rift.exe"}}

    def test_context_comparison_is_scoped_and_candidate_only(self):
        other = json.loads(json.dumps(self.ctx))
        other["target"]["processId"] = 101
        self.assertEqual("matching", library.compare_context(self.ctx, other))
        other["zoneIdCandidate"] = "z00000002ABCDEF00"
        other["rawZoneKey"] = 2
        self.assertEqual("mismatch", library.compare_context(self.ctx, other))
        other["target"]["hostName"] = "another-host"
        self.assertEqual("unknown", library.compare_context(self.ctx, other))
        self.assertEqual("unknown", library.compare_context(None, self.ctx))
        self.assertEqual("unknown", library.compare_context({**self.ctx, "worldId": "observed-world"}, self.ctx))
        with self.assertRaises(ValueError):
            library.normalize_context({**self.ctx, "rawZoneKey": 3})
        with self.assertRaises(ValueError):
            library.normalize_context({"version": 1, "zoneIdCandidate": "z00000001ABCDEF00"})

    def test_save_list_import_and_overwrite(self):
        route = dict(self.route, routeContext=self.ctx)
        route_id = library.save_route(route, "Test route", "test", library_dir=self.directory)
        self.assertEqual(route_id, "test")
        self.assertNotIn("routeName", route)
        entry = library.list_routes(self.ctx, library_dir=self.directory)[0]
        self.assertEqual((entry["name"], entry["waypointCount"], entry["estimatedHeightCount"], entry["contextStatus"]),
                         ("Test route", 2, 2, "matching"))
        with self.assertRaises(FileExistsError):
            library.save_route(route, "Other", "test", library_dir=self.directory)
        self.assertEqual(library.load_route("test", self.directory)["routeName"], "Test route")
        source = Path(self.temp.name) / "legacy.json"
        original = json.dumps(self.route)
        source.write_text(original, encoding="utf-8")
        library.import_route(source, route_id="legacy", library_dir=self.directory)
        self.assertEqual(source.read_text(encoding="utf-8"), original)
        self.assertEqual([r["id"] for r in library.list_routes(self.ctx, "unknown", library_dir=self.directory)], ["legacy"])
        library.save_route(route, "Updated", "test", overwrite=True, library_dir=self.directory)
        self.assertEqual(library.load_route("test", self.directory)["routeName"], "Updated")
        with self.assertRaises(ValueError):
            library.load_route("../test", self.directory)

    def test_measured_counts_require_receipts(self):
        identity = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "1"}
        self.route["pointMeasurements"] = [measurement({"x": 1, "y": 5, "z": 2}, identity,
                                                       "sample", "2026-01-01T00:00:00Z"), None]
        library.save_route(self.route, "Measured", library_dir=self.directory)
        row = library.list_routes(library_dir=self.directory)[0]
        self.assertEqual((row["measuredHeightCount"], row["estimatedHeightCount"]), (1, 1))

    def test_corrupt_receipts_and_oversized_entries_are_reported(self):
        corrupt = dict(self.route, pointMeasurements=[{"kind": "forged"}, None])
        with self.assertRaisesRegex(ValueError, "invalid-route-measurement"):
            library.save_route(corrupt, "Bad", library_dir=self.directory)
        self.directory.mkdir()
        (self.directory / "bad.json").write_text(json.dumps(corrupt), encoding="utf-8")
        (self.directory / "large.json").write_bytes(b" " * (library.MAX_ENTRY_BYTES + 1))
        entries = {row["id"]: row for row in library.list_routes(library_dir=self.directory)}
        self.assertIn("invalid-route-measurement", entries["bad"]["error"])
        with self.assertRaisesRegex(ValueError,"invalid-route-name"):
            library.save_route(dict(self.route,routeName={"unexpected":"object"}),"Bad name",library_dir=self.directory)
        self.assertIn("route-entry-too-large", entries["large"]["error"])
        with self.assertRaisesRegex(ValueError, "route-entry-too-large"):
            library.load_route("large", self.directory)

    def test_entry_limit_is_explicit(self):
        self.directory.mkdir()
        for i in range(library.MAX_ENTRIES + 1):
            (self.directory / f"{i}.json").touch()
        with self.assertRaisesRegex(ValueError, "library-entry-limit-exceeded"):
            library.list_routes(library_dir=self.directory)


if __name__ == "__main__":
    unittest.main()
