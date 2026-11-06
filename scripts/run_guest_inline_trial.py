"""Guarded, individually receipted guest steps for the V14 -> V15 typed-inline trial.

The previous coordinator must have exited normally and the canonical authority
must be quarantined. Each keyboard command requires an exclusive VMware mutex,
unchanged VM epoch, a verified PowerShell screenshot, and the prior receipt.
No game controls or memory writes are generated. Service listeners are started
separately and never concurrently.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_native_host_handover import authority_snapshot
from scripts.vm_console_native import (
    Blocked, ControlMutex, DEFAULT_VMRUN, _capture, _type_text,
    collect_identity, connect, validate_config,
)

HOME = ROOT / "artifacts" / "update-recovery-20261023-01"
REQUEST = HOME / "rr2-inline-oct24-01.request.json"
PLAN = HOME / "coordinated-host-plan-v15.json"
REQUEST_SHA = "B7CF3747A3DED22FAC9707E5EF6095DCEE9232329AE5F06BC7EFD23D3DAA145F"
GAME_SHA = "7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD"
BUNDLE_SHA = "484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716"
BUNDLE_BYTES = 74254755
PID = 6940
TICKS = 639284177321390013
GUEST_TEMP = "rr2-inline-oct24-01"
PREFIX = "rr2-inline-guest-step-"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def check_request() -> bytes:
    data = REQUEST.read_bytes()
    if sha(data) != REQUEST_SHA:
        raise Blocked("inline-request-content-changed")
    parsed = json.loads(data)
    if (parsed.get("schemaVersion") != 1
            or parsed.get("evidenceKind") != "native-typed-inline-capture-request/1"
            or parsed.get("target") != {
                "processId": PID, "processStartUtcTicks": TICKS,
                "executableSha256": GAME_SHA,
            }
            or parsed.get("startAddress") != "0x10000"
            or parsed.get("maxScanBytes") != 536870912
            or parsed.get("maxDurationMilliseconds") != 30000
            or parsed.get("maxRegionCount") != 32768
            or parsed.get("maxMatchCount") != 128
            or parsed.get("maxCopiedCandidates") != 8):
        raise Blocked("inline-request-exact-epoch-or-bounds-invalid")
    return data


def commands() -> list[tuple[str, str]]:
    payload = base64.b64encode(check_request()).decode("ascii")
    chunks = [payload[i:i + 108] for i in range(0, len(payload), 108)]
    result: list[tuple[str, str]] = [
        ("download", "$f=Join-Path $env:TEMP 'rr2-inline-oct24-01.exe'"),
        ("download", "$u='http://192.168.56.1:8765/rr2-typed-inline-oct24-01.exe'"),
        ("download", "if(!(Test-Path -LiteralPath $f)){Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $f}"),
        ("verify-exe", "$h=(Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash;$n=(Get-Item -LiteralPath $f).Length"),
        ("verify-exe", "$exeok=($h -eq '" + BUNDLE_SHA + "' -and $n -eq " + str(BUNDLE_BYTES) + ");Write-Output ('EXE_GATE='+$exeok)"),
        ("request", "$b='" + chunks[0] + "'"),
    ]
    result.extend(("request", "$b+='" + chunk + "'") for chunk in chunks[1:])
    result.extend([
        ("request", "$q=Join-Path $env:TEMP 'rr2-inline-oct24-01.request.json'"),
        ("request", "if($exeok -and !(Test-Path -LiteralPath $q)){[IO.File]::WriteAllBytes($q,[Convert]::FromBase64String($b))}"),
        ("verify-request", "$qh=(Get-FileHash -LiteralPath $q -Algorithm SHA256).Hash"),
        ("verify-request", "$ready=$exeok -and ($qh -eq '" + REQUEST_SHA + "');Write-Output ('REQ_GATE='+$ready)"),
        ("capture-1", "$d=Join-Path $env:TEMP '" + GUEST_TEMP + "';if($ready -and !(Test-Path -LiteralPath $d)){New-Item -ItemType Directory -Path $d|Out-Null}"),
        ("capture-1", "$out1=Join-Path $d 'run-01'"),
        ("capture-1", "if($ready -and !(Test-Path $out1)){& $f scout-copy-typed-native --request $q --output $out1;Write-Output ('RUN1_EXIT='+$LASTEXITCODE)}"),
        ("capture-1", "if($ready -and (Test-Path $out1) -and !(Test-Path (Join-Path $out1 'input.request.json'))){Copy-Item -LiteralPath $q -Destination (Join-Path $out1 'input.request.json')}"),
        ("capture-2", "$out2=Join-Path $d 'run-02'"),
        ("capture-2", "if($ready -and (Test-Path (Join-Path $out1 'index.json')) -and !(Test-Path $out2)){Start-Sleep -Seconds 8;& $f scout-copy-typed-native --request $q --output $out2;Write-Output ('RUN2_EXIT='+$LASTEXITCODE)}"),
        ("capture-2", "if($ready -and (Test-Path $out2) -and !(Test-Path (Join-Path $out2 'input.request.json'))){Copy-Item -LiteralPath $q -Destination (Join-Path $out2 'input.request.json')}"),
        ("archive", "$z=Join-Path $env:TEMP 'rr2-inline-oct24-01.zip'"),
        ("archive", "if($ready -and (Test-Path (Join-Path $out1 'input.request.json')) -and (Test-Path (Join-Path $out2 'input.request.json')) -and !(Test-Path $z)){Compress-Archive -LiteralPath $out1,$out2 -DestinationPath $z -CompressionLevel Optimal}"),
        ("archive", "$zs=(Get-FileHash -LiteralPath $z -Algorithm SHA256).Hash;$zn=(Get-Item -LiteralPath $z).Length;Write-Output ('ZIP_SHA='+$zs+' ZIP_BYTES='+$zn)"),
        ("claim", "$claim='RR2INLINEZIP1|'+$zs+'|'+$zn+'|" + str(PID) + "|" + str(TICKS) + "'"),
        ("claim", "$claim+='|" + GAME_SHA + "|" + BUNDLE_SHA + "'"),
        ("claim", "$claimUrl='http://192.168.56.1:8765/rr2-typed-inline-zip-claim-oct24-01'"),
        ("claim", "if($ready -and (Test-Path $z)){$r=Invoke-WebRequest -UseBasicParsing -Uri $claimUrl -Method Post -ContentType 'text/plain' -Body $claim;Write-Output ('CLAIM_HTTP='+$r.StatusCode)}"),
        ("upload", "$uploadUrl='http://192.168.56.1:8765/rr2-map-oct24-01-report.json'"),
        ("upload", "if($ready -and (Test-Path $z)){$r=Invoke-WebRequest -UseBasicParsing -Uri $uploadUrl -Method Post -ContentType 'application/octet-stream' -InFile $z;Write-Output ('UPLOAD_HTTP='+$r.StatusCode)}"),
    ])
    if any(len(cmd) > 350 or not cmd.isascii()
           or any(ord(char) < 32 for char in cmd) for _, cmd in result):
        raise Blocked("guest-command-exceeds-bounded-ascii-contract")
    return result


def maintenance() -> dict:
    if not (HOME / "STOP-NATIVE-20261024-V14.request").is_file():
        raise Blocked("v14-normal-stop-marker-missing")
    if not (HOME / "coordinated-host-v14-exited.json").is_file():
        raise Blocked("v14-normal-exit-receipt-missing")
    if (HOME / "coordinated-host-v15-process.json").exists():
        raise Blocked("v15-already-started")
    plan = json.loads(PLAN.read_text("utf-8"))
    if (plan.get("configSha256", "").upper() !=
            "90F2B8AB6F575C776941F0B160FF4CE1D8BC8575408975FE7645ADDED5325A2C"):
        raise Blocked("v15-config-pin-changed")
    blocked, holder, cleanup = authority_snapshot(
        Path(plan["database"]), plan["resource"])
    if blocked != 1 or holder is not None or cleanup is not None:
        raise Blocked("canonical-authority-not-quarantined")
    return plan


def require_download_delivered(plan: dict) -> None:
    """Prove the one-use full transfer completed, not merely that GET was typed."""
    receipt = HOME / "rr2-inline-download-process.json"
    finished = HOME / "rr2-inline-download-exited.json"
    events = ROOT / "artifacts" / "validation" / (
        "rr2-scout-copy-publish-oct24-01") / "transfer-events"
    if not (receipt.is_file() and finished.is_file()
            and events.is_dir() and not events.is_symlink()):
        raise Blocked("guest-executable-download-not-independently-completed")
    running = json.loads(receipt.read_text("utf-8"))
    exited = json.loads(finished.read_text("utf-8"))
    pid = running.get("pid")
    if (type(pid) is not int or pid < 1
            or running.get("purpose") != "one-use-typed-inline-download"
            or running.get("vmIdentity") != plan.get("vmIdentity")
            or running.get("windowsSessionId") != 2 or running.get("inJob") is not False
            or exited.get("pid") != pid or exited.get("phase") != "download"):
        raise Blocked("guest-executable-download-owner-differs")
    records = list(events.glob("*.json"))
    if not 1 <= len(records) <= 64 or any(p.is_symlink() for p in records):
        raise Blocked("guest-executable-download-event-scope-invalid")
    delivered = [
        json.loads(p.read_text("utf-8")) for p in records
    ]
    matching = [r for r in delivered if r.get("serverPid") == pid]
    if (len(matching) != 1 or matching[0].get("state") != "delivered"
            or matching[0].get("bundle") != "typed-inline"
            or matching[0].get("path") != "/rr2-typed-inline-oct24-01.exe"
            or matching[0].get("sha256", "").upper() != BUNDLE_SHA
            or matching[0].get("bytes") != BUNDLE_BYTES
            or matching[0].get("deliveredBytes") != BUNDLE_BYTES
            or matching[0].get("incompleteResponses") != 0
            or matching[0].get("host") != "192.168.56.1"
            or matching[0].get("guest") != "192.168.56.128"):
        raise Blocked("guest-executable-download-not-independently-completed")


def require_claim_received() -> None:
    """Require server exit and exact claimed ZIP context before upload steps."""
    if not (HOME / "rr2-inline-claim-exited.json").is_file():
        raise Blocked("guest-zip-claim-server-not-exited")
    from scripts.run_guest_inline_service import upload_digest
    upload_digest()


def shell_foreground(path: Path) -> bool:
    """Conservative image gate calibrated on prior exact RIFT guest desktop."""
    from PIL import Image
    with Image.open(path) as image:
        if image.size != (1211, 757):
            return False
        pixels = image.convert("RGB").crop((121, 114, 969, 568))
        dark = sum(1 for rgb in pixels.get_flattened_data() if rgb == (12, 12, 12))
        return dark / (pixels.width * pixels.height) >= 0.57


def execute(step_number: int | None, close: bool = False) -> dict:
    entries = commands()
    if not close and (step_number is None or not 0 <= step_number <= len(entries)):
        raise Blocked("guest-step-outside-plan")
    plan = maintenance()
    if not close and step_number and step_number > 0:
        previous = HOME / (PREFIX + f"{step_number-1:02}") / "receipt.json"
        if (not previous.is_file()
                or json.loads(previous.read_text("utf-8")).get("status") != "completed"):
            raise Blocked("previous-step-not-receipted")
    if not close and step_number is not None and step_number >= 4:
        require_download_delivered(plan)
    if not close and step_number is not None and step_number >= 30:
        require_claim_received()
    folder_name = "rr2-inline-guest-close-01" if close else PREFIX + f"{step_number:02}"
    output = HOME / folder_name
    output.mkdir(exist_ok=False)
    vm = plan["vmIdentity"]
    config = validate_config(
        Path(vm["vmx"]), vm["port"], DEFAULT_VMRUN, output, require_files=True)
    with ControlMutex(config.vmx):
        before = collect_identity(config)
        if before != vm:
            raise Blocked("vm-epoch-changed")
        client = connect(config)
        try:
            _capture(client, output / "before.png")
            if close:
                if not shell_foreground(output / "before.png"):
                    raise Blocked("powershell-foreground-not-verified")
                _type_text(client, "exit")
                client.keyPress("enter")
                time.sleep(2)
            elif step_number == 0:
                client.keyPress("super-r")
                time.sleep(0.25)
                _type_text(client, "powershell")
                client.keyPress("enter")
                time.sleep(2.5)
            else:
                if not shell_foreground(output / "before.png"):
                    raise Blocked("powershell-foreground-not-verified")
                stage, command = entries[step_number-1]
                _type_text(client, command)
                client.keyPress("enter")
                delay = 47 if "scout-copy-typed-native" in command else (
                    3 if "Invoke-WebRequest" in command and stage == "download"
                    else (20 if stage in ("claim", "upload") and "Invoke-WebRequest" in command
                          else (7 if "Compress-Archive" in command else 1.3)))
                time.sleep(delay)
            _capture(client, output / "screen.png")
            if not close and not shell_foreground(output / "screen.png"):
                raise Blocked("powershell-window-lost-after-step")
        finally:
            client.disconnect()
        if collect_identity(config) != before:
            raise Blocked("vm-identity-changed-during-step")
    record = {
        "schemaVersion": 1, "purpose": "exact-epoch-typed-inline-guest-step",
        "status": "completed", "step": "close" if close else step_number,
        "stage": "close" if close else ("bootstrap" if step_number == 0
                                      else entries[step_number-1][0]),
        "commandSha256": None if close or step_number == 0 else
            sha(entries[step_number-1][1].encode("ascii")),
        "requestSha256": REQUEST_SHA, "atUtc": datetime.now(timezone.utc).isoformat(),
        "vmIdentity": vm, "consoleMutexExclusive": True,
        "shellForegroundBeforeCommand": step_number != 0 or close,
        "consoleActionCompleted": True,
        "guestCommandCompletionVerified": False,
    }
    with (output / "receipt.json").open("x", encoding="utf-8") as file:
        json.dump(record, file, indent=2)
        file.write("\n")
    return {"status": "completed", "step": record["step"],
            "stage": record["stage"], "totalCommands": len(entries),
            "receipt": str(output / "receipt.json"),
            "guestCommandCompletionVerified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true")
    group.add_argument("--step", type=int)
    group.add_argument("--close", action="store_true")
    args = parser.parse_args()
    try:
        cmds = commands()
        if args.preview:
            result = {
                "status": "verified-offline", "totalCommands": len(cmds),
                "maxCommandLength": max(map(lambda x: len(x[1]), cmds)),
                "stages": [{"step": n+1, "stage": stage}
                           for n, (stage, _) in enumerate(cmds)],
                "requestSha256": REQUEST_SHA, "requestExactTicks": TICKS,
                "requiresV14NormalExit": True, "guestInputSent": False,
                "guestCommandCompletionVerified": False,
            }
        else:
            result = execute(args.step, close=args.close)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Blocked, OSError, ValueError, KeyError, AssertionError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
