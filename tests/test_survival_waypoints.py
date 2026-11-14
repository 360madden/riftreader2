"""Offline tests for the standalone headless survival Waypoints CLI."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import signal
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import survival_waypoints as cli


NONCE = "0123456789abcdef0123456789abcdef"
ABILITY = "A05213A7D60B13F6B"


class Adapter:
    binding = {"runtimeIdentity": {"machine": "AMD-DESKTOP",
               "gameBuildSha256": "a" * 64, "unitKey": "1"}}
    target = {"machineName": "AMD-DESKTOP", "processId": 21672,
              "processStartUtcTicks": 123, "executableSha256": "a" * 64}
    input_receipt_path = Path("native-input.jsonl")


class Runtime:
    def __init__(self):
        self.calls = []
        self.action_diagnostic = None

    def configure(self, profile, adapter):
        self.calls.append(("configure", profile, adapter))

    def preflight(self, adapter, stop):
        self.calls.append(("preflight", adapter, stop))
        return {"status": "ready", "inputSent": False}

    def route_runner(self, *args, **kwargs):
        self.calls.append(("route", args, kwargs))
        return []

    def status(self):
        return {"configured": bool(self.calls), "active": False,
                "state": "halted", "lastReason": "fixture", "inputSent": False,
                "actionDiagnostic": self.action_diagnostic}


class SurvivalWaypointsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile.json"
        self.route = self.root / "route.json"
        self.checkpoint = self.root / "progress.json"
        self.profile.write_text(json.dumps({
            "schemaVersion": 1, "nonce": NONCE, "resourceKind": "absolute-power",
            "coordinateBasis": {"qualified": True,
                "space": "UIParent-to-client-pixels", "viewportWidth": 1000,
                "viewportHeight": 800, "clientWidth": 1000, "clientHeight": 800,
                "scaleX": 1, "scaleY": 1, "offsetX": 0, "offsetY": 0},
            "abilities": {"damage": ABILITY}, "actions": [ABILITY],
            "thresholds": {"healBelowPct":45, "defendBelowPct":65,
                "retreatBelowPct":25, "recoverHealthPct":80,
                "recoverResourcePct":35, "recoverResourceAbsolute":20,
                "maximumLevelDelta":2},
            "retreat": {"maximumSeconds":20, "minimumTrailPoints":1},
            "timing": {"pollMilliseconds":100,
                       "actionDeadlineMilliseconds":3000}}, indent=2), encoding="utf-8")
        self.route.write_text(json.dumps({"waypoints": [["Start", 1, 2],
                                                          ["End", 2, 3]]}), encoding="utf-8")
        self.outputs = []
        self.adapters = []
        self.runtimes = []

    def parse(self, *values):
        return cli.build_parser().parse_args(values)

    def factories(self):
        def adapter(*values):
            self.adapters.append(values)
            return Adapter()
        def runtime():
            value = Runtime(); self.runtimes.append(value); return value
        return adapter, runtime

    def test_status_profile_is_offline_structured_and_needs_no_adapter(self):
        args = self.parse("status-profile", "--profile", str(self.profile))
        adapter, runtime = self.factories()
        code, result = cli.execute(
            args, adapter_factory=adapter, runtime_factory=runtime,
            emit=self.outputs.append)
        self.assertEqual(0, code)
        self.assertEqual("valid", result["status"])
        self.assertEqual("absolute-power", result["resourceKind"])
        self.assertEqual({"damage": ABILITY}, result["roles"])
        self.assertEqual([], self.adapters)
        self.assertEqual([], self.runtimes)

    def test_preflight_constructs_adapter_after_profile_validation_and_sends_no_input(self):
        args = self.parse("preflight", "--expected-host", "AMD-DESKTOP",
                          "--physical-pid", "21672", "--profile", str(self.profile))
        adapter, runtime = self.factories()
        code, result = cli.execute(
            args, adapter_factory=adapter, runtime_factory=runtime,
            emit=self.outputs.append)
        self.assertEqual(0, code)
        self.assertEqual("ready", result["preflight"]["status"])
        self.assertFalse(result["inputSent"])
        self.assertEqual(1, len(self.adapters))
        self.assertEqual(["configure", "preflight"],
                         [call[0] for call in self.runtimes[0].calls])

    def test_run_requires_execute_before_adapter_and_uses_shared_playback_contract(self):
        common = ("run", "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                  "--profile", str(self.profile), "--route", str(self.route),
                  "--checkpoint", str(self.checkpoint), "--direction", "reverse")
        adapter, runtime = self.factories()
        with self.assertRaisesRegex(cli.UsageError, "requires --execute"):
            cli.execute(self.parse(*common), adapter_factory=adapter,
                        runtime_factory=runtime, emit=self.outputs.append)
        self.assertEqual([], self.adapters)

        observed = {}
        cursor = SimpleNamespace(direction="reverse", next_index=2,
                                 ordered_points=[("End", 2, 3), ("Start", 1, 2)])
        legs = [{"status":"arrived", "inputSent":True}]
        def playback(adapter_value, document, stop, emit, **options):
            observed.update(adapter=adapter_value, document=document, stop=stop,
                            emit=emit, options=options)
            return legs, cursor
        code, result = cli.execute(
            self.parse(*common, "--execute"), adapter_factory=adapter,
            runtime_factory=runtime, playback=playback, emit=self.outputs.append)
        self.assertEqual(0, code)
        self.assertEqual("arrived", result["status"])
        self.assertTrue(result["inputSent"])
        self.assertIs(observed["options"]["runner"].__self__, self.runtimes[0])
        self.assertEqual("reverse", observed["options"]["direction"])
        self.assertFalse(observed["options"]["resume"])
        self.assertTrue(observed["options"]["pass_through"])
        self.assertTrue(observed["options"]["height_aware"])
        self.assertEqual(self.checkpoint, observed["options"]["checkpoint"])

    def test_real_playback_advances_guide_once_and_passes_kinds_and_heights(self):
        self.route.write_text(json.dumps({"waypoints": [["Start", 1, 2],
                                                         ["Stop", 2, 2],
                                                         ["End", 3, 2]],
                                          "heights": [5, 5, 5],
                                          "pointKinds": ["pass", "stop", "pass"]}),
                              encoding="utf-8")
        observed = {}
        class RecordingRuntime(Runtime):
            def route_runner(self, adapter, points, stop, emit, **options):
                observed.update(options)
                from dataclasses import make_dataclass
                position = make_dataclass("Position", ["x", "y", "z"])
                options["entry_check"](position(1, 5, 2))
                for index, (name, x, z) in enumerate(points):
                    passed = index == 0
                    emit({"status": "passed" if passed else "arrived", "name": name,
                          "goal": {"x": x, "z": z},
                          "position": {"x": x, "y": 5, "z": z},
                          "passageVerified": passed, "releaseSucceeded": True,
                          "desktopInputsDown": []})
                return [{"status": "arrived", "inputSent": True}]
        args = self.parse("run", "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                          "--profile", str(self.profile), "--route", str(self.route),
                          "--checkpoint", str(self.checkpoint), "--execute")
        code, result = cli.execute(args, adapter_factory=lambda *_: Adapter(),
                                   runtime_factory=RecordingRuntime, emit=self.outputs.append,
                                   receipt_root=self.root)
        self.assertEqual(0, code)
        self.assertEqual(3, result["nextIndex"])
        self.assertEqual(["pass", "stop", "pass"], observed["point_kinds"])
        self.assertEqual([5, 5, 5], observed["goal_heights"])
        advances = [e["nextWaypoint"] for e in self.outputs
                    if e.get("status") in ("passed", "arrived") and e.get("type") == "event"]
        self.assertEqual([1, 2, 3], advances)

    def test_resume_requires_existing_checkpoint_and_sets_resume(self):
        values = ("resume", "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                  "--profile", str(self.profile), "--route", str(self.route),
                  "--checkpoint", str(self.checkpoint), "--execute")
        adapter, runtime = self.factories()
        with self.assertRaisesRegex(cli.UsageError, "does not exist"):
            cli.execute(self.parse(*values), adapter_factory=adapter,
                        runtime_factory=runtime, emit=self.outputs.append)
        self.assertEqual([], self.adapters)
        self.checkpoint.write_text("{}", encoding="utf-8")
        seen = {}
        cursor = SimpleNamespace(direction="forward", next_index=2,
                                 ordered_points=[("Start", 1, 2), ("End", 2, 3)])
        def playback(*_args, **options):
            seen.update(options)
            return [], cursor
        cli.execute(self.parse(*values), adapter_factory=adapter,
                    runtime_factory=runtime, playback=playback,
                    emit=self.outputs.append)
        self.assertTrue(seen["resume"])
        self.assertTrue(seen["pass_through"])
        self.assertTrue(seen["height_aware"])

    def test_sigint_and_sigbreak_handlers_latch_without_raising(self):
        stop = threading.Event()
        with cli.signal_stop(stop):
            signal.raise_signal(signal.SIGINT)
            self.assertTrue(stop.is_set())
        stop.clear()
        if hasattr(signal, "SIGBREAK"):
            with cli.signal_stop(stop):
                signal.raise_signal(signal.SIGBREAK)
                self.assertTrue(stop.is_set())

    def test_main_reports_usage_as_json_before_live_construction(self):
        stderr = StringIO()
        with redirect_stderr(stderr), redirect_stdout(StringIO()):
            code = cli.main(["run", "--expected-host", "AMD-DESKTOP",
                             "--physical-pid", "21672", "--profile", str(self.profile),
                             "--route", str(self.route)])
        self.assertEqual(2, code)
        result = json.loads(stderr.getvalue())
        self.assertEqual("usage-error", result["status"])
        self.assertFalse(result["inputSent"])

    def test_runtime_failure_saves_bounded_diagnostic_receipt(self):
        values = ("run", "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                  "--profile", str(self.profile), "--route", str(self.route),
                  "--checkpoint", str(self.checkpoint), "--execute")
        adapter, runtime = self.factories()
        def playback(_adapter, _document, _stop, emit, **_options):
            for number in range(300):
                emit({"status":"sample", "number":number})
            self.runtimes[0].action_diagnostic = {
                "operation": "cancel", "stage": "cancel-click",
                "error": {"type": "SurvivalActionError",
                          "reason": "uncertain-release:" + "x" * 4000},
                "nativeReceiptFromAttempt": True,
                "rawNativeReceipt": {
                    "status": "halted", "reason": "native-refusal:" + "y" * 4000,
                    "errorType": "InvalidOperationException",
                    "actionId": "controls.cancel", "cleanup": True,
                    "inputSent": True, "releaseSucceeded": False,
                    "desktopInputsDown": ["mouse-left"] + ["z" * 200] * 40,
                    "responseVerified": False,
                    "target": {"machineName": "AMD-DESKTOP", "processId": 21672,
                               "processStartUtcTicks": 123,
                               "executableSha256": "a" * 64,
                               "windowHandle": "0x1C4013AE",
                               "executablePath": "q" * 100000},
                    "hugeBlob": "z" * 100000}}
            _adapter._survival_cleanup_uncertain = True
            raise RuntimeError("critical-unavailable")
        with self.assertRaises(cli.ExecutionFailure) as caught:
            cli.execute(self.parse(*values), adapter_factory=adapter,
                        runtime_factory=runtime, playback=playback,
                        emit=self.outputs.append, receipt_root=self.root / "receipts")
        failure = caught.exception
        self.assertEqual("refused", failure.status)
        self.assertTrue(failure.receipt.is_file())
        document = json.loads(failure.receipt.read_text(encoding="utf-8"))
        self.assertEqual("critical-unavailable", document["error"]["reason"])
        self.assertEqual("RuntimeError", document["error"]["type"])
        self.assertEqual(self.checkpoint.as_posix(),
                         Path(document["checkpointPath"]).as_posix())
        self.assertEqual(256, len(document["events"]))
        self.assertEqual(44, document["events"][0]["number"])
        self.assertEqual(299, document["events"][-1]["number"])
        self.assertEqual(Adapter.target, document["exactTarget"])
        self.assertTrue(document["releaseFault"])
        self.assertEqual("halted", document["runtime"]["state"])
        self.assertEqual("native-input.jsonl", document["latestNativeInputReceiptPath"])
        diagnostic = document["runtime"]["actionDiagnostic"]
        self.assertEqual("cancel", diagnostic["operation"])
        self.assertEqual("cancel-click", diagnostic["stage"])
        self.assertEqual("SurvivalActionError", diagnostic["error"]["type"])
        self.assertEqual(2000, len(diagnostic["error"]["reason"]))
        self.assertTrue(diagnostic["error"]["truncated"])
        self.assertTrue(diagnostic["nativeReceiptFromAttempt"])
        raw = diagnostic["rawNativeReceipt"]
        self.assertEqual("controls.cancel", raw["actionId"])
        self.assertTrue(raw["cleanup"])
        self.assertTrue(raw["inputSent"])
        self.assertFalse(raw["releaseSucceeded"])
        self.assertFalse(raw["responseVerified"])
        self.assertEqual(32, len(raw["desktopInputsDown"]))
        self.assertEqual(21672, raw["target"]["processId"])
        self.assertEqual(123, raw["target"]["processStartUtcTicks"])
        self.assertEqual("a" * 64, raw["target"]["executableSha256"])
        self.assertEqual("0x1C4013AE", raw["target"]["windowHandle"])
        self.assertNotIn("hugeBlob", raw)
        self.assertNotIn("executablePath", raw["target"])
        self.assertTrue(diagnostic["rawNativeReceiptTruncated"])
        self.assertLessEqual(len(json.dumps(document["runtime"]).encode("utf-8")),
                             32 * 1024)

    def test_main_error_json_includes_failure_receipt_path(self):
        receipt = self.root / "failure.json"
        receipt.write_text("{}", encoding="utf-8")
        failure = cli.ExecutionFailure(RuntimeError("critical-unavailable"),
                                       receipt, "refused")
        stderr = StringIO()
        with (patch.object(cli, "execute", side_effect=failure),
              redirect_stderr(stderr), redirect_stdout(StringIO())):
            code = cli.main(["status-profile", "--profile", str(self.profile)])
        self.assertEqual(3, code)
        result = json.loads(stderr.getvalue())
        self.assertEqual("refused", result["status"])
        self.assertEqual(str(receipt), result["receipt"])

    def test_stop_failure_receipt_is_classified_and_contains_path_for_stderr(self):
        values = ("run", "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                  "--profile", str(self.profile), "--route", str(self.route), "--execute")
        adapter, runtime = self.factories()
        stop = threading.Event()
        def playback(*_args, **_options):
            stop.set()
            return [], SimpleNamespace(direction="forward", next_index=0,
                                       ordered_points=[("Start", 1, 2)])
        with self.assertRaises(cli.ExecutionFailure) as caught:
            cli.execute(self.parse(*values), adapter_factory=adapter,
                        runtime_factory=runtime, playback=playback, stop=stop,
                        emit=self.outputs.append, receipt_root=self.root / "stop-receipts")
        self.assertEqual("stopped", caught.exception.status)
        document = json.loads(caught.exception.receipt.read_text(encoding="utf-8"))
        self.assertTrue(document["stopLatched"])
        self.assertEqual("stopped", document["status"])


if __name__ == "__main__":
    unittest.main()
