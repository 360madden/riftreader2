"""Focused Lua 5.1 tests for the read-only casting state model."""
from __future__ import annotations

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "addon" / "RiftReader2Casting"
TOC = PACKAGE / "RiftAddon.toc"
MODEL = PACKAGE / "model.lua"
COMMANDS = PACKAGE / "commands.lua"
MAIN = PACKAGE / "main.lua"


API_FACTORY = r"""
return function(state)
    local counts = { lookup = 0, detail = 0, ability = 0, abilityList = 0,
        abilityBatch = 0, abilityScalar = 0, legacyAbility = 0 }
    local api = {
        System = { Secure = function()
            if state.secureError then error("secure state error") end
            return state.secure == true
        end },
        Time = { Frame = function()
            if state.clockError then error("clock error") end
            return state.clock
        end },
        Mouse = function() return TEST_MOUSE end,
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
                    counts.abilityList = counts.abilityList + 1
                    if state.listError then error("list error") end
                    return state.abilityList
                end,
                Detail = function(id)
                    counts.ability = counts.ability + 1
                    if state.abilityError then error("ability error") end
                    if type(id) == "table" then
                        counts.abilityBatch = counts.abilityBatch + 1
                        local result = {}
                        for key in pairs(id) do result[key] = state.abilities[key] end
                        return result
                    end
                    counts.abilityScalar = counts.abilityScalar + 1
                    local result = state.abilities[id]
                    if state.changeAbilityAfter and counts.abilityScalar >= state.changeAbilityAfter and
                            type(result) == "table" then
                        local changed = {}
                        for key, value in pairs(result) do changed[key] = value end
                        changed.currentCooldownRemaining = state.changedCooldown
                        return changed
                    end
                    return result
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
TEST_FRAMES = {}
TEST_SLASH = {}
TEST_CHAT = {}
TEST_PRINT = {}
TEST_CONSOLE_FAILURE = false
TEST_MOUSE = {x = 350, y = 115, Left = false}
TEST_VIEWPORT = {width = 1920, height = 1080}
TEST_POINT_FAILURE = {}
print = function(message) TEST_PRINT[#TEST_PRINT + 1] = message end
local function frame(name, kind, parent)
    local value = { frameName = name, frameKind = kind, frameParent = parent }
    TEST_FRAMES[name] = value
    for _, name in ipairs({"SetPoint", "SetWidth", "SetHeight", "SetBackgroundColor", "SetLayer",
        "SetVisible", "SetFontSize", "SetFontColor", "SetWordwrap", "SetText",
        "SetMouseMasking"}) do
        value[name] = function(self, ...) self[name .. "Value"] = {...} end
    end
    value.SetPoint = function(self, ...)
        if TEST_POINT_FAILURE[self.frameName] then return false end
        self.SetPointValue = {...}
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
    CreateContext = function(name) return frame(name, "Context") end,
    CreateFrame = function(kind, name, parent) return frame(name, kind, parent) end,
}
UIParent = {
    GetWidth = function() return TEST_VIEWPORT.width end,
    GetHeight = function() return TEST_VIEWPORT.height end,
}
Event = {
    UI = { Input = { Mouse = {
        Left = { Click = {}, Down = {}, Up = {}, Upoutside = {} },
        Cursor = { Move = {} },
    } } },
    System = { Update = { Begin = {} } },
    Addon = { Load = { End = {} }, SavedVariables = { Load = { End = {} } } },
    Ability = { New = { Cooldown = { Begin = {}, End = {} } } },
    Combat = { Damage = {}, Heal = {}, Miss = {}, Immune = {}, Resist = {}, Dodge = {}, Parry = {} },
}
Command = {
    Console = { Display = function(channel, suppressPrefix, message, html)
        if TEST_CONSOLE_FAILURE then error("console unavailable") end
        TEST_CHAT[#TEST_CHAT + 1] = {channel = channel, suppressPrefix = suppressPrefix,
                                 message = message, html = html}
    end },
    Event = { Attach = function(event, handler, label) TEST_HANDLERS[label] = handler end },
    Slash = { Register = function() TEST_SLASH = {}; return TEST_SLASH end },
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
        self.assertEqual("0.5.1", metadata.Version)
        self.assertEqual("4.4", metadata.Environment)
        self.assertEqual("character", metadata.SavedVariables.RiftReader2CastingEvidence)
        startup = list(metadata.RunOnStartup.values())
        self.assertEqual(["model.lua", "ability_reference.lua", "survival.lua",
                          "commands.lua", "main.lua"], startup)
        for name in startup:
            self.assertTrue((PACKAGE / name).is_file(), name)

    def test_versioned_title_and_colored_initialization_once_per_load(self):
        self.load_main()
        globals_ = self.lua.globals()
        frames = globals_.TEST_FRAMES
        self.assertEqual("Casting", frames["RR2CastingTitle"].SetTextValue[1])
        self.assertEqual("v0.5.1", frames["RR2CastingVersion"].SetTextValue[1])
        for name in ("RR2CastingTitle", "RR2CastingVersion", "RR2CastingReason"):
            self.assertEqual(2, frames[name].SetLayerValue[1], name)
        notify = globals_.TEST_HANDLERS["RR2 casting initialized"]
        notify(None, "UnrelatedAddon")
        self.assertEqual(0, len(globals_.TEST_CHAT))
        notify(None, self.table({"identifier": "RiftReader2Casting"}))
        notify(None, "RiftReader2Casting")
        self.assertEqual(1, len(globals_.TEST_CHAT))
        notice = globals_.TEST_CHAT[1]
        self.assertEqual("general", notice.channel)
        self.assertTrue(notice.html)
        self.assertTrue(notice.suppressPrefix)
        self.assertIn('<font color="#52E3BB">', notice.message)
        self.assertIn("RiftReader2 Casting Readout v0.5.1 initialized.", notice.message)
        globals_.TEST_HANDLERS["RR2 casting saved evidence"](None, "RiftReader2Casting")
        self.assertEqual("0.5.1", globals_.RiftReader2CastingEvidence.addonVersion)
        self.assertEqual(1, len(globals_.TEST_CHAT))

    def test_initialization_fallback_color_and_metadata_validation(self):
        self.load_main(version="<malformed>")
        globals_ = self.lua.globals()
        self.assertEqual("Casting", globals_.TEST_FRAMES["RR2CastingTitle"].SetTextValue[1])
        self.assertEqual("v0.5.1", globals_.TEST_FRAMES["RR2CastingVersion"].SetTextValue[1])
        globals_.TEST_CONSOLE_FAILURE = True
        globals_.TEST_HANDLERS["RR2 casting initialized"](None, "RiftReader2Casting")
        self.assertEqual(0, len(globals_.TEST_CHAT))
        self.assertEqual(1, len(globals_.TEST_PRINT))
        self.assertIn("|cff52E3BBRiftReader2 Casting Readout v0.5.1 initialized.",
                      globals_.TEST_PRINT[1])
        self.assertTrue(globals_.TEST_PRINT[1].endswith("|r"))

    def test_version_uses_valid_runtime_toc_metadata(self):
        self.load_main(version="7.8.9")
        globals_ = self.lua.globals()
        self.assertEqual("Casting", globals_.TEST_FRAMES["RR2CastingTitle"].SetTextValue[1])
        self.assertEqual("v7.8.9", globals_.TEST_FRAMES["RR2CastingVersion"].SetTextValue[1])
        globals_.TEST_HANDLERS["RR2 casting initialized"](None, "RiftReader2Casting")
        self.assertIn("v7.8.9 initialized.", globals_.TEST_CHAT[1].message)

    def test_dashboard_uses_one_design_system_for_all_manual_actions(self):
        self.load_main()
        frames = self.lua.globals().TEST_FRAMES
        self.assertEqual((344, 226),
                         (frames["RR2CastingPanel"].SetWidthValue[1],
                          frames["RR2CastingPanel"].SetHeightValue[1]))
        self.assertEqual("RR2CastingHeader",
                         frames["RR2CastingHide"].frameParent.frameName)
        self.assertEqual(3, frames["RR2CastingHide"].SetLayerValue[1])
        self.assertEqual(28, frames["RR2CastingHide"].SetHeightValue[1])
        for name in ("RR2CastingAbilities", "RR2CastingRecord"):
            self.assertEqual("Frame", frames[name].frameKind, name)
            self.assertEqual(32, frames[name].SetHeightValue[1], name)
        for name in ("RR2CastingSecureButton", "RR2CastingStopButton"):
            self.assertEqual("Frame", frames[name].frameKind, name)
            self.assertEqual(38, frames[name].SetHeightValue[1], name)
        for name in ("RR2CastingAbilities", "RR2CastingRecord",
                     "RR2CastingSecureButton", "RR2CastingStopButton"):
            self.assertEqual("Text", frames[name + "Label"].frameKind, name)
            self.assertEqual(16, frames[name + "Label"].SetFontSizeValue[1], name)
            self.assertEqual("limited",
                             frames[name + "Label"].SetMouseMaskingValue[1], name)
            self.assertEqual(
                tuple(frames[name].SetBackgroundColorValue.values()),
                tuple(frames["RR2CastingAbilities"].SetBackgroundColorValue.values()),
                name,
            )
        self.assertEqual(
            tuple(frames["RR2CastingRecordFill"].SetBackgroundColorValue.values()),
            tuple(frames["RR2CastingSecureButtonFill"].SetBackgroundColorValue.values()),
        )
        for name in ("RR2CastingSecureButton", "RR2CastingStopButton"):
            self.assertEqual("restricted", self.lua.globals().TEST_SECURE_MODES[name])
            self.assertEqual("full", frames[name].SetMouseMaskingValue[1])
            self.assertIsNone(self.lua.globals().TEST_HANDLERS[name + " click"])
        self.assertEqual("stopattack",
                         self.lua.globals().TEST_MACROS["RR2CastingStopButton"])
        self.assertEqual((352, 464),
                         (frames["RR2CastingSecureButton"].SetPointValue[4],
                          frames["RR2CastingSecureButton"].SetPointValue[5]))
        self.assertEqual((561, 464),
                         (frames["RR2CastingStopButton"].SetPointValue[4],
                          frames["RR2CastingStopButton"].SetPointValue[5]))
        self.assertEqual((203, 111),
                         (frames["RR2CastingSecureButton"].SetWidthValue[1],
                          frames["RR2CastingStopButton"].SetWidthValue[1]))

    def test_facing_and_los_are_explicitly_unverified_not_ready(self):
        private, _, _ = self.load_main()
        frames = self.lua.globals().TEST_FRAMES
        self.assertTrue(private.SelectAbility("ability-old"))
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("API READY",
                         frames["RR2CastingStatus"].SetTextValue[1])
        self.assertEqual("Facing / LOS unverified",
                         frames["RR2CastingReason"].SetTextValue[1])
        state = self.lua.globals().RiftReader2CastingAPI.Snapshot().result.state.value
        self.assertEqual("unverified", state.facingAndLineOfSight)

    def test_cli_help_is_versioned_colored_and_explains_manual_limits(self):
        self.load_main()
        slash = self.lua.globals().TEST_SLASH[1][1]
        slash("  HeLp  ")
        chat = [line.message for line in self.lua.globals().TEST_CHAT.values()]
        self.assertGreaterEqual(len(chat), 7)
        joined = "\n".join(chat)
        self.assertIn("COMMAND GUIDE", joined)
        self.assertIn("v0.5.1", joined)
        for command in ("status", "info", "hide", "abilities", "record",
                        "position", "move X Y", "reset"):
            self.assertIn(command, joined)
        self.assertIn("manual clicks", joined)
        self.assertIn("UNVERIFIED", joined)
        self.assertTrue(all('<font color="#' in line for line in chat))
        self.assertIsNone(self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

    def test_cli_status_reports_api_details_not_facing_or_los_guesses(self):
        private, _, _ = self.load_main()
        self.assertTrue(private.SelectAbility("ability-old"))
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        slash = self.lua.globals().TEST_SLASH[1][1]
        slash("status")
        chat = [line.message for line in self.lua.globals().TEST_CHAT.values()]
        joined = "\n".join(chat)
        for expected in ("API READY", "Training Dummy", "Practice Strike",
                         "Range:", "Cast:", "Channel:", "cooldown:", "Power:",
                         "Facing: UNVERIFIED", "Line of sight: UNVERIFIED"):
            self.assertIn(expected, joined)
        self.assertEqual("cast Practice Strike",
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

    def test_programmatic_service_is_class_neutral_and_never_claims_game_action(self):
        state = self.state()
        state.units["player-1"].calling = "cleric"
        state.abilities["cleric-heal"] = self.table({
            "id": "cleric-heal", "idNew": "cleric-heal", "name": "Healing Breath",
            "target": "dummy-1", "costPower": 7, "currentCooldownRemaining": 0,
        })
        state.abilityList["cleric-heal"] = True
        private, _, _ = self.load_main(state)
        api = self.lua.globals().RiftReader2CastingAPI
        capabilities = api.Execute(self.table({
            "schemaVersion": 1, "command": "capabilities", "requestId": "caps-1",
        }))
        self.assertTrue(capabilities.accepted)
        self.assertFalse(capabilities.gameActionSent)
        self.assertEqual("not-performed", capabilities.effectStatus)
        self.assertFalse(capabilities.result.programmaticCast)
        self.assertEqual("existing-callback-status-only",
                         capabilities.result.stopControl)

        selected = api.Execute(self.table({
            "schemaVersion": 1, "command": "select", "abilityId": "cleric-heal",
        }))
        self.assertTrue(selected.accepted)
        self.assertFalse(selected.gameActionSent)
        self.assertFalse(selected.result.castPerformed)
        self.assertEqual("cleric-heal", private.Instance.selected)
        self.assertEqual("cast Healing Breath",
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        self.assertEqual("stopattack",
                         self.lua.globals().TEST_MACROS["RR2CastingStopButton"])
        self.assertIsNone(self.lua.globals().TEST_HANDLERS[
            "RR2CastingSecureButton click"])

    def test_hidden_record_and_configuration_do_not_clear_or_invent_stop(self):
        private, _, _ = self.load_main()
        globals_ = self.lua.globals()
        api = globals_.RiftReader2CastingAPI
        slash = globals_.TEST_SLASH[1][1]
        slash("hide")
        self.assertFalse(globals_.TEST_FRAMES["RR2CastingPanel"].SetVisibleValue[1])
        before_stop = globals_.TEST_MACROS["RR2CastingStopButton"]

        for request in (
            {"schemaVersion": 1, "command": "status"},
            {"schemaVersion": 1, "command": "select", "abilityId": "ability-old"},
            {"schemaVersion": 1, "command": "record"},
        ):
            reply = api.Execute(self.table(request))
            self.assertTrue(reply.accepted, request["command"])
            self.assertFalse(reply.gameActionSent, request["command"])
            self.assertEqual("not-performed", reply.effectStatus)

        self.assertFalse(globals_.TEST_FRAMES["RR2CastingPanel"].SetVisibleValue[1])
        self.assertEqual(before_stop, globals_.TEST_MACROS["RR2CastingStopButton"])
        status = api.Snapshot()
        self.assertEqual("unobserved", status.result.stop.value.globalStopLatch)
        self.assertFalse(status.result.stop.value.hudVisible)
        self.assertIsNone(globals_.TEST_HANDLERS["RR2 casting focus"])
        self.assertEqual("ability-old", private.Instance.selected)

    def test_hidden_hud_cannot_publish_clickable_cast_or_stop_rectangles(self):
        state = self.state()
        api, _ = self.factory(state)
        self.lua.execute(UI_STUB)
        self.lua.globals().Inspect = api
        private = self.lua.table(Casting=self.module)
        private.Survival = self.lua.execute(r"""return {
            Start=function(inspect, casting, select, rects)
                TEST_SURVIVAL_CONTROLS=rects
            end
        }""")
        metadata = self.lua.table(identifier="RiftReader2Casting",
                                  toc=self.lua.table(Version="0.5.0"))
        self.lua.execute(COMMANDS.read_text(encoding="utf-8"), metadata, private)
        self.lua.execute(MAIN.read_text(encoding="utf-8"), metadata, private)
        self.lua.execute(r"""
            UIParent.GetLeft=function() return 0 end
            UIParent.GetTop=function() return 0 end
            for _,name in ipairs({"RR2CastingSecureButton","RR2CastingStopButton"}) do
                local frame=TEST_FRAMES[name]
                frame.GetLeft=function(self) return self.SetPointValue[4] end
                frame.GetTop=function(self) return self.SetPointValue[5] end
                frame.GetWidth=function(self) return self.SetWidthValue[1] end
                frame.GetHeight=function(self) return self.SetHeightValue[1] end
            end
        """)
        self.assertTrue(private.SelectAbility("ability-old"))

        shown = self.lua.globals().TEST_SURVIVAL_CONTROLS("player-1", "dummy-1")
        self.assertTrue(shown.cast.mapped)
        self.assertTrue(shown.stop.mapped)
        self.assertEqual((352, 464, 203, 38),
                         (shown.cast.left, shown.cast.top,
                          shown.cast.width, shown.cast.height))
        self.assertEqual((561, 464, 111, 38),
                         (shown.stop.left, shown.stop.top,
                          shown.stop.width, shown.stop.height))
        self.lua.globals().TEST_HANDLERS["RR2CastingAbilities click"]()
        picker = self.lua.globals().TEST_SURVIVAL_CONTROLS("player-1", "dummy-1")
        self.assertFalse(picker.cast.mapped)
        self.assertFalse(picker.stop.mapped)
        self.lua.globals().TEST_HANDLERS["RR2CastingClose click"]()
        self.lua.globals().TEST_VIEWPORT.width = 300
        clipped = self.lua.globals().TEST_SURVIVAL_CONTROLS("player-1", "dummy-1")
        self.assertFalse(clipped.cast.mapped)
        self.assertFalse(clipped.stop.mapped)
        self.lua.globals().TEST_VIEWPORT.width = 1920
        self.lua.globals().TEST_SLASH[1][1]("hide")
        hidden = self.lua.globals().TEST_SURVIVAL_CONTROLS("player-1", "dummy-1")
        self.assertFalse(hidden.visible)
        self.assertFalse(hidden.cast.mapped)
        self.assertFalse(hidden.stop.mapped)
        self.assertEqual("cast Practice Strike",
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        self.assertEqual("stopattack",
                         self.lua.globals().TEST_MACROS["RR2CastingStopButton"])

    def test_cli_rejects_invalid_input_and_never_dispatches_cast_or_stop(self):
        private, state, _ = self.load_main()
        slash = self.lua.globals().TEST_SLASH[1][1]
        self.assertTrue(private.SelectAbility("ability-old"))
        initial_macro = self.lua.globals().TEST_MACROS["RR2CastingSecureButton"]
        stop_macro = self.lua.globals().TEST_MACROS["RR2CastingStopButton"]
        for argument in ("bogus", "show unexpected", "move 10",
                         "move nan 12", "move 1 2 extra", "x" * 97, 123):
            slash(argument)
            latest = self.lua.globals().TEST_CHAT[len(self.lua.globals().TEST_CHAT)].message
            self.assertTrue("Unknown" in latest or "Invalid" in latest
                            or "Unexpected" in latest or "Usage" in latest,
                            str(argument))
            self.assertEqual(initial_macro,
                             self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
            self.assertEqual(stop_macro,
                             self.lua.globals().TEST_MACROS["RR2CastingStopButton"])
        slash(None)  # Old no-argument command remains Show.
        self.assertTrue(self.lua.globals().TEST_FRAMES["RR2CastingPanel"].SetVisibleValue[1])
        state.secure = True
        slash("hide")
        self.assertTrue(self.lua.globals().TEST_FRAMES["RR2CastingPanel"].SetVisibleValue[1])
        self.assertIn("combat-lock",
                      self.lua.globals().TEST_CHAT[len(self.lua.globals().TEST_CHAT)].message)
        state.secure = False
        self.lua.globals().TEST_CONSOLE_FAILURE = True
        before = len(self.lua.globals().TEST_PRINT)
        slash("help")
        self.assertGreater(len(self.lua.globals().TEST_PRINT), before)
        self.assertIn("|cff", self.lua.globals().TEST_PRINT[before + 1])

    def test_drag_repositions_all_four_surfaces_and_clamps_to_viewport(self):
        self.load_main()
        globals_ = self.lua.globals()
        globals_.TEST_HANDLERS["RR2 casting saved evidence"](None, "RiftReader2Casting")
        frames, mouse = globals_.TEST_FRAMES, globals_.TEST_MOUSE
        mouse.x, mouse.y, mouse.Left = 350, 115, True
        handlers = globals_.TEST_HANDLERS
        handlers["RR2 casting drag start"]()
        mouse.x, mouse.y = 500, 215
        handlers["RR2 casting drag move"]()
        positions = {
            "RR2CastingPanel": (490, 384),
            "RR2CastingPicker": (490, 384),
            "RR2CastingSecureButton": (502, 564),
            "RR2CastingStopButton": (711, 564),
        }
        for name, (left, top) in positions.items():
            point = frames[name].SetPointValue
            self.assertEqual((left, top), (point[4], point[5]), name)
        self.assertEqual(490, globals_.RiftReader2CastingEvidence.hudPosition.x)
        self.assertEqual(384, globals_.RiftReader2CastingEvidence.hudPosition.y)
        mouse.x, mouse.y = 5000, 5000
        handlers["RR2 casting drag move"]()
        self.assertEqual(1920 - 344, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(1080 - 226, frames["RR2CastingPanel"].SetPointValue[5])
        self.assertEqual(1920 - 344 + 12,
                         frames["RR2CastingSecureButton"].SetPointValue[4])
        self.assertEqual(1080 - 226 + 180,
                         frames["RR2CastingStopButton"].SetPointValue[5])
        handlers["RR2 casting drag cancel"]()
        mouse.x, mouse.y = 100, 100
        handlers["RR2 casting drag move"]()
        self.assertEqual(1920 - 344, frames["RR2CastingPanel"].SetPointValue[4])

    def test_drag_does_not_continue_after_mouse_button_is_released(self):
        self.load_main()
        globals_ = self.lua.globals()
        frames, mouse, handlers = (globals_.TEST_FRAMES, globals_.TEST_MOUSE,
                                   globals_.TEST_HANDLERS)
        mouse.x, mouse.y, mouse.Left = 350, 115, True
        handlers["RR2 casting drag start"]()
        mouse.x, mouse.y, mouse.Left = 550, 250, False
        handlers["RR2 casting drag move"]()
        self.assertEqual(340, frames["RR2CastingPanel"].SetPointValue[4])
        mouse.Left = True
        handlers["RR2 casting drag move"]()  # Released drag must stay stopped.
        self.assertEqual(340, frames["RR2CastingPanel"].SetPointValue[4])

    def test_drag_combat_and_rejected_protected_move_fail_closed(self):
        _, state, _ = self.load_main()
        globals_ = self.lua.globals()
        frames, mouse, handlers = (globals_.TEST_FRAMES, globals_.TEST_MOUSE,
                                   globals_.TEST_HANDLERS)
        mouse.x, mouse.y, mouse.Left = 350, 115, True
        handlers["RR2 casting drag start"]()
        state.secure = True
        mouse.x, mouse.y = 650, 260
        handlers["RR2 casting drag move"]()
        self.assertEqual(340, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(340 + 12,
                         frames["RR2CastingSecureButton"].SetPointValue[4])
        state.secure = False
        mouse.x, mouse.y = 350, 115
        handlers["RR2 casting drag start"]()
        globals_.TEST_POINT_FAILURE["RR2CastingStopButton"] = True
        mouse.x, mouse.y = 650, 260
        handlers["RR2 casting drag move"]()
        self.assertEqual(340, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(340 + 12,
                         frames["RR2CastingSecureButton"].SetPointValue[4])
        self.assertEqual(340 + 221,
                         frames["RR2CastingStopButton"].SetPointValue[4])

    def test_picker_title_can_drag_without_covering_manual_action_tray(self):
        self.load_main()
        globals_ = self.lua.globals()
        frames, mouse, handlers = (globals_.TEST_FRAMES, globals_.TEST_MOUSE,
                                   globals_.TEST_HANDLERS)
        handlers["RR2CastingAbilities click"]()
        self.assertTrue(frames["RR2CastingPicker"].SetVisibleValue[1])
        mouse.x, mouse.y, mouse.Left = 320, 110, True
        handlers["RR2 casting drag start picker"]()
        mouse.x, mouse.y = 420, 210
        handlers["RR2 casting drag move picker"]()
        self.assertEqual(440, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(384, frames["RR2CastingPicker"].SetPointValue[5])
        self.assertEqual(452, frames["RR2CastingSecureButton"].SetPointValue[4])
        handlers["RR2 casting drag end picker"]()
        self.assertTrue(frames["RR2CastingPicker"].SetVisibleValue[1])

    def test_saved_hud_position_restores_and_deferred_viewport_is_retried(self):
        self.lua.globals().RiftReader2CastingEvidence = self.table({
            "hudPosition": {"x": 803, "y": 237},
        })
        self.load_main()
        globals_ = self.lua.globals()
        frames, handlers = globals_.TEST_FRAMES, globals_.TEST_HANDLERS
        globals_.TEST_VIEWPORT.width = None
        handlers["RR2 casting saved evidence"](None, "RiftReader2Casting")
        self.assertEqual(340, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(803, globals_.RiftReader2CastingEvidence.hudPosition.x)
        globals_.TEST_VIEWPORT.width = 1920
        handlers["RR2 casting readout"](None)
        self.assertEqual(803, frames["RR2CastingPanel"].SetPointValue[4])
        self.assertEqual(237, frames["RR2CastingPicker"].SetPointValue[5])
        self.assertEqual(803 + 221,
                         frames["RR2CastingStopButton"].SetPointValue[4])

    def test_saved_hud_position_rejects_malformed_values(self):
        self.lua.globals().RiftReader2CastingEvidence = self.table({
            "hudPosition": {"x": float("nan"), "y": "offscreen"},
        })
        self.load_main()
        globals_ = self.lua.globals()
        globals_.TEST_HANDLERS["RR2 casting saved evidence"](
            None, "RiftReader2Casting")
        self.assertEqual(340,
                         globals_.TEST_FRAMES["RR2CastingPanel"].SetPointValue[4])
        self.assertIn("invalid-saved-hud-position",
                      list(globals_.RiftReader2CastingEvidence.loadWarnings.values()))
        self.assertEqual(340, globals_.RiftReader2CastingEvidence.hudPosition.x)

    def test_cli_move_reset_and_record_preserve_hidden_dashboard(self):
        self.load_main()
        globals_ = self.lua.globals()
        slash = globals_.TEST_SLASH[1][1]
        frames = globals_.TEST_FRAMES
        slash("  MoVe  700  250 ")
        self.assertEqual((700, 250),
                         (frames["RR2CastingPanel"].SetPointValue[4],
                          frames["RR2CastingPanel"].SetPointValue[5]))
        slash("position")
        self.assertIn("X 700, Y 250",
                      globals_.TEST_CHAT[len(globals_.TEST_CHAT)].message)
        slash("hide")
        self.assertFalse(frames["RR2CastingPanel"].SetVisibleValue[1])
        slash("record")
        self.assertFalse(frames["RR2CastingPanel"].SetVisibleValue[1])
        slash("reset")
        self.assertEqual((340, 284),
                         (frames["RR2CastingPanel"].SetPointValue[4],
                          frames["RR2CastingPanel"].SetPointValue[5]))
        self.assertIsNone(globals_.TEST_MACROS["RR2CastingSecureButton"])
        self.assertEqual("stopattack", globals_.TEST_MACROS["RR2CastingStopButton"])

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

    def test_picker_modal_geometry_and_secure_caption_are_readable(self):
        private, _, _ = self.load_main()
        frames = self.lua.globals().TEST_FRAMES
        handlers = self.lua.globals().TEST_HANDLERS
        self.assertEqual("Select an ability",
                         frames["RR2CastingSecureButtonLabel"].SetTextValue[1])
        self.assertIsNotNone(handlers["RR2 casting picker backdrop"])
        self.assertTrue(private.SelectAbility("ability-old"))
        self.assertEqual("Cast  Practice Strike",
                         frames["RR2CastingSecureButtonLabel"].SetTextValue[1])
        picker = frames["RR2CastingPicker"]
        picker_bottom = picker.SetPointValue[5] + picker.SetHeightValue[1]
        secure_top = frames["RR2CastingSecureButton"].SetPointValue[5]
        hud_footer_bottom = (frames["RR2CastingPanel"].SetPointValue[5]
                             + frames["RR2CastingRecord"].SetPointValue[5]
                             + frames["RR2CastingRecord"].SetHeightValue[1])
        self.assertGreater(secure_top, picker_bottom)
        self.assertGreaterEqual(picker_bottom, hud_footer_bottom)
        last_row = frames["RR2CastingChoice4"]
        last_row_bottom = last_row.SetPointValue[5] + last_row.SetHeightValue[1]
        self.assertLess(last_row_bottom, frames["RR2CastingPrev"].SetPointValue[5])

    def test_secure_cast_caption_truncates_utf8_without_broken_codepoints(self):
        state = self.state()
        long_name = "火球术" * 10
        state.abilities["ability-old"].name = long_name
        private, _, _ = self.load_main(state)
        self.assertTrue(private.SelectAbility("ability-old"))
        caption = self.lua.globals().TEST_FRAMES[
            "RR2CastingSecureButtonLabel"].SetTextValue[1]
        self.assertTrue(caption.startswith("Cast  "))
        self.assertTrue(caption.endswith("..."))
        self.assertLessEqual(len(caption.removeprefix("Cast  ").encode("utf-8")), 16)
        self.assertEqual("cast " + long_name,
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])

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

    def load_main(self, state=None, *, version="0.5.1"):
        state = state or self.state()
        api, counts = self.factory(state)
        self.lua.execute(UI_STUB)
        self.lua.globals().Inspect = api
        private = self.lua.table(Casting=self.module)
        metadata = self.lua.table(identifier="RiftReader2Casting",
                                  toc=self.lua.table(Version=version))
        self.lua.execute(COMMANDS.read_text(encoding="utf-8"), metadata, private)
        self.lua.execute(MAIN.read_text(encoding="utf-8"), metadata, private)
        return private, state, counts

    def readout(self, state=None):
        private, _, counts = self.load_main(state)
        self.assertTrue(private.SelectAbility("ability-old"))
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        frames = self.lua.globals().TEST_FRAMES
        reply = self.lua.globals().RiftReader2CastingAPI.Snapshot()
        self.assertTrue(reply.accepted)
        return reply.result.state.value, frames, counts

    def test_readout_shows_melee_and_ranged_api_metadata_without_new_calls(self):
        cases = (
            ("melee", 0, 3, 0, False, False, "API READY",
             "Facing / LOS unverified", "instant (0s)"),
            ("ranged", 8, 30, 1.75, True, True, "BLOCKED",
             "Target is out of API range", "1.75s"),
        )
        for label, minimum, maximum, cast_time, channeled, out_of_range, status, reason, cast_label in cases:
            with self.subTest(ability=label):
                state = self.state()
                ability = state.abilities["ability-old"]
                ability.rangeMin = minimum
                ability.rangeMax = maximum
                ability.castingTime = cast_time
                ability.channeled = channeled
                ability.outOfRange = out_of_range
                snapshot, frames, counts = self.readout(state)

                self.assertEqual((minimum, maximum),
                                 (snapshot.ability.rangeMin, snapshot.ability.rangeMax))
                self.assertEqual((cast_time, channeled),
                                 (snapshot.ability.castingTime, snapshot.ability.channeled))
                self.assertEqual(status, frames["RR2CastingStatus"].SetTextValue[1])
                self.assertEqual(reason, frames["RR2CastingReason"].SetTextValue[1])
                self.assertEqual(3, counts.abilityScalar)  # Two select calls and the normal read.
                self.assertEqual("cast Practice Strike",
                                 self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
                self.assertEqual(226, frames["RR2CastingPanel"].SetHeightValue[1])
                self.assertEqual(141, frames["RR2CastingAbilities"].SetPointValue[5])
                self.assertEqual(284 + 180, frames["RR2CastingSecureButton"].SetPointValue[5])
                self.assertEqual(340 + 221, frames["RR2CastingStopButton"].SetPointValue[4])
                self.assertEqual(203, frames["RR2CastingSecureButton"].SetWidthValue[1])
                self.assertEqual((344, 176),
                                 (frames["RR2CastingPicker"].SetWidthValue[1],
                                  frames["RR2CastingPicker"].SetHeightValue[1]))
                self.assertEqual(16, frames["RR2CastingStatus"].SetFontSizeValue[1])

    def test_readout_distinguishes_missing_cast_time_from_instant(self):
        state = self.state()
        state.abilities["ability-old"].rangeMin = 4.5
        snapshot, _, _ = self.readout(state)
        self.assertEqual(4.5, snapshot.ability.rangeMin)
        self.assertIsNone(snapshot.ability.rangeMax)
        self.assertIsNone(snapshot.ability.castingTime)
        self.assertIsNone(snapshot.ability.channeled)
        self.assertEqual(0, snapshot.ability.currentCooldownRemaining)

    def test_snapshot_omits_nonfinite_values_without_coercing_raw_scalar(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=repr(invalid)):
                state = self.state()
                ability = state.abilities["ability-old"]
                ability.rangeMin = invalid
                ability.rangeMax = invalid
                ability.castingTime = invalid
                ability.channeled = "true"
                snapshot, frames, _ = self.readout(state)
                self.assertIsNone(snapshot.ability.rangeMin)
                self.assertIsNone(snapshot.ability.rangeMax)
                self.assertIsNone(snapshot.ability.castingTime)
                self.assertEqual("true", snapshot.ability.channeled)
                self.assertIsNot(snapshot.ability.channeled, True)
                self.assertEqual("API READY", frames["RR2CastingStatus"].SetTextValue[1])

    def test_saved_evidence_survives_update_before_exact_load_end(self):
        prior = self.table({
            "stamp": "persisted-before-load",
            "last": {"abilityId": "ability-old"},
            "trials": [{"status": "finished", "events": []}],
        })
        self.lua.globals().RiftReader2CastingEvidence = prior
        private, _, _ = self.load_main()
        handlers = self.lua.globals().TEST_HANDLERS
        event = self.lua.globals().Event.Addon.SavedVariables.Load.End
        handlers["RR2 casting readout"](self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("persisted-before-load",
                         self.lua.globals().RiftReader2CastingEvidence.stamp)
        handlers["RR2 casting saved evidence"](event, "AnotherAddon")
        self.assertEqual("persisted-before-load",
                         self.lua.globals().RiftReader2CastingEvidence.stamp)
        handlers["RR2 casting saved evidence"](event, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual("0.5.1", published.addonVersion)
        self.assertEqual(1, len(published.previousTrials))
        self.assertEqual("finished", published.previousTrials[1].status)
        self.assertEqual("ability-old", private.Instance.selected)
        self.assertEqual("cast Practice Strike",
                         self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        handlers["RR2 casting saved evidence"](event, "RiftReader2Casting")
        self.assertEqual(1, len(self.lua.globals().RiftReader2CastingEvidence.previousTrials))

    def test_corrupt_saved_trial_shapes_are_skipped_without_blocking_load(self):
        self.lua.globals().RiftReader2CastingEvidence = self.table({
            "previousTrials": 42,
            "trials": [False, 17, {"status": "aborted", "events": 17}],
        })
        self.load_main()
        handlers = self.lua.globals().TEST_HANDLERS
        event = self.lua.globals().Event.Addon.SavedVariables.Load.End
        handlers["RR2 casting saved evidence"](event, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual("0.5.1", published.addonVersion)
        self.assertEqual(1, len(published.previousTrials))
        self.assertEqual("aborted", published.previousTrials[1].status)
        self.assertIsNotNone(published.abilityMappings)
        handlers["RR2 casting readout"](self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("0.5.1", self.lua.globals().RiftReader2CastingEvidence.addonVersion)

    def assert_historical_mapping_with_missing_modern_api(self, missing_table):
        state = self.state()
        state.legacyAbilities["ability-old"] = self.table({
            "name": "Legacy Only", "id": "ability-old",
        })
        self.lua.globals().RiftReader2CastingEvidence = self.table({
            "last": {"abilityId": "ability-old"},
            "trials": [{"status": "finished", "events": [{"ability": "ability-old"}]}],
        })
        private, _, _ = self.load_main(state)
        modern = self.lua.globals().Inspect.Ability.New
        if missing_table:
            self.lua.globals().Inspect.Ability.New = None
        else:
            modern.Detail = None
        self.lua.globals().TEST_HANDLERS["RR2 casting saved evidence"](
            None, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual("0.5.1", published.addonVersion)
        mapping = published.abilityMappings["ability-old"]
        self.assertIsNone(mapping["New"])
        self.assertEqual("Legacy Only", mapping["Legacy"].name)
        self.assertIsNone(private.Instance.selected)
        self.assertIsNone(self.lua.globals().TEST_MACROS["RR2CastingSecureButton"])
        self.assertEqual(1, len(self.lua.globals().TEST_CHAT))
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2 casting readout"](self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("select-ability", private.Instance.last.reason)

    def test_saved_mapping_handles_missing_modern_api_table(self):
        self.assert_historical_mapping_with_missing_modern_api(True)

    def test_saved_mapping_does_not_mislabel_legacy_as_new(self):
        self.assert_historical_mapping_with_missing_modern_api(False)

    def test_runtime_ability_api_disappears_after_selection_without_crashing(self):
        private, _, _ = self.load_main()
        self.assertTrue(private.SelectAbility("ability-old"))
        self.lua.globals().Inspect.Ability.New = None
        self.assertFalse(private.SelectAbility("ability-old"))
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("blocked", private.Instance.last.status)
        self.assertEqual("select-ability", private.Instance.last.reason)
        self.assertEqual("BLOCKED",
                         self.lua.globals().TEST_FRAMES["RR2CastingStatus"].SetTextValue[1])

    def test_runtime_unit_api_disappears_fail_closed(self):
        private, _, _ = self.load_main()
        self.lua.globals().Inspect.Unit = None
        self.lua.globals().TEST_HANDLERS["RR2 casting readout"](
            self.lua.globals().Event.System.Update.Begin)
        self.assertEqual("blocked", private.Instance.last.status)
        self.assertEqual("player-unavailable", private.Instance.last.reason)
        self.assertEqual("BLOCKED",
                         self.lua.globals().TEST_FRAMES["RR2CastingStatus"].SetTextValue[1])

    def test_saved_load_recovers_from_clock_failure_and_publishes_evidence(self):
        self.lua.globals().RiftReader2CastingEvidence = self.table({
            "stamp": "old", "trials": [{"status": "finished", "events": []}],
        })
        _, state, _ = self.load_main()
        state.clockError = True
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2 casting saved evidence"](None, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual("0.5.1", published.addonVersion)
        self.assertEqual(1, len(published.previousTrials))
        self.assertIn("frame-clock-unavailable", list(published.loadWarnings.values()))
        self.assertEqual(1, len(self.lua.globals().TEST_CHAT))
        state.clockError = False
        handlers["RR2 casting readout"](None)
        self.assertIsNotNone(published.last)

    def test_saved_load_recovers_when_clock_table_is_missing(self):
        self.load_main()
        self.lua.globals().Inspect.Time = None
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2 casting saved evidence"](None, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual("0.5.1", published.addonVersion)
        self.assertIn("frame-clock-unavailable", list(published.loadWarnings.values()))
        self.assertEqual(1, len(self.lua.globals().TEST_CHAT))

    def test_saved_load_recovers_from_ability_catalog_error(self):
        private, _, _ = self.load_main()
        private.Instance.Abilities = self.lua.eval("function() error('catalog failure') end")
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2 casting saved evidence"](None, "RiftReader2Casting")
        published = self.lua.globals().RiftReader2CastingEvidence
        self.assertEqual(0, len(published.abilities))
        self.assertIn("ability-catalog-unavailable", list(published.loadWarnings.values()))
        self.assertEqual("0.5.1", published.addonVersion)

    def test_hud_hides_secure_buttons_and_slash_reopens_them(self):
        private, state, _ = self.load_main()
        frames = self.lua.globals().TEST_FRAMES
        self.lua.globals().TEST_HANDLERS["RR2CastingHide click"]()
        self.assertFalse(frames["RR2CastingPanel"].SetVisibleValue[1])
        self.assertFalse(frames["RR2CastingSecureButton"].SetVisibleValue[1])
        self.assertFalse(frames["RR2CastingStopButton"].SetVisibleValue[1])
        self.lua.globals().TEST_SLASH[1][1]()
        self.assertTrue(frames["RR2CastingPanel"].SetVisibleValue[1])
        self.assertTrue(frames["RR2CastingSecureButton"].SetVisibleValue[1])
        self.assertTrue(frames["RR2CastingStopButton"].SetVisibleValue[1])

        state.secureError = True
        self.lua.globals().TEST_HANDLERS["RR2CastingHide click"]()
        self.assertTrue(frames["RR2CastingPanel"].SetVisibleValue[1])
        self.assertTrue(frames["RR2CastingSecureButton"].SetVisibleValue[1])

    def test_exact_target_dodge_is_visible_without_upgrading_hit_verdict(self):
        private, state, _ = self.load_main()
        self.assertTrue(private.SelectAbility("ability-old"))
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2CastingRecord click"]()
        trial = private.Instance.trial
        dodge = self.table({"caster": "player-1", "target": "dummy-1",
                            "ability": "ability-old", "abilityNew": "ability-new"})
        handlers["RR2 casting dodge"](self.lua.globals().Event.Combat.Dodge, dodge)
        state.clock = 161
        handlers["RR2 casting readout"](self.lua.globals().Event.System.Update.Begin)
        self.assertFalse(trial.hit)
        self.assertEqual("no-matching-outcome-observed", trial.reason)
        reply = self.lua.globals().RiftReader2CastingAPI.Execute(
            self.table({"schemaVersion": 1, "command": "trial-status"}))
        self.assertTrue(reply.accepted)
        self.assertEqual("finished", reply.result.value.status)
        self.assertIn("DODGE on selected target", reply.result.value.outcome)

    def test_ready_with_realistic_absent_optional_flags(self):
        model, _, _ = self.selected()
        result = model.Read(model)
        self.assertEqual("ready", result.status)
        self.assertEqual("observed-ready", result.reason)
        self.assertEqual("unverified", result.facingAndLineOfSight)
        self.assertIsNone(result.ability.unusable)

    def test_ability_catalog_uses_one_list_and_one_batch_detail_call(self):
        state = self.state()
        state.abilityList = self.table({
            "ability-old": True, "passive": True, "free": True, "sparse": True,
        })
        state.abilities["passive"] = self.table({
            "id": "passive", "name": "Passive Ward", "passive": True, "costPower": 0,
        })
        state.abilities["free"] = self.table({
            "id": "free", "name": "Free Strike", "costPower": 0, "costSpirit": 2,
            "continuous": True, "stealthRequired": False, "icon": "icon.dds",
            "focusMin": 1, "focusMax": 5,
        })
        state.abilities["sparse"] = self.table({"id": "sparse"})
        model, _, counts = self.model(state)
        abilities = model.Abilities(model)
        items = {item.lookupId: item for item in abilities.values()}

        self.assertEqual({"ability-old", "passive", "free", "sparse"}, set(items))
        self.assertTrue(items["passive"].passive)
        self.assertEqual(0, items["passive"].costPower)
        self.assertEqual(0, items["free"].costPower)
        self.assertEqual(2, items["free"].costSpirit)
        self.assertTrue(items["free"].continuous)
        self.assertFalse(items["free"].stealthRequired)
        self.assertEqual("icon.dds", items["free"].icon)
        self.assertEqual(1, items["free"].focusMin)
        self.assertEqual(5, items["free"].focusMax)
        self.assertIsNone(items["sparse"].name)
        self.assertIsNone(items["sparse"].costPower)
        self.assertEqual(1, counts.abilityList)
        self.assertEqual(1, counts.abilityBatch)
        self.assertEqual(0, counts.abilityScalar)

    def test_picker_filters_known_unsupported_types_without_removing_them_from_catalog(self):
        state = self.state()
        state.abilityList = self.table({
            "passive": True, "positioned": True, "auto": True, "free": True, "sparse": True,
        })
        state.abilities["passive"] = self.table({"id": "passive", "name": "Passive", "passive": True})
        state.abilities["positioned"] = self.table({"id": "positioned", "name": "Ground", "positioned": True})
        state.abilities["auto"] = self.table({"id": "auto", "name": "Auto", "autoattack": True})
        state.abilities["free"] = self.table({"id": "free", "name": "Free Strike", "costPower": 0})
        state.abilities["sparse"] = self.table({"id": "sparse"})
        _, _, counts = self.load_main(state)

        self.lua.globals().TEST_HANDLERS["RR2CastingAbilities click"]()
        frames = self.lua.globals().TEST_FRAMES
        self.assertEqual("Free Strike", frames["RR2CastingChoice1Label"].SetTextValue[1])
        self.assertTrue(frames["RR2CastingChoice1"].SetVisibleValue[1])
        self.assertEqual("-", frames["RR2CastingChoice2Label"].SetTextValue[1])
        self.assertFalse(frames["RR2CastingChoice2"].SetVisibleValue[1])
        self.assertFalse(frames["RR2CastingChoice3"].SetVisibleValue[1])
        self.assertEqual("Page 1 / 1", frames["RR2CastingPage"].SetTextValue[1])
        self.assertEqual(1, counts.abilityList)
        self.assertEqual(1, counts.abilityBatch)

    def test_picker_paginates_four_choices_with_readable_rows(self):
        state = self.state()
        ids = [f"ability-{i:02d}" for i in range(1, 26)]
        state.abilityList = self.table({identifier: True for identifier in ids})
        for i, identifier in enumerate(ids, 1):
            state.abilities[identifier] = self.table({
                "id": identifier, "name": f"Spell {i:02d}",
            })
        self.load_main(state)
        handlers = self.lua.globals().TEST_HANDLERS
        handlers["RR2CastingAbilities click"]()
        frames = self.lua.globals().TEST_FRAMES
        self.assertEqual("Page 1 / 7", frames["RR2CastingPage"].SetTextValue[1])
        self.assertEqual("Spell 01", frames["RR2CastingChoice1Label"].SetTextValue[1])
        self.assertEqual("Spell 04", frames["RR2CastingChoice4Label"].SetTextValue[1])
        self.assertIsNone(frames["RR2CastingChoice5"])
        handlers["RR2CastingNext click"]()
        self.assertEqual("Page 2 / 7", frames["RR2CastingPage"].SetTextValue[1])
        self.assertEqual("Spell 05", frames["RR2CastingChoice1Label"].SetTextValue[1])
        self.assertEqual("Spell 08", frames["RR2CastingChoice4Label"].SetTextValue[1])
        handlers["RR2CastingPrev click"]()
        self.assertEqual("Page 1 / 7", frames["RR2CastingPage"].SetTextValue[1])

    def test_spirit_resource_is_copied_and_checked(self):
        state = self.state()
        state.units["player-1"].spirit = 4
        state.abilities["ability-old"].costSpirit = 5
        model, _, _ = self.selected(state)
        blocked = model.Read(model)
        self.assertEqual(4, blocked.player.spirit)
        self.assertEqual(5, blocked.ability.costSpirit)
        self.assertEqual("insufficient-or-unknown-spirit", blocked.reason)

        state.units["player-1"].spirit = 5
        ready = model.Read(model)
        self.assertEqual("ready", ready.status)

    def test_present_malformed_ability_costs_block_readiness(self):
        fields = ("costPower", "costMana", "costEnergy", "costCharge",
                  "costSpirit", "costPlanarCharge")
        for field in fields:
            for bad in (-1, "unknown", float("nan"), float("inf")):
                with self.subTest(field=field, bad=repr(bad)):
                    state = self.state()
                    setattr(state.abilities["ability-old"], field, bad)
                    model, _, _ = self.selected(state)
                    result = model.Read(model)
                    self.assertEqual("blocked", result.status)
                    self.assertEqual("invalid-ability-cost", result.reason)

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

    def test_heal_and_overheal_are_confirmed_separately_from_damage_hit(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "heal", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-old",
            "abilityNew": "ability-new", "abilityName": "Practice Mend", "heal": 19, "overheal": 0,
        }))
        self.assertFalse(model.trial.hit)
        self.assertTrue(model.trial.healingConfirmed)
        self.assertFalse(model.trial.overhealObserved)
        self.assertEqual(19, model.trial.lastHeal.heal)
        state.clock = 161
        model.Read(model)
        self.assertEqual("intended-heal-confirmed", model.trial.reason)

        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "heal", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-old",
            "abilityNew": "ability-new", "abilityName": "Practice Mend", "heal": 0, "overheal": 27,
        }))
        self.assertFalse(model.trial.hit)
        self.assertFalse(model.trial.healingConfirmed)
        self.assertTrue(model.trial.overhealObserved)
        self.assertEqual(27, model.trial.lastHeal.overheal)
        state.clock = 161
        model.Read(model)
        self.assertEqual("intended-overheal-observed", model.trial.reason)

    def test_damage_confirmation_has_finish_precedence_over_healing(self):
        model, state, _ = self.selected()
        self.assertTrue(model.Begin(model))
        common = {"caster": "player-1", "target": "dummy-1", "ability": "ability-old",
                  "abilityNew": "ability-new", "abilityName": "Practice Strike"}
        model.Combat(model, "heal", self.table({**common, "heal": 8, "overheal": 3}))
        model.Combat(model, "damage", self.table({**common, "damage": 12}))
        state.clock = 161
        model.Read(model)
        self.assertTrue(model.trial.hit)
        self.assertTrue(model.trial.healingConfirmed)
        self.assertEqual("intended-hit-confirmed", model.trial.reason)

    def test_wrong_combat_identities_cannot_qualify_healing_or_overheal(self):
        cases = (
            {"caster": "other", "target": "dummy-1", "abilityNew": "ability-new"},
            {"caster": "player-1", "target": "other", "abilityNew": "ability-new"},
            {"caster": "player-1", "target": "dummy-1", "abilityNew": "other"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                model, _, _ = self.selected()
                self.assertTrue(model.Begin(model))
                event = {"caster": "player-1", "target": "dummy-1", "ability": "ability-old",
                         "abilityNew": "ability-new", "abilityName": "Practice Mend",
                         "heal": 22, "overheal": 9}
                event.update(changes)
                model.Combat(model, "heal", self.table(event))
                self.assertFalse(model.trial.hit)
                self.assertFalse(model.trial.healingConfirmed)
                self.assertFalse(model.trial.overhealObserved)
                self.assertIsNone(model.trial.lastHeal)

    def test_damage_mitigation_fields_are_retained(self):
        model, _, _ = self.selected()
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-old",
            "abilityNew": "ability-new", "damage": 40, "damageAbsorbed": 1,
            "damageBlocked": 2, "damageDeflected": 3, "damageIntercepted": 4,
            "damageModified": 5, "overkill": 6,
        }))
        event = model.trial.lastHit
        self.assertEqual((1, 2, 3, 4, 5, 6),
                         (event.damageAbsorbed, event.damageBlocked, event.damageDeflected,
                          event.damageIntercepted, event.damageModified, event.overkill))

    def test_out_of_combat_state_does_not_filter_exact_outcome(self):
        state = self.state()
        state.units["player-1"].combat = False
        state.units["dummy-1"].combat = False
        model, _, _ = self.selected(state)
        self.assertTrue(model.Begin(model))
        model.Combat(model, "damage", self.table({
            "caster": "player-1", "target": "dummy-1", "ability": "ability-old",
            "abilityNew": "ability-new", "damage": 7,
        }))
        self.assertTrue(model.trial.hit)

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
        self.assertEqual("no-matching-outcome-observed", model.trial.reason)

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
        self.assertEqual("no-matching-outcome-observed", model.trial.reason)

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

        heal = self.table({"caster": "player-1", "target": "dummy-1",
                           "ability": "ability-old", "abilityNew": "ability-new",
                           "abilityName": "Practice Mend", "heal": 13, "overheal": 2})
        handlers["RR2 casting heal"](self.lua.globals().Event.Combat.Heal, heal)
        self.assertTrue(instance.trial.healingConfirmed)
        self.assertTrue(instance.trial.overhealObserved)
        self.assertEqual(13, instance.trial.lastHeal.heal)

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
