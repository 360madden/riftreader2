# RIFT-Lab-1 receiver deployment: three reuse-first milestones

Date: October 22, 2026 (America/New_York). Scope: **host-side delivery and verification infrastructure**. The three milestones described below are complete within that scope. **Guest installation and Windows restart recovery remain unproved.** Do not conflate a passing local transfer or test harness with successful guest deployment.

## Starting point and preservation

The existing RiftReader2 native coordinator was already running and connected. Verified exact VMware VMX/VNC identity was vmware-vmx PID 52872, RIFT guest process PID 5076, receiver instance 8b9468f7712941f487a232b6cf7c5329. The guest was disarmed and not in a recovery state; **RIFT was not foreground**. No game input, guest receiver restart, VM restart or native host replacement was requested here.

The VM's `ethernet0.connectionType` is `nat`; the Windows host adapter for `192.168.56.1` was independently identified as **VMware Network Adapter VMnet8**. This is a private VMware NAT-side address, **not VMnet1 host-only mode**. The VM has configured read-only shared folders, but `isolation.tools.hgfs.disable = "TRUE"` is present. The restriction was preserved. The guest's WinRM 5985/5986, SMB 445 and RDP 3389 management endpoints were not listening. VMware guest process execution still requires guest Windows credentials distinct from the VM encryption credential. A previously blocked guest diagnostic was not retried or bypassed.

No new Windows service, Task Scheduler task, auto-login, guest process-execution listener, firewall change, guest password, VMware setting or outside deployment dependency was introduced. The previous native host config and canonical durable queue were not reset.

## M1 — VMware VMnet8 private NAT-side package delivery: PASS (host scope)

Staged the *existing* already validated receiver ZIP into a dedicated non-secret folder under:

`artifacts/receiver-milestones-20261022-01/host-only-download/`

Prepared `START-HOST-ONLY-TRANSFER.cmd`, which uses **Python's existing `-m http.server`** and binds only the VMware VMnet8 host-side `192.168.56.1:8765` address. No custom file-transfer server was built.

An actual host-side GET to the bound interface downloaded the original 7,917-byte ZIP and matched its pinned SHA-256 `b219c79b52e70bf2fbbcfa06f0e0d3793174bf9a0f9f1b40c19a49a37f547712`. A bogus private-config path returned HTTP 404, the server was not bound on 127.0.0.1, and the test process was stopped. **This was not a guest-initiated download.**

Evidence: `artifacts/receiver-milestones-20261022-01/m1-stage.json` and `m1-tested.json`.

## M2 — Pinned, reversible guest installer v2: PASS (local/fixture scope)

Built a separate **v2 package**, leaving the original ZIP intact:

`artifacts/receiver-milestones-20261022-01/host-only-download/RR2-Guest-Startup-v2.zip`

SHA-256: `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`; size **8,243 bytes**; six members.

The guest package reuses the existing `scripts/guest_receiver_startup.ps1` byte-for-byte and Windows' built-in per-user Startup folder. Its new `VERIFY-LAUNCHER.cmd` checks the script hash before any installation, status check or removal. Its `INSTALL-ONCE.cmd` verifies the expected guest machine/receiver binary hash and does not elevate, store credentials or send game input. Status and removal wrappers preserve the same source integrity check. The full ZIP contains no guest config JSON, tokens, game files or receiver binary. The installer does not grant a lease or modify the native host.

**13 direct local/fixture checks passed**, including unmodified launcher acceptance, byte-exact ZIP entries, tampered and missing script refusal, three guarded entrypoint refusals, and an actual wrong-machine installation rejection before modifying Windows Startup. The host Startup shortcut existence stayed unchanged. The v2 ZIP was also served and retrieved using the built-in private VMnet8 HTTP server; transferred bytes and SHA-256 matched. The temporary test server was shut down.

For actual transfer, the preferred host launcher is `START-HOST-ONLY-TRANSFER-v2.cmd`. It prints the guest browser URL:

`http://192.168.56.1:8765/RR2-Guest-Startup-v2.zip`

Evidence: `m2-package.json`, `m2-tested.json`, `m2-transfer-test.json`, and the reproducible disposable verifier `test_guest_installer_v2.py`, all under `artifacts/receiver-milestones-20261022-01/`. Guest download, installation and shortcut execution are **not** claimed.

## M3 — Read-only independent restart acceptance: PASS (tests + live baseline)

Added `scripts/verify_guest_recovery.py`, `tests/test_verify_guest_recovery.py` and registered the tests in the repository's `scripts/validate.ps1` full gate.

