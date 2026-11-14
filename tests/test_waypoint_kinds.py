import unittest

from scripts.waypoint_kinds import point_kinds
from scripts.physical_waypoints import validate_route_document
from scripts.waypoints_cli import build_parser


class WaypointKindsTests(unittest.TestCase):
    def test_legacy_and_declared_types(self):
        document = {"waypoints": [["a", 1, 2], ["b", 3, 4]]}
        self.assertEqual(point_kinds(document), ["pass", "pass"])
        document["pointKinds"] = ["stop", "pass"]
        self.assertEqual(point_kinds(document), ["stop", "pass"])
        validate_route_document(document)

    def test_invalid_types_are_rejected(self):
        for kinds in (["pass"], ["pass", "STOP"], ["pass", None], "pass"):
            with self.subTest(kinds=kinds), self.assertRaises(ValueError):
                validate_route_document({"waypoints": [["a", 1, 2], ["b", 3, 4]], "pointKinds": kinds})

    def test_cli_parser_exposes_kind(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["route", "add", "--x", "1", "--z", "2", "--kind", "stop"]).kind, "stop")
        self.assertEqual(parser.parse_args(["route", "update", "1", "--kind", "pass"]).kind, "pass")


if __name__ == "__main__":
    unittest.main()
