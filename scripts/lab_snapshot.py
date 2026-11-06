"""Create or list VMware lab snapshots using cached VM credentials.

Requires pywinpty on Windows. The VM encryption password is supplied to vmcli's
private pseudoconsole, never placed in its arguments or emitted in reports.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

from lab_codex import load_config
from vmware_guest_session import _saved_secret

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '.local' / 'tools' / 'snapshot-python'))


def snapshot_names(vmrun, vmx, secret):
    args = [str(vmrun), '-T', 'ws', '-vp', secret, 'listSnapshots', str(vmx)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        args[4] = '[cleared]'
    if result.returncode:
        raise RuntimeError('snapshot-list-failed')
    lines = result.stdout.splitlines()
    if not lines or not re.fullmatch(r'Total snapshots: \d+', lines[0].strip()):
        raise RuntimeError('snapshot-list-unrecognized')
    names = [line.strip() for line in lines[1:] if line.strip()]
    if len(names) != int(lines[0].split(':', 1)[1]):
        raise RuntimeError('snapshot-list-incomplete')
    return names


def take(vmcli, vmx, name, secret, timeout):
    from winpty import PtyProcess
    process = PtyProcess.spawn([str(vmcli), str(vmx), 'Snapshot', 'Take',
                                '--memory', name])
    chunks = queue.Queue()

    def read_output():
        try:
            while True:
                chunks.put(process.read(4096))
        except EOFError:
            pass
        finally:
            chunks.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + timeout
    output = ''
    sent = False
    ended = False
    while time.monotonic() < deadline:
        try:
            chunk = chunks.get(timeout=min(1, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if chunk is None:
            ended = True
            break
        output = (output + chunk)[-65536:]
        if not sent and 'encrypted virtual machine password:' in output.lower():
            process.write(secret + '\r')
            sent = True
    if not ended:
        process.close(force=True)
        raise RuntimeError('snapshot-timeout-outcome-unknown')
    process.isalive()
    if not sent:
        raise RuntimeError('snapshot-password-prompt-not-seen')
    if process.exitstatus != 0:
        raise RuntimeError('snapshot-command-failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('list', 'take'))
    parser.add_argument('--lab', choices=('lab1', 'lab2'), required=True)
    parser.add_argument('--name', help='Required for take; unique snapshot name')
    args = parser.parse_args()
    if args.action == 'take' and (not args.name or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', args.name)):
        parser.error('take requires --name with 1-80 letters, numbers, dots, underscores or hyphens')
    _, _, config = load_config(ROOT / '.local' / 'lab-codex.json')
    vmx = Path(config['labs'][args.lab]['vmx'])
    vmrun = Path(config['vmrun'])
    vmcli = vmrun.with_name('vmcli.exe')
    secret = _saved_secret('VMware Encrypted VM: ' + str(vmx))
    try:
        before = snapshot_names(vmrun, vmx, secret)
        report = {'lab': args.lab, 'action': args.action, 'snapshots_before': before}
        if args.action == 'take':
            if args.name in before:
                raise RuntimeError('snapshot-name-already-exists')
            take(vmcli, vmx, args.name, secret, 600)
            after = snapshot_names(vmrun, vmx, secret)
            if args.name not in after:
                raise RuntimeError('snapshot-not-found-after-success')
            report.update(name=args.name, includes_memory=True, snapshots_after=after)
        report['status'] = 'verified'
        print(json.dumps(report, indent=2))
    finally:
        secret = None


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ImportError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(json.dumps({'status': 'failed', 'reason': reason}))
        raise SystemExit(1)
