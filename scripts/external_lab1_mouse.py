"""Host-only Lab-1 capture/move/left-click using the installed vncdotool.

Run with RR2's existing artifacts/tools/control-python/Scripts/python.exe.
Coordinates are pixels in the FULL VMware guest desktop capture, not the RIFT
client image. No guest package, helper installation, or guest-agent input.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import socket
import ctypes
from ctypes import wintypes
import sqlite3
from contextlib import closing
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import vm_console_native as native
from scripts.run_xyz_workflow import read_review
from scripts.lab_codex import LabCodex
from scripts.vmware_guest_session import POWERSHELL, _wipe
from scripts.control_host import HostConfig
from scripts.ensure_controller import CONFIGS, QUEUE, _launch_lock

VMX = Path(r"C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx")
VMRUN = Path(r"C:\Program Files\VMware\VMware Workstation\vmrun.exe")


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def require_queue_clear():
    try:
        if not QUEUE.is_file():
            raise native.Blocked("controller-queue-unavailable")
        with closing(sqlite3.connect(QUEUE.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT blocked, holder FROM resources WHERE name=?", ("vm:rift-lab-1",)).fetchone()
            if row is None or row[0] != 1 or row[1] is not None:
                raise native.Blocked("lab1-queue-not-quarantined-or-held")
            for (specification,) in db.execute("SELECT specification FROM requests WHERE state IN ('queued','active','cleanup')"):
                if "vm:rift-lab-1" in json.loads(specification)["resources"]:
                    raise native.Blocked("lab1-queue-pending")
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        raise native.Blocked("controller-queue-unavailable") from None


def require_controller_absent():
    config = HostConfig.load(CONFIGS["lab1"])
    if config.vmx != VMX.resolve() or config.vnc_port != 5905:
        raise native.Blocked("controller-config-binding-mismatch")
    table = listener_table()
    for port in (config.ui_port, config.agent_port):
        if native.parse_tcp_listener_rows(table, port, listener_table=True):
            raise native.Blocked("controller-listening")


def listener_table():
    try:
        api = ctypes.WinDLL("iphlpapi", use_last_error=True)
        query = api.GetExtendedTcpTable
        query.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
        size = wintypes.DWORD()
        first = query(None, ctypes.byref(size), False, socket.AF_INET,
                      native.TCP_TABLE_OWNER_PID_LISTENER, 0)
        if first != 122 or size.value < 4 or size.value > 16 * 1024 * 1024:
            raise native.Blocked("controller-listener-state-uncertain")
        data = ctypes.create_string_buffer(size.value)
        capacity = size.value
        if query(data, ctypes.byref(size), False, socket.AF_INET,
                 native.TCP_TABLE_OWNER_PID_LISTENER, 0) or size.value > capacity:
            raise native.Blocked("controller-listener-state-uncertain")
        return bytes(data.raw[:size.value])
    except (OSError, AttributeError, ValueError):
        raise native.Blocked("controller-listener-state-uncertain") from None



GAME_SHA = "1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8"


def interactive_game_probe(guest, script, ownership):
    sid = ownership.get("currentSid")
    name = ownership.get("interactiveName")
    if (ownership.get("machine") != "RIFT-LAB-1" or not isinstance(sid, str) or not sid
            or sid != ownership.get("interactiveSid") or sid != ownership.get("gameOwnerSid")
            or not isinstance(name, str) or not name or len(name) > 256):
        raise native.Blocked("guest-account-sid-mismatch")
    original = guest._username
    temporary = ctypes.create_unicode_buffer(name)
    guest._username = temporary
    try:
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        if len(encoded) > 4096:
            raise native.Blocked("guest-probe-too-large")
        guest.run("runProgramInGuest", "-interactive", POWERSHELL, "-NoProfile",
                  "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded, timeout=25)
    finally:
        guest._username = original
        _wipe(temporary)


def guest_game_identity(vm_identity, output, phase):
    api = LabCodex()
    _, _, config, lab = api._configuration("lab1")
    if lab["vmx"].resolve() != VMX.resolve() or lab["vncPort"] != 5905:
        raise native.Blocked("guest-config-binding-mismatch")
    guest_path = lab["guestRoot"] + "\\rr2-mouse-" + uuid.uuid4().hex + ".json"
    literal = "'" + guest_path.replace("'", "''") + "'"
    script = r"""$ErrorActionPreference='Stop';
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class RR2MouseGate {[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);[DllImport("user32.dll")] public static extern short GetAsyncKeyState(int v); }';
if($env:COMPUTERNAME -cne 'RIFT-LAB-1'){throw 'wrong-machine'};
$p=@(Get-Process -Name 'rift_x64' -ErrorAction Stop);if($p.Count -ne 1){throw 'game-count'};$g=$p[0];
$sha=(Get-FileHash -LiteralPath $g.Path -Algorithm SHA256).Hash;
$h=[RR2MouseGate]::GetForegroundWindow();[uint32]$fg=0;if($h -eq [IntPtr]::Zero){throw 'foreground-unavailable'};[void][RR2MouseGate]::GetWindowThreadProcessId($h,[ref]$fg);
$self=Get-Process -Id $PID;if($fg -ne [uint32]$g.Id -or $g.SessionId -le 0 -or $self.SessionId -ne $g.SessionId){throw 'foreground-or-session-mismatch'};
for($k=1;$k -le 254;$k++){if(([int][RR2MouseGate]::GetAsyncKeyState($k) -band 32768) -ne 0){throw 'held-input'}};
$w=[Security.Principal.WindowsIdentity]::GetCurrent();
$r=[ordered]@{sid=$w.User.Value;machine=$env:COMPUTERNAME;pid=[int]$g.Id;ticks=[long]$g.StartTime.ToUniversalTime().Ticks;sha=$sha;session=[int]$g.SessionId;foregroundPid=[int]$fg;neutral=$true};
[IO.File]::WriteAllText(DEST,($r|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
""".replace("DEST", literal)
    sid_path = lab["guestRoot"] + "\\rr2-mouse-sid-" + uuid.uuid4().hex + ".json"
    sid_literal = "'" + sid_path.replace("'", "''") + "'"
    sid_script = r"""$ErrorActionPreference='Stop';if($env:COMPUTERNAME -cne 'RIFT-LAB-1'){throw 'machine'};
$w=[Security.Principal.WindowsIdentity]::GetCurrent();$i=(Get-CimInstance Win32_ComputerSystem).UserName;
if(-not $i){throw 'interactive-unavailable'};$is=(New-Object Security.Principal.NTAccount($i)).Translate([Security.Principal.SecurityIdentifier]).Value;
$g=@(Get-CimInstance Win32_Process -Filter "Name='rift_x64.exe'");if($g.Count -ne 1){throw 'game-count'};
$gs=Invoke-CimMethod -InputObject $g[0] -MethodName GetOwnerSid;
$r=@{machine=$env:COMPUTERNAME;currentSid=$w.User.Value;interactiveName=$i;interactiveSid=$is;gameOwnerSid=$gs.Sid;gamePid=[int]$g[0].ProcessId;gameSession=[int]$g[0].SessionId};
[IO.File]::WriteAllText(DEST,($r|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))""".replace("DEST", sid_literal)
    with api._session(config, lab, vm_identity, output) as guest:
        guest.powershell(sid_script, timeout=30)
        guest.copy_from_guest(sid_path, output / ("account-" + phase + ".json"), timeout=20)
        ownership = json.loads((output / ("account-" + phase + ".json")).read_text(encoding="utf-8-sig"))
        interactive_game_probe(guest, script, ownership)
        guest.copy_from_guest(guest_path, output / ("game-" + phase + ".json"), timeout=20)
    value = json.loads((output / ("game-" + phase + ".json")).read_text(encoding="utf-8-sig"))
    if (value.get("sid") != ownership.get("currentSid") or value.get("pid") != ownership.get("gamePid")
            or value.get("session") != ownership.get("gameSession")):
        raise native.Blocked("guest-game-owner-changed")
    if (value.get("machine") != "RIFT-LAB-1" or value.get("sha") != GAME_SHA
            or type(value.get("pid")) is not int or value["pid"] <= 0
            or type(value.get("ticks")) is not int or value["ticks"] <= 0
            or type(value.get("session")) is not int or value["session"] <= 0
            or value.get("foregroundPid") != value["pid"] or value.get("neutral") is not True):
        raise native.Blocked("guest-game-identity-or-foreground-unavailable")
    return value


def run(args):
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "artifacts") or output.exists():
        raise ValueError("fresh RR2 artifacts output required")
    config = native.validate_config(VMX, 5905, VMRUN, output, require_files=True)
    output.mkdir(parents=True, exist_ok=False)
    result = {"action": args.action, "hostOnly": True, "backend": "vncdotool",
              "inputMayHaveBeenSent": False, "buttonReleaseSent": False,
              "connectionClosed": False, "consoleMutexReleased": False, "status": "pending"}
    client = None
    try:
        with _launch_lock("lab1"), native.ControlMutex(VMX) as owner:
            if owner.abandoned:
                raise native.Blocked("abandoned-console-owner-requires-review")
            require_controller_absent()
            require_queue_clear()
            result["beforeIdentity"] = native.collect_identity(config)
            if args.action != "capture":
                result["gameBefore"] = guest_game_identity(result["beforeIdentity"], output, "before")
            client = native.connect(config)
            try:
                size = native._capture(client, output / "before.png")
                result["desktopSize"] = size
                capture = {"captureId": uuid.uuid4().hex, "image": str(output / "before.png"),
                           "imageSha256": hashlib.sha256((output / "before.png").read_bytes()).hexdigest(),
                           "action": args.action, "position": [args.x, args.y]}
                save(output / "capture.json", capture)
                if args.action != "capture":
                    if (type(args.x) is not int or type(args.y) is not int
                            or not 0 <= args.x < size[0] or not 0 <= args.y < size[1]):
                        raise ValueError("position outside reviewed guest desktop")
                    print(json.dumps({"action": args.action, "desktopPosition": [args.x, args.y]}), flush=True)
                    note = read_review(capture, timeout=40)
                    save(output / "review.json", {"captureId": capture["captureId"], "note": note})
                    native.verify_identity(config, result["beforeIdentity"])
                    require_controller_absent()
                    require_queue_clear()
                    probe_started = time.monotonic()
                    game_after = guest_game_identity(result["beforeIdentity"], output, "after")
                    if game_after != result["gameBefore"]:
                        raise native.Blocked("guest-game-identity-changed")
                    native.verify_identity(config, result["beforeIdentity"])
                    require_controller_absent()
                    require_queue_clear()
                    if time.monotonic() - probe_started > 10.0:
                        raise native.Blocked("guest-input-observation-stale")
                    # VNC coordinates are connection-local: move and click MUST share this client.
                    result["inputMayHaveBeenSent"] = True
                    client.mouseMove(args.x, args.y)
                    if args.action == "click":
                        try:
                            client.mouseDown(1)
                            time.sleep(0.1)
                        finally:
                            client.mouseUp(1)
                            result["buttonReleaseSent"] = True
                    time.sleep(0.35)
                    if native._capture(client, output / "after.png") != size:
                        raise ValueError("guest desktop geometry changed")
                    result["afterImageSha256"] = hashlib.sha256((output / "after.png").read_bytes()).hexdigest()
                result["afterIdentity"] = native.verify_identity(config, result["beforeIdentity"])
                result["status"] = "completed-awaiting-visual-review"
            finally:
                try:
                    if result["inputMayHaveBeenSent"]:
                        client.mouseUp(1)
                        result["buttonReleaseSent"] = True
                finally:
                    client.disconnect()
                    if not client.factory._rr2_closed.is_set():
                        raise native.Blocked("console-disconnect-unconfirmed")
                    result["connectionClosed"] = True
                    client = None
        result["consoleMutexReleased"] = True
    except BaseException:
        result["status"] = "blocked"
        raise
    finally:
        save(output / "result.json", result)
    print(json.dumps({"status": result["status"], "output": str(output),
                      "image": str(output / ("before.png" if args.action == "capture" else "after.png")),
                      "hostOnly": True, "buttonReleaseSent": result["buttonReleaseSent"],
                      "connectionClosed": result["connectionClosed"]}), flush=True)
    return result


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("action", choices=("capture", "move", "click"))
    command.add_argument("x", type=int, nargs="?")
    command.add_argument("y", type=int, nargs="?")
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    try:
        run(args)
    except Exception as error:
        print(json.dumps({"status": "blocked", "errorType": type(error).__name__,
                          "reason": str(error) if isinstance(error, native.Blocked) else "operation failed; inspect retained receipt"}),
              file=sys.stderr)
        raise SystemExit(2)
