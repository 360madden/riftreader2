"""Capture the raw Soul Recall definition timing for the current lab process."""
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
READER_SHA='7C2E38B9BF825CB4613DAD6A5A5140C41A81200CD344CBE7D9C76706D76344B1'
READER=ROOT/'artifacts/native-cooldown-direct-scale-20261107/publish/RiftReader2.Live.exe'
KEY=1012591716

def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid-lab')
    if READER.is_symlink() or not READER.is_file() or READER.stat().st_size!=117720928 or digest(READER)!=READER_SHA: raise ValueError('reader-mismatch')
    sources=[Path(__file__),ROOT/'scripts/sample_current_native_ability_catalog.py',ROOT/'scripts/sample_current_native_ability_records.py']
    pins={str(p):digest(p) for p in sources}
    api=LabCodex();_,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root/'.doctor'))
    token=uuid.uuid4().hex;output=ROOT/'artifacts/native-soul-recall-timing-20261107/runs'/lab/token;output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot']+r'\current-zone-id-'+READER_SHA[:16]
    exe=folder+r'\RiftReader2.Live.exe';report=folder+r'\soul-'+token+'.json';probe=folder+r'\identity-'+token+'.json';guest_key=folder+r'\key-'+token+'.txt'
    key_bytes=str(KEY).encode('ascii');key_sha=hashlib.sha256(key_bytes).hexdigest().upper();key_file=output/'key.txt'
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
    result=json.loads(raw.decode('utf-8-sig'));validate_record_costs_timing(result,pid=pid,ticks=ticks,keys=[KEY]);obs=result['observation'];row=obs['records'][0]
    if any(digest(p)!=pins[str(p)] for p in sources) or digest(READER)!=READER_SHA:raise ValueError('source-or-reader-changed')
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'identity':obs['identity'],'readerSha256':READER_SHA,'guestReaderReused':identity['installed'],'key':KEY,'recordStatus':row['status'],'rawTiming':row.get('rawTiming'),'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'keySha256':key_sha,'sourceSha256':pins,'startedAtUtc':obs['startedAtUtc'],'completedAtUtc':obs['completedAtUtc'],'qualification':'raw definition timing candidate; cooldown, freshness and restart unverified'}
    with (output/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lab',required=True,choices=('lab1','lab2'));a=p.parse_args()
    print(json.dumps(run(a.lab)),flush=True)
