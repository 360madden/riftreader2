"""Read a VMware lab's guest process list without invoking guest Codex."""
import argparse
from datetime import datetime, timezone
import json
import re

from lab_codex import LabCodex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', choices=('lab1', 'lab2'), required=True)
    args = parser.parse_args()
    lab = LabCodex()
    _, _, config, settings = lab._configuration(args.lab)
    output = lab.run_root / '.doctor'
    native = lab._native(config, settings, output)
    identity = lab.collect_identity(native)
    with lab._session(config, settings, identity, output) as guest:
        data = guest.run('listProcessesInGuest')
    lines = data.splitlines()
    if not lines or not re.fullmatch(r'Process list: \d+', lines[0].strip()):
        raise RuntimeError('unexpected-guest-process-format')
    commands = []
    for line in lines[1:]:
        match = re.search(r'\bcmd=(.*)$', line)
        if not match:
            raise RuntimeError('unexpected-guest-process-line')
        commands.append(match.group(1).strip())
    if len(commands) != int(lines[0].split(':', 1)[1]):
        raise RuntimeError('incomplete-guest-process-list')
    print(json.dumps({'lab': args.lab, 'checkedUtc': datetime.now(timezone.utc).isoformat(),
                      'guestProcessList': 'success', 'processCount': len(commands),
                      'riftProcessPresent': any(re.search(r'(?i)(?:^|[\\/\s"])rift(?:_x64)?\.exe(?=$|[\s"])', c) for c in commands),
                      'vmx': identity['vmx'], 'vmPid': identity['pid'],
                      'scope': 'guest process inventory; no Codex or game actions'}, indent=2))


if __name__ == '__main__':
    main()
