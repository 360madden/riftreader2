"""Run actual Lua 5.1 survey frames through the Python decoder, offline."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lupa.lua51 import LuaRuntime
from scripts import npc_survey_live as survey

NONCE="a"*32
PLAYER="u0000000000000001"
UNIT="u0000000000000002"
OTHER="u0000000000000003"
ADDON=Path(__file__).resolve().parents[1]/"addon"/"RiftReader2NpcSurvey"


class NpcSurveyTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            clock=12; selfId="u0000000000000001"; calls=0; listCalls=0
            units={u0000000000000002={id="u0000000000000002",name='Coastal "Stalker"',
                level=13,coordX=12.5,coordY=0,coordZ=-2,health=0,relation="hostile",
                player=false,attackable=false}}
            visible={u0000000000000002="random specimen",u0000000000000003="another specifier"}
            Inspect={Time={Frame=function() return clock end},Unit={
                Lookup=function() return selfId end,
                List=function() listCalls=listCalls+1; return (listCalls%2==0 and after) or visible end,
                Detail=function(id) calls=calls+1; return units[id] end}}
            Command={Slash={Register=function(name) slash={}; return slash end},
                     Event={Attach=function(_,handler,label) tick=handler; eventLabel=label end},
                     Console={Display=function(_,_,message) lastMessage=message end}}; Event={System={Update={Begin={}}}}
        """)
        self.g=self.lua.globals()
        self.api=self.lua.table()
        self.lua.execute((ADDON/"survey.lua").read_text(),self.lua.table(identifier="RiftReader2NpcSurvey"),self.api)

    def test_slash_owner_matches_host_addon_but_wire_keeps_producer_identity(self):
        for owner,key in (("RiftReader2Casting","identifier"),("RiftReader2NpcSurvey","Identifier")):
            self.lua.execute((ADDON/"survey.lua").read_text(),self.lua.table_from({key:owner}),self.api)
            entry=self.g.slash[1]
            self.assertEqual(entry[2],owner)
            self.assertEqual(self.g.eventLabel,owner+" NPC survey")
            entry[1]("bind "+NONCE+" "+UNIT)
            self.assertIn("bound 1 units",self.g.lastMessage)
            self.assertEqual(survey.decode_frame(self.sample(13),NONCE,PLAYER,[UNIT])["addon"],
                             "RiftReader2NpcSurvey")

    def bind(self,arg):
        self.assertTrue(self.api.Command("bind "+NONCE+" "+arg)[0])

    def sample(self,t):
        self.g.clock=t
        self.g.tick()
        return self.g.RiftReader2NpcSurveyWire.encode() if self.g.RiftReader2NpcSurveyWire else None

    def test_exact_id_membership_before_and_after_and_missing_fields(self):
        self.bind(UNIT+","+OTHER)
        frame=survey.decode_frame(self.sample(13),NONCE,PLAYER,[UNIT,OTHER])
        row=frame["units"][UNIT]
        self.assertEqual((row["name"],row["relation"],row["coordY"],row["health"]),
                         ('Coastal "Stalker"',"hostile",0,0))
        self.assertIs(row["rawAttackable"],False)
        self.assertNotIn("attackable",row)
        self.assertNotIn("combat",row)
        self.assertEqual(frame["units"][OTHER],{"visibleBefore":True,"visibleAfter":True,"status":"unavailable"})
        self.lua.execute("after={u0000000000000003='any'}")
        changed=survey.decode_frame(self.sample(13.3),NONCE,PLAYER,[UNIT,OTHER])
        self.assertFalse(changed["keysetStable"])
        self.assertEqual(changed["units"][UNIT]["status"],"observed")
        self.assertFalse(changed["units"][UNIT]["visibleAfter"])

    def test_absent_relation_and_mismatched_detail_are_not_classified(self):
        self.bind(UNIT)
        self.lua.execute('units.u0000000000000002.relation=nil; units.u0000000000000002.attackable=1')
        row=survey.decode_frame(self.sample(13),NONCE,PLAYER,[UNIT])["units"][UNIT]
        self.assertNotIn("relation",row)
        self.assertNotIn("rawAttackable",row)
        self.lua.execute("units.u0000000000000002.id=selfId")
        self.assertEqual(survey.decode_frame(self.sample(14),NONCE,PLAYER,[UNIT])["units"][UNIT]["status"],
                         "identity-mismatch")
        self.lua.execute("Inspect.Unit.List=nil")
        row=survey.decode_frame(self.sample(15),NONCE,PLAYER,[UNIT])["units"][UNIT]
        self.assertEqual(row["status"],"identity-mismatch")
        self.assertNotIn("visibleBefore",row)

    def test_auto_pages_use_keys_and_require_stable_list(self):
        self.lua.execute('visible={}; for i=1,14 do visible[string.format("u%016X",i)]="not an ID" end')
        self.bind("visible")
        frame=survey.decode_frame(self.sample(13),NONCE,PLAYER,None,1)
        self.assertEqual(len(frame["units"]),12)
        self.assertTrue(self.api.Command("page 2")[0])
        second=survey.decode_frame(self.sample(14),NONCE,PLAYER,None,2)
        self.assertEqual(set(second["units"]),{"u000000000000000D","u000000000000000E"})
        self.lua.execute('after={u0000000000000001="self"}')
        with self.assertRaises(ValueError): survey.decode_frame(self.sample(15),NONCE,PLAYER,None,2)

    def test_advancement_conflict_wrong_binding_and_clear(self):
        self.bind(UNIT)
        first=self.sample(13)
        second=self.sample(13.3)
        journal={}
        pair=[({"address":"0x11000"},first)]
        a,_=survey.newest(pair,NONCE,PLAYER,[UNIT],journal,None)
        self.assertIsNone(survey.newest(pair,NONCE,PLAYER,[UNIT],journal,a))
        b,_=survey.newest([({"address":"0x12000"},second)],NONCE,PLAYER,[UNIT],journal,a)
        self.assertGreater(b["sequence"],a["sequence"])
        with self.assertRaisesRegex(ValueError,"conflicting"):
            survey.newest([({"address":"0x11000"},first.replace(b"hostile",b"neutral"))],
                          NONCE,PLAYER,[UNIT],journal,a)
        for args in [("b"*32,PLAYER,[UNIT]),(NONCE,OTHER,[UNIT]),(NONCE,PLAYER,[OTHER])]:
            with self.assertRaises(ValueError): survey.decode_frame(first,*args)
        self.assertIsNone(self.sample(12))
        self.assertFalse(list(self.g.RiftReader2NpcSurveyFrames.values()))

    def test_raw_id_outside_specifier_list_can_have_exact_detail(self):
        self.assertFalse(self.api.Command("bind "+NONCE+" "+UNIT+","+UNIT)[0])
        self.assertFalse(self.api.Command("bind "+NONCE+" "+",".join(f"u{x:016X}" for x in range(13)))[0])
        self.bind(UNIT)
        self.lua.execute('visible={}; units.u0000000000000002.availability="partial"')
        frame=survey.decode_frame(self.sample(13),NONCE,PLAYER,[UNIT])
        self.assertEqual(self.g.calls,1)
        self.assertEqual(frame["units"][UNIT]["status"],"observed")
        self.assertEqual(frame["units"][UNIT]["availability"],"partial")
        self.assertFalse(frame["units"][UNIT]["visibleBefore"])

    def test_full_acquisition_uses_two_independent_advanced_frames(self):
        self.bind(UNIT)
        target={"processId":42,"processStartUtcTicks":1234,"executableSha256":"A"*64}
        chunks=[[({"address":"0x11000"},self.sample(t))] for t in (13,13.3)]
        with tempfile.TemporaryDirectory() as tmp:
            seed=Path(tmp)/"index.json"
            seed.write_text(json.dumps({"evidenceKind":"native-value-scout/1","identity":target,
                "coveredSpans":[{"baseAddress":"0x10000","byteLength":16777216}]}))
            out=Path(tmp)/"run"
            with patch.object(survey.physical_rift,"select_physical",return_value={"status":"ready","target":target}), \
                 patch.object(survey,"PhysicalAdapter") as adapter, patch.object(survey,"scout",side_effect=chunks), \
                 patch.object(survey.time,"sleep"):
                adapter.return_value.target=target
                adapter.return_value.unit_key="1"
                result=survey.acquire("AMD-DESKTOP",42,NONCE,[UNIT],out,seed)
                self.assertEqual((result["status"],result["observedUnits"]),("advancing",1))
                self.assertEqual(result["confirmedUnitIds"],[UNIT])
                self.assertEqual([source["sequence"] for source in result["sources"]],[1,2])
                self.assertFalse(result["inputSent"])
                self.assertTrue((out/"result.json").is_file())

    def test_scout_validates_native_request_then_accepts_complete_frame_in_context(self):
        self.bind(UNIT)
        data=self.sample(13)
        target={"processId":42,"processStartUtcTicks":1234,"executableSha256":"A"*64}
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Path(tmp)/"attempt-1.scout"
            def write_index(command,request,result,runner):
                self.assertEqual(command,"scout-values-native")
                req=json.loads(request.read_bytes())
                self.assertIsNone(req["references"][0]["tolerance"])
                self.assertEqual(req["references"][0]["value"],str(int.from_bytes(b"RR2N","little")))
                result.mkdir()
                (result/"index.json").write_text(json.dumps({"request":req}))
            found=[({"address":"0x12000","referenceNames":["rr2-npc-survey"]},data)]
            with patch.object(survey,"_run_native",write_index), \
                 patch.object(survey,"_validate_scout",return_value=found), \
                 patch.object(survey.survival_live,"_capture_known") as capture:
                self.assertEqual(survey.scout(target,0x10000,0x10000,attempt),found)
                capture.assert_not_called()
