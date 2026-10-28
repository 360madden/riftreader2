"""Offline checks for repeatable XYZ capture and the one reviewed pulse."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from scripts import run_xyz_workflow as workflow


class WorkflowTests(unittest.TestCase):
    def bound_status(self):
        from tests.test_nav_control_watchdog import VM, TARGET
        host = dict(connected=True, vmIdentity=dict(VM), instanceId='guest-one',
                    machineName=TARGET['machineName'],
                    consoleReservation=dict(held=True, faulted=False),
                    coordination=dict(state='ready'))
        guest = dict(instanceId='guest-one', target=dict(TARGET), armed=False,
                     busy=False, desktopInputsDown=[], recoveryRequired=False)
        host['coordination']['supervisor'] = dict(
            epoch=workflow.resource_epoch(workflow.bind_identity(host, guest)))
        guard = workflow.HostGuard.__new__(workflow.HostGuard)
        guard.check = MagicMock()
        guard.client = MagicMock()
        guard.client.request.return_value = dict(host=host, guest=guest)
        guard.plan = dict(vmIdentity=dict(VM))
        guard.profile = dict(executableSha256=TARGET['executableSha256'])
        guard.target = None
        return guard, host, guest

    def test_ready_controller_must_bind_current_game_epoch(self):
        guard, host, guest = self.bound_status()
        guest['target']['processStartUtcTicks'] += 1
        guest['target']['processId'] += 1
        with self.assertRaisesRegex(ValueError, 'previous game/session'):
            guard.status()
        self.assertIsNone(guard.target)
        host['coordination']['supervisor']['epoch'] = workflow.resource_epoch(
            workflow.bind_identity(host, guest))
        self.assertEqual(guest, guard.status()['guest'])

    def test_missing_supervisor_binding_is_unavailable(self):
        guard, host, _ = self.bound_status()
        del host['coordination']['supervisor']
        with self.assertRaisesRegex(ValueError, 'previous game/session'):
            guard.status()

    def test_same_epoch_foreground_loss_does_not_change_identity_binding(self):
        guard, _, guest = self.bound_status()
        guest['target']['isForeground'] = False
        self.assertEqual(guest, guard.status()['guest'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, payload=None, records=None):
        payload = payload or {'status.json': b'{"completed":true}'}
        if records is None:
            records = [{'path': k, 'byteLength': len(v), 'sha256': workflow.digest(v)} for k, v in payload.items()]
        archive = self.root/'trial.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name, data in payload.items(): z.writestr(name,data)
            z.writestr('files.json',json.dumps(records))
        claim = dict(phase='baseline', byteLength=archive.stat().st_size, sha256=workflow.digest(archive.read_bytes()))
        return archive, claim

    def test_verified_archive_preserves_bytes(self):
        archive,claim=self.archive({'lua/nested.json':b'{"a":1}'})
        out=self.root/'out'
        self.assertEqual(2,workflow.unpack_phase(archive,claim,out,'baseline'))
        self.assertEqual(b'{"a":1}',(out/'lua/nested.json').read_bytes())
        with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,out,'baseline')

    def test_rejects_changed_archive_before_extract(self):
        archive,claim=self.archive();archive.write_bytes(archive.read_bytes()+b'changed')
        with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,self.root/'out','baseline')
        self.assertFalse((self.root/'out').exists())

    def test_rejects_unsafe_and_alias_names(self):
        for name in ('../escape','/absolute','C:/drive','A/./b','A//b','nul.json','a:stream','a./b'):
            with self.subTest(name=name):
                archive,claim=self.archive({name:b'not trusted'})
                with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,self.root/'out','baseline')
                self.assertFalse((self.root/'out').exists())

    def test_rejects_case_collision(self):
        archive,claim=self.archive({'A.json':b'1','a.json':b'2'})
        with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,self.root/'out','baseline')

    def test_rejects_manifest_mismatch_before_extract(self):
        archive,claim=self.archive(records=[dict(path='status.json',byteLength=18,sha256='A'*64)])
        with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,self.root/'out','baseline')
        self.assertFalse((self.root/'out').exists())

    def test_rejects_undeclared_member(self):
        archive,claim=self.archive({'status.json':b'{}','extra.txt':b'1'},records=[dict(path='status.json',byteLength=2,sha256=workflow.digest(b'{}'))])
        with self.assertRaises(ValueError): workflow.unpack_phase(archive,claim,self.root/'out','baseline')

    def test_phase_uses_dynamic_epoch_and_inert_encoded_paths(self):
        cfg={'guestDirectory':r"C:\Lab\O'Brien",'readerSha256':'A'*64}
        target=dict(processId=333,processStartUtcTicks=444,executableSha256='B'*64)
        script=workflow.phase_script(cfg,'C'*64,target,r'C:\RIFT_TRANSFER\XYZ\test','baseline')
        encoded=script.split("FromBase64String('",1)[1].split("'",1)[0]
        settings=json.loads(base64.b64decode(encoded))
        self.assertEqual(target,settings['target'])
        self.assertEqual(cfg['guestDirectory'],settings['guestDirectory'])
        self.assertNotIn("O'Brien",script)
        self.assertNotIn('639285359295548343',script)
        self.assertEqual(target,json.loads(settings['pointerRequest'])['target'])
        other=workflow.phase_script(cfg,'C'*64,target,r'C:\RIFT_TRANSFER\XYZ\test','after')
        encoded=other.split("FromBase64String('",1)[1].split("'",1)[0]
        self.assertEqual(settings['pointerRequest'],json.loads(base64.b64decode(encoded))['pointerRequest'])

    def test_staged_phase_invokes_hash_check_and_short_file_command(self):
        script = self.root / 'baseline.ps1'
        script.write_text("Write-Output 'phase'\n", encoding='utf-8-sig')
        guest = MagicMock()
        with patch.object(workflow.uuid, 'uuid4', return_value=SimpleNamespace(hex='a' * 32)):
            remote = workflow.launch_phase_script(
                guest, script, r"C:\Lab\O'Brien", 'baseline', timeout=91)
        first, second = guest.run.call_args_list
        self.assertEqual('copyFileFromHostToGuest', first.args[0])
        self.assertEqual(str(script.resolve()), first.args[1])
        self.assertEqual(remote, first.args[2])
        check = guest.powershell.call_args.args[0]
        self.assertNotIn("O'Brien", check)
        self.assertTrue(remote.startswith(r'C:\Users\Public\Documents\RR2XYZ-baseline-'))
        self.assertNotIn(r"C:\Lab", remote)
        self.assertIn(workflow.digest(script.read_bytes()), check)
        self.assertEqual('runProgramInGuest', second.args[0])
        self.assertEqual(workflow.POWERSHELL, second.args[1])
        self.assertEqual('-File', second.args[-2])
        self.assertEqual(remote, second.args[-1])
        self.assertEqual(91, second.kwargs['timeout'])

    def test_staged_phase_hash_check_failure_prevents_execution(self):
        script = self.root / 'baseline.ps1'
        script.write_text("Write-Output 'phase'\n", encoding='utf-8-sig')
        guest = MagicMock()
        guest.powershell.side_effect = workflow.SessionError('guest-script-hash-mismatch')
        with self.assertRaisesRegex(workflow.SessionError, 'guest-script-hash-mismatch'):
            workflow.launch_phase_script(guest, script, r'C:\Lab', 'baseline')
        self.assertEqual(1, guest.run.call_count)
        self.assertEqual('copyFileFromHostToGuest', guest.run.call_args.args[0])

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell 5.1 compatibility fixture')
    def test_guest_packaging_fragment_runs_in_windows_powershell(self):
        phase = self.root/'baseline'
        phase.mkdir()
        (phase/'status.json').write_text('{"completed":true}')
        (phase/'lua').mkdir()
        (phase/'lua/frame.json').write_text('{"frame":1}')
        source=(workflow.ROOT/'scripts/xyz_capture.ps1').read_text()
        function=source[source.index('function Assert-PlainPath'):source.index('Assert-PlainPath $root')]
        fragment=source[source.index('$files = @'):]
        root=str(self.root).replace("'","''")
        script=("$ErrorActionPreference='Stop'; $root='"+root+"'; $out=Join-Path $root 'baseline'; "
                "$settings=[pscustomobject]@{phase='baseline'}; $status=@{completed=$true}; "
                "$utf8=New-Object System.Text.UTF8Encoding($false);\n"+function+'\n'+fragment)
        path=self.root/'package.ps1';path.write_text(script,encoding='utf-8')
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        env=dict(os.environ, PSModulePath=str(powershell.parent/'Modules'))
        result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',encoded],
                              capture_output=True,text=True,timeout=30,env=env)
        self.assertEqual(0,result.returncode,result.stderr)
        claim=workflow.load(self.root/'baseline.receipt.json')
        self.assertEqual(3,workflow.unpack_phase(self.root/'baseline.zip',claim,self.root/'unpacked','baseline'))

    def test_preview_never_opens_guest(self):
        cfg={k:str(self.root/k) for k in ('hostPlan','hostProcess','vmrun','profile')}
        for key in ('hostPlan','hostProcess','vmrun'): Path(cfg[key]).write_text('{}')
        Path(cfg['profile']).write_bytes((workflow.ROOT/'config/position-candidate-profile.json').read_bytes())
        cfg.update(schemaVersion=1,guestDirectory=r'C:\RIFT_TRANSFER\reader',readerSha256='A'*64)
        path=self.root/'config.json';path.write_text(json.dumps(cfg))
        with patch.object(workflow,'HostGuard',side_effect=AssertionError('No live access')), contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(0,workflow.main(['--config',str(path)]))
        self.assertIn('configuration-valid-no-live-access',stdout.getvalue())

    def pulse_fixture(self):
        guard=MagicMock()
        guard.plan={'database':'queue','resource':'vm:test','configPath':'private.json'}
        guard.status.return_value={'guest':{'target':{'isForeground':True}}}
        q=MagicMock()
        q.status.return_value={'resources':[{'name':'vm:test','blocked':False,'holder':None,'epoch':'epoch'}],'requests':[]}
        q.dispatch.return_value={'request_id':'test','token':'sensitive'}
        q.finish.return_value={'state':'finished'}
        client=MagicMock();client.request.return_value={'stopped':True}
        return guard,q,client

    def test_reviewer_decline_stops_and_finishes_without_input(self):
        guard,q,client=self.pulse_fixture()
        with patch.object(workflow,'AccessQueue',return_value=q), patch.object(workflow.HostConfig,'load'), \
             patch.object(workflow,'ControlClient',return_value=client), patch.object(workflow,'_capture',return_value={'captureId':'id'}), \
             patch.object(workflow,'_arm') as arm, patch.object(workflow,'_action') as action:
            with self.assertRaisesRegex(ValueError,'declined'):
                workflow.pulse(guard,self.root,'test',reviewer=lambda _: (_ for _ in ()).throw(ValueError('declined')))
        arm.assert_not_called();action.assert_not_called()
        client.request.assert_called_once_with('/api/stop',method='POST',payload={})
        self.assertEqual('failed',q.finish.call_args.args[2])

    def test_failed_release_is_not_a_success_or_retried(self):
        guard,q,client=self.pulse_fixture()
        result={'result':{'result':{'deliverySucceeded':True,'releaseSucceeded':False,'targetLost':False,'stateUncertain':True,'cancelled':False}}}
        with patch.object(workflow,'AccessQueue',return_value=q), patch.object(workflow.HostConfig,'load'), \
             patch.object(workflow,'ControlClient',return_value=client), patch.object(workflow,'_capture',return_value={'captureId':'id'}), \
             patch.object(workflow,'_arm'), patch.object(workflow,'_action',return_value=result) as action:
            with self.assertRaisesRegex(ValueError,'release failed'):
                workflow.pulse(guard,self.root,'test',reviewer=lambda _:'reviewed clear ground')
        self.assertEqual(1,action.call_count)
        self.assertEqual('failed',q.finish.call_args.args[2])
        client.request.assert_called_once_with('/api/stop',method='POST',payload={})

    def test_success_is_one_100ms_pulse_then_stop_and_finish(self):
        guard,q,client=self.pulse_fixture()
        result={'result':{'result':{'deliverySucceeded':True,'releaseSucceeded':True,'targetLost':False,'stateUncertain':False,'cancelled':False}}}
        with patch.object(workflow,'AccessQueue',return_value=q), patch.object(workflow.HostConfig,'load'), \
             patch.object(workflow,'ControlClient',return_value=client), patch.object(workflow,'_capture',return_value={'captureId':'id'}), \
             patch.object(workflow,'_arm'), patch.object(workflow,'_action',return_value=result) as action:
            workflow.pulse(guard,self.root,'test',reviewer=lambda _:'reviewed clear ground')
        self.assertEqual(1,action.call_count)
        self.assertEqual(100,action.call_args.args[1].hold_ms)
        self.assertEqual('w',action.call_args.args[1].keys)
        self.assertEqual('succeeded',q.finish.call_args.args[2])
        client.request.assert_called_once_with('/api/stop',method='POST',payload={})

    def test_export_excludes_private_arm_and_reopens_exactly(self):
        workflow.save(self.root/'summary.json',{'status':'candidate-motion-consistent'})
        workflow.save(self.root/'motion-arm.private.json',{'armToken':'must-not-export'})
        workflow.export(self.root)
        with zipfile.ZipFile(self.root/'evidence.zip') as z:
            self.assertNotIn('motion-arm.private.json',z.namelist())
            self.assertEqual({'summary.json','manifest.json'},set(z.namelist()))
        self.assertTrue(workflow.load(self.root/'export-receipt.json')['verified'])

    def test_export_refuses_unredacted_token(self):
        workflow.save(self.root/'accidental.json',{'armToken':'must-not-export'})
        with self.assertRaises(ValueError): workflow.export(self.root)
        self.assertFalse((self.root/'evidence.zip').exists())


if __name__=='__main__':
    unittest.main()
