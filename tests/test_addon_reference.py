from pathlib import Path
import json
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'addon' / 'RiftReader2'
FIXTURE = ROOT / 'contracts' / 'addon' / 'fixtures' / 'reference-v1.json'
NONCE = '0123456789abcdef0123456789abcdef'
FIELDS = ['coordX','coordY','coordZ','health','healthMax','mana','manaMax','power','combo','planar','planarMax','combat','dead','mounted','zone']

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''state={clock=1, player="player_1", detail={coordX=0,coordY=2,coordZ=-3,health=100,healthMax=100,mana=20,manaMax=40,power=0,combo=0,planar=0,planarMax=5,combat=false,dead=false,mounted=false,zone="Sanctum"}}; calls=0
        api={Time={Frame=function() return state.clock end},Unit={Lookup=function() calls=calls+1; if state.race and calls%2==0 then return "other" end; return state.player end, Detail=function() return state.detail end}}''')
        self.private = self.lua.table()
        self.lua.execute((PACKAGE/'reference.lua').read_text(), self.lua.table(), self.private)
        self.instance = self.private.Reference.New(self.lua.globals().api)
        self.bind = self.lua.eval('function(p,n) p:Bind(n) end')
        self.update = self.lua.eval('function(p) return p:Update() end')
        self.bind(self.instance, NONCE)
    def sample(self):
        result = self.update(self.instance)
        frame = result[0] if isinstance(result, tuple) else result
        if frame is None: return None, None
        self.assertTrue(frame.startswith('RR2R1|') and frame.endswith('|ENDRR2R1'))
        self.assertLessEqual(len(frame),8192)
        return frame, json.loads(frame[6:-9])
    def test_fixture(self):
        before, a = self.sample()
        self.lua.execute('state.clock=2; state.detail.mana=0; state.detail.combat=true')
        after, b = self.sample()
        expected = json.loads(FIXTURE.read_text())
        self.assertEqual(expected, dict(nonce=NONCE,before=a,after=b,beforeFrame=before,afterFrame=after))
    def test_types_and_absence(self):
        self.lua.execute('state.detail.mana=nil; state.detail.health=0/0; state.detail.dead=0; state.detail.zone="\\001"')
        _, data = self.sample(); f=data['fields']
        self.assertEqual(set(f),set(FIELDS))
        self.assertEqual(f['mana'], {'status':'unavailable'})
        for name in ('health','dead','zone'): self.assertEqual(f[name], {'status':'invalid'})
        self.assertEqual(f['power'], {'status':'ok','value':0})
        self.assertEqual(f['combat'], {'status':'ok','value':False})
    def test_clock_and_identity(self):
        _, a=self.sample()
        self.lua.execute('state.clock=nil'); _, b=self.sample()
        self.assertEqual(b['clock']['status'],'unavailable')
        self.assertEqual(b['player']['status'],'unavailable')
        self.assertTrue(all(v == {'status':'unavailable'} for v in b['fields'].values()))
        self.assertIsNone(self.sample()[0])
        self.lua.execute('state.clock=2; state.race=true'); _, c=self.sample()
        self.assertEqual(c['epoch'],a['epoch']+1)
        self.assertEqual(c['player']['status'],'invalid')
        self.assertTrue(all(v == {'status':'unavailable'} for v in c['fields'].values()))
        self.lua.execute('state.clock=1; state.race=false'); _, d=self.sample()
        self.assertEqual(d['epoch'],c['epoch']+1)
    def test_failures_and_exhaustion(self):
        self.lua.execute('state.clock=-1')
        _, data=self.sample()
        self.assertEqual(data['clock'], {'status':'invalid'})
        self.assertIsNone(self.sample()[0])
        self.lua.execute('state.clock=1; state.player=nil')
        _, data=self.sample()
        self.assertEqual(data['player'], {'status':'unavailable'})
        self.lua.execute('state.clock=2; state.player=123')
        _, data=self.sample()
        self.assertEqual(data['player'], {'status':'invalid'})
        self.lua.execute('state.clock=3; state.player="p"; state.detail=42')
        _, data=self.sample()
        self.assertTrue(all(v == {'status':'invalid'} for v in data['fields'].values()))
        self.lua.execute('state.clock=4; state.detail=nil')
        _, data=self.sample()
        self.assertTrue(all(v == {'status':'unavailable'} for v in data['fields'].values()))
        self.instance.Sequence=9007199254740991
        self.lua.execute('state.clock=5')
        self.assertIsNone(self.sample()[0])
        self.assertTrue(self.instance.Stopped)
        self.assertIsNone(self.instance.Frame)

    def test_rebind(self):
        frame, a=self.sample()
        self.bind(self.instance, 'f'*32)
        self.assertIsNone(self.instance.Frame)
        frame, b=self.sample()
        self.assertEqual(b['sessionId'],'f'*32)
        self.assertGreater(b['sequence'],a['sequence'])

class ReferenceMainTests(unittest.TestCase):
    def setUp(self):
        from tests.test_guidance_addon import MAIN_STUB
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MAIN_STUB)
        self.private = self.lua.table()
        for name in ('wire.lua','producer.lua','reference.lua','live.lua','guidance.lua','main.lua'):
            self.lua.execute((PACKAGE/name).read_text(), self.lua.table(), self.private)
        self.lua.execute('TEST_SLASH.rr2guide[1][1]("bind lab1 ' + NONCE + '")')
    def tick(self, clock):
        self.lua.globals().TEST_STATE.clock = clock
        self.lua.execute('TEST_HANDLERS["RiftReader2 update"]()')
    def test_retention_rebind_and_identity_clear(self):
        self.tick(100)
        for i in range(1, 12): self.tick(100+i)
        g=self.lua.globals()
        self.assertEqual(len(g.RiftReader2_ReferenceFrames),8)
        self.lua.execute('TEST_STATE.player="other"')
        self.tick(112)
        self.assertEqual(len(g.RiftReader2_ReferenceFrames),1)
        self.lua.execute('TEST_STATE.clock=nil; TEST_HANDLERS["RiftReader2 update"]()')
        self.assertEqual(len(g.RiftReader2_ReferenceFrames),1)
        self.assertEqual(json.loads(g.RiftReader2_ReferenceFrame[6:-9])['player']['status'],'unavailable')
        self.lua.execute('TEST_SLASH.rr2guide[1][1]("rebind lab1 ' + 'f'*32 + '")')
        self.assertIsNone(g.RiftReader2_ReferenceFrame)
        self.assertEqual(len(g.RiftReader2_ReferenceFrames),0)
        self.tick(113)
        self.assertEqual(json.loads(g.RiftReader2_ReferenceFrame[6:-9])['sessionId'],'f'*32)
        # A new addon load naturally discards the previous published globals.
        self.lua.execute((PACKAGE/'main.lua').read_text(), self.lua.table(), self.private)
        self.assertIsNone(g.RiftReader2_ReferenceFrame)
        self.assertEqual(len(g.RiftReader2_ReferenceFrames),0)

if __name__ == '__main__': unittest.main()
