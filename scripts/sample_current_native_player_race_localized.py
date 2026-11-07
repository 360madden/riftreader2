"""Capture bounded self race-name candidates without game input."""
import argparse, hashlib, json, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
from scripts.sample_current_native_selected_target import derive_name
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = '594D9D9E07EB86B0D928842B4A572863D2EC03D54DEA7937BD03BAD881B40184'
READER = ROOT / 'artifacts/native-player-race-localized-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-player-race-localized-20261107/runs'

QUALIFICATION='raw referent seed; referent type, API correspondence, freshness and restart unverified'

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
    rs=o.get('raceRecordStatus'); record=o.get('raceRecordAddress'); selector=o.get('raceSelector'); tls=o.get('raceTlsIndex'); collection=o.get('raceCollection'); text=o.get('raceTextCandidate')
    if selector is not None and not integer(selector,0,65535): invalid()
    if tls is not None and not integer(tls,0,2**32-1): invalid()
    if collection is not None and not integer(collection,0x10000,0x7fffffffffff): invalid()
    if record is not None and not integer(record,0x10000,0x7fffffffffff): invalid()
    if rs is None:
        if any(v is not None for v in (record,selector,tls,collection,text)): invalid()
    elif rs=='unavailable':
        if text is not None: invalid()
    elif rs in ('cache-miss','null-holder','null-record','unverified-type','type-0718-text-unavailable','type-0718-text-candidate'):
        if ps!='resident-unqueried' or status!='raw-candidate' or selector is None or not integer(tls,0,1087) or collection is None: invalid()
        if rs in ('cache-miss','null-holder','null-record'):
            if record is not None or text is not None: invalid()
        else:
            if record is None: invalid()
            if rs=='type-0718-text-candidate':
                if not isinstance(text,str): invalid()
            elif text is not None: invalid()
    else: invalid()
    localized=o.get('localizedNameSeed')
    if rs in ('type-0718-text-unavailable','type-0718-text-candidate'):
        if not isinstance(localized,dict) or localized.get('qualification')!='raw localized name seed; API raceName selection and freshness unverified': invalid()
        ls=localized.get('status'); mode=localized.get('localizationMode'); child=localized.get('childAddress'); loc=localized.get('localizationKey'); fallback=localized.get('fallbackText'); dictionary=localized.get('dictionary')
        if ls=='unavailable':
            if any(v is not None for v in (mode,child,loc,fallback,dictionary)): invalid()
        elif ls=='null-child':
            if not integer(mode,-2**31,2**31-1) or any(v is not None for v in (child,loc,fallback,dictionary)): invalid()
        elif ls=='unverified-type':
            if not integer(mode,-2**31,2**31-1) or not integer(child,0x10000,0x7fffffffffff) or any(v is not None for v in (loc,fallback,dictionary)): invalid()
        elif ls in ('raw-candidate','raw-candidate-dictionary-unavailable'):
            if not integer(mode,-2**31,2**31-1) or not integer(child,0x10000,0x7fffffffffff) or not integer(loc,0,2**32-1) or not isinstance(fallback,str): invalid()
            if ls=='raw-candidate-dictionary-unavailable' and (loc==0 or dictionary is not None): invalid()
            if ls=='raw-candidate' and ((loc==0 and dictionary is not None) or (loc!=0 and not isinstance(dictionary,dict))): invalid()
        else: invalid()
    elif localized is not None: invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117630816 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-player-race-localized-' + READER_SHA[:16]
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
    localized=observation.get('localizedNameSeed'); name=None
    if isinstance(localized,dict) and localized.get('status') in ('raw-candidate','raw-candidate-dictionary-unavailable'):
        if localized['localizationMode']==1 and localized['fallbackText']: name={'fallbackNameCandidate':localized['fallbackText'],'qualification':'mode 1 raw fallback candidate; API raceName selection unverified'}
        elif localized.get('dictionary') is not None:
            seed={'status':'raw-candidate','branch':'localized','localizationKey':localized['localizationKey'],'rawFallback':localized['fallbackText'],'dictionary':localized['dictionary']}
            name=derive_name({'status':'candidate','identity':observation['identity'],'nameSeed':seed},pid=pid,ticks=ticks)
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'gameProcessId':pid,'gameProcessStartUtcTicks':ticks,'gameSha256':GAME_SHA,'readerExecutableSha256':READER_SHA,'guestReaderReused':identity['installed'],'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'observation':observation,'localizedCandidate':name}
    with (output/'summary.json').open('x',encoding='utf-8') as f: json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--lab',choices=('lab1','lab2'),required=True);args=parser.parse_args()
    try: print(json.dumps(run(args.lab)),flush=True)
    except (ValueError,OSError,RuntimeError) as exc: print(json.dumps({'status':'blocked','reason':str(exc)[:160]}),flush=True);raise SystemExit(2) from None