The checker observes the exact VMware VM identity **before** native HTTP GET status, checks it again afterward, then reads the durable SQLite authority using `mode=ro` plus `PRAGMA query_only=ON`. The regular queue `status()` is intentionally **not** called because it performs expiry maintenance and writes state. It requires supervisor running and cleanup verified, known-console reservation held, guest disarmed and no sampled pressed inputs, queue free/no pending grants and an exact matching VM/game/receiver/supervisor epoch.

The `baseline` and `verify` operations persist one-use, token-free evidence. Receiver-only recovery requires a new receiver instance with the **same** game process. The narrow guest-Windows-restart scenario requires a new receiver instance **and new RIFT process start identity**, with matching build and a new reconciled queue epoch. Both insist on the same VMware/host identities, advancing connection sequence, fresh cleanup evidence, preserved history and no pending work. Changed/mismatched target and session information fails closed. The tool never sends STOP, capture, ARM, action, recover, guest bootstrap or movement commands.

**18 focused tests passed**, including reject cases, fixture SQLite unchanged after a read-only query, failure to overwrite prior evidence, and the simulated host CLI. An actual **live baseline was recorded successfully** at `artifacts/receiver-milestones-20261022-01/m3-live-baseline.json`, with RIFT foreground *false*. A deliberate live no-restart comparison correctly returned `native-connection-not-advanced` and did not create a false-positive result file; see `m3-live-negative-test.json`.

The full main-checkout gate `rr2-m3-full-repo-validation-20261022-01` completed successfully: **364 C# tests, 462 Python tests, 108 Lua checks and 22 shared cases**, zero-warning Release, native published synthetic smoke, locked restore, formatting and deterministic replay. The 18 new tests are *included* in the Python 462, not additive. Gate artifact: `artifacts/validation/20261022T091430Z-e8057f2c`.

The checker deliberately outputs `windowsBootIndependentlyVerified: false` and `shortcutAutoLaunchIndependentlyVerified: false` even after successful session comparison. A fresh receiver/game session alone is not proof that the VM rebooted or that nobody manually started the receiver.

## Deployment still outstanding — one user-in-guest step

1. On the **physical host**, double-click `C:\work\riftreader2\artifacts\receiver-milestones-20261022-01\START-HOST-ONLY-TRANSFER-v2.cmd`. This runs a temporary file server only while the console window remains open.
2. Inside **RIFT-Lab-1 guest Windows**, navigate to `http://192.168.56.1:8765/RR2-Guest-Startup-v2.zip`. If this network route is unreachable, use an existing authorized USB transfer method rather than changing VMware security settings or firewall rules.
3. In guest PowerShell, use `Get-FileHash -Algorithm SHA256` on the downloaded ZIP and compare against `ab5242d0317257dc2b2328f0bc1da98cc24088a2140ea4d968a29c86c23f708f`. Extract the verified ZIP, then run `INSTALL-ONCE.cmd` as the guest's normal signed-in Windows user. Expect a confirmed `installed` or `already-installed` result.
4. Verify `shell:startup` contains `RiftReader2 Receiver.lnk` and `CHECK-STATUS.cmd` reports the expected guest receiver state. Shut down the temporary host server with Ctrl+C.
5. For receiver-only acceptance: take a fresh host baseline, restart only the guest receiver through a reviewed maintenance procedure (not a blind kill), then run the `verify --mode receiver` comparison. For a Windows guest restart, take a **separate fresh baseline**, reboot Windows in the guest, sign in, launch RIFT, and run `verify --mode guest-restart`. Confirm the actual Startup shortcut was invoked by separate guest-side logon evidence before claiming unattended recovery.

The current connection should be preserved until that one-time guest action is ready. **No autonomous guest installation, guest logon/reboot or real receiver-restart trial was performed in these three engineering milestones.**

Links: [current status](../status.md), [prior startup helper qualification](receiver-startup-recovery-2026-10-22.md), [coordination history](navigation-coordinated-host-2026-10-22.md). Standard features reused: [Microsoft Windows Startup folder](https://support.microsoft.com/en-au/windows/experience/startup-boot/configure-startup-applications-in-windows), [VMware Workstation guest operations](https://techdocs2-prod.adobecqms.net/content/dam/broadcom/techdocs/us/en/pdf/vmware/desktop-hypervisors/workstation/vmware-workstation-pro-17-0.pdf).

Model: GPT-6. Reasoning level:
