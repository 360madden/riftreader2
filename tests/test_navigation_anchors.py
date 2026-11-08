"""Offline regression tests for the persistent, nonauthorizing XYZ anchor catalog."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts import navigation_anchors as anchors
from scripts.movement_controller import Position, planar_distance


def fixture():
    return {
        "schemaVersion": 1,
        "coordinateFrame": anchors.COORDINATE_FRAME,
        "anchors": [{
            "id": "Pier_North",
            "label": "  North pier  ",
            "position": {"x": 7183.560546875, "y": 820.7896118164062,
                         "z": 3156.038330078125},
            "zoneLabel": "  test zone  ",
            "source": {
                "kind": "native-cache-candidate",
                "gameBuildSha256": "a" * 64,
                "evidenceSha256": "b" * 64,
                "capturedAtUtc": "2026-11-08T13:00:00Z"
            },
            "qualification": "offline-reference-only"
        }]
    }


class NavigationAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalog.json"

    def save(self, value):
        self.path.write_text(json.dumps(value, allow_nan=True), encoding="utf-8")
        return self.path

    def test_exact_coordinates_and_hashes_survive_validation(self):
        valid = anchors.validate_catalog(fixture())
        point = valid["anchors"][0]["position"]
        self.assertEqual(point["x"], 7183.560546875)
        self.assertEqual(point["y"], 820.7896118164062)
        self.assertEqual(point["z"], 3156.038330078125)
        self.assertEqual(valid["anchors"][0]["label"], "North pier")
        self.assertEqual(valid["anchors"][0]["zoneLabel"], "test zone")
        self.assertEqual(valid["anchors"][0]["source"]["gameBuildSha256"], "A" * 64)
        self.assertEqual(valid["anchors"][0]["source"]["evidenceSha256"], "B" * 64)
        self.assertEqual(valid["anchors"][0]["source"]["capturedAtUtc"],
                         "2026-11-08T13:00:00+00:00")

    def test_resolved_goal_is_xz_planar_but_never_authorizes_input(self):
        catalog = anchors.load_catalog(self.save(fixture()))
        result = anchors.resolve_anchor(catalog, "pier_NORTH")
        self.assertEqual(result["status"], "offline-reference-only")
        self.assertIs(result["movementEligible"], False)
        self.assertIs(result["zoneLabelIsMetadataOnly"], True)
        self.assertEqual(result["anchor"]["id"], "Pier_North")
        self.assertEqual(result["planarGoal"],
                         {"x": 7183.560546875, "z": 3156.038330078125})
        self.assertNotIn("readerNonce", result)

    def test_casefold_duplicates_and_unstable_ids_are_blocked(self):
        catalog = fixture()
        second = deepcopy(catalog["anchors"][0])
        second["id"] = "pier_north"
        catalog["anchors"].append(second)
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "duplicate anchor id"):
            anchors.validate_catalog(catalog)
        for invalid in ("", "123", "anchor name", "a" * 65, None):
            with self.subTest(invalid=invalid):
                catalog = fixture()
                catalog["anchors"][0]["id"] = invalid
                with self.assertRaisesRegex(anchors.AnchorCatalogError, "anchor id"):
                    anchors.validate_catalog(catalog)

    def test_missing_extra_and_malformed_fields_fail_closed(self):
        for edit in ("missing-x", "extra-world", "extra-active-flag", "extra-top"):
            with self.subTest(edit=edit):
                catalog = fixture()
                if edit == "missing-x":
                    del catalog["anchors"][0]["position"]["x"]
                elif edit == "extra-world":
                    catalog["anchors"][0]["worldInstanceId"] = "not-qualified"
                elif edit == "extra-active-flag":
                    catalog["anchors"][0]["navigationEligible"] = True
                else:
                    catalog["currentSession"] = "pinned"
                with self.assertRaisesRegex(anchors.AnchorCatalogError, "fields are invalid"):
                    anchors.validate_catalog(catalog)

    def test_nonfinite_boolean_and_missing_xyz_are_rejected(self):
        for invalid in (True, None, "2", float("nan"), float("inf"),
                        -float("inf"), 10 ** 1000):
            with self.subTest(value=str(invalid)[:40]):
                catalog = fixture()
                catalog["anchors"][0]["position"]["x"] = invalid
                with self.assertRaises(anchors.AnchorCatalogError):
                    anchors.validate_catalog(catalog)

    def test_wrong_frame_or_schema_cannot_be_resolved(self):
        for field, value in (("schemaVersion", True), ("schemaVersion", 2),
                             ("coordinateFrame", "longitude-latitude"),
                             ("coordinateFrame", None)):
            catalog = fixture()
            catalog[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(anchors.AnchorCatalogError):
                    anchors.validate_catalog(catalog)

    def test_provenance_requires_exact_digests_utc_and_known_source_kind(self):
        for field, value in (("gameBuildSha256", "not-a-sha"),
                             ("evidenceSha256", "z" * 64),
                             ("capturedAtUtc", "2026-11-08T08:00:00-05:00"),
                             ("capturedAtUtc", "2026-11-08"),
                             ("kind", "native-verified-live"),
                             ("kind", [])):
            catalog = fixture()
            catalog["anchors"][0]["source"][field] = value
            with self.subTest(field=field, value=str(value)[:30]):
                with self.assertRaises(anchors.AnchorCatalogError):
                    anchors.validate_catalog(catalog)

    def test_native_candidate_cannot_claim_movement_ready_status(self):
        catalog = fixture()
        for claimed in ("verified-fresh", "native-live", True):
            catalog["anchors"][0]["qualification"] = claimed
            with self.subTest(claimed=claimed):
                with self.assertRaisesRegex(anchors.AnchorCatalogError, "cannot authorize"):
                    anchors.validate_catalog(catalog)
        catalog["anchors"][0]["qualification"] = "offline-reference-only"
        catalog["anchors"][0]["zoneLabel"] = None
        self.assertIsNone(anchors.validate_catalog(catalog)["anchors"][0]["zoneLabel"])

    def test_order_independent_lookup_and_unknown_id(self):
        catalog = fixture()
        other = deepcopy(catalog["anchors"][0])
        other.update(id="SouthPier", label="South pier",
                     position={"x": -1, "y": 0, "z": 200})
        catalog["anchors"] = [other, catalog["anchors"][0]]
        self.assertEqual(anchors.resolve_anchor(catalog, "PIER_NORTH")["anchor"]["id"],
                         "Pier_North")
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "anchor not found"):
            anchors.resolve_anchor(catalog, "unknown")

    def test_planar_distance_uses_existing_xz_convention(self):
        point = anchors.resolve_anchor(fixture(), "Pier_North")["anchor"]["position"]
        before = Position(point["x"], point["y"] + 100, point["z"])
        after = Position(point["x"] + 3, point["y"] - 100, point["z"] + 4)
        self.assertEqual(planar_distance(before, after), 5.0)

    def test_json_rejects_duplicate_fields_and_nonfinite_constants(self):
        self.path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "duplicate JSON field"):
            anchors.load_catalog(self.path)
        catalog = fixture()
        catalog["anchors"][0]["position"]["z"] = math.inf
        self.save(catalog)
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "nonfinite JSON"):
            anchors.load_catalog(self.path)

    def test_empty_catalog_is_valid_and_oversize_is_not(self):
        empty = fixture()
        empty["anchors"] = []
        self.assertEqual(anchors.load_catalog(self.save(empty))["anchors"], [])
        self.path.write_text("x" * (anchors.MAX_CATALOG_BYTES + 1), encoding="utf-8")
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "oversized"):
            anchors.load_catalog(self.path)

    def test_cli_lists_resolves_and_reports_invalid_without_input(self):
        self.save(fixture())
        listed = io.StringIO()
        with redirect_stdout(listed):
            self.assertEqual(anchors.main(["--catalog", str(self.path)]), 0)
        listing = json.loads(listed.getvalue())
        self.assertIs(listing["movementEligible"], False)
        self.assertEqual(listing["anchors"][0]["id"], "Pier_North")
        resolved = io.StringIO()
        with redirect_stdout(resolved):
            self.assertEqual(anchors.main(["--catalog", str(self.path),
                                           "--anchor-id", "PIER_NORTH"]), 0)
        self.assertEqual(json.loads(resolved.getvalue())["planarGoal"]["x"],
                         7183.560546875)
        blocked = io.StringIO()
        with redirect_stdout(blocked):
            self.assertEqual(anchors.main(["--catalog", str(self.path),
                                           "--anchor-id", "missing"]), 2)
        self.assertEqual(json.loads(blocked.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
