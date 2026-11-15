"""Offline-only checkpoint consistency tests; no physical RIFT access."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import audit_hunt_mission_progress as cli
from scripts import hunt_mission
from scripts.waypoint_progress import RouteProgress


TARGET = "u800000020502E041"
SAFE = {"x": 1.0, "y": 5.0, "z": 2.0}
IDENTITY = {"machine": "AMD-DESKTOP", "gameBuildSha256": "a" * 64, "unitKey": "1"}


class HuntMissionAuditTests(unittest.TestCase):
    def setUp(self):
        self.mission = {
            "name": "Offline audit",
            "binding": {"routeSha256": "b" * 64, "profileSha256": "c" * 64},
            "safeAnchor": {**SAFE, "planarTolerance": .5, "heightTolerance": .75},
            "hunt": {"expectedTargetId": TARGET, "maximumKills": 2},
        }
        self.route = {"waypoints": [["Safe", 1, 2], ["Hunt", 4, 6]]}
        self.document = hunt_mission._return_document(
            [(1.0, 5.0, 2.0), (2.0, 5.0, 3.3),
             (3.0, 5.0, 4.6), (4.0, 5.0, 6.0)], IDENTITY)
        self.progress = {
            "schema": hunt_mission.CHECKPOINT_SCHEMA,
            "mission": self.mission["name"],
            "missionBinding": deepcopy(self.mission["binding"]),
            "stage": "complete", "completed": True,
            "outboundNextIndex": 2,
            "returnDocument": self.document,
            "returnNextIndex": len(self.document["waypoints"]),
            "finalPosition": deepcopy(SAFE),
            "encounter": {"status": "blocked", "reason": "kill-credit-unverified",
                          "selectedTargetId": TARGET, "releaseSucceeded": True,
                          "desktopInputsDown": [], "inputSent": False},
            "killProofs": [], "killCount": 0,
        }

    def check(self, data=None):
        return cli.audit(self.mission, self.route, self.progress if data is None else data)

    def test_normal_return_is_consistent_not_live_qualified(self):
        result = self.check()
        self.assertEqual("consistent", result["status"])
        self.assertEqual("return", result["mode"])
        self.assertEqual("checkpoint-only-not-live-qualified", result["scope"])

    def test_safe_retreat_is_separate_from_normal_return(self):
        p = deepcopy(self.progress)
        p["encounter"]["reason"] = "selected-encounter-unsafe"
        p.pop("returnNextIndex")
        p["safeRetreat"] = {"safeRetreat": True, "status": "arrived",
                            "releaseSucceeded": True, "desktopInputsDown": [],
                            "position": deepcopy(SAFE)}
        self.assertEqual("safe-retreat", self.check(p)["mode"])
        p["safeRetreat"]["status"] = "blocked"
        with self.assertRaisesRegex(hunt_mission.MissionError, "safe-retreat"):
            self.check(p)
        p["safeRetreat"]["status"] = "arrived"
        p["safeRetreat"]["releaseSucceeded"] = False
        with self.assertRaisesRegex(hunt_mission.MissionError, "safe-retreat"):
            self.check(p)

    def test_qualified_exact_target_kill_count(self):
        p = deepcopy(self.progress)
        p["encounter"] = {"status": "completed", "selectedTargetId": TARGET,
                           "releaseSucceeded": True, "desktopInputsDown": []}
        p["killCount"] = 1
        p["killProofs"] = [{"qualified": True, "kind": "player-kill-confirmed",
                             "targetId": TARGET, "sequence": 3}]
        p["encounter"]["killProof"] = deepcopy(p["killProofs"][0])
        self.assertEqual(1, self.check(p)["killCount"])
        p["killProofs"][0]["targetId"] = "u0000000000000003"
        with self.assertRaisesRegex(hunt_mission.MissionError, "kill proof"):
            self.check(p)
        p["killProofs"][0]["targetId"] = TARGET
        p["killProofs"][0]["sequence"] = 4
        with self.assertRaisesRegex(hunt_mission.MissionError, "checkpoint disagree"):
            self.check(p)
        p["killCount"] = 2
        p["killProofs"] = [deepcopy(p["encounter"]["killProof"])] * 2
        with self.assertRaisesRegex(hunt_mission.MissionError, "proof list disagree"):
            self.check(p)

    def test_qualified_kill_requires_same_selected_target(self):
        p = deepcopy(self.progress)
        p["encounter"] = {"status": "completed", "selectedTargetId": "u0000000000000003",
                          "inputSent": False, "releaseSucceeded": True,
                          "desktopInputsDown": []}
        p["killCount"] = 1
        p["killProofs"] = [{"qualified": True, "kind": "player-kill-confirmed",
                            "targetId": TARGET, "sequence": 3}]
        p["encounter"]["killProof"] = deepcopy(p["killProofs"][0])
        with self.assertRaisesRegex(hunt_mission.MissionError, "selected encounter target"):
            self.check(p)
        p["encounter"]["selectedTargetId"] = None
        with self.assertRaisesRegex(hunt_mission.MissionError, "selected encounter target"):
            self.check(p)
        p["encounter"]["selectedTargetId"] = TARGET
        self.assertEqual(1, self.check(p)["killCount"])

    def test_unmatched_target_without_input_can_still_return_without_kill(self):
        p = deepcopy(self.progress)
        p["encounter"]["selectedTargetId"] = "u0000000000000003"
        self.assertEqual(0, self.check(p)["killCount"])

    def test_incomplete_or_forged_completion_is_blocked(self):
        cases = [
            ("completed", False, "not complete"),
            ("outboundNextIndex", 1, "outbound"),
            ("returnNextIndex", 1, "return progress"),
            ("killCount", 1, "proof list"),
            ("finalPosition", {"x": 42, "y": 5, "z": 42}, "safe anchor"),
        ]
        for field, value, expected in cases:
            with self.subTest(field=field):
                p = deepcopy(self.progress)
                p[field] = value
                with self.assertRaisesRegex(hunt_mission.MissionError, expected):
                    self.check(p)

    def test_mismatched_mission_and_corridor_are_blocked(self):
        cases = [
            (("mission",), "wrong", "mission binding"),
            (("returnDocument", "provenance", "retainedPoints"), 99, "count"),
            (("returnDocument", "provenance", "runtimeIdentity", "machine"),
             "OTHER-HOST", "AMD-DESKTOP"),
            (("returnDocument", "waypoints", 0, 1), 9000, "retreat"),
        ]
        for keys, value, expected in cases:
            with self.subTest(keys=keys):
                p = deepcopy(self.progress)
                node = p
                for key in keys[:-1]:
                    node = node[key]
                node[keys[-1]] = value
                with self.assertRaisesRegex(hunt_mission.MissionError, expected):
                    self.check(p)

    def test_bad_target_or_held_input_blocks_consistency(self):
        for update, expected in [
            ({"selectedTargetId": "u0000000000000003", "inputSent": True},
             "selection"),
            ({"releaseSucceeded": False}, "release"),
            ({"desktopInputsDown": ["w"]}, "release"),
            ({"allInputsReleased": False}, "release"),
        ]:
            with self.subTest(update=update):
                p = deepcopy(self.progress)
                p["encounter"].update(update)
                with self.assertRaisesRegex(hunt_mission.MissionError, expected):
                    self.check(p)

    def test_blocked_unsafe_encounter_cannot_claim_normal_return(self):
        p = deepcopy(self.progress)
        p["encounter"]["reason"] = "encounter-deadline"
        with self.assertRaisesRegex(hunt_mission.MissionError, "normal return"):
            self.check(p)

    def route_receipt(self, document):
        cursor = RouteProgress(document, "forward", IDENTITY)
        first = cursor.ordered_points[0]
        start = {"x": first[1], "z": first[2]}
        if cursor.heights is not None:
            start["y"] = cursor.heights[0]
        cursor.begin(start)
        for index, goal in enumerate(cursor.ordered_points):
            cursor.confirm_arrival(index, goal)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            cursor.save(path)
            return json.loads(path.read_text(encoding="utf-8"))

    def test_strict_route_progress_cross_checks_both_sidecars(self):
        outbound = self.route_receipt(self.route)
        returned = self.route_receipt(self.document)
        result = cli.audit(self.mission, self.route, self.progress,
                           outbound_receipt=outbound, return_receipt=returned,
                           require_route_progress=True)
        self.assertEqual("consistent", result["status"])
        self.assertEqual("checkpoint-and-route-progress-not-live-qualified",
                         result["scope"])
        for side, value, reason in [
            ("outbound", None, "outbound route progress receipt is missing"),
            ("return", None, "return route progress receipt is missing"),
            ("outbound", {**outbound, "nextIndex": 1}, "outbound route progress receipt is incomplete"),
            ("return", {**returned, "routeHash": "a" * 64}, "return route progress receipt is invalid"),
            ("return", {**returned, "identity": {**returned["identity"], "unitKey": "other"}},
             "return route progress receipt is invalid"),
        ]:
            with self.subTest(side=side, reason=reason):
                arguments = {"outbound_receipt": outbound, "return_receipt": returned}
                arguments[side + "_receipt"] = value
                with self.assertRaisesRegex(hunt_mission.MissionError, reason):
                    cli.audit(self.mission, self.route, self.progress,
                              require_route_progress=True, **arguments)

    def test_safe_retreat_needs_outbound_sidecar_not_normal_return(self):
        p = deepcopy(self.progress)
        p["encounter"]["reason"] = "selected-encounter-unsafe"
        p.pop("returnNextIndex")
        p["safeRetreat"] = {"safeRetreat": True, "status": "arrived",
                            "releaseSucceeded": True, "desktopInputsDown": [],
                            "position": deepcopy(SAFE)}
        result = cli.audit(self.mission, self.route, p,
                           outbound_receipt=self.route_receipt(self.route),
                           require_route_progress=True)
        self.assertEqual("safe-retreat", result["mode"])
        with self.assertRaisesRegex(hunt_mission.MissionError, "outbound route progress receipt is missing"):
            cli.audit(self.mission, self.route, p, require_route_progress=True)

    def test_strict_cli_reads_sibling_sidecars_and_refuses_missing(self):
        outbound = self.route_receipt(self.route)
        returned = self.route_receipt(self.document)
        def loader(path, *_):
            name = path.name
            if name == "run.json":
                return self.progress
            if name == "run.outbound.json":
                return outbound
            if name == "run.return.json":
                return returned
            raise hunt_mission.MissionError("unexpected checkpoint")
        argv = ["--mission", "unused", "--route", "unused",
                "--profile", "unused", "--checkpoint", "run.json",
                "--require-route-progress"]
        with (patch.object(cli.mission_cli, "load_definition",
                           return_value=(self.mission, self.route, {})),
              patch.object(cli.mission_cli, "_load_json", side_effect=loader)):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, cli.main(argv))
            self.assertEqual("consistent", json.loads(output.getvalue())["status"])
            returned = None
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(2, cli.main(argv))
            self.assertEqual("blocked", json.loads(output.getvalue())["status"])

    def test_cli_returns_json_and_exit_code_without_process_access(self):
        with (patch.object(cli.mission_cli, "load_definition",
                           return_value=(self.mission, self.route, {})),
              patch.object(cli.mission_cli, "_load_json", return_value=self.progress)):
            output = StringIO()
            with redirect_stdout(output):
                code = cli.main(["--mission", "unused", "--route", "unused",
                                 "--profile", "unused", "--checkpoint", "unused"])
            self.assertEqual(0, code)
            self.assertEqual("consistent", json.loads(output.getvalue())["status"])
            self.progress["completed"] = False
            output = StringIO()
            with redirect_stdout(output):
                code = cli.main(["--mission", "unused", "--route", "unused",
                                 "--profile", "unused", "--checkpoint", "unused"])
            self.assertEqual(2, code)
            self.assertEqual("blocked", json.loads(output.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
