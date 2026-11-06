# VMware RIFT Lab Essential Software Setup

Date: 2026-11-06 (America/New_York)
Scope: RIFT-Lab-1 and RIFT-Lab-2. Host source: `C:\work\riftreader2`.

## Target state

Both independent Windows 11 x64 guests should have:
- VMware Tools running and PowerShell 7 available (already present).
- Git for Windows.
- Python 3.14 with a real interpreter, not merely a WindowsApps alias.
- .NET 10 SDK for C# development.
- Current Node.js Active LTS with npm for support tooling.
- WinGet for repeatable developer-tool installation.

Optional, defer until a demonstrated use: WinApp CLI, OpenSSH Server, full Visual Studio or native C++ toolchains, complete Workbridge-MCP source tree.

## Installation and verification

Use the **host** Python executable, not a guest shell, from the root of `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe scripts\lab_software_inventory.py --lab all

# One package, one guest at a time; use only when absent:
C:\Python314\python.exe scripts\lab_software_install.py --lab lab1 --package Git.Git
C:\Python314\python.exe scripts\lab_software_install.py --lab lab2 --package Git.Git
# Allowed alternatives: Python.Python.3.14, Microsoft.DotNet.SDK.10, OpenJS.NodeJS.LTS.

C:\Python314\python.exe -m unittest discover -s tests -p test_lab_software_setup.py -v
```

These scripts use the existing VM-specific cached-credential checks and exact VM identity verification in `lab_codex.py` and `vmware_guest_session.py`. Installation is limited to four allowlisted WinGet package IDs. WinGet is invoked silently without the `--allow-reboot` flag. Each guest writes a JSON result, copied back to `artifacts/lab-software-install` and provenance checked. Inventory artifacts are in `artifacts/lab-software-inventory`.

## Boundaries

- Do not restart, close, foreground, or send inputs to any RIFT game.
- Do not restart either VM or Windows without first asking Joey.
- Do not copy the 14 GB Workbridge-MCP source tree for this baseline.
- Do not disable Windows security or broadly change group membership to install developer packages; the observed guest session already reported an elevated token.
- If a package install returns nonzero, inspect the recorded report and resolve the exact failure before retrying.
- Always verify effective executable paths and versions in a **fresh guest inventory** after installing, because WindowsApps app aliases and stale PATH entries can be misleading.
- Leave Lab 1 and Lab 2 independent; never assume they have identical installed state.

## Baseline inventory (before installs)

- Both guests: Windows 11 Home x64 build 26300, 8 GiB RAM, VMware Tools running, PowerShell 7.6.9, WinGet 1.29.380, elevated guest command token.
- Lab 1: 39.16 GiB free. Lab 2: 50.46 GiB free.
- Python interpreter, .NET SDK, Git and Node.js were not verified prior to installation.
- Windows OpenSSH **client** was present; OpenSSH Server was not tested and is not required for VMware Guest Operations.

## Final acceptance checklist

- [x] Lab 1: Git, Python/pip, .NET SDK, Node/npm resolve with successful version probes.
- [x] Lab 2: Git, Python/pip, .NET SDK, Node/npm resolve with successful version probes.
- [x] Both guests: VMware Tools still running.
- [x] No VM reboot or game restart.
- [x] Ten offline report validation tests pass.
- [x] Disk free: Lab 1 = 36.91 GiB, Lab 2 = 48.23 GiB; both machine identities validated.

## Verified result (2026-11-06)

| Dependency | Lab 1 | Lab 2 |
| --- | --- | --- |
| Git | 2.56.0.windows.4 | 2.56.0.windows.4 |
| Python / pip | 3.14.10 / 26.2.2 | 3.14.10 / 26.2.2 |
| .NET SDK | 10.0.403 | 10.0.403 |
| Node.js / npm | 26.13.0 / 11.20.0 | 26.13.0 / 11.20.0 |
| PowerShell | 7.6.9 | 7.6.9 |
| WinGet | 1.29.380 | 1.29.380 |
| VMware Tools | Running | Running |

All eight WinGet installation reports returned exit code 0, and a separate post-install inventory verified the live executables. The explicit Python interpreter path is under the guest user's local Programs folder. No VM or RIFT game reboot/restart was executed. Node.js 26 is the Active LTS series as of November 2026; Node 24 is now Maintenance LTS.

The OpenSSH *client* binary is present but its `-V` probe did not return a clean result in this scripted PowerShell environment; remote SSH capability is **not** marked verified. Windows App Development CLI (`winapp`) was not installed because it is optional for current RIFT work.
