import json
import tempfile
import unittest
from pathlib import Path

from scripts import summarize_survival_acceptance as summary


class SurvivalAcceptanceSummaryTests(unittest.TestCase):
    def sample(self, clock, self_hp, target_hp, *, state="fight", checkpoint=2,
               incoming=None, outgoing=None, stop=False):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        snapshot = {"sessionId": "a" * 32, "epoch": 3, "sequence": int(clock * 10),
                    "frameTime": clock, "playerId": player_id, "targetId": target_id,
                    "player": {"health": self_hp, "healthMax": 100},
                    "target": {"health": target_hp, "healthMax": 100},
                    "lastIncoming": incoming, "lastPositiveEvent": outgoing}
        return {"type": "telemetry", "wallTime": clock,
                "playerId": player_id, "targetId": target_id,
                "epoch": 3, "sequence": int(clock * 10), "frameTime": clock,
                "native": {}, "snapshot": snapshot,
                "telemetry": {"player": {"healthPct": self_hp, "inCombat": True,
                                           "dead": False},
                              "encounter": {"incomingDamageObserved": incoming is not None}},
                "policy": {"state": state, "checkpoint": checkpoint,
                           "pendingLeg": ["finish", 1, 2]}, "stopSet": stop}

    def test_correlates_exact_incoming_and_outgoing_damage_and_invariants(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id, "selectedTargetId": target_id, "abilityName": "Claw"}
        outgoing = {"sequence": 8, "clock": 10.5, "kind": "damage", "damage": 20,
                    "caster": player_id, "target": target_id, "selectedTargetId": target_id, "abilityName": "Strike"}
        telemetry = [self.sample(10, 100, 100),
                     self.sample(11, 88, 80, incoming=incoming, outgoing=outgoing),
                     self.sample(12, 88, 80, state="retreat"),
                     self.sample(13, 88, 80, state="recover"),
                     self.sample(14, 100, 80, state="rejoin"),
                     self.sample(15, 100, 80, state="travel")]
        route = [{"status": "encounter-interrupted", "releaseSucceeded": True},
                 {"status": "arrived", "releaseSucceeded": True,
                  "desktopInputsDown": [], "nextIndex": 3}]

        value = summary.summarize(route, telemetry)

        self.assertTrue(value["acceptance"]["incomingDamage"])
        self.assertTrue(value["acceptance"]["outgoingDamage"])
        self.assertEqual("preserved", value["acceptance"]["checkpointInvariant"])
        self.assertEqual("preserved", value["acceptance"]["recoveryResumeInvariant"])
        self.assertEqual("clear-throughout", value["acceptance"]["stopInvariant"])
        self.assertTrue(value["route"]["allRetainedReleasesVerified"])

    def test_missing_or_wrong_attribution_is_honestly_unavailable(self):
        telemetry = [self.sample(10, 100, 100), self.sample(11, 90, 80)]
        route = [{"status": "arrived", "releaseSucceeded": True,
                  "desktopInputsDown": []}]
        value = summary.summarize(route, telemetry)
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["acceptance"]["outgoingDamage"])
        self.assertEqual("unavailable", value["telemetry"]["incomingCorrelation"]["status"])

    def test_damage_attribution_rejects_non_damage_and_missing_selected_target(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.4, "kind": "heal", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        route = [{"status": "encounter-interrupted", "releaseSucceeded": True}]
        for replacement in ({"kind": "heal"},
                            {"kind": "damage", "selectedTargetId": None}):
            with self.subTest(replacement=replacement):
                incoming = {**event, **replacement}
                value = summary.summarize(route, [self.sample(10, 100, 100),
                                                  self.sample(11, 88, 100, incoming=incoming)])
                self.assertFalse(value["acceptance"]["incomingDamage"])
                self.assertEqual("unavailable",
                                 value["telemetry"]["incomingCorrelation"]["status"])

    def test_late_event_cannot_be_used_to_explain_earlier_health_loss(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 12.5, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        value = summary.summarize([{"status": "encounter-interrupted"}],
                                  [self.sample(10, 100, 100),
                                   self.sample(11, 88, 100, incoming=event)])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertEqual("observed-unpaired",
                         value["telemetry"]["incomingCorrelation"]["status"])

    def test_changed_selected_target_does_not_validate_old_target_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        incoming = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                    "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        after = self.sample(11, 88, 100, incoming=incoming)
        after["snapshot"]["targetId"] = "u0000000000000003"
        after["targetId"] = "u0000000000000003"
        value = summary.summarize([{"status": "encounter-interrupted"}],
                                  [self.sample(10, 100, 100), after])
        self.assertFalse(value["acceptance"]["incomingDamage"])

    def test_target_switch_between_samples_blocks_prior_event_attribution(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        before = self.sample(10, 100, 100, incoming=event)
        after = self.sample(11, 88, 100)
        after["snapshot"]["targetId"] = "u0000000000000003"
        after["targetId"] = "u0000000000000003"
        value = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["telemetry"]["selfHealthDrops"][0]["attributionEligible"])
        self.assertEqual("observed-unpaired",
                         value["telemetry"]["incomingCorrelation"]["status"])

    def test_replayed_frame_sequence_cannot_qualify_damage(self):
        player_id, target_id = "u0000000000000001", "u0000000000000002"
        event = {"sequence": 7, "clock": 10.4, "kind": "damage", "damage": 12,
                 "caster": target_id, "target": player_id, "selectedTargetId": target_id}
        before = self.sample(10, 100, 100)
        after = self.sample(11, 88, 100, incoming=event)
        after["snapshot"]["sequence"] = before["snapshot"]["sequence"]
        value = summary.summarize([{"status": "encounter-interrupted"}], [before, after])
        self.assertFalse(value["acceptance"]["incomingDamage"])
        self.assertFalse(value["telemetry"]["selfHealthDrops"][0]["attributionEligible"])

    def test_route_only_never_claims_damage_and_cli_writes_new_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route = root / "route.jsonl"
            output = root / "summary.json"
            route.write_text(json.dumps({"status": "arrived", "releaseSucceeded": True,
                                         "desktopInputsDown": [], "nextIndex": 2}) + "\n",
                             encoding="utf-8")
            self.assertEqual(0, summary.main(["--route", str(route), "--output", str(output)]))
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("unavailable", value["telemetry"]["status"])
            self.assertFalse(value["acceptance"]["incomingDamage"])
            with self.assertRaisesRegex(summary.AcceptanceError, "output-exists"):
                summary.main(["--route", str(route), "--output", str(output)])


if __name__ == "__main__":
    unittest.main()
