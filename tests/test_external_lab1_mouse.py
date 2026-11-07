from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
from contextlib import ExitStack, nullcontext, closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
from scripts import external_lab1_mouse as route
real_queue_check = route.require_queue_clear
real_controller_check = route.require_controller_absent

class Mutex:
    abandoned = False
    released = False
    def __enter__(self): return self
    def __exit__(self, *args): self.released = True

class Client:
    def __init__(self): self.events = []; self.factory = SimpleNamespace(_rr2_closed=SimpleNamespace(is_set=lambda: True))
    def mouseMove(self, *xy): self.events.append(('move', *xy))
    def mouseDown(self, button): self.events.append(('down', button))
    def mouseUp(self, button): self.events.append(('up', button))
    def disconnect(self): self.events.append(('disconnect',))

class RouteTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/'artifacts').mkdir()
        self.client=Client(); self.mutex=Mutex(); self.stack=ExitStack(); self.addCleanup(self.stack.close)
        def mock(obj, name, value): self.stack.enter_context(patch.object(obj,name,value))
        mock(route,'guest_game_identity',lambda *a: {'pid':1}); mock(route,'_launch_lock',lambda lab: nullcontext()); mock(route,'require_queue_clear',lambda:None); mock(route,'ROOT',self.root); mock(route.native,'validate_config',lambda *a,**k: a[:2]); mock(route.native,'ControlMutex',lambda vmx:self.mutex)
        mock(route.native,'collect_identity',lambda c:{'id':1}); mock(route.native,'verify_identity',lambda c,i:i); mock(route.native,'connect',lambda c:self.client)
        def capture(client,path): path.write_bytes(b'image'); return (100,80)
        mock(route.native,'_capture',capture); mock(route,'require_controller_absent',lambda:None); mock(route.time,'sleep',lambda _:None)
    def args(self): return SimpleNamespace(action='click',x=10,y=20,output=self.root/'artifacts'/'run')
    def test_review_then_same_client_click(self):
        def review(capture,timeout):
            self.assertEqual(self.client.events,[]); self.assertTrue(capture['captureId']); return 'reviewed screenshot'
        with patch.object(route,'read_review',review): result=route.run(self.args())
        self.assertEqual(self.client.events,[('move',10,20),('down',1),('up',1),('up',1),('disconnect',)])
        self.assertTrue(result['buttonReleaseSent'] and result['connectionClosed'] and self.mutex.released)
        self.assertIn('RIFT-Lab-1',str(route.VMX))
    def test_review_decline_blocks_input(self):
        with patch.object(route,'read_review',side_effect=ValueError('declined')):
            with self.assertRaises(ValueError): route.run(self.args())
        self.assertEqual(self.client.events,[('disconnect',)]); self.assertTrue(self.mutex.released)
    def test_release_and_disconnect_after_down_failure(self):
        def fail(button): self.client.events.append(('down',button)); raise OSError('failed')
        self.client.mouseDown=fail
        with patch.object(route,'read_review',return_value='reviewed screenshot'):
            with self.assertRaises(OSError): route.run(self.args())
        self.assertIn(('up',1),self.client.events); self.assertEqual(self.client.events[-1],('disconnect',)); self.assertTrue(self.mutex.released)
    def test_controller_arrives_during_review(self):
        with patch.object(route,'require_controller_absent',side_effect=[None,route.native.Blocked('controller-listening')]), patch.object(route,'read_review',return_value='reviewed screenshot'):
            with self.assertRaises(route.native.Blocked): route.run(self.args())
        self.assertEqual(self.client.events,[('disconnect',)]); self.assertTrue(self.mutex.released)
    def test_listener_table_empty_listening_and_error(self):
        import struct, socket
        config=SimpleNamespace(vmx=route.VMX.resolve(),vnc_port=5905,ui_port=49811,agent_port=49810)
        def table(port): return struct.pack('<I6I',1,2,0,socket.htons(port),0,0,99)
        with patch.object(route.HostConfig,'load',return_value=config), patch.object(route,'listener_table',return_value=struct.pack('<I',0)):
            real_controller_check()
        with patch.object(route.HostConfig,'load',return_value=config), patch.object(route,'listener_table',return_value=table(49810)):
            with self.assertRaises(route.native.Blocked): real_controller_check()
        with patch.object(route.HostConfig,'load',return_value=config), patch.object(route,'listener_table',side_effect=route.native.Blocked('query-failed')):
            with self.assertRaises(route.native.Blocked): real_controller_check()
    def test_changed_game_epoch_blocks_before_input(self):
        with patch.object(route,'guest_game_identity',side_effect=[{'pid':1},{'pid':2}]), patch.object(route,'read_review',return_value='reviewed screenshot'):
            with self.assertRaises(route.native.Blocked): route.run(self.args())
        self.assertEqual(self.client.events,[('disconnect',)]); self.assertTrue(self.mutex.released)
    def test_interactive_alias_requires_matching_sids_and_restores_username(self):
        import ctypes
        original=ctypes.create_unicode_buffer('cached-name'); calls=[]
        guest=SimpleNamespace(_username=original)
        def run(*args,**kwargs): calls.append((guest._username.value,args))
        guest.run=run
        ownership={'machine':'RIFT-LAB-1','currentSid':'S-1','interactiveSid':'S-1','gameOwnerSid':'S-2','interactiveName':'LAB\\user'}
        with self.assertRaises(route.native.Blocked): route.interactive_game_probe(guest,'test',ownership)
        self.assertEqual(calls,[]); self.assertIs(guest._username,original)
        ownership['gameOwnerSid']='S-1'; route.interactive_game_probe(guest,'test',ownership)
        self.assertEqual(calls[0][0],ownership['interactiveName']); self.assertIn('-interactive',calls[0][1]); self.assertIs(guest._username,original)
    def test_stale_guest_observation_blocks_input(self):
        with patch.object(route.time,'monotonic',side_effect=[10.0,21.0]), patch.object(route,'read_review',return_value='reviewed screenshot'):
            with self.assertRaises(route.native.Blocked): route.run(self.args())
        self.assertEqual(self.client.events,[('disconnect',)]); self.assertTrue(self.mutex.released)
    def test_unconfirmed_disconnect_is_failure(self):
        self.client.factory._rr2_closed.is_set=lambda: False
        with patch.object(route,'read_review',return_value='reviewed screenshot'):
            with self.assertRaises(route.native.Blocked): route.run(self.args())
        self.assertTrue(self.mutex.released)
    def test_queue_requires_quarantine_and_no_pending_lab1(self):
        path=self.root/'queue.sqlite3'
        with closing(sqlite3.connect(path, isolation_level=None)) as db:
            db.execute('CREATE TABLE resources (name TEXT, blocked INTEGER, holder TEXT)')
            db.execute('CREATE TABLE requests (state TEXT, specification TEXT)')
            db.execute("INSERT INTO resources VALUES ('vm:rift-lab-1',1,NULL)")
        with patch.object(route,'QUEUE',path):
            real_queue_check()
            with closing(sqlite3.connect(path, isolation_level=None)) as db: db.execute("UPDATE resources SET blocked=0")
            with self.assertRaises(route.native.Blocked): real_queue_check()
            with closing(sqlite3.connect(path, isolation_level=None)) as db:
                db.execute("UPDATE resources SET blocked=1")
                db.execute('INSERT INTO requests VALUES (?,?)',('queued','{"resources":{"vm:rift-lab-1":"epoch"}}'))
            with self.assertRaises(route.native.Blocked): real_queue_check()
    def test_abandoned_owner_blocks(self):
        self.mutex.abandoned=True
        with self.assertRaises(route.native.Blocked): route.run(self.args())
        self.assertEqual(self.client.events,[]); self.assertTrue(self.mutex.released)

if __name__=='__main__': main()
