"""Offline integration of the Tk bridge and its real local mailbox."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from scripts import waypoint_cli_protocol as protocol


CHILD = r'''
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import threading
import time
import scripts.physical_waypoints as app
import scripts.waypoint_connection as connection
import scripts.waypoint_observation as observation
import scripts.waypoint_recording as recording
import scripts.waypoint_cli_protocol as protocol

root = Path(sys.argv[1])
app.ROOT = root
(root / 'artifacts').mkdir(exist_ok=True)
def fake_startfile(path):
    (root / 'opened-log-directory').write_text(str(path), encoding='utf-8')
app.os.startfile = fake_startfile
original_server = protocol.LocalSessionServer
class Server(original_server):
    def __init__(self, *args, **kwargs):
        kwargs['root'] = root / 'sessions'
        super().__init__(*args, **kwargs)
    def poll(self, dispatch):
        # Let the test atomically stage both requests before this poll.
        if (root / 'hold-poll').exists():
            return
        import tkinter as tk
        tkroot = tk._default_root
        if not getattr(tkroot, '_diagnostic_test_clipboard', False):
            def clipboard_clear():
                (root / 'clipboard.txt').write_text('', encoding='utf-8')
            def clipboard_append(text):
                with (root / 'clipboard.txt').open('a', encoding='utf-8') as stream: stream.write(text)
            tkroot.clipboard_clear = clipboard_clear
            tkroot.clipboard_append = clipboard_append
            tkroot._diagnostic_test_clipboard = True
        def invoke_button(label):
            def visit(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'TButton' and child.cget('text') == label:
                        child.invoke(); return True
                    if visit(child): return True
                return False
            return visit(tkroot)
        if (root / 'gui-copy-diagnostics').exists():
            invoke_button('Copy diagnostics')
            (root / 'gui-copy-diagnostics').unlink()
            (root / 'gui-copy-complete').touch()
        if (root / 'gui-open-logs').exists():
            invoke_button('Open logs')
            (root / 'gui-open-logs').unlink()
            (root / 'gui-open-complete').touch()
        if (root / 'gui-callback-failure').exists():
            (root / 'gui-callback-failure').unlink()
            def fail_callback(): raise RuntimeError('gui-callback-marker')
            tkroot.after(0, fail_callback)
        if (root / 'thread-failure').exists():
            (root / 'thread-failure').unlink()
            def fail_thread(): raise RuntimeError('thread-failure-marker')
            worker = threading.Thread(target=fail_thread, name='diagnostic-test-worker')
            worker.start(); worker.join()
        draft = root / 'draft-fields'
        if draft.exists():
            entries = []
            def collect(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'TEntry': entries.append(child)
                    collect(child)
            collect(tk._default_root)
            for entry, value in zip(entries[:3], ('Pending draft', '5', '6')):
                entry.delete(0, 'end'); entry.insert(0, value)
            draft.unlink()
        gui_stop = root / 'gui-stop'
        if gui_stop.exists():
            def visit(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'TButton' and child.cget('text') == 'Stop Recording':
                        child.invoke()
                        return True
                    if visit(child):
                        return True
                return False
            visit(tk._default_root)
            gui_stop.unlink()
        return super().poll(dispatch)
protocol.LocalSessionServer = Server
@dataclass
class Position:
    x: float = 12.0
    y: float = 3.0
    z: float = 24.0
class Adapter:
    pid = 123
    target = {'hostName': 'AMD-DESKTOP', 'executableSha256': 'a' * 64, 'processId': 123,
              'processStartUtcTicks': '12345', 'executablePath': 'C:/rift.exe', 'hwnd': '99'}
    binding = {'runtimeIdentity': {'machine': 'AMD-DESKTOP', 'gameBuildSha256': 'a' * 64, 'unitKey': '1'}}
    input_receipt_path = root / 'no-input'
class NoForeground:
    def __init__(self, *args): pass
    def close(self): pass
app.ForegroundStop = NoForeground
app.PhysicalAdapter = lambda *args: Adapter()
def fake_zone(adapter):
    from datetime import datetime, timezone
    if (root / 'zone-fail').exists():
        raise app.WaypointError('simulated zone unavailable')
    number = 2 if (root / 'zone-different').exists() else 1
    return {'version': 1, 'zoneIdCandidate': f'z{number:08X}ABCDEF00', 'rawZoneKey': number,
            'source': 'fake-observation', 'observedAtUtc': datetime.now(timezone.utc).isoformat(),
            'target': dict(adapter.target), 'playerKey': '1'}
app.read_route_context = fake_zone
app.verify_stopped_pose = lambda *args, **kw: {'status': 'pass', 'samples': [{'position': {'x': 1, 'y': 2, 'z': 3}, 'bearing': 45}]}
pose = SimpleNamespace(position=Position(), bearing=45.0, acquired=time.monotonic(), source='fake-native.json')
observation.observe_batch = lambda *args, **kw: [pose]
class Recorder:
    def __init__(self, identity): pass
    def observe(self, pose): pass
    @property
    def progress(self): return {'sampleCount': 2, 'observedPathLength': 1.0}
    def finish(self):
        (root / 'finish-entered').touch()
        while (root / 'hold-finish').exists(): time.sleep(.01)
        return {'waypoints': [['Start', 1, 2], ['End', 2, 3]]}
recording.RouteRecorder = Recorder
connection.idle_read = lambda adapter, *args, **kw: (adapter, pose, False)
def route(adapter, points, stop, emit, **kw):
    (root / 'movement-called').write_text('yes')
    if (root / 'stopped').exists():
        raise app.Stopped('simulated stop')
    if (root / 'fail').exists():
        raise app.WaypointError('simulated movement failure')
    return [{'position': {'x': 1, 'y': 2, 'z': 3}, 'bearing': 45, 'distance': 0}]
app.run_route = route
app.run_facing = lambda *args, **kw: {'bearing': 45}
args = SimpleNamespace(expected_host='AMD-DESKTOP', physical_pid=123, basis=None,
                       route=None, face_waypoints=False, background=True, auto_reconnect=False,
                       initial_adapter=Adapter())
app.launch_window(args)
'''


class GuiBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.child = subprocess.Popen([sys.executable, '-c', CHILD, str(self.root)],
                                      cwd=Path(__file__).resolve().parents[1],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.addCleanup(self.cleanup_child)
        end = time.monotonic() + 10
        while time.monotonic() < end:
            sessions = protocol.discover_sessions(root=self.root / 'sessions')
            if sessions:
                self.session = sessions[0]
                break
            if self.child.poll() is not None:
                self.fail(self.child.stderr.read().decode(errors='replace'))
            time.sleep(.02)
        else:
            self.fail('GUI session did not start')
        # Initial background refresh must finish before mutations.
        end = time.monotonic() + 5
        while time.monotonic() < end:
            status = self.call('status')
            self.assertTrue(status['ok'], status)
            if not status['data']['app']['busy']:
                break
            time.sleep(.05)

    def cleanup_child(self):
        if self.child.poll() is None:
            try:
                if hasattr(self, 'session'):
                    self.call('app.close', {'discard': True})
                else:
                    self.child.kill()
                self.child.wait(timeout=5)
            except Exception:
                self.child.kill()
                self.child.wait(timeout=5)
        self.child.communicate()
        self.temp.cleanup()

    def call(self, op, args=None, rid=None):
        return protocol.request(self.session, op, args or {}, timeout=5, request_id=rid)

    def test_cached_status_and_route_dirty_revision_round_trip(self):
        status = self.call('status')['data']
        self.assertFalse(status['app']['visible'])
        self.assertFalse(status['inputSent'])
        self.assertEqual(status['pose']['source'], 'existing-idle-reader')
        added = self.call('route.add', {'name': 'A', 'x': 1, 'z': 2})
        self.assertTrue(added['ok'], added)
        revision = added['data']['revision']
        rejected = self.call('route.new', {'revision': revision})
        self.assertEqual(rejected['error']['code'], 'unsaved-route')
        stale = self.call('route.add', {'name': 'B', 'x': 3, 'z': 4, 'revision': revision - 1})
        self.assertEqual(stale['error']['code'], 'route-changed')
        path = self.root / 'route.json'
        self.assertTrue(self.call('route.save', {'file': str(path)})['ok'])
        self.assertTrue(self.call('route.new', {})['ok'])
        loaded = self.call('route.load', {'file': str(path)})
        self.assertTrue(loaded['ok'], loaded)
        listed = self.call('route.list')['data']
        self.assertEqual(listed['points'][0]['name'], 'A')
        self.assertFalse(listed['dirty'])

    def test_deferred_success_and_failure_publish_receipts(self):
        result = self.call('move.to', {'x': 1, 'z': 2, 'execute': True})
        self.assertTrue(result['ok'], result)
        receipt = json.loads(Path(result['data']['receipt']).read_text())
        self.assertEqual(receipt['status'], 'completed')
        (self.root / 'fail').write_text('yes')
        failed = self.call('move.to', {'x': 3, 'z': 4, 'execute': True})
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['error']['code'], 'operation-failed')
        receipt = json.loads(Path(failed['data']['receipt']).read_text())
        self.assertEqual(receipt['failure']['reason'], 'simulated movement failure')

    def test_stopped_worker_reports_cancelled_receipt(self):
        (self.root / 'stopped').touch()
        stopped = self.call('move.to', {'x': 1, 'z': 2, 'execute': True})
        self.assertFalse(stopped['ok'])
        self.assertEqual(stopped['error']['code'], 'cancelled')
        self.assertEqual(stopped['error']['exitCode'], 130)
        receipt = json.loads(Path(stopped['data']['receipt']).read_text())
        self.assertEqual(receipt['status'], 'stopped')
        self.assertEqual(receipt['stopVerification']['status'], 'pass')

    def test_record_save_and_cancel_does_not_reuse_old_destination(self):
        saved_path = self.root / 'saved.json'
        self.assertTrue(self.call('record.start')['ok'])
        saved = self.call('record.stop', {'file': str(saved_path)})
        self.assertTrue(saved['ok'], saved)
        self.assertEqual(json.loads(saved_path.read_text())['waypoints'][0][0], 'Start')

        self.assertTrue(self.call('record.start')['ok'])
        (self.root / 'finish-entered').unlink(missing_ok=True)
        (self.root / 'hold-finish').touch()
        old_path = self.root / 'cancelled.json'
        results = {}
        def pending_stop():
            results['stop'] = self.call('record.stop', {'file': str(old_path)})
        thread = threading.Thread(target=pending_stop)
        thread.start()
        end = time.monotonic() + 5
        while not (self.root / 'finish-entered').exists() and time.monotonic() < end:
            time.sleep(.01)
        self.assertTrue((self.root / 'finish-entered').exists())
        replacement = self.call('record.stop', {'file': str(self.root / 'replacement.json')})
        self.assertEqual(replacement['error']['code'], 'recording-finishing')
        def cancel():
            results['cancel'] = self.call('record.cancel', rid='cancel-recording')
        cancel_thread = threading.Thread(target=cancel)
        cancel_thread.start()
        # Wait for cancellation dispatch before allowing the worker to publish.
        end = time.monotonic() + 5
        accepted = Path(self.session['path']) / 'accepted' / 'cancel-recording.json'
        while not accepted.exists() and time.monotonic() < end:
            time.sleep(.01)
        self.assertTrue(accepted.exists())
        (self.root / 'hold-finish').unlink()
        thread.join(5); cancel_thread.join(5)
        self.assertTrue(results['cancel']['ok'], results)
        self.assertFalse(results['stop']['ok'], results)
        self.assertFalse(old_path.exists())

        # Stop the next recording through the GUI's existing button, which uses
        # its default destination rather than supplying a new CLI file.
        self.assertTrue(self.call('record.start')['ok'])
        (self.root / 'gui-stop').touch()
        end = time.monotonic() + 5
        while not list((self.root / 'artifacts').glob('recorded-route-*.json')) and time.monotonic() < end:
            time.sleep(.02)
        self.assertTrue(list((self.root / 'artifacts').glob('recorded-route-*.json')))
        self.assertFalse(old_path.exists())

    def test_correlated_stop_cancels_queued_request_before_admission(self):
        hold = self.root / 'hold-poll'
        hold.touch()
        time.sleep(.2)
        session = self.session
        deadline = (protocol._now() + __import__('datetime').timedelta(seconds=5)).isoformat()
        def stage(rid, command, arguments):
            msg = {**{k: session[k] for k in ('version', 'sessionId', 'host', 'pid', 'processStart')},
                   'requestId': rid, 'command': command, 'arguments': arguments, 'deadlineUtc': deadline}
            protocol._write_once(Path(session['path']) / 'requests' / (rid + '.json'), msg)
        stage('queued-move', 'move.to', {'x': 1, 'z': 2, 'execute': True})
        stage('correlated-stop', 'stop', {'requestId': 'queued-move'})
        hold.unlink()
        end = time.monotonic() + 5
        responses = Path(session['path']) / 'responses'
        while not (responses / 'queued-move.json').exists() and time.monotonic() < end:
            time.sleep(.02)
        result = protocol._read(responses / 'queued-move.json')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['exitCode'], 130)
        self.assertFalse((self.root / 'movement-called').exists())

    def test_stop_priority_cancels_already_queued_move(self):
        hold = self.root / 'hold-poll'
        hold.touch()
        time.sleep(.2)
        session = self.session
        deadline = (protocol._now() + __import__('datetime').timedelta(seconds=5)).isoformat()
        def stage(rid, command, arguments):
            msg = {**{k: session[k] for k in ('version', 'sessionId', 'host', 'pid', 'processStart')},
                   'requestId': rid, 'command': command, 'arguments': arguments, 'deadlineUtc': deadline}
            protocol._write_once(Path(session['path']) / 'requests' / (rid + '.json'), msg)
        stage('queued-move', 'move.to', {'x': 1, 'z': 2, 'execute': True})
        stage('stop', 'stop', {})
        hold.unlink()
        end = time.monotonic() + 5
        path = Path(session['path']) / 'responses' / 'queued-move.json'
        while not path.exists() and time.monotonic() < end:
            time.sleep(.02)
        self.assertTrue(path.exists())
        self.assertEqual(protocol._read(path)['error']['code'], 'cancelled-by-stop')
        self.assertFalse((self.root / 'movement-called').exists())

    def test_zone_library_and_explicit_tagging(self):
        zone = self.call('zone.refresh')
        self.assertTrue(zone['ok'], zone)
        self.assertEqual(zone['data']['context']['zoneIdCandidate'], 'z00000001ABCDEF00')
        legacy = self.root / 'legacy.json'
        legacy_data = {'waypoints': [['Legacy', 1, 2]], 'heights': [None]}
        original = json.dumps(legacy_data)
        legacy.write_text(original, encoding='utf-8')
        imported = self.call('library.import', {'file': str(legacy), 'name': 'Legacy', 'route_id': 'legacy'})
        self.assertTrue(imported['ok'], imported)
        self.assertEqual(legacy.read_text(encoding='utf-8'), original)
        self.assertIsNone(imported['data']['routeContext'])
        loaded = self.call('library.load', {'route_id': 'legacy'})
        self.assertTrue(loaded['ok'], loaded)
        context = self.call('route.context')['data']
        self.assertIsNone(context['routeContext'])
        self.assertEqual(context['comparison'], 'unknown')
        tagged = self.call('route.tag-zone')
        self.assertTrue(tagged['ok'], tagged)
        self.assertEqual(tagged['data']['comparison'], 'matching')
        self.assertTrue(self.call('route.list')['data']['dirty'])
        saved = self.call('library.save', {'name': 'Tagged', 'route_id': 'tagged'})
        self.assertTrue(saved['ok'], saved)
        self.assertEqual(saved['data']['routeContext']['zoneIdCandidate'], 'z00000001ABCDEF00')
        listing = self.call('library.list', {'zone': 'matching'})
        self.assertTrue(listing['ok'], listing)
        self.assertEqual([row['id'] for row in listing['data']['routes']], ['tagged'])
        self.assertTrue(self.call('library.load', {'route_id': 'tagged', 'discard': True})['ok'])
        self.assertEqual(self.call('route.context')['data']['comparison'], 'matching')
        renamed = self.call('library.save', {'name': 'Renamed', 'route_id': 'tagged', 'overwrite': True})
        self.assertTrue(renamed['ok'], renamed)
        current = self.call('route.list')['data']
        self.assertEqual(current['document']['routeName'], 'Renamed')
        self.assertFalse(current['dirty'])
        self.assertIsNone(json.loads(legacy.read_text()).get('routeContext'))

    def test_replay_status_matches_snapshot_and_explains_endpoint(self):
        self.assertTrue(self.call('route.add', {'name': 'Here', 'x': 12, 'z': 24})['ok'])
        self.assertTrue(self.call('route.add', {'name': 'End', 'x': 13, 'z': 24})['ok'])
        playback = self.call('playback.status')['data']
        self.assertTrue(playback['faceWaypoints'])
        self.assertTrue(playback['readiness']['forward']['ready'], playback)
        self.assertFalse(playback['readiness']['reverse']['ready'])
        self.assertIn('endpoint', playback['readiness']['reverse']['reason'])
        self.assertFalse(playback['readiness']['resume']['ready'])
        self.assertIn('no saved', playback['readiness']['resume']['reason'])
        snapshot = self.call('status')['data']
        self.assertEqual(playback['readiness'], snapshot['playback']['readiness'])
        self.assertEqual(snapshot['app']['name'], "Joey D's Waypoints")
        self.assertEqual(snapshot['app']['version'], '1.1.0')
        self.assertFalse((self.root / 'movement-called').exists())

    def test_current_update_replaces_measurement_and_manual_edit_reports_loss(self):
        self.assertTrue(self.call('route.add', {'name': 'Keep name', 'x': 1, 'z': 2})['ok'])
        self.assertTrue(self.call('route.add', {'name': 'Other', 'x': 3, 'z': 4})['ok'])
        updated = self.call('route.update', {'point': 1, 'current': True})
        self.assertTrue(updated['ok'], updated)
        self.assertTrue(updated['data']['change']['measurementReplaced'])
        listing = self.call('route.list')['data']
        self.assertEqual(listing['document']['waypoints'], [['Keep name', 12., 24.], ['Other', 3., 4.]])
        self.assertEqual(listing['document']['heights'], [3., None])
        self.assertEqual(listing['selected'], [1])
        changed = self.call('route.update', {'point': 1, 'x': 12.5})
        self.assertTrue(changed['ok'], changed)
        self.assertTrue(changed['data']['change']['measurementDiscarded'])
        self.assertTrue(changed['data']['change']['coordinatesChanged'])
        self.assertFalse((self.root / 'movement-called').exists())

    def test_cli_selection_requires_explicit_draft_discard(self):
        self.assertTrue(self.call('route.add', {'name': 'One', 'x': 1, 'z': 2})['ok'])
        self.assertTrue(self.call('route.add', {'name': 'Two', 'x': 3, 'z': 4})['ok'])
        (self.root / 'draft-fields').touch()
        listing = self.call('route.list')['data']
        self.assertTrue(listing['editDraft']['pending'])
        self.assertEqual(listing['selected'], [2])
        refused = self.call('route.select', {'point': 1})
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error']['code'], 'unapplied-edit')
        saved = self.call('route.save', {'file': str(self.root / 'draft-not-saved.json')})
        self.assertFalse(saved['ok'])
        self.assertFalse((self.root / 'draft-not-saved.json').exists())
        chosen = self.call('route.select', {'point': 1, 'discard_draft': True})
        self.assertTrue(chosen['ok'], chosen)
        listing = self.call('route.list')['data']
        self.assertFalse(listing['editDraft']['pending'])
        self.assertEqual(listing['selected'], [1])
        self.assertFalse((self.root / 'movement-called').exists())

    def test_diagnostics_report_keeps_route_request_and_full_malformed_json_trace(self):
        self.assertTrue(self.call('route.add', {'name':'Current', 'x':1, 'z':2})['ok'])
        current = self.root / 'current-route.json'
        self.assertTrue(self.call('route.save', {'file':str(current)})['ok'])
        malformed = self.root / 'malformed-route.json'
        malformed.write_text('{"waypoints": [', encoding='utf-8')
        failed = self.call('route.load', {'file':str(malformed)}, rid='malformed-route-request')
        self.assertFalse(failed['ok'], failed)
        report = self.call('diagnostics.show')['data']['text']
        for marker in ("Joey D's Waypoints diagnostics", 'App version: 1.1.0',
                       current.name, 'malformed-route-request', 'JSONDecodeError',
                       'Traceback (most recent call last):'):
            self.assertIn(marker, report)
        self.assertFalse((self.root / 'movement-called').exists())

    def test_diagnostics_capture_unhandled_gui_callback_and_thread_failure(self):
        (self.root / 'gui-callback-failure').touch()
        (self.root / 'thread-failure').touch()
        end = time.monotonic() + 5
        report = ''
        while time.monotonic() < end:
            self.assertTrue(self.call('status')['ok'])
            report = self.call('diagnostics.show')['data']['text']
            if 'gui-callback-marker' in report and 'thread-failure-marker' in report:
                break
            time.sleep(.03)
        for marker in ('gui-callback-marker', 'thread-failure-marker',
                       'diagnostic-test-worker', 'Traceback (most recent call last):'):
            self.assertIn(marker, report)
        self.assertIsNone(self.child.poll())

    def test_diagnostics_cli_and_activity_buttons_use_mocked_clipboard_and_explorer(self):
        copied = self.call('diagnostics.copy')
        self.assertTrue(copied['ok'], copied)
        self.assertTrue(copied['data']['copied'])
        text = (self.root / 'clipboard.txt').read_text(encoding='utf-8')
        self.assertEqual(copied['data']['characters'], len(text))
        self.assertIn("Joey D's Waypoints diagnostics", text)
        opened = self.call('diagnostics.open')
        self.assertTrue(opened['ok'], opened)
        self.assertEqual((self.root / 'opened-log-directory').read_text(encoding='utf-8'),
                         opened['data']['directory'])

        (self.root / 'clipboard.txt').unlink(missing_ok=True)
        (self.root / 'opened-log-directory').unlink(missing_ok=True)
        (self.root / 'gui-copy-diagnostics').touch()
        (self.root / 'gui-open-logs').touch()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.call('status')
            if ((self.root / 'gui-copy-complete').exists()
                    and (self.root / 'gui-open-complete').exists()):
                break
            time.sleep(.03)
        self.assertTrue((self.root / 'gui-copy-complete').exists())
        self.assertTrue((self.root / 'gui-open-complete').exists())
        self.assertIn("Joey D's Waypoints diagnostics",
                      (self.root / 'clipboard.txt').read_text(encoding='utf-8'))
        self.assertIn('waypoint-logs',
                      (self.root / 'opened-log-directory').read_text(encoding='utf-8'))
        self.assertFalse((self.root / 'movement-called').exists())

    def test_zone_guard_rechecks_before_movement(self):
        self.assertTrue(self.call('route.add', {'name': 'A', 'x': 1, 'z': 2})['ok'])
        self.assertTrue(self.call('route.tag-zone')['ok'])
        (self.root / 'zone-different').touch()
        blocked = self.call('route.run', {'execute': True})
        self.assertFalse(blocked['ok'], blocked)
        self.assertIn('zone', blocked['error']['message'].lower())
        self.assertFalse((self.root / 'movement-called').exists())
        (self.root / 'zone-different').unlink()
        (self.root / 'zone-fail').touch()
        blocked = self.call('route.run', {'execute': True})
        self.assertFalse(blocked['ok'], blocked)
        self.assertFalse((self.root / 'movement-called').exists())
        (self.root / 'zone-fail').unlink()
        completed = self.call('route.run', {'execute': True})
        self.assertTrue(completed['ok'], completed)
        self.assertTrue((self.root / 'movement-called').exists())


if __name__ == '__main__':
    unittest.main()
