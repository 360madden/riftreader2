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
    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_no_args_and_help_alias(self):
        self.assertEqual(self.call()[0], 0)
        alias = self.call('help', 'radar', 'set')
        direct = self.call('radar', 'set', '--help')
        self.assertEqual(alias, direct)
        for phrase in ('Requires:', 'Effects:', 'Defaults:', 'Example:'):
            self.assertIn(phrase, direct[1])

    def test_all_leaf_help(self):
        for command in ('status doctor capabilities stop app.list app.open app.show app.hide app.close '
                        'route.list route.load route.save route.new route.add route.update route.remove '
                        'route.reorder route.select route.undo route.validate route.run radar.status radar.show '
                        'radar.hide radar.set radar.move radar.lock radar.unlock beacons.status beacons.show '
                        'beacons.hide beacons.set guide.status guide.start guide.stop trail.status trail.start '
                        'trail.stop trail.list trail.save trail.clear record.status record.start record.stop '
                        'record.cancel move.to face playback.start playback.resume playback.status '
                        'view.save view.open view.open-3d receipt.list receipt.show').split():
            with self.subTest(command=command):
                self.assertEqual(self.call(*command.split('.'), '--help')[0], 0)

    def test_common_flags_survive_any_level(self):
        parser = cli.build_parser()
        for argv in (['--session','a','radar','set','--opacity','70'],
                     ['radar','--session','a','set','--opacity','70'],
                     ['radar','set','--opacity','70','--session','a']):
            self.assertEqual(parser.parse_args(argv).session, 'a')

    def test_usage_is_one_json_on_stdout(self):
        for argv in (['radar','set','--op','70'], ['face','nan','--execute'],
                     ['route','select','0'], ['radar','set','--opacity','101'],
                     ['move','to','1','2'], ['route','add','--x','1'],
                     ['route','add','--current','--x','1','--z','2'],
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
        self.assertIn('JSON manifest',self.call('view','save','--help')[1])
        self.assertIn('.rrd',self.call('view','open-3d','--help')[1])

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
