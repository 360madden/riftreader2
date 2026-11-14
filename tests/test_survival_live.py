"""Focused tests for the read-only survival live consumer."""
from __future__ import annotations

from copy import deepcopy
import contextlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import survival_live as live

NONCE = "0123456789abcdef0123456789abcdef"
PLAYER = "u035400012FA2D207"
TARGET = {"processId": 21672, "processStartUtcTicks": 639302305454629980,
          "executableSha256": "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"}


def frame(sequence=1, clock=10.0, *, pages=1, entries=None):
    entries = entries if entries is not None else {"A1": "Defend"}
    return {
        "schemaVersion": 1, "addon": "RiftReader2Casting",
        "addonVersion": "0.4.2", "source": "rift-api",
        "eventScope": "selected-or-self/1",
        "sessionId": NONCE, "epoch": 7, "sequence": sequence,
        "frameTime": clock, "playerId": PLAYER.lower(), "targetId": None,
        "status": "observed", "player": {"health": 100, "healthMax": 100},
        "target": {}, "ability": {}, "cast": {"status": "idle"},
        "readiness": {"status": "blocked", "reason": "select-ability"},
        "catalog": {"status": "observed", "count": len(entries) if pages == 1 else 9,
                    "page": 1, "pages": pages, "sampledAt": clock,
                    "entries": entries},
        "controls": {}, "trial": {},
    }


def wire(value):
    return (live.MARKER + json.dumps(value, separators=(",", ":")).encode()
            + live.SUFFIX + b"\0tail")


class Adapter:
    target = TARGET
    unit_key = int(PLAYER[1:], 16)
    def __init__(self, *_args):
        pass


class SurvivalLiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed.json"
        self.seed.write_text(json.dumps({
            "evidenceKind": "native-value-scout/1", "identity": TARGET,
            "coveredSpans": [{"baseAddress": "0x100000",
                              "byteLength": 16 * 1024 * 1024}],
        }), encoding="utf-8")

    @staticmethod
    def selector(**_kwargs):
        return {"status": "ready", "target": deepcopy(TARGET)}

    def test_compact_addon_version_keeps_nonce_and_schema_checks(self):
        value = frame()
        value["addonVersion"] = "0.5.0"
        self.assertEqual("0.5.0", live.decode_frame(wire(value), NONCE, PLAYER)["frame"]["addonVersion"])
        value["sessionId"] = "f" * 32
        with self.assertRaisesRegex(live.SurvivalLiveError, "nonce-mismatch"):
            live.decode_frame(wire(value), NONCE, PLAYER)
        value["sessionId"] = NONCE
        value["addonVersion"] = "0.5.1"
        self.assertEqual("0.5.1", live.decode_frame(wire(value), NONCE, PLAYER)["frame"]["addonVersion"])
        value["addonVersion"] = "0.5.2"
        with self.assertRaisesRegex(live.SurvivalLiveError, "unexpected-survival-frame-contract"):
            live.decode_frame(wire(value), NONCE, PLAYER)

    def test_decode_preserves_false_zero_and_case_insensitive_player(self):
        value = frame()
        value["player"].update({"combat": False, "power": 0})
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        self.assertIs(decoded["player"]["combat"], False)
        self.assertEqual(0, decoded["player"]["power"])
        bad = deepcopy(value)
        bad["sessionId"] = "f" * 32
        with self.assertRaisesRegex(live.SurvivalLiveError, "nonce-mismatch"):
            live.decode_frame(wire(bad), NONCE, PLAYER)

    def test_action_profile_and_cancel_geometry_are_retained(self):
        value = frame()
        action = {"slot": 1, "mapped": True, "visible": True,
                  "abilityId": "A1", "abilityName": "Defend", "macro": "cast Defend",
                  "uniqueLearnedName": True, "left": 10, "top": 20,
                  "width": 100, "height": 40,
                  "readiness": {"status": "ready", "reason": "observed-ready"},
                  "ability": {"target": PLAYER}}
        value["controls"] = {
            "space": "UIParent", "actions": {"A1": action},
            "cancel": {"mapped": True, "visible": True, "left": 10, "top": 70,
                       "width": 100, "height": 40}}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        self.assertEqual("A1", decoded["controls"]["actions"]["A1"]["abilityId"])
        self.assertTrue(decoded["controls"]["cancel"]["mapped"])

    def test_outcome_requires_newer_exact_ids_and_positive_result(self):
        baseline = {"sequence": 4, "clock": 20}
        value = frame(clock=22)
        value["targetId"] = "u0000000000000002"
        value["lastEvent"] = {"sequence": 5, "clock": 21, "kind": "damage",
                              "caster": PLAYER, "target": "u0000000000000002",
                              "selectedTargetId": "u0000000000000002",
                              "normalizedAbilityId": "A1", "damage": 18}
        result = live.assess_outcome(
            baseline, value, player_id=PLAYER, target_id="u0000000000000002",
            ability_id="A1", submission_frame_time=20.5,
            outcome_deadline_frame_time=23)
        self.assertEqual("intended-hit-confirmed", result["status"])
        value["lastEvent"]["sequence"] = 4
        self.assertEqual("event-not-newer-than-baseline", live.assess_outcome(
            baseline, value, player_id=PLAYER, target_id="u0000000000000002",
            ability_id="A1", submission_frame_time=20.5,
            outcome_deadline_frame_time=23)["reason"])

    def test_self_effect_keeps_separate_hostile_selection(self):
        hostile = "u0000000000000002"
        value = frame(clock=30)
        value["targetId"] = hostile
        value["lastEvent"] = {
            "sequence": 2, "clock": 29.5, "kind": "heal", "caster": PLAYER,
            "target": PLAYER, "selectedTargetId": hostile,
            "normalizedAbilityId": "HEAL1", "heal": 50}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        result = live.assess_outcome(
            None, decoded, player_id=PLAYER, encounter_target_id=hostile,
            effect_target_id=PLAYER, ability_id="HEAL1", submission_frame_time=29,
            outcome_deadline_frame_time=32)
        self.assertEqual("intended-heal-confirmed", result["status"])
        wrong = live.assess_outcome(
            None, decoded, player_id=PLAYER, encounter_target_id="u0000000000000003",
            effect_target_id=PLAYER, ability_id="HEAL1", submission_frame_time=29,
            outcome_deadline_frame_time=32)
        self.assertEqual("post-action-event-id-mismatch", wrong["reason"])

    def test_incoming_requires_current_exact_selected_context(self):
        hostile = "u0000000000000002"
        value = frame(clock=40)
        value["targetId"] = hostile
        value["lastIncoming"] = {
            "sequence": 1, "clock": 39, "kind": "damage", "caster": hostile,
            "target": PLAYER, "selectedTargetId": hostile, "damage": 13}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        self.assertEqual("incoming-damage-observed", live.assess_incoming(
            decoded, player_id=PLAYER, encounter_target_id=hostile)["status"])
        value["lastIncoming"]["clock"] = 37.9
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "stale-or-future-survival-event"):
            live.decode_frame(wire(value), NONCE, PLAYER)

    def test_exact_death_survives_cleared_selection_and_caster_is_optional(self):
        hostile = "u0000000000000002"
        value = frame(clock=40)
        value.update(addonVersion="0.5.1", deathScope="exact-unit-death/1",
                     targetId=None,
                     lastDeath={"sequence": 3, "clock": 39, "target": hostile,
                                "targetName": "Hostile"})
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        self.assertEqual(hostile, decoded["lastDeath"]["target"])
        self.assertNotIn("caster", decoded["lastDeath"])
        value["lastDeath"]["caster"] = PLAYER
        self.assertEqual(PLAYER, live.decode_frame(wire(value), NONCE, PLAYER)
                         ["frame"]["lastDeath"]["caster"])

    def test_death_scope_identity_and_freshness_are_strict(self):
        hostile = "u0000000000000002"
        value = frame(clock=40)
        value.update(addonVersion="0.5.1", deathScope="exact-unit-death/1",
                     lastDeath={"sequence": 1, "clock": 39, "target": hostile})
        for mutation, reason in (
                ({"deathScope": "selected-target-death/1"}, "unexpected-survival-death-scope"),
                ({"lastDeath": {"sequence": 1, "clock": 34.9, "target": hostile}},
                 "stale-or-future-survival-death"),
                ({"lastDeath": {"sequence": 1, "clock": 41, "target": hostile}},
                 "stale-or-future-survival-death"),
                ({"lastDeath": {"sequence": 1, "clock": 39, "target": "bad"}},
                 "invalid-survival-last-death")):
            candidate=deepcopy(value); candidate.update(mutation)
            with self.assertRaisesRegex(live.SurvivalLiveError, reason):
                live.decode_frame(wire(candidate), NONCE, PLAYER)

    def test_death_generation_cannot_rewind_or_mutate(self):
        hostile = "u0000000000000002"
        previous = {"sequence": 2, "clock": 39, "target": hostile}
        live._validate_death_progression(previous, deepcopy(previous))
        live._validate_death_progression(
            previous, {"sequence": 3, "clock": 39.5, "target": hostile})
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "death-generation-regressed"):
            live._validate_death_progression(
                previous, {"sequence": 1, "clock": 38, "target": hostile})
        changed = dict(previous, caster=PLAYER)
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "conflicting-survival-death-generation"):
            live._validate_death_progression(previous, changed)

    def test_legacy_frame_can_support_cleanup_but_not_contextual_outcome(self):
        value = frame(clock=50)
        del value["eventScope"]
        value["targetId"] = "u0000000000000002"
        value["lastEvent"] = {"sequence": 1, "clock": 49, "kind": "immune",
                              "caster": PLAYER, "target": value["targetId"]}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        self.assertIsNone(decoded.get("eventScope"))
        result = live.assess_outcome(
            None, decoded, player_id=PLAYER,
            encounter_target_id=value["targetId"], effect_target_id=value["targetId"],
            ability_id="A1", submission_frame_time=48,
            outcome_deadline_frame_time=51)
        self.assertEqual("post-action-event-id-mismatch", result["reason"])

    def test_positive_hit_survives_later_immune_diagnostic(self):
        hostile = "u0000000000000002"
        value = frame(clock=33)
        value.update(targetId=hostile,
                     positiveEventScope="last-effective-damage-or-heal/1")
        value["lastPositiveEvent"] = {
            "sequence": 5, "clock": 31, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": "A1", "damage": 27}
        value["lastEvent"] = {
            "sequence": 6, "clock": 31.2, "kind": "immune", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": "A1"}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        outcome = live.assess_outcome(
            {"sequence": 4, "clock": 29}, decoded, player_id=PLAYER,
            encounter_target_id=hostile, effect_target_id=hostile,
            ability_id="A1", submission_frame_time=30,
            outcome_deadline_frame_time=32)
        self.assertEqual("intended-hit-confirmed", outcome["status"])
        self.assertEqual("lastPositiveEvent", outcome["eventSource"])
        self.assertEqual("immune", outcome["latestDiagnosticEvent"]["kind"])

    def test_only_immune_never_becomes_positive_outcome(self):
        hostile = "u0000000000000002"
        value = frame(clock=33)
        value["targetId"] = hostile
        value["lastEvent"] = {
            "sequence": 6, "clock": 31.2, "kind": "immune", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": "A1"}
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        outcome = live.assess_outcome(
            {"sequence": 4, "clock": 29}, decoded, player_id=PLAYER,
            encounter_target_id=hostile, effect_target_id=hostile,
            ability_id="A1", submission_frame_time=30,
            outcome_deadline_frame_time=32)
        self.assertEqual("unavailable", outcome["status"])
        self.assertEqual("no-positive-matching-damage-or-heal", outcome["reason"])

    def test_per_ability_positive_survives_newer_unrelated_positive(self):
        hostile = "u0000000000000002"
        requested, unrelated = "PACIFY", "AUTOATTACK"
        value = frame(clock=43)
        value.update(targetId=hostile,
                     positiveEventScope="last-effective-damage-or-heal/1",
                     positiveEventsScope="per-ability/1")
        requested_event = {
            "sequence": 8, "clock": 41, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": requested, "abilityName": "Pacify", "damage": 31}
        unrelated_event = {
            "sequence": 9, "clock": 41.2, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": unrelated, "abilityName": "Attack", "damage": 212}
        value["positiveEvents"] = {requested: requested_event,
                                   unrelated: unrelated_event}
        value["lastPositiveEvent"] = unrelated_event
        value["lastEvent"] = unrelated_event
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        outcome = live.assess_outcome(
            {"sequence": 7, "clock": 39}, decoded, player_id=PLAYER,
            encounter_target_id=hostile, effect_target_id=hostile,
            ability_id=requested, submission_frame_time=40,
            outcome_deadline_frame_time=42)
        self.assertEqual("intended-hit-confirmed", outcome["status"])
        self.assertEqual("positiveEvents.PACIFY", outcome["eventSource"])
        self.assertEqual(31, outcome["event"]["damage"])

    def test_explicit_effect_ability_profile_matches_observed_effect_id(self):
        hostile = "u0000000000000002"
        cast_id = "A661611602A6D2082"
        effect_id = "A70A3925291DD1E14"
        autoattack_id = "A4FDE7DEC3FDF0909"
        value = frame(clock=53)
        value.update(targetId=hostile,
                     positiveEventScope="last-effective-damage-or-heal/1",
                     positiveEventsScope="per-ability/1")
        effect = {
            "sequence": 12, "clock": 51, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": effect_id,
            "abilityName": "Pacifying Strike", "damage": 212}
        autoattack = {
            "sequence": 13, "clock": 51.2, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": autoattack_id,
            "abilityName": "AutoAttack", "damage": 108}
        value["positiveEvents"] = {effect_id: effect, autoattack_id: autoattack}
        value["lastPositiveEvent"] = autoattack
        value["lastEvent"] = autoattack
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        outcome = live.assess_outcome(
            {"sequence": 10, "clock": 49}, decoded, player_id=PLAYER,
            encounter_target_id=hostile, effect_target_id=hostile,
            ability_id=cast_id, effect_ability_ids=[effect_id],
            submission_frame_time=50, outcome_deadline_frame_time=52)
        self.assertEqual("intended-hit-confirmed", outcome["status"])
        self.assertEqual(f"positiveEvents.{effect_id}", outcome["eventSource"])
        self.assertEqual(cast_id, outcome["castAbilityId"])
        self.assertEqual(effect_id, outcome["effectAbilityId"])

    def test_effect_profile_never_infers_unlisted_autoattack(self):
        hostile = "u0000000000000002"
        cast_id = "A661611602A6D2082"
        autoattack_id = "A4FDE7DEC3FDF0909"
        value = frame(clock=63)
        value.update(targetId=hostile,
                     positiveEventScope="last-effective-damage-or-heal/1",
                     positiveEventsScope="per-ability/1")
        autoattack = {
            "sequence": 15, "clock": 61, "kind": "damage", "caster": PLAYER,
            "target": hostile, "selectedTargetId": hostile,
            "normalizedAbilityId": autoattack_id,
            "abilityName": "AutoAttack", "damage": 108}
        value["positiveEvents"] = {autoattack_id: autoattack}
        value["lastPositiveEvent"] = autoattack
        value["lastEvent"] = autoattack
        decoded = live.decode_frame(wire(value), NONCE, PLAYER)["frame"]
        outcome = live.assess_outcome(
            {"sequence": 14, "clock": 59}, decoded, player_id=PLAYER,
            encounter_target_id=hostile, effect_target_id=hostile,
            ability_id=cast_id, effect_ability_ids=["A70A3925291DD1E14"],
            submission_frame_time=60, outcome_deadline_frame_time=62)
        self.assertEqual("unavailable", outcome["status"])
        self.assertEqual("post-action-event-id-mismatch", outcome["reason"])
        self.assertEqual(autoattack_id, outcome["effectAbilityId"])

    def test_effect_profile_is_explicit_unique_and_bounded(self):
        hostile = "u0000000000000002"
        decoded = live.decode_frame(wire(frame()), NONCE, PLAYER)["frame"]
        common = dict(player_id=PLAYER, encounter_target_id=hostile,
                      effect_target_id=hostile, ability_id="CAST",
                      submission_frame_time=1, outcome_deadline_frame_time=2)
        for invalid in ([], ["A", "A"], ["A", "B", "C", "D", "E"]):
            outcome = live.assess_outcome(None, decoded,
                                          effect_ability_ids=invalid, **common)
            self.assertEqual("invalid-effect-ability-ids", outcome["reason"])

    def test_positive_event_map_is_bounded_and_exact_keyed(self):
        hostile = "u0000000000000002"
        value = frame(clock=12)
        value.update(targetId=hostile, positiveEventsScope="per-ability/1",
                     positiveEventScope="last-effective-damage-or-heal/1")
        event = {"sequence": 1, "clock": 11, "kind": "damage", "caster": PLAYER,
                 "target": hostile, "selectedTargetId": hostile,
                 "normalizedAbilityId": "A1", "damage": 1}
        value["positiveEvents"] = {"WRONG": event}
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "invalid-survival-positive-event-key"):
            live.decode_frame(wire(value), NONCE, PLAYER)
        value["positiveEvents"] = {f"A{i}": dict(event, normalizedAbilityId=f"A{i}")
                                   for i in range(9)}
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "invalid-survival-positive-events"):
            live.decode_frame(wire(value), NONCE, PLAYER)

    def test_outcome_baseline_uses_max_outgoing_generation(self):
        snapshot = {"lastPositiveEvent": {"sequence": 7, "clock": 40},
                    "lastEvent": {"sequence": 8, "clock": 40.2}}
        self.assertEqual({"sequence": 8, "clock": 40.2,
                          "sources": ["lastEvent", "lastPositiveEvent"]},
                         live.outcome_baseline(snapshot))

    def test_seed_autodiscovery_requires_exact_epoch(self):
        artifacts = self.root / "artifacts"
        old = deepcopy(TARGET); old["processStartUtcTicks"] -= 1
        for folder, identity in (("survival-old/scout", old),
                                 ("survival-current/scout", TARGET)):
            path = artifacts / folder / "index.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "evidenceKind": "native-value-scout/1", "identity": identity,
                "coveredSpans": [{"baseAddress": "0x300000",
                                  "byteLength": 16 * 1024 * 1024}],
            }), encoding="utf-8")
        selected = live.autodiscover_seed(TARGET, artifacts)
        self.assertIn("survival-current", str(selected))

    def test_known_frame_batch_uses_two_ranges_per_address(self):
        request = live._capture_request(TARGET, [0x100000, 0x200000])
        self.assertEqual(4, len(request["ranges"]))
        self.assertEqual("0x100000", request["ranges"][0]["address"])
        self.assertEqual("0x101000", request["ranges"][1]["address"])
        self.assertEqual("0x200000", request["ranges"][2]["address"])

    def test_scout_captures_all_64_matches_in_native_sized_batches(self):
        candidates = [({"address": f"0x{0x100000 + i * 0x1000:X}",
                        "referenceNames": ["rr2-survival-prefix"]}, b"prefix")
                      for i in range(40)]
        batches = []
        def capture(_target, addresses, _prefix, _runner):
            batches.append(list(addresses))
            return [({"address": f"0x{address:X}"}, b"frame") for address in addresses]
        with patch.object(live, "_run_native", return_value=None), \
                patch.object(live, "_read_json", return_value={}), \
                patch.object(live, "_validate_scout", return_value=candidates), \
                patch.object(live, "_capture_known", side_effect=capture):
            result = live._scout_once(
                TARGET, 0x100000, 16 * 1024 * 1024, 450,
                self.root / "batched.scout", runner=object())
        self.assertEqual([16, 16, 8], [len(batch) for batch in batches])
        self.assertEqual(40, len(result))

    def test_later_marker_beyond_first_eight_can_advance_selection(self):
        calls = 0
        def scout(*_args):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [({"address": "0x100000"}, wire(frame(100, 100)))]
            rows = [({"address": f"0x{0x200000 + i * 0x1000:X}"},
                     wire(frame(i + 1, i + 1))) for i in range(8)]
            rows.extend([({"address": f"0x{0x300000 + i * 0x1000:X}"},
                          wire(frame(101 + i, 101 + i))) for i in range(8)])
            return rows
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "later-current",
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout,
            capture_known=lambda *_args: [])
        self.assertEqual(108, result["sourceWindow"]["lastSequence"])

    def test_continually_old_advancement_fails_relative_liveness(self):
        calls = 0
        def scout(*_args):
            nonlocal calls
            calls += 1
            return [({"address": "0x200000"}, wire(frame(calls, 10 + calls * .2)))]
        consumer = live.SurvivalLiveConsumer(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "relative-stale",
            selector=self.selector, adapter_factory=Adapter, scout_once=scout,
            capture_known=lambda *_args: [], relative_lag_seconds=2)
        consumer.snapshot()
        consumer.latest_reference["acceptedAtMonotonic"] -= 5
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "survival-source-relative-lag-exceeded"):
            consumer.snapshot()

    def test_two_independent_advancing_acquisitions_ready_not_engagement(self):
        calls = []
        lengths = []
        def scout(_target, _base, length, _milliseconds, attempt, _runner):
            calls.append(attempt); lengths.append(length)
            seq = len(calls)
            return [({"address": f"0x{0x200000 + seq:X}"},
                     wire(frame(seq, 10 + seq)))]
        output = self.root / "out"
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, output,
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout,
            capture_known=lambda *_args: [])
        self.assertTrue(result["telemetry"]["ready"])
        self.assertFalse(result["engagement"]["ready"])
        self.assertEqual([1, 2], [s["sequence"] for s in result["sources"]])
        self.assertEqual([16 * 1024 * 1024, 2 * 1024 * 1024], lengths)
        self.assertTrue(result["catalog"]["complete"])
        self.assertTrue((output / "result.json").is_file())

    def test_known_address_batch_can_advance_without_another_scout(self):
        scout_calls = 0
        def scout(*_args):
            nonlocal scout_calls
            scout_calls += 1
            return [({"address": "0x200000"}, wire(frame(1, 11)))]
        cached_calls = 0
        def cached(_target, addresses, _prefix, _runner):
            nonlocal cached_calls
            cached_calls += 1
            self.assertEqual([0x200000], addresses)
            return [({"address": "0x200000"}, wire(frame(2, 12)))]
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "cached",
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout, capture_known=cached)
        self.assertEqual(1, scout_calls)
        self.assertEqual(1, cached_calls)
        self.assertFalse(result["attempts"][1]["boundedScoutPerformed"])

    def test_narrow_pool_miss_falls_back_to_full_admitted_span_once(self):
        lengths = []
        def scout(_target, _base, length, *_args):
            lengths.append(length)
            sequence = 2 if len(lengths) == 3 else 1
            return [({"address": "0x200000"}, wire(frame(sequence, 10 + sequence)))]
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "fallback",
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout,
            capture_known=lambda *_args: [])
        self.assertEqual([16 * 1024 * 1024, 2 * 1024 * 1024,
                          16 * 1024 * 1024], lengths)
        second = result["attempts"][1]
        self.assertTrue(second["fullSpanFallbackPerformed"])
        self.assertEqual("full-admitted-span-scout", second["phases"][-1]["kind"])

    def test_failed_cached_read_is_discarded_then_rescouts(self):
        scout_calls = 0
        def scout(*_args):
            nonlocal scout_calls
            scout_calls += 1
            return [({"address": "0x200000"}, wire(frame(
                scout_calls, 10 + scout_calls)))]
        def failed_cache(*_args):
            raise live.CaptureError("stale-address-unreadable")
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "cache-failure",
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout, capture_known=failed_cache)
        phase = result["attempts"][1]["phases"][0]
        self.assertEqual("unavailable", phase["status"])
        self.assertEqual(2, result["sourceWindow"]["lastSequence"])

    def test_recent_cancel_reference_needs_no_ability_readiness(self):
        value = frame(1, 11)
        value["targetId"] = "u0000000000000002"
        value["controls"] = {
            "space": "UIParent", "actions": {},
            "cancel": {"mapped": True, "visible": True, "left": 10, "top": 20,
                       "width": 100, "height": 40}}
        consumer = live.SurvivalLiveConsumer(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "cancel-ref",
            selector=self.selector, adapter_factory=Adapter,
            scout_once=lambda *_args: [({"address": "0x200000"}, wire(value))],
            capture_known=lambda *_args: [])
        consumer.snapshot()
        reference = consumer.cancel_reference(max_age_seconds=5)
        self.assertEqual("cached-verified-cancel", reference["status"])
        self.assertFalse(reference["abilityReadinessRequired"])
        self.assertIn("exact-current-selected-target",
                      reference["requiredExecutionChecks"])
        consumer.latest_reference["acceptedAtMonotonic"] -= 6
        with self.assertRaisesRegex(live.SurvivalLiveError, "cancel-reference-expired"):
            consumer.cancel_reference(max_age_seconds=5)

    def test_history_in_one_scan_does_not_replace_second_acquisition(self):
        history = [({"address": "0x1"}, wire(frame(1, 10))),
                   ({"address": "0x2"}, wire(frame(2, 11)))]
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "advancing-survival-frames-not-observed"):
            live.acquire(
                "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "stale",
                interval_milliseconds=0, max_attempts=2,
                selector=self.selector, adapter_factory=Adapter,
                scout_once=lambda *_args: history,
                capture_known=lambda *_args: [])

    def test_advancing_unavailable_frames_do_not_make_telemetry_ready(self):
        count = 0
        def scout(*_args):
            nonlocal count
            count += 1
            value = frame(count, 10 + count); value["status"] = "unavailable"
            return [({"address": "0x1"}, wire(value))]
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "advancing-survival-frames-not-observed"):
            live.acquire(
                "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "unavailable",
                interval_milliseconds=0, max_attempts=2,
                selector=self.selector, adapter_factory=Adapter, scout_once=scout,
                capture_known=lambda *_args: [])

    def test_partial_catalog_is_explicitly_unsupported(self):
        count = 0
        def scout(*_args):
            nonlocal count
            count += 1
            return [({"address": "0x1"}, wire(frame(
                count, 10 + count, pages=2, entries={"A1": "Defend"})))]
        result = live.acquire(
            "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "partial",
            interval_milliseconds=0, selector=self.selector,
            adapter_factory=Adapter, scout_once=scout,
            capture_known=lambda *_args: [])
        self.assertFalse(result["catalog"]["complete"])
        self.assertIn("complete-learned-ability-catalog", result["unsupportedFields"])

    def test_conflicting_same_generation_is_rejected(self):
        changed = frame(1, 10)
        changed["player"]["health"] = 99
        calls = 0
        def scout(*_args):
            nonlocal calls
            calls += 1
            return [({"address": "0x1"}, wire(frame(1, 10) if calls == 1 else changed))]
        with self.assertRaisesRegex(live.SurvivalLiveError,
                                    "conflicting-survival-generation"):
            live.acquire(
                "AMD-DESKTOP", 21672, NONCE, self.seed, self.root / "conflict",
                interval_milliseconds=0, max_attempts=2,
                selector=self.selector, adapter_factory=Adapter,
                scout_once=scout, capture_known=lambda *_args: [])

    def test_malformed_catalog_and_duplicate_json_fail_closed(self):
        value = frame()
        value["catalog"]["entries"] = {str(i): "x" for i in range(9)}
        with self.assertRaisesRegex(live.SurvivalLiveError, "catalog-entries"):
            live.decode_frame(wire(value), NONCE, PLAYER)
        raw = (live.MARKER + b'{"schemaVersion":1,"schemaVersion":1}'
               + live.SUFFIX)
        with self.assertRaisesRegex(live.SurvivalLiveError, "duplicate-survival-frame-key"):
            live.decode_frame(raw, NONCE, PLAYER)

    def test_cli_bad_nonce_blocks_before_live_read(self):
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            code = live.main([
                "--expected-host", "AMD-DESKTOP", "--physical-pid", "21672",
                "--session-id", "BAD", "--seed-index", str(self.seed),
                "--output", str(self.root / "never")])
        result = json.loads(buffer.getvalue())
        self.assertEqual(2, code)
        self.assertFalse(result["ready"])
        self.assertFalse(result["inputSent"])
        self.assertEqual("invalid-survival-session-id", result["reason"])


if __name__ == "__main__":
    unittest.main()
