"""Synthetic Lab 1 observation tests; no guest, controller or queue is contacted."""
from contextlib import redirect_stderr
import io
import json
import struct
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts import inspect_lab2_workflow as flow
from scripts import inspect_lab2_tool as tool


class Lab1ObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        base = patch.object(flow, "OUTPUT_BASE", self.root.parent)
        base.start()
        self.addCleanup(base.stop)
        self.target = {"processId": 42, "processStartUtcTicks": 123,
                       "executableSha256": "A" * 64, "windowHandle": "0x12",
                       "clientWidth": 640, "clientHeight": 480, "isForeground": True}
        self.state = {"lab": "lab1", "resource": "vm:rift-lab-1",
                      "output": str(self.root), "epoch": "epoch", "target": self.target,
                      "vmIdentity": {"epoch": 1}}
        self.marker("lab1")

    def marker(self, lab):
        (self.root / "workflow-owner.json").write_text(json.dumps(
            {"workflow": lab + "-inspection/1", "output": str(self.root)}), encoding="utf-8")

    def save_state(self, state):
        (self.root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (self.root / "state.sha256.json").write_text(json.dumps(
            {"sha256": flow.digest(self.root / "state.json")}), encoding="utf-8")

    def config(self, **changes):
        value = dict(expected_machine_name=flow.LABS["lab1"]["machine"],
                     vmx=flow.LABS["lab1"]["vmx"], vnc_port=flow.LABS["lab1"]["port"],
                     ui_port=49811)
        value.update(changes)
        return SimpleNamespace(**value)

    def test_explicit_binding_is_immutable_and_distinct(self):
        binding = flow.lab_binding("lab1")
        self.assertEqual((binding.lab, binding.resource, binding.owner, binding.workflow,
                          binding.ui_port),
                         ("lab1", "vm:rift-lab-1", "lab1-inspection",
                          "lab1-inspection/1", 49811))
        self.assertEqual(flow.lab_binding("lab2").ui_port, 49921)
        with self.assertRaises((AttributeError, TypeError)):
            binding.resource = "vm:rift-lab-2"
        with self.assertRaises(flow.InspectionBlocked):
            flow.lab_binding("lab3")

    def test_lab2_marker_cannot_open_lab1_before_host_or_queue(self):
        self.marker("lab2")
        with patch.object(flow, "ManagedPinnedHost") as host, patch.object(flow, "AccessQueue") as queue:
            with self.assertRaises(flow.InspectionBlocked):
                flow.reopen(self.root, lab="lab1")
        host.assert_not_called()
        queue.assert_not_called()

    def test_cross_lab_state_and_resource_block_before_host_or_queue(self):
        for changes in ({"lab": "lab2"}, {"resource": "vm:rift-lab-2"}):
            with self.subTest(changes=changes):
                self.save_state({**self.state, **changes})
                with patch.object(flow, "ManagedPinnedHost") as host, patch.object(flow, "AccessQueue") as queue:
                    with self.assertRaisesRegex(flow.InspectionBlocked, "target binding changed"):
                        flow.reopen(self.root, lab="lab1", _admitted={})
                host.assert_not_called()
                queue.assert_not_called()

    def test_lab1_split_and_native_cli_refused_before_dependencies(self):
        cases = [[phase, "--lab", "lab1"] for phase in ("preflight", "capture", "verify")]
        cases.append(["run", "--lab", "lab1", "--native-vitals"])
        for args in cases:
            with self.subTest(args=args), patch.object(flow, "ensure_guest_agent") as guest, \
                    patch.object(flow, "ensure_inspection_dependency") as dependency, \
                    patch.object(flow, "admit_inspection_host_with_status") as admission, \
                    patch.object(flow, "AccessQueue") as queue, redirect_stderr(io.StringIO()) as err:
                output = self.root.parent / (self.root.name + "-unused")
                self.assertEqual(flow.main(args + ["--output", str(output)]), 2)
                reason = json.loads(err.getvalue())["reason"]
                self.assertIn("native" if "--native-vitals" in args else "joined", reason)
                guest.assert_not_called()
                dependency.assert_not_called()
                admission.assert_not_called()
                queue.assert_not_called()

    def test_lab1_dependency_uses_canonical_endpoint(self):
        config = self.config()
        status = {"host": {"connected": True, "machineName": flow.LABS["lab1"]["machine"],
                           "coordination": {"state": "ready", "resource": "vm:rift-lab-1"},
                           "consoleReservation": {"held": True, "faulted": False}},
                  "guest": {"armed": False, "busy": False, "recoveryRequired": False,
                            "desktopInputsDown": []}}
        with patch.object(flow.HostConfig, "load", return_value=config) as load, \
                patch.object(flow, "_probe", return_value=status) as probe, \
                patch.object(flow, "ensure_guest_agent") as ensure:
            flow.ensure_inspection_dependency(lab="lab1")
        load.assert_called_once_with(flow.CONFIGS["lab1"])
        probe.assert_called_once_with(config)
        ensure.assert_not_called()

    def test_lab2_endpoint_is_refused_for_lab1_before_probe_or_recovery(self):
        with patch.object(flow.HostConfig, "load", return_value=self.config(ui_port=49921)), \
                patch.object(flow, "_probe") as probe, patch.object(flow, "ensure_guest_agent") as ensure:
            with self.assertRaises(flow.InspectionBlocked):
                flow.ensure_inspection_dependency(lab="lab1")
        probe.assert_not_called()
        ensure.assert_not_called()

    def test_fresh_identity_uses_lab1_config_and_epoch_resource(self):
        host = MagicMock()
        host.status.return_value = {"guest": {"target": self.target}}
        def query(*args, **kwargs):
            return kwargs["_status_supplier"](host.config)
        with patch.object(flow, "validate_config", return_value="native"), \
                patch.object(flow, "query", side_effect=query) as identity, \
                patch.object(flow, "ready_epoch", return_value="epoch") as epoch:
            flow.fresh(host, self.state, _check_status=True)
        self.assertEqual(identity.call_args.args[3], flow.CONFIGS["lab1"])
        self.assertEqual(epoch.call_args.args[2], "vm:rift-lab-1")
        self.assertEqual(epoch.call_args.args[1]["lab"], "lab1")
        host.status.assert_called_once_with(require_armed=False)

    def test_lab1_capture_queue_uses_lab1_owner_resource_and_request(self):
        host, queue = MagicMock(), MagicMock()
        queue.dispatch.side_effect = RuntimeError("synthetic dispatch stop")
        with patch.object(flow, "reopen", return_value=(self.state, host)), \
                patch.object(flow, "fresh"), patch.object(flow, "check_status"), \
                patch.object(flow, "AccessQueue", return_value=queue), \
                patch.object(flow, "idle_queue") as idle, patch.object(flow, "_capture") as capture:
            with self.assertRaisesRegex(RuntimeError, "synthetic dispatch stop"):
                flow.capture(self.root, flow.Timings(), lab="lab1", _admitted={"host": host})
        request, owner, kind, epochs = queue.submit.call_args.args
        self.assertTrue(request.startswith("lab1-inspect-"))
        self.assertEqual((owner, kind, epochs), ("lab1-inspection", "C", {"vm:rift-lab-1": "epoch"}))
        idle.assert_called_once_with(queue, "vm:rift-lab-1", "epoch")
        queue.cancel.assert_called_once_with(request, "lab1-inspection")
        capture.assert_not_called()

    def test_lab1_run_inspection_is_explicit_capture_only(self):
        def workflow(args):
            self.assertIn("--lab", args)
            self.assertEqual(args[args.index("--lab") + 1], "lab1")
            self.assertNotIn("--native-vitals", args)
            print(json.dumps({"phase": "run"}))
            return 0
        with patch.object(tool.flow, "main", side_effect=workflow), \
                patch.object(tool, "delivery", return_value={"targetId": "lab1"}) as delivery:
            result, _ = tool.run_inspection(self.root, capture_only=True, lab="lab1")
        self.assertEqual(result["targetId"], "lab1")
        self.assertEqual(delivery.call_args.kwargs, {"require_native": False, "lab": "lab1"})


    def delivery_fixture(self):
        capture = self.root / "capture"
        capture.mkdir(exist_ok=True)
        raw = bytearray(54 + 640 * 480 * 3)
        raw[:2] = b"BM"
        struct.pack_into("<I", raw, 2, len(raw))
        struct.pack_into("<I", raw, 10, 54)
        struct.pack_into("<IiiHH", raw, 14, 40, 640, 480, 1, 24)
        image = capture / "image.bmp"
        image.write_bytes(raw)
        image_hash = flow.digest(image)
        metadata = {"target": self.target, "captureId": "lab1-fresh-capture",
                    "capturedAtUtc": "2026-11-09T12:00:00Z",
                    "savedImage": {"sha256": image_hash}, "artifact": {"sha256": image_hash}}
        (capture / "capture.json").write_text(json.dumps(metadata), encoding="utf-8")
        self.save_state(self.state)
        report = {"status": "verified-awaiting-visual-review", "lab": "lab1",
                  "epoch": "epoch", "target": self.target, "image": str(image),
                  "captureId": metadata["captureId"], "capturedAtUtc": metadata["capturedAtUtc"],
                  "finalInventory": {"status": "passed"}}
        receipt = {"status": "captured-and-released", "epoch": "epoch",
                   "metadataSha256": flow.digest(capture / "capture.json"),
                   "imageSha256": image_hash,
                   "watchdogCleanup": {"stopVerified": True, "generation": 2, "receipt": "lab1-cleanup"}}
        (self.root / "report.json").write_text(json.dumps(report), encoding="utf-8")
        (self.root / "capture-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return {"phase": "run", "status": report["status"], "output": str(self.root),
                "image": str(image), "report": str(self.root / "report.json"), "elapsedSeconds": 3.5}

    def test_lab1_delivery_preserves_identity_hash_and_cleanup(self):
        console = self.delivery_fixture()
        result = tool.delivery(self.root, console, require_native=False, lab="lab1")
        self.assertEqual(result["targetId"], "lab1")
        self.assertEqual(result["workflow"], "vmware")
        self.assertEqual(result["captureBackend"], "managed-controller/guest-agent")
        self.assertEqual(result["imageSha256"], flow.digest(Path(result["image"])))
        self.assertEqual(result["target"]["processStartUtcTicks"], "123")
        self.assertTrue(result["cleanupVerified"])
        self.assertNotIn("nativeVitals", result)

    def test_lab1_delivery_refuses_crossed_marker_report_state_and_resource(self):
        for case in ("marker", "report", "state", "resource"):
            with self.subTest(case=case):
                self.marker("lab1")
                console = self.delivery_fixture()
                if case == "marker":
                    self.marker("lab2")
                elif case == "report":
                    path = self.root / "report.json"
                    report = json.loads(path.read_text(encoding="utf-8"))
                    report["lab"] = "lab2"
                    path.write_text(json.dumps(report), encoding="utf-8")
                else:
                    self.save_state({**self.state, **({"lab": "lab2"} if case == "state"
                                                     else {"resource": "vm:rift-lab-2"})})
                with self.assertRaises((ValueError, flow.InspectionBlocked)):
                    tool.delivery(self.root, console, require_native=False, lab="lab1")

    def test_lab1_delivery_and_run_reject_native_before_work(self):
        with patch.object(tool.flow, "main") as workflow:
            with self.assertRaisesRegex(ValueError, "lab1-native"):
                tool.run_inspection(self.root, lab="lab1")
        workflow.assert_not_called()
        with patch.object(tool, "safe_bytes") as read:
            with self.assertRaisesRegex(ValueError, "lab1-native"):
                tool.delivery(self.root, {}, lab="lab1")
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
