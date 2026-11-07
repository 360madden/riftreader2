"""Capture qualified self experience-value candidates without game input."""
import argparse, hashlib, json, math, struct, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
from scripts.sample_current_native_experience_seed import validate_report as validate_seed
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = 'A96508FE963E4DFDE6EABD50889FD0432A72C0309AEC562E35CBF87B584F49D9'
READER = ROOT / 'artifacts/native-zone-provider-fix-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-experience-values-20261107/runs'

QUALIFICATION='candidate-only; API agreement, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid experience-values report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-current-experience-values-candidate/1' or report.get('status')!='complete': invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00'));end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
    seed=o.get('seed')
    validate_seed({'schemaVersion':1,'contractVersion':'native-current-experience-seed-candidate/1','status':'complete','observation':seed},pid=pid,ticks=ticks)
    if seed.get('identity')!=identity: invalid()
    try: seed_start=datetime.fromisoformat(seed['startedAtUtc'].replace('Z','+00:00'));seed_end=datetime.fromisoformat(seed['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if seed_start<start or seed_end>end: invalid()
    status=o.get('valueStatus'); level=o.get('level'); limit=o.get('limit'); mode=o.get('mode'); baseline=o.get('baseline'); needed=o.get('needed'); accumulated=o.get('accumulatedCandidate')
    for x in (level,limit,mode,needed):
        if x is not None and not integer(x,-2**31,2**31-1): invalid()
    for x in (baseline,accumulated):
        if x is not None and not integer(x,-2**63,2**63-1): invalid()
    if status=='seed-unavailable':
        if seed['branch']=='indexed-raw-candidate' or any(x is not None for x in (level,limit,mode,baseline,needed,accumulated)): invalid()
    elif status=='progress-type-unavailable':
        if seed['branch']!='indexed-raw-candidate' or any(x is not None for x in (level,limit,mode,baseline,needed,accumulated)): invalid()
    elif status in ('cap-type-unavailable','native-minus-one-level-cap','baseline-unavailable','provider-uninitialized','cold-cache-or-null','needed-type-unavailable','native-minus-one-needed','arithmetic-overflow','raw-values-candidate'):
        if seed['branch']!='indexed-raw-candidate' or level is None or (level & 0xffffffff)!=seed['selected']['rawDword24']: invalid()
        if status=='cap-type-unavailable':
            if any(x is not None for x in (limit,mode,baseline,needed,accumulated)): invalid()
        elif limit is None: invalid()
        if status not in ('cap-type-unavailable',):
            if status in ('native-minus-one-level-cap','baseline-unavailable'):
                if any(x is not None for x in (mode,baseline,needed,accumulated)): invalid()
            elif baseline is None: invalid()
        if status in ('provider-uninitialized','cold-cache-or-null','needed-type-unavailable') and any(x is not None for x in (mode,needed,accumulated)): invalid()
        if status in ('native-minus-one-needed','arithmetic-overflow','raw-values-candidate'):
            if mode is None or needed is None: invalid()
            if status=='native-minus-one-needed' and (needed!=-1 or accumulated is not None): invalid()
            if status=='arithmetic-overflow' and (needed==-1 or accumulated is not None): invalid()
            if status=='raw-values-candidate' and (needed==-1 or accumulated is None or accumulated!=seed['selected']['rawInt64_18']-baseline+needed): invalid()
    else: invalid()
    rested_status=o.get('restedStatus'); rested_flag=o.get('restedFlag'); rested_bits=o.get('restedRawBits'); rested=o.get('restedCandidate')
    if rested_status in ('unavailable','provider-uninitialized'):
        if any(v is not None for v in (rested_flag,rested_bits,rested)): invalid()
    elif rested_status in ('raw-rested-candidate','nonfinite-or-out-of-range'):
        if not integer(rested_flag,0,255) or not integer(rested_bits,0,2**32-1) or seed['branch']!='indexed-raw-candidate': invalid()
        if rested_flag!=0 and rested_bits!=seed['selected']['rawFloat20Bits']: invalid()
        number=struct.unpack('<f',struct.pack('<I',rested_bits))[0]
        in_range=math.isfinite(number) and -(2**63)<=number<2**63
        if rested_status=='raw-rested-candidate':
            if not in_range or not integer(rested,-2**63,2**63-1) or rested!=math.trunc(number): invalid()
        elif in_range or rested is not None: invalid()
    else: invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117704544 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-zone-id-' + READER_SHA[:16]
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
            "& $exe sample-current-experience-values --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
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
