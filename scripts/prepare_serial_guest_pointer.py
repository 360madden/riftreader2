#!/usr/bin/env python3
"""Prepare fail-closed, *single-action* guest Run plans for a known pointer.

The source request is exact and cryptographically pinned. This program NEVER
controls a VM. Each generated plan is one separately verifiable VNC action;
do not batch the plans into one uninterrupted input stream.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

BUILD_RE = re.compile(r"[0-9A-F]{64}\Z")
NAME_RE = re.compile(r"[A-Za-z0-9-]{1,24}\Z")
RVA_RE = re.compile(r"0x(?:0|[1-9A-F][0-9A-F]{0,14})\Z")
MAX_COMMAND = 180
CHUNK = 64
MAX_STEPS = 20


class TransportPlanError(ValueError):
    pass


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def build(target, basename, guest_exe,
          root_rva="0x32E0200", terminal_bytes=816):
    if not isinstance(target, dict) or set(target) != {
            "processId", "processStartUtcTicks", "executableSha256"}:
        raise TransportPlanError("target must have exact PID/start/build keys")
    pid, ticks, sha = (target[k] for k in
                       ("processId", "processStartUtcTicks", "executableSha256"))
    if (type(pid) is not int or not 1 <= pid < 2 ** 31 or
            type(ticks) is not int or ticks <= 0 or
            not isinstance(sha, str) or not BUILD_RE.fullmatch(sha)):
        raise TransportPlanError("invalid exact target identity")
    if not isinstance(basename, str) or not NAME_RE.fullmatch(basename):
        raise TransportPlanError("invalid or unsafe temporary basename")
    if not isinstance(root_rva, str) or not RVA_RE.fullmatch(root_rva):
        raise TransportPlanError("invalid canonical RVA")
    if type(terminal_bytes) is not int or not 812 <= terminal_bytes <= 1024:
        raise TransportPlanError("terminal length cannot cover known XYZ offsets")
    if (not isinstance(guest_exe, str) or not guest_exe.startswith("C:\\")
            or not guest_exe.lower().endswith("\\riftreader2.live.exe")
            or any(c in guest_exe for c in '"&|<>%^\r\n')
            or len(guest_exe) > 145 or " " in guest_exe):
        raise TransportPlanError("guest executable must be a short absolute path without shell metacharacters")

    request = {
        "schemaVersion": 1,
        "evidenceKind": "native-pointer-follow-request/1",
        "target": target,
        "rootRva": root_rva,
        "offsets": ["0x0"],
        "terminalByteLength": terminal_bytes,
        "maxDurationMilliseconds": 5000,
    }
    content = canonical(request)
    encoded = base64.b64encode(content).decode("ascii")
    basename = "rr2-" + basename
    b64 = f"%TEMP%\\{basename}.b64"
    req = f"%TEMP%\\{basename}.json"
    result = f"%TEMP%\\{basename}-result.json"
    commands = []
    for offset in range(0, len(encoded), CHUNK):
        part = encoded[offset:offset + CHUNK]
        direction = ">" if offset == 0 else ">>"
        commands.append(f"cmd.exe /c echo {part} {direction} {b64}")
    commands.append(f"cmd.exe /c certutil -f -decode {b64} {req}")
    # Stop here and verify the printed SHA-256 against requestSha256 in the
    # pinned manifest before invoking any native process reader.
    commands.append(f"cmd.exe /k certutil -hashfile {req} SHA256")
    commands.append(f"cmd.exe /k {guest_exe} follow-pointer --request {req} --output {result}")
    if len(commands) > MAX_STEPS or any(len(c) > MAX_COMMAND for c in commands):
        raise TransportPlanError("bounded guest input command limit exceeded")
    return request, commands


def publish(folder, request, commands):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise TransportPlanError("output directory must already exist")
    manifest = {
        "schemaVersion": 1,
        "evidenceKind": "guest-serial-pointer-transport-plan/1",
        "requestSha256": hashlib.sha256(canonical(request)).hexdigest().upper(),
        "request": request,
        "commandCount": len(commands),
        "maximumCommandChars": max(map(len, commands)),
        "executionRule": "one bootstrap invocation per action, verify guest outcome before continuing",
        "nativeResult": "unverified-until-real-guest-report",
        "lastCommandRequiresDecodedRequestVerification": True,
        "processIdentityMustBeReverifiedBeforeRun": True,
        "neverTreatWindowsRunSuccessAsNativeSuccess": True,
    }
    output = [("request.json", canonical(request)),
              ("manifest.json", canonical(manifest))]
    for index, command in enumerate(commands, 1):
        output.append((f"step-{index:02}.json", canonical({
            "schemaVersion": 1, "actions": [{
                "type": "windowsRunText", "text": command
            }]
        })))
    created = []
    temp_files = []
    try:
        if any((folder / name).exists() for name, _ in output):
            raise TransportPlanError("one or more output files already exist")
        for name, contents in output:
            destination = folder / name
            with tempfile.NamedTemporaryFile(
                mode="wb", delete=False, dir=folder, prefix=".rr2-staged-",
            ) as handle:
                path = Path(handle.name)
                temp_files.append(path)
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(path, destination)
            created.append(destination)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temp_files:
            path.unlink(missing_ok=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-ticks", type=int, required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--guest-exe", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        request, commands = build(
            {"processId": args.pid,
             "processStartUtcTicks": args.start_ticks,
             "executableSha256": args.build},
            args.name, args.guest_exe
        )
        manifest = publish(args.out_dir, request, commands)
        print(json.dumps({
            "prepared": True,
            "steps": len(commands),
            "maxCommandChars": manifest["maximumCommandChars"],
            "requestSha256": manifest["requestSha256"],
            "nativeVerified": False,
        }, separators=(",", ":")))
        return 0
    except (TransportPlanError, OSError) as error:
        print(f"Transport plan rejected: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
