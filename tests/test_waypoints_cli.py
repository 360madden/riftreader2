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
        self.assertIn(f"Joey D's Waypoints {cli.VERSION}", version[1])
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
                        'record.cancel move.to move.pick move.mode face playback.start playback.resume playback.status '
                        'view.status view.save view.load view.open view.open-3d receipt.list receipt.show '
                        'zone.status zone.refresh route.context route.tag-zone '
                        'preview.status preview.set preview.fit preview.project pose.status pose.set pose.refresh '
                        'diagnostics.status diagnostics.show diagnostics.events diagnostics.copy diagnostics.open '
                        'library.list library.save library.import library.load library.show library.select').split():
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
            (("library", "select", "camp"), "library.select", {"route_id":"camp"}),
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
            'point':3, 'clear':False, 'discard_draft':True}))
        help_text = self.call('route','select','--help')[1]
        self.assertIn('explicitly discard unapplied Edit waypoint fields', help_text)

    def test_route_select_clear_prepares_new_point_form_and_requires_exclusive_choice(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('route.select',data={'selected':[]})) as request:
            code,out,_ = self.call('route','select','--clear','--discard-draft')
        self.assertEqual(code, 0)
        self.assertEqual(request.call_args.args[1:3], ('route.select', {'clear':True,'discard_draft':True}))
        self.assertIn('Waypoint selection cleared; Add X/Z form is ready.', out)
        for args in (('route','select'), ('route','select','3','--clear')):
            with self.subTest(args=args), patch.object(protocol,'resolve_session') as resolve:
                self.assertEqual(self.call(*args)[0], 2)
                resolve.assert_not_called()

    def test_status_reports_current_tab_and_unapplied_edit_fields(self):
        data = {'app':{'tab':'edit','visible':True}, 'route':{'count':3,'dirty':False,
                'editDraft':{'pending':True,'point':2,'valid':False,'reason':'Enter finite X and Z'}}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('status', data=data))
        for phrase in ('tab edit', 'Edit draft: pending for point 2 | invalid | Enter finite X and Z',
                       'apply it or select with --discard-draft'):
            self.assertIn(phrase, out.getvalue())

    def test_scene_status_reports_failed_capture_and_missing_nearby_asset(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('view.status',data={'lastCaptureState':'failed',
                'lastCaptureError':'RIFT identity changed', 'nearbySample':'missing.json', 'nearbyAvailable':False}))
        for phrase in ('Last capture: failed', 'Capture error: RIFT identity changed',
                       'Nearby sample: unavailable | missing.json'):
            self.assertIn(phrase, out.getvalue())
        self.assertNotIn('Nearby sample: retained', out.getvalue())

    def test_preview_commands_are_small_display_only_controls(self):
        cases = [
            (("preview", "status"), "preview.status", {}),
            (("preview", "set", "--range", "5"), "preview.set", {"range": 5.0}),
            (("preview", "fit"), "preview.fit", {}),
            (("preview", "project", "--canvas-x", "220", "--canvas-y", "120"),
             "preview.project", {"canvas_x": 220.0, "canvas_y": 120.0}),
        ]
        for argv, operation, payload in cases:
            with self.subTest(argv=argv), patch.object(protocol, "resolve_session", return_value={}), patch.object(
                    protocol, "request", return_value=cli.result(operation, data={})) as request:
                self.assertEqual(self.call(*argv, "--json")[0], 0)
                self.assertEqual(request.call_args.args[1:3], (operation, payload))
        set_help = self.call("preview", "set", "--help")[1]
        self.assertIn("2, 5, 10, 20, 50, 100, 250, 500, 1000 or 1500", " ".join(set_help.split()))
        self.assertIn("reads no new pose", set_help)
        fit_help = self.call("preview", "fit", "--help")[1]
        self.assertIn("cached finite pose", fit_help)
        self.assertIn("capped at 1500 units", fit_help)
        project_help = self.call("preview", "project", "--help")[1]
        self.assertIn("flat world X/Z", project_help)
        self.assertIn("sends no game input", project_help)

    def test_map_pick_dispatch_and_human_projection(self):
        projection = {"x": 123.5, "z": 456.25, "canvasX": 220.0, "canvasY": 120.0,
                      "kind":"map-world-xz", "heightKnown":False, "terrainAvailable":False,
                      "inputSent":False, "qualification":"flat owned-map candidate"}
        with patch.object(protocol, "resolve_session", return_value={}), patch.object(
                protocol, "request", return_value=cli.result("move.pick", data={})) as request:
            self.assertEqual(self.call("move", "pick", "--canvas-x", "220", "--canvas-y", "120",
                                       "--execute", "--json")[0], 0)
        self.assertEqual(request.call_args.args[1:3], ("move.pick", {
            "canvas_x":220.0, "canvas_y":120.0, "execute":True}))
        self.assertEqual(cli.LONG_ROUTE_TIMEOUT, request.call_args.kwargs["timeout"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result("preview.project", data={"projection":projection}))
        for phrase in ("canvas X 220.0 / Y 120.0", "world X 123.5 / Z 456.25",
                       "Height: unknown", "no game input", "flat owned-map candidate"):
            self.assertIn(phrase, out.getvalue())

    def test_move_mode_is_input_free_configuration_with_short_timeout(self):
        for engine in ("continuous", "pulse"):
            with self.subTest(engine=engine), patch.object(
                    protocol, "resolve_session", return_value={}), patch.object(
                    protocol, "request", return_value=cli.result(
                        "move.mode", data={"movementEngine": engine})) as request:
                self.assertEqual(self.call("move", "mode", "--engine", engine, "--json")[0], 0)
                self.assertEqual(request.call_args.args[1:3],
                                 ("move.mode", {"engine": engine}))
                self.assertEqual(request.call_args.kwargs["timeout"], 10)
        help_text = self.call("move", "mode", "--help")[1]
        self.assertIn("continuous (default) or legacy pulse", " ".join(help_text.split()))
        self.assertIn("sends no game input", help_text)
        self.assertNotIn("--execute", help_text)

    def test_move_mode_requires_a_known_engine_before_session_dispatch(self):
        for argv in (("move", "mode"), ("move", "mode", "--engine", "steps")):
            with self.subTest(argv=argv), patch.object(protocol, "resolve_session") as resolve:
                self.assertEqual(self.call(*argv)[0], 2)
                resolve.assert_not_called()

    def test_move_mode_and_status_render_the_selected_engine(self):
        for command, data in (("move.mode", {"movementEngine": "continuous"}),
                              ("status", {"movementEngine": "pulse"})):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.emit(cli.result(command, data=data))
            self.assertIn("Movement engine: " + data["movementEngine"], out.getvalue())

    def test_map_projection_arguments_and_execute_are_required(self):
        for argv in (("preview","project","--canvas-x","1"),
                     ("preview","project","--canvas-x","nan","--canvas-y","2"),
                     ("move","pick","--canvas-x","1","--canvas-y","2")):
            with self.subTest(argv=argv), patch.object(protocol,"resolve_session") as resolve:
                self.assertEqual(self.call(*argv)[0], 2)
                resolve.assert_not_called()

    def test_preview_range_is_validated_before_dispatch(self):
        with patch.object(protocol, "resolve_session") as resolve:
            code, _, error = self.call("preview", "set", "--range", "7")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", error)
        resolve.assert_not_called()

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

        reply = cli.result('diagnostics.events', data={'entries':[]})
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=reply) as request:
            self.assertEqual(self.call('diagnostics','events','--session','running-helper',
                                       '--level','warning','--limit','25','--search','reader','--json')[0],0)
        self.assertEqual(request.call_args.args[1:3], ('diagnostics.events', {
            'level':'warning', 'limit':25, 'search':'reader'}))

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

    def test_diagnostics_events_offline_fallback_and_validation(self):
        events={'entries':[{'timestamp':'2026-11-13T12:00:00Z','level':'error','message':'Reader failed',
                            'exceptionType':'RuntimeError','requestId':'req-7','traceback':'full trace'}],
                'shownCount':1,'matchedCount':1,'offline':True,'logFile':'C:/logs/waypoints.jsonl'}
        with patch.object(protocol,'discover_sessions',return_value=[]), patch(
                'scripts.waypoint_diagnostics.existing_events',return_value=events,create=True) as existing, patch.object(
                cli.subprocess,'Popen',side_effect=AssertionError('must not launch helper')):
            code,out,_=self.call('diagnostics','events','--level','warning','--limit','25','--search','reader','--json')
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out)['data']['entries'][0]['traceback'],'full trace')
        existing.assert_called_once_with(cli.ROOT,limit=25,level='warning',search='reader')
        for argv in (('diagnostics','events','--level','info'),
                     ('diagnostics','events','--limit','0'),
                     ('diagnostics','events','--limit','201'),
                     ('diagnostics','events','--search','x'*201)):
            with self.subTest(argv=argv):
                self.assertEqual(self.call('--json',*argv)[0],2)

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

    def test_library_detail_and_filter_output(self):
        row = {'id':'camp', 'name':'Camp route', 'waypointCount':4, 'measuredHeightCount':1,
               'estimatedHeightCount':3, 'contextStatus':'mismatch', 'path':'C:/routes/camp.json',
               'modifiedAtUtc':'2026-11-13T12:00:00Z', 'planarDistance':12.5,
               'routeContext':{'zoneName':'Camp zone', 'zoneIdCandidate':'z0000000100000000'}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('library.list', data={'routes':[], 'shownCount':0, 'totalCount':2,
                'filter':'matching', 'search':'Camp', 'selectedId':'camp'}))
            cli.emit(cli.result('library.select', data={'row':row}))
            cli.emit(cli.result('library.show', data={'row':{'id':'broken', 'error':'invalid-route', 'path':'broken.json'}}))
        text = out.getvalue()
        for phrase in ('0 of 2 routes', "Filters: zone matching | search 'Camp'", 'Selected: camp',
                       'No library routes match', 'Library route: camp | Camp route | 4 points',
                       'Camp zone [z0000000100000000]', 'comparison mismatch',
                       'File: C:/routes/camp.json', '1 measured, 3 estimated/unknown',
                       'File modified: 2026-11-13T12:00:00Z', '12.50 world units', 'Unavailable: invalid-route'):
            self.assertIn(phrase, text)
        self.assertIn('saved zone context', self.call('library','list','--help')[1])
        self.assertIn('without replacing the loaded route', self.call('library','select','--help')[1])
        self.assertEqual(self.call('--json','library','select')[0],2)

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

    def test_long_route_commands_get_full_trip_deadline_without_slowing_stop(self):
        expected = cli.MAX_TRIP_SECONDS + 30
        self.assertEqual(expected, cli.LONG_ROUTE_TIMEOUT)
        for argv, operation in ((('move','to','500','0','--execute'), 'move.to'),
                                (('move','pick','--canvas-x','220','--canvas-y','120','--execute'), 'move.pick'),
                                (('route','run','--execute'), 'route.run'),
                                (('playback','start','--execute'), 'playback.start'),
                                (('playback','resume','--execute'), 'playback.resume')):
            with self.subTest(operation=operation), patch.object(
                    protocol, 'resolve_session', return_value={}), patch.object(
                    protocol, 'request', return_value=cli.result(operation)) as request:
                self.assertEqual(self.call(*argv, '--json')[0], 0)
                self.assertEqual(request.call_args.kwargs['timeout'], expected)
        with patch.object(protocol, 'resolve_session', return_value={}), patch.object(
                protocol, 'request', return_value=cli.result('stop')) as request:
            self.assertEqual(self.call('stop', '--json')[0], 0)
            self.assertEqual(request.call_args.kwargs['timeout'], 10)

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
        events_help=self.call('diagnostics','events','--help')[1]
        for phrase in ('structured log events', 'minimum severity', 'warning (includes errors)',
                       '1-200', 'case-insensitive', 'Effects: Read-only;',
                       'uses saved logs when no helper is running', 'select --session'):
            self.assertIn(phrase, events_help)
        copy_help=self.call('diagnostics','copy','--help')[1]
        self.assertIn('Windows clipboard', copy_help)
        self.assertIn('does not change RIFT', copy_help)
        open_help=self.call('diagnostics','open','--help')[1]
        self.assertIn('Windows Explorer', open_help)
        self.assertIn('does not change RIFT', open_help)
        for verb in ('status','show','events','copy','open'):
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

    def test_human_preview_reports_pose_age_offscreen_points_and_fit_cap(self):
        preview = {
            'radius': 20, 'routeCount': 4, 'selected': [3], 'visibleCount': 2,
            'offscreenCount': 2, 'offscreenPoints': [
                {'number': 3, 'name': 'Far camp'}, {'number': 4, 'name': 'Cliff'}],
            'poseAvailable': True, 'poseStatus': 'cached', 'poseAgeSeconds': 1.25,
            'fitAvailable': True, 'fitLimited': True, 'requiredRadius': 33.4,
            'terrainAvailable': False,
            'qualification': 'Local preview only; terrain and clearance are not shown.',
        }
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('preview.status', data=preview))
        rendered = out.getvalue()
        for phrase in ('Local preview: 20 units | 2/4 points visible | 2 off-screen',
                       'Preview pose: cached | 1.25s old | Fit available',
                       'Fit limited: preview is capped at 1500 units; route requires about 33.4 units',
                       'Off-screen points: 3 (Far camp), 4 (Cliff)',
                       'terrain and clearance are not shown'):
            self.assertIn(phrase, rendered)

    def test_route_list_and_status_render_nested_preview_summary(self):
        preview = {'radius': 10, 'routeCount': 2, 'visibleCount': 2, 'offscreenCount': 0,
                   'poseAvailable': False, 'poseStatus': 'unavailable', 'fitAvailable': False}
        for command, data in (
                ('route.list', {'points': [], 'preview': preview}),
                ('status', {'route': {}, 'preview': preview})):
            with self.subTest(command=command):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    cli.emit(cli.result(command, data=data))
                self.assertIn('Local preview: 10 units | 2/2 points visible | 0 off-screen', out.getvalue())
                self.assertIn('Preview pose: unavailable | Fit unavailable', out.getvalue())

    def test_human_playback_status_explains_each_admission(self):
        readiness = {
            'forward': {'ready': True, 'reason': 'At route start', 'direction': 'forward',
                        'nextIndex': 0, 'nextPointNumber':1, 'nextName': 'Camp', 'remainingDistance': 4.25},
            'reverse': {'ready': False, 'reason': 'Move 6.2 units to End', 'direction': 'reverse',
                        'nextIndex': 0, 'nextPointNumber':5, 'nextName': 'End', 'remainingDistance': None},
            'resume': {'ready': True, 'reason': 'On unfinished leg', 'direction': 'reverse',
                       'nextIndex': 2, 'nextPointNumber':3, 'nextName': 'Bridge', 'remainingDistance': 1.5},
        }
        data = {'active': False, 'progress': {'direction': 'reverse', 'nextIndex': 2},
                'checkpoint': 'progress.json', 'faceWaypoints': True, 'readiness': readiness}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('playback.status',data=data)):
            code,out,_ = self.call('playback','status')
        self.assertEqual(code, 0)
        for phrase in ('Replay: idle | face before each leg', 'Saved progress: ready | reverse | point 3 (Bridge)',
                       'Forward: ready | forward | point 1 (Camp) | 4.25 units remaining | At route start',
                       'Reverse: blocked | reverse | point 5 (End) | Move 6.2 units to End',
                       'Resume: ready | reverse | point 3 (Bridge) | 1.50 units remaining | On unfinished leg'):
            self.assertIn(phrase, out)

    def test_playback_complete_cursor_uses_validated_saved_progress_and_no_phantom_point(self):
        completed = {'ready':False,'direction':'reverse','nextIndex':4,'nextPointNumber':None,
                     'nextName':None,'pointCount':4,'completedCount':4,'complete':True,
                     'startPointNumber':4,'startName':'End','remainingDistance':0.,'reason':'route already complete'}
        data = {'active':False,'progress':{'direction':'forward','nextIndex':0},
                'readiness':{'resume':completed}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.human_playback(data)
            cli.human_playback(data,compact=True)
        rendered = out.getvalue()
        self.assertIn('Saved progress: complete | reverse | route complete | start point 4 (End) | 4/4 points confirmed', rendered)
        self.assertIn('Resume: complete | reverse | route complete', rendered)
        self.assertIn('Replay: idle | Resume complete', rendered)
        self.assertNotIn('point 5', rendered)
        self.assertNotIn('Saved cursor: forward', rendered)

    def test_resume_default_does_not_send_direction_and_help_explains_checkpoint_behavior(self):
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('playback.resume',data={})) as request:
            self.assertEqual(self.call('playback','resume','--execute','--json')[0], 0)
        self.assertNotIn('direction', request.call_args.args[2])
        resume_help = ' '.join(self.call('playback','resume','--help')[1].split())
        self.assertIn('saved checkpoint direction', resume_help)
        self.assertIn('explicit value must match it', resume_help)
        start_help = ' '.join(self.call('playback','start','--help')[1].split())
        self.assertIn('replaces saved progress only after fresh admission', start_help)
        self.assertIn("select the helper's checkpoint path", start_help)

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

    def test_human_pose_labels_cached_samples_without_presenting_stale_position_as_current(self):
        pose = {'status':'unavailable', 'source':'existing-idle-reader', 'sampleStatus':'cached',
                'liveEnabled':False, 'updating':False,
                'ageSeconds':3.5, 'sampledAtUtc':'2026-11-13T12:00:00Z',
                'position':{'x':101,'y':202,'z':303}, 'bearing':45,
                'reason':'Cached sample expired', 'qualification':'Cached GUI sample; unavailable for control.'}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.human_pose(pose)
        rendered = out.getvalue()
        for phrase in ('Pose: unavailable | existing-idle-reader | 3.50s old',
                       'Live pose: off | not updating | sample cached',
                       'Pose observed: 2026-11-13T12:00:00Z',
                       'Pose reason: Cached sample expired', 'unavailable for control'):
            self.assertIn(phrase, rendered)
        self.assertNotIn('Position:', rendered)

    def test_human_pose_reports_observation_and_qualification_for_fresh_reader(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.human_pose({'status':'fresh', 'source':'owned-beacon-reader', 'ageSeconds':.25,
                            'sampledAtUtc':'2026-11-13T12:00:00Z',
                            'position':{'x':1,'y':2,'z':3}, 'bearing':90,
                            'qualification':'Native candidate pose'})
        for phrase in ('0.25s old', 'Pose observed: 2026-11-13T12:00:00Z',
                       'Position: X 1 / Y 2 / Z 3 | facing 90 degrees',
                       'Pose qualification: Native candidate pose'):
            self.assertIn(phrase, out.getvalue())

    def test_pose_commands_dispatch_to_existing_helper_without_input_authority(self):
        data = {'status':'unavailable', 'sampleStatus':'cached', 'liveEnabled':False,
                'updating':False, 'source':'existing-idle-reader', 'ageSeconds':4.5}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('pose.set',data=data)) as request:
            code, out, _ = self.call('pose','set','--live','off')
        self.assertEqual(code, 0)
        self.assertEqual(request.call_args.args[1:3], ('pose.set', {'live':'off'}))
        self.assertIn('Live pose: off | not updating | sample cached', out)
        self.assertEqual(self.call('pose','set')[0], 2)
        help_text = self.call('pose','set','--help')[1]
        self.assertIn('sends no game input', help_text)
        self.assertIn('pose set --live on', help_text)
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('pose.status',data=data)) as request:
            code, out, _ = self.call('pose','status','--json')
        self.assertEqual(code, 0)
        self.assertEqual(request.call_args.args[1:3], ('pose.status', {}))
        self.assertEqual(json.loads(out)['data'], data)

    def test_stop_and_status_keep_release_and_stationary_evidence_separate(self):
        controls = {'stopLatched':True, 'ownedActionActive':False, 'f8':'active',
                    'ownedActionEnded':True, 'keyReleaseEvidence':'see-pulse-receipts',
                    'stationaryEvidence':'fail', 'result':{'receipt':'run.json'},
                    'qualification':'Owned cancellation only; arbitrary autorun unproven.'}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('stop', data=controls))
        for phrase in ('STOP: latched | owned action idle | F8 active',
                       'Key release evidence: see-pulse-receipts | stationary evidence: fail',
                       'Owned action ended: yes', 'Receipt: run.json', 'arbitrary autorun unproven'):
            self.assertIn(phrase, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('status', data={'controls':controls}))
        self.assertIn('STOP: latched | owned action idle | F8 active', out.getvalue())
        self.assertIn('stationary evidence: fail', out.getvalue())

    def test_pose_refresh_dispatches_one_explicit_read_and_renders_pose(self):
        data = {'status':'fresh', 'sampleStatus':'fresh', 'liveEnabled':True,
                'updating':False, 'source':'existing-idle-reader', 'ageSeconds':.1,
                'position':{'x':1,'y':2,'z':3}, 'bearing':90}
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',return_value=cli.result('pose.refresh',data=data)) as request:
            code,out,_ = self.call('pose','refresh')
        self.assertEqual(code, 0)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1:3], ('pose.refresh', {}))
        self.assertIn('Position: X 1 / Y 2 / Z 3 | facing 90 degrees', out)
        help_text = self.call('pose','refresh','--help')[1]
        self.assertIn('one fresh read', help_text)
        self.assertIn('sends no game input', help_text)

    def test_stop_without_evidence_and_cancelled_movement_remain_honest(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('stop', data={'stopLatched':True,'ownedActionEnded':True}))
        self.assertIn('Key release evidence: not-measured | stationary evidence: not-measured', out.getvalue())
        stopped = cli.result('stop',data={'stopLatched':True,'ownedActionActive':False,
                                       'keyReleaseEvidence':'not-measured','stationaryEvidence':'unavailable'})
        with patch.object(protocol,'resolve_session',return_value={}), patch.object(
                protocol,'request',side_effect=[KeyboardInterrupt(),stopped]):
            code,out,_ = self.call('move','to','1','2','--execute')
        self.assertEqual(code, 130)
        self.assertIn('STOP response: completed', out)
        self.assertIn('Key release evidence: not-measured | stationary evidence: unavailable', out)

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
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('diagnostics.status',data={
                'available':False,'offline':True,'error':'disk is read-only',
                'logFile':'C:/logs/waypoints.log'}))
        for phrase in ('Diagnostics logging: unavailable | saved/offline logs',
                       'Logging error: disk is read-only', 'Log file: C:/logs/waypoints.log'):
            self.assertIn(phrase,out.getvalue())

    def test_diagnostics_events_human_output_is_concise_and_points_to_full_trace(self):
        data={'entries':[{'timestamp':'2026-11-13T12:00:00Z','level':'warning','message':'Reader delayed',
                          'status':'withheld','operation':'beacons','reason':'RIFT is hidden','persisted':False},
                         {'timestamp':'2026-11-13T12:00:01Z','level':'error','message':'Reader failed\nretrying',
                          'command':'beacons.show','code':'reader-failed','exceptionType':'RuntimeError',
                          'exceptionMessage':'reader pipe closed','requestId':'req-7','traceback':'full trace'}],
              'shownCount':2,'matchedCount':4,'offline':True,'logFile':'C:/logs/waypoints.jsonl'}
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.emit(cli.result('diagnostics.events',data=data))
        rendered=out.getvalue()
        for phrase in ('2 shown / 4 matched', 'saved log', 'WARNING', 'Reader delayed', 'ERROR',
                       'status withheld', 'operation beacons', 'reason RIFT is hidden', 'memory only',
                       'Reader failed retrying', 'command beacons.show', 'code reader-failed',
                       'exception RuntimeError', 'error reader pipe closed', 'request req-7',
                       'Tracebacks are retained in --json output', 'C:/logs/waypoints.jsonl'):
            self.assertIn(phrase,rendered)
        self.assertNotIn('full trace',rendered)

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
