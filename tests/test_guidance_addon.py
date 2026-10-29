"""Real Lua 5.1 tests for bounded, manual RiftReader2 guidance feedback."""
from __future__ import annotations

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "addon" / "RiftReader2"
GUIDANCE = PACKAGE / "guidance.lua"
MAIN = PACKAGE / "main.lua"
NONCE = "0123456789abcdef0123456789abcdef"
OTHER_NONCE = "fedcba9876543210fedcba9876543210"


MAIN_STUB = r"""
TEST_STATE = {
    clock = 100,
    player = "player_1",
    x = 10,
    y = 20,
    z = 30,
}
TEST_PRINT = {}
TEST_SLASH = {}
TEST_HANDLERS = {}
TEST_FRAMES = {}
TEST_MACROS = {}
print = function(value) TEST_PRINT[#TEST_PRINT + 1] = tostring(value) end
Inspect = {
    Time = { Frame = function() return TEST_STATE.clock end },
    Unit = {
        Lookup = function(kind)
            if kind == "player" then return TEST_STATE.player end
        end,
        Detail = function(id)
            if id ~= TEST_STATE.player then return nil end
            return { coordX = TEST_STATE.x, coordY = TEST_STATE.y,
                coordZ = TEST_STATE.z, health = 100, healthMax = 100,
                combat = false }
        end,
    },
}
Event = {
    System = { Update = { Begin = {} } },
    Addon = { Startup = { End = {} } },
}
Command = {
    Slash = { Register = function(name)
        local handlers = {}
        TEST_SLASH[name] = handlers
        return handlers
    end },
    Event = { Attach = function(event, callback, label)
        table.insert(event, { callback, label })
        TEST_HANDLERS[label] = callback
    end },
}
local function frame(name)
    local value = { name = name }
    TEST_FRAMES[name] = value
    for _, method in ipairs({ "SetPoint", "SetWidth", "SetHeight",
        "SetFontSize", "SetBackgroundColor" }) do
        value[method] = function(self, ...) self[method .. "Value"] = {...} end
    end
    value.SetText = function(self, text) self.text = text end
    value.EventMacroSet = function(self, ...)
        TEST_MACROS[#TEST_MACROS + 1] = {...}
    end
    return value
end
UI = {
    CreateContext = function(name) return { name = name } end,
    CreateFrame = function(_, name) return frame(name) end,
}
UIParent = {}
"""


class GuidanceAddonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.private = self.lua.table()
        self.lua.execute(GUIDANCE.read_text(encoding="utf-8"),
                         self.lua.table(identifier="RiftReader2"), self.private)
        self.new_guidance = self.private.Guidance.New
        self.bind = self.lua.eval("function(g, lab, nonce) return g:Bind(lab, nonce) end")
        self.receive = self.lua.eval(
            "function(g, args, observation, now) return g:Receive(args, observation, now) end")
        self.status = self.lua.eval(
            "function(g, observation, now) return g:Status(observation, now) end")
        self.text = self.lua.eval(
            "function(g, observation, now) return g:Text(observation, now) end")
        self.invalidate = self.lua.eval(
            "function(g, reason) return g:Invalidate(reason) end")

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({key: self.table(item)
                                        for key, item in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(item) for item in value])
        return value

    def observation(self, **changes):
        value = {
            "sequence": 10,
            "epoch": 2,
            "clock": {"status": "ok", "value": 100.0},
            "player": {"status": "ok", "value": "player_1"},
            "fields": {
                "coordX": {"status": "ok", "value": 10.0},
                "coordY": {"status": "ok", "value": 20.0},
                "coordZ": {"status": "ok", "value": 30.0},
            },
        }
        value.update(changes)
        return self.table(value)

    @staticmethod
    def command(*, sequence=1, epoch=2, source_sequence=10, clock=100,
                player="player_1", x=10, y=20, z=30, distance=5,
                dx=3, dz=4, dy=1, lab="lab1", nonce=NONCE):
        return (f"result {lab} {nonce} {sequence} {epoch} {source_sequence} "
                f"{clock} {player} {x} {y} {z} {distance} {dx} {dz} {dy}")

    def bound(self):
        guidance = self.new_guidance()
        accepted, _ = self.bind(guidance, "lab1", NONCE)
        self.assertTrue(accepted)
        return guidance

    def assert_rejected(self, guidance, command, observation=None, now=100.5):
        accepted, reason = self.receive(
            guidance, command, observation or self.observation(), now)
        self.assertFalse(accepted, command)
        self.assertIsInstance(reason, str)
        return reason

    def test_binding_is_exact_immutable_and_idempotent(self):
        guidance = self.new_guidance()
        for lab, nonce in (("", NONCE), ("lab3", NONCE), ("LAB1", NONCE),
                           ("lab1", ""), ("lab1", NONCE.upper()),
                           ("lab1", NONCE + "0")):
            accepted, _ = self.bind(guidance, lab, nonce)
            self.assertFalse(accepted)
            self.assertIsNone(guidance.Nonce)

        self.assertTrue(self.bind(guidance, "lab1", NONCE)[0])
        self.assertTrue(self.bind(guidance, "lab1", NONCE)[0])
        self.assertFalse(self.bind(guidance, "lab2", NONCE)[0])
        self.assertFalse(self.bind(guidance, "lab1", OTHER_NONCE)[0])
        self.assertEqual("lab1", guidance.Lab)
        self.assertEqual(NONCE, guidance.Nonce)

    def test_exact_token_ascii_and_length_contract(self):
        guidance = self.bound()
        valid = self.command()
        for command in ("", "result", valid + " extra", valid.rsplit(" ", 1)[0],
                        valid.replace("result ", "request ", 1),
                        valid + "\n", valid + "\x00", "x" * 513):
            self.assert_rejected(guidance, command)
        self.assertEqual(0, guidance.LastSequence)

    def test_wrong_lab_or_session_does_not_poison_counters(self):
        guidance = self.bound()
        self.assert_rejected(guidance, self.command(lab="lab2"))
        self.assert_rejected(guidance, self.command(nonce=OTHER_NONCE))
        self.assertEqual(0, guidance.LastSequence)
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])

    def test_counter_bounds_and_number_grammar_fail_closed(self):
        for field, values in {
            "sequence": (0, -1, "1.0", "1e0", 9007199254740992),
            "epoch": (0, -1, "2.0", 9007199254740992),
            "source_sequence": (0, -1, "10.0", 9007199254740992),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    guidance = self.bound()
                    self.assert_rejected(
                        guidance, self.command(**{field: value}))

        for field, values in {
            "clock": (-1, "nan", "inf", "1e309", "1,0", "--1"),
            "x": ("nan", "inf", 10000001),
            "y": ("-inf", -10000001),
            "z": ("1e309", 10000001),
            "distance": (-1, "nan", 30000001),
            "dx": ("nan", 20000001),
            "dz": ("inf", -20000001),
            "dy": ("1e309", 20000001),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    guidance = self.bound()
                    self.assert_rejected(
                        guidance, self.command(**{field: value}))

    def test_player_and_distance_fields_are_strict(self):
        for player in ("", "player-1", "player 1", "x" * 129):
            self.assert_rejected(self.bound(), self.command(player=player))
        for distance, dx, dz in ((5.1, 3, 4), (0, 3, 4), (5, 0, 0)):
            self.assert_rejected(
                self.bound(), self.command(distance=distance, dx=dx, dz=dz))

    def test_source_identity_epoch_sequence_and_clock_must_align(self):
        cases = (
            (self.command(player="other"), self.observation(), 100.5),
            (self.command(epoch=3), self.observation(), 100.5),
            (self.command(source_sequence=11), self.observation(), 100.5),
            (self.command(clock=101), self.observation(), 101),
            (self.command(clock=89), self.observation(), 100.5),
            (self.command(clock=101), self.observation(), 100.5),
        )
        for command, observation, now in cases:
            with self.subTest(command=command):
                self.assert_rejected(self.bound(), command, observation, now)

    def test_absent_stale_or_rolled_back_current_source_is_rejected(self):
        cases = (
            self.observation(clock=self.table({"status": "unavailable"})),
            self.observation(clock=self.table({"status": "ok", "value": 98.0})),
            self.observation(player=self.table({"status": "unavailable"})),
            self.observation(fields=self.table({})),
            self.observation(fields=self.table({
                "coordX": {"status": "unavailable"},
                "coordY": {"status": "ok", "value": 20},
                "coordZ": {"status": "ok", "value": 30},
            })),
        )
        for observation in cases:
            self.assert_rejected(self.bound(), self.command(), observation, 100.5)
        self.assert_rejected(self.bound(), self.command(), self.observation(), 99.9)

    def test_malformed_observation_counters_fail_closed_without_lua_error(self):
        for changes in ({"sequence": None}, {"sequence": "10"},
                        {"epoch": None}, {"epoch": "2"}):
            with self.subTest(changes=changes):
                guidance = self.bound()
                try:
                    accepted, _ = self.receive(
                        guidance, self.command(), self.observation(**changes), 100.5)
                except Exception as error:  # Lupa exposes a Lua comparison error here.
                    self.fail(f"malformed observation escaped guidance boundary: {error}")
                self.assertFalse(accepted)

    def test_duplicate_out_of_order_and_unadvanced_source_are_rejected(self):
        guidance = self.bound()
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])
        for command in (self.command(), self.command(sequence=0),
                        self.command(sequence=2, source_sequence=10)):
            self.assert_rejected(guidance, command)
        advanced = self.observation(sequence=11,
                                    clock=self.table({"status": "ok", "value": 101}))
        self.assertTrue(self.receive(
            guidance,
            self.command(sequence=2, source_sequence=11, clock=101),
            advanced, 101.5)[0])

    def test_movement_invalidation_is_latched(self):
        guidance = self.bound()
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])
        moved_fields = self.table({
            "coordX": {"status": "ok", "value": 10.6},
            "coordY": {"status": "ok", "value": 20},
            "coordZ": {"status": "ok", "value": 30},
        })
        state, reason = self.status(
            guidance, self.observation(fields=moved_fields), 100.6)
        self.assertEqual("unavailable", state)
        self.assertIn("moved", reason.lower())
        self.assertIsNone(guidance.Result)
        state, _ = self.status(guidance, self.observation(), 100.7)
        self.assertEqual("unavailable", state)
        self.assertIsNone(guidance.Result)

    def test_exact_result_age_limit_with_fresh_observation(self):
        current = self.observation(sequence=21,
                                   clock={"status": "ok", "value": 109})
        for now, expected in ((110, True), (110.001, False)):
            with self.subTest(now=now):
                guidance = self.bound()
                accepted, _ = self.receive(guidance, self.command(), current, now)
                self.assertEqual(expected, accepted)
                if expected:
                    state, _ = self.status(guidance, current, 110.001)
                    self.assertEqual("unavailable", state)
                    self.assertIsNone(guidance.Result)

    def test_exact_coordinate_limit_on_receipt_and_status(self):
        for x, expected in ((10.5, True), (10.5001, False)):
            with self.subTest(x=x):
                fields = {"coordX": {"status": "ok", "value": x},
                          "coordY": {"status": "ok", "value": 20},
                          "coordZ": {"status": "ok", "value": 30}}
                moved = self.observation(fields=fields)
                fresh = self.bound()
                accepted, _ = self.receive(fresh, self.command(), moved, 100.5)
                self.assertEqual(expected, accepted)
                existing = self.bound()
                self.assertTrue(self.receive(existing, self.command(), self.observation(), 100.5)[0])
                state, _ = self.status(existing, moved, 100.5)
                self.assertEqual("received" if expected else "unavailable", state)

    def test_expired_result_is_removed_and_never_restored(self):
        guidance = self.bound()
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])
        fresh_later = self.observation(
            sequence=20, clock=self.table({"status": "ok", "value": 111}))
        state, reason = self.status(guidance, fresh_later, 111)
        self.assertEqual("unavailable", state)
        self.assertIn("expired", reason.lower())
        self.assertIsNone(guidance.Result)
        self.status(guidance, self.observation(), 100.6)
        self.assertIsNone(guidance.Result)

    def test_status_invalidates_identity_epoch_sequence_and_clock_rollback(self):
        cases = (
            self.observation(player=self.table({"status": "ok", "value": "other"})),
            self.observation(epoch=3),
            self.observation(sequence=9),
            self.observation(clock=self.table({"status": "ok", "value": 99.9})),
        )
        for observation in cases:
            with self.subTest(observation=observation):
                guidance = self.bound()
                self.assertTrue(self.receive(
                    guidance, self.command(), self.observation(), 100.5)[0])
                state, _ = self.status(guidance, observation, 100.5)
                self.assertEqual("unavailable", state)
                self.assertIsNone(guidance.Result)

    def test_clear_preserves_replay_fences(self):
        guidance = self.bound()
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])
        self.invalidate(guidance, "Cancelled by operator.")
        self.assertIsNone(guidance.Result)
        self.assert_rejected(guidance, self.command())
        self.assert_rejected(guidance, self.command(sequence=2))
        advanced = self.observation(
            sequence=11, clock=self.table({"status": "ok", "value": 101}))
        self.assertTrue(self.receive(
            guidance,
            self.command(sequence=2, source_sequence=11, clock=101),
            advanced, 101.5)[0])

    def test_text_reports_identity_values_and_honest_state(self):
        guidance = self.bound()
        waiting = self.text(guidance, self.observation(), 100.5)
        self.assertIn("WAITING", waiting)
        self.assertTrue(self.receive(
            guidance, self.command(), self.observation(), 100.5)[0])
        text = self.text(guidance, self.observation(), 100.6)
        for expected in ("lab1", "RESULT 1", "Planar distance 5.00",
                         "dX +3.00", "dZ +4.00", "Vertical dY +1.00",
                         "EXTERNAL CALCULATION / MANUAL DELIVERY"):
            self.assertIn(expected, text)

    def test_external_calculator_slash_contract_is_accepted_verbatim(self):
        """Matches the exact command asserted by the .NET calculator tests."""
        guidance = self.new_guidance()
        self.assertTrue(self.bind(guidance, "lab1", NONCE)[0])
        observation = self.observation(
            sequence=12,
            epoch=3,
            clock=self.table({"status": "ok", "value": 123.5}),
            player=self.table({"status": "ok", "value": "u123_ABC"}),
            fields=self.table({
                "coordX": {"status": "ok", "value": 10},
                "coordY": {"status": "ok", "value": 2},
                "coordZ": {"status": "ok", "value": 20},
            }))
        command = ("result lab1 0123456789abcdef0123456789abcdef "
                   "7 3 12 123.5 u123_ABC 10 2 20 5 -3 4 4")
        accepted, reason = self.receive(guidance, command, observation, 124)
        self.assertTrue(accepted, reason)
        self.assertEqual(7, guidance.Result.sequence)
        self.assertEqual(0.5, guidance.Result.sourceToReceiptSeconds)

    def load_main(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        private = lua.table()
        for name in ("wire.lua", "producer.lua", "live.lua", "guidance.lua"):
            lua.execute((PACKAGE / name).read_text(encoding="utf-8"),
                        lua.table(identifier="RiftReader2"), private)
        lua.execute(MAIN_STUB)
        lua.execute(MAIN.read_text(encoding="utf-8"),
                    lua.table(identifier="RiftReader2"), private)
        lua.globals().TEST_HANDLERS["RiftReader2 startup"]()
        return lua, private

    @staticmethod
    def slash(lua, name, args):
        lua.globals().TEST_SLASH[name][1][1](args)

    def test_main_shared_live_binding_conflict_does_not_poison_guidance(self):
        lua, private = self.load_main()
        self.slash(lua, "rr2bind", NONCE)
        self.slash(lua, "rr2guide", f"bind lab2 {OTHER_NONCE}")
        self.assertIsNone(private.GuidanceInstance.Nonce)
        self.assertEqual("unbound", private.GuidanceInstance.State)
        self.slash(lua, "rr2guide", f"bind lab2 {NONCE}")
        self.assertEqual("lab2", private.GuidanceInstance.Lab)
        self.assertEqual(NONCE, private.GuidanceInstance.Nonce)
        lua.globals().TEST_HANDLERS["RiftReader2 update"]()
        frame = lua.globals().RiftReader2_Frame
        self.assertEqual(f"RR2L1|{NONCE}|{frame}|ENDRR2L1",
                         lua.globals().RiftReader2_LiveFrame)
        self.slash(lua, "rr2guide", f"bind lab1 {NONCE}")
        self.assertEqual("lab2", private.GuidanceInstance.Lab)

        lua, private = self.load_main()
        self.slash(lua, "rr2guide", f"bind lab1 {NONCE}")
        self.slash(lua, "rr2bind", OTHER_NONCE)
        self.assertEqual("lab1", private.GuidanceInstance.Lab)
        self.assertEqual(NONCE, private.GuidanceInstance.Nonce)
        lua.globals().TEST_HANDLERS["RiftReader2 update"]()
        frame = lua.globals().RiftReader2_Frame
        self.assertEqual(f"RR2L1|{NONCE}|{frame}|ENDRR2L1",
                         lua.globals().RiftReader2_LiveFrame)

    def test_main_result_clear_status_and_ui_have_no_action_macros(self):
        lua, private = self.load_main()
        globals_ = lua.globals()
        self.assertEqual("unbound", globals_.RiftReader2_Guidance.state)
        self.slash(lua, "rr2guide", f"bind lab1 {NONCE}")
        self.assertIn("WAITING", globals_.TEST_FRAMES["RiftReader2GuidanceText"].text)
        self.assertIn("Bound lab1; manual feedback only.",
                      globals_.TEST_PRINT[len(globals_.TEST_PRINT)])
        self.slash(lua, "rr2guide", self.command(epoch=1, source_sequence=1))
        self.assertEqual("received", globals_.RiftReader2_Guidance.state)
        self.assertEqual(1, globals_.RiftReader2_Guidance.result.sourceSequence)
        self.assertEqual(100, globals_.RiftReader2_Guidance.result.clock)
        self.assertEqual(0, globals_.RiftReader2_Guidance.result.sourceToReceiptSeconds)
        self.assertIn("Planar distance 5.00",
                      globals_.TEST_FRAMES["RiftReader2GuidanceText"].text)
        self.slash(lua, "rr2guide", "status")
        self.assertIn("RR2 GUIDANCE", globals_.TEST_PRINT[len(globals_.TEST_PRINT)])
        self.slash(lua, "rr2guide", "clear")
        self.assertEqual("unavailable", globals_.RiftReader2_Guidance.state)
        self.assertIn("UNAVAILABLE", globals_.TEST_FRAMES["RiftReader2GuidanceText"].text)
        self.assertEqual(0, len(globals_.TEST_MACROS))
        self.assertIsNone(private.GuidanceInstance.Result)

    def test_guidance_sources_contain_no_action_or_message_dispatch(self):
        guidance = GUIDANCE.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        for forbidden in ("EventMacroSet", "Command.Message", "Command.Input",
                          "cast ", "target ", "move "):
            self.assertNotIn(forbidden, guidance)
        self.assertNotIn("EventMacroSet", main)
        self.assertNotIn("Command.Message", main)


if __name__ == "__main__":
    unittest.main()
