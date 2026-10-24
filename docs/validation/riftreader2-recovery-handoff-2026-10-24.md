# RiftReader2 recovery handoff — October 24, 2026

**Purpose:** Preserve the last verified checkpoint before a ChatGPT/workflow timeout. This document is a recovery handoff, NOT a claim that the timeout affected RIFT or that new discovery was completed. Do not resume old, unverified VM commands. All times are America/New_York unless labeled UTC.

- **Workspace:** `C:\work\riftreader2`
- **Branch:** `codex/modular-foundation`
- **Verified pre-handoff HEAD:** `a7c172bf3c1c704aefaff797a0672e97a14b44b9`
- **Relevant prior commit:** `1a8481967beb06dcac9b1126c0050b40e736b6d6` (verified guest PowerShell native pointer recovery)
- **Other baseline:** `84202d3a33c759b8ad2162b779ad1e71e79d9b34` (failed Windows Run transport; historical)

## 1. Verified current state and last known good evidence

A fresh, **read-only** status query made during handoff preparation on
2026-10-24 at approximately 00:48 EDT confirmed:

- Exactly one running VMware guest listed by vmrun:
  `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`.
- Coordinated host `connected=true`, coordination `ready`, supervisor `running`.
- Guest RIFT PID `2768`, creation ticks `639282812576974124`.
- Executable SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
  This matches the October 19 build; **the on-disk executable is unchanged**.
- Game foreground `true`; `armed=false`, `busy=false`,
  `recoveryRequired=false`, `desktopInputsDown=[]`.
- Guest agent instance `8b9468f7712941f487a232b6cf7c5329`.
- The read-only host status confirms the **control** connection, not a
  restored **typed Lua** readback; do not equate these two observers.

Do **not** reuse any process IDs, absolute heap addresses, receiver sequence
numbers or VM session IDs without reacquiring fresh values when resuming.

### Native position pointer — successfully resolved, semantic validation pending

The existing installed `RiftReader2.Live.exe follow-pointer` ran **once**
against the live current-process request via the existing **guest PowerShell
console** (not Windows Run). It completed a native 816-byte terminal read
with no failed read. The canonical request was reconstructed in guest Windows
using `Set-Content`, `Add-Content`, `certutil -decode`, then its SHA-256
was checked **inside** the guest before the reader ran:

- Request SHA-256:
  `76FE68E1446396AD32E0E6CC5D0219DE6C5E9205C4FAF9BED66E21C225CE505E`.
- Root RVA `0x32E0200`, offsets `0x0` then known XYZ float32 offsets
  `0x320 / 0x324 / 0x328` within the terminal owner bytes.
- Observed native XYZ: **(7459.142, 863.7189, 2973.08)**.
- Guest-reported native report SHA-256:
  `40351546D62620736D40BA89B487EA8157E75DFA713B7B1E1D71F1790E0896AE`.
- Guest-local report:
  `%TEMP%\rr2-oct23v3-report.json`.
- The host has screenshot and console evidence, **not a byte-for-byte host copy
  of this complete native report**. Do not claim independent full-report review.
- Tracked evidence:
  `docs/validation/rift-position-pointer-recovered-2026-10-23.md`.
- Reusable host-only planner:
  `scripts/prepare_direct_shell_pointer.py`; focused **8/8** tests passed.
  Historical Run-dialog planner failures are superseded for this use.

This proves the same-build root could still be read in another process
epoch after the recent RIFT maintenance. It does **not** yet prove the XYZ
values represent the current player because a fresh, independent typed Lua
coordinate sample in that **same** game process is missing. Field meaning
remains **candidate-only**; neither update-survival with a different
executable nor automatic restart recovery is established.

### Current blocker — typed Lua observer broad-scan budget

The newest existing readback-aware guest observer is installed at

`C:\RIFT_TRANSFER\GuestReadback\GuestObserver\RiftReader.GuestObserver.exe`

and was restarted once after closing the old passive version. The newer
executable's observed SHA-256 is

`DFEB9ED1CFC7E9D79B8B7D23696CD41A370B0ADF8B110E2F3449557228E6C3F`.

It writes guest-local JSON for the correct current RIFT game PID and build,
but its `readback.status` is **blocked** with reason
`scan-byte-budget-exceeded`. It therefore does **not** publish
`readback.typedApi` or fresh XYZ coordinates. The older passive observer
could observe the process but had no typedApi; it was stopped cleanly.

