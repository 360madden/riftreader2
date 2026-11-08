"""Capture bounded raw self-owned buff-list candidates without game input."""
import argparse, hashlib, json, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = 'A70BD1259DAEC131898C638D3D4D540086C6195015AFA33BA262E5CA9CEE8B04'
READER = ROOT / 'artifacts/native-buff-state80-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-buff-state80-20261107/runs'

QUALIFICATION='raw-list-candidates; visibility, buff IDs, names, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid buff-seeds report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-current-buff-seeds-candidate/1' or report.get('status')!='complete': invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00')); end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
    if not integer(o.get('unitKey'),1,2**64-1) or not integer(o.get('context'),0x10000,0x7fffffffffff-0x310) or type(o.get('sentinel')) is not int or o['sentinel']!=o['context']+0x310: invalid()
    nodes=o.get('nodes')
    if not isinstance(nodes,list) or len(nodes)>256: invalid()
    seen=set()
    for index,node in enumerate(nodes):
        if not isinstance(node,dict) or not integer(node.get('address'),0x10000,0x7fffffffffff) or node['address'] in seen: invalid()
        seen.add(node['address'])
        if not integer(node.get('next'),0x10000,0x7fffffffffff) or not integer(node.get('object'),0,2**64-1) or not integer(node.get('control'),0,2**64-1): invalid()
        if node['next'] != (nodes[index+1].get('address') if index+1<len(nodes) and isinstance(nodes[index+1],dict) else o['sentinel']): invalid()
        raw=node.get('rawObject')
        if not isinstance(raw,dict) or raw.get('status') not in ('raw-candidate','unavailable'): invalid()
        numeric=('vtableRva','dword08','qword10','qword20','qword28','dword3C','qword48','descriptorDword38','descriptorVtableRva','stateDword88','clockAddress','clockVtableRva','clockSlot30Rva','clockSlot38Rva','clockSlot48Rva')
        for k in numeric:
            value=raw.get(k); maximum=2**32-1 if k in ('dword08','dword3C','descriptorDword38','stateDword88') else 2**64-1
            if value is not None and not integer(value,0,maximum): invalid()
        # Newer readers expose a signed grouping input. Older retained reports
        # legitimately lack both fields; absence is not evidence for zero.
        if ('stateDword80' in raw) != ('stateDword80Status' in raw): invalid()
        if 'stateDword80' in raw:
            value=raw['stateDword80']; status80=raw['stateDword80Status']
            if status80 not in ('raw-candidate','null','unavailable'): invalid()
            if status80=='raw-candidate':
                if raw['status']!='raw-candidate' or not raw.get('qword20') or not integer(value,-2**31,2**31-1): invalid()
            elif value is not None: invalid()
            if raw['status']=='unavailable' and status80!='unavailable': invalid()
            if raw['status']=='raw-candidate' and ((raw.get('qword20')==0 and status80!='null') or (raw.get('qword20')!=0 and status80=='null')): invalid()
        if raw['status']=='unavailable':
            if any(raw.get(k) is not None for k in numeric+('descriptorStatus','stateStatus','clockStatus')): invalid()
        else:
            if any(raw.get(k) is None for k in ('dword08','qword10','qword20','qword28','dword3C','qword48')) or raw.get('descriptorStatus') not in ('null','unavailable','raw-candidate') or raw.get('stateStatus') not in ('null','unavailable','raw-candidate') or raw.get('clockStatus') not in ('null','unavailable','vtable-outside-module','raw-candidate'): invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117741408 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-buff-seeds-' + READER_SHA[:16]
    exe=folder+r'\RiftReader2.Live.exe'; report=folder+r'\sample-'+token+'.json'; probe=folder+r'\identity-'+token+'.json'
    with api._session(config,settings,vm,output) as guest:
        preflight=("$ErrorActionPreference='Stop';$folder="+ps_literal(folder)+";[IO.Directory]::CreateDirectory($folder)|Out-Null;"
            "$game=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);if($game.Count -ne 1){throw 'exactly-one-game-required'};"
            "$p=$game[0];$sha=(Get-FileHash -LiteralPath $p.Path -Algorithm SHA256).Hash;if($sha -cne "+ps_literal(GAME_SHA)+"){throw 'rift-build-mismatch'};"
            "$exe="+ps_literal(exe)+";$installed=Test-Path -LiteralPath $exe -PathType Leaf;if($installed -and (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'guest-reader-hash-collision'};"
            "$data=[ordered]@{pid=[int]$p.Id;ticks=[long]$p.StartTime.ToUniversalTime().Ticks;sha=$sha;installed=[bool]$installed};"
            "$bytes=[Text.Encoding]::UTF8.GetBytes(($data|ConvertTo-Json -Compress));$f=[IO.File]::Open("+ps_literal(probe)+",[IO.FileMode]::CreateNew,[IO.FileAccess]::Write);try{$f.Write($bytes,0,$bytes.Length)}finally{$f.Dispose()}")
        guest.powershell(preflight,timeout=80); guest.copy_from_guest(probe,output/'identity.json',timeout=50)
        identity=json.loads((output/'identity.json').read_text(encoding='utf-8-sig')); pid=identity['pid']; ticks=identity['ticks']
        if type(pid) is not int or pid<=0 or type(ticks) is not int or ticks<=0 or identity.get('sha')!=GAME_SHA or type(identity.get('installed')) is not bool: raise ValueError('invalid process identity')
        if not identity['installed']: guest.run('copyFileFromHostToGuest',str(READER),exe,timeout=180)
        launch=("$ErrorActionPreference='Stop';$exe="+ps_literal(exe)+";if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'guest-reader-sha-mismatch'};"
            "$g=Get-Process -Id "+str(pid)+" -ErrorAction Stop;if($g.ProcessName -cne 'rift_x64' -or [long]$g.StartTime.ToUniversalTime().Ticks -ne "+str(ticks)+"){throw 'game-epoch-changed'};"
            "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "+ps_literal(GAME_SHA)+"){throw 'rift-build-changed'};"
            "$out="+ps_literal(report)+";if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
            "& $exe sample-current-buff-seeds --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};if((Get-Item -LiteralPath $out).Length -gt 8000000){throw 'native-report-too-large'}")
        guest.powershell(launch,timeout=130);guest.copy_from_guest(report,output/'samples.json',timeout=70)
    raw=(output/'samples.json').read_bytes()
    if len(raw)>8000000: raise ValueError('report too large')
    data=json.loads(raw.decode('utf-8-sig'))
    observation=validate_report(data,pid=pid,ticks=ticks)
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'gameProcessId':pid,'gameProcessStartUtcTicks':ticks,'gameSha256':GAME_SHA,'readerExecutableSha256':READER_SHA,'guestReaderReused':identity['installed'],'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'observation':observation}
    with (output/'summary.json').open('x',encoding='utf-8') as f: json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--lab',choices=('lab1','lab2'),required=True);args=parser.parse_args()
    try: print(json.dumps(run(args.lab)),flush=True)
    except (ValueError,OSError,RuntimeError) as exc: print(json.dumps({'status':'blocked','reason':str(exc)[:160]}),flush=True);raise SystemExit(2) from None
