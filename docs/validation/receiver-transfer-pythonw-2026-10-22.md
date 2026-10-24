# Receiver package delivery — existing Pythonw firewall rule reused

Date: October 22, 2026, America/New_York. Status: **LIVE LIMITED-DURATION DOWNLOAD LISTENER VERIFIED; GUEST INSTALLATION NOT VERIFIED**.

## Why this work matters

The previous installer ZIP was correct but only tested with a host-initiated GET. RIFT-Lab-1 could not be proven to reach the host. Windows Defender Firewall was investigated **read-only** before changing any settings. It was a potential transfer blocker:

- `192.168.56.1/24` is Windows' existing **VMware Network Adapter VMnet8**, connected to the guest's NAT network. The configured guest address is `192.168.56.128`. This is not VMnet1.
- Existing `C:\Python314\python.exe` inbound Public TCP/UDP allow rules were **disabled**. A separate enabled rule for the native receiver host is scoped to port 49712 and cannot be used for the ZIP.
- The already installed `C:\Python314\pythonw.exe` has an **enabled inbound TCP allow rule on the Public profile**. That rule is pre-existing; it was not changed, broadened or recreated. An explicit read using the NetSecurity cmdlets confirmed Enabled=True, Direction=Inbound, Action=Allow, Program=pythonw.exe, Protocol=TCP.
- The current Workbridge process is **not elevated**. Reading the effective ActiveStore port rules was denied. There is therefore no basis for claiming the entire Windows Filtering Platform decision or actual guest-initiated reachability is proved. We did **not** attempt UAC, create a firewall exception or modify the Public/private profile.
- WinRM 5985/5986, SMB 445 and RDP 3389 have no verified guest listeners. VMware guest process operations still require Windows guest credentials independent of the saved VM encryption credential.

## Reused software and narrowly scoped live listener

Rather than write a new network service or change Windows Firewall, the transfer uses Python's **standard library `http.server` and `socketserver`** inside the already allowed `pythonw.exe` process.

The thin bounded wrapper is an ignored local artifact:

`artifacts/receiver-milestones-20261022-01/transfer_server_pythonw.py`

Its preflight checks the exact ZIP SHA-256 `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f` and 64-KiB size limit, rejects links and invalid packages, binds only `192.168.56.1:8765`, and checks the **source address** is exactly `192.168.56.128`. It returns HTTP 200 only for `/RR2-Guest-Startup-v2.zip` and HEAD of that path; all other file paths are 404, non-guest clients receive 403 and writes/POST are not supported. The HTTP response includes the checksum. No private host config, guest executable, token, password or directory listing is served. It exits after **one complete ZIP response** or a **ten-minute monotonic deadline**.

The host launcher `LAUNCH-RECEIVER-TRANSFER.ps1` verifies the source hash, package hash, VMware VMnet8 adapter, installed pythonw.exe and its *existing* firewall rule before launching. The user-facing `START-RECEIVER-TRANSFER-PYTHONW.cmd` starts it without UAC; `CHECK-RECEIVER-TRANSFER.cmd` shows the latest verified receipt. No Windows service, Task Scheduler task, VM modification, firewall setting or auto-login is created.

## Actual tests and observations

Seven isolated tests passed in `test_transfer_pythonw.py`. They include a **real Pythonw.exe subprocess** on host loopback, exact SHA file delivery and automatic termination, source-IP rejection, path traversal/other file 404s, HEAD-not-consuming-download behavior, POST rejection, source ZIP tamper rejection and strict timeout bounds. The initial test exposed a bool-as-int timeout bug; it was corrected and the entire seven-test suite passed.

PowerShell preflight passed against the actual VMnet8 interface and existing Windows Firewall rule. An initial `Start-Process` launch under Workbridge opened and verified port 8765, but its child was killed when the bounded Workbridge command completed; this is expected Windows job-object behavior, not a failed HTTP server.

A second, independently launched `pythonw.exe` user process was created through Windows' built-in WMI/CIM process creation, reusing the already tested native-host persistence pattern. The exact new process and its TCP listener survived the Workbridge caller exiting:

- Start recorded **2026-10-22T09:39:42.901691Z**, Pythonw.exe **PID 39644**, creation ticks **134371355814576221**.
- Verified address **192.168.56.1:8765**, and exact process/listener owner.
- Admission source IP **192.168.56.128**; one allowed ZIP and no other route.
- Persisted check **2026-10-22T09:40:12.449353Z** showed state **listening**, 0 requests/downloads, no guest upload, no game input.
- A subsequent PowerShell status check **2026-10-22T09:42:04.247Z** confirmed the same process was still alive with `downloadCount=0`.
- The server stops on one successful guest GET or at the ten-minute deadline. **Do not treat PID 39644 or the server as permanently current.** Read the receipt and process identity each time.

The exact VMware VM and current connected native host were rechecked before the WMI launch; the coordinator remained ready and the guest disarmed, with no sampled held inputs. RIFT was **not foreground**, and no game control action, VM restart or guest receiver restart was attempted.

## Alternative existing VMware media folder

We also staged a verified copy of the same ZIP in the existing configured host media folder:

`C:\RIFT MODDING\Media\RR2-Guest-Startup-v2-20261022.zip`

The VMX already names this folder `RIFT-Installers` with read-only guest access, but explicitly sets `isolation.tools.hgfs.disable = "TRUE"`. It is therefore **not valid to claim the guest can currently read it**, and the VMware isolation setting was preserved. Do not change shared-folder isolation solely to claim a successful transfer.

Evidence: `artifacts/receiver-milestones-20261022-01/alternate-transfer-staging.json`.

## Guest installation and reboot still required

A read-only VMware Tools GuestInfo lookup on **2026-10-22T09:41:24.359Z** returned an empty `rr2.receiver-startup` value. This provides no guest installation receipt. No successful guest HTTP request reached the listener during the confirmed observations; whether a guest-side attempt was made is unknown. **No installation, receiver restart or Windows guest logon/reboot was proved.**

While the limited server is alive, inside the guest Windows browser open:

`http://192.168.56.1:8765/RR2-Guest-Startup-v2.zip`

If expired, start another limited transfer on the **physical host** by double-clicking:

`C:\work\riftreader2\artifacts\receiver-milestones-20261022-01\START-RECEIVER-TRANSFER-PYTHONW.cmd`

Use `CHECK-RECEIVER-TRANSFER.cmd` on the host to distinguish `listening`, `served`, `expired` and terminated stale processes. Check the downloaded ZIP SHA-256 inside guest Windows, extract it, then run its original `INSTALL-ONCE.cmd` as the signed-in guest user. Confirm `shell:startup` contains the link and `CHECK-STATUS.cmd` confirms the receiver. The guest startup script already reports nonsecret install status through VMware Tools GuestInfo if available, but that was empty at the last check.

Once installed, collect a fresh baseline using the existing `scripts/verify_guest_recovery.py`, verify a controlled receiver-only restart, and separately qualify Windows guest logon/reboot. Never infer unattended startup from a new receiver connection alone. Do not rerun older blocked guest-console diagnostics or reset the canonical queue.

The source/test suite and current host-side ZIP remain intact. No tracked project source or runtime modules were edited in this transfer iteration; only ignored artifacts and dated documentation were added.

Model: GPT-6. Reasoning level:
