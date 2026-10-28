"""Request a bounded local launcher operation through cached VMware guest login."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_xyz_workflow as w
from scripts.vmware_guest_session import GuestSession
from scripts.nav_access_queue import QueueError


@contextmanager
def maintenance_lease(guard, output):
    queue = w.AccessQueue(guard.plan['database'])
    rid = 'agent-maintenance-' + uuid.uuid4().hex[:12]
    # Serialize admission with other cooperative dispatches. Status is paged:
    # 100 historical completed rows must not conceal a newer queued request.
    with queue.dispatch_fence():
        page = queue.status()
        resource = next(v for v in page['resources'] if v['name'] == guard.plan['resource'])
        w.require(not resource.get('blocked') and resource.get('holder') is None,
                  'Control resource occupied')
        while True:
            w.require(not any(v['state'] in ('queued', 'active', 'cleanup')
                              for v in page.get('requests', [])), 'Control queue occupied')
            cursor = page.get('next_sequence')
            if cursor is None:
                break
            page = queue.status(after_sequence=cursor)
        queue.submit(rid, 'agent-launcher', 'C', {resource['name']: resource['epoch']},
                     ttl_ms=30000, max_ms=120000, estimated_ms=1000)
        try:
            grant = queue.dispatch()
            w.require(grant and grant['request_id'] == rid, 'Maintenance grant unavailable')
        except BaseException:
            # Cancel only this request. Do not consume or release a foreign grant.
            try:
                queue.cancel(rid, 'agent-launcher')
            except QueueError:
                pass
            raise
    done = threading.Event()

    def heartbeat():
        while not done.wait(8):
            try:
                queue.heartbeat(rid, grant['token'])
            except QueueError:
                return  # Reconnecting the guest revokes the old session's lease.

    thread = threading.Thread(target=heartbeat, daemon=True)
    completed = False
    verdict = {'succeeded': True}
    started = False
    try:
        thread.start()
        started = True
        yield verdict
        completed = verdict['succeeded'] is True
    finally:
        done.set()
        if started:
            thread.join()
        status = 'succeeded' if completed else 'failed'
        try:
            queue.check(rid, grant['token'])
        except QueueError:
            current = next(v for v in queue.status()['resources'] if v['name'] == resource['name'])
            w.require(current['epoch'] != resource['epoch'], 'Maintenance lease lost without a session transition')
            outcome = 'revoked-by-session-transition'
        else:
            notes = (['launcher operation finished; see result.json'] if status == 'succeeded'
                     else ['launcher operation failed; see local diagnostics'])
            queue.finish(rid, grant['token'], status, notes)
            outcome = 'released'
        w.save(output / 'maintenance.json', dict(requestId=rid, outcome=outcome, operationStatus=status))


def run(config, output, guest_root, operation, release=None):
    if not re.fullmatch(r'[A-Za-z]:\\[A-Za-z0-9_\\-]+', guest_root):
        raise ValueError('Invalid guest launcher root')
    if operation not in ('restart', 'update'):
        raise ValueError('Invalid operation')
    if (operation == 'update') != (release is not None):
        raise ValueError('Only update requires a staged release descriptor')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    cfg, profile, _ = w.read_config(Path(config))
    guard = w.HostGuard(cfg, profile, output)
    # Updates use only a free control resource, never interrupt an active experiment.
    queue = w.AccessQueue(guard.plan['database']).status()
    resource = next(v for v in queue['resources'] if v['name'] == guard.plan['resource'])
    w.require(not resource['blocked'] and resource['holder'] is None and
              not any(v['state'] in ('queued', 'active', 'cleanup') for v in queue['requests']), 'Control queue occupied')
    w.save(output / 'before.json', w.sanitize(guard.status()))
    request = dict(id=uuid.uuid4().hex, operation=operation)
    if release is not None:
        request['release'] = release
    w.save(output / 'request.json', request)
    sha = w.digest((output / 'request.json').read_bytes())
    incoming = guest_root + '\\request-' + request['id'] + '.tmp'
    with maintenance_lease(guard, output) as verdict:
        with GuestSession(Path(cfg['vmrun']), guard.native.vmx, guard.check) as guest:
            w.save(output / 'stop.json', w.sanitize(guard.client.request('/api/stop', method='POST', payload={})))
            guest.run('copyFileFromHostToGuest', str((output / 'request.json').resolve()), incoming)
            # Atomic publication: the launcher never reads a partly transferred request.
            script = ("$ErrorActionPreference='Stop';$p='" + incoming + "';$r='" + guest_root +
                      "';if([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($p))).Replace('-','') -ne '" + sha + "'){throw 'request-hash-mismatch'};"
                      "[IO.File]::Move($p,($r+'\\request.json'));$f=$r+'\\results\\" + request['id'] +
                      ".json';$end=[DateTime]::UtcNow.AddSeconds(95);while(-not(Test-Path -LiteralPath $f)){"
                      "if([DateTime]::UtcNow -ge $end){throw 'launcher-response-timeout'};Start-Sleep -Milliseconds 200}")
            guest.powershell(script, timeout=110)
            guest.copy_from_guest(guest_root + '\\results\\' + request['id'] + '.json', output / 'result.json')
            guest.copy_from_guest(guest_root + '\\launcher-state.json', output / 'launcher-state.json')
        result = w.load(output / 'result.json')
        w.require(result['id'] == request['id'], 'Launcher response identity mismatch')
        w.require(type(result.get('success')) is bool, 'Launcher success flag is invalid')
        verdict['succeeded'] = result['success']
        if operation in ('start', 'restart', 'update') and result['success']:
            deadline = time.monotonic() + 30
            while True:
                try:
                    state = guard.status()
                    w.require(state['guest'].get('gracefulShutdownVersion') == 1, 'Managed guest capability missing')
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.5)
            w.save(output / 'after.json', w.sanitize(state))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('restart', 'update'))
    parser.add_argument('--config', type=Path, default=ROOT / 'artifacts/xyz-workflow.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guest-root', default=r'C:\RIFT_TRANSFER\RiftReader2Control\managed')
    parser.add_argument('--release', type=Path, help='JSON containing exactly release and sha256; already staged in guest')
    args = parser.parse_args()
    result = run(args.config, args.output, args.guest_root, args.operation,
                 w.load(args.release) if args.release else None)
    print(json.dumps(result))
    raise SystemExit(0 if result['success'] else 2)
