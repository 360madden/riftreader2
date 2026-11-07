"""Capture a same-process, non-atomic candidate ability catalog without game input."""
import argparse
import base64
import hashlib
import json
import math
import re
import struct
from datetime import datetime
from pathlib import Path
import ntpath
import binascii
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.probe_native_unit_manager import inspection_identity, encoded, sha
from scripts.sample_current_native_ability_maps import GAME_SHA, validate_report as validate_maps
from scripts.sample_current_native_ability_records import validate_report as validate_records
from scripts.native_localization_huffman import decode_localization_huffman
from scripts.native_localization_record import parse_localization_record

READER = ROOT / 'artifacts/native-variant-guards-20261107/publish/RiftReader2.Live.exe'
READER_SHA = '3239D8FE72077051AC19781847D703E702D29CEF29A2001A8CA910A1DD60247E'

DICTIONARY_QUALIFICATION = 'candidate-only; framing, freshness and restart unverified'

def validate_record_costs_timing(report, *, pid, ticks, keys):
    validate_records(report, pid=pid, ticks=ticks, keys=keys)
    for row in report['observation']['records']:
        if row['status'] != 'type-verified-candidate':
            if row.get('rawRange') is not None or row.get('rawVariants') is not None or row.get('requiredLevelRaw') is not None: raise ValueError('unexpected-raw-fields')
            continue
        required_level=row.get('requiredLevelRaw')
        if type(required_level) is not int or not -2**31<=required_level<=2**31-1: raise ValueError('invalid-required-level')
        costs=row.get('rawCosts'); timing=row.get('rawTiming')
        variants=row.get('rawVariants')
        if not isinstance(variants,dict): raise ValueError('invalid-raw-variants')
        variant_status=variants.get('status'); source=variants.get('sourceAddress'); entries=variants.get('entries')
        def pointer(v): return type(v) is int and 0x10000<=v<=0x7fffffffffff
        if variant_status in ('primary-empty','primary-null'):
            if source is not None or entries is not None: raise ValueError('invalid-primary-variants')
        elif variant_status=='primary-unverified-type':
            if not pointer(source) or entries is not None: raise ValueError('invalid-primary-variants')
        elif variant_status in ('empty','raw-candidates'):
            if not pointer(source) or not isinstance(entries,list) or len(entries)>64 or ((variant_status=='empty') != (len(entries)==0)): raise ValueError('invalid-variant-vector')
            for entry in entries:
                if not isinstance(entry,dict): raise ValueError('invalid-variant-entry')
                status=entry.get('status'); address=entry.get('address'); vt=entry.get('vtable'); getter=entry.get('getterRva'); key=entry.get('key')
                if status=='null':
                    if type(address) is not int or address!=0 or any(v is not None for v in (vt,getter,key)): raise ValueError('invalid-null-variant')
                elif status in ('unknown-type','unverified-type','type-0061-raw-candidate'):
                    if not pointer(address) or type(vt) is not int or not 0<=vt<=2**64-1 or (getter is not None and (type(getter) is not int or not 0<=getter<=2**64-1)): raise ValueError('invalid-variant-type')
                    if status=='type-0061-raw-candidate':
                        if type(key) is not int or not 0<=key<=0xffffffff: raise ValueError('invalid-variant-key')
                    elif key is not None: raise ValueError('unverified-variant-key')
                else: raise ValueError('invalid-variant-status')
        else: raise ValueError('invalid-variant-status')
        raw_range=row.get('rawRange')
        if not isinstance(raw_range,dict) or raw_range.get('qualification') != 'raw definition inputs; adjusted range and usability unverified': raise ValueError('invalid-raw-range')
        for raw_name,number_name in (('baseMinRawHex','baseMin'),('baseMaxRawHex','baseMax')):
            text=raw_range.get(raw_name); value=raw_range.get(number_name)
            if not isinstance(text,str) or re.fullmatch(r'[0-9a-fA-F]{8}',text) is None: raise ValueError('invalid-raw-range-scalar')
            raw=bytes.fromhex(text); number=struct.unpack('<f',raw)[0]
            if math.isfinite(number):
                if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>3.4028234663852886e38 or struct.pack('<f',value)!=raw: raise ValueError('invalid-raw-range-scalar')
            elif value is not None: raise ValueError('invalid-raw-range-scalar')
        begin=raw_range.get('conditionsBegin'); end=raw_range.get('conditionsEnd'); conditions=raw_range.get('conditions'); stealth=raw_range.get('stealthRequiredCandidate')
        if type(begin) is not int or type(end) is not int or not isinstance(conditions,list) or len(conditions)>64 or any(type(v) is not int or not 0<=v<=0xffffffff for v in conditions) or type(stealth) is not bool or stealth != (1 in conditions) or (begin==0)!=(end==0) or end<begin or end-begin != 4*len(conditions) or (begin!=0 and (begin<0x10000 or begin%4 or end>0x7fffffffffff)): raise ValueError('invalid-raw-range-conditions')
        if not isinstance(costs,dict) or costs.get('status') not in ('empty','raw-candidates') or not isinstance(costs.get('children'),list) or len(costs['children'])>64 or ((costs['status']=='empty') != (len(costs['children'])==0)): raise ValueError('invalid-raw-costs')
        for cost in costs['children']:
            if not isinstance(cost,dict) or cost.get('status') not in ('null','unknown-type','unverified-type','power-raw-candidate','mana-raw-candidate','energy-raw-candidate','mana-charge-raw-candidate','typed-unhandled-1e2d'): raise ValueError('invalid-raw-cost-child')
        if not isinstance(timing,dict) or type(timing.get('rawGate88')) is not int or type(timing.get('baseCooldownMilliseconds')) is not int: raise ValueError('invalid-raw-timing')
        for span in (timing.get('primary'),timing.get('secondary')):
            if not isinstance(span,dict) or span.get('status') not in ('empty','not-single','null-child','unknown-type','unverified-type','type-0650-raw-candidate','type-0678-raw-candidate','typed-0759-fixed-input','typed-0648-zero-path') or type(span.get('count')) is not int or not 0<=span['count']<=64: raise ValueError('invalid-raw-timing-span')

