"""Capture a guarded selected-target vitals candidate without game input."""
import argparse, base64, hashlib, json, math, sys, uuid
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
READER_SHA = '5843EF6E58EA0E43CB3C08732934561476D3E726FF367E3C2DAC9B6BF19CD803'
READER = ROOT / 'artifacts/native-target-context-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-selected-target-20261107/runs'

QUALIFICATION='candidate-only; target and vitals semantics, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v,low,high): return type(v) is int and low<=v<=high
    def invalid(): raise ValueError('invalid selected-target report')
    if not isinstance(report,dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion']!=1 or report.get('contractVersion')!='native-current-selected-target-candidate-sample/1' or report.get('status')!='complete' or report.get('qualification')!=QUALIFICATION: invalid()
    o=report.get('observation')
    if not isinstance(o,dict) or o.get('qualification')!=QUALIFICATION: invalid()
    identity=o.get('identity')
    if not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get('processId')) is not int or identity['processId']!=pid or type(identity.get('processStartUtcTicks')) is not int or identity['processStartUtcTicks']!=ticks or identity.get('executableSha256')!=GAME_SHA: invalid()
    def interval(value):
        try: start=datetime.fromisoformat(value['startedAtUtc'].replace('Z','+00:00')); end=datetime.fromisoformat(value['completedAtUtc'].replace('Z','+00:00'))
        except (KeyError,AttributeError,TypeError,ValueError): invalid()
        if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
        return start,end
    outer_start,outer_end=interval(o)
    if not integer(o.get('selfKey'),1,2**64-1): invalid()
    status=o.get('status'); before=o.get('beforeGuardStatus'); after=o.get('afterGuardStatus')
    key=o.get('targetKey'); unit=o.get('targetUnitId'); entity=o.get('targetEntity'); vitals=o.get('targetVitals')
    if status=='unavailable':
        if before not in ('raw-getter-zero-candidate','override-unavailable','guard-unreadable-or-invalid') or any(x is not None for x in (after,key,unit,entity,vitals,o.get('targetPosition'),o.get('targetContext'))): invalid()
    elif status=='candidate':
        if before!='fallback-key-candidate' or after!='fallback-key-candidate' or not integer(key,1,2**64-1) or unit!=f'u{key:016X}' or not integer(entity,0x10000,0x7fffffffffff) or not isinstance(vitals,dict) or vitals.get('identity')!=identity or type(vitals.get('unitKey')) is not int or vitals['unitKey']!=key: invalid()
        if not isinstance(o.get('nameSeed'),dict): invalid()
        context=o.get('targetContext')
        if not isinstance(context,dict) or context.get('qualification')!='typed owner raw inputs; target level presentation, combat semantics and freshness unverified': invalid()
        owner=context.get('owner'); level=context.get('rawLevel'); combat=context.get('rawCombat'); combat_bool=context.get('combatCandidate'); ctx_status=context.get('status')
        if ctx_status=='raw-typed-candidate':
            if not integer(owner,0x10000,0x7fffffffffff) or not integer(level,-2**31,2**31-1) or not integer(combat,0,255) or type(combat_bool) is not bool or combat_bool!=(combat!=0): invalid()
        elif ctx_status=='unverified-type':
            if not integer(owner,0x10000,0x7fffffffffff) or any(x is not None for x in (level,combat,combat_bool)): invalid()
        elif ctx_status in ('owner-unavailable','owner-or-fields-unavailable'):
            if any(x is not None for x in (owner,level,combat,combat_bool)): invalid()
        else: invalid()
        position=o.get('targetPosition')
        if not isinstance(position,dict) or type(position.get('unitKey')) is not int or position['unitKey']!=key or position.get('qualification')!='cached position candidate; freshness and target semantics unverified': invalid()
        if position.get('status')=='component-unavailable':
            if any(position.get(k) is not None for k in ('componentAddress','startedAtUtc','completedAtUtc','position')): invalid()
        elif position.get('status')=='candidate':
            if not integer(position.get('componentAddress'),0x10000,0x7fffffffffff): invalid()
            pstart,pend=interval(position)
            if pstart<outer_start or pend>outer_end: invalid()
            xyz=position.get('position')
            if not isinstance(xyz,dict) or any(type(xyz.get(k)) not in (int,float) or not math.isfinite(xyz[k]) for k in ('x','y','z')): invalid()
        else: invalid()
        start,end=interval(vitals)
        if start<outer_start or end>outer_end or vitals.get('qualification')!='candidate-only; semantics/passive-freshness/restart-unverified': invalid()
        for name in ('health','energy','mana'):
            field=vitals.get(name)
            if not isinstance(field,dict): invalid()
            current=field.get('current'); maximum=field.get('maximum'); reason=field.get('unavailableReason')
            if field.get('status')=='calculated-candidate':
                if not integer(current,-2**63,2**63-1) or not integer(maximum,-2**63,2**63-1) or reason is not None: invalid()
            elif field.get('status')=='unavailable':
                if current is not None or maximum is not None or not isinstance(reason,str) or not reason: invalid()
            else: invalid()
    else: invalid()
    return o

