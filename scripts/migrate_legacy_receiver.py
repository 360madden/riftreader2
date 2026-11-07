"""Explicit, per-lab migration of a verified legacy observation receiver.

Stops one pinned Task Scheduler instance. Does not send game input. A failure
may leave the old task stopped or removed; backups are retained, never restored
or used to affect another owner automatically. External task managers do not
participate in our lock and can race these checks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import ensure_receiver as receiver

BACKEND = ROOT / 'scripts' / 'Migrate-RR2LegacyReceiverTask.ps1'
LEGACY_REGISTRATIONS = Path(r'C:\work\workbridge-mcp\.local\helpers')


def backend(action, lab, **kwargs):
    executable = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    cmd = [str(executable), '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
           'RemoteSigned', '-File', str(BACKEND), '-Action', action, '-Lab', lab]
    for key, value in kwargs.items():
        cmd.extend(['-' + key, str(value)])
    result = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError('scheduler-' + action + '-failed')
    return json.loads(result.stdout.decode('utf-8-sig'))


def receipt_file(lab, identity, config):
    candidates = sorted((receiver.TASKS / lab).glob('*/process.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True)[:64]
    matches = []
    for path in candidates:
        try:
            if path.stat().st_size > 65536:
                continue
            value = json.loads(path.read_text(encoding='utf-8'))
            p = value['processIdentity']
            if (value['lab'] == lab and value['pid'] == identity['pid']
                and value['configSha256'] == receiver.sha(config)
                and value['sourceSha256'] == receiver.SOURCE_SHA256
                and value['entrySha256'] == receiver.sha(receiver.ENTRY)
                and int(p['startTicks']) + receiver.WINDOWS_TICKS_OFFSET == int(identity['processStartUtcTicks'])
                and p['image'].casefold() == identity['image'].casefold()):
                matches.append(path)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    if len(matches) != 1:
        raise RuntimeError('matching-receipt-not-unique')
    return matches[0]


def migrate(lab):
    if lab not in receiver.PORTS:
        raise RuntimeError('unknown-lab')
    config = receiver._config(lab)
    folder = ROOT / 'artifacts' / 'receiver-migrations' / (lab + '-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    stage = 'preflight'
    try:
        with receiver._launch_lock(lab):
            old = receiver._probe(lab, config)
            if old is None:
                raise RuntimeError('legacy-receiver-not-running')
            receiver._legacy_task_status(lab, old)
            receipt = receipt_file(lab, old, config)
            snap = backend('snapshot', lab)
            instances = snap['instances']
            if (len(instances) != 1 or instances[0]['pid'] != old['pid']
                    or not isinstance(instances[0]['guid'], str) or not instances[0]['guid']):
                raise RuntimeError('legacy-task-instance-mismatch')
            xml = folder / 'legacy-task.xml'
            xml.write_text(snap['xml'], encoding='utf-8', newline='')
            (folder / 'process.json').write_bytes(receipt.read_bytes())
            registration = LEGACY_REGISTRATIONS / ('rr2-receiver-' + lab) / 'registration.json'
            if registration.stat().st_size > 65536:
                raise RuntimeError('registration-too-large')
            registration_bytes = registration.read_bytes()
            if len(registration_bytes) > 65536:
                raise RuntimeError('registration-too-large')
            registration_sha = hashlib.sha256(registration_bytes).hexdigest().upper()
            (folder / 'registration.json').write_bytes(registration_bytes)
            (folder / 'registration.sha256').write_text(registration_sha + '\n', encoding='ascii')
            (folder / 'pin.json').write_text(json.dumps({'lab': lab, 'receiver': old,
                'instance': instances[0], 'receiptPath': str(receipt)}, indent=2), encoding='utf-8')
            # Re-run both the listener/receipt proof and the legacy source-task
            # proof after backups, before any mutation.
            if receiver._probe(lab, config) != old:
                raise RuntimeError('receiver-changed')
            receiver._legacy_task_status(lab, old)
            stage = 'stop'
            backend('stop', lab, XmlFile=xml, Instance=instances[0]['guid'],
                    PidValue=old['pid'], StartTicks=old['processStartUtcTicks'],
                    RegistrationSha256=registration_sha)
            stage = 'verify-exit-and-port'
            if receiver._port_owners(receiver.PORTS[lab]):
                raise RuntimeError('receiver-port-not-vacant')
            stage = 'delete'
            backend('delete', lab, XmlFile=xml, RegistrationSha256=registration_sha)
        # ensure acquires its own lock; holding it here would deadlock.
        stage = 'start'
        result = receiver.ensure(lab)
        if result['state'] != 'started':
            raise RuntimeError('new-receiver-not-started-by-migration')
        receiver._task_status(lab)
        if not receiver._matching_receipt(lab, result['receiver'], config):
            raise RuntimeError('new-receipt-mismatch')
        return {'lab': lab, 'state': 'migrated', 'backup': str(folder),
                'receiverPid': result['receiver']['pid']}
    except Exception as exc:
        raise RuntimeError(f'{stage}: {exc}; backup: {folder}') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', choices=('lab1', 'lab2'), required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(migrate(args.lab)))
        return 0
    except Exception as exc:
        print(json.dumps({'lab': args.lab, 'state': 'blocked', 'reason': str(exc)}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
