import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "experiment_core.py"
SPEC = importlib.util.spec_from_file_location("experiment_core", SCRIPT)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

VM = {"vmx": "rift-lab.vmx", "startTicks": 123}
GAME = {"processId": 456, "startTicks": 789, "buildSha256": "B" * 64}


def valid_plan():
    return {
        "schemaVersion": 1,
        "experimentId": "turn-left-001",
        "key": "a",
        "holdMilliseconds": 80,
        "expectedVmIdentity": VM,
        "expectedGameBinding": GAME,
        "reviewedCaptureId": "capture-123",
        "configSha256": "A" * 64,
    }


class FakeAdapter:
    def __init__(self, identities=None, pulse_result=None, pulse_error=None):
        self.identities = list(identities or [(VM, GAME)] * 3)
        self.pulse_result = pulse_result or {
            "inputSent": True,
            "releaseSent": True,
            "hostStartedAtUtc": "2026-10-19T12:00:00Z",
            "hostCompletedAtUtc": "2026-10-19T12:00:00.080Z",
        }
        self.pulse_error = pulse_error
        self.calls = []

    def identity(self):
        self.calls.append("identity")
        return self.identities.pop(0)

    def capture_before(self):
        self.calls.append("capture_before")
        return {"captureId": "before"}

    def pulse(self, key, hold_ms, capture_id, stop_requested):
        self.calls.append(("pulse", key, hold_ms, capture_id))
        if self.pulse_error:
            raise self.pulse_error
        return self.pulse_result

    def capture_after(self):
        self.calls.append("capture_after")
        return {"captureId": "after"}

    def stop(self):
        self.calls.append("stop")
        return {"status": "requested"}

    def recover(self):
        self.calls.append("recover")
        return {"releaseSent": True}


class ExperimentCoreTests(unittest.TestCase):
    def run_once(self, adapter=None, plan=None, stop_requested=lambda: False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "experiment"
        result = core.run_experiment(
            plan or valid_plan(), adapter or FakeAdapter(), output, stop_requested
        )
        self.assertTrue((output / "result.json").is_file())
        return result, output

    def test_completed_means_delivered_sampled_and_identity_bound(self):
        adapter = FakeAdapter()
        result, _ = self.run_once(adapter)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["identityChecks"]), 3)
        self.assertIsNone(result["recovery"])
        self.assertIn("capture_after", adapter.calls)
        self.assertTrue(any("does not verify" in item for item in result["uncertainties"]))

    def test_identity_drift_before_pulse_sends_zero_input(self):
        changed = dict(GAME, processId=999)
        adapter = FakeAdapter(identities=[(VM, GAME), (VM, changed)])
        result, _ = self.run_once(adapter)
        self.assertEqual(result["status"], "refused")
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "pulse" for call in adapter.calls))
        self.assertNotIn("stop", adapter.calls)

    def test_invalid_bounds_are_rejected_before_io(self):
        for hold in (19, 251, True):
            with self.subTest(hold=hold):
                adapter = FakeAdapter()
                plan = valid_plan()
                plan["holdMilliseconds"] = hold
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / "experiment"
                    with self.assertRaises(core.ExperimentError):
                        core.run_experiment(plan, adapter, output)
                    self.assertFalse(output.exists())
                    self.assertEqual(adapter.calls, [])

    def test_cancellation_during_pulse_requests_stop_and_recovery(self):
        adapter = FakeAdapter()
        checks = iter((False, False, True))
        result, _ = self.run_once(adapter, stop_requested=lambda: next(checks, True))
        self.assertEqual(result["status"], "cancelled")
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)
        self.assertTrue(result["recovery"]["recover"]["releaseSent"])

    def test_pulse_exception_preserves_uncertainty_and_recovers(self):
        adapter = FakeAdapter(pulse_error=RuntimeError("partial delivery unknown"))
        result, _ = self.run_once(adapter)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)
        self.assertIsNone(result["pulse"])

    def test_keyboard_interrupt_is_durable_cancelled_result_with_recovery(self):
        adapter = FakeAdapter(pulse_error=KeyboardInterrupt())
        result, output = self.run_once(adapter)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["error"]["type"], "KeyboardInterrupt")
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)
        self.assertTrue((output / "result.json").is_file())

    def test_stop_during_after_capture_cannot_report_completed(self):
        adapter = FakeAdapter()
        checks = iter((False, False, False, True))
        result, _ = self.run_once(adapter, stop_requested=lambda: next(checks, True))
        self.assertEqual(result["status"], "cancelled")
        self.assertIn("capture_after", adapter.calls)
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)

    def test_possible_input_signal_is_not_erased_by_input_sent_false(self):
        adapter = FakeAdapter(
            pulse_result={
                "inputSent": False,
                "inputMayHaveBeenSent": True,
                "releaseSent": True,
            }
        )
        result, _ = self.run_once(adapter)
        self.assertEqual(result["status"], "failed")
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)

    def test_unconfirmed_release_cannot_complete(self):
        adapter = FakeAdapter(pulse_result={"inputSent": True, "releaseSent": False})
        result, _ = self.run_once(adapter)
        self.assertEqual(result["status"], "failed")
        self.assertIn("stop", adapter.calls)
        self.assertIn("recover", adapter.calls)
        self.assertTrue(any("release" in item.lower() for item in result["uncertainties"]))

    def test_existing_output_rejects_duplicate_without_adapter_io(self):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "experiment"
            output.mkdir()
            with self.assertRaisesRegex(core.ExperimentError, "single-use"):
                core.run_experiment(valid_plan(), adapter, output)
        self.assertEqual(adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
