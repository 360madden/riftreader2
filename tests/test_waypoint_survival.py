import unittest

from scripts.waypoint_survival import (
    SurvivalPolicyError, SurvivalPorts, VerifiedBindingProfile, WaypointSurvivalRunner,
)


def release(reason):
    return {"releaseSucceeded": True, "desktopInputsDown": [], "reason": reason}


class Harness:
    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = []

    def telemetry(self):
        if len(self.observations) > 1:
            return self.observations.pop(0)
        return self.observations[0]

    def cast(self, binding):
        self.calls.append(("cast", binding))
        return {"accepted": True, "binding": binding}

    def start_move(self, mode, points, leg):
        self.calls.append(("move-start", mode, points, leg))

    def release_move(self, reason):
        self.calls.append(("move-release", reason))
        return release(reason)

    def redirect(self, mode, points, leg):
        self.calls.append(("move-redirect", mode, points, leg))

    def start_combat(self):
        self.calls.append(("combat-start",))

    def release_combat(self, reason):
        self.calls.append(("combat-release", reason))
        return release(reason)

    def start_recovery(self):
        self.calls.append(("recovery-start",))

    def release_recovery(self, reason):
        self.calls.append(("recovery-release", reason))
        return release(reason)

    def reachable(self, points):
        self.calls.append(("reachable", points))
        return bool(points)

    def ports(self):
        return SurvivalPorts(self.telemetry, self.cast, self.start_move, self.release_move,
                             self.redirect, self.start_combat, self.release_combat,
                             self.start_recovery, self.release_recovery, self.reachable)


PROFILE = VerifiedBindingProfile(
    damage="ability:verified-damage", heal="ability:verified-heal",
    defense="ability:verified-defense", interrupt="ability:verified-interrupt")


def observation(*, present=False, combat=False, health=100, resource=100, dead=False,
                casting=False, known=True, delta=0, losing=False, off=False, on=False,
                fresh=True, ready_overrides=None):
    abilities = {}
    for binding in PROFILE.roles.values():
        abilities[binding] = {"learned": True, "ready": True, "usable": True,
                              "resourceCostPct": 10}
    for binding, changes in (ready_overrides or {}).items():
        abilities[binding].update(changes)
    return {"fresh": fresh, "identityValid": True, "readinessFresh": True,
            "player": {"dead": dead, "inCombat": combat, "healthPct": health,
                       "resourcePct": resource},
            "encounter": {"present": present, "casting": casting,
                          "threatKnown": known, "levelDelta": delta, "losing": losing,
                          "offCorridor": off, "onCorridor": on},
            "abilities": abilities}


