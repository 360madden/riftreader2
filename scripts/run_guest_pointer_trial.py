"""Guarded serial native-pointer trial for V15 normal exit -> V16 recovery.

Consumes two already prepared, SHA-pinned PowerShell pointer transport plans.
This module never stops or launches a coordinator. A separate service controls
one-use claim/upload listeners. Each console action is separately receipted,
but its guest command is NOT thereby declared complete.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.run_guest_inline_trial import (
    shell_foreground, sha,
)
from scripts.prepare_native_host_handover import authority_snapshot
from scripts.vm_console_native import (
    Blocked, ControlMutex, DEFAULT_VMRUN, _capture, _type_text,
    collect_identity, connect, validate_config,
)

HOME = ROOT / "artifacts" / "update-recovery-20261023-01"
PLAN = HOME / "coordinated-host-plan-v16.json"
A = HOME / "rr2-v16-pointer-a-oct24-01"
B = HOME / "rr2-v16-pointer-b-oct24-01"
PREFIX = "rr2-v16-pointer-guest-step-"
GAME_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
BUNDLE_SHA = "70553F4CE4A9C73C5043CCA16622084734E6C69B1C9E49132C9F622A5F821E4E"
REQUEST_SHA = "C6B90D59DCF472E50DCEEAE6992AED98446754D466AE2AFA1AE9510EFD5BE9EE"
MANIFEST_SHA = "CE46667F1C6E8E750F7B761F2E9FB517EB786E9BCD2C30B5F363362F56F8EAC1"
PLAN_SHA = None  # A normal same-epoch V16 handover plan is verified by its contents and VM identity.
PID = 6940
TICKS = 639284177321390013
BINARY = r"C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad\RiftReader2.Live.exe"
CLAIM_ROUTE = "/rr2-native-pointer-zip-claim-oct24-01"
UPLOAD_ROUTE = "/rr2-native-pointer-oct24-01-report.zip"
CONFIG_SHA = "90F2B8AB6F575C776941F0B160FF4CE1D8BC8575408975FE7645ADDED5325A2C"


def checked_request(folder: Path, suffix: str) -> list[str]:
    req_file = folder / "request.json"
    manifest_file = folder / "manifest.json"
    if sha(req_file.read_bytes()) != REQUEST_SHA or sha(manifest_file.read_bytes()) != MANIFEST_SHA:
        raise Blocked("pointer-source-request-or-transport-manifest-changed")
    request = json.loads(req_file.read_bytes())
    manifest = json.loads(manifest_file.read_bytes())
    target = {
        "processId": PID, "processStartUtcTicks": TICKS,
        "executableSha256": GAME_SHA,
    }
    if (request != {
            "schemaVersion": 1, "evidenceKind": "native-pointer-follow-request/1",
            "target": target, "rootRva": "0x32E0200", "offsets": ["0x0"],
            "terminalByteLength": 816, "maxDurationMilliseconds": 5000,
            } or manifest.get("requestSha256") != REQUEST_SHA
            or manifest.get("target") != target or manifest.get("commandCount") != 10
            or manifest.get("readerExecuted") is not False):
        raise Blocked("pointer-transport-request-or-manifest-contract-changed")
    commands = []
    for index in range(1, 11):
        p = folder / f"step-{index:02}.json"
        stage = json.loads(p.read_bytes())
        cmd = stage.get("text")
        if (stage.get("schemaVersion") != 1 or type(cmd) is not str
                or not cmd.isascii() or len(cmd) > 220
                or "\n" in cmd or "\r" in cmd):
            raise Blocked("pointer-guest-step-unbounded-or-invalid")
        commands.append(cmd)
    if suffix not in ("a", "b"):
        raise Blocked("invalid-guest-pointer-step-suffix")
    expected_final = (
        f'& "{BINARY}" follow-pointer --request '
        f'"$env:TEMP\\rr2-v16ptr-{suffix}.json" '
        f'--output "$env:TEMP\\rr2-v16ptr-{suffix}-report.json"')
    if commands[-1] != expected_final:
        raise Blocked("pointer-guest-binary-or-final-command-changed")
    # The original manifest pins the request, not every stage body. Rebuild the
    # canonical transport locally so even an intermediate command cannot drift.
    from scripts.prepare_direct_shell_pointer import prepare
    expected_request, expected_commands = prepare(target, "v16ptr-" + suffix, BINARY)
    if request != expected_request or commands != expected_commands:
        raise Blocked("pointer-transport-step-source-drift")
    return commands


def commands() -> list[tuple[str, str]]:
    a = checked_request(A, "a")
    b = checked_request(B, "b")
    request_a = '"$env:TEMP\\rr2-v16ptr-a.json"'
    request_b = '"$env:TEMP\\rr2-v16ptr-b.json"'
    result = [
        ("binary", "$exe='" + BINARY + "'"),
        ("binary", "$eh=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash"),
        ("binary", "$exeok=($eh -eq '" + BUNDLE_SHA + "');Write-Output ('EXE_GATE='+$exeok)"),
    ]
    for suffix, entries in (("a", a), ("b", b)):
        for position, command in enumerate(entries, 1):
            if position == 10:
                request_path = request_a if suffix == "a" else request_b
                guard = ("$exeok -and " + ("$aok -and " if suffix == "b" else "")
                         + "((Get-FileHash -LiteralPath " + request_path
                         + " -Algorithm SHA256).Hash -eq '" + REQUEST_SHA + "')")
                command = ("if(" + guard + "){" + command
                           + ";Write-Output ('RUN_" + suffix.upper()
                           + "_EXIT='+$LASTEXITCODE)}")
            result.append(("pointer-" + suffix, command))
        report_path = "$env:TEMP\\rr2-v16ptr-" + suffix + "-report.json"
        result.append(("verify-" + suffix,
                       "$" + suffix + "ok=($exeok -and (Test-Path "
                       + '"' + report_path + '"'
                       + ") -and ((Get-Content -LiteralPath "
                       + '"' + report_path + '"'
                       + " -Raw|ConvertFrom-Json).resolution.status -eq 'complete'));"
                       "Write-Output ('PTR_" + suffix.upper() + "_GATE=' + $"
                       + suffix + "ok)"))
    result.extend([
        ("archive", "$z=Join-Path $env:TEMP 'rr2-v16ptr-oct24-01.zip'"),
        ("archive",
         "if($aok -and $bok -and !(Test-Path $z)){Compress-Archive -LiteralPath "
         '"$env:TEMP\\rr2-v16ptr-a.json","$env:TEMP\\rr2-v16ptr-a-report.json",'
         '"$env:TEMP\\rr2-v16ptr-b-report.json" -DestinationPath $z -CompressionLevel Optimal}'),
        ("archive", "$zs=(Get-FileHash -LiteralPath $z -Algorithm SHA256).Hash;"
         "$zn=(Get-Item -LiteralPath $z).Length;Write-Output ('PTR_ZIP_SHA='+$zs+' BYTES='+$zn)"),
        ("claim", "$claim='RR2PTRZIP1|'+$zs+'|'+$zn+'|" + str(PID) + "|"
         + str(TICKS) + "|" + GAME_SHA + "|" + BUNDLE_SHA + "'"),
        ("claim", "$claimUrl='http://192.168.56.1:8765" + CLAIM_ROUTE + "'"),
        ("claim", "if($aok -and $bok -and $zn -le 2097152){"
         "$r=Invoke-WebRequest -UseBasicParsing -Uri $claimUrl -Method Post "
         "-ContentType 'text/plain' -Body $claim;"
         "Write-Output ('PTR_CLAIM_HTTP='+$r.StatusCode)}"),
        ("upload", "$uploadUrl='http://192.168.56.1:8765" + UPLOAD_ROUTE + "'"),
        ("upload", "if($aok -and $bok -and (Test-Path $z)){"
         "$r=Invoke-WebRequest -UseBasicParsing -Uri $uploadUrl -Method Post "
         "-ContentType 'application/octet-stream' -InFile $z;"
         "Write-Output ('PTR_UPLOAD_HTTP='+$r.StatusCode)}"),
    ])
    if (len(result) != 33 or any(
            len(command) > 490 or not command.isascii()
            or any(ord(char) < 32 for char in command)
            for _, command in result)):
        raise Blocked("guest-pointer-command-bound-or-count-invalid")
    return result


def parse_powershell(entries: list[tuple[str, str]]) -> dict:
    """Parse every intended guest command using Windows PowerShell 5.1 AST.

    Host-only: sends command bodies to a parser as JSON on stdin, never to a
    shell for execution, a guest process, a listener, or the VMware console.
    """
    executable = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if os.name != "nt" or not executable.is_file():
        raise Blocked("windows-powershell-parser-unavailable")
    ast_only = r"""
