"""Withdrawn integration tests for the shared Waypoints survival runtime."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.waypoint_survival_runtime import (
    _PolicyBackend, WaypointSurvivalRuntime, WaypointSurvivalRuntimeError)


NONCE = "0123456789abcdef0123456789abcdef"
PLAYER_KEY = 239816685251645959
PLAYER = f"u{PLAYER_KEY:016X}"
TARGET_KEY = 42
TARGET = f"u{TARGET_KEY:016X}"
ABILITY = "A05213A7D60B13F6B"


def basis():
    return {"qualified": True, "space": "UIParent-to-client-pixels",
            "viewportWidth": 1965.3360595703, "viewportHeight": 1024.0,
            "clientWidth": 1902, "clientHeight": 991,
            "scaleX": 0.9677734375, "scaleY": 0.9677734375,
            "offsetX": 0.0, "offsetY": 0.0}


def frame(sequence, *, event=None):
    action = {"slot": 1, "mapped": True, "visible": True,
              "abilityId": ABILITY, "abilityName": "Spark",
              "uniqueLearnedName": True, "macro": "cast Spark\nstopattack",
              "left": 100.0, "top": 100.0, "width": 60.0, "height": 30.0,
              "readiness": {"status": "ready"},
              "ability": {"idNew": ABILITY, "target": TARGET, "costPower": 10}}
    snapshot = {"status": "observed", "eventScope": "selected-or-self/1",
                "sessionId": NONCE, "playerId": PLAYER,
                "targetId": TARGET, "epoch": 7, "sequence": sequence,
                "frameTime": float(sequence),
                "player": {"health": 100, "healthMax": 100, "power": 50,
                           "level": 3, "coordX": 1.0, "coordY": 5.0, "coordZ": 2.0},
                "target": {"health": 80, "healthMax": 100, "level": 3,
                           "dead": False, "relation": "hostile",
                           "coordX": 3.0, "coordZ": 4.0},
                "catalog": {"entries": {ABILITY: "Spark"}},
                "controls": {"space": "UIParent", "viewportWidth": 1965.3360595703,
                             "viewportHeight": 1024.0, "actions": {ABILITY: action}},
                "lastEvent": event}
    return {"telemetryReady": sequence > 1, "baseline": sequence == 1,
            "sessionId": NONCE, "playerId": PLAYER, "sequence": sequence,
            "snapshot": snapshot, "catalog": {"complete": True,
                "entries": {ABILITY: "Spark"}}, "actions": {ABILITY: action}}


def native():
    return {"player": {"key": PLAYER_KEY,
                       "health": {"available": True, "current": 100,
                                  "maximum": 100, "deadAvailable": True, "dead": False},
                       "combat": {"available": True, "value": True},
                       "level": {"available": True, "value": 3}},
            "selectedTarget": {"available": True, "key": str(TARGET_KEY),
                       "health": {"available": True, "current": 80, "maximum": 100,
                                  "deadAvailable": True, "dead": False},
                       "combat": {"available": True, "value": True},
                       "level": {"available": True, "value": 3}}}


class Adapter:
    host = "AMD-DESKTOP"
    pid = 21672
    unit_key = str(PLAYER_KEY)
    target = {"machineName": host, "processId": pid,
              "processStartUtcTicks": 639302305454629980,
              "executableSha256": "A" * 64, "hwnd": 0x1234}

    def reserve(self):
        raise AssertionError("withdrawn preflight must not reserve input")


class Consumer:
    reports = []
    constructions = []
    cancel_calls = []

    def __init__(self, **values):
        self.values = values
        self.items = [deepcopy(item) for item in type(self).reports]
        type(self).constructions.append(values)

    def snapshot(self):
        if len(self.items) > 1:
            return self.items.pop(0)
        return deepcopy(self.items[0])

    def cancel_reference(self, *, max_age_seconds=5.0):
        type(self).cancel_calls.append(max_age_seconds)
        return {"status": "observed", "maxAgeSeconds": max_age_seconds}


class Actions:
    def __init__(self):
        self.calls = []

    def cast(self, ability_id):
        self.calls.append(("cast", ability_id))
        return {"trustedReceipt": True, "admissionEpoch": 7,
                "admissionSequence": 2, "admissionFrameTime": 2.0,
                "outcomeBaseline": None}

    def begin_encounter(self):
        self.calls.append(("begin-encounter",))

    def cancel(self):
        self.calls.append(("cancel",))
        return {"status": "already-clean", "inputSent": False}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps({
            "schemaVersion": 1, "nonce": NONCE, "resourceKind": "absolute-power",
            "coordinateBasis": basis(), "abilities": {"damage": ABILITY},
            "actions": [ABILITY],
            "thresholds": {"healBelowPct":45, "defendBelowPct":65,
                "retreatBelowPct":25, "recoverHealthPct":80,
                "recoverResourcePct":35, "recoverResourceAbsolute":20,
                "maximumLevelDelta":2},
            "retreat": {"maximumSeconds":20, "minimumTrailPoints":1},
            "timing": {"pollMilliseconds":100, "actionDeadlineMilliseconds":3000},
        }), encoding="utf-8")
        Consumer.reports = [frame(1), frame(2)]
        Consumer.constructions = []
        Consumer.cancel_calls = []
        self.actions = Actions()
        self.factory_calls = []
        self.facing_calls = []

        def action_factory(**values):
            self.factory_calls.append(values)
            return self.actions

        self.runtime = WaypointSurvivalRuntime(
            consumer_factory=Consumer, action_factory=action_factory,
            native_context_reader=lambda _adapter: native(),
            artifact_root=self.root / "artifacts",
            facing_runner=lambda *_args, **kwargs: self.facing_calls.append(kwargs["point"]) or {
                "status": "facing", "allPulsesReleased": True})

    def test_configure_and_two_frame_preflight_build_one_shared_backend_without_input(self):
        configured = self.runtime.configure(self.profile, Adapter())
        self.assertTrue(configured["configured"])
        self.assertTrue(configured["coordinateBasisQualified"])
        stop = threading.Event()
        result = self.runtime.preflight(Adapter(), stop)
        self.assertEqual("ready", result["status"])
        self.assertFalse(result["inputSent"])
        self.assertEqual(1, len(Consumer.constructions))
        self.assertEqual(NONCE, Consumer.constructions[0]["session_id"])
        self.assertEqual(1, len(self.factory_calls))
        self.assertIs(self.factory_calls[0]["stop"], stop)
        telemetry = self.runtime._latest_telemetry
        self.assertEqual("absolute-power", telemetry["player"]["resourceKind"])
        self.assertEqual(50, telemetry["player"]["resourceCurrent"])
        self.assertNotIn("resourcePct", telemetry["player"])
        self.assertTrue(telemetry["player"]["inCombat"])

    def test_stop_and_identity_or_basis_mismatch_refuse_before_backend(self):
        self.runtime.configure(self.profile, Adapter())
        stop = threading.Event(); stop.set()
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError, "stopped"):
            self.runtime.preflight(Adapter(), stop)
        self.assertEqual([], self.factory_calls)

        changed = Adapter()
        changed.target = dict(Adapter.target, processId=1)
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError, "identity-changed"):
            self.runtime.preflight(changed, threading.Event())
        self.assertEqual([], self.factory_calls)

        invalid = basis(); invalid["viewportWidth"] = 1900
        self.runtime.set_coordinate_basis(invalid)
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError, "basis-mismatch"):
            self.runtime.preflight(Adapter(), threading.Event())
        self.assertEqual([], self.factory_calls)

    def test_cast_requires_newer_exact_positive_outcome_and_release_is_idempotent(self):
        event = {"sequence": 1, "clock": 3.0, "kind": "damage",
                 "caster": PLAYER, "target": TARGET,
                 "selectedTargetId": TARGET,
                 "normalizedAbilityId": ABILITY, "damage": 12}
        Consumer.reports = [frame(1), frame(2), frame(3, event=event)]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        result = self.runtime._backend.cast(ABILITY)
        self.assertTrue(result["accepted"])
        self.assertEqual([(3.0, 4.0)], self.facing_calls)
        self.assertEqual("intended-hit-confirmed", result["outcome"]["status"])
        release = self.runtime._backend.release_combat("combat-complete")
        self.assertTrue(release["releaseSucceeded"])
        self.assertEqual([], release["desktopInputsDown"])

    def test_cast_polls_past_nonpositive_event_for_later_positive_receipt(self):
        immune = {"sequence": 1, "clock": 3.0, "kind": "immune",
                  "caster": PLAYER, "target": TARGET, "selectedTargetId": TARGET,
                  "normalizedAbilityId": ABILITY}
        hit = {"sequence": 2, "clock": 4.0, "kind": "damage",
               "caster": PLAYER, "target": TARGET, "selectedTargetId": TARGET,
               "normalizedAbilityId": ABILITY, "damage": 7}
        Consumer.reports = [frame(1), frame(2), frame(3, event=immune), frame(4, event=hit)]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        result = self.runtime._backend.cast(ABILITY)
        self.assertTrue(result["accepted"])
        self.assertEqual("intended-hit-confirmed", result["outcome"]["status"])
        self.assertNotIn(("cancel",), self.actions.calls)

    def test_cast_uses_exact_backend_admission_time_and_baseline(self):
        hit = {"sequence": 11, "clock": 50.5, "kind": "damage",
               "caster": PLAYER, "target": TARGET, "selectedTargetId": TARGET,
               "normalizedAbilityId": ABILITY, "damage": 9}
        post = frame(13, event=hit)
        post["snapshot"]["frameTime"] = 51.0
        self.actions.cast = lambda ability_id: {
            "trustedReceipt": True, "admissionEpoch": 7,
            "admissionSequence": 12, "admissionFrameTime": 50.0,
            "outcomeBaseline": {"sequence": 10, "clock": 49.0,
                                "sources": ["lastPositiveEvent"]}}
        Consumer.reports = [frame(1), frame(2), post]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        result = self.runtime._backend.cast(ABILITY)
        self.assertTrue(result["accepted"])
        self.assertEqual(50.5, result["outcome"]["event"]["clock"])

    def test_cast_accepts_only_explicit_profiled_effect_sub_id(self):
        effect_id = "A70A3925291DD1E14"
        document = json.loads(self.profile.read_text(encoding="utf-8"))
        document["outcomeAbilityIds"] = {ABILITY: [effect_id]}
        self.profile.write_text(json.dumps(document), encoding="utf-8")
        hit = {"sequence": 1, "clock": 3.0, "kind": "damage",
               "caster": PLAYER, "target": TARGET, "selectedTargetId": TARGET,
               "normalizedAbilityId": effect_id, "damage": 212}
        Consumer.reports = [frame(1), frame(2), frame(3, event=hit)]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        result = self.runtime._backend.cast(ABILITY)
        self.assertTrue(result["accepted"])
        self.assertEqual(ABILITY, result["outcome"]["castAbilityId"])
        self.assertEqual(effect_id, result["outcome"]["effectAbilityId"])

    def test_outcome_timeout_uses_cancel_cleanup_before_returning_failure(self):
        immune = {"sequence": 1, "clock": 3.0, "kind": "immune",
                  "caster": PLAYER, "target": TARGET, "selectedTargetId": TARGET,
                  "normalizedAbilityId": ABILITY}
        Consumer.reports = [frame(1), frame(2), frame(3, event=immune)]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        ticks = iter((0.0, 4.0, 4.0))
        self.runtime.clock = lambda: next(ticks)
        result = self.runtime._backend.cast(ABILITY)
        self.assertFalse(result["accepted"])
        self.assertIn(("cancel",), self.actions.calls)
        self.assertEqual("already-clean", result["cleanup"]["status"])

    def test_route_runner_passes_verified_profile_and_shared_backend(self):
        self.runtime.configure(self.profile, Adapter())
        expected = [{"status": "arrived"}]
        events = []
        with patch("scripts.waypoint_survival_runtime.run_survival_route",
                   return_value=expected) as run:
            result = self.runtime.route_runner(
                Adapter(), [("one", 1, 2)], threading.Event(), events.append)
        self.assertIs(result, expected)
        options = run.call_args.kwargs
        self.assertEqual("absolute-power", options["profile"].resource_kind)
        self.assertEqual(20, options["profile"].recover_resource_absolute)
        self.assertIs(options["action_backend"], self.runtime._backend)
        self.assertEqual("completed", events[-1]["survival"]["state"])
        status = self.runtime.status()
        self.assertFalse(status["active"])
        self.assertEqual("completed", status["state"])
        self.assertFalse(status["inputSent"])

    def test_native_addon_health_maximum_mismatch_fails_closed(self):
        bad = native()
        bad["player"]["health"]["maximum"] = 99
        runtime = WaypointSurvivalRuntime(
            consumer_factory=Consumer, action_factory=lambda **_values: Actions(),
            native_context_reader=lambda _adapter: bad,
            artifact_root=self.root / "other")
        runtime.configure(self.profile, Adapter())
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError, "health-mismatch"):
            runtime.preflight(Adapter(), threading.Event())

    def test_newer_native_health_drives_policy_and_transitional_target_death(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime._adapter, self.runtime._player_id = Adapter(), PLAYER
        self.runtime._target_id = TARGET
        changed = native()
        changed["player"]["health"]["current"] = 80
        changed["selectedTarget"]["health"].update(current=0, dead=True)
        telemetry = self.runtime._normalize(frame(2), changed)
        self.assertEqual(80, telemetry["player"]["healthPct"])
        self.assertEqual("changed-during-acquisition",
                         telemetry["player"]["healthReconciliation"])
        self.assertEqual("changed-during-acquisition",
                         telemetry["encounter"]["targetHealthReconciliation"])
        self.assertFalse(telemetry["encounter"]["present"])

    def test_cancel_reference_forwards_to_active_consumer_without_snapshot(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        before = len(self.runtime._consumer.items)
        result = self.runtime.cancel_reference(max_age_seconds=4.0)
        self.assertEqual({"status": "observed", "maxAgeSeconds": 4.0}, result)
        self.assertEqual([4.0], Consumer.cancel_calls)
        self.assertEqual(before, len(self.runtime._consumer.items))

    def test_status_preserves_action_failure_diagnostic_for_cli_receipt(self):
        diagnostic = {"operation": "cancel", "stage": "cancel-click",
                      "error": {"type": "SurvivalActionError",
                                "reason": "native lease lost"},
                      "nativeReceiptFromAttempt": True,
                      "rawNativeReceipt": {"status": "halted",
                                           "reason": "native lease lost",
                                           "inputSent": True,
                                           "releaseSucceeded": False}}
        self.runtime._backend = SimpleNamespace(action_diagnostic=diagnostic)
        observed = self.runtime.status()["actionDiagnostic"]
        self.assertEqual(diagnostic, observed)
        observed["error"]["reason"] = "mutated"
        self.assertEqual("native lease lost",
                         self.runtime.status()["actionDiagnostic"]["error"]["reason"])

    def test_decimal_string_player_and_target_keys_and_partial_catalog_are_admitted(self):
        current = frame(2)
        current["catalog"]["complete"] = False
        current["catalog"].update(count=55, page=7, pages=7)
        current["catalog"]["entries"] = {}
        Consumer.reports = [frame(1), current]
        self.runtime.configure(self.profile, Adapter())
        result = self.runtime.preflight(Adapter(), threading.Event())
        self.assertEqual("ready", result["status"])
        self.assertEqual(PLAYER, result["playerId"])

    def test_no_target_is_ordinary_out_of_combat_but_unknown_threat_in_combat(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime._adapter = Adapter()
        self.runtime._player_id = PLAYER
        self.runtime._target_id = None
        report = frame(2)
        report["snapshot"].update(targetId=None, target={})
        no_target = native()
        no_target["player"]["combat"]["value"] = False
        no_target["selectedTarget"] = {"available": False, "key": None,
            "health": {"available": False}, "level": {"available": False}}
        telemetry = self.runtime._normalize(report, no_target)
        self.assertEqual((False, False),
                         (telemetry["encounter"]["present"],
                          telemetry["encounter"]["threatKnown"]))
        no_target["player"]["combat"]["value"] = True
        telemetry = self.runtime._normalize(report, no_target)
        self.assertEqual((True, False),
                         (telemetry["encounter"]["present"],
                          telemetry["encounter"]["threatKnown"]))

    def test_first_exact_hostile_after_idle_no_target_pins_one_encounter(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime._adapter, self.runtime._player_id = Adapter(), PLAYER
        self.runtime._target_id = None
        telemetry = self.runtime._normalize(frame(2), native())
        self.assertTrue(telemetry["encounter"]["threatKnown"])
        self.assertEqual(TARGET, self.runtime._target_id)
        self.runtime._backend = _PolicyBackend(self.runtime, self.actions)
        self.runtime._backend.release_combat("combat-complete")
        self.assertIsNone(self.runtime._target_id)

    def test_friendly_or_changed_target_is_unknown_and_dead_target_ends_encounter(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime._adapter = Adapter()
        self.runtime._player_id = PLAYER
        self.runtime._target_id = TARGET
        report = frame(2)
        friendly = deepcopy(report)
        friendly["snapshot"]["target"]["relation"] = "friendly"
        telemetry = self.runtime._normalize(friendly, native())
        self.assertEqual((True, False),
                         (telemetry["encounter"]["present"],
                          telemetry["encounter"]["threatKnown"]))
        dead = deepcopy(report)
        dead["snapshot"]["target"].update(health=0, dead=True)
        dead_native = native()
        dead_native["selectedTarget"]["health"].update(current=0, dead=True)
        telemetry = self.runtime._normalize(dead, dead_native)
        self.assertFalse(telemetry["encounter"]["present"])

    def test_action_factory_receives_fresh_frame_provider_not_cached_report(self):
        Consumer.reports = [frame(1), frame(2), frame(3)]
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        provider = self.factory_calls[0]["snapshot"]
        fresh = provider()
        self.assertEqual(3, fresh["sequence"])
        self.assertEqual(3, self.runtime._latest_report["sequence"])

    def test_corridor_accepts_any_nearby_sample_and_retains_full_path(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime.preflight(Adapter(), threading.Event())
        backend = self.runtime._backend
        self.assertTrue(backend.corridor_reachable([[1, 5, 2], [2, 5, 2]]))
        self.assertTrue(backend.corridor_reachable([[2, 5, 2], [1, 5, 2]]))
        self.assertEqual([(2.0, 5.0, 2.0), (1.0, 5.0, 2.0)],
                         backend.corridor_points)
        self.assertFalse(backend.corridor_reachable([[9, 5, 9], [2, 5, 2]]))
        self.assertFalse(backend.corridor_reachable([[1, 5, 2], [4, 5, 2]]))
        self.assertFalse(backend.corridor_reachable([[1, 2], [2, 2]]))

    def test_exact_recent_incoming_damage_can_qualify_selected_threat(self):
        self.runtime.configure(self.profile, Adapter())
        self.runtime._adapter, self.runtime._player_id = Adapter(), PLAYER
        self.runtime._target_id = TARGET
        report = frame(2)
        report["snapshot"]["target"]["relation"] = "unknown"
        report["snapshot"]["lastIncoming"] = {
            "sequence": 1, "clock": 1.5, "kind": "damage", "caster": TARGET,
            "target": PLAYER, "selectedTargetId": TARGET, "damage": 5,
            "normalizedAbilityId": "enemy-hit"}
        telemetry = self.runtime._normalize(report, native())
        self.assertTrue(telemetry["encounter"]["threatKnown"])
        report["snapshot"]["lastIncoming"]["clock"] = -1
        telemetry = self.runtime._normalize(report, native())
        self.assertFalse(telemetry["encounter"]["threatKnown"])

    def test_health_decline_and_three_second_no_action_window_mark_losing(self):
        from scripts.survival_profile import load_survival_profile
        now = {"value": 0.0}
        runtime = WaypointSurvivalRuntime(clock=lambda: now["value"])
        runtime._profile = load_survival_profile(self.profile)
        runtime._adapter, runtime._player_id, runtime._target_id = Adapter(), PLAYER, TARGET
        waiting = frame(2)
        waiting["actions"][ABILITY]["readiness"]["status"] = "waiting"
        runtime._normalize(waiting, native())
        now["value"] = 3.1
        timed = runtime._normalize(waiting, native())
        self.assertTrue(timed["encounter"]["noActionTimedOut"])
        runtime._latest_telemetry = {"player": {"healthPct": 100}}
        lower = frame(3)
        lower["snapshot"]["player"]["health"] = 84
        lower_native = native(); lower_native["player"]["health"]["current"] = 84
        declining = runtime._normalize(lower, lower_native)
        self.assertTrue(declining["encounter"]["healthDeclining"])
        runtime._health_observation = (100, now["value"])
        small = frame(4)
        small["snapshot"]["player"]["health"] = 95
        small_native = native(); small_native["player"]["health"]["current"] = 95
        stable_fight = runtime._normalize(small, small_native)
        self.assertFalse(stable_fight["encounter"]["healthDeclining"])

    def test_self_role_requires_intrinsic_player_target_before_delivery(self):
        self.runtime._profile = {"abilities": {"heal": ABILITY, "defense": None,
                                                "interrupt": None, "damage": "other"},
                                 "timing": {"actionDeadlineMilliseconds": 3000}}
        self.runtime._player_id, self.runtime._target_id = PLAYER, TARGET
        self.runtime._latest_report = frame(2)
        backend = _PolicyBackend(self.runtime, self.actions)
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError,
                                    "self-action-target-mismatch"):
            backend.cast(ABILITY)
        self.assertEqual([], self.actions.calls)

    def test_begin_encounter_resets_action_owner_once_not_per_cast(self):
        self.runtime._profile = {"abilities": {"heal": None, "defense": None,
                                                "interrupt": None, "damage": ABILITY},
                                 "timing": {"actionDeadlineMilliseconds": 3000}}
        backend = _PolicyBackend(self.runtime, self.actions)
        backend.start_combat()
        self.assertEqual([("begin-encounter",)], self.actions.calls)

    def test_route_preflight_allows_no_selected_target_but_cast_does_not(self):
        reports = [frame(1), frame(2)]
        for report in reports:
            snapshot = report["snapshot"]
            snapshot["targetId"], snapshot["target"] = None, {}
            report["actions"][ABILITY]["ability"]["target"] = None
            snapshot["controls"]["actions"][ABILITY]["ability"]["target"] = None
        Consumer.reports = reports
        no_target = native()
        no_target["selectedTarget"] = {
            "available": False, "key": None,
            "health": {"available": False}, "combat": {"available": False},
            "level": {"available": False}}
        runtime = WaypointSurvivalRuntime(
            consumer_factory=Consumer, action_factory=lambda **_values: Actions(),
            native_context_reader=lambda _adapter: no_target,
            artifact_root=self.root / "idle")
        runtime.configure(self.profile, Adapter())
        result = runtime.preflight(Adapter(), threading.Event())
        self.assertIsNone(result["targetId"])
        with self.assertRaisesRegex(WaypointSurvivalRuntimeError, "selected-target"):
            runtime._backend.cast(ABILITY)

    def test_route_runner_finally_releases_surviving_action_owner(self):
        calls = []
        backend = SimpleNamespace(
            telemetry=lambda: {}, cast=lambda _ability: {},
            start_combat=lambda: None, release_combat=lambda _reason: {},
            start_recovery=lambda: None, release_recovery=lambda _reason: {},
            corridor_reachable=lambda _points: False,
            finalize=lambda: calls.append("finalize"))
        self.runtime._backend = backend
        self.runtime._profile = {"timing": {"pollMilliseconds": 100},
                                 "retreat": {"maximumSeconds": 30,
                                             "minimumTrailPoints": 1}}
        with (patch.object(self.runtime, "preflight", return_value={"status":"ready"}),
              patch.object(self.runtime, "_verified_profile", return_value=object()),
              patch("scripts.waypoint_survival_runtime.run_survival_route",
                    side_effect=RuntimeError("route-failed"))):
            with self.assertRaisesRegex(RuntimeError, "route-failed"):
                self.runtime.route_runner(Adapter(), [("one", 1, 2)],
                                          threading.Event(), lambda _event: None)
        self.assertEqual(["finalize"], calls)


if __name__ == "__main__":
    unittest.main()
