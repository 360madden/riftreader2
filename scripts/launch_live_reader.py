"""Launch one bounded live RiftReader2 reader in an exact current lab session.

This tracked operator helper does not start RIFT, type into the game, start a
control host, or prompt for a guest password. It safely ensures the exact
on-demand host receiver when using the known per-lab private config. It requires the existing
VM-specific cached GuestSession login.

The receiver token is read from a private host configuration, written only to a
temporary LocalAppData staging directory, copied to the guest, and never emitted
to stdout or retained in the host evidence directory.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import uuid
from ctypes import wintypes


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.vm_console_native import (
    TCP_TABLE_OWNER_PID_LISTENER,
    collect_identity,
    parse_tcp_listener_rows,
    process_identity,
    validate_config,
    verify_identity,
)
from scripts.vmware_guest_session import GuestSession, POWERSHELL, SessionError
from scripts.live_reader_config import (
    DEFAULT_SCAN_LIMITS,
    build_live_configuration,
    resolve_max_scan_bytes,
)


SHA256 = re.compile(r"[0-9A-F]{64}")
LABS = {
    "lab1": {
        "machine": "RIFT-LAB-1",
        "vmx": Path(r"C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx"),
        "legacyGuestVmx": Path(r"C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx"),
        "port": 5905,
    },
    "lab2": {
        "machine": "RIFT-LAB-2",
        "vmx": Path(r"C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx"),
        "port": 5962,
    },
}
VMRUN = Path(r"C:\Program Files\VMware\VMware Workstation\vmrun.exe")
DEFAULT_RECEIVERS = {lab: ROOT / ".local" / "two-lab-movement" / (lab + "-receiver.json") for lab in LABS}


def fail(reason: str) -> None:
    raise RuntimeError(reason)


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def no_prompt() -> tuple[object, object]:
    raise SessionError("cached-guest-login-required")

def legacy_guest_target(lab_name: str) -> str | None:
    """One old VM-specific cached-login key; never borrow another lab key."""
    previous = LABS[lab_name].get("legacyGuestVmx")
    if previous is None:
        return None
    return "RiftReader2 Guest Windows: " + str(previous.resolve(strict=False))


def receiver_listener_owner(host: str, port: int) -> int:
    """Return the sole exact-address owner from Windows' listener table.

    The listener-filtered table is authoritative even on Windows builds that
    expose a blank/noncanonical per-row State through Get-NetTCPConnection.
    """
    if os.name != "nt":
        fail("windows-required")
    api = ctypes.WinDLL("iphlpapi", use_last_error=True)
    get_table = api.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    size = wintypes.DWORD()
    get_table(None, ctypes.byref(size), False, socket.AF_INET,
              TCP_TABLE_OWNER_PID_LISTENER, 0)
    if not size.value:
        fail("receiver-listener-query-failed")
    data = ctypes.create_string_buffer(size.value)
    if get_table(data, ctypes.byref(size), False, socket.AF_INET,
                 TCP_TABLE_OWNER_PID_LISTENER, 0):
        fail("receiver-listener-query-failed")
    matches = parse_tcp_listener_rows(
        bytes(data.raw[:size.value]), port, listener_table=True)
    owners = [pid for address, pid in matches if address == host]
    if len(matches) != 1 or len(owners) != 1:
        fail("receiver-listener-not-unique-or-wrong-address")
    return owners[0]


def receiver_preflight(path: Path) -> tuple[dict, str, str]:
    raw = path.read_bytes()
    if len(raw) > 65_536:
        fail("receiver-config-too-large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        fail("invalid-receiver-config")
    address, port, token = value.get("bindAddress"), value.get("port"), value.get("token")
    try:
        address_value = ipaddress.ip_address(address)
    except ValueError:
        fail("invalid-receiver-address")
    if not address_value.is_private or not isinstance(port, int) or not 1024 <= port <= 65535:
        fail("invalid-receiver-endpoint")
    if not isinstance(token, str) or not 32 <= len(token) <= 512:
        fail("invalid-receiver-token")
    endpoint = f"http://{address}:{port}/observation"
    owner_before = receiver_listener_owner(address, port)
    command = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={owner_before}';"
        "if($null -eq $p){throw 'receiver-process-missing'};"
        "[pscustomobject]@{pid=[int]$p.ProcessId;commandLooksLikeReceiver=[bool]($p.CommandLine -match '(?i)receiver')}|"
        "ConvertTo-Json -Compress"
    )
    observed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True, capture_output=True, text=True, timeout=20)
    receipt = json.loads(observed.stdout)
    if receipt.get("commandLooksLikeReceiver") is not True:
        fail("receiver-process-mismatch")
    if int(receipt["pid"]) != owner_before:
        fail("receiver-listener-owner-drift")
    before = process_identity(int(receipt["pid"]))
    after = process_identity(int(receipt["pid"]))
    owner_after = receiver_listener_owner(address, port)
    if before != after or owner_after != owner_before:
        fail("receiver-process-identity-drift")
    receipt = {
        "pid": int(receipt["pid"]),
        # process_identity startTicks use the Windows 1601 epoch.  The strict
        # console pin consumes .NET ticks (year 1), so convert exactly without
        # passing through a microsecond timestamp or floating point.
        "processStartUtcTicks": int(before["startTicks"]) + 504_911_232_000_000_000,
        "image": before["image"],
        "address": address,
        "port": port,
        "configSha256": hashlib.sha256(raw).hexdigest().upper(),
    }
    return receipt, token, endpoint


def game_guard(args: argparse.Namespace) -> str:
    return rf"""
