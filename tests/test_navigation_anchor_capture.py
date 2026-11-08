"""Offline-only tests for converting retained reader receipts to named anchors."""

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import navigation_anchor_capture as capture
from scripts import navigation_anchors as anchors


NONCE = "a" * 32
CAPTURE_TIME = "2026-11-07T02:29:24.3862102+00:00"


def receipt():
    return {"schemaVersion": 1, "observation": {
        "schemaVersion": 1,
        "readerStatus": "running",
        "nonce": NONCE,
        "capturedAtUtc": CAPTURE_TIME,
        "target": {"readerSessionNonce": NONCE, "executableSha256": "b" * 64},
        "fastObservation": {
            "schemaVersion": 1,
            "bindingStatus": "bound-scoped",
            "freshnessStatus": "fresh-scoped",
            "selectionStatus": "selected-scoped",
            "provenance": "recent-full-scan-anchored-candidate-regions/1",
            "candidateSequence": 19529,
            "candidateEpoch": 1,
            "scan": {"scope": "candidate-regions", "status": "complete",
                     "completed": True},
            "observation": {
                "schemaVersion": 1,
                "sequence": 19529,
                "epoch": 1,
                "player": {"status": "ok", "value": "u035400012FA2D678"},
                "fields": {
                    "coordX": {"status": "ok", "value": 7450.2998046875},
                    "coordY": {"status": "ok", "value": 864.3099975585938},
                    "coordZ": {"status": "ok", "value": 2984.559814453125},
                },
            },
        },
    }}


class NavigationAnchorCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw_path = self.root / "receipt.json"

    def write(self, value=None):
        if value is None:
            value = receipt()
        self.raw_path.write_text(json.dumps(value, allow_nan=True), encoding="utf-8")
        return self.raw_path

    def test_retained_receipt_becomes_exact_offline_anchor(self):
        path = self.write()
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        result = capture.catalog_from_receipt(path, "Old_Lab1", "Old Lab 1", "metadata only")
        self.assertEqual(result["coordinateFrame"], anchors.COORDINATE_FRAME)
        saved = result["anchors"][0]
        self.assertEqual(saved["position"], {
            "x": 7450.2998046875, "y": 864.3099975585938,
            "z": 2984.559814453125})
        self.assertEqual(saved["source"], {
            "kind": "addon-feedback-receipt", "gameBuildSha256": "B" * 64,
            "evidenceSha256": digest, "capturedAtUtc": CAPTURE_TIME})
        self.assertEqual(saved["qualification"], "offline-reference-only")
        self.assertEqual(saved["zoneLabel"], "metadata only")
        resolved = anchors.resolve_anchor(result, "old_lab1")
        self.assertFalse(resolved["movementEligible"])
        self.assertEqual(resolved["planarGoal"], {
            "x": 7450.2998046875, "z": 2984.559814453125})

    def test_inconsistent_reader_nonce_is_rejected(self):
        for key, changed in (("nonce", "bad"), ("target", {"readerSessionNonce": "c" * 32,
                                                            "executableSha256": "b" * 64})):
            with self.subTest(key=key):
                value = receipt()
                value["observation"][key] = changed
                with self.assertRaisesRegex(anchors.AnchorCatalogError, "nonce"):
                    capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")

    def test_scoped_sequence_epoch_and_player_must_agree(self):
        for mutation in ("sequence", "epoch", "player"):
            with self.subTest(mutation=mutation):
                value = receipt()
                scoped = value["observation"]["fastObservation"]
                if mutation == "sequence":
                    scoped["candidateSequence"] += 1
                elif mutation == "epoch":
                    scoped["observation"]["epoch"] += 1
                else:
                    scoped["observation"]["player"]["status"] = "unavailable"
                with self.assertRaises(anchors.AnchorCatalogError):
                    capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")

    def test_unselected_unfresh_incomplete_sources_fail_closed(self):
        cases = (("readerStatus", "terminated"),
                 ("bindingStatus", "unbound"),
                 ("freshnessStatus", "stale"),
                 ("selectionStatus", "not-selected"),
                 ("provenance", "unqualified"))
        for name, bad in cases:
            with self.subTest(name=name):
                value = receipt()
                owner = value["observation"] if name == "readerStatus" else value["observation"]["fastObservation"]
                owner[name] = bad
                with self.assertRaises(anchors.AnchorCatalogError):
                    capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")
        for key, bad in (("completed", False), ("scope", "full"), ("status", "partial")):
            value = receipt()
            value["observation"]["fastObservation"]["scan"][key] = bad
            with self.subTest(scan=key), self.assertRaises(anchors.AnchorCatalogError):
                capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")

    def test_coordinates_digest_and_timestamp_are_validated(self):
        for bad in (None, "7450", True, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(position=str(bad)[:30]):
                value = receipt()
                value["observation"]["fastObservation"]["observation"]["fields"]["coordX"]["value"] = bad
                with self.assertRaises(anchors.AnchorCatalogError):
                    capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")
        for key, bad in (("executableSha256", "malformed"),):
            value = receipt()
            value["observation"]["target"][key] = bad
            with self.assertRaises(anchors.AnchorCatalogError):
                capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")
        value = receipt()
        value["observation"]["capturedAtUtc"] = "2026-11-07T02:29:24-05:00"
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "capture must use UTC"):
            capture.catalog_from_receipt(self.write(value), "Anchor", "Anchor")

    def test_bad_json_duplicate_keys_and_oversize_fail_cleanly(self):
        for raw in ('{"schemaVersion":1,"schemaVersion":1}',
                    '{"schemaVersion":1,"observation":NaN}',
                    '{"schemaVersion":1,"observation":',
                    '{"schemaVersion":1,"observation":' + "[" * 20000 + "0" + "]" * 20000 + "}"):
            self.raw_path.write_text(raw, encoding="utf-8")
            with self.assertRaises(anchors.AnchorCatalogError):
                capture.catalog_from_receipt(self.raw_path, "Anchor", "Anchor")
        self.raw_path.write_bytes(b"x" * (capture.MAX_RECEIPT_BYTES + 1))
        with self.assertRaisesRegex(anchors.AnchorCatalogError, "oversized"):
            capture.catalog_from_receipt(self.raw_path, "Anchor", "Anchor")

    def test_cli_creates_once_then_never_overwrites(self):
        self.write()
        output = self.root / "catalog.json"
        args = ["--receipt", str(self.raw_path), "--id", "Lab1", "--label", "Lab 1",
                "--output-catalog", str(output)]
        printed = io.StringIO()
        with redirect_stdout(printed):
            self.assertEqual(capture.main(args), 0)
        self.assertEqual(json.loads(printed.getvalue())["movementEligible"], False)
        self.assertEqual(anchors.load_catalog(output)["anchors"][0]["id"], "Lab1")
        existing = output.read_bytes()
        printed = io.StringIO()
        with redirect_stdout(printed):
            self.assertEqual(capture.main(args), 2)
        self.assertEqual(json.loads(printed.getvalue())["status"], "blocked")
        self.assertEqual(output.read_bytes(), existing)

    def test_invalid_receipt_does_not_create_catalog(self):
        value = deepcopy(receipt())
        value["observation"]["fastObservation"]["observation"]["fields"]["coordZ"]["status"] = "unavailable"
        self.write(value)
        output = self.root / "should-not-exist.json"
        printed = io.StringIO()
        with redirect_stdout(printed):
            self.assertEqual(capture.main(["--receipt", str(self.raw_path), "--id", "Bad",
                                           "--label", "Bad", "--output-catalog", str(output)]), 2)
        self.assertEqual(json.loads(printed.getvalue())["status"], "blocked")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
