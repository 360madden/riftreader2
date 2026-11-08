# RR2 two-lab live-test readiness — 2026-11-07 23:26 EST

Scope: **operational preflight completed, live XYZ/navigation test NOT executed**. The authoritative repository is `C:\work\riftreader2` on AMD-DESKTOP. Source branch `codex/modular-foundation`.

## Verified state

| Gate | Lab 1 | Lab 2 |
|---|---|---|
| VMware WS running, exact VMX | `C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx` | `C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx` |
| VMware host VM process PID | 31864 | 32496 |
| Guest RIFT game PID | 6820 | 10612 |
| RR2 controller API port | 49811 | 49921 |
| Controller ownership | RR2 managed helper, healthy | RR2 managed helper, healthy |
| Guest agent | connected, coordination ready | connected, coordination ready |
| Console | reserved, held, not faulted | reserved, held, not faulted |
| Input | **disarmed, idle, zero keys down** | **disarmed, idle, zero keys down** |
| Guest process list | success, 166 processes, RIFT present | success, 146 processes, RIFT present |

VMware `vmrun -T ws list` found exactly both target VMX paths. No direct physical RIFT fallback is present on AMD-DESKTOP.

## Evidence jobs

- Controllers absent initially: `rr2-root-readonly-noauto-controller-lab1-20261108-01`, `rr2-root-readonly-noauto-controller-lab2-20261108-01`, both expected WinError10061.
- Safe managed disarmed recovery: `rr2-root-managed-disarmed-controller-lab1-20261108-01` and `...lab2-20261108-01`, both **exit 0**. Controllers bound to exact VM identities.
- Guest agents safely restored/reused: `rr2-root-guest-agent-recovery-lab1-20261108-01` and `...lab2-20261108-01`, both **exit 0**, result `started`, connected=true, coordination=ready, consoleHeld=true, guestDisarmedIdle=true.
- Fresh cached-credential checks: Lab1 current VMX target absent, explicitly configured same-Lab1 legacy credential present; Lab2 current VMX guest-Windows + encrypted-VM targets present. Both actual guest login/process probes then **passed**. Credentials never printed, and per-session fresh checks remain mandatory.
- Guest verification: `rr2-root-readonly-guest-process-probe-lab1-20261108-01`, `rr2-root-readonly-guest-process-probe-lab2-20261108-01`, **exit 0**, exact VMX/PID and RIFT presence.

## Postflight exact identity and host release (23:29 EST)

- Nonstarting authenticated status: `rr2-root-ready-status-noauto-lab1-20261108-02` and `...lab2-20261108-02`, both exit 0. Both report exact expected RIFT SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, disarmed, idle, no keys down, and `recoveryRequired=false`.
- Lab 1 RIFT start UTC ticks: `639296903905448486`; Lab 2: `639296904548843022`. Status has matching authenticated host/guest instance, exact machine and VM epoch. **Neither agent advertises `nativeXyzVersion` or `nativeReadLeaseVersion`**, a blocked current-transport capability, not a controller failure.
- New immutable HOST-ONLY release built and synthetic-smoke verified from commit `f78e81cfacee41ec0188e2ed9dcd8df9691a27fb`: `artifacts/host-release-f78e81c-20261108-0428z-001/publish/RiftReader2.Live.exe` (52,254,905 bytes, SHA256 `630571770E0F253235653AA2DF28F60699A5FAF63C04B77E6F175042AABDAE27`), ZIP `bundle/agent.zip` (46,809,102 bytes, SHA256 `1703528A0BE52EFDB618AA8F59B07E77325061FAF56D5E44A54C7F69F5337492`). Not staged to guests.
- Publisher avoided modifying tracked win-x64 RID-incomplete lockfiles by building from an isolated exact git archive. Do not treat host artifact presence as guest deployment or live native XYZ acceptance.
- The connected guest agent needs a separately admitted fleet update. Guarded `guest_agent_launcher.py update --managed-lab labN --release ...` stages no binary. It requires explicit maintenance ownership, pre-staged verified immutable bytes, queue/lease safety, STOP and clean shutdown, and postflight version, actual guest SHA/ACL/capability checks. No update was done during this milestone.

- Strictly read-only queue snapshot `rr2-root-readonly-global-queue-snapshot-20261108-01` passed (SQLite `mode=ro`, `query_only=ON`): **both resources blocked=false, holder=null, pending=0** at 04:31:09Z. This establishes clean RR2 queue state, **not** quiescence of unleased foreign/legacy native readers.
- Managed guest-updater same-lab legacy cached-credential fallback and no-prompt gates were **fixed offline** in source commit `8a66ec0`; focused 27/27 and session-regression 25/25 passed, with independent review. No live guest update attempted. This resolves the launcher source blocker, but does not establish exclusive maintenance ownership or deployed native capability.

## Next bounded live-test gates

1. Revalidate both `control_client.py --config artifacts/control-fleet-live/labN/host.json --no-auto-start status` (read-only; no duplicate startup), ensure exact PID/start, disarmed, idle and no held keys.
2. Establish cross-chat/foreign native reader quiescence or exclusive native read admission; `Greeting Jimmy` has not explicitly relinquished any live reader.
3. Exact RIFT SHA is verified for both guests (`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`). But both currently installed guest agents omit `nativeXyzVersion` and `nativeReadLeaseVersion` from status; check installed agent release/maintenance owner before any guarded update. Host-only current release below is **not deployed**. Do **not** run scripts pinned to old executables.
4. Start with a bounded, exact-identity, source-current, lease-admitted, **passive** XYZ+guard sample on one lab. Distinguish cached XYZ, guard availability, source candidate from qualified fresh world coordinates. Validate stop and session release, then repeat on the other lab independently.
5. Only if verified and separately reviewed: bounded movement test with explicit STOP / key-up and observed XYZ delta. No game input was sent in this readiness milestone.

No VM reset, OS/game restart, UI reload, movement keys, clicks, native memory read, foreign lease takeover or guest Codex job occurred during this readiness preflight.

Status: **both labs operationally ready; live telemetry/source-build and cross-chat lease gates outstanding**.
