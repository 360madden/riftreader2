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

    def test_process_start_ticks_are_exact_decimal_text_in_delivery(self):
        ticks = 639297512883473401
        for name in ("report.json", "state.json", "capture/capture.json"):
            path = self.root / name
            data = json.loads(path.read_text())
            data["target"]["processStartUtcTicks"] = ticks
            path.write_text(json.dumps(data), encoding="utf-8")
        state_sha = hashlib.sha256((self.root / "state.json").read_bytes()).hexdigest().upper()
        (self.root / "state.sha256.json").write_text(json.dumps({"sha256": state_sha}), encoding="utf-8")
        self.receipt["metadataSha256"] = hashlib.sha256((self.root / "capture/capture.json").read_bytes()).hexdigest().upper()
        (self.root / "capture-receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        result = tool.delivery(self.root, self.console)
        self.assertEqual(result["target"]["processStartUtcTicks"], str(ticks))
        self.assertEqual(json.loads((self.root / "report.json").read_text())["target"]["processStartUtcTicks"], ticks)

    def test_capture_only_delivery_does_not_require_native_vitals(self):
        path = self.root / "report.json"
        report = json.loads(path.read_text())
        del report["nativeVitals"]
        path.write_text(json.dumps(report), encoding="utf-8")
        result = tool.delivery(self.root, self.console, require_native=False)
        self.assertNotIn("nativeVitals", result)
        self.assertEqual(result["targetId"], "lab2")
        self.assertEqual(result["captureBackend"], "managed-controller/guest-agent")
        self.assertEqual(result["capturedAtUtc"], "t")
        self.assertTrue(result["cleanupVerified"])
        with self.assertRaisesRegex(ValueError, "native candidate result missing"):
            tool.delivery(self.root, self.console)

    def test_capture_only_refuses_native_artifact_mixup(self):
        with self.assertRaisesRegex(ValueError, "capture-only artifacts"):
            tool.delivery(self.root, self.console, require_native=False)

    def test_capture_only_keeps_cleanup_guard(self):
        path = self.root / "report.json"
        report = json.loads(path.read_text())
        del report["nativeVitals"]
        path.write_text(json.dumps(report), encoding="utf-8")
        self.receipt["watchdogCleanup"]["stopVerified"] = False
        (self.root / "capture-receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cleanup proof"):
            tool.delivery(self.root, self.console, require_native=False)

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


class CaptureOnlyTests(unittest.TestCase):
    def test_capture_only_omits_native_read_and_delivers_once(self):
        calls = []
        def workflow(args):
            calls.append(args)
            print('{"phase":"run"}')
            return 0
        out = io.StringIO()
        with patch.object(tool.flow, "main", side_effect=workflow), patch.object(
                tool, "delivery", return_value={"status": "verified-awaiting-visual-review"}) as deliver, redirect_stdout(out):
            self.assertEqual(tool.main(["--output", "fresh", "--capture-only"]), 0)
        self.assertEqual(calls, [["run", "--output", "fresh"]])
        deliver.assert_called_once_with(Path("fresh"), {"phase": "run"}, require_native=False)

    def test_capture_only_rejects_native_modes_before_any_work(self):
        for extra in (["--confirm-output", "second"], ["--reviewed-output", "old"],
                      ["--reviewed-image-sha256", "A" * 64], ["--focus", "energy"]):
            with self.subTest(extra=extra), patch.object(tool.flow, "main") as workflow, redirect_stderr(io.StringIO()):
                self.assertEqual(tool.main(["--output", "fresh", "--capture-only"] + extra), 2)
                workflow.assert_not_called()

    def test_guarded_failure_preserves_reason_without_publishing_artifacts(self):
        def workflow(_):
            print(json.dumps({"status": "blocked", "phase": "run",
                              "errorType": "InspectionBlocked", "reason": "active request prevents capture",
                              "image": "must-not-publish"}), file=tool.sys.stderr)
            return 2
        out, err = io.StringIO(), io.StringIO()
        with patch.object(tool.flow, "main", workflow), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(tool.main(["--output", "fresh", "--capture-only"]), 2)
        self.assertEqual(out.getvalue(), "")
        result = json.loads(err.getvalue())
        self.assertEqual(result["reason"], "active request prevents capture")
        self.assertEqual(result["workflowFailure"]["errorType"], "InspectionBlocked")
        self.assertNotIn("image", result["workflowFailure"])
        self.assertNotIn("must-not-publish", err.getvalue())

    def test_non_object_failure_is_generic(self):
        def workflow(_):
            print('["not a structured failure"]', file=tool.sys.stderr)
            return 2
        with patch.object(tool.flow, "main", workflow):
            with self.assertRaisesRegex(tool.WorkflowBlocked, "guarded workflow failed"):
                tool.run_inspection(Path("fresh"), capture_only=True)


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


class ReviewedContinuationTests(unittest.TestCase):
    def test_invalid_combinations_do_not_run_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            with patch.object(tool.flow, "OUTPUT_BASE", base), patch.object(tool.flow, "main") as workflow, redirect_stderr(io.StringIO()):
                args = ["--output", str(base / "new"), "--reviewed-output", str(base / "old")]
                self.assertEqual(tool.main(args), 2)
                self.assertEqual(tool.main(args + ["--reviewed-image-sha256", "A" * 64, "--focus", "health", "--confirm-output", str(base / "other")]), 2)
                self.assertEqual(tool.main(args + ["--reviewed-image-sha256", "wrong", "--focus", "energy"]), 2)
                workflow.assert_not_called()

    def test_runs_only_new_observation_and_projects_selected_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            first, second = base / "old", base / "new"
            prior = {"imageSha256": "A" * 64}
            current = {"status": "verified-awaiting-visual-review", "image": "current", "imageSha256": "B" * 64,
                       "report": "report", "workflowSeconds": 1, "nativeVitals": {"metrics": {"health": 9, "energy": 3}, "qualification": "candidate", "sourceReportSha256": "hash"}}
            def workflow(args):
                print('{}')
                return 0
            out = io.StringIO()
            with patch.object(tool.flow, "OUTPUT_BASE", base), patch.object(tool.flow, "main", side_effect=workflow) as run, patch.object(tool, "reviewed_delivery", return_value=prior), patch.object(tool, "confirmation_evidence", return_value={"source": "source"}), patch.object(tool, "reviewed_snapshot", return_value=("hash",)), patch.object(tool, "delivery", return_value=current), patch.object(tool, "confirm") as confirm, patch.object(tool.flow, "publish"), redirect_stdout(out):
                self.assertEqual(tool.main(["--output", str(second), "--reviewed-output", str(first), "--reviewed-image-sha256", "A" * 64, "--focus", "energy"]), 0)
            run.assert_called_once_with(["run", "--native-vitals", "--output", str(second)])
            confirm.assert_called_once_with(first, second, {"source": "source"})
            result = json.loads(out.getvalue())
            self.assertEqual(result["selectedMetric"], 3)
            self.assertEqual(result["qualification"], "candidate")
            self.assertEqual(result["nativeSourceReportSha256"], "hash")
            self.assertNotIn("nativeVitals", result)

    def test_changed_prior_suppresses_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            out, err = io.StringIO(), io.StringIO()
            with patch.object(tool.flow, "OUTPUT_BASE", base), patch.object(tool.flow, "main", side_effect=lambda _: print('{}') or 0), patch.object(tool, "reviewed_delivery", return_value={"imageSha256": "A" * 64}), patch.object(tool, "confirmation_evidence", return_value={"source": "source"}), patch.object(tool, "reviewed_snapshot", side_effect=[("before",), ("after",)]), patch.object(tool, "delivery", return_value={}), patch.object(tool.flow, "publish") as publish, redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(tool.main(["--output", str(base / "new"), "--reviewed-output", str(base / "old"), "--reviewed-image-sha256", "A" * 64, "--focus", "health"]), 2)
            self.assertEqual(out.getvalue(), "")
            publish.assert_not_called()

    def test_changed_new_delivery_suppresses_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            out, err = io.StringIO(), io.StringIO()
            with patch.object(tool.flow, "OUTPUT_BASE", base), patch.object(tool.flow, "main", side_effect=lambda _: print('{}') or 0), patch.object(tool, "reviewed_delivery", return_value={"imageSha256": "A" * 64}), patch.object(tool, "confirmation_evidence", return_value={"source": "source"}), patch.object(tool, "reviewed_snapshot", return_value=("same",)), patch.object(tool, "confirm"), patch.object(tool, "delivery", side_effect=[{"image": "first"}, {"image": "changed"}]), patch.object(tool.flow, "publish") as publish, redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(tool.main(["--output", str(base / "new"), "--reviewed-output", str(base / "old"), "--reviewed-image-sha256", "A" * 64, "--focus", "health"]), 2)
            self.assertEqual(out.getvalue(), "")
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
