"""Destination composition, using real receipt adoption and no game input."""
from copy import deepcopy
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import waypoint_destination_plan as bridge
from scripts.waypoint_candidate_adoption import validate_adopted_route
from tests.test_waypoint_navigation_candidate import sample, sign


class DestinationPlanTests(unittest.TestCase):
    def setUp(self):
        hostname = patch("scripts.waypoint_destination_plan.platform.node", return_value="AMD-DESKTOP")
        hostname.start()
        self.addCleanup(hostname.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.world = self.root / "world with spaces"
        (self.world / "tools").mkdir(parents=True)
        (self.world / "tools" / "query_destination.py").write_text("# test boundary\n")
        self.candidate = sample()
        self.patch = self.save("patch.json", {"patchId": self.candidate["patchId"],
                                              "coordinates": deepcopy(self.candidate["coordinates"])})
        self.build = self.save("navigation.json", {"buildId": self.candidate["planner"]["buildId"]})
        self.entry = {"id": "known-courtyard-end", "label": "Known courtyard end",
            "type": "route-anchor", "assetOriginXYZ": None, "approachXYZ": [2, 1, 2],
            "derivationState": "manual-unverified", "qualification": "Explicit historical corridor endpoint",
            "evidence": ["patchId:" + self.candidate["patchId"]], "arrivalTolerance": .3}
        self.catalog = self.save("destinations.json", {"schema": "riftworld.destination-catalog/1",
            "destinations": [self.entry]})
        self.player = "239816685251645959"
        self.context = {"version": 1, "zoneIdCandidate": "z1234567800000001",
            "rawZoneKey": 0x12345678, "source": "native-zone.json",
            "observedAtUtc": "2026-11-14T11:59:59Z", "playerKey": self.player,
            "target": {"hostName": "AMD-DESKTOP", "processId": 21672,
                "processStartUtcTicks": 639302305454629980, "executableSha256": "a" * 64}}
        self.zone = self.save("zone.json", {"ok": True, "data": {"context": self.context}})
        self.native = self.save("native.json", {"status": "arrived", "inputSent": True,
            "releaseSucceeded": True, "desktopInputsDown": [], "playerKey": self.player,
            "target": {"machineName": "AMD-DESKTOP", "processId": 21672,
                "processStartUtcTicks": 639302305454629980, "executableSha256": "a" * 64},
            "path": [{"x": x, "y": 1, "z": 2, "bearing": 90,
                "observedAtUtc": f"2026-11-14T12:00:0{x}Z"} for x in range(3)]})
        self.calls = []
        self.receipt_change = None

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def query(self, command, **kwargs):
        self.calls.append((command, kwargs))
        candidate_path = Path(command[command.index("--out") + 1])
        receipt_path = Path(command[command.index("--receipt") + 1])
        candidate_path.write_text(json.dumps(self.candidate), encoding="utf-8")
        receipt = {"schema": "riftworld.destination-query-receipt/1",
            "catalog": bridge._reference(self.catalog),
            "destination": {"entry": self.entry, "entryHash": bridge._identity(self.entry)},
            "patchId": self.candidate["patchId"], "buildId": self.candidate["planner"]["buildId"],
            "query": {"requestedStartXYZ": [0, 1, 2], "selectedApproachXYZ": [2, 1, 2], "exitCode": 0},
            "candidate": {**bridge._reference(candidate_path), "candidateId": self.candidate["candidateId"],
                "status": self.candidate["status"], "evidence": self.candidate["evidence"]},
            "qualification": {"destinationState": "manual-unverified",
                "destinationQualification": self.entry["qualification"],
                "destinationEvidence": self.entry["evidence"], "traversal": "unverified"}}
        if self.receipt_change:
            self.receipt_change(receipt)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, '{"status":"destination-query-published"}', "")

    def plan(self, *, native=True, **options):
        arguments = dict(catalog=self.catalog, destination=self.entry["id"], patch=self.patch,
            build=self.build, start=[0, 1, 2], output_directory=self.root / "plan",
            riftworld_root=self.world, riftworld_python=sys.executable, runner=self.query)
        if native:
            arguments.update(native_receipts=[self.native], native_context=self.zone,
                             native_start=0, native_end=2)
        arguments.update(options)
        return bridge.plan_destination(**arguments)

    def test_positive_query_receipt_and_native_adoption_preserve_default_no_input(self):
        result = self.plan()
        self.assertEqual("adoptable", result["status"])
        self.assertTrue(result["destinationCovered"])
        self.assertFalse(result["inputSent"])
        self.assertFalse(result["currentRouteChanged"])
        self.assertEqual(1, len(self.calls))
        route = json.loads(Path(result["adoptedRoute"]["path"]).read_text())
        validate_adopted_route(route, route["candidateAdoption"]["owner"], self.context, "forward")
        self.assertEqual(self.entry, route["candidateAdoption"]["destinationProvenance"]["destination"]["entry"])
        self.assertEqual(result, json.loads((self.root / "plan" / "plan.json").read_text()))

    def test_without_native_evidence_retains_useful_candidate_and_named_destination(self):
        result = self.plan(native=False)
        self.assertEqual("planned", result["status"])
        self.assertEqual("complete", result["stages"]["query"])
        self.assertEqual("native-evidence-required", result["stages"]["adoption"])
        self.assertNotIn("adoptedRoute", result)
        self.assertTrue(Path(result["candidate"]["path"]).is_file())

    def test_unknown_transform_preserves_plan_but_blocks_adoption(self):
        self.candidate["coordinates"]["transformToRr2Native"] = {"kind": "unknown", "qualification": "unqualified"}
        sign(self.candidate)
        result = self.plan()
        self.assertEqual("blocked", result["status"])
        self.assertTrue(any("identity-frame" in reason for reason in result["blockers"]))
        self.assertIn("destinationReceipt", result)
        self.assertNotIn("adoptedRoute", result)

    def test_partial_path_remains_inspectable_without_adoption(self):
        self.candidate["status"] = "partial"
        sign(self.candidate)
        result = self.plan()
        self.assertEqual("partial", result["stages"]["query"])
        self.assertEqual("blocked", result["status"])
        self.assertNotIn("adoptedRoute", result)

    def test_wrong_destination_receipt_cannot_be_adopted(self):
        self.receipt_change = lambda receipt: receipt["query"].update(selectedApproachXYZ=[20, 1, 2])
        result = self.plan()
        self.assertEqual("blocked", result["status"])
        self.assertIn("destination-publication-context-mismatch", result["blockers"])
        self.assertFalse((self.root / "plan" / "adopted-route.json").exists())

    def test_destination_qualification_cannot_be_promoted_by_receipt(self):
        self.receipt_change = lambda receipt: receipt["qualification"].update(traversal="verified")
        result = self.plan()
        self.assertEqual("blocked", result["status"])
        self.assertNotIn("adoptedRoute", result)

    def test_wrong_owner_fails_real_adopter(self):
        receipt = json.loads(self.native.read_text())
        receipt["playerKey"] = "999"
        self.native.write_text(json.dumps(receipt))
        result = self.plan()
        self.assertEqual("blocked", result["status"])
        self.assertIn("zone-context-identity-mismatch", result["blockers"])

    def test_discontinuous_native_evidence_cannot_qualify_a_new_path(self):
        receipt = json.loads(self.native.read_text())
        receipt["path"][1]["x"] = 10
        self.native.write_text(json.dumps(receipt))
        result = self.plan()
        self.assertEqual("blocked", result["status"])
        self.assertTrue(any("discontinuity" in reason for reason in result["blockers"]))
        self.assertNotIn("adoptedRoute", result)

    def test_scope_interior_is_not_destination_coverage(self):
        self.candidate["points"].insert(1, {"id": "middle", "xyz": [1, 1, 2], "flags": 0})
        sign(self.candidate)
        result = self.plan(candidate_start=1, native_start=1)
        self.assertEqual("adoptable", result["status"])
        self.assertFalse(result["destinationCovered"])

    def test_query_uses_safe_argv_and_exact_prepared_inputs(self):
        self.plan()
        command, options = self.calls[0]
        self.assertIsInstance(command, list)
        self.assertEqual(str(self.catalog), command[command.index("--catalog") + 1])
        self.assertEqual(self.world, options["cwd"])
        self.assertNotIn("shell", options)
        self.assertNotIn("--execute", command)

    def test_output_reuse_and_partial_evidence_refuse_before_query(self):
        self.plan()
        with self.assertRaises(FileExistsError):
            self.plan()
        with self.assertRaisesRegex(ValueError, "requires receipts"):
            self.plan(native=False, native_start=0)
        self.assertEqual(1, len(self.calls))

    def test_execution_requires_session_before_any_output_or_query(self):
        with self.assertRaisesRegex(ValueError, "exact session"):
            self.plan(execute=True)
        self.assertFalse(self.calls)
        self.assertFalse((self.root / "plan").exists())

    def executing_runner(self, *, stop_epochs=(0, 0), latched=False, route_hash=None,
                         release=True, position=None, failure=None, receipt_change=None,
                         target_host="AMD-DESKTOP"):
        status_count = 0

        def run(command, **options):
            nonlocal status_count
            if "query_destination.py" in command[1]:
                return self.query(command, **options)
            self.calls.append((command, options))
            if command[2] == "status":
                epoch = stop_epochs[min(status_count, len(stop_epochs) - 1)]
                status_count += 1
                data = {"target": {"machineName": target_host, "processId": 123,
                                   "processStartUtcTicks": 456, "executableSha256": "a" * 64},
                        "app": {"busy": False, "closing": False},
                        "controls": {"stopEpoch": epoch, "stopLatched": latched,
                                     "ownedActionActive": False, "inputReleaseFault": False}}
                response = {"ok": True, "sessionId": "owned", "data": data}
            else:
                route = Path(command[command.index("--file") + 1])
                receipt_value = {"status": "halted" if failure else "completed",
                    "failure": failure, "inputReleaseFault": not release,
                    "operation": "go", "movementEngine": "continuous", "requestId": "owned-request",
                    "externalRouteSha256": bridge._hash(route),
                    "calibrationBinding": {"runtimeIdentity": {"machine": "AMD-DESKTOP",
                        "processId": 123, "processStartUtcTicks": 456, "gameBuildSha256": "a" * 64,
                        "unitKey": self.player}},
                    "result": [{"status": "arrived", "inputSent": True, "pulses": 1,
                        "releaseSucceeded": release, "desktopInputsDown": [] if release else ["W"],
                        "position": position or {"x": 2, "y": 1, "z": 2}}]}
                if receipt_change:
                    receipt_change(receipt_value)
                receipt = self.save("executed.json", receipt_value)
                response = {"ok": not bool(failure), "sessionId": "owned",
                    "requestId": "owned-request",
                    "data": {"executedRouteSha256": route_hash or bridge._hash(route),
                             "receipt": str(receipt)}}
            return subprocess.CompletedProcess(command, 0 if response["ok"] else 1,
                                               json.dumps(response), "")
        return run

    def test_explicit_execution_dispatches_exact_route_and_stop_token(self):
        result = self.plan(execute=True, session="owned", runner=self.executing_runner())
        self.assertEqual("arrived-at-approach", result["status"])
        self.assertTrue(result["inputSent"])
        self.assertFalse(result["currentRouteChanged"])
        command = self.calls[-1][0]
        self.assertEqual(["route", "run"], command[2:4])
        self.assertEqual(result["adoptedRoute"]["sha256"], command[command.index("--route-sha256") + 1])
        self.assertEqual("0", command[command.index("--stop-epoch") + 1])
        self.assertIn("--execute", command)
        self.assertIn("receipt", result["execution"])
        self.assertEqual("not-attempted", result["arrival"]["serviceInteraction"])

    def test_stop_during_planning_cannot_be_erased_before_dispatch(self):
        result = self.plan(execute=True, session="owned",
                           runner=self.executing_runner(stop_epochs=(0, 123)))
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["inputSent"])
        self.assertTrue(any("stop-epoch-changed" in reason for reason in result["blockers"]))
        self.assertEqual(3, len(self.calls))
        self.assertNotIn("execution", result)

    def test_initial_stop_latch_prevents_query_and_dispatch(self):
        result = self.plan(execute=True, session="owned", runner=self.executing_runner(latched=True))
        self.assertEqual("blocked", result["status"])
        self.assertEqual(1, len(self.calls))
        self.assertNotIn("candidate", result)

    def test_other_host_session_is_refused_before_planning(self):
        result = self.plan(execute=True, session="owned",
                           runner=self.executing_runner(target_host="OTHER-HOST"))
        self.assertEqual("blocked", result["status"])
        self.assertEqual(1, len(self.calls))
        self.assertFalse(result["inputSent"])

    def test_route_success_outside_destination_is_not_arrival(self):
        result = self.plan(execute=True, session="owned",
                           runner=self.executing_runner(position={"x": 2.4, "y": 1, "z": 2}))
        self.assertEqual("route-complete-only", result["status"])
        self.assertEqual(.3, result["arrival"]["planarTolerance"])

    def test_execution_hash_mismatch_and_unreleased_receipt_never_become_arrival(self):
        result = self.plan(execute=True, session="owned", runner=self.executing_runner(route_hash="f" * 64))
        self.assertEqual("blocked", result["status"])
        self.assertNotIn("arrival", result)
        result = self.plan(output_directory=self.root / "release-plan", execute=True,
                           session="owned", runner=self.executing_runner(release=False))
        self.assertEqual("execution-unverified", result["status"])
        self.assertNotIn("arrival", result)

    def test_stopped_dispatch_preserves_terminal_receipt_and_destination(self):
        result = self.plan(execute=True, session="owned",
            runner=self.executing_runner(failure={"status": "stopped", "reason": "operator STOP"}))
        self.assertEqual("stopped", result["status"])
        self.assertTrue(result["inputSent"])
        self.assertIn("receipt", result["execution"])
        self.assertEqual(self.entry["id"], result["destinationId"])

    def test_wrong_route_or_runtime_receipt_cannot_establish_arrival(self):
        cases = [lambda receipt: receipt.update(externalRouteSha256="f" * 64),
                 lambda receipt: receipt["calibrationBinding"]["runtimeIdentity"].update(processId=999),
                 lambda receipt: receipt["calibrationBinding"]["runtimeIdentity"].update(unitKey="other"),
                 lambda receipt: receipt.update(requestId="other-request"),
                 lambda receipt: receipt.update(movementEngine="pulse")]
        for index, change in enumerate(cases):
            with self.subTest(case=index):
                result = self.plan(output_directory=self.root / f"wrong-receipt-{index}",
                    execute=True, session="owned", runner=self.executing_runner(receipt_change=change))
                self.assertEqual("execution-unverified", result["status"])
                self.assertNotIn("arrival", result)
                self.assertIn("execution-receipt-route-request-or-runtime-mismatch", result["blockers"])

    def current_runner(self, *, pose_changes=(), **options):
        other = self.executing_runner(**options)
        pose_index = 0

        def run(command, **kwargs):
            nonlocal pose_index
            if command[2:4] != ["pose", "refresh"]:
                return other(command, **kwargs)
            self.calls.append((command, kwargs))
            pose = {"status": "fresh", "sampleStatus": "fresh", "source": "existing-idle-reader",
                    "ageSeconds": .01, "freshForSeconds": 2,
                    "sampledAtUtc": datetime.now(timezone.utc).isoformat(),
                    "position": {"x": 0, "y": 1, "z": 2},
                    "target": {"machineName": "AMD-DESKTOP", "processId": 123,
                               "processStartUtcTicks": 456, "executableSha256": "a" * 64},
                    "runtimeIdentity": {"machine": "AMD-DESKTOP", "processId": 123,
                        "processStartUtcTicks": 456, "gameBuildSha256": "a" * 64, "unitKey": self.player}}
            if pose_index < len(pose_changes):
                pose_changes[pose_index](pose)
            pose_index += 1
            return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True,
                "sessionId": "owned", "requestId": f"pose-{pose_index}", "data": pose}), "")
        return run

    def current_plan(self, **options):
        return self.plan(start=None, from_current=True, session="owned", **options)

    def test_current_pose_supplies_start_with_bound_fresh_provenance(self):
        result = self.current_plan(runner=self.current_runner())
        self.assertEqual("adoptable", result["status"])
        self.assertEqual([0, 1, 2], result["requestedStartXYZ"])
        self.assertEqual("current-native", result["startSource"])
        observation = result["startObservation"]
        self.assertEqual(self.player, observation["runtimeIdentity"]["unitKey"])
        self.assertEqual("existing-idle-reader", observation["source"])
        self.assertEqual("identity", observation["transformToRr2Native"]["kind"])
        self.assertLessEqual(observation["ageSecondsAtValidation"], 2)
        self.assertIn("postPlanningObservation", result)
        self.assertFalse(result["inputSent"])
        query = next(command for command, _ in self.calls if "query_destination.py" in command[1])
        self.assertEqual("0,1,2", query[query.index("--from") + 1])
        self.assertFalse(any("--execute" in command for command, _ in self.calls))

    def test_plan_only_current_observation_preserves_latched_stop(self):
        result = self.current_plan(native=False, runner=self.current_runner(latched=True))
        self.assertEqual("planned", result["status"])
        self.assertTrue(result["observationAdmission"]["stopLatched"])
        self.assertFalse(result["inputSent"])

    def test_current_start_requires_session_and_exclusive_start_selection(self):
        with self.assertRaisesRegex(ValueError, "exact session"):
            self.plan(start=None, from_current=True)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.plan(from_current=True)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.plan(start=None)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            bridge.parser().parse_args(["--catalog", "x", "--patch", "x", "--build", "x",
                "--destination", "x", "--from", "1,2,3", "--from-current", "--out-dir", "x"])
        self.assertFalse(self.calls)

    def test_current_start_requires_explicit_patch_identity_transform(self):
        patch_document = json.loads(self.patch.read_text())
        patch_document["coordinates"]["transformToRr2Native"] = {"kind": "unknown", "qualification": "unqualified"}
        self.patch.write_text(json.dumps(patch_document))
        result = self.current_plan(runner=self.current_runner())
        self.assertEqual("blocked", result["status"])
        self.assertIn("current-native-start-requires-explicit-qualified-identity-transform", result["blockers"])
        self.assertEqual(1, len(self.calls))

    def test_stale_or_wrong_target_pose_is_rejected_before_query(self):
        changes = [lambda pose: pose.update(ageSeconds=3),
            lambda pose: pose.update(sampledAtUtc=(datetime.now(timezone.utc)-timedelta(seconds=4)).isoformat()),
            lambda pose: pose["runtimeIdentity"].update(processId=999),
            lambda pose: pose["target"].update(processId=999),
            lambda pose: pose.update(source=None)]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                before = len(self.calls)
                result = self.current_plan(output_directory=self.root / f"bad-pose-{index}",
                    runner=self.current_runner(pose_changes=[change]))
                self.assertEqual("blocked", result["status"])
                self.assertEqual(2, len(self.calls)-before)
                self.assertNotIn("candidate", result)

    def test_player_change_or_displacement_during_planning_is_not_adopted(self):
        for index, change in enumerate((lambda pose: pose["runtimeIdentity"].update(unitKey="other"),
                                         lambda pose: pose["position"].update(x=1))):
            result = self.current_plan(output_directory=self.root / f"changed-pose-{index}",
                runner=self.current_runner(pose_changes=[lambda pose: None, change]))
            self.assertEqual("blocked", result["status"])
            self.assertNotIn("adoptedRoute", result)
            self.assertIn("candidate", result)

    def test_same_process_other_player_cannot_reuse_native_corridor_evidence(self):
        wrong_player = lambda pose: pose["runtimeIdentity"].update(unitKey="other")
        result = self.current_plan(runner=self.current_runner(pose_changes=[wrong_player, wrong_player]))
        self.assertEqual("blocked", result["status"])
        self.assertIn("current-native-player-does-not-own-adopted-evidence", result["blockers"])
        self.assertNotIn("adoptedRoute", result)

    def test_stop_epoch_change_during_current_observation_blocks_planning(self):
        result = self.current_plan(runner=self.current_runner(stop_epochs=(0, 1)))
        self.assertEqual("blocked", result["status"])
        self.assertIn("session-or-stop-epoch-changed-during-pose-acquisition", result["blockers"])
        self.assertNotIn("candidate", result)

    def test_execute_from_current_still_refuses_initial_stop(self):
        result = self.current_plan(execute=True, runner=self.current_runner(latched=True))
        self.assertEqual("blocked", result["status"])
        self.assertEqual(1, len(self.calls))


