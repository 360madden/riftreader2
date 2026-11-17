"""Offline boundary: screenshot-ray candidates remain advisory even if wrapped as routes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import physical_pixel_composite as composite
from scripts.physical_waypoints import external_candidate_payload, validate_route_document
from scripts.waypoint_candidate_adoption import reject_review_route


REFUSAL = "pixel-composite-candidate-requires-independent-route-evidence"


def advisory_report():
    return {
        "schema": composite.SCHEMA, "status": "candidate-only",
        "pixels": [{"pixel": [850, 530],
                    "surfaceCandidates": {"candidateFirst": {
                        "candidateXYZ": [7218.0, 873.0, 3026.0],
                        "movementEligible": False}}}],
        "inputSent": False, "movementEligible": False,
        "physicalBlockingQualified": False, "navigationQualified": False,
        "visibleSurfaceQualified": False,
    }


def wrapped_as_route(report):
    result = deepcopy(report)
    candidate = result["pixels"][0]["surfaceCandidates"]["candidateFirst"]["candidateXYZ"]
    result["waypoints"] = [["Unqualified pixel ray", candidate[0], candidate[2]]]
    result["heights"] = [candidate[1]]
    return result


class PixelCandidateRouteBoundaryTests(unittest.TestCase):
    def test_genuine_composite_payload_has_no_executable_route(self):
        report = advisory_report()
        self.assertNotIn("waypoints", report)
        with self.assertRaises((KeyError, ValueError, TypeError)):
            validate_route_document(report)

    def test_hybrid_composite_schema_and_waypoints_fail_closed(self):
        malformed = wrapped_as_route(advisory_report())
        with self.assertRaisesRegex(ValueError, REFUSAL):
            reject_review_route(malformed)
        with self.assertRaisesRegex(ValueError, REFUSAL):
            validate_route_document(malformed)

    def test_external_route_candidate_cannot_relabel_pixel_hit(self):
        malformed = wrapped_as_route(advisory_report())
        with TemporaryDirectory() as folder:
            route = Path(folder) / "pixel-as-route.json"
            route.write_text(json.dumps(malformed), encoding="utf-8")
            digest = hashlib.sha256(route.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, REFUSAL):
                external_candidate_payload(route, digest)

    def test_ordinary_explicit_waypoints_still_validate(self):
        route = {"waypoints": [["Ordinary manual waypoint", 5.0, 12.0]],
                 "heights": [3.0]}
        self.assertIs(validate_route_document(route), route)
        reject_review_route(route)


class PinnedPixelCandidateBoundaryTests(unittest.TestCase):
    def test_real_retained_composite_with_added_waypoints_still_refuses(self):
        # Reuse the historical SHA-pinned fixture without duplicating its test class.
        import tests.test_physical_pixel_composite as archived
        fixture = archived.RetainedSanctumWatchTests
        fixture.setUpClass()  # Skips when exact historical files are unavailable.
        frame = composite.load_frame(
            fixture.image, fixture.receipt, fixture.receipt_sha,
            fixture.native_before, fixture.before_sha,
            fixture.native, fixture.native_sha, expected_host="AMD-DESKTOP")
        layers = [composite.load_terrain(fixture.terrain, fixture.terrain_reg),
                  composite.load_temple(fixture.temple, fixture.anchor,
                                        fixture.anchor_sha, frame["identity"])]
        actual_report = composite.analyze_pixels(frame, layers, [(850, 530)],
                                                max_distance=200)
        self.assertEqual(actual_report["status"], "candidate-only")
        self.assertFalse(actual_report["movementEligible"])
        wrapped = wrapped_as_route(actual_report)
        with self.assertRaisesRegex(ValueError, REFUSAL):
            validate_route_document(wrapped)


if __name__ == "__main__":
    unittest.main()