class WaypointSurvivalTests(unittest.TestCase):
    def runner(self, observations, **kwargs):
        harness = Harness(observations)
        runner = WaypointSurvivalRunner(PROFILE, harness.ports(), checkpoint=7,
                                        pending_leg={"from": 7, "to": 8}, **kwargs)
        return runner, harness

    def test_encounter_handoff_preserves_leg_and_uses_verified_interrupt(self):
        runner, h = self.runner([
            observation(present=True, combat=True, casting=True),
            observation(present=True, combat=True, casting=True),
        ])
        runner.start()
        runner.step()
        state = runner.step()
        self.assertEqual("fight", state["state"])
        self.assertEqual({"from": 7, "to": 8}, state["pendingLeg"])
        self.assertEqual([
            ("move-start", "travel", [], {"from": 7, "to": 8}),
            ("move-release", "encounter-interrupt"), ("combat-start",),
            ("cast", PROFILE.interrupt)], h.calls)
        with self.assertRaisesRegex(SurvivalPolicyError, "cannot advance"):
            runner.route_checkpoint_advanced(8, {"from": 8, "to": 9})

    def test_unknown_or_losing_threat_retreats_only_over_known_reverse_trail(self):
        runner, h = self.runner([observation(present=True, combat=True, known=False)])
        runner.record_route_trail_point((1, 2))
        runner.record_route_trail_point((3, 4))
        runner.start()
        runner.step()  # encounter handoff
        state = runner.step()  # unsafe decision
        self.assertEqual("retreat", state["state"])
        self.assertIn(("move-start", "retreat", [[3.0, 4.0], [1.0, 2.0]],
                       {"from": 7, "to": 8}), h.calls)
        self.assertIn(("combat-release", "combat-complete"), h.calls)

    def test_unsafe_without_reverse_trail_halts_and_latches(self):
        runner, _ = self.runner([observation(present=True, combat=True, delta=9)])
        runner.start()
        runner.step()
        state = runner.step()
        self.assertEqual("halt", state["state"])
        self.assertEqual("critical-unavailable", state["coordinator"]["latchReason"])
        self.assertEqual("corridor-unavailable: retained trail is empty",
                         state["failureDetail"])

    def test_recovery_auto_rejoins_only_after_fresh_health_resource_and_no_combat(self):
        runner, h = self.runner([
            observation(present=True, combat=True),
            observation(present=False, combat=False, health=50, resource=20),
            observation(present=False, combat=False, health=85, resource=50),
        ])
        runner.record_route_trail_point((1, 1))
        runner.start()
        runner.step()
        recovering = runner.step()
        self.assertEqual("recover", recovering["state"])
        state = runner.step()
        self.assertEqual("rejoin", state["state"])
        self.assertEqual("movement", state["coordinator"]["activeAction"])
        self.assertIn(("recovery-start",), h.calls)
        self.assertIn(("recovery-release", "recovery-complete"), h.calls)

    def test_operator_stop_is_latched_and_resume_is_explicit(self):
        runner, h = self.runner([observation()])
        runner.record_route_trail_point((1, 1))
        runner.start()
        stopped = runner.operator_stop()
        self.assertEqual(("halt", "operator-stop"),
                         (stopped["state"], stopped["coordinator"]["latchReason"]))
        self.assertEqual("travel", runner.resume()["state"])
        self.assertEqual(2, len([call for call in h.calls if call[0] == "move-start"]))

    def test_death_stale_telemetry_and_unlearned_binding_are_critical_latches(self):
        cases = [
            (observation(dead=True), "death"),
            (observation(fresh=False), "critical-unavailable"),
            (observation(ready_overrides={PROFILE.damage: {"learned": False}}),
             "critical-unavailable"),
        ]
        for observed, reason in cases:
            with self.subTest(reason=reason):
                runner, _ = self.runner([observed])
                runner.start()
                state = runner.step()
                self.assertEqual("halt", state["state"])
                self.assertEqual(reason, state["coordinator"]["latchReason"])
                if observed.get("fresh") is False:
                    self.assertEqual(
                        "SurvivalPolicyError: critical telemetry unavailable",
                        state["failureDetail"])

    def test_no_ready_action_does_not_toggle_or_cast_any_fallback(self):
        overrides = {binding: {"ready": False} for binding in PROFILE.roles.values()}
        runner, h = self.runner([observation(present=True, combat=True,
                                             ready_overrides=overrides)])
        runner.start()
        runner.step()
        state = runner.step()
        self.assertEqual("fight", state["state"])
        self.assertFalse(any(call[0] == "cast" for call in h.calls))

    def test_target_ending_before_owned_action_uses_normal_fight_end_handoff(self):
        runner, h = self.runner([
            observation(present=True, combat=True),
            observation(present=True, combat=True),
            observation(present=False, combat=False),
        ])
        h.cast = lambda binding: {
            "accepted": False, "encounterEnded": True, "inputSent": False,
            "reason": "target-ended-before-action-admission"}
        runner = WaypointSurvivalRunner(
            PROFILE, h.ports(), checkpoint=7, pending_leg={"from": 7, "to": 8})
        runner.record_route_trail_point((1, 2, 3))
        runner.start()
        self.assertEqual("fight", runner.step()["state"])
        raced = runner.step()
        self.assertEqual("fight", raced["state"])
        self.assertIsNone(raced["coordinator"]["latchReason"])
        ended = runner.step()
        self.assertEqual("rejoin", ended["state"])
        self.assertIn(("combat-release", "combat-complete"), h.calls)

    def test_knockback_rejoins_known_corridor_without_advancing_checkpoint(self):
        runner, h = self.runner([observation(off=True), observation(on=True)])
        runner.record_route_trail_point((1, 2, 3))
        runner.start()
        first = runner.step()
        self.assertEqual("rejoin", first["state"])
        second = runner.step()
        self.assertEqual("travel", second["state"])
        self.assertEqual(7, second["checkpoint"])
        self.assertIn(("move-redirect", "rejoin", [[1.0, 2.0, 3.0]],
                       {"from": 7, "to": 8}), h.calls)

    def test_profile_requires_damage_but_preserves_absent_optional_roles(self):
        minimal = VerifiedBindingProfile(damage="verified-damage-id")
        self.assertEqual({"damage": "verified-damage-id"}, minimal.roles)
        with self.assertRaisesRegex(ValueError, "damage binding"):
            VerifiedBindingProfile(damage="")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            VerifiedBindingProfile(damage="same", heal="same")

    def test_absent_optional_roles_are_skipped_without_lookup_or_fabrication(self):
        minimal = VerifiedBindingProfile(damage="actual-damage")
        value = observation(present=True, combat=True, health=40, casting=True)
        value["abilities"] = {"actual-damage": {"learned": True, "ready": True,
                                                  "usable": True, "resourceCostPct": 0}}
        h = Harness([value])
        runner = WaypointSurvivalRunner(minimal, h.ports(), checkpoint=7,
                                        pending_leg={"from": 7, "to": 8})
        runner.start()
        runner.step()
        runner.step()
        self.assertIn(("cast", "actual-damage"), h.calls)

    def test_absolute_power_uses_actual_current_and_cost_without_invented_maximum(self):
        profile = VerifiedBindingProfile(damage="spark-id", resource_kind="absolute-power",
                                         recover_resource_absolute=25)
        value = observation(present=True, combat=True)
        value["player"].pop("resourcePct")
        value["player"].update(resourceKind="absolute-power", resourceCurrent=20)
        value["abilities"] = {"spark-id": {"learned": True, "ready": True,
                                            "usable": True, "resourceCost": 25}}
        h = Harness([value])
        runner = WaypointSurvivalRunner(profile, h.ports())
        runner.start(); runner.step(); runner.step()
        self.assertNotIn(("cast", "spark-id"), h.calls)
        value["player"]["resourceCurrent"] = 30
        runner = WaypointSurvivalRunner(profile, h.ports())
        runner.start(); runner.step(); runner.step()
        self.assertIn(("cast", "spark-id"), h.calls)

    def test_uncertain_encounter_release_stays_latched_through_cleanup_until_resume(self):
        runner, h = self.runner([observation(present=True, combat=True)])
        h.release_move = lambda reason: {"releaseSucceeded": False,
                                         "desktopInputsDown": ["w"], "reason": reason}
        # Rebuild ports after replacing the movement release callback.
        runner = WaypointSurvivalRunner(PROFILE, h.ports(), checkpoint=7,
                                        pending_leg={"from": 7, "to": 8})
        runner.record_route_trail_point((1, 1))
        runner.start()
        state = runner.step()
        self.assertEqual(("halt", "uncertain-release"),
                         (state["state"], state["coordinator"]["latchReason"]))
        cleaned = runner.retry_release(lambda reason: release(reason))
        self.assertEqual((None, "uncertain-release"),
                         (cleaned["coordinator"]["activeAction"],
                          cleaned["coordinator"]["latchReason"]))
        self.assertEqual("rejoin", runner.resume()["state"])


if __name__ == "__main__":
    unittest.main()
