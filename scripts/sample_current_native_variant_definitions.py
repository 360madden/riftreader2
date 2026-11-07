"""Recheck parent variant references and capture their candidate definitions."""
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
from scripts.native_localization_huffman import decode_localization_huffman
from scripts.native_localization_record import parse_localization_record


def run(lab,catalog):
    if lab not in ('lab1','lab2'): raise ValueError('invalid-lab')
    catalog=Path(catalog)
    if not catalog.is_absolute() or not catalog.is_file() or catalog.is_symlink() or catalog.stat().st_size>8000000: raise ValueError('invalid-catalog-path')
    raw=catalog.read_bytes(); catalog_sha=sha(raw); source=json.loads(raw.decode('utf-8-sig'))
    if source.get('readerSha256') not in (READER_SHA,'B56216935082462AF9B381EC37C84D83E74B35FBE97BAD515ADCB63DA8C39D62') or not isinstance(source.get('identity'),dict) or not isinstance(source.get('vmIdentity'),dict) or not isinstance(source.get('records'),list): raise ValueError('invalid-source-catalog')
    parents=[]; seen=set(); lookup=[]
    for row in source['records']:
        if not isinstance(row,dict) or type(row.get('key')) is not int or row['key'] in seen: raise ValueError('invalid-parent-keys')
        seen.add(row['key']); vector=row.get('rawVariants')
        if not isinstance(vector,dict) or vector.get('status')!='raw-candidates': continue
        entries=vector.get('entries')
        if not isinstance(entries,list) or len(entries)>64: raise ValueError('invalid-parent-vector')
        parents.append({'key':row['key'],'rawVariants':vector})
        for item in entries:
            if not isinstance(item,dict): raise ValueError('invalid-variant-entry')
            if item.get('status')=='type-0061-raw-candidate':
                key=item.get('key')
                if type(key) is not int or not 0<=key<=0xffffffff: raise ValueError('invalid-variant-key')
                if key not in lookup: lookup.append(key)
    if not parents or not lookup: raise ValueError('no-typed-variant-references')
    if len(parents)>512 or len(lookup)>4096: raise ValueError('variant-budget-exceeded')
    sources=[Path(__file__),ROOT/'scripts/sample_current_native_ability_catalog.py',ROOT/'scripts/sample_current_native_ability_records.py',ROOT/'scripts/probe_native_unit_manager.py',ROOT/'scripts/native_localization_huffman.py',ROOT/'scripts/native_localization_record.py']
    pins={str(p):sha(p.read_bytes()) for p in sources}
    if READER.is_symlink() or not READER.is_file() or READER.stat().st_size!=117520224 or sha(READER.read_bytes())!=READER_SHA: raise ValueError('reader-mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root/'.doctor'))
    if vm!=source['vmIdentity']: raise ValueError('source-vm-identity-changed')
    token=uuid.uuid4().hex; folder=ROOT/'artifacts/native-variant-definitions-20261107/runs'/lab/token;folder.mkdir(parents=True,exist_ok=False)
    cache=settings['guestRoot']+r'\current-variant-guards-'+READER_SHA[:16]; reader=cache+r'\RiftReader2.Live.exe';prefix=settings['guestRoot']+r'\variant-'+token
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
        if identity!=source['identity']: raise ValueError('source-game-identity-changed')
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
        parentkeys=[p['key'] for p in parents]
        def check_parents(reports):
            rows={r['key']:r for _,o in reports for r in o['records']}
            if any(rows[p['key']]['rawVariants']!=p['rawVariants'] for p in parents): raise ValueError('parent-variant-vector-changed')
        before=chunks('parents-before','sample-current-ability-records',parentkeys);check_parents(before)
        variants=chunks('variants','sample-current-ability-records',lookup)
        names=[]
        for _,o in variants:
            for r in o['records']:
                c=r.get('child') or {};k=c.get('localizationKey') if c.get('status')=='type-verified-candidate' else None
                if k and k not in names:names.append(k)
        dictionaries=chunks('dictionary','sample-current-localization-dictionary',names) if names else []
        after=chunks('parents-after','sample-current-ability-records',parentkeys);check_parents(after)
        final,final_target=inspect('inspect-after')
        if final!=identity or final_target!=target: raise ValueError('process-epoch-changed')
        if sha(catalog.read_bytes())!=catalog_sha or any(sha(p.read_bytes())!=pins[str(p)] for p in sources) or sha(READER.read_bytes())!=READER_SHA: raise ValueError('source-or-reader-changed')
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
                definitions.append({'key':row['key'],'recordSource':name,'record':row,'nameKey':k,'name':byname.get(k)})
        observations=before+variants+dictionaries+after
        result={'status':'candidate-only','qualification':'possible variant references and definitions; selected and learned semantics unverified','identity':identity,'vmIdentity':vm,'sourceCatalog':str(catalog),'sourceCatalogSha256':catalog_sha,'readerSha256':READER_SHA,'sourceSha256':pins,'evidence':evidence,'parents':parents,'definitions':definitions,'observationIntervals':[{'source':n,'startedAtUtc':o['startedAtUtc'],'completedAtUtc':o['completedAtUtc']} for n,o in observations],'limitations':['Sequential chunk captures and repeated anchors are not atomic and cannot exclude ABA.','Cache misses do not establish absence; no winner or learned status is selected.']}
        with (folder/'summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
        return {'status':'candidate-only','summaryPath':str(folder/'summary.json'),'parentCount':len(parents),'lookupCount':len(lookup)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lab',required=True,choices=('lab1','lab2'));p.add_argument('--catalog',required=True);a=p.parse_args()
    print(json.dumps(run(a.lab,a.catalog)),flush=True)