$games=@(Get-Process rift_x64 -ErrorAction Stop)
if($games.Count -ne 1){{throw 'game-process-count'}}
$game=$games[0]
$gameTicks=[string]$game.StartTime.ToUniversalTime().Ticks
$gameSha=(Get-FileHash -LiteralPath $game.Path -Algorithm SHA256).Hash
if($game.Id -ne {args.expected_game_pid}){{throw 'game-pid-drift'}}
if($gameTicks -ne {quote(str(args.expected_game_start_ticks))}){{throw 'game-start-drift'}}
if($gameSha -ne {quote(args.expected_game_sha256)}){{throw 'game-build-drift'}}
if($env:COMPUTERNAME -ne {quote(LABS[args.lab]['machine'])}){{throw 'guest-machine-mismatch'}}
"""


def run_guest_script(session: GuestSession, output: Path, body: str, run_id: str, label: str,
                     timeout: int = 180) -> dict:
    host_script = output / f"{label}.ps1"
    host_receipt = output / f"{label}.json"
    guest_script = rf"C:\Users\Public\Documents\RR2Hour-{run_id}-{label}.ps1"
    guest_receipt = rf"C:\Users\Public\Documents\RR2Hour-{run_id}-{label}.json"
    script = "$ErrorActionPreference='Stop'\n" + body
    script += f"$payload|ConvertTo-Json -Depth 12 -Compress|Set-Content -LiteralPath {quote(guest_receipt)} -Encoding UTF8\n"
    host_script.write_text(script, encoding="utf-8-sig")
    session.run("copyFileFromHostToGuest", str(host_script), guest_script, timeout=90)
    session.powershell(
        f"if((Get-FileHash -LiteralPath {quote(guest_script)}).Hash -ne {quote(sha(host_script))})"
        "{throw 'guest-script-hash-mismatch'}", timeout=60)
    session.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", guest_script,
                timeout=timeout)
    session.copy_from_guest(guest_receipt, host_receipt, timeout=90)
    return json.loads(host_receipt.read_text(encoding="utf-8-sig"))


def private_config(run_id: str, endpoint: str, token: str, guest_output: str,
                   duration: int, poll_interval_milliseconds: int,
                   max_scan_bytes: int) -> tuple[Path, Path, str]:
    base = Path(os.environ["LOCALAPPDATA"]) / "RiftReader2" / "HybridStaging"
    staging = base / run_id
    staging.mkdir(parents=True, exist_ok=False)
    config = staging / "riftreader2-live.json"
    value = build_live_configuration(
        endpoint=endpoint,
        token=token,
        output_path=guest_output,
        duration_seconds=duration,
        poll_interval_milliseconds=poll_interval_milliseconds,
        max_scan_bytes=max_scan_bytes,
    )
    config.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return staging, config, sha(config)


def clean_private(staging: Path) -> None:
    base = (Path(os.environ["LOCALAPPDATA"]) / "RiftReader2" / "HybridStaging").resolve()
    target = staging.resolve()
    if target.parent != base or not target.name:
        fail("private-staging-cleanup-scope")
    shutil.rmtree(target)


def execute(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reader = args.reader.resolve(strict=True)
    if sha(reader) != args.reader_sha256:
        fail("reader-source-hash-mismatch")

    # A reader owns its host-side receiver dependency for the canonical per-lab
    # config, but never starts arbitrary user-supplied endpoints.
    from scripts.ensure_receiver import CONFIGS as RECEIVER_CONFIGS, ensure as ensure_receiver
    if args.receiver_config.resolve() == RECEIVER_CONFIGS[args.lab].resolve():
        ensure_receiver(args.lab)
    receiver, receiver_token, endpoint = receiver_preflight(args.receiver_config.resolve(strict=True))
    run_id = f"{args.lab}-{uuid.uuid4().hex}"
    write_new(output / "receiver.json", receiver)

    lab = LABS[args.lab]
    cfg = validate_config(lab["vmx"], lab["port"], VMRUN, output, require_files=True)
    vm_before = collect_identity(cfg)
    write_new(output / "vm-before.json", vm_before)
    check = lambda: verify_identity(cfg, vm_before)

    guest_dir = rf"C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid\{run_id}"
    guest_exe = guest_dir + r"\RiftReader2.Live.exe"
    guest_config = guest_dir + r"\riftreader2-live.json"
    guest_output = guest_dir + r"\latest.json"
    guest_stdout = guest_dir + r"\reader.stdout.txt"
    guest_stderr = guest_dir + r"\reader.stderr.txt"
    staging = None
    try:
        staging, config, config_sha = private_config(
            run_id, endpoint, receiver_token, guest_output, args.duration_seconds,
            args.poll_interval_milliseconds, args.max_scan_bytes)
        with GuestSession(cfg.vmrun, cfg.vmx, check, cache_guest_credentials=False,
                          _guest_prompt=no_prompt,
                          legacy_guest_credential_target=legacy_guest_target(args.lab)) as session:
            if session.credential_source != "cache":
                fail("noncached-credentials-blocked")
            preflight = game_guard(args) + rf"""