def derive_name(observation, *, pid, ticks):
    qualifier='base name/locale1 candidate; API decoration/language unverified'
    result={'baseNameLocale1Candidate':None,'nameQualification':qualifier,'nameUnavailableReason':None}
    if observation['status'] != 'candidate':
        result['nameUnavailableReason']='target-unavailable'; return result
    seed=observation['nameSeed']; status=seed.get('status'); branch=seed.get('branch')
    allowed={'direct':('raw-candidate','empty'), 'alternate':('raw-candidate','empty-unresolved-fallback'), 'localized':('raw-candidate',), 'entity-virtual':('unresolved',), 'name-read-or-type-failure':('unavailable',)}
    if branch not in allowed or status not in allowed[branch]:
        result['nameUnavailableReason']='invalid-name-seed'; return result
    if branch in ('direct','alternate'):
        name=seed.get('rawDirect')
        if status=='raw-candidate' and isinstance(name,str) and name:
            result['baseNameLocale1Candidate']=name
        else: result['nameUnavailableReason']='empty-or-invalid-direct-name'
        return result
    if branch != 'localized':
        result['nameUnavailableReason']=status; return result
    key=seed.get('localizationKey'); dictionary=seed.get('dictionary')
    if type(key) is not int or not 0<key<=0xffffffff or not isinstance(dictionary,dict):
        result['nameUnavailableReason']='localization-key-or-dictionary-unavailable'; return result
    try:
        if dictionary.get('identity') != observation['identity']: raise ValueError('dictionary-identity-mismatch')
        wrapper={'schemaVersion':1,'contractVersion':'native-current-localization-dictionary-candidate-sample/1','status':'complete','observation':dictionary}
        validate_dictionary(wrapper,pid=pid,ticks=ticks,keys=[key])
        row=dictionary['rows'][0]
        if row['status']!='raw-candidate': raise ValueError('dictionary-'+row['status'])
        frequencies=base64.b64decode(dictionary['frequencyBytesBase64'],validate=True)
        compressed=base64.b64decode(row['compressedBytesBase64'],validate=True)
        decoded,_=decode_localization_huffman(frequencies,compressed,row['decodedSize'])
        name=parse_localization_record(decoded)['candidate_text']
        if not name: raise ValueError('empty-candidate-text')
        result['baseNameLocale1Candidate']=name
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        result['nameUnavailableReason']='name-decode-unavailable: '+str(exc)[:100]
    return result

def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117495648 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-target-context-' + READER_SHA[:16]
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
            "& $exe sample-current-selected-target --pid "+str(pid)+" --start-ticks "+str(ticks)+" --include-name-seed true --include-position true --include-context true --output $out | Out-Null;"
            "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};if((Get-Item -LiteralPath $out).Length -gt 8000000){throw 'native-report-too-large'}")
        guest.powershell(launch,timeout=130);guest.copy_from_guest(report,output/'samples.json',timeout=70)
    raw=(output/'samples.json').read_bytes()
    if len(raw)>8000000: raise ValueError('report too large')
    data=json.loads(raw.decode('utf-8-sig')); observation=validate_report(data,pid=pid,ticks=ticks)
    name=derive_name(observation,pid=pid,ticks=ticks)
    summary={'status':'candidate-only','lab':lab,'vmIdentity':vm,'gameProcessId':pid,'gameProcessStartUtcTicks':ticks,'gameSha256':GAME_SHA,'readerExecutableSha256':READER_SHA,'guestReaderReused':identity['installed'],'sourceReport':str(output/'samples.json'),'sourceReportSha256':hashlib.sha256(raw).hexdigest().upper(),'targetStatus':observation['status'],'qualification':observation['qualification'],'targetPosition':observation.get('targetPosition'),'targetContext':observation.get('targetContext'),**name}
    with (output/'summary.json').open('x',encoding='utf-8') as f: json.dump(summary,f,indent=2)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--lab',choices=('lab1','lab2'),required=True);args=parser.parse_args()
    try: print(json.dumps(run(args.lab)),flush=True)
    except (ValueError,OSError,RuntimeError) as exc: print(json.dumps({'status':'blocked','reason':str(exc)[:160]}),flush=True);raise SystemExit(2) from None
