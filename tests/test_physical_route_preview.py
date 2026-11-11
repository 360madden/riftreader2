"""Offline physical native-position -> named anchor preview acceptance and rejection."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from scripts import navigation_anchors as anchors
from scripts import physical_route_preview as preview


BUILD = "A" * 64
UNIT = "239816685251645959"


def native():
    return {
        "schemaVersion": 1,
        "contractVersion": "native-current-position-candidate-samples/1",
        "qualification": "candidate-only-not-passive-fresh-or-player-semantic-qualified",
        "status": "complete",
        "sourceBuildSha256": BUILD,
        "identity": {
            "processId": 44888,
            "processStartUtcTicks": 639299470183328173,
            "executablePath": "C:\\Program Files (x86)\\Glyph\\Games\\RIFT\\Live\\rift_x64.exe",
            "executableSha256": BUILD,
        },
        "requestedSamples": 2,
        "completedSamples": 2,
        "observations": [
            {
                "index": 1, "unitKey": UNIT, "ownerIdentityStatus": "player-component-chain-anchored",
                "startedAtUtc": "2026-11-11T07:06:42.0000000+00:00",
                "completedAtUtc": "2026-11-11T07:06:42.1000000+00:00",
                "x": 0, "y": 5, "z": 0,
            },
            {
                "index": 2, "unitKey": UNIT, "ownerIdentityStatus": "player-component-chain-anchored",
                "startedAtUtc": "2026-11-11T07:06:42.2000000+00:00",
                "completedAtUtc": "2026-11-11T07:06:42.3000000+00:00",
                "x": 3, "y": -500, "z": 4,
            },
        ],
    }


def catalog():
    return {
        "schemaVersion": 1,
        "coordinateFrame": anchors.COORDINATE_FRAME,
        "anchors": [{
            "id": "North_Gate",
            "label": "North gate",
            "position": {"x": 6, "y": 9000, "z": 8},
            "zoneLabel": "unverified reference",
            "source": {
                "kind": "native-cache-candidate",
                "gameBuildSha256": BUILD,
                "evidenceSha256": "B" * 64,
                "capturedAtUtc": "2026-11-08T13:00:00Z",
            },
            "qualification": "offline-reference-only",
        }],
    }


class PhysicalRoutePreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.report = self.root / "native.json"
        self.anchors = self.root / "anchors.json"
        self.store()

    def store(self, raw=None, saved=None):
        self.report.write_text(json.dumps(native() if raw is None else raw, allow_nan=True),
                               encoding="utf-8")
        self.anchors.write_text(json.dumps(catalog() if saved is None else saved),
                                encoding="utf-8")

    def test_complete_candidate_report_to_named_anchor_progress(self):
        result = preview.preview(self.report, self.anchors, "north_gate")
        self.assertEqual(result["anchorId"], "North_Gate")
        self.assertEqual(result["planarDistanceStartCandidate"], 10.0)
        self.assertEqual(result["planarDistanceEndCandidate"], 5.0)
        self.assertEqual(result["planarProgressTowardAnchorCandidate"], 5.0)
        self.assertEqual(result["planarNetDisplacementCandidate"], 5.0)
        self.assertEqual(result["planarObservedPathLengthCandidate"], 5.0)
        self.assertEqual(result["sampleCount"], 2)
        self.assertEqual(result["unitKey"], UNIT)
        self.assertEqual(result["status"], "offline-candidate-preview")
        self.assertIs(result["movementEligible"], False)
        self.assertIs(result["arrivalQualified"], False)
        self.assertIs(result["worldInstanceMatched"], False)
        self.assertEqual(result["candidateCurrentXYZ"], {"x": 3.0, "y": -500.0, "z": 4.0})
        self.assertRegex(result["nativeReportSha256"], r"^[A-F0-9]{64}$")

    def test_progress_sign_and_out_and_back_path(self):
        value = native()
        last = deepcopy(value["observations"][1])
        last.update(index=3, startedAtUtc="2026-11-11T07:06:42.400Z",
                    completedAtUtc="2026-11-11T07:06:42.500Z", x=0, y=5, z=0)
        value["observations"].append(last)
        value["requestedSamples"] = 3
        value["completedSamples"] = 3
        self.store(raw=value)
        result = preview.preview(self.report, self.anchors, "North_Gate")
        self.assertEqual(result["planarProgressTowardAnchorCandidate"], 0.0)
        self.assertEqual(result["planarNetDisplacementCandidate"], 0.0)
        self.assertEqual(result["planarObservedPathLengthCandidate"], 10.0)

    def test_finite_xyz_cannot_produce_nonfinite_derived_metrics(self):
        saved = catalog()
        saved["anchors"][0]["position"].update(x=0, z=0)
        huge_pair = native()
        huge_pair["observations"][0].update(x=-1e308, z=0)
        huge_pair["observations"][1].update(x=1e308, z=0)
        self.store(raw=huge_pair, saved=saved)
        with self.assertRaisesRegex(preview.RoutePreviewError, "derived planar metric is nonfinite"):
            preview.preview(self.report, self.anchors, "North_Gate")

        # Each segment is finite; their accumulated path still overflows.
        long_path = native()
        rows = []
        for index, x in enumerate((0.0, 1e308, 0.0, 1e308)):
            row = deepcopy(long_path["observations"][0])
            row.update(index=index + 1, x=x, y=0, z=0,
                       startedAtUtc=f"2026-11-11T07:06:42.{index * 100:03d}Z",
                       completedAtUtc=f"2026-11-11T07:06:42.{index * 100 + 50:03d}Z")
            rows.append(row)
        long_path.update(observations=rows, requestedSamples=4, completedSamples=4)
        self.store(raw=long_path, saved=saved)
        with self.assertRaisesRegex(preview.RoutePreviewError, "derived planar metric is nonfinite"):
            preview.preview(self.report, self.anchors, "North_Gate")

    def test_wrong_build_and_bad_anchor_never_claim_route(self):
        saved = catalog()
        saved["anchors"][0]["source"]["gameBuildSha256"] = "C" * 64
        self.store(saved=saved)
        with self.assertRaisesRegex(preview.RoutePreviewError, "different game builds"):
            preview.preview(self.report, self.anchors, "North_Gate")
        self.store()
        with self.assertRaises(anchors.AnchorCatalogError):
            preview.preview(self.report, self.anchors, "unknown")

    def test_invalid_native_report_rejected(self):
        changes = {
            "wrong_contract": lambda r: r.update(contractVersion="native-legacy/1"),
            "missing_rows": lambda r: r["observations"].pop(),
            "wrong_complete": lambda r: r.update(status="partial"),
            "process_changed": lambda r: r["identity"].update(executableSha256="C" * 64),
            "unit_changed": lambda r: r["observations"][1].update(unitKey="123"),
            "unanchored": lambda r: r["observations"][1].update(ownerIdentityStatus="guess"),
            "bad_index": lambda r: r["observations"][1].update(index=1),
            "overlap": lambda r: r["observations"][1].update(startedAtUtc="2026-11-11T07:06:42.090Z"),
            "non_utc": lambda r: r["observations"][1].update(startedAtUtc="2026-11-11T02:06:42-05:00"),
            "nan": lambda r: r["observations"][1].update(z=float("nan")),
            "boolean": lambda r: r["observations"][1].update(x=True),
            "huge_integer": lambda r: r["observations"][1].update(x=10**1000),
            "wrong_reader": lambda r: r["identity"].update(executablePath="C:\\notrift.exe"),
        }
        for name, edit in changes.items():
            with self.subTest(name=name):
                value = native()
                edit(value)
                self.store(raw=value)
                with self.assertRaises(preview.RoutePreviewError):
                    preview.preview(self.report, self.anchors, "North_Gate")

    def test_duplicate_json_key_rejected(self):
        self.report.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
        with self.assertRaises(preview.RoutePreviewError):
            preview.preview(self.report, self.anchors, "North_Gate")

    def test_cli_success_and_blocked_no_traceback(self):
        args = ["--position-report", str(self.report),
                "--catalog", str(self.anchors), "--anchor-id", "North_Gate"]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(preview.main(args), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "offline-candidate-preview")
        self.store(raw={"status": "not-our-format"})
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(preview.main(args), 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