$ErrorActionPreference = 'Stop'
$commands = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
for ($index = 0; $index -lt $commands.Count; $index++) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput(
        [string]$commands[$index], [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        Write-Output ('PARSE_ERROR_STEP=' + ($index + 1))
        Write-Output ('PARSE_REASON=' + $errors[0].Message)
        Write-Output ('PARSE_LENGTH=' + ([string]$commands[$index]).Length)
        exit 2
    }
}
Write-Output ('PARSED=' + $commands.Count)
"""
    try:
        completed = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", ast_only],
            input=json.dumps([entry[1] for entry in entries]), capture_output=True,
            text=True, timeout=30, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise Blocked("guest-command-parser-unavailable") from error
    if completed.returncode != 0 or completed.stdout.strip() != f"PARSED={len(entries)}":
        marker = completed.stdout.strip()
        reason = marker if marker.startswith(("PARSE_ERROR_STEP=", "PARSED=")) else "parser-runtime-error"
        raise Blocked("guest-command-PowerShell-syntax-invalid:" + reason[:80])
    return {"state": "verified-host-powershell-ast-only",
            "parsedCommands": len(entries), "guestInputSent": False}


def maintenance() -> dict:
    prior_stop = HOME / "STOP-NATIVE-20261024-V15.request"
    prior_exit = HOME / "coordinated-host-v15-exited.json"
    prior_process = HOME / "coordinated-host-v15-process.json"
    if not prior_stop.is_file() or not prior_exit.is_file() or not prior_process.is_file():
        raise Blocked("v15-normal-stop-or-exit-not-verified")
    if (HOME / "coordinated-host-v16-process.json").exists():
        raise Blocked("v16-already-started-must-not-enter-console")
    previous = json.loads(prior_process.read_bytes())
    exited = json.loads(prior_exit.read_bytes())
    if (previous.get("pid") != 27856
            or exited.get("pid") != previous["pid"]
            or previous.get("vmIdentity") is None):
        raise Blocked("previous-coordinator-process-identity-differs")
    plan = json.loads(PLAN.read_bytes())
    if (plan.get("configSha256", "").upper() != CONFIG_SHA
            or plan.get("expectedWindowsSession") != 2
            or plan.get("vmIdentity") != previous["vmIdentity"]):
        raise Blocked("v16-plan-config-or-vm-identity-changed")
    blocked, holder, cleanup = authority_snapshot(
        Path(plan["database"]), plan["resource"])
    if blocked != 1 or holder is not None or cleanup is not None:
        raise Blocked("canonical-vm-authority-not-quarantined")
    return plan


def _step_receipt(n: int) -> Path:
    return HOME / (PREFIX + f"{n:02}") / "receipt.json"


def require_previous_step(n: int, entries: list[tuple[str, str]],
                          vm: dict) -> None:
    if n == 0:
        return
    previous = n - 1
    last = _step_receipt(previous)
    if not last.is_file():
        raise Blocked("previous-guest-console-action-not-receipted")
    data = json.loads(last.read_bytes())
    command_sha = (None if previous == 0 else
                   sha(entries[previous - 1][1].encode("ascii")))
    stage = "bootstrap" if previous == 0 else entries[previous - 1][0]
    if (data.get("schemaVersion") != 1
            or data.get("purpose") != "v16-exact-native-pointer-guest-action"
            or data.get("status") != "console-action-completed"
            or data.get("step") != previous
            or data.get("stage") != stage
            or data.get("commandSha256") != command_sha
            or data.get("requestSha256") != REQUEST_SHA
            or data.get("vmIdentity") != vm
            or data.get("mutexExclusive") is not True
            or data.get("consoleActionCompleted") is not True
            or data.get("guestCommandCompletionVerified") is not False):
        raise Blocked("previous-guest-console-action-not-receipted")


def require_claim_received(plan: dict) -> None:
    from scripts import run_guest_pointer_service as service
    service.claim_digest(plan)  # Exact same-VM one-use service + guest ZIP claim.


def require_upload_received(plan: dict) -> None:
    from scripts import run_guest_pointer_service as service
    service.upload_received(plan)  # Both SHA-bound receipts and actual ZIP.


def require_abort_quiescence() -> None:
    """Do not close a guest shell while either one-use receiver is still alive."""
    from scripts import run_guest_pointer_service as service
    for phase in service.SERVER_FILES:
        paths = service.paths_for(phase)
        if paths["process"].exists() and not paths["exit"].is_file():
            raise Blocked("one-use-pointer-service-not-finished-before-abort")
    if service._listener_rows():
        raise Blocked("one-use-pointer-listener-still-present-before-abort")
    if not (HOME / (PREFIX + "00")).is_dir():
        raise Blocked("v16-guest-shell-bootstrap-not-attempted")


def execute(n: int | None, close: bool = False, abort: bool = False) -> dict:
    if close and abort:
        raise Blocked("guest-shell-success-close-and-abort-mutually-exclusive")
    entries = commands()
    if not abort and (HOME / "rr2-v16-pointer-guest-abort-01" / "receipt.json").exists():
        raise Blocked("v16-guest-pointer-trial-already-aborted")
    if not (close or abort) and (n is None or not 0 <= n <= len(entries)):
        raise Blocked("guest-pointer-step-out-of-plan")
    plan = maintenance()
    if not (close or abort):
        require_previous_step(n, entries, plan["vmIdentity"])
        if n == 31:
            from scripts.run_guest_pointer_service import service_started
            service_started("claim", plan)
        if n >= 32:
            require_claim_received(plan)
        if n >= 33:
            from scripts.run_guest_pointer_service import service_started
            service_started("upload", plan)
    elif close:
        require_upload_received(plan)
    else:
        require_abort_quiescence()
    folder_name = ("rr2-v16-pointer-guest-close-01" if close else
                   "rr2-v16-pointer-guest-abort-01" if abort else
                   PREFIX + f"{n:02}")
    folder = HOME / folder_name
    folder.mkdir(exist_ok=False)
    vm = plan["vmIdentity"]
    config = validate_config(
        Path(vm["vmx"]), vm["port"], DEFAULT_VMRUN, folder, require_files=True)
    with ControlMutex(config.vmx):
        before = collect_identity(config)
        if before != vm:
            raise Blocked("v16-pointer-guest-vm-epoch-changed")
        client = connect(config)
        try:
            _capture(client, folder / "before.png")
            if close or abort:
                if not shell_foreground(folder / "before.png"):
                    raise Blocked("guest-PowerShell-no-longer-in-foreground")
                _type_text(client, "exit")
                client.keyPress("enter")
                time.sleep(2)
            elif n == 0:
                client.keyPress("super-r")
                time.sleep(0.25)
                _type_text(client, "powershell")
                client.keyPress("enter")
                time.sleep(2.5)
            else:
                if not shell_foreground(folder / "before.png"):
                    raise Blocked("guest-PowerShell-no-longer-in-foreground")
                stage, command = entries[n - 1]
                _type_text(client, command)
                client.keyPress("enter")
                delay = (14 if "follow-pointer --request" in command
                         else 10 if "Compress-Archive" in command
                         else 9 if "Invoke-WebRequest" in command
                         else 2)
                time.sleep(delay)
            _capture(client, folder / "screen.png")
            if not (close or abort) and not shell_foreground(folder / "screen.png"):
                raise Blocked("guest-PowerShell-focus-lost-after-action")
        finally:
            client.disconnect()
        if collect_identity(config) != before:
            raise Blocked("vm-epoch-changed-during-guest-action")
    step_stage = ("abort" if abort else "close" if close else
                  "bootstrap" if n == 0 else entries[n-1][0])
    record = {
        "schemaVersion": 1, "purpose": "v16-exact-native-pointer-guest-action",
        "status": "guest-shell-aborted" if abort else "console-action-completed",
        "step": "abort" if abort else "close" if close else n,
        "stage": step_stage,
        "commandSha256": None if close or abort or n == 0 else sha(entries[n-1][1].encode("ascii")),
        "requestSha256": REQUEST_SHA,
        "atUtc": datetime.now(timezone.utc).isoformat(),
        "vmIdentity": vm, "mutexExclusive": True,
        "guestCommandCompletionVerified": False,
        "consoleActionCompleted": True,
        "trialAbortedWithoutUploadProof": abort,
    }
    with (folder / "receipt.json").open("x", encoding="utf-8") as dest:
        json.dump(record, dest, indent=2)
        dest.write("\n")
    return {"status": record["status"], "step": record["step"],
            "stage": step_stage, "totalCommands": len(entries),
            "receipt": str(folder / "receipt.json"),
            "guestCommandCompletionVerified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choose = parser.add_mutually_exclusive_group(required=True)
    choose.add_argument("--preview", action="store_true")
    choose.add_argument("--parse-powershell", action="store_true")
    choose.add_argument("--step", type=int)
    choose.add_argument("--close", action="store_true")
    choose.add_argument("--abort", action="store_true")
    args = parser.parse_args()
    try:
        if args.parse_powershell:
            print(json.dumps(parse_powershell(commands())))
        elif args.preview:
            entries = commands()
            print(json.dumps({
                "state": "verified-offline-no-guest-input", "totalCommands": len(entries),
                "maxCommandLength": max(len(x[1]) for x in entries),
                "pointerSourceRequestSha256": REQUEST_SHA,
                "stages": [{"step": n + 1, "stage": x[0]}
                           for n, x in enumerate(entries)],
                "requiresV15NormalExit": True, "requiresV16Absent": True,
                "guestCommandCompletionVerified": False,
            }))
        else:
            print(json.dumps(execute(args.step, close=args.close, abort=args.abort)))
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, AssertionError) as error:
        print(json.dumps({"state": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
