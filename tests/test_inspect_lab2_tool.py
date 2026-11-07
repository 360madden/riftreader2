import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
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


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.first, self.second = self.base / "first", self.base / "second"
        self.base_patch = patch.object(tool.flow, "OUTPUT_BASE", self.base)
        self.base_patch.start()
        self.addCleanup(self.base_patch.stop)

    def evidence(self, n):
        t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=n * 10)
        return {"plan": {"sourceHashes": {"source": "hash"}}, "target": {"pid": 1},
                "vm": {"pid": 2}, "epoch": "epoch", "captureId": f"capture{n}",
                "requestId": f"request{n}", "source": f"source{n}", "started": t,
                "completed": t + timedelta(seconds=1), "captured": t + timedelta(seconds=2)}

    def test_matching_pins_and_fresh_order_pass(self):
        with patch.object(tool, "confirmation_evidence", side_effect=[self.evidence(0), self.evidence(1)]):
            tool.confirm(self.first, self.second)

    def test_changed_pins_reused_ids_and_times_fail(self):
        for key, value in (("plan", {}), ("target", {}), ("vm", {}), ("epoch", "other"),
                           ("captureId", "capture0"), ("requestId", "request0"),
                           ("source", "source0"), ("started", self.evidence(0)["started"])):
            with self.subTest(key=key):
                second = self.evidence(1)
                second[key] = value
                with patch.object(tool, "confirmation_evidence", side_effect=[self.evidence(0), second]):
                    with self.assertRaises(ValueError):
                        tool.confirm(self.first, self.second)

    def test_same_or_existing_roots_block_before_work(self):
        for second in (self.first, self.base):
            with self.subTest(second=second), patch.object(tool.flow, "main") as workflow:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(tool.main(["--output", str(self.first), "--confirm-output", str(second)]), 2)
                workflow.assert_not_called()

    def test_second_failure_does_not_publish_first_image(self):
        calls = []
        def workflow(args):
            calls.append(args)
            print('{}')
            return 0 if len(calls) == 1 else 2
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tool.flow, "main", workflow), patch.object(tool, "delivery", return_value={"image": "secret"}), patch.object(tool, "confirmation_evidence", return_value={}), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(tool.main(["--output", str(self.first), "--confirm-output", str(self.second)]), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["output"], str(self.second))
        self.assertNotIn("image", err.getvalue())

    def test_changed_first_delivery_blocks_both_images(self):
        def workflow(_):
            print('{}')
            return 0
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tool.flow, "main", workflow), patch.object(tool, "delivery", side_effect=[{"image": "one"}, {"image": "two"}, {"image": "changed"}]), patch.object(tool, "confirmation_evidence", return_value={}), patch.object(tool.flow, "publish") as publish, redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(tool.main(["--output", str(self.first), "--confirm-output", str(self.second)]), 2)
        self.assertEqual(out.getvalue(), "")
        publish.assert_not_called()

    def test_success_runs_twice_and_publishes_after_confirmation(self):
        calls = []
        def workflow(args):
            calls.append(args)
            print('{}')
            return 0
        out = io.StringIO()
        with patch.object(tool.flow, "main", workflow), patch.object(tool, "delivery", side_effect=[{"image": "one"}, {"image": "two"}, {"image": "one"}, {"image": "two"}]), patch.object(tool, "confirmation_evidence", return_value={"snapshot": 1}), patch.object(tool, "confirm") as confirm, patch.object(tool.flow, "publish") as publish, redirect_stdout(out):
            self.assertEqual(tool.main(["--output", str(self.first), "--confirm-output", str(self.second)]), 0)
        self.assertEqual(len(calls), 2)
        confirm.assert_called_once_with(self.first, self.second, {"snapshot": 1})
        publish.assert_called_once()
        self.assertEqual(json.loads(out.getvalue())["confirmation"], "passed")


if __name__ == "__main__":
    unittest.main()
