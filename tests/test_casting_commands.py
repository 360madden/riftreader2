"""Focused Lua 5.1 tests for the shared Casting command service."""
from pathlib import Path
import json
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "addon" / "RiftReader2Casting" / "commands.lua"

CALLBACK_FACTORY = r"""
return function(state)
    return {
        snapshot=function() return {status="ready", abilityId=state.selected,
            resources={power=100, mana=250, energy=75}} end,
        listLearned=function() return state.abilities end,
        selectAbility=function(id)
            state.selectCalls=state.selectCalls+1
            if id == "ability-old" or id == "A01" then state.selected=id; return true end
            return false,"ability-not-learned"
        end,
        record=function()
            state.recordCalls=state.recordCalls+1
            if state.recordAllowed then return true end
            return false,"recording-refused"
        end,
        trialStatus=function() return {status=state.trialStatus, abilityId=state.selected} end,
        survival=function(action,args)
            state.survivalCalls=state.survivalCalls+1
            state.lastSurvival=action
            state.lastArg=args[1]
            state.lastArg2=args[2]
            return true,"delegated "..action
        end,
        stopStatus=function() return {latched=state.stopLatched} end,
    }
end
"""


class CastingCommandsTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.private = self.lua.table()
        self.lua.execute(COMMANDS.read_text(encoding="utf-8"),
                         self.lua.table_from({"toc": {"Version": "0.5.0"}}), self.private)
        self.commands = self.private["CastingCommands"]
        self.state = self.lua.table_from({
            "abilities": self.lua.table_from([
                self.lua.table_from({"lookupId": "ability-old", "idNew": "A01",
                                     "name": "Practice Strike", "target": "target-1"}),
                self.lua.table_from({"lookupId": "A01", "idNew": "A01",
                                     "name": "Practice Strike", "target": "target-1"}),
            ]),
            "selected": None,
            "selectCalls": 0,
            "recordCalls": 0,
            "recordAllowed": True,
            "trialStatus": "inactive",
            "survivalCalls": 0,
            "stopLatched": True,
        })
        callbacks = self.lua.execute(CALLBACK_FACTORY)(self.state)
        self.service = self.commands["Create"](callbacks)

    def request(self, command, **values):
        request = {"schemaVersion": 1, "command": command}
        request.update(values)
        return self.service["Execute"](self.lua.table_from(request))

    def test_capabilities_and_global_api_are_versioned_and_never_cast(self):
        result = self.request("capabilities", requestId="req-1")
        self.assertTrue(result["accepted"])
        self.assertEqual("req-1", result["requestId"])
        self.assertFalse(result["gameActionSent"])
        self.assertEqual("not-performed", result["effectStatus"])
        self.assertFalse(result["result"]["programmaticCast"])
        self.assertEqual("existing-callback-status-only", result["result"]["stopControl"])

        namespace = self.lua.table()
        accepted, api = self.commands["InstallGlobal"](self.service, namespace)
        self.assertTrue(accepted)
        self.assertEqual(1, api["schemaVersion"])
        snapshot = namespace["RiftReader2CastingAPI"]["Snapshot"]()
        self.assertEqual("status", snapshot["command"])
        self.assertTrue(snapshot["result"]["stop"]["value"]["latched"])
        self.assertEqual(250, snapshot["result"]["state"]["value"]["resources"]["mana"])

    def test_learned_list_is_paged_and_exact_selection_has_no_cast_effect(self):
        page = self.request("list", page=1, pageSize=1)
        self.assertEqual(2, page["result"]["count"])
        self.assertEqual(2, page["result"]["pages"])
        self.assertEqual("ability-old", page["result"]["entries"][1]["id"])
        refused = self.request("list", page=1, pageSize=26)
        self.assertFalse(refused["accepted"])
        self.assertEqual("invalid-page", refused["reason"])

        selected = self.request("select", abilityId="ability-old")
        self.assertTrue(selected["accepted"])
        self.assertFalse(selected["result"]["castPerformed"])
        self.assertFalse(selected["gameActionSent"])
        self.assertEqual("ability-old", self.state["selected"])
        wrong_case = self.request("select", abilityId="Ability-Old")
        self.assertFalse(wrong_case["accepted"])
        self.assertEqual(2, self.state["selectCalls"])
        self.assertTrue(self.state["stopLatched"])

    def test_record_trial_and_survival_delegate_without_clearing_stop(self):
        recorded = self.request("record")
        self.assertTrue(recorded["accepted"])
        self.assertFalse(recorded["result"]["castPerformed"])
        self.assertEqual(1, self.state["recordCalls"])
        trial = self.request("trial-status")
        self.assertEqual("inactive", trial["result"]["value"]["status"])

        survival = self.request("survival", action="setup",
                                args=self.lua.table_from(["nonce", "A01"]))
        self.assertTrue(survival["accepted"])
        self.assertTrue(survival["result"]["configurationOnly"])
        self.assertEqual("setup", self.state["lastSurvival"])
        self.assertTrue(self.state["stopLatched"])
        refused = self.request("survival", action="cast", args=self.lua.table())
        self.assertFalse(refused["accepted"])
        self.assertEqual(1, self.state["survivalCalls"])

    def test_text_dispatch_is_the_same_bounded_service(self):
        selected = self.commands["DispatchText"](self.service, "select ability-old")
        self.assertTrue(selected["accepted"])
        listed = self.commands["DispatchText"](self.service, "abilities 1 1")
        self.assertEqual("list", listed["command"])
        self.assertEqual(1, listed["result"]["pageSize"])
        survival = self.commands["DispatchText"](self.service, "survival status")
        self.assertTrue(survival["accepted"])
        ids = ",".join(f"A{index:016X}" for index in range(1, 9))
        setup = self.commands["DispatchText"](
            self.service, "survival setup " + "a" * 32 + " " + ids)
        self.assertTrue(setup["accepted"])
        self.assertEqual(ids, self.state["lastArg2"])
        json_status = self.commands["DispatchText"](self.service, "json status")
        self.assertEqual("json", json_status["outputFormat"])
        encoded = self.commands["EncodeResponse"](json_status)
        decoded = json.loads(encoded)
        self.assertEqual("status", decoded["command"])
        encoded_list = self.commands["EncodeResponse"](listed)
        self.assertIsInstance(json.loads(encoded_list)["result"]["entries"], list)
        encoded_capabilities = self.commands["EncodeResponse"](self.request("capabilities"))
        self.assertIsInstance(json.loads(encoded_capabilities)["result"]["commands"], list)
        bad_page = self.commands["DispatchText"](self.service, "list banana")
        self.assertEqual("invalid-page", bad_page["reason"])
        too_long = self.commands["DispatchText"](self.service, "x" * 513)
        self.assertEqual("invalid-command-text", too_long["reason"])
        long_json = self.commands["DispatchText"](self.service, "json " + "x" * 513)
        self.assertEqual("json", long_json["outputFormat"])
        self.assertEqual("invalid-command-text",
                         json.loads(self.commands["EncodeResponse"](long_json))["reason"])
        extra = self.commands["DispatchText"](self.service, "record unexpected")
        self.assertEqual("unexpected-arguments", extra["reason"])

        sparse = self.lua.table()
        sparse[1], sparse[3] = "nonce", "A01"
        malformed = self.request("survival", action="setup", args=sparse)
        self.assertEqual("invalid-survival-command", malformed["reason"])

    def test_invalid_requests_and_callback_failures_are_fail_closed(self):
        invalid = self.service["Execute"](self.lua.table_from({"schemaVersion": 2,
                                                                "command": "status"}))
        self.assertFalse(invalid["accepted"])
        self.assertFalse(invalid["gameActionSent"])
        missing = self.commands["Create"](self.lua.table())
        result = missing["Execute"](self.lua.table_from({"schemaVersion": 1,
                                                          "command": "record"}))
        self.assertFalse(result["accepted"])
        self.assertEqual("record-unavailable", result["reason"])


if __name__ == "__main__":
    unittest.main()