$conflicts=@(Get-CimInstance Win32_Process -Filter "Name='RiftReader2.Live.exe'" | Where-Object {{
    $_.CommandLine -notmatch '(?i)(^|\s)control-agent(\s|$)'
}})
if($conflicts.Count -ne 0){{throw 'live-reader-or-unknown-command-already-running'}}
$dir={quote(guest_dir)}
if(Test-Path -LiteralPath $dir){{throw 'guest-run-directory-exists'}}
New-Item -ItemType Directory -Path $dir -ErrorAction Stop|Out-Null
$payload=@{{status='guest-preflight-passed';gamePid=$game.Id;gameStartUtcTicks=$gameTicks;gameSha256=$gameSha;otherLiveProcessCount=0;inputSent=$false}}
"""
            pre = run_guest_script(session, output, preflight, run_id, "preflight")
            if pre.get("status") != "guest-preflight-passed":
                fail("guest-preflight-failed")

            session.run("copyFileFromHostToGuest", str(reader), guest_exe, timeout=300)
            session.run("copyFileFromHostToGuest", str(config), guest_config, timeout=90)
            clean_private(staging)
            staging = None

            launch = game_guard(args) + rf"""
$other=@(Get-CimInstance Win32_Process -Filter "Name='RiftReader2.Live.exe'" | Where-Object {{
    $_.CommandLine -notmatch '(?i)(^|\s)control-agent(\s|$)'
}})
if($other.Count -ne 0){{throw 'reader-start-race'}}
$exe={quote(guest_exe)};$cfg={quote(guest_config)};$latest={quote(guest_output)}
$stdout={quote(guest_stdout)};$stderr={quote(guest_stderr)}
if((Get-FileHash -LiteralPath $exe).Hash -ne {quote(args.reader_sha256)}){{throw 'guest-reader-hash'}}
if((Get-FileHash -LiteralPath $cfg).Hash -ne {quote(config_sha)}){{throw 'guest-config-hash'}}
$p=Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$deadline=[DateTime]::UtcNow.AddSeconds(90);$nonce=$null;$snapshot=$null
while([DateTime]::UtcNow -lt $deadline -and -not $p.HasExited){{
    Start-Sleep -Milliseconds 250
    if(Test-Path -LiteralPath $stdout){{
        $text=Get-Content -LiteralPath $stdout -Raw
        if($text -match '/rr2bind ([0-9a-f]{{32}})'){{$nonce=$Matches[1]}}
    }}
    if($nonce -and (Test-Path -LiteralPath $latest)){{
        try{{$snapshot=Get-Content -LiteralPath $latest -Raw|ConvertFrom-Json}}catch{{}}
        if($snapshot -and $snapshot.nonce -eq $nonce -and $snapshot.target -and
           $snapshot.target.processId -eq {args.expected_game_pid} -and
           $snapshot.target.executableSha256 -eq {quote(args.expected_game_sha256)}){{break}}
    }}
}}
if($p.HasExited){{throw 'reader-exited-before-ready'}}
if(-not $nonce -or -not $snapshot){{throw 'reader-not-ready'}}
if(-not $snapshot.delivery.enabled -or $snapshot.delivery.endpoint -ne {quote(endpoint)}){{throw 'delivery-binding-mismatch'}}
$p.Refresh();$readerTicks=[string]$p.StartTime.ToUniversalTime().Ticks
$payload=@{{status='reader-ready';readerPid=$p.Id;readerStartUtcTicks=$readerTicks;
 readerSha256=(Get-FileHash -LiteralPath $exe).Hash;nonce=$nonce;
 expiresAtUtc=$p.StartTime.ToUniversalTime().AddSeconds({args.duration_seconds}).ToString('o');
 guestDirectory={quote(guest_dir)};guestOutput=$latest;gamePid=$game.Id;gameStartUtcTicks=$gameTicks;
 gameSha256=$gameSha;scanStatus=$snapshot.riftReader2.scan.status;
 selectionStatus=$snapshot.riftReader2.selectionStatus;deliveryStatus=$snapshot.delivery.status;
 inputSent=$false;controlAgentStopped=$false}}
