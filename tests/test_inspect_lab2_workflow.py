"""Synthetic tests: identity drift and artifact corruption never become success."""
from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import inspect_lab2_workflow as flow


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        base = patch.object(flow, "OUTPUT_BASE", self.root.parent)
        base.start()
        self.addCleanup(base.stop)
        flow.publish(self.root / "workflow-owner.json",
                     {"workflow": "lab2-inspection/1", "output": str(self.root)})
        self.target = {"processId": 42, "processStartUtcTicks": 123,
                       "executableSha256": "A"*64, "windowHandle": "0x12",
                       "clientWidth": 640, "clientHeight": 480, "isForeground": True}
        self.state = {"lab": "lab2", "resource": flow.RESOURCE,
                      "epoch": "epoch", "target": self.target}
        self.now = datetime.now(timezone.utc)

    def artifact(self, **changes):
        folder = self.root / "capture"
        folder.mkdir()
        data = bytearray(26)
        data[:2] = b"BM"
        struct.pack_into("<ii", data, 18, 640, 480)
        (folder / "image.bmp").write_bytes(data)
        digest = hashlib.sha256(data).hexdigest().upper()
        value = {"target": self.target, "capturedAtUtc": self.now.isoformat(),
                 "captureId": "capture", "savedImage": {"path": "image.bmp", "sha256": digest,
                                                        "byteLength": len(data)},
                 "artifact": {"sha256": digest, "byteLength": len(data)}}
        value.update(changes)
        (folder / "capture.json").write_text(json.dumps(value))

    def test_artifact_integrity_and_geometry(self):
        self.artifact()
        flow.validate_capture(self.root, self.state, self.now, self.now)
        (self.root / "capture/image.bmp").write_bytes(b"BM" + b"corrupted")
        with self.assertRaises(flow.InspectionBlocked):
            flow.validate_capture(self.root, self.state, self.now, self.now)

    def test_stale_screenshot_is_refused(self):
        self.artifact(capturedAtUtc=(self.now-timedelta(minutes=1)).isoformat())
        with self.assertRaisesRegex(flow.InspectionBlocked, "UTC"):
            flow.validate_capture(self.root, self.state, self.now, self.now)

    def test_full_target_drift_is_refused(self):
        self.artifact(target={**self.target, "clientWidth": 800})
        with self.assertRaisesRegex(flow.InspectionBlocked, "geometry"):
            flow.validate_capture(self.root, self.state, self.now, self.now)

    def test_epoch_change_is_refused(self):
        host = MagicMock()
        host.status.return_value = {"guest": {"target": self.target}}
        with patch.object(flow, "ready_epoch", return_value="other"):
            with self.assertRaisesRegex(flow.InspectionBlocked, "epoch"):
                flow.check_status(host, self.state)

    def test_wrong_lab_rejected_before_host_creation(self):
        flow.publish(self.root / "state.json", {"lab": "lab1"})
        flow.publish(self.root / "state.sha256.json", {"sha256": flow.digest(self.root / "state.json")})
        with patch.object(flow, "ManagedPinnedHost") as host:
            with self.assertRaisesRegex(flow.InspectionBlocked, "Lab 2"):
                flow.reopen(self.root)
            host.assert_not_called()

    def test_state_mutation_rejected(self):
        flow.publish(self.root / "state.json", self.state)
        flow.publish(self.root / "state.sha256.json", {"sha256": "bad"})
        with self.assertRaisesRegex(flow.InspectionBlocked, "state hash"):
            flow.reopen(self.root)

    def test_publish_is_no_replace(self):
        path = self.root / "immutable.json"
        flow.publish(path, {"a": 1})
        with self.assertRaises(FileExistsError):
            flow.publish(path, {"a": 2})
        self.assertEqual(json.loads(path.read_text()), {"a": 1})

    def test_unrelated_existing_directory_is_never_written(self):
        (self.root / "workflow-owner.json").unlink()
        before = set(self.root.iterdir())
        self.assertEqual(flow.main(["preflight", "--output", str(self.root)]), 2)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_noncanonical_output_is_refused(self):
        with self.assertRaises(flow.InspectionBlocked):
            flow.output_root(self.root / "nested" / "run")

    def capture_fake(self, *, capture_error=False, stop_ok=True, cleanup_error=False,
                     invalid_token=False, cleanup_generation=3, cleanup_receipt="nav-cleanup-proof"):
        host = MagicMock()
        host.client.request.return_value = {"stopped": stop_ok, "recoveryRequired": False}
        queue = MagicMock()
        queue.dispatch_fence.return_value = nullcontext()
        queue.dispatch.side_effect = lambda **kw: {"request_id": kw["request_id"], "token": "invalid" if invalid_token else "a"*64,
                                                 "lease": {flow.RESOURCE: {"epoch": "epoch", "generation": 2}}}
        if not stop_ok:
            queue.finish.side_effect = RuntimeError("lease expired; another owner now holds resource")
        def screenshot(client, output):
            if capture_error:
                raise RuntimeError("authenticated capture refused")
            self.artifact()
        patches = [patch.object(flow, "reopen", return_value=(self.state, host)),
                   patch.object(flow, "check_status"), patch.object(flow, "fresh"),
                   patch.object(flow, "AccessQueue", return_value=queue),
                   patch.object(flow, "idle_queue", return_value={"generation": cleanup_generation,
                                                                  "cleanup_receipt": cleanup_receipt}),
                   patch.object(flow, "ControlClient"),
                   patch.object(flow, "_capture", side_effect=screenshot),
                   patch.object(flow, "await_release", side_effect=RuntimeError("cleanup failed")
                                if cleanup_error else None, return_value="failed" if capture_error or not stop_ok or invalid_token else "succeeded")]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            if capture_error or not stop_ok or cleanup_error or invalid_token or cleanup_generation != 3 or not cleanup_receipt:
                with self.assertRaises((RuntimeError, flow.InspectionBlocked)):
                    flow.capture(self.root, flow.Timings())
                self.assertFalse((self.root / "capture-receipt.json").exists())
            else:
                self.assertEqual(flow.capture(self.root, flow.Timings())["status"], "captured-and-released")
        host.client.request.assert_not_called()
        queue.finish.assert_called_once()
        self.assertEqual(queue.dispatch.call_args.kwargs.keys(), {"request_id"})
        return queue

    def test_read_only_capture_completes_with_named_lease(self):
        self.capture_fake()

    def test_auth_capture_failure_finishes_for_watchdog_cleanup(self):
        queue = self.capture_fake(capture_error=True)
        self.assertEqual(queue.finish.call_args.args[2], "failed")

    def test_expired_lease_never_sends_stop_or_publishes_success(self):
        self.capture_fake(stop_ok=False)

    def test_cleanup_failure_never_publishes_success(self):
        self.capture_fake(cleanup_error=True)

    def test_invalid_issued_token_cannot_capture_or_claim_success(self):
        self.capture_fake(invalid_token=True)
        self.assertFalse((self.root / "capture").exists())

    def test_other_cleanup_generation_cannot_attest_own_release(self):
        self.capture_fake(cleanup_generation=5)

    def test_missing_watchdog_receipt_cannot_attest_release(self):
        self.capture_fake(cleanup_receipt="")

    def test_removed_ownership_marker_blocks_before_admission(self):
        (self.root / "workflow-owner.json").unlink()
        with patch.object(flow, "reopen") as reopen, patch.object(flow, "AccessQueue") as queue:
            with self.assertRaises(RuntimeError):
                flow.capture(self.root, flow.Timings())
            reopen.assert_not_called()
            queue.assert_not_called()

    def test_wrong_dispatch_grant_only_cancels_own_request(self):
        queue = MagicMock()
        queue.dispatch_fence.return_value = nullcontext()
        queue.dispatch.return_value = {"request_id": "someone-else", "token": "b"*64}
        with patch.object(flow, "reopen", return_value=(self.state, MagicMock())), \
                patch.object(flow, "check_status"), patch.object(flow, "fresh"), \
                patch.object(flow, "AccessQueue", return_value=queue), \
                patch.object(flow, "idle_queue"), patch.object(flow, "_capture") as screenshot:
            with self.assertRaisesRegex(flow.InspectionBlocked, "own queue grant"):
                flow.capture(self.root, flow.Timings())
        own_id = queue.submit.call_args.args[0]
        queue.dispatch.assert_called_once_with(request_id=own_id)
        queue.cancel.assert_called_once_with(own_id, flow.OWNER)
        queue.finish.assert_not_called()
        screenshot.assert_not_called()

    def test_fresh_identity_refusal_never_acquires_or_captures(self):
        with patch.object(flow, "reopen", return_value=(self.state, MagicMock())), \
                patch.object(flow, "check_status"), \
                patch.object(flow, "fresh", side_effect=RuntimeError("identity mismatch")), \
                patch.object(flow, "AccessQueue") as queue, \
                patch.object(flow, "_capture") as screenshot:
            with self.assertRaises(RuntimeError):
                flow.capture(self.root, flow.Timings())
            queue.assert_not_called()
            screenshot.assert_not_called()

    def test_failed_phase_cannot_retry_same_root(self):
        self.capture_fake(capture_error=True)
        with patch.object(flow, "reopen") as reopen:
            with self.assertRaisesRegex(flow.InspectionBlocked, "already attempted"):
                flow.capture(self.root, flow.Timings())
            reopen.assert_not_called()

    def test_private_context_rejects_binding_changes(self):
        from types import SimpleNamespace
        from contextlib import ExitStack
        for change in ("root", "planhash", "statehash", "plan", "config", "vm", "target"):
            with self.subTest(change=change):
                root = self.root / change
                root.mkdir()
                plan = {"lab": "lab2", "resource": flow.RESOURCE,
                        "configPath": str(flow.CONFIGS["lab2"]), "database": str(flow.QUEUE),
                        "vmIdentity": {"pid": 10}}
                flow.publish(root / "managed-host-plan.json", plan)
                state = {**self.state, "output": str(root), "vmIdentity": {"pid": 10},
                         "planSha256": flow.digest(root / "managed-host-plan.json")}
                flow.publish(root / "state.json", state)
                flow.publish(root / "state.sha256.json", {"sha256": flow.digest(root / "state.json")})
                host = SimpleNamespace(plan_path=root / "managed-host-plan.json", plan=dict(plan),
                                       config="config", check=MagicMock(),
                                       target={key: self.target[key] for key in
                                               ("processId", "processStartUtcTicks", "executableSha256", "windowHandle")})
                context = {"root": root, "planSha256": state["planSha256"],
                           "stateSha256": flow.digest(root / "state.json"), "host": host}
                with ExitStack() as stack:
                    stack.enter_context(patch.object(flow, "assert_owned"))
                    stack.enter_context(patch.object(flow.HostConfig, "load", return_value="config"))
                    constructor = stack.enter_context(patch.object(flow, "ManagedPinnedHost"))
                    self.assertIs(flow.reopen(root, _admitted=context)[1], host)
                    if change == "root": context["root"] = self.root
                    elif change == "planhash": context["planSha256"] = "changed"
                    elif change == "statehash": context["stateSha256"] = "changed"
                    elif change == "plan": host.plan["resource"] = "vm:rift-lab-1"
                    elif change == "config": host.config = "other"
                    elif change == "vm": host.plan["vmIdentity"] = {"pid": 11}
                    elif change == "target": host.target["windowHandle"] = "0x99"
                    with self.assertRaises(flow.InspectionBlocked):
                        flow.reopen(root, _admitted=context)
                    constructor.assert_not_called()

    def test_preflight_run_uses_one_factory_admission(self):
        from contextlib import ExitStack
        for combined in (False, True):
            with self.subTest(combined=combined):
                root = self.root / ("combined" if combined else "standalone")
                host = MagicMock()
                host.plan = {"vmIdentity": {"pid": 10}, "guestInstance": "agent-instance"}
                host.plan_path = root / "managed-host-plan.json"
                host.status.return_value = {"guest": {"target": self.target}}
                def factory(*args):
                    flow.publish(host.plan_path, host.plan)
                    return host
                with ExitStack() as stack:
                    stack.enter_context(patch.object(flow, "ensure_guest_agent"))
                    admitted_factory = stack.enter_context(patch.object(flow, "admit_lab2_inspection_host", side_effect=factory))
                    standard_factory = stack.enter_context(patch.object(flow, "write_managed_host_plan", side_effect=lambda *args: factory(*args).plan_path))
                    constructor = stack.enter_context(patch.object(flow, "ManagedPinnedHost", return_value=host))
                    stack.enter_context(patch.object(flow, "ready_epoch", return_value="epoch"))
                    stack.enter_context(patch.object(flow, "fresh"))
                    stack.enter_context(patch.object(flow, "check_status"))
                    context = {} if combined else None
                    flow.preflight(root, flow.Timings(), _admitted=context,
                                   _native={"mode": "persistent"} if combined else None)
                    self.assertEqual(admitted_factory.call_count, 1 if combined else 0)
                    self.assertEqual(standard_factory.call_count, 0 if combined else 1)
                    self.assertEqual(constructor.call_count, 0 if combined else 1)
                    if combined:
                        self.assertIs(context["host"], host)
                        self.assertEqual(flow.load(root / "state.json")["nativeRequest"]["agentInstanceId"], "agent-instance")

    def test_final_inventory_failure_prevents_report(self):
        self.artifact()
        flow.publish(self.root / "capture-receipt.json", {
            "status": "captured-and-released", "epoch": "epoch",
            "beforeUtc": self.now.isoformat(), "afterUtc": self.now.isoformat(),
            "metadataSha256": flow.digest(self.root / "capture/capture.json"),
            "imageSha256": flow.digest(self.root / "capture/image.bmp")})
        host = MagicMock()
        host.final_inventory_check.side_effect = RuntimeError("VM inventory changed")
        with patch.object(flow, "reopen", return_value=(self.state, host)), \
                patch.object(flow, "fresh"), patch.object(flow, "check_status"), \
                patch.object(flow, "AccessQueue"), patch.object(flow, "idle_queue"):
            with self.assertRaisesRegex(RuntimeError, "inventory changed"):
                flow.verify(self.root, flow.Timings(), _admitted={"host": host})
        self.assertFalse((self.root / "report.json").exists())

    def test_failed_run_still_checks_final_inventory(self):
        host = MagicMock()
        host.plan = {"vmIdentity": {"pid": 1}}
        def refused(root, timing, *, _admitted):
            _admitted["host"] = host
            raise flow.InspectionBlocked("fresh identity refused")
        with patch.object(flow, "preflight", side_effect=refused):
            self.assertEqual(flow.main(["run", "--output", str(self.root)]), 2)
        host.final_inventory_check.assert_called_once()
        self.assertFalse((self.root / "report.json").exists())

    def test_pid_or_listener_drift_stops_phase_before_queue(self):
        for reason in ("managed host process epoch changed", "operator listener owner changed"):
            with self.subTest(reason=reason), patch.object(flow, "reopen", return_value=(self.state, MagicMock())) as reopen, \
                    patch.object(flow, "check_status", side_effect=RuntimeError(reason)), \
                    patch.object(flow, "AccessQueue") as queue, patch.object(flow, "_capture") as screenshot:
                with self.assertRaisesRegex(RuntimeError, reason):
                    flow.capture(self.root, flow.Timings())
                queue.assert_not_called()
                screenshot.assert_not_called()

    def native_fixture(self):
        from tests.test_sample_current_native_vitals import report, GUEST_READER
        value = report()
        value["observation"]["startedAtUtc"] = self.now.isoformat()
        value["observation"]["completedAtUtc"] = self.now.isoformat()
        identity = value["observation"]["identity"]
        state = {**self.state, "vmIdentity": {"pid": 1},
                 "target": {**self.target, **identity},
                 "nativeRequest": {"readerSha256": "B"*64, "guestReader": GUEST_READER}}
        base = self.root / "native-evidence"
        source = base / "lab2" / "session" / "samples.json"
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps(value))
        summary = {"status": "candidate-only", "lab": "lab2", "vmIdentity": state["vmIdentity"],
                   "gameProcessId": identity["processId"], "gameProcessStartUtcTicks": identity["processStartUtcTicks"],
                   "gameSha256": identity["executableSha256"], "readerExecutableSha256": "B"*64,
                   "guestReaderPath": GUEST_READER, "guestReaderReused": True,
                   "sourceReport": str(source), "sourceReportSha256": flow.digest(source),
                   "metrics": flow.vitals.validate_report(value, pid=identity["processId"],
                                                          ticks=identity["processStartUtcTicks"])}
        return state, summary, base, source

    def test_native_identity_join_rejects_other_epoch(self):
        state, summary, base, source = self.native_fixture()
        with patch.object(flow.vitals, "EVIDENCE", base):
            metrics, completed = flow.validate_native(summary, state, self.now, self.now)
            self.assertEqual(completed, self.now)
            self.assertEqual(metrics["health"]["current"], 100)
            summary["gameProcessId"] += 1
            with self.assertRaisesRegex(flow.InspectionBlocked, "pin mismatch"):
                flow.validate_native(summary, state, self.now, self.now)

    def test_native_source_tamper_is_rejected(self):
        state, summary, base, source = self.native_fixture()
        source.write_text("{}")
        with patch.object(flow.vitals, "EVIDENCE", base):
            with self.assertRaisesRegex(flow.InspectionBlocked, "report hash"):
                flow.validate_native(summary, state, self.now, self.now)

    def test_native_summary_metrics_tamper_is_rejected(self):
        state, summary, base, source = self.native_fixture()
        summary["metrics"]["health"]["current"] = 1
        with patch.object(flow.vitals, "EVIDENCE", base):
            with self.assertRaisesRegex(flow.InspectionBlocked, "metrics differ"):
                flow.validate_native(summary, state, self.now, self.now)

    def test_partial_native_arguments_fail_before_vm(self):
        with patch.object(flow, "preflight") as preflight, patch.object(flow, "ensure_guest_agent") as guest:
            self.assertEqual(flow.main(["run", "--output", str(self.root),
                                       "--native-reader-sha256", "A"*64]), 2)
            preflight.assert_not_called()
            guest.assert_not_called()

    def test_requested_native_failure_blocks_capture_and_report(self):
        options = {"reader": "reader", "readerSha256": "B"*64, "guestReader": "guest"}
        with patch.object(flow, "native_options", return_value=options), \
                patch.object(flow, "preflight"), \
                patch.object(flow, "capture_native", side_effect=flow.InspectionBlocked("native refused")), \
                patch.object(flow, "capture") as capture, patch.object(flow, "verify") as verify:
            self.assertEqual(flow.main(["run", "--output", str(self.root)]), 2)
            capture.assert_not_called()
            verify.assert_not_called()
        self.assertFalse((self.root / "report.json").exists())

    def test_native_call_preserves_original_vm_and_game_before_sampling(self):
        state, summary, base, source = self.native_fixture()
        state["nativeRequest"]["reader"] = str(self.root / "RiftReader2.Live.exe")
        host = MagicMock()
        with patch.object(flow, "reopen", return_value=(state, host)), \
                patch.object(flow, "check_status"), patch.object(flow, "fresh"), \
                patch.object(flow.vitals, "run", side_effect=RuntimeError("expected-vm-epoch-mismatch")) as sample:
            with self.assertRaisesRegex(RuntimeError, "expected-vm"):
                flow.capture_native(self.root, flow.Timings(), _admitted={"host": host})
        self.assertEqual(sample.call_args.kwargs["expected_vm"], state["vmIdentity"])
        self.assertEqual(sample.call_args.args[4], flow.expected_game(state))
        self.assertFalse((self.root / "native-vitals-receipt.json").exists())
        self.assertFalse((self.root / "capture").exists())

    def test_native_source_windows_reparse_directory_is_rejected(self):
        from types import SimpleNamespace
        state, summary, base, source = self.native_fixture()
        original = Path.lstat
        actual = source.parent.lstat()
        def lstat(path, *args, **kwargs):
            if path == source.parent:
                return SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(flow.vitals, "EVIDENCE", base), patch.object(Path, "lstat", autospec=True, side_effect=lstat):
            with self.assertRaisesRegex(flow.InspectionBlocked, "reparse ancestry"):
                flow.validate_native(summary, state, self.now, self.now)

    def test_persistent_native_rejects_other_authenticated_agent_instance(self):
        state, summary, base, source = self.native_fixture()
        state["nativeRequest"] = {"mode": "persistent", "agentInstanceId": "expected-agent"}
        summary.update(transport="persistent-control-agent", activeAgentInstanceId="expected-agent")
        for key in ("readerExecutableSha256", "guestReaderPath", "guestReaderReused"):
            summary.pop(key)
        with patch.object(flow.vitals, "EVIDENCE", base):
            flow.validate_native(summary, state, self.now, self.now)
            summary["activeAgentInstanceId"] = "replacement-agent"
            with self.assertRaisesRegex(flow.InspectionBlocked, "agent binding"):
                flow.validate_native(summary, state, self.now, self.now)

    def test_persistent_requested_failure_never_falls_back_to_reader(self):
        state = {**self.state, "nativeRequest": {"mode": "persistent", "agentInstanceId": "agent"}}
        with patch.object(flow, "reopen", return_value=(state, MagicMock())), \
                patch.object(flow, "check_status"), patch.object(flow, "fresh"), \
                patch.object(flow, "persistent_native", side_effect=RuntimeError("capability unavailable")), \
                patch.object(flow.vitals, "run") as explicit:
            with self.assertRaisesRegex(RuntimeError, "capability unavailable"):
                flow.capture_native(self.root, flow.Timings(), _admitted={})
            explicit.assert_not_called()
        self.assertFalse((self.root / "native-vitals-receipt.json").exists())

    def test_persistent_flags_fail_before_vm_on_conflict_or_wrong_phase(self):
        for options in (["run", "--native-vitals", "--native-reader", str(self.root / "reader.exe")],
                        ["preflight", "--native-vitals"]):
            with self.subTest(options=options), patch.object(flow, "preflight") as preflight:
                self.assertEqual(flow.main([*options, "--output", str(self.root)]), 2)
                preflight.assert_not_called()

    def test_joined_verification_retains_gap_and_rejects_receipt_tamper(self):
        state, summary, base, source = self.native_fixture()
        self.target = state["target"]
        self.artifact()
        flow.publish(self.root / "capture-receipt.json", {
            "status": "captured-and-released", "epoch": "epoch",
            "beforeUtc": self.now.isoformat(), "afterUtc": self.now.isoformat(),
            "metadataSha256": flow.digest(self.root / "capture/capture.json"),
            "imageSha256": flow.digest(self.root / "capture/image.bmp")})
        receipt_path = self.root / "native-vitals-receipt.json"
        flow.publish(receipt_path, {"summary": summary, "beforeUtc": self.now.isoformat(),
                                   "afterUtc": self.now.isoformat()})
        flow.publish(self.root / "native-vitals-receipt.sha256.json", {"sha256": flow.digest(receipt_path)})
        host = MagicMock()
        with patch.object(flow, "reopen", return_value=(state, host)), \
                patch.object(flow, "fresh"), patch.object(flow, "check_status", return_value={}), \
                patch.object(flow, "AccessQueue"), patch.object(flow, "idle_queue"), \
                patch.object(flow.vitals, "EVIDENCE", base):
            result = flow.verify(self.root, flow.Timings())
            self.assertEqual(result["nativeVitals"]["sampleToScreenshotSeconds"], 0)
            self.assertEqual(result["nativeVitals"]["metrics"]["health"]["current"], 100)
            (self.root / "report.json").unlink()
            receipt_path.write_text("{}")
            with self.assertRaisesRegex(flow.InspectionBlocked, "receipt changed"):
                flow.verify(self.root, flow.Timings())
            self.assertFalse((self.root / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
