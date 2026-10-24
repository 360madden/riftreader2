# RIFT-Lab-1 guest receiver recovery — verified live checkpoints

Date: October 24, 2026 (America/New_York). Scope: exact VMware console and the existing guest receiver package. This record supersedes the *not yet served* transfer checkpoint in [host preparation](receiver-iso-host-prep-2026-10-24.md), without changing historical observations.

## Identity and control fence

- Revalidated running VM at `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`: `vmware-vmx.exe` PID **38044**, start ticks **134372941117887852**, VMware log epoch **2026-10-24T05:41:51.833Z**, exclusive loopback VNC listener `127.0.0.1:5905`. Each console operation checked VM identity before and after and used the repository's cooperative console mutex.
- Previous native coordinator V7 process PID 34352 is absent; the planned V8 host was **not** running or launched during these checks. Native ports 49712/49715 were initially closed.
- A SQLite `mode=ro` query of canonical `artifacts/native-coordination-live/queue.sqlite3` found resource `vm:rift-lab-1` **blocked**, no holder and no pending requests (`QUEUE_QUARANTINED_NO_PENDING`). This is not a fresh guest STOP/release receipt. No queue reset, manual unblock, grant, or movement action occurred.

## Package transfer, security warning, and verified pre-existing ZIP

- The unchanged, six-file host ZIP is `artifacts/receiver-milestones-20261022-01/host-only-download/RR2-Guest-Startup-v2.zip`, **8,243 bytes**, SHA-256 `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`.
- Used visually inspected Windows Run input inside the signed-in guest to request `http://192.168.56.1:49712/RR2-Guest-Startup-v2.zip`. The strictly one-use `scripts/serve_guest_receiver_bundle.py` server ran as the existing permitted host `pythonw.exe`, allowed only guest IP `192.168.56.128`, and exited **0** with `bundle-delivered=true` at **2026-10-24T11:28:19.318793Z**. This proves the HTTP server completed a request, *not* that Chrome saved the new download.
- Chrome reported **Insecure download blocked** for the new `RR2-Guest-Startup-v2 (1).zip` due to HTTP. Its full history showed that attempt blocked, and guest Downloads contained an `Unconfirmed 661000.crdownload` file. **No Chrome security override was clicked**, and the blocked file was not opened or cleaned up.
- Chrome also showed an earlier **successfully downloaded** `RR2-Guest-Startup-v2.zip` (Explorer modification time October 24 at 5:36 AM local) in `C:\Users\mrkoo\Downloads`. Guest PowerShell `Get-FileHash -Algorithm SHA256` visibly returned **`AB5242D0317257DC2B2328F0BC1DA98CC24088A2140EA4D968A29C86C23F708F`**, an exact match. The verified earlier guest ZIP eliminates any need to override the blocked HTTP download.
- Explorer showed an already extracted directory `C:\Users\mrkoo\Downloads\RR2-Receiver-20261024-01\RR2-Guest-Startup-v2` with exactly the six expected files (`CHECK-STATUS.cmd`, `guest_receiver_startup.ps1`, `INSTALL-ONCE.cmd`, `README.txt`, `REMOVE-STARTUP.cmd`, `VERIFY-LAUNCHER.cmd`). Directory enumeration alone does not independently hash each extracted file.

## Current manifest and receiver state

- Reviewed the pinned package scripts before invocation. `CHECK-STATUS.cmd` verifies the packaged launcher's SHA-256 before invoking `guest_receiver_startup.ps1 -Mode Status`. The PowerShell status path revalidates the current interactive Windows account, manifest schema/owner, and launcher/receiver/config pinned file hashes.
- Invoked **CHECK-STATUS.cmd** visibly in guest Windows. At approximately **2026-10-24T11:44:19Z**, the result reported `machineName=DESKTOP-8632QPL`, `sessionId=1`, `gamePid=6940`, `state=start`, `connectionVerified=false`, with **Status exit code 0**. In this script, `state=start` means the game is present and a receiver could be started; it is **not** proof of a running receiver or native authenticated connection. The status action itself publishes a local diagnostic `status.json` and optionally VMware GuestInfo, so it is not strictly read-only.
- A valid on-disk manifest is proven by that checker. A Windows Startup shortcut, successful receiver start, authenticated host session, real STOP/release cleanup, and reboot/logon autostart are **not yet verified** at this checkpoint. Do not equate manifest validation or the diagnostic exit code with those milestones.

## Evidence, preservation, and next step

- Session-local visual identity and screenshot receipts are under ignored `artifacts/recovery-20261024-02/` (especially `guest-hash-final/`, `full-download-history/`, `guest-extracted-files/`, and `receiver-status-result/`). Console action plans are preserved there. They are not staged into Git because screenshots can contain game/user-desktop content.
- Next: inspect `shell:startup` through the visible guest UI; use the unchanged, idempotent `INSTALL-ONCE.cmd` only if a valid shortcut is absent and the installer can safely complete. Launch the existing pinned receiver, restart only the new epoch-pinned V8 coordinator, require authenticated guest identity and actual STOP/release-backed cleanup before changing queue authority. Preserve the existing browser-blocked partial download and canonical SQLite queue.
