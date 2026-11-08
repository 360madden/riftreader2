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

## Next bounded live-test gates

1. Revalidate both `control_client.py --config artifacts/control-fleet-live/labN/host.json --no-auto-start status` (read-only; no duplicate startup), ensure exact PID/start, disarmed, idle and no held keys.
2. Establish cross-chat/foreign native reader quiescence or exclusive native read admission; `Greeting Jimmy` has not explicitly relinquished any live reader.
3. Verify exact guest game executable SHA/build, deployed agent version/capability and any leases/queue owners before test. The host-only native release `artifacts/native-xyz-refresh-branch-20261108-0345z-002` is **stale and not deployed**; candidate code is undergoing final source review/commit. Do **not** run scripts pinned to old executables.
4. Start with a bounded, exact-identity, source-current, lease-admitted, **passive** XYZ+guard sample on one lab. Distinguish cached XYZ, guard availability, source candidate from qualified fresh world coordinates. Validate stop and session release, then repeat on the other lab independently.
5. Only if verified and separately reviewed: bounded movement test with explicit STOP / key-up and observed XYZ delta. No game input was sent in this readiness milestone.

No VM reset, OS/game restart, UI reload, movement keys, clicks, native memory read, foreign lease takeover or guest Codex job occurred during this readiness preflight.

Status: **both labs operationally ready; live telemetry/source-build and cross-chat lease gates outstanding**.
