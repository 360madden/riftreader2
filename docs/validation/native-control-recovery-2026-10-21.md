# Native control connection restored — October 21, 2026

Status: **live native connection restored and accepted**. This closes the missing
host/receiver connection problem after Joey recovered RIFT-Lab-1. It does not
complete the separate multi-controller navigation scheduling rollout.

## Detection before guest access

The recovered VM was identified through all existing host-side checks: VMware's
running-VM list contained the exact RIFT-Lab VMX, the VM log named the current
process/boot epoch, direct process inspection matched vmware-vmx.exe and its
start time, and the loopback console listener belonged to that same process.
The native control ports were initially absent. No former VM or game PID was
reused as proof of current identity.

Observed VM identity for this recovery:

- VMX: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`
- VM process / console listener owner: **52872**, port **5905**.
- VM log epoch: `2026-10-22T00:58:03.378Z` (October 21 EDT).
- Process start ticks: `134371042833296918`.

Fresh VM-identity checks guarded each console capture/bootstrap operation.
The console showed RIFT in the game world. Guest diagnostics then confirmed
`DESKTOP-8632QPL`, the existing receiver build directory, and no listed running
receiver. A displayed SHA-256 matched the recorded installed receiver binary.

## Repair performed

The existing native host was restored with its **unchanged** private configuration,
using its original ports **49712** (agent) and **49715** (loopback operator UI).
A first detached child answered briefly but disappeared after its bounded
launcher ended. Its failed lifetime observation and logs are retained. A Windows
process-start request with startup flags was rejected before creating a process.
The corrected normal-user process creation succeeded and survived subsequent
independent command jobs; no scheduled task, service, firewall rule or global
setting was added.

The running host is PID **49956**, Windows session **1**, started at
`2026-10-22T01:12:15.606414Z`. Its artifact wrapper checks the exact recovered VM,
source hash and configuration hash before entering the existing host main routine.
This is the real application process, not a promise of background AI work.
The wrapper and its logs are under `artifacts/native-recovery-20261021-01`.
Logs containing the operator URL are private local artifacts and must not be
published or copied into ordinary reports.

The guest receiver was started from the already installed directory
`C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad` using its existing
`control-agent.json`. No new binary was deployed and credentials were not changed.
A quoted direct launch produced a visible Windows invalid-path error. A short
`cmd.exe /k` invocation with explicit executable/configuration paths succeeded.
The unsuccessful long/quoted launch attempts were retained, not labeled passed.
The supported receiver singleton was not bypassed, and no existing unrelated
process was killed. Diagnostic/bootstrap keyboard input was used in Windows;
no native ARM or movement command was sent. RIFT foreground was restored using
the freshly confirmed game PID.

Receiver executable SHA-256:
`70553f4ce4a9c73c5043cca16622084734e6c69b1c9e49132c9f622a5f821e4e`.
Host configuration SHA-256:
`90f2b8ab6f575c776941f0b160ff4ce1d8bc8575408975fe7645added5325a2c`.
Loaded host source SHA-256:
`1e1aa3931c189cec055c342e01530ba9ab46127fec37a29d3bb6e9a499528d95`.

## Live acceptance

The authenticated receiver instance is `ad6bffc45e804a879a00d6f2a4c299df` at
`192.168.56.128`. Fresh status identifies **RIFT PID 11748**, process-start ticks
`639282275662265230`, window `0x20456`, client size **1211 × 686**, machine
`DESKTOP-8632QPL`, and the expected game executable/hash. It reports foreground,
disarmed, idle, no recovery required, and no sampled held desktop inputs.

The native client successfully retrieved and hash-verified a fresh screenshot.
Visual inspection showed the game world/HUD rather than the diagnostic console.
A separate identity-guarded VM-console capture was also retained. Native STOP
returned `stopped: true, recoveryRequired: false`; the following status remained
idle/disarmed. Capture and STOP were exercised against the current guest, not
simulated fixtures.

The connection was then left without native requests for **135 seconds**.
The journal recorded the receiver's idle disconnect and reconnect. A fresh status
confirmed the **same receiver instance, VM identity and RIFT process**, still
foreground/disarmed/idle. This check passed at **9:33 p.m. EDT** on October 21
(`2026-10-22T01:33:17.667899Z`). The host survived independently of all temporary
launcher/inspection jobs.

## Evidence, preservation and operational limits

Evidence root: `artifacts/native-recovery-20261021-01/`.
Key records: `evidence/baseline.json`, `host-standalone-process.json`,
`evidence/after-cmd-guest-start.json`, `evidence/native-capture-result.json`,
`evidence/stop-result.json`, `evidence/post-stop-status.json`,
`evidence/idle-reconnection.json`, `evidence/capture-hashes.json`, and
`evidence/visual-review.json`. Final checks and the completion record are separate
files in that evidence directory; inspect their actual result fields.

All **231 pre-existing source files** matched their saved baseline before the
intentional documentation updates. The existing Git index, HEAD and host
configuration hashes matched. No implementation code, package, VM configuration,
credential, dependency, Workbridge runtime or unrelated project was edited.
Only this report and the current status handoff are intended tracked changes;
startup helpers/logs/screenshots remain under ignored artifacts. No commit or push.
No new regression-suite total is claimed for this operational recovery.

The newly started host uses the current tested bounded transport implementation.
The NAV-SCHED admission policy and watchdog are still **not installed by its
normal startup configuration**. Do not interpret restored connectivity as complete
multi-worker exclusion, movement parity or navigation success. Sampled key state
is not proof of RIFT input consumption, and text-entry state remains unknown.
Capture/STOP acceptance does not authorize an unattended movement run.

These normal user processes are not configured for automatic Windows startup.
After a future guest or host restart, re-detect VM identity, existing processes,
listener ownership and guest identity before any recovery action; do not blindly
reuse the PIDs or one-off artifact wrapper. Prefer a short explicit receiver
invocation; investigate a failed launch rather than rerunning it as a new action.

Resume from [current status](../status.md) and the
[native control reference](../reference/native-vm-controls.md). The prior
[recovered-VM bootstrap report](navigation-recovered-vm-bootstrap-2026-10-21.md)
records the earlier unavailable connection and remains historical evidence.

Model: GPT-6 Astra Pro. Reasoning level:
