# Native host handover: same-VM-epoch preparation (V10 → V11)

Date: October 24, 2026 (America/New_York). Scope: **preparation only**, not a coordinator restart, VM restart, guest action, or gameplay experiment.

## Why

During the live [V9 → V10 recovery](native-v10-foreground-capture-2026-10-24.md), the original `scripts/prepare_native_host_handover.py` only supported a **changed** VM epoch with a quarantined resource. A same-VM-epoch coordinator handover required careful manual launcher/plan construction. A separate JavaScript JSON round-trip rounded Windows `startTicks=134372941117887852`, a 64-bit timestamp well beyond the exact integer range of JavaScript numbers. That defective plan was detected **before** its host launched and corrected manually; V10 launched with exact identity. This is a loss-of-precision hazard, not evidence of a game or VMware change.

## Guarded implementation

`scripts/prepare_native_host_handover.py` now supports explicit `--same-epoch`; the no-flag default retains the old restarted-VM quarantine behavior.

- Both modes verify the prior plan/config/runtime hash pins, previous coordinator's **live process identity**, canonical queue resource, target VMX/port, unchanged source template contract, and unused successor artifact paths.
- All queue preflights use one SQLite snapshot with `mode=ro` and `PRAGMA query_only=ON`, without expiry sweeps, authority resets, or writes. Active/queued/cleanup requests are rejected.
- **Default restarted-VM mode:** requires `blocked=1`, no queue holder, and an actually changed VM process epoch at the same VMX/port.
- **Same-VM-epoch mode:** requires `blocked=0`, no holder, a nonempty prior cleanup receipt, and exact equality of the full current VMware identity with the prior launch plan.
- The successor plan is assembled in Python and serialized with Python JSON, preserving full 64-bit integers. Launcher/plan are created exclusively; an existing successor artifact is never overwritten.
- No mode launches, kills or stops a coordinator; reserves a second console mutex; dispatches VM/guest/game input; creates a shutdown marker; or edits queue authority. Future startup must still enforce its independent mutex/identity/queue checks.

## Live preparation and verification

After **7/7 focused tests** passed, the following command completed successfully from `C:\work\riftreader2` using Python 3.14:

```powershell
C:\Python314\python.exe -m scripts.prepare_native_host_handover --previous v10 --successor v11 --same-epoch
```

- Returned `handover-prepared-not-executed`, `mode=same-vm-epoch`, V10 PID **8168**, VMware PID **38044**, log epoch `2026-10-24T05:41:51.833Z`.
- New **ignored one-use artifacts only**:
  - `artifacts/update-recovery-20261023-01/coordinated-host-plan-v11.json`
  - `artifacts/update-recovery-20261023-01/run-coordinated-host-v11.py`
- Independent read-back verified V10 owner process is **still alive**; V10 and V11 full `vmIdentity` objects match; exact new `startTicks=134372941117887852`; all five runtime hashes match; only `shutdownFile` and `createdUtc` differ; V11 shutdown marker absent; canonical queue `blocked=0`, holder absent, cleanup receipt present, and no pending requests.
- **V11 is not running. V10 remains the authoritative live coordinator.** The V11 plan is bound to this current VM epoch and must not be launched if the VM process epoch has changed.

Direct checks passed: **7/7 focused handover tests**, **496/496 Python tests** via Python 3.14 unittest discovery, **364/364 .NET 10 tests** (90 Live + 274 core) via `dotnet test RiftReader2.slnx --configuration Release --no-restore`, and `git diff --check`. These are independent of the live coordinator.

The full `scripts/validate.ps1` gate could not begin in its expected PowerShell 7 context through Workbridge: `pwsh` and its conventional executable path were not available as executable targets; the Windows PowerShell 5.1 fallback failed on its Lua `-c` quotation/argument translation in the first line. This is **not** a failure in the new handover tests, but the full script's build/publish/Lua/link-check gate must not be claimed as passed without a later successful run.

## Later operational handover, only when required

Before using V11, refresh the VM/game/receiver/coordinator identities and queue snapshot. Obtain genuine V10 STOP/release evidence and verify its normal exit, listener closure, authoritative queue quarantine, and console mutex release. Recheck all V11 plan/source/runtime hash pins and current VMware epoch **after** that exit. Launch V11 only if its independent startup checks pass, then verify supervisor initial cleanup, guest idle/disarmed state and canonical receipt. If any epoch or ownership precondition differs, **stop and prepare a fresh plan**, preserving existing receipts and artifacts. Never use this prepared plan as automatic permission to restart or replay game input.

Next discovery priority remains qualifying native/addon movement and world-object fields against live captured evidence, with fresh game build/session identity and no inferred field meaning from a screenshot alone.
