"""Capture a guarded selected-target template-name cache candidate."""
import argparse, base64, hashlib, json, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
from scripts.sample_current_native_ability_catalog import validate_dictionary
from scripts.native_localization_huffman import decode_localization_huffman
from scripts.native_localization_record import parse_localization_record
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = '4B481314B7E72B83CB8F5163D895818236E1C1B4E48FEFD2C6C56B66BCB1BB0F'
READER = ROOT / 'artifacts/native-target-template-name-mode-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-target-template-name-20261107/runs'

QUALIFICATION='cache-only raw candidate; name publication, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid target-template-name report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-target-template-name-candidate/1' or report.get('status')!='complete': invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00')); end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
    if not integer(o.get('selfKey'),1,2**64-1) or not integer(o.get('targetKey'),1,2**64-1) or not integer(o.get('targetEntity'),0x10000,0x7fffffffffff) or not integer(o.get('templateKey'),1,2**32-1) or not integer(o.get('selector'),0,65535) or not integer(o.get('tlsIndex'),0,1087) or not integer(o.get('collection'),0x10000,0x7fffffffffff): invalid()
    if not integer(o.get('localizationMode'),-(2**31),2**31-1) or not integer(o.get('formattingFlag'),0,2**32-1): invalid()
    status=o.get('status'); record=o.get('recordAddress'); key=o.get('localizationKey'); fallback=o.get('fallbackText'); dictionary=o.get('dictionary')
    if status in ('cache-miss','null-holder','null-record'):
        if any(v is not None for v in (record,key,fallback,dictionary)): invalid()
    elif status in ('unverified-record-type','null-name-child','unverified-name-type'):
        if not integer(record,0x10000,0x7fffffffffff) or any(v is not None for v in (key,fallback,dictionary)): invalid()
    elif status=='raw-candidate':
        if not integer(record,0x10000,0x7fffffffffff) or not integer(key,0,2**32-1) or not isinstance(fallback,str) or (key==0 and dictionary is not None) or (key!=0 and not isinstance(dictionary,dict)): invalid()
    else: invalid()
    return o

def candidate_name(o, *, pid, ticks):
    result={'baseNameLocale1Candidate':None,'nameQualification':'base name/locale1 candidate; API decoration/language unverified','nameUnavailableReason':o['status'],'rawFallbackNameCandidate':o.get('fallbackText') if o['status']=='raw-candidate' and o.get('fallbackText') else None,'rawFallbackNameQualification':'raw typed fallback text candidate; active manager selection and API decoration unverified'}
    result.update(localizationMode=o['localizationMode'],formattingFlag=o['formattingFlag'],selectedBaseNameCandidate=None,selectedBaseNameQualification='mode-selected base name candidate; API equivalence and decoration unverified')
    if o['status']=='raw-candidate' and o['localizationMode']==1 and o['fallbackText']:
        result['selectedBaseNameCandidate']=o['fallbackText']
    if o['status']!='raw-candidate' or not o['localizationKey']: return result
    try:
        d=o['dictionary']; key=o['localizationKey']
        if d.get('identity')!=o['identity']: raise ValueError('dictionary-identity-mismatch')
        validate_dictionary({'schemaVersion':1,'contractVersion':'native-current-localization-dictionary-candidate-sample/1','status':'complete','observation':d},pid=pid,ticks=ticks,keys=[key])
        row=d['rows'][0]
        if row['status']!='raw-candidate': raise ValueError('dictionary-'+row['status'])
        decoded,_=decode_localization_huffman(base64.b64decode(d['frequencyBytesBase64'],validate=True),base64.b64decode(row['compressedBytesBase64'],validate=True),row['decodedSize'])
        text=parse_localization_record(decoded)['candidate_text']
        if not text: raise ValueError('empty-candidate-text')
        result.update(baseNameLocale1Candidate=text,nameUnavailableReason=None)
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        result['nameUnavailableReason']='name-decode-unavailable: '+str(exc)[:100]
    return result

def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117496160 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-target-template-name-mode-' + READER_SHA[:16]
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
            "& $exe sample-current-target-template-name --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};if((Get-Item -LiteralPath $out).Length -gt 8000000){throw 'native-report-too-large'}")
        guest.powershell(launch,timeout=130);guest.copy_from_guest(report,output/'samples.json',timeout=70)
    raw=(output/'samples.json').read_bytes()
    if len(raw)>8000000: raise ValueError('report too large')
    data=json.loads(raw.decode('utf-8-sig'))
    observation=validate_report(data,pid=pid,ticks=ticks)
    name=candidate_name(observation,pid=pid,ticks=ticks)
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'gameProcessId':pid,'gameProcessStartUtcTicks':ticks,'gameSha256':GAME_SHA,'readerExecutableSha256':READER_SHA,'guestReaderReused':identity['installed'],'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'targetStatus':observation['status'],'targetKey':observation['targetKey'],'targetEntity':observation['targetEntity'],'templateKey':observation['templateKey'],'localizationKey':observation.get('localizationKey'),'qualification':observation['qualification'],**name,'acquisitionDurationMilliseconds':(datetime.fromisoformat(observation['completedAtUtc'].replace('Z','+00:00'))-datetime.fromisoformat(observation['startedAtUtc'].replace('Z','+00:00'))).total_seconds()*1000}
    with (output/'summary.json').open('x',encoding='utf-8') as f: json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--lab',choices=('lab1','lab2'),required=True);args=parser.parse_args()
    try: print(json.dumps(run(args.lab)),flush=True)
    except (ValueError,OSError,RuntimeError) as exc: print(json.dumps({'status':'blocked','reason':str(exc)[:160]}),flush=True);raise SystemExit(2) from None
