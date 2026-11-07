import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import inspect_lab2_tool as tool


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        base_patch = patch.object(tool.flow, "OUTPUT_BASE", self.root.parent)
        base_patch.start()
        self.addCleanup(base_patch.stop)
        (self.root / "workflow-owner.json").write_text(json.dumps({"workflow": "lab2-inspection/1", "output": str(self.root)}), encoding="utf-8")
        capture = self.root / "capture"
        capture.mkdir()
        image = capture / "image.bmp"
        image.write_bytes(b"BM test")
        digest = hashlib.sha256(image.read_bytes()).hexdigest().upper()
        report = {"status": "verified-awaiting-visual-review", "lab": "lab2",
                  "finalInventory": {"status": "passed"}, "image": str(image), "epoch": "e",
                  "target": {"pid": 1}, "captureId": "c", "capturedAtUtc": "t",
                  "nativeVitals": {"metrics": {"health": 10, "unitKey": 239816685224113596}, "mode": "persistent", "qualification": "candidate-only; semantics/passive-freshness/restart-unverified; UI review required"}}
        self.receipt = {"status": "captured-and-released", "imageSha256": digest,
                        "epoch": "e", "watchdogCleanup": {"stopVerified": True, "generation": 5, "receipt": "proof"}}
        metadata = {"savedImage": {"sha256": digest}, "artifact": {"sha256": digest},
                    "target": {"pid": 1}, "captureId": "c", "capturedAtUtc": "t"}
        metadata_raw = json.dumps(metadata).encode()
        self.receipt["metadataSha256"] = hashlib.sha256(metadata_raw).hexdigest().upper()
        state_raw = json.dumps({"epoch": "e", "target": {"pid": 1}}).encode()
        (self.root / "state.json").write_bytes(state_raw)
        (self.root / "state.sha256.json").write_text(json.dumps({"sha256": hashlib.sha256(state_raw).hexdigest().upper()}), encoding="utf-8")
        for path, obj in ((self.root / "report.json", report), (self.root / "capture-receipt.json", self.receipt),
                          (capture / "capture.json", metadata)):
            path.write_text(json.dumps(obj), encoding="utf-8")
        self.console = {"phase": "run", "status": report["status"], "output": str(self.root),
                        "image": str(image), "report": str(self.root / "report.json"), "elapsedSeconds": 3.5}

    def test_delivery_verified_result(self):
        result = tool.delivery(self.root, self.console)
        self.assertEqual(result["image"], self.console["image"])
        self.assertEqual(result["nativeVitals"]["metrics"]["unitKey"], "239816685224113596")
        self.assertEqual(result["nativeVitals"]["metrics"]["health"], 10)
        self.assertEqual(result["nativeVitals"]["qualification"], "candidate-only; semantics/passive-freshness/restart-unverified; UI review required")

    def test_wrong_root_refused(self):
        self.console["image"] = str(self.root.parent / "image.bmp")
        with self.assertRaisesRegex(ValueError, "path mismatch"):
            tool.delivery(self.root, self.console)

    def test_changed_image_refused(self):
        (self.root / "capture" / "image.bmp").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            tool.delivery(self.root, self.console)

    def test_metadata_binding_refused(self):
        path = self.root / "capture" / "capture.json"
        data = json.loads(path.read_text())
        data["captureId"] = "other"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.receipt["metadataSha256"] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        (self.root / "capture-receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            tool.delivery(self.root, self.console)

    def test_changed_metadata_hash_refused(self):
        path = self.root / "capture" / "capture.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            tool.delivery(self.root, self.console)

    def test_reparse_parent_refused(self):
        original = Path.is_symlink
        def fake_symlink(path):
            return path == self.root / "capture" or original(path)
        with patch.object(Path, "is_symlink", fake_symlink):
            with self.assertRaisesRegex(ValueError, "reparse"):
                tool.delivery(self.root, self.console)

    def test_epoch_binding_refused(self):
        self.receipt["epoch"] = "other"
        (self.root / "capture-receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            tool.delivery(self.root, self.console)

    def test_missing_cleanup_refused(self):
        self.receipt["watchdogCleanup"]["stopVerified"] = False
        (self.root / "capture-receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cleanup proof"):
            tool.delivery(self.root, self.console)

    def test_failed_workflow_does_not_publish_image(self):
        def failed(_):
            print('{"image":"unsafe"}')
            return 2
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tool.flow, "main", failed), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(tool.main(["--output", str(self.root)]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("image", json.loads(err.getvalue()))


if __name__ == "__main__":
    unittest.main()