def validate_dictionary(report, *, pid, ticks, keys):
    def integer(x, low=0, high=2**64-1): return type(x) is int and low <= x <= high
    def invalid(): raise ValueError("native-dictionary-report-invalid")
    if (not isinstance(report,dict) or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1 or report.get("contractVersion") != "native-current-localization-dictionary-candidate-sample/1" or report.get("status") != "complete"): invalid()
    o=report.get("observation")
    if not isinstance(o,dict) or o.get("qualification") != DICTIONARY_QUALIFICATION: invalid()
    identity=o.get("identity")
    if (not isinstance(identity,dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(identity.get("processId")) is not int or identity["processId"]!=pid or type(identity.get("processStartUtcTicks")) is not int or identity["processStartUtcTicks"]!=ticks or identity.get("executableSha256")!=GAME_SHA): invalid()
    try:
        start=datetime.fromisoformat(o["startedAtUtc"].replace("Z","+00:00")); end=datetime.fromisoformat(o["completedAtUtc"].replace("Z","+00:00"))
    except (KeyError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start: invalid()
    for key in ("manager","wrapper","inner","dictionary"):
        if not integer(o.get(key),1): invalid()
    if not integer(o.get("bucketBase")) or not integer(o.get("bucketCount"),0,1048576) or not integer(o.get("entryCount")) or not integer(o.get("blobAddress")) or not integer(o.get("blobSize"),0,0xffffffff): invalid()
    try:
        freq=base64.b64decode(o["frequencyBytesBase64"],validate=True)
    except (KeyError,ValueError,TypeError,binascii.Error): invalid()
    if len(freq)!=1024: invalid()
    rows=o.get("rows")
    if not isinstance(rows,list) or len(rows)!=len(keys): invalid()
    for row,key in zip(rows,keys):
        if not isinstance(row,dict) or type(row.get("key")) is not int or row["key"]!=key: invalid()
        if row.get("status")=="cache-miss":
            if any(row.get(k) is not None for k in ("nodeAddress","offset","apparentInputLength","decodedSize","compressedBytesBase64")): invalid()
        elif row.get("status")=="raw-candidate":
            if not integer(row.get("nodeAddress"),1) or not integer(row.get("offset"),0,0xffffffff) or row["offset"]>=o["blobSize"] or not integer(row.get("apparentInputLength"),0,4096) or not integer(row.get("decodedSize"),0,65535): invalid()
            try: raw=base64.b64decode(row["compressedBytesBase64"],validate=True)
            except (KeyError,ValueError,TypeError,binascii.Error): invalid()
            if len(raw)!=row["apparentInputLength"]: invalid()
        else: invalid()
    return {"rowCount":len(rows),"rawCandidateCount":sum(r["status"]=="raw-candidate" for r in rows),"acquisitionDurationMilliseconds":(end-start).total_seconds()*1000,"qualification":DICTIONARY_QUALIFICATION}


def build_launch(guest_exe, guest_keys, guest_report, pid, ticks, key_sha, mode):
    if mode not in ('sample-current-ability-records', 'sample-current-localization-dictionary'): raise ValueError('invalid-mode')
    folder = ntpath.dirname(guest_exe)
    if not folder or any(ntpath.dirname(path).lower() != folder.lower() for path in (guest_keys, guest_report)):
        raise ValueError("guest-paths-must-share-directory")
    return (
        "$ErrorActionPreference='Stop';"
        "$d=" + ps_literal(folder) + ";"
        "$exe=$d+" + ps_literal("\\" + ntpath.basename(guest_exe)) + ";"
        "if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -cne "
        + ps_literal(READER_SHA) + "){throw 'guest-reader-sha-mismatch'};"
        "$g=Get-Process -Id " + str(pid) + " -ErrorAction Stop;"
        "if($g.ProcessName -cne 'rift_x64' -or "
        "[long]$g.StartTime.ToUniversalTime().Ticks -ne " + str(ticks)
        + "){throw 'game-epoch-changed'};"
        "if((Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash -cne "
        + ps_literal(GAME_SHA) + "){throw 'rift-build-changed'};"
        "$keyfile=$d+" + ps_literal("\\" + ntpath.basename(guest_keys)) + ";"
        "if((Get-FileHash -LiteralPath $keyfile -Algorithm SHA256).Hash -cne " + ps_literal(key_sha) + "){throw 'guest-keys-sha-mismatch'};"
        "$keys=[IO.File]::ReadAllText($keyfile);"
        "$out=$d+" + ps_literal("\\" + ntpath.basename(guest_report)) + ";"
        "if(Test-Path -LiteralPath $out){throw 'guest-report-exists'};"
        "& $exe " + mode + " --pid " + str(pid) + " --start-ticks " + str(ticks)
        + (" --keys $keys --include-costs true --include-timing true --include-range true --include-variants true --output $out | Out-Null;" if mode == "sample-current-ability-records" else " --keys $keys --output $out | Out-Null;")
        + "if($LASTEXITCODE -ne 0){throw 'native-sampler-failed'};"
        "if(!(Test-Path -LiteralPath $out)){throw 'native-report-missing'};"
        "if((Get-Item -LiteralPath $out).Length -gt 1000000){throw 'native-report-too-large'}"
        )


def run(lab):
    if lab not in ('lab1', 'lab2'): raise ValueError('invalid-lab')
    sources=[Path(__file__), ROOT/'scripts/sample_current_native_ability_maps.py', ROOT/'scripts/sample_current_native_ability_records.py', ROOT/'scripts/probe_native_unit_manager.py', ROOT/'scripts/native_localization_huffman.py', ROOT/'scripts/native_localization_record.py']
    source_hashes={str(p):sha(p.read_bytes()) for p in sources}
    if READER.is_symlink() or not READER.is_file() or READER.stat().st_size != 117520224 or sha(READER.read_bytes()) != READER_SHA: raise ValueError('reader-mismatch')
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    vm = api.collect_identity(api._native(config, settings, api.run_root / '.doctor'))
    token = uuid.uuid4().hex
    folder = ROOT / 'artifacts/native-ability-catalog-20261107/runs' / lab / token
    folder.mkdir(parents=True, exist_ok=False)
    cache = settings['guestRoot'] + r'\current-variant-guards-' + READER_SHA[:16]
    reader = cache + r'\RiftReader2.Live.exe'
    prefix = settings['guestRoot'] + r'\catalog-' + token
    evidence = {}
    with api._session(config, settings, vm, folder) as guest:
        guest.powershell("$ErrorActionPreference='Stop';[IO.Directory]::CreateDirectory("+ps_literal(cache)+")|Out-Null;$e="+ps_literal(reader)+";if((Test-Path -LiteralPath $e) -and (Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'reader-hash-collision'}", timeout=60)
        # Query cache state in the guest; marker is unique and never overwritten.
        marker = prefix + '-installed.json'
        guest.powershell("$p="+ps_literal(marker)+";$b=[Text.Encoding]::UTF8.GetBytes((Test-Path -LiteralPath "+ps_literal(reader)+" -PathType Leaf).ToString());$f=[IO.File]::Open($p,[IO.FileMode]::CreateNew);try{$f.Write($b,0,$b.Length)}finally{$f.Dispose()}", timeout=60)
        local_marker=folder/'installed.txt'; guest.copy_from_guest(marker, local_marker, timeout=60)
        state=local_marker.read_text().strip()
        if state not in ('True','False'): raise ValueError('invalid-cache-state')
        if state == 'False': guest.run('copyFileFromHostToGuest', str(READER), reader, timeout=180)
        def native(mode, name, request=None, arguments=""):
            output=folder/(name+'.json'); guest_output=prefix+'-'+name+'.json'
            command="$ErrorActionPreference='Stop';$e="+ps_literal(reader)+";if((Get-FileHash -LiteralPath $e -Algorithm SHA256).Hash -cne "+ps_literal(READER_SHA)+"){throw 'reader-sha-mismatch'};if(Test-Path -LiteralPath "+ps_literal(guest_output)+"){throw 'output-exists'};"
            args=arguments
            if request is not None:
                payload=encoded(request); host_request=folder/(name+'-request.json'); guest_request=prefix+'-'+name+'-request.json'
                with host_request.open('xb') as f: f.write(payload)
                guest.powershell('if(Test-Path -LiteralPath '+ps_literal(guest_request)+"){throw 'request-exists'}",timeout=30)
                guest.run('copyFileFromHostToGuest',str(host_request),guest_request,timeout=60)
                command += "if((Get-FileHash -LiteralPath "+ps_literal(guest_request)+" -Algorithm SHA256).Hash -cne "+ps_literal(sha(payload))+"){throw 'request-hash-mismatch'};"
                args=' --request '+ps_literal(guest_request); evidence[host_request.name]=sha(payload)
            command += '& $e '+mode+args+' --output '+ps_literal(guest_output)+" | Out-Null;if($LASTEXITCODE -ne 0){throw 'native-command-failed'};if((Get-Item -LiteralPath "+ps_literal(guest_output)+").Length -gt 1000000){throw 'report-too-large'}"
            guest.powershell(command,timeout=90); guest.copy_from_guest(guest_output,output,timeout=60)
            with output.open('rb') as f: raw=f.read(1000001)
            if len(raw)>1000000: raise ValueError('report-too-large')
            evidence[output.name]=sha(raw)
            return json.loads(raw.decode('utf-8-sig'))
        identity,target=inspection_identity(native('inspect-native','inspect-before'))
        pid=target['processId']; ticks=target['processStartUtcTicks']
        common=' --pid '+str(pid)+' --start-ticks '+str(ticks)
        before=native('sample-current-ability-maps','maps-before',arguments=common)
        validate_maps(before,pid=pid,ticks=ticks)
        first=before['observation']
        if first['identity'] != identity: raise ValueError('map-identity-mismatch')
        def h1(obs):
            matches=[m for m in obs['maps'] if m['offset']==0x1C0]
            if len(matches)!=1: raise ValueError('invalid-h1')
            keys=[r['key'] for r in matches[0]['entries']]
            if not 1<=len(keys)<=512 or len(keys)!=len(set(keys)): raise ValueError('invalid-h1-keys')
            return sorted(keys)
        keys=h1(first)
        def keyed(name, mode, requested):
            payload=','.join(str(k) for k in requested).encode('ascii'); keysha=sha(payload)
            keypath=folder/(name+'-keys.txt')
            with keypath.open('xb') as f: f.write(payload)
            guest_key=cache+'\\'+name+'-keys-'+token+'.txt'; guest_output=cache+'\\'+name+'-'+token+'.json'
            guest.powershell('if(Test-Path -LiteralPath '+ps_literal(guest_key)+"){throw 'keys-exist'}",timeout=30)
            guest.run('copyFileFromHostToGuest',str(keypath),guest_key,timeout=60)
            command=build_launch(reader,guest_key,guest_output,pid,ticks,keysha,mode)
            if len(base64.b64encode(command.encode('utf-16le'))) > 4096: raise ValueError('guest-powershell-script-too-large')
            guest.powershell(command,timeout=130)
            output=folder/(name+'.json'); guest.copy_from_guest(guest_output,output,timeout=70)
            with output.open('rb') as f: raw=f.read(1000001)
            if len(raw)>1000000: raise ValueError('report-too-large')
            evidence[keypath.name]=keysha; evidence[output.name]=sha(raw)
            return json.loads(raw.decode('utf-8-sig'))
        record_reports=[]; names=[]; record_rows=[]
        for i in range(0,len(keys),128):
            chunk=keys[i:i+128]; name=f'records-{i//128+1}'
            report=keyed(name,'sample-current-ability-records',chunk)
            validate_record_costs_timing(report,pid=pid,ticks=ticks,keys=chunk)
            if report['observation']['identity']!=identity: raise ValueError('records-identity-mismatch')
            record_reports.append(report)
            for row in report['observation']['records']:
                record_rows.append((row,name))
                child=row.get('child') or {}
                if child.get('status')=='type-verified-candidate' and child.get('localizationKey'):
                    k=child['localizationKey']
                    if k not in names: names.append(k)
        if not names: raise ValueError('no-name-keys')
        dictionary_reports=[]; dictionary_rows={}
        for i in range(0,len(names),128):
            chunk=names[i:i+128]; name=f'dictionary-{i//128+1}'
            report=keyed(name,'sample-current-localization-dictionary',chunk)
            validate_dictionary(report,pid=pid,ticks=ticks,keys=chunk)
            obs=report['observation']
            if obs['identity']!=identity: raise ValueError('dictionary-identity-mismatch')
            dictionary_reports.append(report)
            frequencies=base64.b64decode(obs['frequencyBytesBase64'],validate=True)
            for row in obs['rows']: dictionary_rows[row['key']]=(row,frequencies,name)
        after=native('sample-current-ability-maps','maps-after',arguments=common)
        validate_maps(after,pid=pid,ticks=ticks)
        last=after['observation']
        if last['identity']!=identity or last['nativeUnitKey']!=first['nativeUnitKey'] or last['context']!=first['context'] or set(h1(last))!=set(keys): raise ValueError('map-owner-or-keys-changed')
        after_identity,after_target=inspection_identity(native('inspect-native','inspect-after'))
        if after_identity!=identity or after_target!=target: raise ValueError('process-epoch-changed')
        if any(sha(p.read_bytes())!=source_hashes[str(p)] for p in sources) or sha(READER.read_bytes())!=READER_SHA: raise ValueError('source-or-reader-changed')
        bymap={r['key']:r for r in first['maps'][0]['entries']}
        rows=[]; failures=0
        for ability,record_source in record_rows:
            key=ability['key']; maprow=bymap[key]; child=ability.get('child') or {}
            name_key=child.get('localizationKey') if child.get('status')=='type-verified-candidate' else None
            candidate=None; reason='unverified_or_missing_name_child'; dict_source=None
            if name_key:
                item,frequencies,dict_source=dictionary_rows[name_key]
                if item['status']!='raw-candidate': reason='dictionary_'+item['status']
                else:
                    try:
                        compressed=base64.b64decode(item['compressedBytesBase64'],validate=True)
                        decoded,_=decode_localization_huffman(frequencies,compressed,item['decodedSize'])
                        candidate=parse_localization_record(decoded)['candidate_text'] or None
                        reason=None if candidate else 'empty_candidate_text'
                    except (ValueError,KeyError,TypeError) as exc:
                        failures+=1; reason='decode_or_parse_failed: '+str(exc)
            rows.append({'key':key,'fullIdCandidate':ability.get('fullIdCandidate'),'apiListFilterNonzeroRaw':ability.get('apiListFilterNonzeroRaw'),'mapPrimaryRawHex':maprow.get('valueRawHex'),'mapSecondaryRawHex':maprow.get('secondaryRawHex'),'nameKey':name_key,'nameCandidate':candidate,'nameUnavailableReason':reason,'rawCosts':ability.get('rawCosts'),'rawTiming':ability.get('rawTiming'),'rawRange':ability.get('rawRange'),'rawVariants':ability.get('rawVariants'),'requiredLevelRaw':ability.get('requiredLevelRaw'),'recordSource':record_source,'dictionarySource':dict_source})
        observations=[first]+[r['observation'] for r in record_reports]+[r['observation'] for r in dictionary_reports]+[last]
        times=[datetime.fromisoformat(o[k].replace('Z','+00:00')) for o in observations for k in ('startedAtUtc','completedAtUtc')]
        joined={'qualification':'candidate-only; separate observations and chunks are not atomic or freshness-qualified','identity':identity,'vmIdentity':vm,'readerSha256':READER_SHA,'guestReaderReused':state=='True','sourceSha256':source_hashes,'evidence':evidence,'summary':{'total':len(rows),'filterNonzero':sum(bool(r['apiListFilterNonzeroRaw']) for r in rows),'names':sum(r['nameCandidate'] is not None for r in rows),'decoderFailures':failures},'records':rows,'observationIntervals':[{'source':name,'startedAtUtc':o['startedAtUtc'],'completedAtUtc':o['completedAtUtc']} for name,o in zip(['maps-before']+[f'records-{i+1}' for i in range(len(record_reports))]+[f'dictionary-{i+1}' for i in range(len(dictionary_reports))]+['maps-after'],observations)],'maximumObservationGapSeconds':(max(times)-min(times)).total_seconds(),'limitations':['Chunks and observations are separate and cannot exclude intervening changes.','No learned-ability, current API name, cost or cooldown semantic claim.']}
        if any(sha(p.read_bytes())!=source_hashes[str(p)] for p in sources): raise ValueError('source-changed-during-decode')
        with (folder/'catalog-summary.json').open('x',encoding='utf-8') as f: json.dump(joined,f,indent=2,ensure_ascii=False)
        return {'status':'candidate-only','summaryPath':str(folder/'catalog-summary.json'),'summary':joined['summary'],'maximumObservationGapSeconds':joined['maximumObservationGapSeconds']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--lab',required=True,choices=('lab1','lab2'));a=p.parse_args()
    print(json.dumps(run(a.lab)),flush=True)
