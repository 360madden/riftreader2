"""Repeat the proven CLI capture / reviewed guarded pulse / comparison workflow.

Default is offline configuration validation. --run performs one live trial;
the current controller still requires review of a fresh screenshot before input.
Credentials exist only in the GuestSession context. No dated artifact imports.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import queue
import re
import stat
import subprocess
import sys
import threading
from types import SimpleNamespace
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.control_client import ControlClient, _capture, _arm, _action
from scripts.control_host import HostConfig
from scripts.nav_access_queue import AccessQueue
from scripts.prepare_xyz_deployment import validate_profile
from scripts.review_native_motion_pair import review
from scripts.vm_console_native import collect_identity, process_identity, validate_config
from scripts.vmware_guest_session import GuestSession, SessionError

MAX_BYTES = 16 * 1024 * 1024
SHA = re.compile(r'[A-F0-9]{64}\Z')
CONFIG_KEYS = {'schemaVersion', 'hostPlan', 'hostProcess', 'vmrun',
               'guestDirectory', 'readerSha256', 'profile'}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest().upper()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON property')
        result[key] = value
    return result


def decode(data):
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def load(path):
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, 'Missing or oversized input')
    return decode(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sanitize(value):
    if isinstance(value, dict):
        return {k: '[redacted]' if any(w in k.lower() for w in ('token', 'password', 'secret', 'authorization'))
                else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def windows_path(value):
    require(isinstance(value, str) and not any(ord(c) < 32 for c in value), 'Invalid guest path')
    path = PureWindowsPath(value)
    require(path.is_absolute() and len(path.drive) == 2 and '..' not in path.parts
            and ':' not in value[2:] and not any(c in value for c in '*?<>|"'), 'Invalid guest path')
    return str(path)


def read_config(path):
    cfg = load(path)
    require(set(cfg) == CONFIG_KEYS and type(cfg['schemaVersion']) is int
            and cfg['schemaVersion'] == 1, 'Unsupported workflow configuration')
    require(isinstance(cfg['readerSha256'], str) and SHA.fullmatch(cfg['readerSha256']), 'Invalid reader hash')
    cfg['guestDirectory'] = windows_path(cfg['guestDirectory'])
    for key in ('hostPlan', 'hostProcess', 'vmrun', 'profile'):
        p = Path(cfg[key])
        require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'Configuration paths must be absolute files')
    profile_bytes = Path(cfg['profile']).read_bytes()
    profile = validate_profile(profile_bytes)
    require(int(profile['rootRva'], 16) == 0x32E0200 and
            [int(v, 16) for v in profile['xyzOffsets']] == [0x320, 0x324, 0x328],
            'Current independent reviewer supports only the proven XYZ recipe')
    return cfg, profile, digest(profile_bytes)


class HostGuard:
    def __init__(self, cfg, profile, output):
        self.cfg, self.profile = cfg, profile
        self.plan_path = Path(cfg['hostPlan'])
        self.receipt_path = Path(cfg['hostProcess'])
        self.plan, self.receipt = load(self.plan_path), load(self.receipt_path)
        self.pins = {self.plan_path: digest(self.plan_path.read_bytes()),
                     self.receipt_path: digest(self.receipt_path.read_bytes()),
                     Path(cfg['profile']): digest(Path(cfg['profile']).read_bytes())}
        p, r = self.plan, self.receipt
        require(p['schemaVersion'] == 1 and r['vmIdentity'] == p['vmIdentity']
                and r['configSha256'] == p['configSha256'] and r['runtimeHashes'] == p['runtimeHashes']
                and r['canonicalDatabase'].casefold() == p['database'].casefold()
                and r['resource'] == p['resource'] and r['windowsSessionId'] == p['expectedWindowsSession']
                and r['inJob'] is False, 'Controller receipt differs from plan')
        self.pins[Path(p['configPath'])] = p['configSha256'].upper()
        for relative, sha in p['runtimeHashes'].items():
            source = (ROOT / relative).resolve()
            require(source.is_relative_to(ROOT), 'Runtime source outside repository')
            self.pins[source] = sha.upper()
        self.verify_files()
        self.native = validate_config(Path(p['vmIdentity']['vmx']), p['vmIdentity']['port'],
                                      Path(cfg['vmrun']), output, require_files=True)
        self.client = ControlClient(HostConfig.load(Path(p['configPath'])))
        self.target = None

    def verify_files(self):
        require(not Path(self.plan['shutdownFile']).exists(), 'Controller shutdown requested')
        for path, sha in self.pins.items():
            require(path.is_file() and digest(path.read_bytes()) == sha, 'Pinned controller/runtime input changed')

    def check(self):
        self.verify_files()
        require(process_identity(self.receipt['pid']) == self.receipt['processIdentity'], 'Controller process changed')
        require(collect_identity(self.native) == self.plan['vmIdentity'], 'VM epoch changed')
        return self.plan['vmIdentity']

    def status(self, *, idle=True):
        self.check()
        value = self.client.request('/api/status', method='GET')
        host, guest = value['host'], value['guest']
        require(host['connected'] and host['vmIdentity'] == self.plan['vmIdentity']
                and host['consoleReservation']['held'] and not host['consoleReservation']['faulted']
                and host['coordination']['state'] == 'ready', 'Controller is not ready or sole owner')
        target = {k: guest['target'][k] for k in ('processId', 'processStartUtcTicks', 'executableSha256')}
        require(target['executableSha256'] == self.profile['executableSha256'], 'Game build differs from profile')
        require(type(target['processId']) is int and target['processId'] > 0
                and type(target['processStartUtcTicks']) is int and target['processStartUtcTicks'] > 0,
                'Invalid game process identity')
        if self.target is None:
            self.target = target
        require(target == self.target, 'Game epoch changed during run')
        if idle:
            require(not guest['armed'] and not guest['busy'] and not guest['desktopInputsDown']
                    and not guest['recoveryRequired'], 'Guest is not idle/disarmed')
        self.check()
        return value


def phase_script(cfg, profile_sha, target, guest_output, phase):
    require(phase in ('baseline', 'after'), 'Unsupported phase')
    pointer = dict(schemaVersion=1, evidenceKind='native-pointer-follow-request/1', target=target,
                   rootRva='0x32E0200', offsets=['0x0'], terminalByteLength=816, maxDurationMilliseconds=5000)
    typed = dict(schemaVersion=1, evidenceKind='native-typed-inline-capture-request/1', target=target,
                 startAddress='0x10000', maxScanBytes=536870912, maxDurationMilliseconds=30000,
                 maxRegionCount=32768, maxMatchCount=128, maxCopiedCandidates=8)
    settings = dict(phase=phase, guestDirectory=cfg['guestDirectory'], guestOutput=windows_path(guest_output),
                    readerSha256=cfg['readerSha256'], profileSha256=profile_sha, target=target,
                    pointerRequest=json.dumps(pointer, sort_keys=True, separators=(',', ':')),
                    typedRequest=json.dumps(typed, sort_keys=True, separators=(',', ':')))
    data = base64.b64encode(json.dumps(settings).encode()).decode('ascii')
    return (ROOT / 'scripts/xyz_capture.ps1').read_text(encoding='utf-8').replace('__SETTINGS_BASE64__', data)


def unpack_phase(archive, claim, destination, phase):
    require(not destination.exists(), 'Extracted evidence already exists')
    require(claim['phase'] == phase and type(claim['byteLength']) is int and
            0 < claim['byteLength'] <= MAX_BYTES and SHA.fullmatch(claim['sha256']), 'Invalid archive claim')
    require(archive.stat().st_size == claim['byteLength'] and digest(archive.read_bytes()) == claim['sha256'],
            'Archive hash or length differs')
    members, names = {}, set()
    with zipfile.ZipFile(archive) as z:
        require(len(z.infolist()) <= 160 and sum(i.file_size for i in z.infolist()) <= MAX_BYTES, 'Archive too large')
        for item in z.infolist():
            name = item.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            require(item.orig_filename.replace('\\', '/') == name and '\0' not in item.orig_filename and parts
                    and name.rstrip('/') == PurePosixPath(name).as_posix()
                    and not PurePosixPath(name).is_absolute() and not any(
                        p in ('.', '..') or ':' in p or p.endswith((' ', '.'))
                        or any(c in p for c in '<>"|?*') or any(ord(c) < 32 for c in p)
                        or p.split('.')[0].casefold() in {'con','prn','aux','nul',
                            *(f'com{i}' for i in range(1,10)), *(f'lpt{i}' for i in range(1,10))}
                        for p in parts), 'Unsafe archive member')
            require(name.casefold() not in names and not stat.S_ISLNK(item.external_attr >> 16), 'Duplicate or linked member')
            names.add(name.casefold())
            if not item.is_dir():
                require(item.file_size <= 8 * 1024 * 1024, 'Member too large')
                members[name] = z.read(item)
    claims = decode(members['files.json'])
    require(isinstance(claims, list) and len({x['path'] for x in claims}) == len(claims), 'Duplicate file declarations')
    require(set(members) == {'files.json'} | {x['path'] for x in claims}, 'Archive member set differs')
    for record in claims:
        raw = members[record['path']]
        require(len(raw) == record['byteLength'] and digest(raw) == record['sha256'], 'Member hash or length differs')
    destination.mkdir()
    for name, raw in members.items():
        p = destination / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as f:
            f.write(raw)
    return len(members)


def collect_phase(session, guard, cfg, profile_sha, output, guest_output, phase):
    guard.status()
    script = phase_script(cfg, profile_sha, guard.target, guest_output, phase)
    with (output / (phase + '.ps1')).open('x', encoding='utf-8') as f:
        f.write(script)
    session.powershell(script, timeout=150)
    receipt_path = output / (phase + '.receipt.json')
    session.copy_from_guest(guest_output + '\\' + phase + '.receipt.json', receipt_path)
    require(receipt_path.stat().st_size <= 16384, 'Receipt too large')
    claim = load(receipt_path)
    require(type(claim['byteLength']) is int and 0 < claim['byteLength'] <= MAX_BYTES, 'Archive exceeds transfer cap')
    archive = output / (phase + '.zip')
    session.copy_from_guest(guest_output + '\\' + phase + '.zip', archive)
    dest = output / (phase + '-originals')
    count = unpack_phase(archive, claim, dest, phase)
    save(output / (phase + '.transfer.json'), dict(atUtc=stamp(), verified=True, files=count, claim=claim))
    status = load(dest / 'status.json')
    require(status['target'] == guard.target and status.get('completed') is True
            and status.get('sampleExit') == 0 and status.get('pointerExit') == 0
            and status.get('luaExit') in (0, 3), 'Phase failed; preserved originals contain diagnostics')
    samples = load(dest / 'samples.json')['samples']
    require(samples['status'] == 'complete' and samples['completedSamples'] == 3, 'Native samples incomplete')
    require(samples['motion']['firstLastDistanceGameUnits'] == 0
            and samples['motion']['maxExcursionFromFirstGameUnits'] == 0, 'Endpoint moved during sampling')
    lua = load(dest / 'lua/index.json')
    require(lua['publishedSnapshots'] > 0 and lua['status'] in ('complete', 'partial'), 'No usable Lua snapshots')
    guard.status()
    print(json.dumps({'phase': phase, 'verifiedFiles': count, 'xyz': {
        k: samples['observations'][-1][k] for k in ('x','y','z')}}), flush=True)


def read_review(capture, timeout=22):
    print(json.dumps({'reviewRequired': True, **capture,
                      'instruction': 'Inspect this screenshot, then enter: approve CAPTURE_ID clear ground; no text entry or dialog'}), flush=True)
    pending = queue.Queue()
    threading.Thread(target=lambda: pending.put(sys.stdin.readline()), daemon=True).start()
    try:
        line = pending.get(timeout=timeout).strip()
    except queue.Empty:
        raise ValueError('Screenshot review timed out; no input authorized') from None
    prefix = 'approve ' + capture['captureId'] + ' '
    require(line.startswith(prefix) and 15 <= len(line[len(prefix):]) <= 300, 'Screenshot review declined or invalid')
    return line[len(prefix):]


def pulse(guard, output, run_id, reviewer=read_review):
    state = guard.status()
    require(state['guest']['target']['isForeground'], 'Game must be foreground before pulse')
    q = AccessQueue(guard.plan['database'])
    status = q.status()
    resource = next(v for v in status['resources'] if v['name'] == guard.plan['resource'])
    require(not resource['blocked'] and resource['holder'] is None and
            not any(v['state'] in ('queued', 'active', 'cleanup') for v in status['requests']), 'Control queue is occupied')
    q.submit(run_id, 'xyz-workflow', 'C', {guard.plan['resource']: resource['epoch']},
             ttl_ms=30000, max_ms=120000, estimated_ms=1000)
    grant = q.dispatch()
    require(grant and grant['request_id'] == run_id, 'Control grant unavailable')
    client = ControlClient(HostConfig.load(Path(guard.plan['configPath'])),
                           access={k: grant[k] for k in ('request_id', 'token')})
    success = False
    try:
        capture = _capture(client, output / 'motion-capture')
        q.heartbeat(grant['request_id'], grant['token'])
        note = reviewer(capture)
        guard.status()
        q.heartbeat(grant['request_id'], grant['token'])
        _arm(client, output/'motion-capture/capture.json', note, output/'motion-arm.private.json')
        result = _action(client, SimpleNamespace(arm=output/'motion-arm.private.json',keys='w',hold_ms=100,
                         mouse_button=None,dx=0,dy=0,wheel=0,output=output/'motion-action.json'))['result']
        result = result['result']
        require(result['deliverySucceeded'] and result['releaseSucceeded'] and not result['targetLost']
                and not result['stateUncertain'] and not result['cancelled'], 'Pulse delivery or release failed')
        success = True
    finally:
        try:
            cleanup = client.request('/api/stop', method='POST', payload={})
            save(output/'motion-stop.json', sanitize(cleanup))
        finally:
            result = q.finish(grant['request_id'], grant['token'], 'succeeded' if success else 'failed',
                              [str(output/'motion-action.json') if success else 'No automatic retry; see retained evidence'])
            save(output/'motion-finish.json', sanitize(result))
    guard.status()


def compare(output):
    cli = ROOT / 'src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll'
    require(cli.is_file(), 'Build the existing offline CLI before this workflow')
    directory = output / 'comparisons'
    directory.mkdir()
    candidates = []
    for a in sorted((output/'baseline-originals/lua').glob('*.snapshot.json')):
        for b in sorted((output/'after-originals/lua').glob('*.snapshot.json')):
            dest = directory / (a.name.split('.')[0] + '-' + b.name.split('.')[0] + '.json')
            result = subprocess.run(['dotnet', str(cli), 'inspect-typed-wire', '--before', str(a),
                                     '--after', str(b), '--output', str(dest)], capture_output=True, timeout=30)
            require(result.returncode == 0, 'Offline Lua inspection failed')
            value = load(dest)
            if value['status'] == 'advanced-in-covered-scope':
                candidates.append((value['selected']['after']['frameTime'], value['selected']['before']['frameTime'], dest))
    require(candidates, 'No advancing Lua pair; retained diagnostics explain why')
    selected = max(candidates)[2]
    report = review(output/'baseline-originals/pointer.json', output/'after-originals/pointer.json',
                    output/'baseline-originals/pointer-request.json', selected, digest(selected.read_bytes()))
    save(output/'motion-review.json', report)
    summary = {k: report[k] for k in ('status','qualification','nativeDisplacement','typedDisplacement',
                                      'nativeMinusTypedDisplacement','endpointAgreement','nativeMinusTypedSampleTimeSeconds')}
    summary.update(nativeDistance=math.sqrt(sum(v*v for v in report['nativeDisplacement'].values())),
                   luaDistance=math.sqrt(sum(v*v for v in report['typedDisplacement'].values())),
                   selectedComparison=selected.name, advancingComparisons=len(candidates), patchRecovery='deferred')
    save(output/'summary.json', summary)
    return summary


def export(output):
    payload = {}
    for p in sorted(output.rglob('*')):
        if not p.is_file() or '.private.' in p.name or p.name in ('evidence.zip', 'export-receipt.json'):
            continue
        require(not p.is_symlink(), 'Linked export source')
        raw = p.read_bytes()
        if p.suffix == '.json':
            obj = decode(raw)
            require(sanitize(obj) == obj, 'Private credential-shaped value in export')
        payload[p.relative_to(output).as_posix()] = raw
    require(sum(map(len, payload.values())) <= 64*1024*1024, 'Export exceeds bound')
    manifest = {name: {'bytes':len(raw),'sha256':digest(raw)} for name,raw in payload.items()}
    payload['manifest.json'] = (json.dumps(manifest,indent=2)+'\n').encode()
    path = output/'evidence.zip'
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in payload.items():
            z.writestr(name,raw)
    with zipfile.ZipFile(path) as z:
        require(set(z.namelist()) == set(payload) and z.testzip() is None, 'Export verification failed')
        for name,raw in payload.items():
            require(z.read(name) == raw, 'Export member changed')
    save(output/'export-receipt.json',dict(files=len(payload),byteLength=path.stat().st_size,
                                         sha256=digest(path.read_bytes()),verified=True))


def run(cfg, profile, profile_sha, output, *, cache_login=False):
    output.mkdir(parents=False, exist_ok=False)
    save(output/'run.json',dict(startedAtUtc=stamp(),phase='started',cacheLoginRequested=cache_login,
                               credentialsWrittenToProject=False,patchRecovery='deferred'))
    guard = HostGuard(cfg,profile,output)
    save(output/'initial-status.json',sanitize(guard.status()))
    run_id = 'xyz-' + uuid.uuid4().hex[:16]
    guest_output = 'C:\\RIFT_TRANSFER\\XYZ\\' + run_id
    try:
        with GuestSession(Path(cfg['vmrun']), guard.native.vmx, guard.check,
                          cache_guest_credentials=cache_login) as guest:
            save(output/'authentication.json',dict(atUtc=stamp(),credentialSource=guest.credential_source,
                                                   cacheWritten=guest.cache_written,credentialsWrittenToProject=False))
            collect_phase(guest,guard,cfg,profile_sha,output,guest_output,'baseline')
            pulse(guard,output,run_id)
            collect_phase(guest,guard,cfg,profile_sha,output,guest_output,'after')
        summary = compare(output)
        save(output/'final-status.json',sanitize(guard.status()))
        save(output/'complete.json',dict(completedAtUtc=stamp(),status=summary['status'],credentialSessionClosed=True))
        export(output)
        print(json.dumps({'output':str(output),'summary':summary,'export':str(output/'evidence.zip')}),flush=True)
        return 0 if summary['status'] == 'candidate-motion-consistent' else 2
    except BaseException as error:
        save(output/'failure.json',dict(atUtc=stamp(),errorType=type(error).__name__,
                                        reason=str(error) if isinstance(error,(ValueError,SessionError)) else 'Operation failed; inspect retained evidence'))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--cache-login',action='store_true',help='Save a verified guest login in Windows Credential Manager; requires --run')
    args = parser.parse_args(argv)
    try:
        cfg, profile, profile_sha = read_config(args.config.resolve())
        require(not args.cache_login or args.run, '--cache-login requires --run')
        if not args.run:
            print(json.dumps({'status':'configuration-valid-no-live-access','guestDirectory':cfg['guestDirectory'],
                              'gameSha256':profile['executableSha256'],'profileSha256':profile_sha}))
            return 0
        require(args.output is not None,'--run requires a new --output directory')
        output = args.output.absolute()
        require(output.parent.is_dir() and not output.exists() and output.resolve().is_relative_to(ROOT/'artifacts'),
                'Output must be a new directory under repository artifacts')
        require((ROOT/'src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll').is_file(),'Build offline CLI first')
        return run(cfg,profile,profile_sha,output,cache_login=args.cache_login)
    except (Exception,KeyboardInterrupt) as error:
        print(json.dumps({'status':'blocked','errorType':type(error).__name__,
                          'reason':str(error) if isinstance(error,(ValueError,SessionError)) else 'Operation failed; retained evidence was not overwritten'}),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
