"""Offline Lua 5.1 tests for the complete Casting + survival startup bundle."""
import json
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime
from tests import test_casting_addon as casting


PACKAGE = Path(__file__).resolve().parents[1] / "addon" / "RiftReader2Casting"
NONCE = "0123456789abcdef" * 2


class SurvivalAddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(casting.UI_STUB)
        self.lua.execute("""
            SLASHES={}
            Command.Slash.Register=function(name) SLASHES[name]={}; return SLASHES[name] end
            UIParent.GetLeft=function() return 0 end
            UIParent.GetTop=function() return 0 end
        """)
        self.st = self.lua.table_from({
            "clock": 21, "playerId":"u0000000000000001", "targetId":"u0000000000000002",
            "units":{"u0000000000000001":{"id":"u0000000000000001","health":100,"healthMax":100,
                      "name":"Player", "power":0,"level":45,"calling":"warrior","combat":False,"dead":False},
                     "u0000000000000002":{"id":"u0000000000000002","health":99,"level":40,
                      "relation":"hostile","coordX":2,"coordY":3,"coordZ":4}},
            "abilities":{"A01":{"id":"A01","idNew":"A01","name":"Strike","costPower":20,
                         "target":"u0000000000000002","currentCooldownRemaining":0}},
            "abilityList":{"A01":True}, "legacyAbilities":{}}, recursive=True)
        self.g.Inspect, _ = self.lua.execute(casting.API_FACTORY)(self.st)
        self.private = self.lua.table()
        metadata = self.lua.table(identifier="RiftReader2Casting", toc=self.lua.table(Version="0.4.2"))
        for filename in ("model.lua","ability_reference.lua","survival.lua","main.lua"):
            self.lua.execute((PACKAGE / filename).read_text(encoding="utf-8"), metadata, self.private)
        self.lua.execute("""
            local function rect(frame,x,w)
                frame.GetLeft=function() return x end; frame.GetTop=function() return 120 end
                frame.GetHeight=function() return 40 end; frame.GetWidth=function() return w end
            end
            rect(TEST_FRAMES.RR2CastingSecureButton,300,350)
            rect(TEST_FRAMES.RR2CastingStopButton,660,194)
        """)

    def command(self, msg):
        return self.private.Survival.Command(msg)

    def observe(self, clock):
        self.st.clock = clock
        self.g.TEST_HANDLERS["RR2 casting readout"]()
        wire = self.g.RiftReader2SurvivalWire
        if wire is None:
            return None
        self.assertLessEqual(len(wire.encode()), 8192)
        self.assertTrue(wire.startswith("RR2SURV1|") and wire.endswith("|ENDRR2SURV1"))
        return json.loads(wire[len("RR2SURV1|"):-len("|ENDRR2SURV1")])

    def test_no_implicit_bind_or_cast_and_shared_secure_mapping(self):
        self.assertIsNone(self.observe(22))
        self.assertFalse(self.command("select A01")[0])
        self.assertFalse(self.command("bind bad")[0])
        self.g.SLASHES.rr2surv[1][1]("bind " + NONCE)
        self.assertTrue(self.command("select A01")[0])
        self.assertFalse(self.command("select not-learned")[0])
        self.assertFalse(self.command("cast A01")[0])
        snap = self.observe(23)
        self.assertEqual((snap["status"],snap["sessionId"],snap["epoch"],snap["sequence"]),
                         ("observed",NONCE,1,1))
        self.assertEqual(snap["player"]["power"],0)
        self.assertIs(snap["player"]["dead"],False)
        self.assertEqual((snap["target"]["level"],snap["target"]["relation"],snap["target"]["coordX"]),
                         (40,"hostile",2))
        self.assertEqual(snap["ability"]["lookupId"],"A01")
        self.assertEqual(snap["catalog"]["entries"],{"A01":"Strike"})
        self.assertEqual(snap["cast"]["status"],"idle")
        self.assertEqual(snap["readiness"]["reason"],"insufficient-or-unknown-power")
        self.assertEqual(snap["controls"]["cast"]["macro"],"cast Strike")
        self.assertTrue(snap["controls"]["cast"]["uniqueLearnedName"])
        self.assertTrue(snap["controls"]["stop"]["mapped"])
        self.assertEqual(snap["controls"]["cast"]["left"],300)
        self.assertEqual(snap["controls"]["cast"]["width"],350)

    def test_eight_retained_frames_epoch_reset_and_clock_regression(self):
        self.command("bind " + NONCE)
        for i in range(12):
            self.observe(22+i)
        sequences = set()
        for wire in self.g.RiftReader2SurvivalFrames.values():
            sequences.add(json.loads(wire[9:-12])["sequence"])
        self.assertEqual(sequences,set(range(5,13)))
        self.assertEqual(self.observe(34)["sequence"],13)
        self.command("bind " + "a"*32)
        self.assertEqual((self.observe(35)["epoch"],self.observe(35)["sequence"]),(2,1))
        self.assertIsNone(self.observe(20))
        self.assertFalse(self.command("select A01")[0])

    def test_target_absence_and_field_availability(self):
        self.st.targetId = None
        self.st.units[self.st.playerId].power = None
        self.st.units[self.st.playerId].dead = None
        self.st.castError = True
        self.command("bind " + NONCE)
        s = self.observe(24)
        self.assertEqual(s["status"],"observed")
        self.assertNotIn("targetId",s)
        self.assertNotIn("dead",s["player"])
        self.assertNotIn("power",s["player"])
        self.assertEqual((s["readiness"]["reason"],s["cast"]["status"]),("no-target","unavailable"))
        self.st.lookupError=True
        self.assertEqual(self.observe(25)["status"],"unavailable")

    def test_catalog_pages_and_ambiguous_macro_names(self):
        for i in range(2,13):
            key=f"A{i:02}"
            self.st.abilityList[key]=True
            self.st.abilities[key]=self.lua.table(id=key,name="Strike" if i==2 else key)
        self.command("bind " + NONCE)
        self.command("select A01")
        first=self.observe(22)
        self.assertFalse(first["controls"]["cast"]["uniqueLearnedName"])
        self.assertEqual((first["catalog"]["count"],first["catalog"]["pages"]), (12,2))
        self.assertFalse(self.command("page 3")[0])
        self.assertTrue(self.command("page 2")[0])
        second=self.observe(23)
        self.assertEqual(len(second["catalog"]["entries"]),4)
        self.assertFalse(first["catalog"]["entries"].keys() & second["catalog"]["entries"].keys())
        self.st.secure=True
        self.assertFalse(self.command("select A02")[0])
        self.command("clear")
        self.assertIsNone(self.observe(24))

    def test_prepared_slots_work_without_remapping_in_combat(self):
        self.st.abilityList.A02=True
        self.st.abilities.A02=self.lua.table(id="A02",idNew="A02",name="Followup",
                                              target=self.st.targetId,costPower=0)
        self.command("bind "+NONCE)
        self.assertTrue(self.command("slot 1 A01")[0])
        self.assertTrue(self.command("slot 2 A02")[0])
        self.assertFalse(self.command("slot 3 A02")[0])
        self.st.secure=True
        self.assertFalse(self.command("slot 2 clear")[0])
        snap=self.observe(22)
        actions=snap["controls"]["actions"]
        self.assertEqual(set(actions),{"A01","A02"})
        self.assertNotIn("lookupId",snap["ability"])
        self.assertEqual(actions["A02"]["readiness"]["status"],"ready")
        self.assertEqual(actions["A01"]["readiness"]["reason"],"insufficient-or-unknown-power")
        self.assertEqual(self.g.TEST_MACROS.RR2SurvivalSlot2,"cast Followup\nstopattack")
        self.assertEqual(snap["controls"]["cancel"]["effectQualification"],"unverified")
        self.g.TEST_HANDLERS["RR2 casting damage"](None,self.lua.table(caster=self.st.playerId,
            target=self.st.targetId,abilityNew="A02",damage=7))
        event=self.observe(23)["lastEvent"]
        self.assertEqual((event["normalizedAbilityId"],event["target"],event["damage"]),("A02",self.st.targetId,7))
        self.st.secure=False
        self.assertTrue(self.command("slot 2 clear")[0])
        self.assertNotIn("A02",self.observe(24)["controls"]["actions"])

    def test_exact_self_effect_and_selected_incoming_have_independent_receipts(self):
        p, t = self.st.playerId, self.st.targetId
        self.st.abilityList.A02=True
        self.st.abilities.A02=self.lua.table(id="A02", idNew="A02", name="Self Heal",
                                             target=p, costPower=0)
        self.command("bind "+NONCE)
        self.command("slot 1 A02")
        self.command("select A02")
        frame=self.observe(22)
        slot=frame["controls"]["actions"]["A02"]
        self.assertEqual((slot["readiness"]["status"],slot["ability"]["target"]),("ready",p))
        self.assertEqual(frame["readiness"]["reason"],"ability-target-mismatch")
        self.assertEqual(frame["eventScope"],"selected-or-self/1")
        heal=self.g.TEST_HANDLERS["RR2 casting heal"]
        hit=self.g.TEST_HANDLERS["RR2 casting damage"]
        heal(None,self.lua.table(caster=p,target=p,abilityNew="A02",heal=9))
        hit(None,self.lua.table(caster="u0000000000000003",target=p,damage=12))
        hit(None,self.lua.table(caster=t,target=p,damage=0))
        hit(None,self.lua.table(caster=t,target=p,damage=13))
        frame=self.observe(22.5)
        self.assertEqual(frame["lastEvent"]["selectedTargetId"],t)
        self.assertEqual((frame["lastEvent"]["target"],frame["lastEvent"]["heal"]),(p,9))
        self.assertEqual((frame["lastIncoming"]["sequence"],frame["lastIncoming"]["caster"],
                          frame["lastIncoming"]["target"],frame["lastIncoming"]["damage"]),(1,t,p,13))
        self.st.targetId=None
        changed=self.observe(23)
        self.assertNotIn("lastIncoming",changed)
        self.assertNotIn("lastEvent",changed)
        self.assertEqual(changed["controls"]["actions"]["A02"]["readiness"]["status"],"ready")
        self.st.targetId=t
        expired=self.observe(24.25)
        self.assertNotIn("lastIncoming",expired)
        self.assertNotIn("lastEvent",expired)

    def test_effective_outcome_survives_later_immunity_for_five_seconds(self):
        p,t=self.st.playerId,self.st.targetId
        self.command("bind "+NONCE)
        self.observe(22)
        hit=self.g.TEST_HANDLERS["RR2 casting damage"]
        heal=self.g.TEST_HANDLERS["RR2 casting heal"]
        immune=self.g.TEST_HANDLERS["RR2 casting immune"]
        hit(None,self.lua.table(caster=p,target=t,abilityNew="A01",damage=42))
        immune(None,self.lua.table(caster=p,target=t,abilityNew="A01",damage=42))
        frame=self.observe(22.5)
        self.assertEqual(frame["positiveEventScope"], "last-effective-damage-or-heal/1")
        self.assertEqual((frame["lastEvent"]["kind"],frame["lastEvent"]["sequence"]),("immune",2))
        self.assertEqual((frame["lastPositiveEvent"]["kind"],frame["lastPositiveEvent"]["sequence"],
                          frame["lastPositiveEvent"]["damage"]),("damage",1,42))
        heal(None,self.lua.table(caster=p,target=p,abilityNew="A02",heal=0,overheal=100))
        old=self.observe(27)
        self.assertNotIn("lastEvent",old)
        self.assertEqual(old["lastPositiveEvent"]["normalizedAbilityId"],"A01")
        self.assertNotIn("lastPositiveEvent",self.observe(27.25))
        heal(None,self.lua.table(caster=p,target=p,abilityNew="A02",heal=15))
        self.assertEqual(self.observe(28)["lastPositiveEvent"]["target"],p)
        self.st.targetId=None
        self.assertNotIn("lastPositiveEvent",self.observe(29))

    def test_later_different_proc_preserves_exact_ability_receipt(self):
        p,t=self.st.playerId,self.st.targetId
        self.command("bind "+NONCE)
        self.observe(22)
        hit=self.g.TEST_HANDLERS["RR2 casting damage"]
        hit(None,self.lua.table(caster=p,target=t,abilityNew="A01",damage=100))
        hit(None,self.lua.table(caster=p,target=t,abilityNew="A02",damage=212))
        frame=self.observe(22.5)
        self.assertEqual(frame["positiveEventsScope"],"per-ability/1")
        self.assertEqual(frame["lastPositiveEvent"]["normalizedAbilityId"],"A02")
        self.assertEqual(frame["positiveEvents"]["A01"]["abilityName"],"Strike")
        self.assertEqual(frame["positiveEvents"]["A01"]["damage"],100)
        self.assertEqual(frame["positiveEvents"]["A02"]["damage"],212)
        for n in range(3,10):
            hit(None,self.lua.table(caster=p,target=t,abilityNew=f"A{n:02}",damage=n))
        self.assertEqual(set(self.observe(23)["positiveEvents"]),{f"A{n:02}" for n in range(2,10)})
        self.st.targetId=None
        self.assertFalse(self.observe(24)["positiveEvents"])
        self.st.targetId=t
        self.assertFalse(self.observe(28)["positiveEvents"])

    def test_batch_setup_validates_prepares_and_rolls_back_slots(self):
        new="a"*32
        self.st.abilityList.A02=True
        self.st.abilities.A02=self.lua.table(id="A02",idNew="A02",name="Heal",target=self.st.playerId)
        self.assertTrue(self.command("setup "+NONCE+" A01,A02")[0])
        first=self.observe(22)
        self.assertEqual(set(first["controls"]["actions"]),{"A01","A02"})
        self.assertEqual(first["sessionId"],NONCE)
        self.assertTrue(self.command("setup "+new+" A02")[0])
        second=self.observe(23)
        self.assertEqual(set(second["controls"]["actions"]),{"A02"})
        self.assertEqual((second["sessionId"],second["epoch"],second["controls"]["actions"]["A02"]["slot"]),(new,2,1))
        for invalid in ("A02,A02","A01,","A01,,A02","A03"):
            self.assertFalse(self.command("setup "+NONCE+" "+invalid)[0])
            self.assertIsNone(self.observe(24))
        self.st.abilities.A02.passive=True
        self.assertFalse(self.command("setup "+NONCE+" A01,A02")[0])
        self.assertIsNone(self.observe(25))
        self.assertTrue(self.command("bind "+NONCE)[0])
        self.assertFalse(self.observe(26)["controls"]["actions"])
        self.st.secure=True
        self.assertFalse(self.command("setup "+new+" A01")[0])
        self.assertIsNone(self.observe(27))
        self.assertFalse(self.command("bind "+new)[0])
        self.st.secure=False
        self.assertTrue(self.command("setup "+new+" A01")[0])
        self.assertEqual(set(self.observe(28)["controls"]["actions"]),{"A01"})


if __name__ == "__main__":
    unittest.main()