Read-only source inspection found the inherited guest readback implementation
defaults to **4 GiB** scanned, **10 seconds** per pass and **1 MiB** chunks.
An incomplete scan fails closed before typed-frame freshness evaluation.
The broad private-memory scan apparently now exceeds its budget. **This
does not establish that the Lua producer frame is absent or corrupt.**

The old observer's HTTP delivery target
`192.168.56.1:49712/observation` conflicts with the current coordinated
host using port **49712**. Guest-local JSON writing remains independent
from failed HTTP delivery. **Do not seize, rebind or replace port 49712**
solely to obtain typed readback.

Detailed source/evidence:
`docs/validation/rift-typed-readback-blocker-2026-10-23.md`;
ignored screenshot evidence:
`artifacts/update-recovery-20261023-01/guest-readback-block-settled/screen.png`
(SHA-256
`7EF8C8A6D8DDD23BD463670F760F2353934AF60B11E8FDCF67F8FC6CEF7221C1`).

### Control, navigation, and guest startup

- The coordinated native control host was restored to **V7**, historical
  process PID `34352` in Windows session 2, according to the October 23
  readback record. The newly queried live status confirms the host is
  **connected/ready**, but the PID was not independently re-read during this
  handoff. Detect its actual PID afresh before a maintenance shutdown.
- Host/guest control and supervisor are healthy/disarmed; this is **not**
  proof that background automatic startup at guest logon works.
- Durable navigation queue authority:
  `artifacts/native-coordination-live/queue.sqlite3`,
  resource `vm:rift-lab-1`. A prior recovery made a forensic copy of its
  database/journal and found integrity OK. Preserve live database AND
  journal; do not delete/replace them or silently recreate queue authority.
- Concurrent extensive uncommitted navigation/control modifications existed
  before this handoff, including `scripts/control_host.py`,
  `scripts/control_client.py`, `scripts/vm_console_native.py`,
  `scripts/nav_* `, `docs/status.md`, `docs/README.md`,
  `scripts/validate.ps1`, several tests, and validation notes.
  **Do not stash/reset/stage/commit/overwrite those files** from this handoff.
- The actual guest Startup installer and unattended logon/reboot recovery
  remain unverified. Relevant:
  `docs/validation/receiver-startup-recovery-2026-10-22.md`,
  `docs/validation/receiver-transfer-pythonw-2026-10-22.md`.
- Historical bounded S/A/D, forward/turn, camera, STOP/release and queue
  proof remains recorded, but is not equivalent to unattended navigation.
  Do not repeat basic key discovery when resuming this compatibility pass.

## 2. Roadmap with acceptance gates

| Sequence | Scope | Status as of this handoff | Required acceptance |
|---|---|---|---|
| 0 | Preserve current code, memory evidence, VM and queue | **Complete** | Unique tracked handoff; unrelated dirty files untouched |
| 1 | Recover VM, game identity, native coordinator and guest receiver | **Complete with startup limits** | Fresh VM/game PID/start/build; host connected and idle; queue preserved |
| 2 | Confirm executable compatibility after recent RIFT maintenance | **Complete for same on-disk build** | SHA-256 equals October 19 baseline; no claim about server-side changes |
| 3 | Replace failed Windows Run transport; read historical pointer | **Complete for raw native read** | Guest request hash checked, 816-byte read success, native XYZ recorded |
| 4 | Restore independent **fresh typed Lua API** | **BLOCKED — highest priority** | Bounded positive typed frame with complete producer header/footer, unique player, advancing source sequence/time, strict PID/start/build and owner validation; malformed/stale/conflicting frames rejected |
| 5 | Reconcile native XYZ against current process Lua XYZ | **Pending phase 4** | Fresh near-time same-process independent typed XYZ matches or contradicts native read, with raw report retained on host and confidence/limits documented |
| 6 | Re-qualify current-health/max/resource fields | **Not restarted** | Fresh same-epoch candidate discovery and changed-state comparisons; do not reuse addresses from PID 8356; distinguish current health from maximum and replicated copies |
| 7 | Confirm unattended receiver recovery on Windows login/restart | **Not yet qualified** | Real startup installation and actual restart/logon acceptance; no status shortcut |
| 8 | Resume concurrent navigation Tracks A/B/C and guarded experiments | **Partially implemented with retained evidence** | Exclusive queue ownership, fresh image/binding review, bounded movement/camera inputs and reviewed STOP/release; avoid conflicting live access |
| 9 | New native field discovery / future player automation | **Deferred** | Finish current compatibility and semantic evidence gates before expansion |