class CurrentStartMailboxTests(unittest.TestCase):
    """Real hidden Tk/mailbox pose refresh with a fake adapter; no game access."""
    setUp = DestinationPlanTests.setUp
    save = DestinationPlanTests.save
    query = DestinationPlanTests.query
    plan = DestinationPlanTests.plan

    def mailbox(self):
        from tests import test_waypoint_cli_gui as harness_module
        from tests.test_waypoint_external_route import EXTERNAL_CHILD
        child = EXTERNAL_CHILD.replace("'unitKey': '1'}}", "'unitKey': '1', 'processId': 123, "
                                       "'processStartUtcTicks': '12345'}}")
        child = child.replace("connection.idle_read = lambda adapter, *args, **kw: (adapter, pose, False)",
            "connection.idle_read = lambda adapter, *args, **kw: (adapter, SimpleNamespace("
            "position=Position(), bearing=45.0, acquired=time.monotonic(), source='fake-native.json'), False)")
        harness = harness_module.GuiBridgeTests("runTest")
        with patch("tests.test_waypoint_cli_gui.CHILD", child):
            harness.setUp()
        self.addCleanup(harness.cleanup_child)
        # Native history belongs to the fake adapter's same-build player.
        self.context["playerKey"] = self.player = "1"
        self.zone.write_text(json.dumps({"ok": True, "data": {"context": self.context}}))
        native = json.loads(self.native.read_text())
        native["playerKey"] = self.player
        self.native.write_text(json.dumps(native))
        return harness

    def mailbox_runner(self, harness):
        from scripts import waypoint_cli_protocol as protocol
        from scripts import waypoints_cli
        original_discover = protocol.discover_sessions

        def run(command, **options):
            if "query_destination.py" in command[1]:
                return self.query(command, **options)
            stdout, stderr = io.StringIO(), io.StringIO()

            def discover(helper="waypoints", root=None):
                return original_discover(helper, harness.root / "sessions" if root is None else root)

            with patch.object(protocol, "discover_sessions", discover), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = waypoints_cli.main(command[2:])
            return subprocess.CompletedProcess(command, code, stdout.getvalue(), stderr.getvalue())
        return run

    def test_current_start_uses_actual_pose_refresh_without_changing_dirty_route(self):
        harness = self.mailbox()
        self.assertTrue(harness.call("route.add", {"name": "Preserved", "x": 10, "z": 20})["ok"])
        before = harness.call("route.list")["data"]
        result = self.plan(start=None, from_current=True, session=harness.session["sessionId"],
                           runner=self.mailbox_runner(harness))
        self.assertEqual("adoptable", result["status"], result["blockers"])
        self.assertEqual([0, 1, 2], result["requestedStartXYZ"])
        self.assertEqual("1", result["startObservation"]["runtimeIdentity"]["unitKey"])
        self.assertFalse(result["inputSent"])
        self.assertFalse((harness.root / "movement-called").exists())
        after = harness.call("route.list")["data"]
        for key in ("document", "revision", "dirty", "selected", "file"):
            self.assertEqual(before[key], after[key], key)

    def test_latched_stop_survives_actual_pose_refresh_and_plan_only(self):
        harness = self.mailbox()
        self.assertTrue(harness.call("stop")["ok"])
        before = harness.call("status")["data"]["controls"]
        self.assertTrue(before["stopLatched"])
        result = self.plan(start=None, from_current=True, session=harness.session["sessionId"],
                           runner=self.mailbox_runner(harness))
        self.assertEqual("adoptable", result["status"], result["blockers"])
        after = harness.call("status")["data"]["controls"]
        self.assertTrue(after["stopLatched"])
        self.assertEqual(before["stopEpoch"], after["stopEpoch"])
        self.assertFalse(result["inputSent"])
        self.assertFalse((harness.root / "movement-called").exists())


if __name__ == "__main__":
    unittest.main()