"""
            ready = run_guest_script(session, output, launch, run_id, "launch", timeout=150)
            if (ready.get("status") != "reader-ready" or ready.get("readerSha256") != args.reader_sha256
                    or not re.fullmatch(r"[0-9a-f]{32}", str(ready.get("nonce", "")))):
                fail("reader-launch-receipt-mismatch")
            session.copy_from_guest(guest_output, output / "latest.json", timeout=90)

        vm_after = verify_identity(cfg, vm_before)
        write_new(output / "vm-after.json", vm_after)
        summary = {
            "status": "reader-running-postflight-verified",
            "lab": args.lab,
            "runId": run_id,
            "readerPid": ready["readerPid"],
            "readerStartUtcTicks": ready["readerStartUtcTicks"],
            "readerSha256": ready["readerSha256"],
            "nonce": ready["nonce"],
            "expiresAtUtc": ready["expiresAtUtc"],
            "guestDirectory": guest_dir,
            "guestOutput": guest_output,
            "gamePid": args.expected_game_pid,
            "gameStartUtcTicks": str(args.expected_game_start_ticks),
            "gameSha256": args.expected_game_sha256,
            "maxScanBytes": args.max_scan_bytes,
            "receiver": receiver,
            "vmIdentityStable": vm_after == vm_before,
            "inputSent": False,
            "controlAgentStopped": False,
            "cleanup": "reader exits automatically at the configured bounded duration",
            "atUtc": datetime.now(timezone.utc).isoformat(),
        }
        write_new(output / "summary.json", summary)
        return summary
    finally:
        if staging is not None and staging.exists():
            clean_private(staging)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--lab", choices=tuple(LABS), required=True)
    result.add_argument("--expected-game-pid", type=int, required=True)
    result.add_argument("--expected-game-start-ticks", type=int, required=True)
    result.add_argument("--expected-game-sha256", type=str.upper, required=True)
    result.add_argument("--reader", type=Path, required=True,
                        help="host path to the published RiftReader2.Live.exe")
    result.add_argument("--reader-sha256", type=str.upper, required=True)
    result.add_argument("--receiver-config", type=Path, default=None,
                        help="private host receiver JSON; its token is never emitted")
    result.add_argument("--duration-seconds", type=int, default=900)
    result.add_argument("--poll-interval-milliseconds", type=int, default=500)
    result.add_argument("--scan-limit-config", type=Path, default=DEFAULT_SCAN_LIMITS,
                        help="tracked per-lab maxScanBytes configuration")
    result.add_argument("--max-scan-bytes", type=int,
                        help="bounded one-run override; otherwise use the tracked per-lab setting")
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.receiver_config is None:
        args.receiver_config = DEFAULT_RECEIVERS[args.lab]
    if args.expected_game_pid <= 0 or args.expected_game_start_ticks <= 0:
        fail("invalid-game-identity")
    if SHA256.fullmatch(args.expected_game_sha256) is None or SHA256.fullmatch(args.reader_sha256) is None:
        fail("invalid-sha256")
    if not 60 <= args.duration_seconds <= 3600:
        fail("duration-out-of-range")
    if not 250 <= args.poll_interval_milliseconds <= 60_000:
        fail("poll-interval-out-of-range")
    try:
        args.max_scan_bytes = resolve_max_scan_bytes(
            args.lab, config_path=args.scan_limit_config, override=args.max_scan_bytes)
        summary = execute(args)
    except Exception as error:
        print(json.dumps({"status": "blocked", "reason": str(error).split(":", 1)[0]}))
        return 2
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
