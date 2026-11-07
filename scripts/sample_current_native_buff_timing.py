"""Capture raw self-owned buff timer candidates without game input."""
import argparse, hashlib, json, math, struct, sys, uuid
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.inventory_passive_rift_sources import ps_literal
from scripts.sample_current_native_xyz import digest
from scripts.sample_current_native_buff_seeds import validate_report as validate_seeds
GAME_SHA = '1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8'
READER_SHA = 'BDE40E279E0E6CB22B167A9A3CF98B425B4380E6BF21B53C78B5AB18D50659FE'
READER = ROOT / 'artifacts/native-buff-timing-20261107/publish/RiftReader2.Live.exe'
EVIDENCE = ROOT / 'artifacts/native-buff-timing-20261107/runs'

def validate_report(report, *, pid, ticks):
    o=validate_seeds(report,pid=pid,ticks=ticks)
    def real(v): return type(v) in (int,float) and math.isfinite(v)
    def integer(v,lo,hi): return type(v) is int and lo<=v<=hi
    def invalid(): raise ValueError('invalid buff-timing report')
    before=o.get('clockBefore'); after=o.get('clockAfter')
    if not real(before) or not real(after) or after<before: invalid()
    statuses=('unavailable','unsupported-clock-profile','state-sentinel','dynamic-duration-unavailable','reference-type-unavailable','raw-timing-candidate','read-or-type-unavailable')
    for node in o['nodes']:
        t=node.get('timing'); raw=node['rawObject']
        if not isinstance(t,dict) or t.get('status') not in statuses: invalid()
        bits=t.get('beginRawBits'); begin=t.get('begin'); ref=t.get('timerReference')
        if (bits is None)!=(begin is None): invalid()
        if bits is not None:
            if not integer(bits,0,2**32-1) or not real(begin) or abs(begin)>3.4028234663852886e38 or struct.pack('<f',begin)!=struct.pack('<I',bits): invalid()
        for field in ('timerReference','referenceVtableRva','referenceGetterRva','referenceSlot48Rva'):
            v=t.get(field)
            if v is not None and not integer(v,0,2**64-1): invalid()
        ticks_value=t.get('durationTicks'); duration=t.get('duration'); remaining=t.get('remaining')
        if t['status']=='raw-timing-candidate':
            if not integer(ticks_value,-2**63,2**63-1) or not real(duration) or not real(remaining) or bits is None or not integer(ref,1,2**64-1): invalid()
            vt=raw.get('clockVtableRva'); profiles={0x26BC950:(0x72AE00,0x286CDC8,0x18254A0),0x26BC9A0:(0x72AE70,0x2CC0618,0x225CA20)}
            if vt not in profiles: invalid()
            duration_slot,refvt,refgetter=profiles[vt]
            if raw.get('stateDword88') in (None,5) or raw.get('clockSlot30Rva')!=duration_slot or raw.get('clockSlot38Rva')!=0x72B3C0 or raw.get('clockSlot48Rva')!=0x09D680 or t.get('referenceVtableRva')!=refvt or t.get('referenceGetterRva')!=refgetter: invalid()
        elif any(v is not None for v in (ticks_value,duration,remaining)): invalid()
        if t['status']=='state-sentinel' and raw.get('stateDword88')!=5: invalid()
    return o

def run(lab):
    if lab not in ('lab1','lab2'): raise ValueError('invalid lab')
    if not READER.is_file() or READER.is_symlink() or READER.stat().st_size != 117552992 or digest(READER) != READER_SHA: raise ValueError('reader identity mismatch')
    api=LabCodex(); _,_,config,settings=api._configuration(lab)
    vm=api.collect_identity(api._native(config,settings,api.run_root / '.doctor'))
    token=uuid.uuid4().hex; output=EVIDENCE / lab / token; output.mkdir(parents=True,exist_ok=False)
    folder=settings['guestRoot'] + r'\current-buff-timing-' + READER_SHA[:16]
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
            "& $exe sample-current-buff-seeds --pid "+str(pid)+" --start-ticks "+str(ticks)+" --include-timing true --output $out | Out-Null;"
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
