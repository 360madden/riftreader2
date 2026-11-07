"""Capture raw self experience-route seeds without game input."""
import argparse, hashlib, json, math, struct, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = '723C499D90FA10B02AC22E85441DE132E525650178DA4CF841C73C9B6781448E'
READER = ROOT / 'artifacts/native-experience-seed-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-experience-seed-20261107/runs'

QUALIFICATION='raw experience inputs; calculated experience, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid experience-seed report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-current-experience-seed-candidate/1' or report.get('status')!='complete': invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00'));end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start or not integer(o.get('unitKey'),1,2**64-1): invalid()
    for field in ('entity','component','owner'):
        if not integer(o.get(field),0x10000,0x7fffffffffff): invalid()
    for field in ('ownerVtableRva','ownerGetterRva'):
        if o.get(field) is not None and not integer(o[field],0,2**64-1): invalid()
    index=o.get('index');flag=o.get('rawByte24F'); begin=o.get('vectorBegin'); endptr=o.get('vectorEnd'); refs=o.get('references'); branch=o.get('branch');selected=o.get('selected');a=o.get('special7D8');b=o.get('special7E0')
    if not integer(index,-2**31,2**31-1) or not integer(o.get('rawDword160'),0,2**32-1) or not integer(flag,0,255) or not integer(begin,0,2**64-1) or not integer(endptr,0,2**64-1) or not isinstance(refs,list) or len(refs)>256 or (begin==0)!=(endptr==0) or endptr<begin or endptr-begin!=8*len(refs) or (begin!=0 and (begin<0x10000 or begin%8 or endptr>0x7fffffffffff)) or any(not integer(r,0,2**64-1) for r in refs): invalid()
    if branch=='indexed-raw-candidate':
        if not 0<=index<len(refs) or refs[index]==0 or not isinstance(selected,dict) or selected.get('address')!=refs[index] or not integer(selected.get('address'),0x10000,0x7fffffffffff) or any(x is not None for x in (a,b)): invalid()
        for field in ('vtableRva','getterRva'):
            if selected.get(field) is not None and not integer(selected[field],0,2**64-1): invalid()
        if not integer(selected.get('rawInt64_18'),-2**63,2**63-1) or not integer(selected.get('rawDword24'),0,2**32-1) or not integer(selected.get('rawFloat20Bits'),0,2**32-1): invalid()
        bits=selected['rawFloat20Bits']; number=struct.unpack('<f',struct.pack('<I',bits))[0]; value=selected.get('rawFloat20')
        if math.isfinite(number):
            if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>3.4028234663852886e38 or struct.pack('<f',value)!=struct.pack('<I',bits): invalid()
        elif value is not None: invalid()
    elif branch=='special-index-minus-one':
        if index!=-1 or flag==0 or selected is not None or not integer(a,0,2**64-1) or not integer(b,0,2**64-1): invalid()
    elif branch=='index-minus-one':
        if index!=-1 or flag!=0 or any(x is not None for x in (selected,a,b)): invalid()
    elif branch=='index-out-of-range':
        if index==-1 or 0<=index<len(refs) or any(x is not None for x in (selected,a,b)): invalid()
    elif branch=='selected-null':
        if not 0<=index<len(refs) or refs[index]!=0 or any(x is not None for x in (selected,a,b)): invalid()
    else: invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117647200 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-experience-seed-' + READER_SHA[:16]
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
            "& $exe sample-current-experience-seed --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
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
