"""Focused Lua 5.1 tests for the read-only casting state model."""
from __future__ import annotations

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "addon" / "RiftReader2Casting"
TOC = PACKAGE / "RiftAddon.toc"
MODEL = PACKAGE / "model.lua"
MAIN = PACKAGE / "main.lua"


API_FACTORY = r"""
return function(state)
    local counts = { lookup = 0, detail = 0, ability = 0, legacyAbility = 0 }
    local api = {
        System = { Secure = function()
            if state.secureError then error("secure state error") end
            return state.secure == true
        end },
        Time = { Frame = function()
            if state.clockError then error("clock error") end
            return state.clock
        end },
        Unit = {
            Lookup = function(specifier)
                counts.lookup = counts.lookup + 1
                if state.lookupError then error("lookup error") end
                if specifier == "player" then
                    if state.changePlayer and counts.lookup >= 3 then return "player-changed" end
                    return state.playerId
                end
                if specifier == "player.target" then
                    if state.changeTarget and counts.lookup >= 4 then return "target-changed" end
                    return state.targetId
                end
            end,
            Detail = function(id)
                counts.detail = counts.detail + 1
                if state.detailError then error("detail error") end
                return state.units[id]
            end,
            Castbar = function()
                if state.castError then error("cast error") end
                return state.cast
            end,
        },
        Ability = {
            Detail = function(id)
                counts.legacyAbility = counts.legacyAbility + 1
                if state.legacyAbilityError then error("legacy ability error") end
                return state.legacyAbilities[id]
            end,
            New = {
                List = function()
                    if state.listError then error("list error") end
                    return state.abilityList
                end,
                Detail = function(id)
                    counts.ability = counts.ability + 1
                    if state.abilityError then error("ability error") end
                    return state.abilities[id]
                end,
            },
        },
    }
    return api, counts
end
"""


UI_STUB = r"""
TEST_HANDLERS = {}
TEST_MACROS = {}
TEST_SECURE_MODES = {}
TEST_MACRO_FAILURE = false
local function frame(name)
    local value = { frameName = name }
    for _, name in ipairs({"SetPoint", "SetWidth", "SetHeight", "SetBackgroundColor", "SetLayer",
        "SetVisible", "SetFontSize", "SetText"}) do
        value[name] = function(self, ...) self[name .. "Value"] = {...} end
    end
    value.EventAttach = function(self, event, handler, label) TEST_HANDLERS[label] = handler end
    value.SetSecureMode = function(self, mode) TEST_SECURE_MODES[self.frameName] = mode end
    value.EventMacroSet = function(self, event, macro)
        if TEST_MACRO_FAILURE then error("macro configuration rejected") end
        TEST_MACROS[self.frameName] = macro
    end
    return value
end
UI = {
    CreateContext = function(name) return frame(name) end,
    CreateFrame = function(kind, name) return frame(name) end,
}
UIParent = {}
Event = {
    UI = { Input = { Mouse = { Left = { Click = {} } } } },
    System = { Update = { Begin = {} } },
    Addon = { SavedVariables = { Load = { End = {} } } },
    Ability = { New = { Cooldown = { Begin = {}, End = {} } } },
    Combat = { Damage = {}, Miss = {}, Immune = {}, Resist = {}, Dodge = {}, Parry = {} },
}
Command = {
    Event = { Attach = function(event, handler, label) TEST_HANDLERS[label] = handler end },
    Slash = { Register = function() return {} end },
}
"""


class CastingAddonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        private = self.lua.table()
        self.lua.execute(MODEL.read_text(encoding="utf-8"),
                         self.lua.table(identifier="RiftReader2Casting"), private)
        self.module = private.Casting
        self.factory = self.lua.execute(API_FACTORY)

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({key: self.table(item) for key, item in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(item) for item in value])
        return value

    def state(self, **updates):
        state = {
            "clock": 100.0,
            "playerId": "player-1",
            "targetId": "dummy-1",
            "units": {
                "player-1": {"id": "player-1", "name": "Atank", "health": 18208,
                             "healthMax": 18208, "power": 100},
                "dummy-1": {"id": "dummy-1", "name": "Training Dummy", "health": 99999,
                            "healthMax": 99999, "relation": "hostile"},
            },
            "abilities": {
                "ability-old": {"id": "ability-old", "idNew": "ability-new", "name": "Practice Strike",
                                "target": "dummy-1", "costPower": 20,
                                "currentCooldownRemaining": 0},
                "ability-new": {"id": "ability-new", "idNew": "ability-new", "name": "Practice Strike",
                                "target": "dummy-1", "costPower": 20,
                                "currentCooldownRemaining": 0},
                "ability-alias": {"id": "ability-alias", "idNew": "ability-new", "name": "Practice Strike"},
            },
            "abilityList": {"ability-old": True},
            "legacyAbilities": {},
        }
        state.update(updates)
        return self.table(state)

    def model(self, state=None):
        state = state or self.state()
        api, counts = self.factory(state)
        return self.module.New(api), state, counts

    def test_package_metadata_and_load_order(self):
        read_toc = self.lua.eval(r"""function(source)
            local chunk = assert(loadstring(source))
            local metadata = {}
            setfenv(chunk, metadata)
            chunk()
            return metadata
        end""")
        metadata = read_toc(TOC.read_text(encoding="utf-8"))
        self.assertEqual(PACKAGE.name, metadata.Identifier)
        for field in ("Name", "Author", "Email"):
            value = metadata[field]
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), field)
        self.assertEqual("4.4", metadata.Environment)
        self.assertEqual("character", metadata.SavedVariables.RiftReader2CastingEvidence)
        startup = list(metadata.RunOnStartup.values())
        self.assertEqual(["model.lua", "main.lua"], startup)
        for name in startup:
            self.assertTrue((PACKAGE / name).is_file(), name)

    def test_secure_cast_button_configures_exact_selected_ability_only(self):
        private, _, counts = self.load_main()
        self.assertTrue(private.SelectAbility("ability-old"))
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual("cast Practice Strike",
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        self.assertEqual("restricted",
                         self.lua.globals().TEST_SECURE_MODES["RR2CastingSecure"])
        self.assertEqual("restricted",
                         self.lua.globals().TEST_SECURE_MODES["RR2CastingSecureButton"])
        self.assertIsNone(private.Instance.trial)
        self.assertIsNone(self.lua.globals().TEST_HANDLERS["RR2CastingSecureButton click"])
        self.assertGreater(counts.ability, 0)

    def test_stop_attack_is_separate_restricted_macro_without_automatic_trigger(self):
        private, _, _ = self.load_main()
        self.assertEqual("stopattack",
                         self.lua.globals().TEST_MACROS["RR2CastingStopButton"])
        self.assertEqual("restricted",
                         self.lua.globals().TEST_SECURE_MODES["RR2CastingStopButton"])
        self.assertIsNone(self.lua.globals().TEST_HANDLERS["RR2CastingStopButton click"])
        self.assertIsNone(private.Instance.trial)
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("stopattack",
                         self.lua.globals().TEST_MACROS["RR2CastingStopButton"])
        self.assertIsNone(private.Instance.trial)

    def test_secure_state_failure_does_not_change_existing_selection(self):
        private, state, _ = self.load_main()
        state.secure = True
        self.assertFalse(private.SelectAbility("ability-old"))
        self.assertIsNone(private.Instance.selected)
        self.assertIsNone(self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

        state.secure = False
        self.assertTrue(private.SelectAbility("ability-old"))
        original_macro = self.lua.globals().TEST_MACROS["RR2CastingSecureButton"]
        state.abilities["ability-second"] = self.table({
            "id": "ability-second", "name": "Second Strike", "target": "dummy-1",
            "currentCooldownRemaining": 0,
        })
        state.secure = True
        self.assertFalse(private.SelectAbility("ability-second"))
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual(original_macro,
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        state.secure = False
        state.secureError = True
        self.assertFalse(private.SelectAbility("ability-second"))
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual(original_macro,
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

    def test_trial_and_macro_failure_leave_selected_ability_unchanged(self):
        private, state, _ = self.load_main()
        state.abilities["ability-second"] = self.table({
            "id": "ability-second", "name": "Second Strike", "target": "dummy-1",
            "currentCooldownRemaining": 0,
        })
        self.assertTrue(private.SelectAbility("ability-old"))
        original_macro = self.lua.globals().TEST_MACROS["RR2CastingSecureButton"]

        self.assertTrue(private.Instance.Begin(private.Instance))
        self.assertFalse(private.SelectAbility("ability-second"))
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual(original_macro,
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

        private.Instance.trial.status = "finished"
        self.lua.globals().TEST_MACRO_FAILURE = True
        self.assertFalse(private.SelectAbility("ability-second"))
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual(original_macro,
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

    def test_macro_name_injection_and_unsupported_abilities_are_rejected(self):
        for mutation in ("newline", "passive", "positioned", "autoattack"):
            with self.subTest(mutation=mutation):
                private, state, _ = self.load_main()
                detail = {"id": "bad", "name": "Unsafe Strike", "target": "dummy-1",
                          "currentCooldownRemaining": 0}
                if mutation == "newline":
                    detail["name"] = "Unsafe\ncast Other"
                else:
                    detail[mutation] = True
                state.abilities["bad"] = self.table(detail)
                self.assertFalse(private.SelectAbility("bad"))
                self.assertIsNone(private.Instance.selected)
                self.assertIsNone(self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

    def selected(self, state=None):
        model, state, counts = self.model(state)
        self.assertTrue(model.Select(model, "ability-old"))
        return model, state, counts

    def load_main(self, state=None):
        state = state or self.state()
        api, counts = self.factory(state)
        self.lua.execute(UI_STUB)
        self.lua.globals().Inspect = api
        private = self.lua.table(Casting=self.module)
        self.lua.execute(MAIN.read_text(encoding="utf-8"),
                         self.lua.table(identifier="RiftReader2Casting"), private)
        return private, state, counts

    def test_ready_with_realistic_absent_optional_flags(self):
        model, _, _ = self.selected()
        result = model.Read(model)
        self.assertEqual("ready", result.status)
        self.assertEqual("observed-ready", result.reason)
        self.assertEqual("unverified", result.facingAndLineOfSight)
        self.assertIsNone(result.ability.unusable)

    def test_effective_cooldown_waits(self):
        state = self.state()
        state.abilities["ability-old"].currentCooldownRemaining = 1.25
        model, _, _ = self.selected(state)
        result = model.Read(model)
        self.assertEqual("waiting", result.status)
        self.assertEqual("cooldown-ability-or-gcd", result.reason)

    def test_invalid_cooldown_fails_closed(self):
        for value in (-0.01, float("nan"), float("inf")):
            with self.subTest(value=value):
                state = self.state()
                state.abilities["ability-old"].currentCooldownRemaining = value
                model, _, _ = self.selected(state)
                result = model.Read(model)
                self.assertEqual("blocked", result.status)
                self.assertEqual("invalid-cooldown", result.reason)

    def test_castbar_error_differs_from_valid_empty_castbar(self):
        model, _, _ = self.selected(self.state(castError=True))
        failed = model.Read(model)
        self.assertEqual("blocked", failed.status)
        self.assertEqual("cast-state-unavailable", failed.reason)

        model, _, _ = self.selected()
        ready = model.Read(model)
        self.assertEqual("ready", ready.status)

    def test_readiness_rejections(self):
        cases = (
            ("insufficient-or-unknown-power", lambda s: setattr(s.units["player-1"], "power", 10)),
            ("cast-or-channel-active", lambda s: setattr(s, "cast", self.table({"ability": "other", "remaining": 0.5}))),
            ("ability-unusable", lambda s: setattr(s.abilities["ability-old"], "unusable", True)),
            ("out-of-range", lambda s: setattr(s.abilities["ability-old"], "outOfRange", True)),
            ("cooldown-paused", lambda s: setattr(s.abilities["ability-old"], "currentCooldownPaused", True)),
        )
        for reason, mutate in cases:
            with self.subTest(reason=reason):
                state = self.state()
                mutate(state)
                model, _, _ = self.selected(state)
                result = model.Read(model)
                self.assertEqual(reason, result.reason)
                self.assertIn(result.status, ("blocked", "waiting"))

    def test_identity_change_fails_closed(self):
        model, _, _ = self.selected(self.state(changeTarget=True))
        result = model.Read(model)
        self.assertEqual("blocked", result.status)
        self.assertEqual("identity-changed", result.reason)

    def test_begin_is_observation_only_and_locks_selection(self):
        model, _, counts = self.selected()
        ok = model.Begin(model)
        self.assertTrue(ok)
        self.assertEqual("recording", model.trial.status)
        self.assertFalse(model.Select(model, "ability-new"))
        self.assertEqual("ability-old", model.selected)
        # Only read-side API calls exist in the supplied interface.
        self.assertGreater(counts.lookup, 0)
        self.assertGreater(counts.ability, 0)

    def test_hit_requires_player_target_and_ability_identity(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        wrong = (
            {"caster": "other", "target": "dummy-1", "ability": "ability-old", "damage": 5},
            {"caster": "player-1", "target": "other", "ability": "ability-old", "damage": 5},
            {"caster": "player-1", "target": "dummy-1", "ability": "other", "abilityName": "Practice Strike", "damage": 5},
            {"caster": "player-1", "target": "dummy-1", "abilityName": "Practice Strike", "damage": 5},
        )
        for event in wrong:
            model.Combat(model, "damage", self.table(event))
        self.assertFalse(model.trial.hit)

        model.Combat(model, "damage", self.table({"caster": "player-1", "target": "dummy-1",
                                            "ability": "ability-alias", "abilityName": "Localized Strike",
                                            "damage": 17, "crit": False}))
        self.assertTrue(model.trial.hit)
        self.assertTrue(model.trial.lastHit.matchesAbility)
        self.assertTrue(model.trial.lastHit.matchesTarget)
        self.assertEqual(17, model.trial.lastHit.damage)

    def test_legacy_ability_detail_can_normalize_combat_id_to_selected_new_id(self):
        state = self.state()
        state.legacyAbilities["combat-id"] = self.table({"idNew": "ability-new"})
        model, _, counts = self.selected(state)
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "combat-id",
            "abilityName": "Practice Strike", "damage": 23,
        }))
        self.assertTrue(model.trial.hit)
        self.assertEqual("ability-new", model.trial.lastHit.normalizedAbilityId)
        self.assertEqual("Inspect.Ability.Detail", model.trial.lastHit.abilityMappingSource)
        self.assertGreater(counts.legacyAbility, 0)

    def test_combat_ability_new_is_primary_exact_mapping(self):
        model, _, counts = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "combat-legacy-id",
            "abilityNew": "ability-new", "abilityName": "Practice Strike", "damage": 31,
        }))
        self.assertTrue(model.trial.hit)
        self.assertEqual("ability-new", model.trial.lastHit.normalizedAbilityId)
        self.assertEqual("Event.Combat.abilityNew", model.trial.lastHit.abilityMappingSource)
        self.assertEqual(0, counts.legacyAbility)

    def test_mismatched_combat_ability_new_is_not_overridden_by_name_or_legacy_mapping(self):
        state = self.state()
        state.legacyAbilities["combat-legacy-id"] = self.table({"idNew": "ability-new"})
        model, _, counts = self.selected(state)
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "combat-legacy-id",
            "abilityNew": "different-ability", "abilityName": "Practice Strike", "damage": 31,
        }))
        self.assertFalse(model.trial.hit)
        event = model.trial.events[1]
        self.assertFalse(event.matchesAbility)
        self.assertEqual("different-ability", event.normalizedAbilityId)
        self.assertEqual("Event.Combat.abilityNew", event.abilityMappingSource)
        self.assertEqual(0, counts.legacyAbility)

    def test_mismatched_ability_new_overrides_even_equal_selected_legacy_id(self):
        model, _, counts = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-old",
            "abilityNew": "different-ability", "abilityName": "Practice Strike", "damage": 31,
        }))
        self.assertFalse(model.trial.hit)
        event = model.trial.events[1]
        self.assertFalse(event.matchesAbility)
        self.assertEqual("different-ability", event.normalizedAbilityId)
        self.assertEqual("Event.Combat.abilityNew", event.abilityMappingSource)
        self.assertEqual(0, counts.legacyAbility)

    def test_mismatched_ability_new_overrides_even_equal_selected_modern_id(self):
        model, _, counts = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-new",
            "abilityNew": "different-ability", "abilityName": "Practice Strike", "damage": 31,
        }))
        self.assertFalse(model.trial.hit)
        event = model.trial.events[1]
        self.assertFalse(event.matchesAbility)
        self.assertEqual("different-ability", event.normalizedAbilityId)
        self.assertEqual("Event.Combat.abilityNew", event.abilityMappingSource)
        self.assertEqual(0, counts.legacyAbility)

    def test_empty_case_changed_and_oversized_ability_new_ids_cannot_hit(self):
        for value in ("", "ABILITY-NEW", "x" * 2049):
            with self.subTest(length=len(value), value=value[:20]):
                model, _, _ = self.selected()
                self.assertTrue(model.Begin(model))
                model.Combat(model, "damage", self.table({
                    "caster": "player-1", "target": "dummy-1", "ability": "combat-id",
                    "abilityNew": value, "abilityName": "Practice Strike", "damage": 31,
                }))
                self.assertFalse(model.trial.hit)
                event = model.trial.events[1]
                self.assertFalse(event.matchesAbility)
                if value == "" or len(value) > 128:
                    self.assertIsNone(event.normalizedAbilityId)
                else:
                    self.assertEqual(value, event.normalizedAbilityId)

    def test_missing_errored_wrong_or_name_only_legacy_mapping_cannot_hit(self):
        cases = (
            ("missing", {}, False),
            ("error", {}, True),
            ("wrong", {"combat-id": {"idNew": "different-ability"}}, False),
        )
        for label, mappings, legacy_error in cases:
            with self.subTest(label=label):
                state = self.state(legacyAbilityError=legacy_error)
                for key, value in mappings.items():
                    state.legacyAbilities[key] = self.table(value)
                model, _, _ = self.selected(state)
                self.assertTrue(model.Begin(model))
                model.Combat(model, "damage", self.table({
                    "caster": "player-1", "target": "dummy-1", "ability": "combat-id",
                    "abilityName": "Practice Strike", "damage": 23,
                }))
                self.assertFalse(model.trial.hit)
                event = model.trial.events[1]
                self.assertFalse(event.matchesAbility)
                if label == "wrong":
                    self.assertEqual("different-ability", event.normalizedAbilityId)
                    self.assertEqual("Inspect.Ability.Detail", event.abilityMappingSource)
                else:
                    self.assertIsNone(event.normalizedAbilityId)
                    self.assertIsNone(event.abilityMappingSource)

        model, _, _ = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1",
            "abilityName": "Practice Strike", "damage": 23,
        }))
        self.assertFalse(model.trial.hit)

    def test_new_mapping_prevents_fallback_to_conflicting_legacy_mapping(self):
        state = self.state()
        state.abilities["combat-id"] = self.table({"id": "different-ability", "name": "Practice Strike"})
        state.legacyAbilities["combat-id"] = self.table({"idNew": "ability-new"})
        model, _, counts = self.selected(state)
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "combat-id",
            "abilityName": "Practice Strike", "damage": 23,
        }))
        self.assertFalse(model.trial.hit)
        self.assertEqual("different-ability", model.trial.events[1].normalizedAbilityId)
        self.assertEqual("Inspect.Ability.New.Detail", model.trial.events[1].abilityMappingSource)
        self.assertEqual(0, counts.legacyAbility)

    def test_target_change_aborts_recording_before_event(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        state.targetId = "dummy-2"
        model.Combat(model, "damage", self.table({"caster": "player-1", "target": "dummy-1",
                                            "ability": "ability-old", "damage": 20}))
        self.assertEqual("aborted", model.trial.status)
        self.assertEqual("target-or-player-changed", model.trial.reason)
        self.assertFalse(model.trial.hit)

    def test_trial_expires_with_explicit_no_hit_result(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        state.clock = 161
        model.Read(model)
        self.assertEqual("finished", model.trial.status)
        self.assertEqual("no-matching-damage-observed", model.trial.reason)

    def test_snapshot_fault_cannot_become_a_hit(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        state.clockError = True
        model.Combat(model, "damage", self.table({"caster": "player-1", "target": "dummy-1",
                                                   "ability": "ability-old", "damage": 30}))
        self.assertFalse(model.trial.hit)
        state.clockError = False
        state.clock = 161
        model.Read(model)
        self.assertEqual("no-matching-damage-observed", model.trial.reason)

    def test_cooldown_events_keep_only_selected_ability_during_window(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))

        model.Cooldown(model, "begin", self.table({"other": 2.0}))
        self.assertEqual(0, len(model.trial.cooldowns))
        model.Cooldown(model, "begin", self.table({"ability-old": 1.25, "other": 2.0}))
        model.Cooldown(model, "end", self.table({"ability-new": 0}))
        self.assertEqual(2, len(model.trial.cooldowns))
        self.assertEqual("begin", model.trial.cooldowns[1].kind)
        self.assertEqual(1.25, model.trial.cooldowns[1].remaining)
        self.assertEqual("end", model.trial.cooldowns[2].kind)

        state.clock = 161
        model.Cooldown(model, "begin", self.table({"ability-old": 1.0}))
        self.assertEqual(2, len(model.trial.cooldowns))

    def test_cooldown_evidence_is_bounded(self):
        model, _, _ = self.selected()
        self.assertTrue(model.Begin(model))
        values = self.table({"ability-old": 1.0})
        for _ in range(70):
            model.Cooldown(model, "begin", values)
        self.assertEqual(64, len(model.trial.cooldowns))

    def test_evidence_lists_are_bounded(self):
        model, _, _ = self.selected()
        self.assertTrue(model.Begin(model))
        event = self.table({"caster": "player-1", "target": "dummy-1",
                            "ability": "ability-old", "damage": 1})
        for _ in range(70):
            model.Combat(model, "miss", event)
        for _ in range(650):
            model.Read(model)
        self.assertEqual(64, len(model.trial.events))
        self.assertTrue(model.trial.eventsTruncated)
        self.assertEqual(630, len(model.trial.samples))

    def test_api_errors_become_unavailable_instead_of_escaping(self):
        model, state, _ = self.model(self.state(abilityError=True))
        self.assertFalse(model.Select(model, "ability-old"))
        self.assertEqual(0, len(model.Abilities(model)))

        model, _, _ = self.selected(self.state(clockError=True))
        result = model.Read(model)
        self.assertEqual("blocked", result.status)
        self.assertEqual("player-unavailable", result.reason)

    def test_main_dispatches_modern_event_handle_prefix_without_false_hit(self):
        # Command.Event.Attach prepends the standard event handle. This exercises
        # the real wrappers rather than the legacy table.insert callback shape.
        private, state, _ = self.load_main()
        instance = private.Instance
        self.assertTrue(instance.Select(instance, "ability-old"))
        self.assertTrue(instance.Begin(instance))
        handlers = self.lua.globals().TEST_HANDLERS

        wrong = self.table({"caster": "player-1", "target": "dummy-1",
                            "ability": "other", "abilityName": "Practice Strike", "damage": 9})
        handlers["RR2 casting damage"](self.lua.globals().Event.Combat.Damage, wrong)
        self.assertFalse(instance.trial.hit)

        hit = self.table({"caster": "player-1", "target": "dummy-1",
                          "ability": "ability-old", "abilityName": "Practice Strike", "damage": 11})
        handlers["RR2 casting damage"](self.lua.globals().Event.Combat.Damage, hit)
        self.assertTrue(instance.trial.hit)

        handlers["RR2 casting cooldown Begin"](
            self.lua.globals().Event.Ability.New.Cooldown.Begin,
            self.table({"ability-old": 1.1, "other": 4.0}))
        self.assertEqual(1, len(instance.trial.cooldowns))
        self.assertEqual(1.1, instance.trial.cooldowns[1].remaining)

        handlers["RR2 casting readout"](self.lua.globals().Event.System.Update.Begin)
        handlers["RR2 casting saved evidence"](
            self.lua.globals().Event.Addon.SavedVariables.Load.End, "RiftReader2Casting")
        evidence = self.lua.globals().RiftReader2CastingEvidence
        self.assertIsNotNone(evidence.loadedAt)
        self.assertTrue(evidence.trial.hit)


if __name__ == "__main__":
    unittest.main()
