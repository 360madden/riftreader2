import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import export_continuous_route as export
from scripts.waypoint_measurements import parse_projection_route


SHA = "a" * 64
PLAYER = "239816685251645959"


def native(points, *, status="arrived", release=True):
    return {"status": status, "inputSent": True, "releaseSucceeded": release,
            "desktopInputsDown": [], "playerKey": PLAYER,
            "target": {"machineName": "AMD-DESKTOP", "processId": 21672,
                       "processStartUtcTicks": 639302305454629980,
                       "executableSha256": SHA}, "path": points}


def point(x, z, second, *, y=863.0, bearing=0.0):
    return {"x": x, "y": y, "z": z, "bearing": bearing,
            "distance": 1, "observedAtUtc": f"2026-11-14T12:00:{second:02d}Z"}


class ExportContinuousRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.zone = self.root / "zone.json"
        self.zone.write_text(json.dumps({"ok": True, "data": {"context": {
            "version": 1, "zoneIdCandidate": "z1234567800000001",
            "rawZoneKey": 0x12345678, "source": "zone-native.json",
            "observedAtUtc": "2026-11-14T11:59:59Z", "playerKey": PLAYER,
            "target": {"hostName": "AMD-DESKTOP", "processId": 21672,
                       "processStartUtcTicks": 639302305454629980,
                       "executableSha256": SHA}}}}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_forward_reverse_keeps_only_actual_timed_samples(self):
        forward = self.save("forward.json", {"nativeReceipt": native([
            point(0, 0, 0), point(0, 0.25, 1), point(0, 0.75, 2), point(0, 1, 3)])})
        reverse = self.save("reverse.json", native([
            point(0, 1, 4, bearing=180), point(0, 0.5, 5, bearing=180),
            point(0, 0, 6, bearing=180)]))
        document = export.export_route([forward, reverse], self.zone, spacing=.5)
        parsed = parse_projection_route(document)
        self.assertEqual("independent-point-observations", parsed["provenanceKind"])
        self.assertEqual([0, .75, 1, .5, 0], [row[2] for row in document["waypoints"]])
        self.assertEqual(["2026-11-14T12:00:00Z", "2026-11-14T12:00:02Z",
                          "2026-11-14T12:00:03Z", "2026-11-14T12:00:05Z",
                          "2026-11-14T12:00:06Z"],
                         [row["observedAtUtc"] for row in document["pointMeasurements"]])
        self.assertTrue(all(row["kind"] == "native-player-position"
                            for row in document["pointMeasurements"]))
        self.assertEqual("z1234567800000001".upper().replace("Z", "z", 1),
                         document["routeContext"]["zoneIdCandidate"])

    def test_jsonl_survival_interrupt_and_return_export_three_endpoints(self):
        interrupted = native([point(0, 0, 0), point(0, .5, 1), point(0, 1, 2)],
                             status="halted")
        interrupted.update(reason="survival-combat", survivalInterrupt=True)
        forward = self.root / "forward.jsonl"
        forward.write_text(json.dumps({"status": "progress"}) + "\n"
                           + json.dumps(interrupted) + "\n", encoding="utf-8")
        reverse = self.save("reverse.json", native([
            point(0, 1, 3, bearing=180), point(0, .5, 4, bearing=180),
            point(0, 0, 5, bearing=180)]))
        document = export.export_route(
            [forward, reverse], self.zone, endpoints_only=True)
        self.assertEqual([["Observed 1", 0, 0], ["Observed 2", 0, 1],
                          ["Observed 3", 0, 0]], document["waypoints"])
        self.assertEqual(["2026-11-14T12:00:00Z", "2026-11-14T12:00:02Z",
                          "2026-11-14T12:00:05Z"],
                         [row["observedAtUtc"] for row in document["pointMeasurements"]])

    def test_rejects_unreleased_or_nonarrival_receipt(self):
        for value in (native([point(0, 0, 0), point(0, 1, 1)], release=False),
                      native([point(0, 0, 0), point(0, 1, 1)], status="stopped"),
                      native([point(0, 0, 0), point(0, 1, 1)], status="halted")):
            path = self.save("bad.json", value)
            with self.subTest(status=value["status"]), self.assertRaises(export.ExportError):
                export.export_route([path], self.zone)

    def test_rejects_stale_or_wrong_identity_zone_context(self):
        receipt = self.save("move.json", native([point(0, 0, 0), point(0, 1, 1)]))
        zone = json.loads(self.zone.read_text(encoding="utf-8"))
        zone["data"]["context"]["playerKey"] = "42"
        self.zone.write_text(json.dumps(zone), encoding="utf-8")
        with self.assertRaisesRegex(export.ExportError, "identity-mismatch"):
            export.export_route([receipt], self.zone)

    def test_cli_writes_valid_route_and_refuses_overwrite(self):
        receipt = self.save("move.json", native([point(0, 0, 0), point(0, 1, 1)]))
        output = self.root / "route.json"
        args = ["--receipt", str(receipt), "--zone-context", str(self.zone),
                "--output", str(output)]
        self.assertEqual(0, export.main(args))
        self.assertTrue(output.is_file())
        self.assertEqual(2, export.main(args))

    def test_direct_script_help_bootstraps_repository_imports(self):
        script = Path(export.__file__).resolve()
        completed = subprocess.run(
            [sys.executable, str(script), "--help"], cwd=self.root,
            capture_output=True, text=True, timeout=10)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("--receipt", completed.stdout)
        self.assertNotIn("ModuleNotFoundError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
