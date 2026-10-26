"""Prepare a hash-pinned guest launcher/release ZIP; no deployment or game input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(executable, output, guest_root):
    executable, output = Path(executable), Path(output)
    if not re.fullmatch(r'[A-Za-z]:\\[A-Za-z0-9_\\-]+', guest_root):
        raise ValueError('Use a plain absolute guest directory without spaces or shell characters')
    data = executable.read_bytes()
    if not data or len(data) > 256 * 1024 * 1024:
        raise ValueError('Invalid executable size')
    sha = hashlib.sha256(data).hexdigest().upper()
    release = dict(release='agent-' + sha[:12].lower(), sha256=sha)
    source = ROOT / 'scripts/Start-GuestAgentLauncher.ps1'
    launcher = source.read_bytes()
    launcher_sha = hashlib.sha256(launcher).hexdigest().upper()
    output.mkdir(parents=True, exist_ok=False)
    script = guest_root + r'\Start-GuestAgentLauncher.ps1'
    command = ('powershell.exe -NoProfile -WindowStyle Hidden -Command "'
        "$ErrorActionPreference='Stop';$p='" + script + "';if([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($p))).Replace('-','') -ne '"
        + launcher_sha + "'){throw 'launcher-hash-mismatch'};& ([scriptblock]::Create([IO.File]::ReadAllText($p))) -Root '"
        + guest_root + "'")
    with zipfile.ZipFile(output / 'agent.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr('releases/' + release['release'] + '/RiftReader2.Live.exe', data)
        archive.writestr('Start-GuestAgentLauncher.ps1', launcher)
        archive.writestr('Launch-Agent.cmd', '@echo off\r\n' + command + '"\r\n')
        archive.writestr('Install-Startup.cmd', '@echo off\r\n' + command + ' -InstallStartup"\r\n')
        archive.writestr('current.json', json.dumps(release))
    result = dict(release=release, guestRoot=guest_root, launcherSha256=launcher_sha,
                  archiveSha256=hashlib.sha256((output / 'agent.zip').read_bytes()).hexdigest().upper(),
                  archiveBytes=(output / 'agent.zip').stat().st_size)
    (output / 'release.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guest-root', default=r'C:\RIFT_TRANSFER\RiftReader2Control\managed')
    args = parser.parse_args()
    print(json.dumps(prepare(args.executable, args.output, args.guest_root)))
