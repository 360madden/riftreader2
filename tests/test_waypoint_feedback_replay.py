"""Synthetic historical replay only; no native adapters or input."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from scripts.waypoint_progress import RouteProgress
from scripts.waypoint_feedback_replay import assess_retained_leg, replay, main


def fixture(moving=False):
    route = {"waypoints": [["start", 0, 0], ["end", 4, 0]], "heights": [10, 10]}
    identity = {"machine": "fixture", "gameBuildSha256": "a"*64, "unitKey": "7",
                "processId": 20, "processStartUtcTicks": "123"}
    cursor = RouteProgress(route, identity=identity)
    cursor.begin({"x": 0, "y": 10, "z": 0})
    cursor.confirm_arrival(0, cursor.ordered_points[0])
    checkpoint = {"version": 1, "route": route, "routeHash": cursor.route_hash,
                  "direction": "forward", "identity": cursor.identity,
                  "nextIndex": 1, "start": cursor.start}
    run = {"externalRouteSha256": "b"*64, "operation": "go", "movementEngine": "continuous",
           "inputReleaseFault": False, "requestId": "fixture-request",
           "status": "halted", "failure": {"status": "halted"},
           "calibrationBinding": {"runtimeIdentity": identity}}
    stamp = lambda seconds: "2026-11-27T10:00:%06.3f+00:00" % seconds
    path = [{"x": i*.2 if moving else 0, "y": 10, "z": 0, "bearing": 90,
             "observedAtUtc": stamp(.2+i*.5)} for i in range(4)]
    native = {"version": 1, "kind": "native-continuous-move", "status": "halted",
              "reason": "progress-stalled", "releaseSucceeded": True, "desktopInputsDown": [],
              "inputSent": True, "pathTruncated": False, "passedWaypoints": [],
              "survivalInterrupt": False, "survivalMode": "disabled",
              "target": {"machineName": "fixture", "executableSha256": "a"*64,
                         "processId": 20, "processStartUtcTicks": "123"},
              "playerKey": "7", "goal": {"x": 4, "y": 10, "z": 0},
              "path": path, "readCount": 4,
              "position": {a: path[-1][a] for a in "xyz"},
              "keySendEvents": [
                  {"key": "W", "phase": "key-down", "inserted": True,
                   "callStartedAtUtc": stamp(0), "callCompletedAtUtc": stamp(.1)},
                  {"key": "W", "phase": "key-up", "inserted": True,
                   "callStartedAtUtc": stamp(1.8), "callCompletedAtUtc": stamp(1.9)}]}
    return route, checkpoint, run, native


class ReplayTests(unittest.TestCase):
    def assess(self, data):
        return assess_retained_leg(*data, route_sha256="b"*64)

    def test_stall_and_forward_are_candidates_without_mutation(self):
        for moving, status in [(False, "stalled-candidate"), (True, "forward-progress-candidate")]:
            data = fixture(moving)
            before = copy.deepcopy(data)
            result = self.assess(data)
            self.assertEqual(status, result["status"])
            self.assertEqual(not moving, result["replanSuggested"])
            self.assertFalse(result["inputSent"])
            self.assertTrue(result["candidateOnly"])
            self.assertFalse(result["automaticRetry"])
            self.assertTrue(result["requiresExplicitNewRun"])
            self.assertFalse(result["currentFreshnessVerified"])
            self.assertEqual(before, data)

    def test_qualification_and_provenance_refusals(self):
        cases = [
            (1, "nextIndex", 0), (1, "nextIndex", 2),
            (2, "externalRouteSha256", "c"*64), (2, "inputReleaseFault", True),
            (2, "status", "stopped"), (2, "movementEngine", "survival"),
            (3, "pathTruncated", True), (3, "readCount", 5),
            (3, "survivalInterrupt", True), (3, "survivalMode", "retreat"),
            (3, "controlPauseVersion", 1),
            (3, "releaseSucceeded", False), (3, "desktopInputsDown", ["W"]),
            (3, "passedWaypoints", [{"index": 0}]),
            (3, "controlPauseReceipts", [{}]), (3, "reason", "survival-combat"),
            (3, "playerKey", "8"), (3, "inputSent", False),
        ]
        for index, key, value in cases:
            with self.subTest(key=key, value=value):
                data = fixture()
                data[index][key] = value
                with self.assertRaises(ValueError):
                    self.assess(data)

    def test_process_goal_and_route_scope_refusals(self):
        for key, value in [("processId", 21), ("processStartUtcTicks", "124"),
                           ("machineName", "other"), ("executableSha256", "c"*64)]:
            data = fixture()
            data[3]["target"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assess(data)
        data = fixture()
        data[3]["goal"]["x"] = 3
        with self.assertRaises(ValueError):
            self.assess(data)
        data = fixture()
        data[0]["waypoints"].append(["extra", 5, 0])
        data[0]["heights"].append(10)
        with self.assertRaises(ValueError):
            self.assess(data)

    def test_path_and_input_boundaries_refuse(self):
        mutators = [
            lambda n: n["path"][1].update(observedAtUtc=n["path"][0]["observedAtUtc"]),
            lambda n: n["path"][1].update(observedAtUtc="2026-11-27T10:00:00.700"),
            lambda n: n["path"][1].update(y=None),
            lambda n: n["path"][1].update(x=float("nan")),
            lambda n: n["position"].update(x=9),
            lambda n: n["keySendEvents"][0].update(key="A"),
            lambda n: n["keySendEvents"][0].update(inserted=False),
            lambda n: n["keySendEvents"].append(dict(n["keySendEvents"][0])),
            lambda n: n["keySendEvents"][1].update(callStartedAtUtc="2026-11-27T10:00:00.100Z"),
            lambda n: n["keySendEvents"][1].update(callStartedAtUtc="2026-11-27T10:00:00.600Z"),
        ]
        for mutate in mutators:
            data = fixture()
            mutate(data[3])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.assess(data)

    def test_playback_and_malformed_external_hash_refuse_cleanly(self):
        for operation in ("play", "resume"):
            data = fixture()
            data[2].update(operation=operation, externalRouteSha256=None, direction="forward")
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "go-receipt-required"):
                self.assess(data)
        for value in (None, True, 42, [], {}, "", "x"*64):
            data = fixture()
            data[2]["externalRouteSha256"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.assess(data)

    def test_identity_types_reject_even_when_both_sources_match(self):
        for key, values in (
                ("processId", (True, False, 0, -1, "20", 20.0)),
                ("processStartUtcTicks", (True, False, 0, -1, "-1", "abc", "1.0", 1.0, "")),
                ("gameBuildSha256", ("x"*64, "", None, True))):
            for value in values:
                data = fixture()
                data[2]["calibrationBinding"]["runtimeIdentity"][key] = value
                target_key = "executableSha256" if key == "gameBuildSha256" else key
                data[3]["target"][target_key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.assess(data)
        data = fixture()
        data[2]["calibrationBinding"]["runtimeIdentity"]["processStartUtcTicks"] = 123
        self.assertEqual("stalled-candidate", self.assess(data)["status"])

    def test_malformed_documents_and_keys_raise_value_error(self):
        for index in range(4):
            for value in (None, [], 1, "bad"):
                data = list(fixture())
                data[index] = value
                with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                    self.assess(data)
        data = fixture()
        data[2]["calibrationBinding"] = []
        with self.assertRaises(ValueError):
            self.assess(data)
        for value in (None, True, [], 1):
            data = fixture()
            data[3]["keySendEvents"][0]["key"] = value
            with self.subTest(key=value), self.assertRaises(ValueError):
                self.assess(data)

    def test_sparse_window_is_insufficient_not_stall(self):
        data = fixture()
        data[3]["path"][2]["observedAtUtc"] = "2026-11-27T10:00:01.500Z"
        data[3]["path"][3]["observedAtUtc"] = "2026-11-27T10:00:01.700Z"
        self.assertEqual("insufficient-feedback", self.assess(data)["status"])

    def test_pinned_replay_and_cli_refuse_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {key: Path(tmp)/ (key+".json") for key in
                     ("route", "checkpoint", "run_receipt", "native_receipt")}
            data = fixture()
            data[2]["inputReceiptPath"] = str(paths["native_receipt"])
            args = {}
            for key, doc in zip(paths, data):
                paths[key].write_text(json.dumps(doc)+"\n", encoding="utf-8")
                args[key] = paths[key]
                args[key+"_sha256"] = hashlib.sha256(paths[key].read_bytes()).hexdigest()
            # Bind the run to the actual route bytes, then update its own pin.
            data[2]["externalRouteSha256"] = args["route_sha256"]
            paths["run_receipt"].write_text(json.dumps(data[2]), encoding="utf-8")
            args["run_receipt_sha256"] = hashlib.sha256(paths["run_receipt"].read_bytes()).hexdigest()
            original = {p: p.read_bytes() for p in paths.values()}
            result = replay(**args)
            self.assertEqual("stalled-candidate", result["status"])
            self.assertEqual({"recordedPath": str(paths["native_receipt"]),
                              "mode": "original-path"}, result["nativeReceiptReference"])
            cli = [item for key, value in args.items() for item in ("--"+key.replace("_", "-"), str(value))]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(cli))
            self.assertEqual("stalled-candidate", json.loads(output.getvalue())["status"])
            self.assertEqual(original, {p: p.read_bytes() for p in paths.values()})
            paths["native_receipt"].write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash-mismatch"):
                replay(**args)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(2, main(cli))


    def test_relocated_receipt_requires_exact_original_path_and_unchanged_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {key: Path(tmp) / (key + ".json") for key in
                     ("route", "checkpoint", "run_receipt", "native_receipt")}
            data = fixture()
            args = {}
            for key, doc in zip(paths, data):
                paths[key].write_text(json.dumps(doc), encoding="utf-8")
                args[key] = paths[key]
                args[key + "_sha256"] = hashlib.sha256(paths[key].read_bytes()).hexdigest()
            data[2]["externalRouteSha256"] = args["route_sha256"]

            def pin_run(recorded):
                data[2]["inputReceiptPath"] = recorded
                paths["run_receipt"].write_text(json.dumps(data[2]), encoding="utf-8")
                args["run_receipt_sha256"] = hashlib.sha256(paths["run_receipt"].read_bytes()).hexdigest()

            # Original paths from either operating system need no old filesystem.
            for recorded in (r"C:\RR2\retained\input.jsonl", "/rr2-archive/input.jsonl"):
                with self.subTest(recorded=recorded):
                    pin_run(recorded)
                    before = {p: p.read_bytes() for p in paths.values()}
                    with self.assertRaisesRegex(ValueError, "native-receipt-reference-mismatch"):
                        replay(**args)
                    with self.assertRaisesRegex(ValueError, "relocation-reference-mismatch"):
                        replay(**args, recorded_native_receipt_path=recorded + ".other")
                    result = replay(**args, recorded_native_receipt_path=recorded)
                    self.assertEqual("stalled-candidate", result["status"])
                    self.assertEqual({"recordedPath": recorded, "mode": "explicit-relocation"},
                                     result["nativeReceiptReference"])
                    self.assertEqual(str(paths["native_receipt"].resolve()),
                                     result["sources"]["nativeReceipt"]["path"])
                    self.assertFalse(result["currentFreshnessVerified"])
                    self.assertFalse(result["inputSent"])
                    cli = [item for key, value in args.items()
                           for item in ("--" + key.replace("_", "-"), str(value))]
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(0, main(cli + ["--recorded-native-receipt-path", recorded]))
                    self.assertEqual(result["nativeReceiptReference"],
                                     json.loads(output.getvalue())["nativeReceiptReference"])
                    self.assertEqual(before, {p: p.read_bytes() for p in paths.values()})

            pin_run("relative/input.jsonl")
            with self.assertRaisesRegex(ValueError, "relocation-reference-mismatch"):
                replay(**args, recorded_native_receipt_path="relative/input.jsonl")
            recorded = r"C:\RR2\retained\input.jsonl"
            pin_run(recorded)
            paths["native_receipt"].write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source-hash-mismatch"):
                replay(**args, recorded_native_receipt_path=recorded)


if __name__ == "__main__":
    unittest.main()
