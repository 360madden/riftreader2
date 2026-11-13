"""Focused console contract checks; never opens the GUI or reads RIFT."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import waypoint_cli_protocol as protocol
from scripts import waypoints_cli as cli


class CliTests(unittest.TestCase):
    def test_machine_json_survives_legacy_windows_output_encoding(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        envelope = cli.result("status", data={"state": "Stopped — no input active.", "name": "地図"})
        with contextlib.redirect_stdout(stream):
            cli.emit(envelope, machine=True)
        stream.flush()
        decoded = raw.getvalue().decode("utf-8")
        self.assertEqual(json.loads(decoded), envelope)
        self.assertEqual(len(decoded.splitlines()), 1)

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_no_args_and_help_alias(self):
        self.assertEqual(self.call()[0], 0)
        help_text = self.call()[1]
        self.assertIn("Control Joey D's Waypoints", help_text)
        version = self.call('--version')
        self.assertEqual(version[0], 0)
        self.assertIn("Joey D's Waypoints 1.1.0", version[1])
        self.assertIn('rr2-waypoints', version[1])
        alias = self.call('help', 'radar', 'set')
        direct = self.call('radar', 'set', '--help')
        self.assertEqual(alias, direct)
        for phrase in ('Requires:', 'Effects:', 'Defaults:', 'Example:'):
            self.assertIn(phrase, direct[1])

    def test_all_leaf_help(self):
        for command in ('status doctor capabilities stop app.list app.open app.show app.hide app.close '
                        'route.list route.load route.save route.new route.add route.update route.remove '
                        'route.reorder route.select route.undo route.validate route.run radar.status radar.show '
                        'radar.hide radar.set radar.move radar.reset-position radar.lock radar.unlock beacons.status beacons.show '
                        'beacons.hide beacons.set beacons.reset guide.status guide.start guide.stop trail.status trail.start '
                        'trail.stop trail.list trail.save trail.clear record.status record.start record.stop '
                        'record.cancel move.to face playback.start playback.resume playback.status '
                        'view.status view.save view.load view.open view.open-3d receipt.list receipt.show '
                        'zone.status zone.refresh route.context route.tag-zone '
                        'diagnostics.status diagnostics.show diagnostics.copy diagnostics.open '
                        'library.list library.save library.import library.load library.show').split():
            with self.subTest(command=command):
                self.assertEqual(self.call(*command.split('.'), '--help')[0], 0)

    def test_common_flags_survive_any_level(self):
        parser = cli.build_parser()
        for argv in (['--session','a','radar','set','--opacity','70'],
                     ['radar','--session','a','set','--opacity','70'],
                     ['radar','set','--opacity','70','--session','a']):
            self.assertEqual(parser.parse_args(argv).session, 'a')

    def test_library_and_zone_dispatch_use_existing_session_only(self):
        cases = [
            (("zone", "status"), "zone.status", {}),
            (("zone", "refresh"), "zone.refresh", {}),
            (("route", "context"), "route.context", {}),
            (("route", "tag-zone"), "route.tag-zone", {}),
            (("library", "list"), "library.list", {"zone":"all"}),
            (("library", "list", "--zone", "matching", "--search", "Camp"), "library.list", {"zone":"matching", "search":"Camp"}),
            (("library", "save", "Camp", "--id", "camp", "--overwrite"), "library.save", {"name":"Camp", "route_id":"camp", "overwrite":True}),
            (("library", "import", "source.json", "--name", "Camp", "--id", "camp"), "library.import", {"file":str(Path("source.json").resolve()), "name":"Camp", "route_id":"camp", "overwrite":False}),
            (("library", "load", "camp", "--discard"), "library.load", {"route_id":"camp", "discard":True}),
            (("library", "show", "camp"), "library.show", {"route_id":"camp"}),
        ]
        for argv, operation, payload in cases:
            with self.subTest(argv=argv), patch.object(protocol, 'resolve_session', return_value={}), patch.object(protocol, 'request', return_value=cli.result(operation, data={})) as request, patch.object(cli.subprocess, 'Popen') as spawn:
                self.assertEqual(self.call(*argv, '--json')[0], 0)
                self.assertEqual(request.call_args.args[1:3], (operation, payload))
                spawn.assert_not_called()

    def test_route_update_current_dispatches_read_only_capture_without_execute(self):
        reply = cli.result('route.update', data={'revision':3, 'selected':[2],
            'change':{'nameChanged':True, 'coordinatesChanged':True, 'measurementDiscarded':False,
                      'recordingDiscarded':True, 'measurementReplaced':True}})
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=reply) as request:
            code,out,_ = self.call('route','update','2','--current','--name','Fresh position')
        self.assertEqual(code, 0)
        self.assertEqual(request.call_args.args[1:3], ('route.update', {
            'name':'Fresh position', 'current':True, 'point':2}))
        for phrase in ('Selected waypoint: 2', 'name updated', 'coordinates updated',
                       'fresh measured XYZ captured', 'recording provenance discarded', 'Route revision: 3'):
            self.assertIn(phrase, out)

    def test_route_select_explicitly_discards_unapplied_edit_draft(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('route.select',data={})) as request:
            self.assertEqual(self.call('route','select','3','--discard-draft','--json')[0], 0)
        self.assertEqual(request.call_args.args[1:3], ('route.select', {
            'point':3, 'discard_draft':True}))
        help_text = self.call('route','select','--help')[1]
        self.assertIn('explicitly discard unapplied Edit waypoint fields', help_text)

    def test_scene_commands_dispatch_explicit_capture_options_and_reset(self):
        cases = [
            (('beacons','reset'), 'beacons.reset', {}),
            (('view','status'), 'view.status', {}),
            (('view','load','scene.json'), 'view.load', {'file':str(Path('scene.json').resolve())}),
            (('view','save','scene.json'), 'view.save', {
                'file':str(Path('scene.json').resolve()), 'overwrite':False,
                'bring_forward':False, 'nearby_units':False}),
            (('view','save','scene.json','--bring-forward','--nearby-units','--overwrite'), 'view.save', {
                'file':str(Path('scene.json').resolve()), 'overwrite':True,
                'bring_forward':True, 'nearby_units':True}),
        ]
        for argv,operation,payload in cases:
            with self.subTest(argv=argv), patch.object(protocol,'resolve_session',return_value={}), patch.object(
                    protocol,'request',return_value=cli.result(operation,data={})) as request:
                self.assertEqual(self.call(*argv,'--json')[0], 0)
                self.assertEqual(request.call_args.args[1:3], (operation,payload))

    def test_radar_reset_position_dispatches_without_new_settings(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('radar.reset-position',data={})) as request:
            self.assertEqual(self.call('radar','reset-position','--json')[0], 0)
        self.assertEqual(request.call_args.args[1:3], ('radar.reset-position', {}))

    def test_diagnostics_commands_dispatch_through_gui_owner(self):
        for verb in ('status','show','copy','open'):
            operation='diagnostics.'+verb
            with self.subTest(verb=verb), patch.object(protocol,'resolve_session',return_value={}), patch.object(
                    protocol,'request',return_value=cli.result(operation,data={})) as request:
                self.assertEqual(self.call('diagnostics',verb,'--session','running-helper','--json')[0], 0)
                self.assertEqual(request.call_args.args[1:3], (operation,{}))
                self.assertEqual(request.call_args.kwargs['timeout'], 10)

    def test_diagnostics_fall_back_to_saved_logs_without_launching_helper(self):
        status={'loggingAvailable':True,'logFile':'C:/logs/waypoints.log','directory':'C:/logs'}
        report='saved diagnostics\n'
        with patch.object(protocol,'discover_sessions',return_value=[]), patch(
                'scripts.waypoint_diagnostics.existing_status',return_value=status,create=True), patch(
                'scripts.waypoint_diagnostics.existing_report',return_value=report,create=True), patch.object(
                cli.subprocess,'Popen',side_effect=AssertionError('must not launch helper')):
            code,out,_=self.call('diagnostics','show')
        self.assertEqual(code,0)
        self.assertEqual(out,report)

        with patch.object(protocol,'discover_sessions',return_value=[]), patch(
                'scripts.waypoint_diagnostics.existing_status',return_value=status,create=True), patch(
                'scripts.waypoint_diagnostics.existing_report',return_value=report,create=True), patch.object(
                cli.subprocess,'run') as run:
            self.assertEqual(self.call('diagnostics','copy','--json')[0],0)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0],['clip.exe'])
        self.assertEqual(run.call_args.kwargs['input'],b'\xff\xfe'+report.encode('utf-16le'))
        self.assertFalse(run.call_args.kwargs['shell'])

    def test_offline_diagnostics_open_and_explicit_session_rules(self):
        status={'loggingAvailable':True,'logFile':'C:/logs/waypoints.log','directory':'C:/logs'}
        with patch.object(protocol,'discover_sessions',return_value=[]), patch(
                'scripts.waypoint_diagnostics.existing_status',return_value=status,create=True), patch.object(
                cli.Path,'is_dir',return_value=True), patch.object(cli.os,'startfile',create=True) as start:
            code,out,_=self.call('diagnostics','open','--json')
        self.assertEqual(code,0)
        start.assert_called_once_with(Path('C:/logs'))
        with patch.object(protocol,'resolve_session',side_effect=protocol.CliError(
                'session-unavailable','No matching helper',exit_code=3)), patch.object(
                protocol,'discover_sessions',side_effect=AssertionError('explicit session bypasses fallback')):
            code,out,_=self.call('diagnostics','show','--session','missing','--json')
        self.assertEqual(code,3)
        self.assertEqual(json.loads(out)['error']['code'],'session-unavailable')

    def test_library_usage_and_help_never_resolve_native_or_session(self):
        with patch.object(protocol, 'resolve_session', side_effect=AssertionError('session lookup')), patch.object(cli.subprocess, 'Popen', side_effect=AssertionError('process launch')):
            for argv in (("library", "load"), ("library", "show"), ("library", "save"),
                         ("library", "import"), ("library", "list", "--zone", "nearby"),
                         ("library", "list", "--file", "routes.json"),
                         ("zone", "refresh", "--execute")):
                with self.subTest(argv=argv):
                    self.assertEqual(self.call('--json', *argv)[0], 2)
            for argv in (("zone", "refresh"), ("route", "tag-zone"), ("library", "import")):
                code, out, _ = self.call(*argv, '--help')
                self.assertEqual(code, 0)
                self.assertIn('sends no game input', out)
            self.assertIn('actual world instance', self.call('zone', 'refresh', '--help')[1])

    def test_human_library_and_zone_are_candidate_labeled(self):
        context = {'zoneIdCandidate':'z0000000100000000', 'source':'native-candidate'}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('library.list', data={'routes':[{'id':'camp', 'name':'Camp', 'waypointCount':3,
                'measuredHeightCount':2, 'estimatedHeightCount':1, 'contextStatus':'matching', 'routeContext':context}]}))
            cli.emit(cli.result('zone.status', data={'context':context, 'currentAgeSeconds':.25, 'status':'fresh'}))
            cli.emit(cli.result('route.context', data={'routeContext':context, 'currentContext':context, 'comparison':'matching'}))
        for phrase in ('camp | Camp', '3 points', '2 measured', '1 estimated/unknown', '0.25s old',
                       'actual world instance unproven', 'Zone comparison: matching (candidate evidence only)'):
            self.assertIn(phrase, out.getvalue())

    def test_usage_is_one_json_on_stdout(self):
        for argv in (['radar','set','--op','70'], ['face','nan','--execute'],
                     ['route','select','0'], ['radar','set','--opacity','101'],
                     ['move','to','1','2'], ['route','add','--x','1'],
                     ['route','add','--current','--x','1','--z','2'],
                     ['route','update','1','--current','--x','1'],
                     ['route','update','1'], ['trail','save','x','--segment','0'],
                     ['--jsonl','status'], ['route','selct','1']):
            with self.subTest(argv=argv):
                code, out, err = self.call('--json', *argv)
                self.assertEqual(code, 2)
                self.assertFalse(json.loads(out)['ok'])
                self.assertEqual(err, '')
                self.assertEqual(len(out.splitlines()), 1)

    def test_dispatch_and_timeout_defaults(self):
        with patch.object(protocol,'resolve_session',return_value={'sessionId':'s'}), patch.object(protocol,'request',return_value=cli.result('face')) as request:
            code, out, _ = self.call('face','90','--execute','--json')
            self.assertEqual(code,0)
            self.assertTrue(json.loads(out)['ok'])
            self.assertEqual(request.call_args.kwargs['timeout'],150)
            self.assertEqual(request.call_args.args[1],'face')
            self.assertEqual(request.call_args.args[2]['bearing'],90)
            self.call('--timeout','7','status','--json')
            self.assertEqual(request.call_args.kwargs['timeout'],7)
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('view.save',data={})) as request:
            self.assertEqual(self.call('view','save','scene.json','--json')[0], 0)
            self.assertEqual(request.call_args.kwargs['timeout'], 120)

    def test_refusal_and_unavailable_are_not_success(self):
        with patch.object(protocol,'resolve_session',side_effect=protocol.CliError('session-unavailable','No app',exit_code=3)):
            code,out,_ = self.call('status','--json')
            self.assertEqual(code,3)
            self.assertEqual(json.loads(out)['error']['code'],'session-unavailable')
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(protocol,'request',return_value=cli.result('radar.show',ok=False,error={'code':'busy','exitCode':4})):
            self.assertEqual(self.call('radar','show','--json')[0],4)

    def test_movement_ctrl_c_stops_owned_request(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(protocol,'request',side_effect=[KeyboardInterrupt(),cli.result('stop',data={'releaseSucceeded':True})]) as request:
            code,out,_ = self.call('move','to','1','2','--execute','--json')
            self.assertEqual(code,130)
            self.assertEqual(json.loads(out)['status'],'cancelled')
            owned = request.call_args_list[0].kwargs['request_id']
            self.assertEqual(request.call_args_list[1].args[1],'stop')
            self.assertEqual(request.call_args_list[1].args[2]['requestId'],owned)

    def test_watch_is_explicit_jsonl_with_count(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(protocol,'request',return_value=cli.result('status')), patch.object(cli.time,'sleep'):
            code,out,_ = self.call('status','--watch','--jsonl','--count','2')
            self.assertEqual(code,0)
            self.assertEqual(len(out.splitlines()),2)
            self.assertTrue(all(json.loads(row)['ok'] for row in out.splitlines()))

    def test_radar_ranges_and_resume_cursor_contract(self):
        for argv in (("radar", "set", "--range", "3"), ("radar", "set", "--opacity", "19"),
                     ("beacons", "set", "--size", "0.25"),
                     ("playback", "resume", "--from", "1", "--execute"),
                     ("playback", "start", "--from", "1", "--execute"),
                     ("guide", "start", "--confirm-samples", "2")):
            self.assertEqual(self.call("--json", *argv)[0], 2)
        args = cli.build_parser().parse_args(["playback", "resume", "--execute"])
        self.assertIsNone(args.direction)

    def test_offline_receipts_include_native_and_run_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"waypoint-run-a.json").write_text('{"status":"complete"}')
            native = root/"waypoint-input-b.jsonl"
            native.write_text('{"releaseSucceeded":true}\n{"releaseSucceeded":false}\n')
            (root/"unrelated.json").write_text('{}')
            code, out, _ = self.call('receipt','list','--directory',directory,'--json')
            self.assertEqual(code,0)
            self.assertEqual(len(json.loads(out)['data']['files']),2)
            code, out, _ = self.call('receipt','show',str(native),'--json')
            self.assertEqual(code,0)
            self.assertEqual(len(json.loads(out)['data']),2)

    def test_app_open_reuses_helper_and_refuses_implicit_route_load(self):
        session = {'sessionId':'s', 'pid':123}
        state = cli.result('status',data={'target':{'processId':99},'route':{'path':'saved.json'}})
        with patch.object(protocol,'discover_sessions',return_value=[session]), patch.object(protocol,'request',side_effect=[state, cli.result('app.show')]) as request, patch.object(cli.subprocess,'Popen') as spawn:
            code,out,_ = self.call('app','open','--json')
            self.assertEqual(code,0)
            self.assertTrue(json.loads(out)['data']['reused'])
            self.assertEqual(request.call_args.args[1],'app.show')
            spawn.assert_not_called()
        with patch.object(protocol,'discover_sessions',return_value=[session]), patch.object(protocol,'request',return_value=state), patch.object(cli.subprocess,'Popen') as spawn:
            code,out,_ = self.call('app','open','--route','another.json','--json')
            self.assertEqual(code,4)
            self.assertEqual(json.loads(out)['error']['code'],'route-load-required')
            spawn.assert_not_called()

    def test_app_open_matches_launch_token_across_windows_redirector(self):
        from types import SimpleNamespace
        token = 'unique-launch-token'
        descriptor = {'sessionId':'new', 'pid':999, 'launchToken':token}
        child = SimpleNamespace(pid=123, poll=lambda:None)
        with patch.object(protocol,'discover_sessions',side_effect=[[],[descriptor]]), patch.object(cli.Path,'exists',return_value=True), patch.object(cli.uuid,'uuid4',return_value=SimpleNamespace(hex=token)), patch.object(cli.subprocess,'Popen',return_value=child) as spawn:
            code,out,_ = self.call('app','open','--json')
            self.assertEqual(code,0)
            self.assertEqual(json.loads(out)['data']['pid'],999)
            command=spawn.call_args.args[0]
            self.assertEqual(command[command.index('--launch-token')+1],token)

    def test_app_open_reuses_matching_route_file_key(self):
        session={'sessionId':'s','pid':123}
        with patch.object(protocol,'discover_sessions',return_value=[session]), patch.object(protocol,'request',side_effect=[cli.result('status',data={'route':{'file':'saved.json'}}),cli.result('app.show')]), patch.object(cli.subprocess,'Popen') as spawn:
            self.assertEqual(self.call('app','open','--route','saved.json','--json')[0],0)
            spawn.assert_not_called()

    def test_app_open_explicit_session_never_launches_on_pid_mismatch(self):
        session = {'sessionId':'s', 'pid':123}
        with patch.object(protocol,'discover_sessions',return_value=[session]), patch.object(protocol,'resolve_session',return_value=session), patch.object(protocol,'request',return_value=cli.result('status',data={'target':{'processId':99}})), patch.object(cli.subprocess,'Popen') as spawn:
            code,out,_ = self.call('app','open','--session','s','--pid','98','--json')
            self.assertEqual(code,3)
            self.assertEqual(json.loads(out)['error']['code'],'session-target-mismatch')
            spawn.assert_not_called()

    def test_expired_response_and_manual_y_are_explicit_failures(self):
        self.assertEqual(self.call('--json','route','add','--x','1','--z','2','--y','3')[0],2)
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(protocol,'request',return_value=cli.result('status',ok=False,error={'code':'expired'})):
            self.assertEqual(self.call('status','--json')[0],5)

    def test_offline_mixed_measured_estimated_and_unknown_receipts(self):
        from scripts.waypoint_measurements import measurement
        identity={'machine':'AMD-DESKTOP','gameBuildSha256':'a'*64,'unitKey':'player'}
        receipt=measurement({'x':1,'y':3,'z':2},identity,'native-player','2026-11-13T12:00:00+00:00')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mixed.json'
            for receipts,heights,measured in (([receipt,None],[3,None],1),([None,None],[None,None],0)):
                path.write_text(json.dumps({'waypoints':[['A',1,2],['B',3,4]],'heights':heights,'pointMeasurements':receipts}),encoding='utf-8')
                for operation in ('list','validate'):
                    code,out,_=self.call('route',operation,'--file',str(path),'--json')
                    self.assertEqual(code,0,out)
                    data=json.loads(out)['data']
                    self.assertEqual(data['measuredCount'],measured)
                    self.assertEqual(data['estimatedCount'],2-measured)
                    self.assertNotIn('projection',data)
            path.write_text(json.dumps({'waypoints':[['A',1,2]],'heights':[3],'pointMeasurements':[{'bad':'receipt'}]}),encoding='utf-8')
            for operation in ('list','validate'):
                code,out,_=self.call('route',operation,'--file',str(path),'--json')
                self.assertEqual(code,1)
                self.assertFalse(json.loads(out)['ok'])

    def test_help_matches_passive_and_view_effects(self):
        for command in (('radar','status'),('guide','status'),('trail','list')):
            self.assertIn('Effects: Read-only;',self.call(*command,'--help')[1])
        self.assertIn('Changes helper visibility',self.call('app','show','--help')[1])
        self.assertIn('owned shared reader',self.call('beacons','show','--help')[1])
        for command in (('radar','show'), ('guide','start'), ('trail','start')):
            help_text = self.call(*command, '--help')[1]
            self.assertIn('owned shared reader', help_text)
            self.assertIn('sends no game input', help_text)
        radar_reset = self.call('radar','reset-position','--help')[1]
        for phrase in ('saved manual radar position', 'retains range, opacity and enabled state'):
            self.assertIn(phrase, radar_reset)
        self.assertIn("configured value (0.6 at startup)", self.call('guide','start','--help')[1])
        guide_help = self.call('guide','start','--help')[1]
        for phrase in ('up to 4 seconds', 'refuses without applying', 'explicit retry'):
            self.assertIn(phrase, guide_help)
        close_help = self.call('app','close','--help')[1]
        self.assertIn('retained', close_help)
        self.assertIn('breadcrumb trail history', close_help)
        self.assertIn('JSON manifest',self.call('view','save','--help')[1])
        self.assertIn('.rrd',self.call('view','open-3d','--help')[1])
        playback_help = self.call('playback','status','--help')[1]
        self.assertIn('existing pose', playback_help)
        self.assertIn('rechecks live admission', playback_help)
        self.assertIn('Effects: Read-only;', playback_help)
        update_help = self.call('route','update','--help')[1]
        self.assertIn('freshly measured player XYZ', update_help)
        self.assertIn('may be combined with --name', update_help)
        self.assertIn('--x/--z', update_help)
        self.assertIn('sends no game input', update_help)
        reset_help = self.call('beacons','reset','--help')[1]
        self.assertIn('preserving target, selected guide and enabled state', reset_help)
        beacon_help = self.call('beacons','set','--help')[1]
        for phrase in ('restart the owned reader', 'refused during manual guide/trail use'):
            self.assertIn(phrase, beacon_help)
        view_help = self.call('view','save','--help')[1]
        for phrase in ('every route point must have measured XYZ evidence', 'default is', 'focus-neutral',
                       'no nearby-unit sample', 'Defaults: timeout 120 seconds',
                       'seconds to wait; default 120 for this command'):
            self.assertIn(phrase, view_help)
        load_help = self.call('view','load','--help')[1]
        self.assertIn('Load saved image and 3D asset references', load_help)
        self.assertIn('opens no viewer', load_help)
        self.assertIn('Effects: Read-only;', self.call('diagnostics','status','--help')[1])
        self.assertIn('Effects: Read-only;', self.call('diagnostics','show','--help')[1])
        copy_help=self.call('diagnostics','copy','--help')[1]
        self.assertIn('Windows clipboard', copy_help)
        self.assertIn('does not change RIFT', copy_help)
        open_help=self.call('diagnostics','open','--help')[1]
        self.assertIn('Windows Explorer', open_help)
        self.assertIn('does not change RIFT', open_help)
        for verb in ('status','show','copy','open'):
            self.assertIn('without a Waypoints window', self.call('diagnostics',verb,'--help')[1])

    def test_human_route_list_marks_selected_points(self):
        data={'points':[{'number':1,'name':'Start','x':1,'z':2},
                        {'number':2,'name':'Camp','x':3,'z':4}],
              'selected':[2], 'editDraft':{'pending':True,'point':2,'valid':False,'reason':'X is not finite'},
              'dirty':False, 'revision':7, 'file':'route.json'}
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('route.list',data=data))
        self.assertIn('Selected: 2', out.getvalue())
        self.assertIn(' *2. Camp', out.getvalue())
        self.assertIn('Edit draft: pending for point 2 | invalid | X is not finite', out.getvalue())
        self.assertIn('--discard-draft', out.getvalue())

    def test_human_playback_status_explains_each_admission(self):
        readiness = {
            'forward': {'ready': True, 'reason': 'At route start', 'direction': 'forward',
                        'nextIndex': 0, 'nextName': 'Camp', 'remainingDistance': 4.25},
            'reverse': {'ready': False, 'reason': 'Move 6.2 units to End', 'direction': 'reverse',
                        'nextIndex': 0, 'nextName': 'End', 'remainingDistance': None},
            'resume': {'ready': True, 'reason': 'On unfinished leg', 'direction': 'reverse',
                       'nextIndex': 2, 'nextName': 'Bridge', 'remainingDistance': 1.5},
        }
        data = {'active': False, 'progress': {'direction': 'reverse', 'nextIndex': 2},
                'checkpoint': 'progress.json', 'faceWaypoints': True, 'readiness': readiness}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('playback.status',data=data)):
            code,out,_ = self.call('playback','status')
        self.assertEqual(code, 0)
        for phrase in ('Replay: idle | face before each leg', 'Saved cursor: reverse | next point 3',
                       'Forward: ready | forward | point 1 (Camp) | 4.25 units remaining | At route start',
                       'Reverse: blocked | reverse | point 1 (End) | Move 6.2 units to End',
                       'Resume: ready | reverse | point 3 (Bridge) | 1.50 units remaining | On unfinished leg'):
            self.assertIn(phrase, out)

    def test_main_status_has_compact_playback_readiness(self):
        data={'host':'AMD-DESKTOP','target':{'processId':99},'app':{'busy':False,'visible':True},
              'route':{'count':2,'dirty':False},'pose':{},'radar':{},
              'playback':{'active':False,'readiness':{
                  'forward':{'ready':True},'reverse':{'ready':False},'resume':{'ready':False}}}}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('status',data=data)):
            code,out,_ = self.call('status')
        self.assertEqual(code, 0)
        self.assertIn('Replay: idle | F ready | R blocked | Resume blocked', out)

    def test_human_status_is_compact_and_distinguishes_observed_radar(self):
        data={'host':'AMD-DESKTOP','target':{'processId':99},'app':{'busy':False,'visible':True,'state':'Connected'},
              'route':{'count':7,'dirty':True,'file':'route.json'},
              'pose':{'status':'fresh','source':'owned-beacon-reader','ageSeconds':.15,'position':{'x':1,'y':2,'z':3},'bearing':90},
              'radar':{'enabled':True,'range':10,'opacity':85,'unlocked':False,'observed':None}}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(protocol,'request',return_value=cli.result('status',data=data,session='s')):
            code,out,_=self.call('status')
            self.assertEqual(code,0)
            for phrase in ('session s','AMD-DESKTOP','RIFT PID: 99','7 points','unsaved changes','owned-beacon-reader','0.15s old','Radar requested: on','Radar observed: unavailable'):
                self.assertIn(phrase,out)
            self.assertLess(len(out.splitlines()),12)
            _,machine,_=self.call('status','--json')
            self.assertEqual(json.loads(machine)['data'],data)

    def test_human_movement_keeps_receipt_and_radar_actual_values(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('playback.start',data={'operation':'play','state':'Complete','receipt':'run.json'}))
            cli.emit(cli.result('radar.set',data={'enabled':True,'range':10,'opacity':85,'observed':{'visible':True,'range':10,'opacity':.85,'unlocked':False}}))
        self.assertIn('Receipt: run.json',out.getvalue())
        self.assertIn('Radar observed: visible, range 10 units, opacity 85%',out.getvalue())

    def test_human_radar_explains_saved_but_unconfirmed_display(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('radar.show', status='configured', data={
                'enabled':True, 'range':10, 'opacity':85, 'unlocked':False,
                'observed':None, 'displayPending':True}))
        rendered=out.getvalue()
        self.assertIn('Radar observed: unavailable', rendered)
        self.assertIn('settings saved; visibility is unconfirmed', rendered)
        self.assertIn('check radar status', rendered)

    def test_human_explore_status_exposes_floor_and_trail_readiness(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('guide.status',data={
                'status':'active','direction':'forward','activeIndex':1,'activeName':'Upstairs',
                'distance':.4,'completedIndices':[0],'pointCount':3,'arrivalRadius':.6,
                'heightWarning':True,'heightSeparation':4.25}))
            cli.emit(cli.result('trail.list',data={
                'active':False,'discardedPointCount':12,'segments':[
                    {'number':1,'pointCount':8,'observedPathLength':3.125,'reason':'sample-gap',
                     'exportable':True,'waypointCount':3,'exportReason':None},
                    {'number':2,'pointCount':1,'observedPathLength':0.,'reason':'started',
                     'exportable':False,'waypointCount':None,
                     'exportReason':'Recording requires movement of at least 0.05 units'}]}))
        rendered=out.getvalue()
        for phrase in ('Confirmed points: 1/3', 'arrival radius 0.6 units',
                       'Floor warning: waypoint may be on another floor (+4.2 units)',
                       'Retention: 12 older samples discarded',
                       'Segment 1: 8 samples | 3.12 units | ready to save as 3 waypoints | split: sample-gap',
                       'Segment 2: 1 samples | 0.00 units | not ready to save: Recording requires movement'):
            self.assertIn(phrase, rendered)

    def test_scene_status_distinguishes_reader_visibility_and_capture_assets(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('beacons.status',data={
                'readerRunning':True,'closing':False,'size':1.0,'opacity':100,'labels':True,
                'target':False,'guide':False,'pose':{},
                'visibility':{'visible':False,'state':'withheld','reason':'RIFT is not foreground'}}))
            cli.emit(cli.result('view.status',data={
                'options':{'bringForward':False,'nearbyUnits':False},
                'readiness':{'ready':False,'reason':'5 route points lack measured XYZ evidence',
                             'measured':2,'total':7},
                'image':'scene.png','imageAvailable':True,'rerun':'scene.rrd','rerunAvailable':False,
                'nearbySample':None,'lastCaptureState':'complete'}))
        rendered=out.getvalue()
        for phrase in ('Beacon reader: running', 'Beacon visibility: hidden | withheld | RIFT is not foreground',
                       'Capture options: focus-neutral | nearby units off',
                       'Capture readiness: blocked | 2/7 measured points | 5 route points lack measured XYZ evidence',
                       'Last image: available | scene.png', '3D rerun: unavailable | scene.rrd',
                       'Last capture: complete'):
            self.assertIn(phrase, rendered)

    def test_diagnostics_human_output_and_main_status_are_concise(self):
        report='Joey D\'s Waypoints diagnostics\nTarget: AMD-DESKTOP\n'
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('diagnostics.show',data={'text':report,'logFile':'waypoints.log','directory':'logs'}))
        self.assertEqual(out.getvalue(), report)
        data={'host':'AMD-DESKTOP','target':{'processId':99},'app':{'busy':False,'visible':True},
              'route':{'count':0,'dirty':False},'pose':{},'radar':{},
              'diagnostics':{'loggingAvailable':True,'logFile':'C:/logs/waypoints.log'}}
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('status',data=data))
            cli.emit(cli.result('diagnostics.copy',data={'copied':True,'characters':52,'logFile':'waypoints.log'}))
            cli.emit(cli.result('diagnostics.open',data={'opened':True,'directory':'C:/logs'}))
        for phrase in ('Diagnostics: logging available | C:/logs/waypoints.log',
                       'Diagnostics copied: 52 characters | waypoints.log',
                       'Diagnostics directory opened: C:/logs'):
            self.assertIn(phrase, out.getvalue())

    def test_offline_manual_route_does_not_resolve_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'route.json'
            path.write_text(json.dumps({'waypoints':[['A',1,2],['B',3,4]]}),encoding='utf-8')
            with patch.object(protocol,'resolve_session',side_effect=AssertionError('live session lookup')):
                for operation in ('list','validate'):
                    code,out,_=self.call('route',operation,'--file',str(path),'--json')
                    self.assertEqual(code,0)
                    self.assertEqual(json.loads(out)['data']['points'][0]['number'],1)


if __name__ == '__main__':
    unittest.main()
