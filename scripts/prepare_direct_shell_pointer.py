#!/usr/bin/env python3
"""Prepare immutable direct-PowerShell native pointer plans. Never accesses VM."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

class PlanError(ValueError):
    pass

def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")

def prepare(target, name, guest_exe):
    if not isinstance(target, dict) or set(target) != {"processId", "processStartUtcTicks", "executableSha256"}:
        raise PlanError("exact process identity required")
    pid, ticks, digest = (target[k] for k in ("processId", "processStartUtcTicks", "executableSha256"))
    if type(pid) is not int or not 1 <= pid < 2**31 or type(ticks) is not int or ticks <= 0 or not isinstance(digest, str) or not re.fullmatch("[A-F0-9]{64}", digest):
        raise PlanError("invalid process identity")
    if not isinstance(name, str) or not re.fullmatch("[A-Za-z0-9-]{1,24}", name):
        raise PlanError("invalid output name")
    if not isinstance(guest_exe, str) or not guest_exe.startswith("C:\\") or not guest_exe.endswith("\\RiftReader2.Live.exe") or len(guest_exe) > 150 or " " in guest_exe or any(c in guest_exe for c in "\"&|<>%^$\r\n" + chr(96)):
        raise PlanError("invalid native executable path")
    request = {"schemaVersion": 1, "evidenceKind": "native-pointer-follow-request/1", "target": dict(target), "rootRva": "0x32E0200", "offsets": ["0x0"], "terminalByteLength": 816, "maxDurationMilliseconds": 5000}
    data = encode(request)
    payload = base64.b64encode(data).decode("ascii")
    prefix = "rr2-" + name
    path = "$env:TEMP\\" + prefix
    commands = []
    for i in range(0, len(payload), 64):
        command = "Set-Content" if i == 0 else "Add-Content"
        commands.append(f'{command} -Path "{path}.b64" -Value "{payload[i:i+64]}" -Encoding ascii')
    commands.extend([
        f'certutil -f -decode "{path}.b64" "{path}.json"',
        f'Get-FileHash "{path}.json" -Algorithm SHA256',
        f'& "{guest_exe}" follow-pointer --request "{path}.json" --output "{path}-report.json"',
    ])
    if len(commands) > 20 or max(map(len, commands)) > 220:
        raise PlanError("command budget exceeded")
    return request, commands

def publish(folder, request, commands):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise PlanError("output directory must already exist")
    manifest = {"schemaVersion": 1, "evidenceKind": "direct-powershell-pointer-transport-plan/1",
                "requestSha256": hashlib.sha256(encode(request)).hexdigest().upper(),
                "target": request["target"], "commandCount": len(commands),
                "maxCommandLength": max(map(len, commands)),
                "requiresVerifiedPowerShellPrompt": True, "requiresExclusiveVMConsole": True,
                "verifyGuestHashBeforeReader": True, "readerExecuted": False,
                "qualification": "candidate-only"}
    data = [("request.json", encode(request)), ("manifest.json", encode(manifest))]
    data += [(f"step-{i:02}.json", encode({"schemaVersion": 1, "text": cmd})) for i, cmd in enumerate(commands, 1)]
    if any((folder / name).exists() for name, _ in data):
        raise PlanError("plan outputs already exist")
    staged, published = [], []
    try:
        for name, contents in data:
            with tempfile.NamedTemporaryFile(mode="wb", dir=folder, prefix=".rr2-", delete=False) as f:
                stage = Path(f.name)
                staged.append(stage)
                f.write(contents); f.flush(); os.fsync(f.fileno())
            output = folder / name
            os.link(stage, output)
            published.append(output)
    except BaseException:
        for p in published: p.unlink(missing_ok=True)
        raise
    finally:
        for p in staged: p.unlink(missing_ok=True)
    return manifest

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("pid", "start-ticks", "build", "name", "guest-exe", "out-dir"):
        p.add_argument("--" + arg, required=True)
    args = p.parse_args(argv)
    try:
        req, commands = prepare({"processId": int(args.pid),
            "processStartUtcTicks": int(args.start_ticks),
            "executableSha256": args.build}, args.name, args.guest_exe)
        result = publish(Path(args.out_dir), req, commands)
    except (PlanError, ValueError, OSError) as exc:
        print("Direct shell plan rejected: " + str(exc))
        return 2
    print(json.dumps({"prepared": True, "requestSha256": result["requestSha256"], "steps": len(commands), "readerExecuted": False}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
