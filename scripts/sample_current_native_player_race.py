"""Capture raw self race-route candidates without game input."""
import argparse, hashlib, json, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = 'AFA473BD8C69B0AE6D8BE9D2BD781E375007512703ADD6DC27DFD2EBC2664B58'
READER = ROOT / 'artifacts/native-player-race-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-player-race-20261107/runs'

QUALIFICATION='raw referent seed; race type, API text, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid player-race seed report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-current-player-race-seed/1' or report.get('status')!='complete': invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00'));end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start or not integer(o.get('selfKey'),1,2**64-1) or not integer(o.get('selfEntity'),0x10000,0x7fffffffffff) or not integer(o.get('health'),0x10000,0x7fffffffffff): invalid()
    status=o.get('referentStatus');addr=o.get('referentAddress');vt=o.get('referentVtable');getter=o.get('referentGetterRva');key=o.get('rawRaceKey')
    if status=='raw-candidate':
        if not integer(addr,0x10000,0x7fffffffffff) or not integer(vt,0,2**64-1) or not integer(key,0,2**32-1) or (getter is not None and not integer(getter,0,2**64-1)): invalid()
    elif status in ('unavailable','null-referent'):
        if any(v is not None for v in (addr,vt,getter,key)): invalid()
    else: invalid()
    provider=o.get('providerAddress'); ps=o.get('providerStatus')
    if ps=='resident-unqueried':
        if not integer(provider,0x10000,0x7fffffffffff): invalid()
    elif ps in ('null-provider','unavailable'):
        if provider is not None: invalid()
    else: invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117602144 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-player-race-' + READER_SHA[:16]
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
            "& $exe sample-current-player-race --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
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
