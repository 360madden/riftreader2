"""Capture bounded raw self cooldown modifier candidates without game input."""
import argparse, hashlib, json, math, struct, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = '6F662E78BBE5A360914FA38F2B26EAB4B3C9004EA4B4B641E15D7FBBB9A2CDF6'
READER_SIZE = 117741920
READER = ROOT / 'artifacts/native-range-energy-role-factor-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-cooldown-modifiers-20261107/runs'

QUALIFICATION = 'raw modifier census only; eligibility, adjusted cooldown, freshness and restart unverified'

def validate_report(report, *, pid, ticks):
    def integer(v, low, high): return type(v) is int and low <= v <= high
    def invalid(): raise ValueError('invalid cooldown modifier report')
    def pointer(v): return integer(v, 0x10000, 0x7fffffffffff) and v % 8 == 0
    if not isinstance(report, dict) or type(report.get('schemaVersion')) is not int or report['schemaVersion'] != 1 or report.get('contractVersion') != 'native-current-cooldown-modifiers-candidate/1' or report.get('status') != 'complete': invalid()
    o = report.get('observation')
    if not isinstance(o, dict) or o.get('qualification') != QUALIFICATION: invalid()
    ident = o.get('identity')
    if not isinstance(ident, dict) or not integer(pid,1,2**31-1) or not integer(ticks,1,2**63-1) or type(ident.get('processId')) is not int or ident['processId'] != pid or type(ident.get('processStartUtcTicks')) is not int or ident['processStartUtcTicks'] != ticks or ident.get('executableSha256') != GAME_SHA: invalid()
    try: start=datetime.fromisoformat(o['startedAtUtc'].replace('Z','+00:00')); end=datetime.fromisoformat(o['completedAtUtc'].replace('Z','+00:00'))
    except (KeyError,TypeError,AttributeError,ValueError): invalid()
    if start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0 or end.utcoffset().total_seconds()!=0 or end<start or not integer(o.get('selfKey'),1,2**64-1) or not pointer(o.get('component')): invalid()
    config=o.get('rangeConfig')
    if config is not None:
        if not isinstance(config,dict): invalid()
        cs=config.get('status'); root=config.get('root'); address=config.get('address')
        data=('minBits','min','maxBits','max','specialKey')
        if cs=='typed-0e29-candidate':
            if not pointer(root) or not pointer(address) or not integer(config.get('specialKey'),0,2**32-1): invalid()
            for bk,fk in (('minBits','min'),('maxBits','max')):
                bits=config.get(bk);value=config.get(fk)
                if not integer(bits,0,2**32-1): invalid()
                decoded=struct.unpack('<f',struct.pack('<I',bits))[0]
                if math.isfinite(decoded):
                    if type(value) not in (int,float) or not math.isfinite(value): invalid()
                    try: matches=struct.pack('<f',value)==struct.pack('<I',bits)
                    except (OverflowError,struct.error): invalid()
                    if not matches: invalid()
                elif value is not None: invalid()
        elif cs=='null-root':
            if type(root) is not int or root!=0 or address is not None or any(config.get(k) is not None for k in data): invalid()
        elif cs=='null-config':
            if not pointer(root) or type(address) is not int or address!=0 or any(config.get(k) is not None for k in data): invalid()
        elif cs=='unverified-type':
            if not pointer(root) or not pointer(address) or any(config.get(k) is not None for k in data): invalid()
        elif cs=='read-unavailable':
            if (root is not None and not integer(root,0,2**64-1)) or (address is not None and not integer(address,0,2**64-1)) or any(config.get(k) is not None for k in data): invalid()
        else: invalid()
    begin=o.get('begin'); endaddr=o.get('end'); rows=o.get('rows')
    if not integer(begin,0,0x7fffffffffff) or not integer(endaddr,0,0x7fffffffffff) or (begin==0)!=(endaddr==0) or endaddr<begin or (endaddr-begin)%32 or (endaddr-begin)//32>256 or (begin and not pointer(begin)) or not isinstance(rows,list) or len(rows)!=(endaddr-begin)//32: invalid()
    def span(v):
        if not isinstance(v,dict): invalid()
        b=v.get('begin'); e=v.get('end'); values=v.get('values')
        if not integer(b,0,0x7fffffffffff) or not integer(e,0,0x7fffffffffff) or (b==0)!=(e==0) or e<b or (e-b)%4 or (e-b)//4>512 or (b and (b<0x10000 or b%4)) or not isinstance(values,list) or len(values)!=(e-b)//4 or any(not integer(x,0,2**32-1) for x in values): invalid()
    incomplete=False; mode4=False; mode0_payload=False; mode0_attempt=False
    for i,r in enumerate(rows):
        if not isinstance(r,dict) or r.get('entryAddress')!=begin+32*i or not isinstance(r.get('rawEntryHex'),str) or len(r['rawEntryHex'])!=64: invalid()
        try: raw=bytes.fromhex(r['rawEntryHex'])
        except ValueError: invalid()
        if len(raw)!=32 or not integer(r.get('pointer'),0,2**64-1) or struct.unpack_from('<Q',raw)[0]!=r['pointer']: invalid()
        status=r.get('status'); p=r['pointer']; scale=r.get('rawScaleKey')
        if scale is not None and (status not in ('mode-4-raw-candidate','mode-0-raw-candidate','mode-2-raw-candidate') or not integer(scale,0,2**32-1)): invalid()
        seed=r.get('flag33Seed')
        if seed is not None:
            if status not in ('mode-0-raw-candidate','mode-2-raw-candidate') or not integer(r.get('flag33'),1,255) or not isinstance(seed,dict) or not pointer(seed.get('entity')): invalid()
            es=seed.get('entrySourceKey'); source=seed.get('entitySourceKey'); match=seed.get('sourceMatches'); address=seed.get('address'); key=seed.get('key18'); slot=seed.get('slot1C'); ss=seed.get('status')
            if not integer(es,0,2**64-1) or es!=struct.unpack_from('<Q',raw,16)[0] or (source is not None and not integer(source,0,2**64-1)) or (match is not None and type(match) is not bool) or (source is None and match is not None) or (source is not None and match!=(source==es)) or (address is not None and not integer(address,0,2**64-1)): invalid()
            if ss=='entry-count-branch':
                if match is not False or any(v is not None for v in (address,key,slot)): invalid()
            elif ss=='null-073c-reference':
                if match is not True or type(address) is not int or address!=0 or key is not None or slot is not None: invalid()
            elif ss=='unverified-073c-type':
                if match is not True or not pointer(address) or key is not None or slot is not None: invalid()
            elif ss in ('typed-073c-direct-branch','typed-073c-fallback-branch'):
                if match is not True or not pointer(address) or not integer(key,-2**31,2**31-1) or not integer(slot,-2**31,2**31-1) or (ss=='typed-073c-direct-branch')!=(key!=0 and slot!=-1): invalid()
            elif ss=='read-unavailable':
                if key is not None or slot is not None: invalid()
            else: invalid()
            factor=seed.get('roleFactor')
            if factor is not None:
                if ss!='typed-073c-direct-branch' or not isinstance(factor,dict): invalid()
                fs=factor.get('status'); rv=factor.get('rawMultiplier'); addresses=[factor.get(k) for k in ('roleAddress','nodeAddress','containerAddress','childAddress')]
                if any(a is not None and not integer(a,0,2**64-1) for a in addresses): invalid()
                if fs=='raw-factor-candidate':
                    if not all(pointer(a) for a in addresses) or not integer(rv,-2**31,2**31-1): invalid()
                elif fs in ('role-index-outside-zero-candidate','null-role-zero-candidate','tree-miss-zero-candidate','null-container-zero-candidate','slot-miss-zero-candidate'):
                    if type(rv) is not int or rv!=0: invalid()
                    role,node,container,child=addresses
                    if fs=='role-index-outside-zero-candidate' and addresses!=[None,None,None,None]: invalid()
                    if fs=='null-role-zero-candidate' and addresses!=[0,None,None,None]: invalid()
                    if fs=='tree-miss-zero-candidate' and not (pointer(role) and node==0 and container is None and child is None): invalid()
                    if fs=='null-container-zero-candidate' and not (pointer(role) and pointer(node) and container==0 and child is None): invalid()
                    if fs=='slot-miss-zero-candidate' and not (pointer(role) and pointer(node) and pointer(container) and child is None): invalid()
                elif fs in ('owner-type-unavailable','role-type-unavailable','tree-path-unavailable','container-type-unavailable','child-type-unavailable','read-or-binding-unavailable'):
                    if rv is not None: invalid()
                else: invalid()
        direct=r.get('directScale')
        if direct is not None:
            if status not in ('mode-4-raw-candidate','mode-0-raw-candidate','mode-2-raw-candidate') or r.get('flag36')!=1 or (status in ('mode-0-raw-candidate','mode-2-raw-candidate') and r.get('flag33')!=0) or not isinstance(direct,dict) or not integer(scale,0,2**32-1) or type(direct.get('key')) is not int or direct['key']!=scale: invalid()
            ds=direct.get('status'); multiplier=direct.get('rawMultiplier')
            if ds=='raw-factor-candidate':
                if scale<=1 or not integer(multiplier,-2**31,2**31-1): invalid()
            elif ds in ('null-link-zero-candidate','null-row-zero-candidate'):
                if scale<=1 or type(multiplier) is not int or multiplier!=0: invalid()
            elif ds=='zero-key-unresolved':
                if scale!=0 or multiplier is not None: invalid()
            elif ds=='caller-bypass':
                if scale!=1 or multiplier is not None: invalid()
            elif ds in ('owner-type-unavailable','tree-unavailable','tree-type-unavailable','unmatched-header-unavailable','cycle-unavailable','row-type-unavailable','node-budget-unavailable','read-or-binding-unavailable'):
                if scale<=1 or multiplier is not None: invalid()
            else: invalid()
        if status=='null-reference':
            if p!=0: invalid()
            incomplete=True
        elif status=='unavailable':
            if p==0: invalid()
            incomplete=True
        elif status in ('mode-candidate','mode-4-raw-candidate','mode-0-raw-candidate','mode-0-payload-unavailable','mode-2-raw-candidate','mode-2-payload-unavailable'):
            mode=r.get('mode');vt=r.get('vtable'); getter=r.get('getterRva')
            if not pointer(p) or not integer(mode,-2**31,2**31-1) or not integer(vt,0,2**64-1) or (getter is not None and not integer(getter,0,2**64-1)): invalid()
            if status=='mode-candidate':
                if mode==4: invalid()
            elif status in ('mode-0-payload-unavailable','mode-2-payload-unavailable'):
                if mode!=(0 if status=='mode-0-payload-unavailable' else 2) or any(r.get(k) is not None for k in ('float18Bits','float18','float24Bits','float24','operation','flag30','flag33','flag34','flag36','exclusions','directKeys','tags1','tags2','tags3','rawScaleKey','directScale')): invalid()
                mode0_attempt=True
            else:
                if (status=='mode-4-raw-candidate' and mode!=4) or (status=='mode-0-raw-candidate' and mode!=0) or (status=='mode-2-raw-candidate' and mode!=2): invalid()
                if mode==4: mode4=True
                else: mode0_payload=True; mode0_attempt=True
                for bits_key,float_key in [('float18Bits','float18'),('float24Bits','float24')]:
                    bits=r.get(bits_key); val=r.get(float_key)
                    if not integer(bits,0,2**32-1): invalid()
                    decoded=struct.unpack('<f',struct.pack('<I',bits))[0]
                    if (math.isfinite(decoded) and (type(val) not in (int,float) or not math.isfinite(val) or struct.pack('<f',val)!=struct.pack('<I',bits))) or (not math.isfinite(decoded) and val is not None): invalid()
                if not integer(r.get('operation'),0,2**32-1) or any(not integer(r.get(k),0,255) for k in ('flag30','flag33','flag34','flag36')): invalid()
                for k in ('exclusions','directKeys','tags1','tags2','tags3'): span(r.get(k))
        else: invalid()
    expected='incomplete' if incomplete else 'mode-4-present' if mode4 else 'no-mode-4-observed'
    if o.get('censusStatus')!=expected or ((mode4 or mode0_payload) and not integer(o.get('rawContextKey'),0,2**32-1)) or (not mode4 and not mode0_payload and o.get('rawContextKey') is not None and not ((incomplete or mode0_attempt) and integer(o.get('rawContextKey'),0,2**32-1))): invalid()
    return o


def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != READER_SIZE or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
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
            "& $exe sample-current-cooldown-modifiers --pid "+str(pid)+" --start-ticks "+str(ticks)+" --output $out | Out-Null;"
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
