"""Focused Lua 5.1 tests for the optional Casting ability reference wire."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

from tests.test_casting_addon import API_FACTORY


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "addon" / "RiftReader2Casting"
MODEL = PACKAGE / "model.lua"
REFERENCE = PACKAGE / "ability_reference.lua"
ABILITY = "A0865F2DE73516486"


STUB = r"""
TEST_HANDLERS = {}
Event = { System = { Update = { Begin = {} } } }
Command = {
    Event = { Attach = function(event, handler, label) TEST_HANDLERS[label] = handler end },
    Slash = { Register = function() error("reference must not register slash commands") end },
}
UI = setmetatable({}, {__index = function() error("reference must not create UI") end})
"""


class CastingAbilityReferenceTests(unittest.TestCase):
    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({key: self.table(item) for key, item in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(item) for item in value])
        return value

    def state(self, **updates):
        state = {
            "clock": 100.0,
            "playerId": "uPLAYER",
            "targetId": "uPLAYER",
            "units": {
                "uPLAYER": {"id": "uPLAYER", "name": "Trio", "health": 9000,
                            "healthMax": 9000, "mana": 3980, "combat": False},
            },
            "abilities": {
                ABILITY: {"id": ABILITY, "idNew": ABILITY, "name": "Lifebound Veil",
                          "target": "uPLAYER", "costMana": 15,
                          "currentCooldownRemaining": 0, "currentCooldownPaused": False,
                          "unusable": False, "outOfRange": False, "passive": False,
                          "positioned": False, "autoattack": False},
            },
            "abilityList": {ABILITY: True}, "cast": {}, "legacyAbilities": {},
        }
        state.update(updates)
        return self.table(state)

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        self.private = self.lua.table()
        self.lua.execute(MODEL.read_text(encoding="utf-8"),
                         self.lua.table(identifier="RiftReader2Casting"), self.private)
        self.factory = self.lua.execute(API_FACTORY)
        self.state_value = self.state()
        api, self.counts = self.factory(self.state_value)
        self.lua.globals().Inspect = api
        addon = self.lua.table(identifier="RiftReader2Casting",
                               toc=self.lua.table(Version="0.4.1"))
        self.lua.execute(REFERENCE.read_text(encoding="utf-8"), addon, self.private)
        self.reference = self.private.AbilityReference

    def wire(self):
        raw = self.lua.globals().RiftReader2CastingAbilityReferenceWire
        self.assertIsInstance(raw, str)
        self.assertTrue(raw.startswith("RR2CASTREF1|") and raw.endswith("|RR2CASTREFEND"))
        return json.loads(raw[len("RR2CASTREF1|"):-len("|RR2CASTREFEND")])

    def test_ready_self_target_is_typed_observation_only(self):
        value = self.wire()
        self.assertEqual(1, value["schemaVersion"])
        self.assertEqual("0.4.1", value["addonVersion"])
        self.assertEqual("ready", value["readiness"]["status"])
        self.assertEqual("observed-ready", value["readiness"]["reason"])
        self.assertEqual({"status": "ok", "kind": "number", "value": 15},
                         value["ability"]["costMana"])
        self.assertEqual("uPLAYER", value["ability"]["target"]["value"])
        self.assertEqual(3980, value["player"]["mana"]["value"])
        self.assertFalse(value["actionAllowed"])
        self.assertEqual("unverified", value["facingAndLineOfSight"])
        self.assertEqual("external-deployment-receipt-required",
                         value["lineage"]["installedSourceSha256"])
        self.assertIn("RR2 casting ability reference", self.lua.globals().TEST_HANDLERS)

    def test_no_target_and_effective_target_mismatch_fail_closed(self):
        self.state_value.targetId = None
        self.state_value.clock = 100.3
        self.reference.Refresh(True)
        self.assertEqual("no-target", self.wire()["readiness"]["reason"])

        self.state_value.targetId = "uOTHER"
        self.state_value.units["uOTHER"] = self.table({"id": "uOTHER", "name": "Other",
                                                       "health": 1000})
        self.state_value.clock = 100.6
        self.reference.Refresh(True)
        self.assertEqual("ability-target-mismatch", self.wire()["readiness"]["reason"])

    def test_cooldown_cast_unusable_and_insufficient_mana_are_preserved(self):
        cases = (
            ({"currentCooldownRemaining": 2}, "cooldown-ability-or-gcd", "waiting"),
            ({"currentCooldownPaused": True}, "cooldown-paused", "blocked"),
            ({"unusable": True}, "ability-unusable", "blocked"),
            ({"costMana": 4000}, "insufficient-or-unknown-mana", "blocked"),
        )
        original = self.state_value.abilities[ABILITY]
        for changes, reason, status in cases:
            with self.subTest(reason=reason):
                ability = {key: value for key, value in original.items()}
                ability.update(changes)
                self.state_value.abilities[ABILITY] = self.table(ability)
                self.state_value.clock = self.state_value.clock + 0.3
                self.reference.Refresh(True)
                value = self.wire()
                self.assertEqual(reason, value["readiness"]["reason"])
                self.assertEqual(status, value["readiness"]["status"])
        self.state_value.abilities[ABILITY] = original
        self.state_value.cast = self.table({"ability": ABILITY, "abilityName": "Lifebound Veil"})
        self.state_value.clock = self.state_value.clock + 0.3
        self.reference.Refresh(True)
        self.assertEqual("cast-or-channel-active", self.wire()["readiness"]["reason"])

    def test_invalid_cost_name_id_and_identity_drift_fail_closed(self):
        ability = self.state_value.abilities[ABILITY]
        ability.costMana = "15"
        self.state_value.clock = 100.3
        self.reference.Refresh(True)
        value = self.wire()
        self.assertEqual("invalid", value["ability"]["costMana"]["status"])
        self.assertEqual("invalid-ability-cost", value["readiness"]["reason"])

        ability.costMana = 15
        ability.name = "Wrong"
        self.state_value.clock = 100.6
        self.reference.Refresh(True)
        self.assertEqual("ability-name-mismatch", self.wire()["readiness"]["reason"])

        ability.name = "Lifebound Veil"
        ability.idNew = "AOTHER"
        self.state_value.clock = 100.9
        self.reference.Refresh(True)
        self.assertEqual("ability-id-mismatch", self.wire()["readiness"]["reason"])

        ability.idNew = ABILITY
        self.counts.lookup = 0
        self.state_value.changeTarget = True
        self.state_value.clock = 101.2
        self.reference.Refresh(True)
        self.assertEqual("identity-changed-after-detail", self.wire()["readiness"]["reason"])

    def test_changed_second_ability_detail_is_serialized_but_never_ready(self):
        self.state_value.changeAbilityAfter = self.counts.abilityScalar + 2
        self.state_value.changedCooldown = 9
        self.state_value.clock = 100.3
        self.reference.Refresh(True)
        value = self.wire()
        self.assertEqual("blocked", value["readiness"]["status"])
        self.assertEqual("ability-detail-inconsistent", value["readiness"]["reason"])
        self.assertEqual(9, value["ability"]["currentCooldownRemaining"]["value"])

    def test_invalid_clock_publishes_once_suppresses_work_and_recovers(self):
        handler = self.lua.globals().TEST_HANDLERS["RR2 casting ability reference"]
        initial = self.wire()
        ability_calls = self.counts.ability
        lookup_calls = self.counts.lookup
        self.state_value.clock = "invalid"

        handler()
        invalid = self.wire()
        self.assertEqual(initial["sequence"] + 1, invalid["sequence"])
        self.assertEqual("frame-clock-invalid", invalid["readiness"]["reason"])
        self.assertEqual(ability_calls, self.counts.ability)
        self.assertEqual(lookup_calls, self.counts.lookup)

        handler()
        self.assertEqual(invalid["sequence"], self.wire()["sequence"])
        self.assertEqual(ability_calls, self.counts.ability)
        self.assertEqual(lookup_calls, self.counts.lookup)

        # Recovery bypasses the ordinary 250 ms cadence so the invalid frame
        # cannot linger merely because the finite clock is near the last one.
        self.state_value.clock = 100.1
        handler()
        recovered = self.wire()
        self.assertEqual(invalid["sequence"] + 1, recovered["sequence"])
        self.assertEqual("ready", recovered["readiness"]["status"])
        self.assertGreater(self.counts.ability, ability_calls)

    def test_cadence_is_bounded_and_wire_is_deterministic(self):
        first = self.wire()
        handler = self.lua.globals().TEST_HANDLERS["RR2 casting ability reference"]
        handler()
        self.assertEqual(first["sequence"], self.wire()["sequence"])
        self.state_value.clock = 100.26
        handler()
        second = self.wire()
        self.assertEqual(first["sequence"] + 1, second["sequence"])
        encoded = self.lua.globals().RiftReader2CastingAbilityReferenceJson
        self.assertLessEqual(len(encoded.encode("utf-8")), 8192)
        self.assertEqual(encoded, json.dumps(second, sort_keys=True, separators=(",", ":")))

    def test_missing_api_publishes_blocked_without_ui_or_action(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(STUB)
        private = lua.table()
        lua.execute(MODEL.read_text(encoding="utf-8"),
                    lua.table(identifier="RiftReader2Casting"), private)
        lua.globals().Inspect = lua.table()
        lua.execute(REFERENCE.read_text(encoding="utf-8"),
                    lua.table(identifier="RiftReader2Casting"), private)
        snapshot = lua.globals().RiftReader2CastingAbilityReference
        self.assertEqual("blocked", snapshot.readiness.status)
        self.assertFalse(snapshot.actionAllowed)


if __name__ == "__main__":
    unittest.main()
