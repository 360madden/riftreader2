"""Stage a hash-pinned RR2 Windows agent in one owned, idle VMware lab.

No agent/game restart, input, registration, or current.json mutation. The
separate guest_agent_launcher.py updater must activate the verified release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ensure_guest_agent import GUEST_ROOT
from scripts.guest_agent_launcher import (
    ManagedMaintenanceGuard, maintenance_guest_session, maintenance_lease,
)
from scripts.run_xyz_workflow import require, save, sanitize


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _preflight(root: str, release: str) -> str:
    r, name = _quoted(root), _quoted(release)
    return (
        "$ErrorActionPreference='Stop';"
        "$r=" + r + ";$n=" + name + ";"
        "$c=Get-Content -LiteralPath ($r+'\\current.json') -Raw|ConvertFrom-Json;"
        "$s=Get-Content -LiteralPath ($r+'\\launcher-state.json') -Raw|ConvertFrom-Json;"
        "if($s.state -cne 'running' -or $s.release.release -cne $c.release"
        " -or $s.release.sha256 -ine $c.sha256){throw 'active-descriptor-mismatch'};"
        "$old=$r+'\\releases\\'+$c.release+'\\RiftReader2.Live.exe';"
        "if((Get-FileHash -LiteralPath $old).Hash -ine $c.sha256){throw 'active-hash-mismatch'};"
        "$p=Get-Process -Id $s.agentPid -ErrorAction Stop;"
        "if($p.Path -ine $old -or $p.StartTime.ToUniversalTime().Ticks -ne $s.agentStartTicks)"
        "{throw 'active-process-mismatch'};"
        "if(Test-Path -LiteralPath ($r+'\\request.json')){throw 'launcher-busy'};"
        "if(Test-Path -LiteralPath ($r+'\\releases\\'+$n)){throw 'candidate-exists'};"
    )


def _finalize(root: str, release: str, sha: str, size: int, incoming: str,
              proof: str) -> str:
    r, n, src, out = map(_quoted, (root, release, incoming, proof))
    return (
        "$ErrorActionPreference='Stop';"
        "$r=" + r + ";$n=" + n + ";$src=" + src + ";$out=" + out + ";"
        "$current=Get-Content -LiteralPath ($r+'\\current.json') -Raw|ConvertFrom-Json;"
        "if(Test-Path -LiteralPath ($r+'\\request.json')){throw 'launcher-busy'};"
        "$d=$r+'\\releases\\'+$n;$target=$d+'\\RiftReader2.Live.exe';"
        "if(Test-Path -LiteralPath $d){throw 'candidate-exists'};"
        "if((Get-Item -LiteralPath $src).Length -ne " + str(size) +
        " -or (Get-FileHash -LiteralPath $src).Hash -cne '" + sha +
        "'){throw 'incoming-hash-mismatch'};"
        "New-Item -ItemType Directory -Path $d -ErrorAction Stop|Out-Null;"
        "[IO.File]::Move($src,$target);"
        "if((Get-Item -LiteralPath $target).Length -ne " + str(size) +
        " -or (Get-FileHash -LiteralPath $target).Hash -cne '" + sha +
        "'){throw 'staged-hash-mismatch'};"
        "$after=Get-Content -LiteralPath ($r+'\\current.json') -Raw|ConvertFrom-Json;"
        "if($after.release -cne $current.release -or $after.sha256 -ine $current.sha256)"
        "{throw 'active-release-changed'};"
        "$v=@{release=$n;sha256='" + sha + "';bytes=" + str(size) +
        ";stageOnly=$true};"
        "[IO.File]::WriteAllText($out,($v|ConvertTo-Json -Compress))"
    )


def stage(lab: str, executable: Path, output: Path) -> dict:
    require(lab in ('lab1', 'lab2'), 'Invalid managed lab')
    executable = executable.resolve(strict=True)
    require(executable.is_file(), 'Agent executable missing')
    size = executable.stat().st_size
    require(0 < size <= 256 * 1024 * 1024, 'Invalid agent size')
    with executable.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest().upper()
    release = 'agent-' + sha[:12].lower()
    require(bool(re.fullmatch(r'agent-[a-f0-9]{12}', release)), 'Invalid release')
    output.mkdir(parents=True, exist_ok=False)
    guard = ManagedMaintenanceGuard(lab, output)
    prior = guard.status()
    guest = prior['guest']
    require(prior['host']['connected'] is True and guest['armed'] is False
            and guest['busy'] is False and guest['recoveryRequired'] is False
            and guest['desktopInputsDown'] == [], 'Live agent not safely idle')
    save(output / 'before.json', sanitize(prior))
    unique = uuid.uuid4().hex
    incoming = GUEST_ROOT + '\\stage-agent-' + unique + '.incoming'
    proof = GUEST_ROOT + '\\stage-proof-' + unique + '.json'
    descriptor = {'release': release, 'sha256': sha}
    with maintenance_lease(guard, output):
        with maintenance_guest_session(guard.vmrun, guard, lab) as vm:
            require(vm.credential_source == 'cache', 'Cached guest credential required')
            vm.powershell(_preflight(GUEST_ROOT, release), timeout=60)
            vm.run('copyFileFromHostToGuest', str(executable), incoming, timeout=100)
            vm.powershell(_finalize(GUEST_ROOT, release, sha, size, incoming, proof),
                          timeout=45)
            vm.copy_from_guest(proof, output / 'guest-proof.json', timeout=45)
        after = guard.status()
        require(after['host']['instanceId'] == prior['host']['instanceId']
                and after['guest']['instanceId'] == guest['instanceId']
                and after['guest']['armed'] is False and after['guest']['busy'] is False
                and after['guest']['desktopInputsDown'] == []
                and after['guest']['recoveryRequired'] is False,
                'Agent changed during staging')
        save(output / 'after.json', sanitize(after))
    observed = json.loads((output / 'guest-proof.json').read_text(encoding='utf-8-sig'))
    require(observed['release'] == release and observed['sha256'] == sha
            and observed['bytes'] == size and observed['stageOnly'] is True,
            'Guest staging proof mismatch')
    save(output / 'update-descriptor.json', descriptor)
    return {'state': 'staged', 'lab': lab, 'release': release, 'sha256': sha,
            'bytes': size, 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--managed-lab', choices=('lab1', 'lab2'), required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.managed_lab, args.executable, args.output)))
