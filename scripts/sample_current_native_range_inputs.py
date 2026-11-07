"""Capture range and energy input candidates for a bounded historical key selection."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
from scripts.sample_current_native_ability_catalog import build_launch,validate_record_costs_timing

GAME_SHA='1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA='F46E827E5CA29D9CA5CBDDC43CC30D37CBC26CB4E745A9CAFAE1793AB7B6D523'
READER=ROOT/'artifacts/native-range-context-20261107/publish/RiftReader2.Live.exe'
SOURCE=ROOT/'artifacts/rre-peer-reference-20261107/cost-range-comparison.json'

def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid-lab')
    if READER.is_symlink() or not READER.is_file() or READER.stat().st_size!=117733216 or digest(READER)!=READER_SHA: raise ValueError('reader-mismatch')
    sources=[Path(__file__),ROOT/'scripts/sample_current_native_ability_catalog.py',ROOT/'scripts/sample_current_native_ability_records.py']
    pins={str(p):digest(p) for p in sources}
    source_raw=SOURCE.read_bytes(); source_sha=hashlib.sha256(source_raw).hexdigest().upper(); prior=json.loads(source_raw)
    selected=[]
    for row in prior['rows']:
        range_value=row['apiRangeComparison']['rangeMax']; reasons=[]
        if range_value['apiPresent'] and type(range_value['apiValue']) in (int,float) and range_value['apiValue']>0: reasons.append('historical-positive-range-max')
        if row.get('energyComparison')=='different-input': reasons.append('historical-energy-mismatch')
        if reasons:
            key=row.get('nativeKey')
            if type(key) is not int or not 0<=key<=0xffffffff or any(x['key']==key for x in selected): raise ValueError('invalid-provenance-keys')
            selected.append({'key':key,'id':row.get('id'),'reasons':reasons})
    if not 1<=len(selected)<=54: raise ValueError('invalid-selection-size')
    keys=[x['key'] for x in selected]
    api=LabCodex();_,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root/'.doctor'))
    token=uuid.uuid4().hex;output=ROOT/'artifacts/native-range-inputs-20261107/runs'/lab/token;output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot']+r'\current-zone-id-'+READER_SHA[:16]
    exe=folder+r'\RiftReader2.Live.exe';report=folder+r'\range-'+token+'.json';probe=folder+r'\identity-'+token+'.json';guest_key=folder+r'\key-'+token+'.txt'
    provenance={'sourcePath':str(SOURCE),'sourceSha256':source_sha,'selection':selected}
    with (output/'provenance.json').open('x',encoding='utf-8') as f:json.dump(provenance,f,indent=2)
    key_bytes=','.join(str(key) for key in keys).encode('ascii');key_sha=hashlib.sha256(key_bytes).hexdigest().upper();key_file=output/'key.txt'
    with key_file.open('xb') as f:f.write(key_bytes)
    with api._session(config,settings,vm,output) as guest:
        preflight=("$ErrorActionPreference='Stop';$folder="+ps_literal(folder)+";[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;if($sha -cne "+ps_literal(GAME_SHA)+"){throw 'rift-build-mismatch'};"
            "$exe="+ps_literal(exe)+";$installed=Test-Path -LiteralPath $exe -PathType Leaf;if($installed -and (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'guest-reader-hash-collision'};"
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;sha=$sha;installed=[bool]$installed};"
            "$bytes=[Text.Encoding]::UTF8.GetBytes(($data|ConvertTo-Json -Compress));$f=[IO.File]::Open("+ps_literal(probe)+",[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);try{$f.Write($bytes,0,$bytes.Length)}finally{$f.Dispose()}")
        guest.powershell(preflight,timeout=80);guest.copy_from_guest(probe,output/'identity.json',timeout=50)
        identity=json.loads((output/'identity.json').read_text(encoding='utf-8-sig'));pid=identity['pid'];ticks=identity['ticks']
        if type(pid) is not int or pid<=0 or type(ticks) is not int or ticks<=0 or identity.get('sha')!=GAME_SHA or type(identity.get('installed')) is not bool: raise ValueError('invalid-process-identity')
        if not identity['installed']:guest.run('copyFileFromHostToGuest',str(READER),exe,timeout=180)
        guest.powershell('if(Test-Path -LiteralPath '+ps_literal(guest_key)+"){throw 'key-exists'}",timeout=30)
        guest.run('copyFileFromHostToGuest',str(key_file),guest_key,timeout=60)
        command=build_launch(exe,guest_key,report,pid,ticks,key_sha,'sample-current-ability-records',reader_sha=READER_SHA)
        if len(base64.b64encode(command.encode('utf-16le')))>4096:raise ValueError('guest-command-too-large')
        guest.powershell(command,timeout=130);guest.copy_from_guest(report,output/'samples.json',timeout=70)
    with (output/'samples.json').open('rb') as f:raw=f.read(1000001)
    if len(raw)>1000000:raise ValueError('report-too-large')
    result=json.loads(raw.decode('utf-8-sig'));validate_record_costs_timing(result,pid=pid,ticks=ticks,keys=keys);obs=result['observation']
    for row in obs['records']:
        if row['status']!='type-verified-candidate': continue
        raw_range=row['rawRange']; begin=raw_range.get('tagsBegin'); end=raw_range.get('tagsEnd'); tags=raw_range.get('tags')
        if type(begin) is not int or type(end) is not int or not isinstance(tags,list) or len(tags)>64 or any(type(v) is not int or not 0<=v<=0xffffffff for v in tags) or (begin==0)!=(end==0) or end<begin or end-begin!=len(tags)*4 or (begin!=0 and (begin<0x10000 or begin%4 or end>0x7fffffffffff)): raise ValueError('invalid-tag-vector')
        for child in row['rawCosts']['children']:
            flag=child.get('flag20')
            if child.get('status')=='energy-raw-candidate':
                if type(flag) is not int or not 0<=flag<=255: raise ValueError('invalid-energy-flag')
            elif flag is not None: raise ValueError('unexpected-energy-flag')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper()!=source_sha or any(digest(p)!=pins[str(p)] for p in sources) or digest(READER)!=READER_SHA:raise ValueError('source-or-reader-changed')
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'identity':obs['identity'],'readerSha256':READER_SHA,'guestReaderReused':identity['installed'],'selection':selected,'records':obs['records'],'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'keySha256':key_sha,'provenance':str(output/'provenance.json'),'provenanceSha256':digest(output/'provenance.json'),'sourceSha256':pins,'startedAtUtc':obs['startedAtUtc'],'completedAtUtc':obs['completedAtUtc'],'qualification':'raw definition inputs only; adjusted API range, costs, freshness and restart unverified'}
    with (output/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lab',required=True,choices=('lab1','lab2'));a=p.parse_args()
    print(json.dumps(run(a.lab)),flush=True)
