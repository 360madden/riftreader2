"""Offline admission, identity pairing and no-input tests for the native CLI."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import read_native_telemetry as cli
from scripts.sample_current_native_vitals import GAME_SHA

INSTANCE = "a" * 32
GAME = {"processId": 123, "processStartUtcTicks": 639000000000000001,
        "executableSha256": GAME_SHA}
VM = {"vmx": "lab2.vmx", "port": 5962, "logEpoch": "epoch", "pid": 4,
      "listenerPid": 4, "image": "vmware-vmx.exe", "startTicks": 12}
KEY = "18446744073709551615"


def status():
    return {"host": {"connected": True, "machineName": "RIFT-LAB-2",
            "instanceId": INSTANCE, "vmIdentity": dict(VM),
            "coordination": {"state": "ready"},
            "consoleReservation": {"held": True, "faulted": False}},
            "guest": {"armed": False, "busy": False, "recoveryRequired": False,
                      "desktopInputsDown": [], "instanceId": INSTANCE,
                      "target": {**GAME, "machineName": "RIFT-LAB-2"}}}


def sample(kind):
    row = {"schemaVersion": 1, "status": "candidate-only", "lab": "lab2",
           "transport": "persistent-control-agent", "vmIdentity": dict(VM),
           "activeAgentInstanceId": INSTANCE, "gameProcessId": GAME["processId"],
           "gameProcessStartUtcTicks": GAME["processStartUtcTicks"], "gameSha256": GAME_SHA,
           "observedAtUtc": "2026-11-09T15:50:00.0000001Z",
           "sourceReport": (str(Path.cwd() / "artifacts" / (kind + "-test") / "samples.json")
                            if kind in ("smoothed-scalar", "actor-pose") else kind + ".json"),
           "sourceReportSha256": "B" * 64,
           "limitation": "candidate-only"}
    row["metrics"] = ({"unitKey": KEY, "x": 1.5, "y": 2.5, "z": 3.5,
                       "freshness": "unqualified"} if kind == "position" else
                      {"unitKey": int(KEY), "health": {"current": 100, "maximum": 100},
                       "mana": {"current": None, "status": "unavailable"}} if kind == "vitals" else
                       {"unitKey": KEY, "playerKeyDecimal": KEY, "targetCandidate": 2.5,
                         "headingQualified": False} if kind == "smoothed-scalar" else
                        {"unitKey": KEY, "playerKeyDecimal": KEY,
                        "actorAngleDegreesCandidate": 45.0,
                        "actorHeadingQualified": False})
    return row


class NativeTelemetryCommandTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.before, self.after = status(), status()
        self.position, self.vitals, self.pose = sample("position"), sample("vitals"), sample("actor-pose")
        self.host = SimpleNamespace(expected_machine_name="RIFT-LAB-2", vmx=Path("lab2.vmx"),
                                    vnc_port=5962, vmrun=Path("vmrun.exe"), output_directory=Path("output"))
        self.client = Mock()
        self.client.request.side_effect = [self.before, self.after]
        self.hostname = stack.enter_context(patch.object(cli.socket, "gethostname", return_value="AMD-DESKTOP"))
        self.ensure = stack.enter_context(patch.object(cli, "ensure"))
        self.resolve = stack.enter_context(patch.object(cli, "resolve_current_managed_controller",
            return_value=(Path("process.json"), {"vmIdentity": dict(VM)}, {})))
        stack.enter_context(patch.object(cli.HostConfig, "load", return_value=self.host))
        stack.enter_context(patch.object(cli, "ControlClient", return_value=self.client))
        stack.enter_context(patch.object(cli, "validate_config", return_value="native-config"))
        self.xyz_query = stack.enter_context(patch.object(cli, "query_xyz", return_value=self.position))
        self.vitals_query = stack.enter_context(patch.object(cli, "query_vitals", return_value=self.vitals))
        self.pose_query = stack.enter_context(patch.object(cli, "query_actor_pose", return_value=self.pose))
        self.scalar = sample("smoothed-scalar")
        self.scalar_query = stack.enter_context(patch.object(cli, "query_smoothed_scalar", return_value=self.scalar))

    def run_read(self):
        return cli.read_once("lab2", "AMD-DESKTOP")

    def test_success_preserves_candidates_sources_nulls_and_lossless_unit(self):
        original = copy.deepcopy(self.vitals)
        result = self.run_read()
        self.assertEqual("candidate-only", result["status"])
        self.assertFalse(result["atomic"])
        self.assertFalse(result["luaReaderUsed"])
        self.assertFalse(result["screenshotUsed"])
        self.assertEqual(KEY, result["unitKey"])
        self.assertEqual(KEY, result["vitals"]["metrics"]["unitKey"])
        self.assertIsNone(result["vitals"]["metrics"]["mana"]["current"])
        self.assertEqual(original, self.vitals)
        self.assertEqual("position.json", result["position"]["sourceReport"])
        self.assertEqual("unqualified", result["position"]["metrics"]["freshness"])
        self.ensure.assert_called_once_with("lab2")
        self.assertEqual(2, self.resolve.call_count)
        self.assertEqual([("/api/status",), ("/api/status",)],
                         [call.args for call in self.client.request.call_args_list])
        self.assertTrue(all(call.kwargs == {"method": "GET"}
                            for call in self.client.request.call_args_list))
        self.xyz_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab2"], lab="lab2")
        self.pose_query.assert_not_called()

    def test_wrong_machine_rejected_before_dependency_start(self):
        self.hostname.return_value = "LEGION"
        with self.assertRaisesRegex(ValueError, "host-mismatch"):
            self.run_read()
        self.ensure.assert_not_called()
        self.xyz_query.assert_not_called()

    def test_wrong_expected_host_rejected_before_dependency_start(self):
        with self.assertRaisesRegex(ValueError, "host-mismatch"):
            cli.read_once("lab2", "LEGION")
        self.ensure.assert_not_called()

    def test_unsupported_lab_has_no_fallback(self):
        with self.assertRaisesRegex(ValueError, "target-not-supported"):
            cli.read_once("lab3", "AMD-DESKTOP")
        self.ensure.assert_not_called()

    def _lab1(self):
        self.host.expected_machine_name = "RIFT-LAB-1"
        for observed in (self.before, self.after):
            observed["host"]["machineName"] = "RIFT-LAB-1"
            observed["guest"]["target"]["machineName"] = "RIFT-LAB-1"
        for source in (self.position, self.pose, self.scalar):
            source["lab"] = "lab1"

    def test_lab1_defaults_to_position_only_without_vitals(self):
        self._lab1()
        result = cli.read_once("lab1", "AMD-DESKTOP")
        self.assertEqual(result["targetId"], "lab1")
        self.assertEqual(result["unitKey"], KEY)
        self.assertIn("position", result)
        self.assertNotIn("vitals", result)
        self.ensure.assert_called_once_with("lab1")
        self.xyz_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab1"], lab="lab1")
        self.vitals_query.assert_not_called()
        self.pose_query.assert_not_called()
        self.scalar_query.assert_not_called()

    def test_lab1_can_select_existing_pose_and_scalar_sources(self):
        self._lab1()
        result = cli.read_once("lab1", "AMD-DESKTOP",
                               fields=("smoothed-scalar", "actor-pose", "position"))
        self.assertEqual(result["targetId"], "lab1")
        self.assertEqual(set(result) & set(cli.NATIVE_FIELDS),
                         {"position", "actor-pose", "smoothed-scalar"})
        self.pose_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab1"], lab="lab1")
        self.scalar_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab1"], lab="lab1")
        self.vitals_query.assert_not_called()

    def test_lab1_vitals_refused_before_controller_or_sources(self):
        with self.assertRaisesRegex(ValueError, "lab1-vitals-not-supported"):
            cli.read_once("lab1", "AMD-DESKTOP", fields=("position", "vitals"))
        self.ensure.assert_not_called()
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_not_called()

    def test_lab1_source_from_lab2_is_not_mixed(self):
        self._lab1()
        self.pose["lab"] = "lab2"
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            cli.read_once("lab1", "AMD-DESKTOP", fields=("position", "actor-pose"))
        self.vitals_query.assert_not_called()

    def test_armed_controller_blocks_reads(self):
        self.before["guest"]["armed"] = True
        with self.assertRaisesRegex(ValueError, "not-idle"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_wrong_guest_blocks_reads(self):
        self.before["host"]["machineName"] = "RIFT-LAB-1"
        with self.assertRaisesRegex(ValueError, "guest-mismatch"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_changed_build_blocks_reads(self):
        self.before["guest"]["target"]["executableSha256"] = "C" * 64
        with self.assertRaisesRegex(ValueError, "build-mismatch"):
            self.run_read()
        self.xyz_query.assert_not_called()

    def test_different_unit_keys_are_not_merged(self):
        self.vitals["metrics"]["unitKey"] = 999
        with self.assertRaisesRegex(ValueError, "unit-changed"):
            self.run_read()

    def test_wrong_process_epoch_is_not_merged(self):
        self.position["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_changed_agent_is_not_merged(self):
        self.vitals["activeAgentInstanceId"] = "b" * 32
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_changed_vm_is_not_merged(self):
        self.position["vmIdentity"]["startTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()

    def test_postflight_target_change_blocks_publication(self):
        self.after["guest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(ValueError, "postflight-changed"):
            self.run_read()

    def test_no_fallback_after_native_query_failure(self):
        self.xyz_query.side_effect = cli.Blocked("native-xyz-response-stale")
        with self.assertRaises(cli.Blocked):
            self.run_read()
        self.vitals_query.assert_not_called()

    def test_unit_key_validation_rejects_invalid_types_and_ranges(self):
        for value in (True, 0, -1, "01", "1.0", 2**64, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "unit-key-invalid"):
                cli.unit_key(value)

    def test_position_only_never_queries_vitals(self):
        self.vitals_query.side_effect = AssertionError("unrequested read")
        result = cli.read_once("lab2", "AMD-DESKTOP", fields=("position",))
        self.assertIn("position", result)
        self.assertNotIn("vitals", result)
        self.assertEqual(KEY, result["position"]["metrics"]["unitKey"])
        self.xyz_query.assert_called_once()
        self.vitals_query.assert_not_called()
        self.assertEqual(2, self.resolve.call_count)
        self.assertEqual(2, self.client.request.call_count)

    def test_vitals_only_never_queries_position_and_preserves_null(self):
        self.xyz_query.side_effect = AssertionError("unrequested read")
        original = copy.deepcopy(self.vitals)
        result = cli.read_once("lab2", "AMD-DESKTOP", fields=("vitals",))
        self.assertNotIn("position", result)
        self.assertIn("vitals", result)
        self.assertEqual(KEY, result["vitals"]["metrics"]["unitKey"])
        self.assertIsNone(result["vitals"]["metrics"]["mana"]["current"])
        self.assertEqual(original, self.vitals)
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_called_once()
        self.assertEqual(2, self.resolve.call_count)

    def test_pose_only_is_read_only_with_lossless_owner_key(self):
        result = cli.read_once("lab2", "AMD-DESKTOP", fields=("actor-pose",))
        self.assertNotIn("position", result)
        self.assertNotIn("vitals", result)
        self.assertEqual(KEY, result["unitKey"])
        self.assertEqual(KEY, result["actor-pose"]["metrics"]["playerKeyDecimal"])
        self.assertFalse(result["actor-pose"]["metrics"]["actorHeadingQualified"])
        source = Path(result["actor-pose"]["sourceReport"])
        self.assertEqual(str(source.with_name("summary.json")),
                         result["actor-pose"]["summaryPath"])
        self.assertNotIn("summaryPath", self.pose)
        self.pose_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab2"], lab="lab2")
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_not_called()

    def test_pose_and_position_mismatch_cannot_publish(self):
        self.pose["metrics"]["unitKey"] = "999"
        with self.assertRaisesRegex(ValueError, "unit-changed"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("position", "actor-pose"))

    def test_pose_process_epoch_mismatch_cannot_publish(self):
        self.pose["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("actor-pose",))

    def test_pose_summary_requires_absolute_samples_sibling(self):
        for source in ("relative/samples.json", str(Path.cwd() / "wrong.json")):
            with self.subTest(source=source):
                self.client.request.side_effect = [self.before, self.after]
                self.pose["sourceReport"] = source
                with self.assertRaisesRegex(ValueError, "pose-source-invalid"):
                    cli.read_once("lab2", "AMD-DESKTOP", fields=("actor-pose",))

    def test_pose_failure_does_not_fall_back(self):
        self.pose_query.side_effect = cli.Blocked("native-actor-pose-unavailable")
        with self.assertRaises(cli.Blocked):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("actor-pose",))
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_not_called()

    def test_scalar_only_retains_candidate_and_never_queries_other_sources(self):
        result = cli.read_once("lab2", "AMD-DESKTOP", fields=("smoothed-scalar",))
        self.assertEqual(KEY, result["unitKey"])
        self.assertEqual(2.5, result["smoothed-scalar"]["metrics"]["targetCandidate"])
        self.assertFalse(result["smoothed-scalar"]["metrics"]["headingQualified"])
        source = Path(result["smoothed-scalar"]["sourceReport"])
        self.assertEqual(str(source.with_name("summary.json")),
                         result["smoothed-scalar"]["summaryPath"])
        self.assertNotIn("summaryPath", self.scalar)  # Do not mutate saved source.
        self.scalar_query.assert_called_once_with("native-config", VM, GAME, cli.CONFIGS["lab2"], lab="lab2")
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_not_called()
        self.pose_query.assert_not_called()

    def test_scalar_summary_requires_real_absolute_samples_sibling(self):
        for source in ("relative/samples.json", str(Path.cwd() / "other.json")):
            with self.subTest(source=source):
                self.client.request.side_effect = [self.before, self.after]
                self.scalar["sourceReport"] = source
                with self.assertRaisesRegex(ValueError, "scalar-source-invalid"):
                    cli.read_once("lab2", "AMD-DESKTOP", fields=("smoothed-scalar",))

    def test_scalar_cannot_merge_wrong_owner_or_epoch(self):
        self.scalar["metrics"]["unitKey"] = "999"
        with self.assertRaisesRegex(ValueError, "unit-changed"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("position", "smoothed-scalar"))
        self.scalar["metrics"]["unitKey"] = KEY
        self.scalar["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("smoothed-scalar",))

    def test_all_sources_can_be_requested_explicitly(self):
        result = cli.read_once("lab2", "AMD-DESKTOP", fields=("actor-pose", "vitals", "position"))
        self.assertEqual(KEY, result["unitKey"])
        self.assertEqual({"position", "vitals", "actor-pose"},
                         set(result) & set(cli.NATIVE_FIELDS))
        self.xyz_query.assert_called_once()
        self.vitals_query.assert_called_once()
        self.pose_query.assert_called_once()

    def test_invalid_selection_stops_before_startup_or_queries(self):
        for fields in (None, "position", (), [], ("health",), (True,), ({},),
                       ("position", "position"), ("vitals", "position", "vitals")):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, "native-read-fields-"):
                cli.read_once("lab2", "AMD-DESKTOP", fields=fields)
        self.ensure.assert_not_called()
        self.xyz_query.assert_not_called()
        self.vitals_query.assert_not_called()

    def test_selection_has_canonical_order(self):
        self.assertEqual(("position", "vitals"), cli.selected_fields(["vitals", "position"]))
        self.assertEqual(("position", "vitals", "actor-pose"),
                         cli.selected_fields(["actor-pose", "vitals", "position"]))

    def test_scalar_selection_keeps_original_default_and_order(self):
        self.assertEqual(("position", "vitals"), cli.DEFAULT_FIELDS)
        self.assertEqual(("position", "actor-pose", "smoothed-scalar"),
                         cli.selected_fields(["smoothed-scalar", "position", "actor-pose"]))
        self.scalar_query.assert_not_called()

    def test_single_source_still_requires_its_pinned_identity(self):
        self.vitals["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("vitals",))
        self.xyz_query.assert_not_called()

    def test_single_source_still_requires_postflight_identity(self):
        self.after["guest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(ValueError, "postflight-changed"):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("position",))
        self.vitals_query.assert_not_called()

    def test_first_source_identity_failure_prevents_second_query(self):
        self.position["gameProcessStartUtcTicks"] += 1
        with self.assertRaisesRegex(ValueError, "source-identity-mismatch"):
            self.run_read()
        self.vitals_query.assert_not_called()

    def test_selected_query_failure_does_not_fall_back(self):
        self.vitals_query.side_effect = cli.Blocked("native-vitals-response-stale")
        with self.assertRaises(cli.Blocked):
            cli.read_once("lab2", "AMD-DESKTOP", fields=("vitals",))
        self.xyz_query.assert_not_called()

    def test_cli_default_and_explicit_field_selections(self):
        for args, expected in (([], cli.DEFAULT_FIELDS), (["--fields", "position"], ["position"]),
                               (["--fields", "vitals"], ["vitals"]),
                                (["--fields", "actor-pose"], ["actor-pose"]),
                                 (["--fields", "smoothed-scalar"], ["smoothed-scalar"])):
            output = io.StringIO()
            with self.subTest(args=args), patch.object(cli, "read_once", return_value={"status":"candidate-only"}) as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP", *args])
            self.assertEqual(0, code)
            read.assert_called_once_with("lab2", "AMD-DESKTOP", fields=expected)
            self.assertEqual("candidate-only", json.loads(output.getvalue())["status"])

    def test_cli_lab1_defaults_to_position_and_allows_selected_pose(self):
        for args, expected in (([], ("position",)),
                               (["--fields", "position", "actor-pose"], ["position", "actor-pose"])):
            output = io.StringIO()
            with self.subTest(args=args), patch.object(cli, "read_once", return_value={
                    "status": "candidate-only", "targetId": "lab1"}) as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab1", "--expected-host", "AMD-DESKTOP", *args])
            self.assertEqual(code, 0)
            read.assert_called_once_with("lab1", "AMD-DESKTOP", fields=expected)
            self.assertEqual(json.loads(output.getvalue())["targetId"], "lab1")

    def test_cli_lab1_denies_vitals_and_readout_comparison_before_startup(self):
        for args, reason in ((["--fields", "vitals"], "native-read-lab1-vitals-not-supported"),
                             (["--compare-readout-before", "missing.json"],
                              "native-read-lab1-comparison-not-supported")):
            output = io.StringIO()
            with self.subTest(args=args), patch.object(cli, "read_once") as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab1", "--expected-host", "AMD-DESKTOP", *args])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["reason"], reason)
            read.assert_not_called()
        self.ensure.assert_not_called()

    def test_cli_one_command_pose_turn_comparison_uses_new_saved_capture(self):
        before = Path("previous/summary.json")
        after = Path("fresh/summary.json")
        row = {"status": "candidate-only", "actor-pose": {"summaryPath": str(after)}}
        expected = {"status": "candidate-only", "matrices": {
            "actorMatrix": {"deltaDegreesCandidate": 2.0}}}
        output = io.StringIO()
        with patch.object(cli, "read_once", return_value=row) as read, \
                patch.object(cli, "compare_pose_turn", return_value=expected) as compare, \
                redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                             "--fields", "actor-pose", "--compare-pose-before", str(before)])
        self.assertEqual(0, code)
        read.assert_called_once_with("lab2", "AMD-DESKTOP", fields=["actor-pose"])
        compare.assert_called_once_with(before, after)
        result = json.loads(output.getvalue())
        self.assertEqual(expected, result["poseTurnComparison"])
        self.assertEqual(2.0, result["poseTurnComparison"]["matrices"]["actorMatrix"][
            "deltaDegreesCandidate"])
        self.assertFalse(self.ensure.called)  # The mocked read did not start a controller.

    def test_cli_pose_compare_requires_selected_pose_before_starting(self):
        output = io.StringIO()
        with patch.object(cli, "read_once") as read, \
                patch.object(cli, "compare_pose_turn") as compare, \
                redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                             "--compare-pose-before", "previous/summary.json"])
        self.assertEqual(2, code)
        self.assertEqual("native-read-pose-compare-requires-pose",
                         json.loads(output.getvalue())["reason"])
        read.assert_not_called()
        compare.assert_not_called()
        self.ensure.assert_not_called()

    def test_cli_pose_compare_identity_failure_is_blocked(self):
        output = io.StringIO()
        row = {"status": "candidate-only", "actor-pose": {"summaryPath": "fresh/summary.json"}}
        with patch.object(cli, "read_once", return_value=row), \
                patch.object(cli, "compare_pose_turn", side_effect=cli.Blocked(
                    "pose-turn-process-or-controller-changed")), redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                             "--fields", "actor-pose",
                             "--compare-pose-before", "previous/summary.json"])
        self.assertEqual(2, code)
        self.assertEqual("pose-turn-process-or-controller-changed",
                         json.loads(output.getvalue())["reason"])

    def test_cli_saves_complete_readout_without_shell_redirection(self):
        from tempfile import TemporaryDirectory
        row = {"schemaVersion": 1, "status": "candidate-only",
               "unitKey": KEY, "position": {"metrics": {"x": 1.25, "z": 2.5}}}
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "before.json"
            output = io.StringIO()
            with patch.object(cli, "read_once", return_value=row) as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                                 "--fields", "position", "--output-json", str(destination)])
            self.assertEqual(0, code)
            self.assertTrue(destination.is_file())
            self.assertEqual(row, json.loads(destination.read_text(encoding="utf-8")))
            self.assertEqual(row, json.loads(output.getvalue()))
            self.assertTrue(destination.read_bytes().endswith(b"\n"))
            read.assert_called_once_with("lab2", "AMD-DESKTOP", fields=["position"])
            self.ensure.assert_not_called()

    def test_cli_existing_output_is_preserved_before_native_startup(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "existing.json"
            destination.write_text('{"mine":true}', encoding="utf-8")
            output = io.StringIO()
            with patch.object(cli, "read_once") as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                                 "--output-json", str(destination)])
            self.assertEqual(2, code)
            self.assertEqual("native-read-output-unavailable",
                             json.loads(output.getvalue())["reason"])
            self.assertEqual('{"mine":true}', destination.read_text(encoding="utf-8"))
            read.assert_not_called()
            self.ensure.assert_not_called()

    def test_cli_failed_read_never_creates_output(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "unused.json"
            output = io.StringIO()
            with patch.object(cli, "read_once", side_effect=cli.Blocked("native-read-stale")), \
                    redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                                 "--output-json", str(destination)])
            self.assertEqual(2, code)
            self.assertFalse(destination.exists())
            self.assertEqual("native-read-stale", json.loads(output.getvalue())["reason"])

    def test_cli_second_capture_saves_readout_and_compares_real_baseline(self):
        from tempfile import TemporaryDirectory
        from tests.test_compare_native_player_reads import pair
        import hashlib
        baseline, fresh = pair(("position",))
        with TemporaryDirectory() as temporary:
            previous = Path(temporary) / "before.json"
            current = Path(temporary) / "after.json"
            previous.write_text(json.dumps(baseline, separators=(",", ":")) + "\n",
                                encoding="utf-8")
            output = io.StringIO()
            with patch.object(cli, "read_once", return_value=fresh) as read, redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                                 "--fields", "position", "--output-json", str(current),
                                 "--compare-readout-before", str(previous)])
            self.assertEqual(0, code)
            read.assert_called_once_with("lab2", "AMD-DESKTOP", fields=["position"])
            persisted = json.loads(current.read_text(encoding="utf-8"))
            self.assertEqual(fresh, persisted)
            self.assertNotIn("readoutComparison", persisted)
            response = json.loads(output.getvalue())
            comparison = response["readoutComparison"]
            self.assertAlmostEqual(75.96375653207352, comparison["comparison"][
                "position"]["xzTravelAngleDegreesCandidate"])
            self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest().upper(),
                             comparison["afterSourceSha256"])
            self.assertEqual(hashlib.sha256(previous.read_bytes()).hexdigest().upper(),
                             comparison["beforeSourceSha256"])
            self.assertFalse(self.ensure.called)

    def test_cli_baseline_requires_output_and_matching_fields_before_start(self):
        from tempfile import TemporaryDirectory
        from tests.test_compare_native_player_reads import pair
        previous, _ = pair(("position",))
        with TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "before.json"
            output_file = Path(temporary) / "after.json"
            baseline.write_text(json.dumps(previous), encoding="utf-8")
            for extra, expected in (
                    ([], "native-read-comparison-output-required"),
                    (["--output-json", str(output_file)], "native-read-baseline-fields-mismatch")):
                output = io.StringIO()
                with self.subTest(extra=extra), patch.object(cli, "read_once") as read, \
                        redirect_stdout(output):
                    code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                                     "--fields", "vitals", "--compare-readout-before",
                                     str(baseline), *extra])
                self.assertEqual(2, code)
                self.assertEqual(expected, json.loads(output.getvalue())["reason"])
                read.assert_not_called()
                self.ensure.assert_not_called()
            self.assertFalse(output_file.exists())

    def test_cli_duplicate_selection_is_blocked_without_dependency_start(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP",
                             "--fields", "vitals", "vitals"])
        self.assertEqual(2, code)
        self.assertEqual("native-read-fields-duplicated", json.loads(output.getvalue())["reason"])
        self.ensure.assert_not_called()

    def test_cli_preserves_safe_dependency_reason_without_retry(self):
        output = io.StringIO()
        error = cli.DependencyUnavailable("controller", "managed-owner-refused")
        with patch.object(cli, "read_once", side_effect=error) as read, redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP"])
        self.assertEqual(2, code)
        self.assertEqual("managed-owner-refused", json.loads(output.getvalue())["reason"])
        self.assertEqual(1, read.call_count)

    def test_cli_sanitizes_malformed_dependency_codes(self):
        for value in (None, 123, "private value with spaces", "x" * 101):
            error = cli.DependencyUnavailable("private-name", value)
            output = io.StringIO()
            with self.subTest(value=value), patch.object(cli, "read_once", side_effect=error), redirect_stdout(output):
                code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP"])
            self.assertEqual(2, code)
            self.assertEqual("native-read-unavailable", json.loads(output.getvalue())["reason"])
            self.assertNotIn("private", output.getvalue())

    def test_cli_sanitizes_unexpected_errors(self):
        output = io.StringIO()
        with patch.object(cli, "read_once", side_effect=RuntimeError("private transport value")), redirect_stdout(output):
            code = cli.main(["--lab", "lab2", "--expected-host", "AMD-DESKTOP"])
        self.assertEqual(2, code)
        self.assertEqual("native-read-unavailable", json.loads(output.getvalue())["reason"])
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
