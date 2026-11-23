"""Archive publication checks without a game or navigation process."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts import archive_waypoint_destination as archive, waypoint_destination_plan as planner
from tests.test_waypoint_navigation_candidate import sample


class ArchiveDestinationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        candidate = sample()
        patch_dir = self.root / "patches" / "fixture"
        patch_dir.mkdir(parents=True)
        geometry = self.save("geometry.obj", "geometry fixture")
        placements = self.save("placements.json", {})
        patch_path = self.save("patches/fixture/patch.json", {
            "schema": "riftworld.patch/1", "source": {"provider": "telara-fly"}, "patchId": candidate["patchId"],
            "files": {"geometry": {"path": "../../geometry.obj", "sha256": planner._hash(geometry)},
                      "placements": {"path": "../../placements.json", "sha256": planner._hash(placements)}},
        })
        (self.root / "navigation").mkdir()
        mesh = self.save("navigation/detour.bin", "mesh fixture")
        prepared = self.save("navigation/prepare.obj", "prepared geometry fixture")
        build = self.save("navigation/navigation.json", {
            "files": {"navmesh": {"path": mesh.name, "sha256": planner._hash(mesh)},
                      "preparedObj": {"path": prepared.name, "sha256": planner._hash(prepared)}},
        })
        self.context = self.save("zone.json", {})
        native = self.save("retained.jsonl", {})
        self.route = {"waypoints": [["Start", 1, 2], ["Stop", 3, 4]], "heights": [5, 6],
                      "pointKinds": ["pass", "stop"], "routeContext": {}, "candidateAdoption": {
                          "candidateId": candidate["candidateId"], "direction": "forward",
                          "owner": {"machine": "SOURCE-HOST", "unitKey": "42"},
                          "nativeIndices": [0, 1], "candidateIndices": [0, 1],
                          "zoneContextSha256": planner._hash(self.context).lower(),
                          "sourceReceipts": [planner._reference(native)],
                      }}
        self.route["candidateAdoption"]["integritySha256"] = archive._adoption_digest(self.route)
        self.plan = self.save("plan.json", {
            "schema": planner.SCHEMA, "status": "adoptable", "destinationCovered": True,
            "inputSent": False, "currentRouteChanged": False, "destinationId": "fixture-end",
            "requestedStartXYZ": [1, 5, 2], "candidate": planner._reference(self.save("candidate.json", candidate)),
            "adoptedRoute": planner._reference(self.save("route.json", self.route)),
            "nativeContext": planner._reference(self.context), "inputs": {
                "patch": planner._reference(patch_path), "build": planner._reference(build),
                "catalog": planner._reference(self.save("catalog.json", {})),
            },
        })
        self.output = self.root / "published archive"

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_export_publishes_only_after_verification(self):
        def verify(handoff_path, output_directory):
            self.assertFalse(self.output.exists())
            handoff = json.loads(handoff_path.read_bytes())
            with ZipFile(handoff_path.parent / handoff["archive"]) as files:
                recipe = json.loads(files.read("replay.json"))
                self.assertIn("patch/geometry.obj", files.namelist())
                self.assertEqual(recipe["nativeReceipts"], ["evidence/receipt-0.jsonl"])
                self.assertTrue(recipe["expected"]["routeGeometrySha256"])
            return {"ownerHost": "LOCAL-HOST", "verifiedResult": recipe["expected"]}

        with patch.object(archive, "replay_destination_archive", side_effect=verify):
            result = archive.export_archive(self.plan, self.output)
        self.assertEqual(result["status"], "exported")
        self.assertEqual(result["archiveSha256"], planner._hash(self.output / "waypoints-destination.zip"))
        self.assertEqual(result["verifiedResult"]["stops"], 1)

    def test_failed_verification_does_not_publish_and_context_edits_are_rejected(self):
        with patch.object(archive, "replay_destination_archive", side_effect=ValueError("verification failed")) as replay:
            with self.assertRaisesRegex(ValueError, "verification failed"):
                archive.export_archive(self.plan, self.output)
            self.assertFalse(self.output.exists())
            self.context.write_text("{ }", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source-hash-mismatch"):
                archive.export_archive(self.plan, self.output)
        self.assertFalse(self.output.exists())
        replay.assert_called_once()
