"""Physical target-name reducer and mocked acquisition; no native process access."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import physical_rift as p
from tests.test_physical_only_selection import IDENTITY, REPORT_IDENTITY


def report():
    # Native template report shape retained from physical PID51524; no artifact dependency.
    return dict(schemaVersion=1, contractVersion='native-target-template-name-candidate/1', status='complete',
        observation=dict(identity=deepcopy(REPORT_IDENTITY),
            startedAtUtc='2026-11-12T22:09:06.8665483+00:00', completedAtUtc='2026-11-12T22:09:06.9236355+00:00',
            selfKey=239816685251645959, targetKey=9223372045797034555,
            targetEntity=2624201541136, templateKey=545286772, selector=623, tlsIndex=20,
            collection=2623363710400, localizationMode=1, formattingFlag=0, status='raw-candidate',
            recordAddress=2624273186368, localizationKey=1066247106, fallbackText='3rd Guard Soldier',
            dictionary=dict(identity=deepcopy(REPORT_IDENTITY), startedAtUtc='2026-11-12T22:09:06.9078087+00:00',
                completedAtUtc='2026-11-12T22:09:06.9094737+00:00', rows=[dict(key=1066247106,status='cache-miss')]),
            qualification='cache-only raw candidate; name publication, freshness and restart unverified'))


class TargetNameTests(unittest.TestCase):
    def test_physical_shape_lossless_keys_and_selected_name(self):
        value=p._native_values('target-name',report())
        self.assertEqual(value['selectedBaseNameCandidate'],'3rd Guard Soldier')
        self.assertEqual(value['targetKey'],'9223372045797034555')
        self.assertEqual(value['selfKey'],'239816685251645959')
        self.assertEqual(value['status'],'available-candidate')
        self.assertIsNone(value['reason'])
        self.assertIn('restart unverified',value['qualification'])

    def test_nonselected_modes_and_unreadable_text_unavailable(self):
        for changes,reason in ((dict(localizationMode=0),'unsupported-localization-mode'),
                (dict(formattingFlag=1),'formatting-required'),(dict(fallbackText=''),'empty-fallback'),
                (dict(fallbackText='a\nb'),'unreadable-fallback')):
            with self.subTest(changes=changes):
                source=report();source['observation'].update(changes)
                value=p._native_values('target-name',source)
                self.assertEqual(value['reason'],reason)
                self.assertIsNone(value['selectedBaseNameCandidate'])
                self.assertEqual(value['rawFallbackNameCandidate'],source['observation']['fallbackText'])

    def test_cache_and_type_statuses_explicitly_unavailable(self):
        for status in ('cache-miss','null-holder','null-record','unverified-record-type','null-name-child','unverified-name-type'):
            source=report();row=source['observation'];row.update(status=status,localizationKey=None,fallbackText=None,dictionary=None)
            if status in ('cache-miss','null-holder','null-record'):row['recordAddress']=None
            value=p._native_values('target-name',source)
            self.assertEqual(value['reason'],status)
            self.assertEqual(value['status'],'unavailable')

    def test_malformed_contract_keys_pointers_time_and_status_rejected(self):
        for field,value in (('selfKey',True),('targetKey','9223372045797034555'),('targetKey',2**64),
                ('targetEntity',3),('collection',0),('recordAddress',True),('selector',65536),
                ('tlsIndex',1088),('status','complete'),('fallbackText','x'*128),
                ('completedAtUtc','2026-11-12T22:09:05+00:00'),('qualification','qualified')):
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                source=report();source['observation'][field]=value;p._native_values('target-name',source)
        for field,value in (('schemaVersion',True),('contractVersion','wrong'),('status','partial')):
            with self.subTest(field=field),self.assertRaises(ValueError):
                source=report();source[field]=value;p._native_values('target-name',source)
        source=report();source['observation']['dictionary']['identity']['processId']+=1
        with self.assertRaises(ValueError):p._native_values('target-name',source)

    def acquire(self, *, stale=False, wrong_summary=False, wrong_epoch=False):
        with TemporaryDirectory() as folder:
            exe=Path(folder)/'reader.exe';exe.touch();path=Path(folder)/'new.json'
            selection=dict(status='ready',ownerHost='AMD-DESKTOP',target=deepcopy(IDENTITY))
            def run(command,**kwargs):
                self.assertEqual(command,[str(exe),'sample-current-target-template-name','--pid','123','--start-ticks',IDENTITY['processStartUtcTicks'],'--output',str(path)])
                source=report();row=source['observation']
                if not stale:
                    now=datetime.now(timezone.utc).isoformat();row.update(startedAtUtc=now,completedAtUtc=now)
                    row['dictionary'].update(startedAtUtc=now,completedAtUtc=now)
                if wrong_epoch:row['identity']['processId']+=1
                path.write_text(json.dumps(source))
                summary=dict(recordType='native-target-template-name-summary/1',status='complete' if wrong_summary else 'raw-candidate',output=str(path))
                return subprocess.CompletedProcess(command,0,json.dumps(summary),'')
            with patch.object(p.socket,'gethostname',return_value='AMD-DESKTOP'),patch.object(p,'NATIVE_EXE',exe),patch.object(p.subprocess,'run',side_effect=run):
                value=p.read_native(selection,'target-name',output=path)
            if value['status']=='complete':self.assertEqual(value['nativeSourceSha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            return value

    def test_new_kind_dispatch_fresh_receipt_source_hash(self):
        result=self.acquire();self.assertEqual(result['status'],'complete')
        self.assertEqual(result['nativeValues']['selectedBaseNameCandidate'],'3rd Guard Soldier')

    def test_stale_receipt_mismatch_and_wrong_epoch_refuse(self):
        for kwargs in (dict(stale=True),dict(wrong_summary=True),dict(wrong_epoch=True)):
            with self.subTest(kwargs=kwargs):self.assertEqual(self.acquire(**kwargs)['status'],'blocked')

    def test_target_name_cannot_request_burst(self):
        selection=dict(status='ready',ownerHost='AMD-DESKTOP',target=deepcopy(IDENTITY))
        with patch.object(p.socket,'gethostname',return_value='AMD-DESKTOP'),patch.object(p.subprocess,'run') as run:
            self.assertEqual(p.read_native(selection,'target-name',samples=2)['status'],'blocked');run.assert_not_called()


if __name__=='__main__':unittest.main()
