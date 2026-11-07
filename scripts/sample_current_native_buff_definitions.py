"""Recheck raw buff-list seeds and capture their ability-definition candidates."""
import argparse
import base64
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.probe_native_unit_manager import inspection_identity,sha
from scripts.sample_current_native_ability_catalog import (READER,READER_SHA,build_launch,validate_record_costs_timing,validate_dictionary)
from scripts.sample_current_native_buff_seeds import validate_report as validate_seeds
from scripts.sample_current_native_buff_seeds import READER as SEED_READER, READER_SHA as SEED_SHA
from scripts.native_localization_huffman import decode_localization_huffman
from scripts.native_localization_record import parse_localization_record


def run(lab,seed):
    if lab not in ('lab1','lab2'): raise ValueError('invalid-lab')
    catalog=Path(seed)
    if not catalog.is_absolute() or not catalog.is_file() or catalog.is_symlink() or catalog.stat().st_size>8000000: raise ValueError('invalid-catalog-path')
    raw=catalog.read_bytes(); catalog_sha=sha(raw); source=json.loads(raw.decode('utf-8-sig'))
    if source.get('readerExecutableSha256')!=SEED_SHA or not isinstance(source.get('observation'),dict) or not isinstance(source.get('vmIdentity'),dict): raise ValueError('invalid-seed-summary')
    source_obs=source['observation']; identity=source_obs.get('identity') or {}
    pid=identity.get('processId');ticks=identity.get('processStartUtcTicks')
    validate_seeds({'schemaVersion':1,'contractVersion':'native-current-buff-seeds-candidate/1','status':'complete','observation':source_obs},pid=pid,ticks=ticks)
    lookup=[]
    for node in source_obs['nodes']:
        raw_object=node['rawObject']; key=raw_object.get('dword3C') if raw_object.get('status')=='raw-candidate' else None
        if key is not None and key not in lookup: lookup.append(key)
    if not lookup: raise ValueError('no-raw-definition-keys')
    sources=[Path(__file__),ROOT/'scripts/sample_current_native_ability_catalog.py',ROOT/'scripts/sample_current_native_ability_records.py',ROOT/'scripts/probe_native_unit_manager.py',ROOT/'scripts/native_localization_huffman.py',ROOT/'scripts/native_localization_record.py',ROOT/'scripts/sample_current_native_buff_seeds.py']
    pins={str(p):sha(p.read_bytes()) for p in sources}
    if READER.is_symlink() or not READER.is_file() or READER.stat().st_size!=117537120 or sha(READER.read_bytes())!=READER_SHA or sha(SEED_READER.read_bytes())!=SEED_SHA: raise ValueError('reader-mismatch')
    if SEED_READER.is_symlink() or not SEED_READER.is_file() or SEED_READER.stat().st_size!=117544800 or sha(SEED_READER.read_bytes())!=SEED_SHA: raise ValueError('seed-reader-mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root/'.doctor'))
    if vm!=source['vmIdentity']: raise ValueError('source-vm-identity-changed')
    token=uuid.uuid4().hex; folder=ROOT/'artifacts/native-buff-definitions-20261107/runs'/lab/token;folder.mkdir(parents=True,exist_ok=False)
    cache=settings['guestRoot']+r'\current-variant-restrictions-'+READER_SHA[:16]; reader=cache+r'\RiftReader2.Live.exe';prefix=settings['guestRoot']+r'\buffdefs-'+token
    evidence={}
    with api._session(config,settings,vm,folder) as guest:
        guest.powershell("$ErrorActionPreference='Stop';[IO.Directory]::CreateDirectory("+ps_literal(cache)+")|Out-Null;$e="+ps_literal(reader)+";if((Test-Path -LiteralPath $e) -and (Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'reader-hash-collision'}",timeout=60)
        marker=prefix+'-installed.json'
        guest.powershell("$p="+ps_literal(marker)+";$b=[Text.Encoding]::UTF8.GetBytes((Test-Path -LiteralPath "+ps_literal(reader)+" -PathType Leaf).ToString());$f=[IO.File]::Open($p,[IO.FileMode]::CreateNew);try{$f.Write($b,0,$b.Length)}finally{$f.Dispose()}",timeout=60)
        local=folder/'installed.txt';guest.copy_from_guest(marker,local,timeout=60);state=local.read_text().strip()
        if state not in ('True','False'): raise ValueError('invalid-cache-state')
        if state=='False': guest.run('copyFileFromHostToGuest',str(READER),reader,timeout=180)
        def inspect(name):
            output=prefix+'-'+name+'.json';local=folder/(name+'.json')
            command="$ErrorActionPreference='Stop';$e="+ps_literal(reader)+";if((Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'reader-sha-mismatch'};if(Test-Path -LiteralPath "+ps_literal(output)+"){throw 'output-exists'};& $e inspect-native --output "+ps_literal(output)+" | Out-Null;if($LASTEXITCODE -ne 0){throw 'inspect-failed'}"
            guest.powershell(command,timeout=90);guest.copy_from_guest(output,local,timeout=60);data=local.read_bytes();evidence[local.name]=sha(data);return inspection_identity(json.loads(data.decode('utf-8-sig')))
        identity,target=inspect('inspect-before')
        if identity!=source_obs['identity']: raise ValueError('source-game-identity-changed')
        pid=target['processId'];ticks=target['processStartUtcTicks']
        def capture(name,mode,keys):
            payload=','.join(str(k) for k in keys).encode('ascii');keysha=sha(payload);file=folder/(name+'-keys.txt')
            with file.open('xb') as f:f.write(payload)
            guest_key=cache+'\\'+name+'-keys-'+token+'.txt';guest_report=cache+'\\'+name+'-'+token+'.json'
            guest.powershell('if(Test-Path -LiteralPath '+ps_literal(guest_key)+"){throw 'keys-exist'}",timeout=30)
            guest.run('copyFileFromHostToGuest',str(file),guest_key,timeout=60)
            command=build_launch(reader,guest_key,guest_report,pid,ticks,keysha,mode)
            if len(base64.b64encode(command.encode('utf-16le')))>4096: raise ValueError('guest-command-too-large')
            guest.powershell(command,timeout=130);dest=folder/(name+'.json');guest.copy_from_guest(guest_report,dest,timeout=70)
            with dest.open('rb') as f:data=f.read(1000001)
            if len(data)>1000000: raise ValueError('report-too-large')
            report=json.loads(data.decode('utf-8-sig'));validator=validate_record_costs_timing if mode=='sample-current-ability-records' else validate_dictionary
            validator(report,pid=pid,ticks=ticks,keys=keys)
            if report['observation']['identity']!=identity: raise ValueError('capture-identity-mismatch')
            evidence[file.name]=keysha;evidence[dest.name]=sha(data)
            return report['observation']
        def chunks(prefix_name,mode,keys):
            result=[]
            for offset in range(0,len(keys),128):
                name=prefix_name+'-'+str(offset//128+1);obs=capture(name,mode,keys[offset:offset+128]);result.append((name,obs))
            return result
        seed_cache=settings['guestRoot']+r'\current-buff-seeds-'+SEED_SHA[:16]; seed_reader=seed_cache+r'\RiftReader2.Live.exe'
        guest.powershell("$ErrorActionPreference='Stop';[IO.Directory]::CreateDirectory("+ps_literal(seed_cache)+")|Out-Null;$e="+ps_literal(seed_reader)+";if((Test-Path -LiteralPath $e) -and (Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(SEED_SHA)+"){throw 'seed-reader-hash-collision'}",timeout=60)
        seed_marker=prefix+'-seed-installed.txt'; local_seed_marker=folder/'seed-installed.txt'
        guest.powershell("$p="+ps_literal(seed_marker)+";$b=[Text.Encoding]::UTF8.GetBytes((Test-Path -LiteralPath "+ps_literal(seed_reader)+" -PathType Leaf).ToString());$f=[IO.File]::Open($p,[IO.FileMode]::CreateNew);try{$f.Write($b,0,$b.Length)}finally{$f.Dispose()}",timeout=60)
        guest.copy_from_guest(seed_marker,local_seed_marker,timeout=60);seed_state=local_seed_marker.read_text().strip()
        if seed_state not in ('True','False'): raise ValueError('invalid-seed-reader-cache-state')
        if seed_state=='False': guest.run('copyFileFromHostToGuest',str(SEED_READER),seed_reader,timeout=180)
        def capture_seeds(name):
            output=prefix+'-'+name+'.json';local=folder/(name+'.json')
            command="$ErrorActionPreference='Stop';$e="+ps_literal(seed_reader)+";if((Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(SEED_SHA)+"){throw 'seed-reader-sha-mismatch'};if(Test-Path -LiteralPath "+ps_literal(output)+"){throw 'output-exists'};& $e sample-current-buff-seeds --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output "+ps_literal(output)+" | Out-Null;if($LASTEXITCODE -ne 0){throw 'seed-failed'};if((Get-Item -LiteralPath "+ps_literal(output)+").Length -gt 1000000){throw 'seed-report-too-large'}"
            guest.powershell(command,timeout=90);guest.copy_from_guest(output,local,timeout=60)
            with local.open('rb') as f:raw=f.read(1000001)
            if len(raw)>1000000: raise ValueError('seed-report-too-large')
            evidence[local.name]=sha(raw);report=json.loads(raw.decode('utf-8-sig'));obs=validate_seeds(report,pid=pid,ticks=ticks)
            if any(obs.get(k)!=source_obs.get(k) for k in ('identity','unitKey','context','sentinel','nodes')): raise ValueError('seed-list-changed')
            return obs
        before=capture_seeds('seeds-before')
        variants=chunks('variants','sample-current-ability-records',lookup)
        names=[]
        for _,o in variants:
            for r in o['records']:
                c=r.get('child') or {};k=c.get('localizationKey') if c.get('status')=='type-verified-candidate' else None
                if k and k not in names:names.append(k)
        dictionaries=chunks('dictionary','sample-current-localization-dictionary',names) if names else []
        after=capture_seeds('seeds-after')
        final,final_target=inspect('inspect-after')
        if final!=identity or final_target!=target: raise ValueError('process-epoch-changed')
        if sha(catalog.read_bytes())!=catalog_sha or any(sha(p.read_bytes())!=pins[str(p)] for p in sources) or sha(READER.read_bytes())!=READER_SHA or sha(SEED_READER.read_bytes())!=SEED_SHA: raise ValueError('source-or-reader-changed')
        byname={}
        for name,o in dictionaries:
            frequencies=base64.b64decode(o['frequencyBytesBase64'],validate=True)
            for row in o['rows']:
                value=None;reason='dictionary-'+row['status']
                if row['status']=='raw-candidate':
                    try:
                        decoded,_=decode_localization_huffman(frequencies,base64.b64decode(row['compressedBytesBase64'],validate=True),row['decodedSize'])
                        value=parse_localization_record(decoded)['candidate_text'] or None;reason=None if value else 'empty-candidate-text'
                    except (ValueError,KeyError,TypeError) as exc: reason='decode-unavailable: '+str(exc)[:100]
                byname[row['key']]={'candidate':value,'reason':reason,'source':name}
        definitions=[]
        for name,o in variants:
            for row in o['records']:
                c=row.get('child') or {};k=c.get('localizationKey') if c.get('status')=='type-verified-candidate' else None
                name_info=byname.get(k) or {'candidate':None,'reason':'unverified-or-missing-name-child','source':None}
                definitions.append({'key':row['key'],'recordSource':name,'record':row,'nameKey':k,'abilityDefinitionNameCandidate':name_info['candidate'],'nameUnavailableReason':name_info['reason'],'dictionarySource':name_info['source']})
        observations=[('seeds-before',before)]+variants+dictionaries+[('seeds-after',after)]
        result={'status':'candidate-only','qualification':'raw buff nodes and ability-definition name candidates; API selected buff names unverified','identity':identity,'vmIdentity':vm,'sourceSeed':str(catalog),'sourceSeedSha256':catalog_sha,'seedReaderSha256':SEED_SHA,'readerSha256':READER_SHA,'sourceSha256':pins,'evidence':evidence,'nodes':source_obs['nodes'],'definitions':definitions,'observationIntervals':[{'source':n,'startedAtUtc':o['startedAtUtc'],'completedAtUtc':o['completedAtUtc']} for n,o in observations],'limitations':['Sequential chunk captures and repeated anchors are not atomic and cannot exclude ABA.','Cache misses do not establish absence; no winner or learned status is selected.']}
        with (folder/'summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
        return {'status':'candidate-only','summaryPath':str(folder/'summary.json'),'nodeCount':len(source_obs['nodes']),'lookupCount':len(lookup)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lab',required=True,choices=('lab1','lab2'));p.add_argument('--seed',required=True);a=p.parse_args()
    print(json.dumps(run(a.lab,a.seed)),flush=True)