There is **no meaningful single percentage complete** for the project;
foundation/control infrastructure is relatively mature while recovery,
typed data and future navigation research retain different acceptance
gates. Use the statuses above instead of inflating progress estimates.

## 3. Safe next actions after opening a new chat

1. Inspect `AGENTS.md`, this handoff, `docs/status.md` and
   `docs/validation/rift-typed-readback-blocker-2026-10-23.md`.
   Run `git status --short` and `git log -3 --oneline`.
   Preserve all existing modified/untracked navigation files.
2. Run **read-only** native-host `/api/status` through the existing
   `scripts.control_client.ControlClient` and saved host configuration;
   verify exact VM/game epoch, coordinator, queue ownership, guest
   idle/disarmed/no held inputs. Do not assume the historical PIDs persist.
3. Read the V1 typed-readback code at
   `C:\rift modding\RiftReader\reader\RiftReader.Reader\GuestReadback`
   without modifying V1. Investigate the producer `RRAPIVAL` /
   `RRAPIVALEND` frame and prior known-positive successful scan reports.
   Prefer a **bounded, exact-process memory-region selection** or validated
   reusable frame locator over blindly raising the 4 GiB/10 s scan budgets.
4. Write tests that prove a uniquely selected, complete fresh typed frame,
   advancing source sequence/time and fail-closed behavior on ambiguity,
   stale epochs, malformed frames, partial reads and wrong player/build.
   Do not treat a missing result as zero.
5. Only after fresh typed readback is verified, compare native XYZ in
   this *same* process epoch; copy the guest-local native report to a
   pinned, private host evidence path if an existing secure transport can
   do it without changing VM settings. Preserve its full SHA-256 and
   independent Lua source evidence.
6. Defer new health-resource and navigation discovery until steps 4–5
   produce a reliable semantic baseline. Separately keep guest Startup
   recovery on its own roadmap lane.
7. Run focused tests, then `pwsh -NoProfile -File scripts/validate.ps1`
   before a scoped commit. The most recent documented full gate for the
   pointer recovery was **364 C# / 462 Python / 108 Lua / 22 Lua-C#**,
   with zero-warning .NET 10 Release; the eight new direct-shell tests
   were separately run, not integrated in the concurrently edited gate.
   Do not treat historical test results as a fresh run.

## 4. Source files and evidence index

- Native pointer and transport:
  `docs/validation/rift-position-pointer-recovered-2026-10-23.md`
- Typed Lua blocker and scan-budget root cause:
  `docs/validation/rift-typed-readback-blocker-2026-10-23.md`
- Historical failed Windows Run transport (superseded):
  `docs/validation/serial-guest-pointer-transport-2026-10-23.md`
- Direct-PowerShell request planner:
  `scripts/prepare_direct_shell_pointer.py`
- Direct-PowerShell tests:
  `tests/test_direct_shell_pointer.py`
- Historical native-field evidence and position:
  `docs/validation/native-player-fields-2026-10-19.md`,
  `docs/reference/native-field-evidence.md`
- Coordinated host recovery:
  `docs/validation/rift-update-runtime-recovery-2026-10-23.md`
- Canonical navigation ownership:
  `docs/planning/navigation-access-queue.md` and live queue path above.
- Earlier camera/movement evidence:
  `docs/planning/native-vm-control-roadmap.md`
- Overall foundation roadmap:
  `docs/planning/implementation-roadmap.md`

## 5. Scope of this handoff

Documentation-only recovery snapshot. **No** game input, RIFT process
restart, new memory read, V1 source modification, Windows settings change,
VM power operation, queue mutation, background task creation or guest
deployment was performed to produce this document. Its current facts
were checked read-only and may change after this timestamp.

Do not interpret the user-visible timeout as proof that any game or
host process timed out. Restart work from independently verified identities,
not from guesses or the prior command prompt.
