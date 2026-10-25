# Near-time native/Lua motion comparison — V17 offline gate (October 24, 2026)

Status: **reviewer implemented and tested offline; no movement trial, V16 STOP, V17 launch, or new guest sample has occurred.** This is a proposed evidence gate, not a report of measured motion. [The current live native XYZ originals](../validation/native-pointer-xyz-first-live-2026-10-24.md) remain a stationary **candidate-only-not-synchronized** result.

## Why a separate reviewer is necessary

The earlier strict native XYZ reviewer, `scripts/review_current_pointer_xyz.py`, expressly requires a stationary advancing Lua reference. That is correct for the initial one-owner/one-root identification, but cannot validate a moving before/after pair. The new `scripts/review_native_motion_pair.py` is an **offline, no-input, no-process, no-network** consumer of four original observations: one native pointer owner window and one advancing typed-Lua snapshot at **each** of two states.

Both native reports must resolve the exact same game process/build epoch, module RVA `0x32E0200`, a single pointer hop, and 816 actual owner bytes with finite float32 XYZ at `+0x320/+0x324/+0x328`. The typed source must be a separately SHA-pinned, strict C# `inspect-typed-wire` result with valid independently advancing sequence/frame clocks, one player unit, distinct original snapshots/wires and complete acquisitions.

The tool accepts **existing original file paths** and creates exactly one new result file. It never overwrites, changes the game, or opens a controller.

### Example, run in PowerShell on the Windows host

```powershell
cd C:\work\riftreader2
& C:\Python314\python.exe scripts\review_native_motion_pair.py `
  --native-before C:\path\to\pre-pointer-original.json `
  --native-after C:\path\to\post-pointer-original.json `
  --request C:\path\to\exact-pointer-request.json `
  --typed-comparison C:\path\to\strict-advancing-lua-comparison.json `
  --typed-sha256 EXACT_64_CHARACTER_UPPERCASE_HEX `
  --output C:\path\to\new-motion-review.json
```

Default gates (caller can tighten within hard-coded limits):

| Property | Gate |
| --- | --- |
| Native and Lua sample identity | Exact process PID, start ticks and game executable SHA |
| Native pointer semantics | Exact root, one raw verified pointer hop and 816 owner bytes |
| Lua source | Distinct complete snapshots, distinct wire hashes, advancing sequence/clock, same player |
| Chronology | Both before acquisitions precede both after acquisitions; no overlapping clusters |
| Native–Lua time per state | Absolute difference at most **180 seconds**, checked on unrounded durations |
| Native–Lua XYZ per state | All three differences at most **0.02 game units** |
| Detectable motion | At least **0.1 units** on any Lua axis and matching native movement |
| Delta agreement | Each native-minus-Lua displacement difference at most **0.04 units** |
| Reproducibility | SHA-pinned inputs, deterministic output, no overwrite |

Result states:

- `candidate-motion-consistent`: both states match and significant movement agrees, still **not causal proof**.
- `candidate-motion-disagrees`: typed source moved but the native endpoint or displacement did not agree.
- `insufficient-source-motion`: the qualified typed source was stationary or below threshold.
- A malformed, stale, wrong-epoch, overlapping-time or unqualified input is **blocked**; no output is published.

Every accepted output uses qualification `candidate-only-no-stimulus-or-clock-skew-proof`. A strict numeric match is **not** permission to describe fully validated player controls, field semantics or speed. The host/guest clock offset has not been measured, and a typed frame might be older than its enclosing memory snapshot. A future movement-action audit must independently verify key-down/up and where the stimulus falls between the two states.

## Safe operational sequence to mature next

1. The live read-only V16 check at **2026-10-25T00:25:38Z** found authenticated ready/running coordination, the exclusive VM console held, RIFT foreground, guest disarmed/no held keys, unchanged exact RIFT PID **6940** and VMware PID **38044**. **Do not create a second VM controller or call VNC directly.**
2. The existing no-overwrite host-only handover preparer successfully created `coordinated-host-plan-v17.json` (SHA-256 **BF5F56D6219ED0E2AF44CE320CDD09B96C8FA73B7B39418FFFF3191FAE9B9727**) and `run-coordinated-host-v17.py` (SHA-256 **E84E6FC5B43D9461A9217CBBC0EF37F9D23C24292877D0B4EE5442CAD7FACEE2**) at **2026-10-25T00:26:31Z**. It confirmed the same VM epoch, current V16 owner PID **28496**, free cleaned canonical queue, and no STOP marker. **The successor is staged only; V16 remains the owner.**
3. Implement and syntax-test an exact-epoch **pre-state** guest trial while V16 is normally STOPped and the VM authority is quarantined. Gather a fresh typed snapshot and pointer-original within a bounded near-time window, transfer both with source hashes and one-use exact-peer ZIP receipts; no game movement during the shell session. Restore game foreground and start the already staged V17 coordinator after successful cleanup.
4. Through V17's **existing** access-queued controller, obtain and review a current screenshot, obtain a legitimate short-lived grant, then run at most one documented bounded key pulse (20–250 ms) with stop/release and independent evidence. Reject focus loss, dialogs, stale process/build, text-entry uncertainty, failed release or missing lease. This step must not be attempted while the game state cannot be visually reviewed.
5. After the pulse is safely complete and V17 has normally STOPped, repeat an exact-epoch **post-state** guest typed snapshot and pointer-original, then close the shell and recover a separately prepared successor. No V16/V17/guest input may overlap. Transfer post originals separately with no-overwrite SHA/size receipts.
6. Run strict C# typed-wire before/after inspection to establish same-player producer advancement. Then run the new offline motion reviewer with the saved originals and source SHA. An actual motion **candidate** requires four near-time originals and a separate reviewed control/clock timeline. If any stage fails, keep the prior evidence, record the failure and restore a safe owner instead of promoting a field.

The earlier real V16 source (21:34–21:36Z) and native reads (00:00–00:02Z) are deliberately **rejected** by the new paired-motion reviewer: both typed captures predate both native captures, so the supposed pre/post intervals overlap, and they are more than two hours apart. This negative control prevents reusing a stationary numerical match as movement proof.

## Validation and artifacts

- Focused offline tests exercise exact synthetic motion, no-movement, missing/wrong values, wrong epoch, forged pointer bytes, changed source digest, mismatched player/wire, reversed/overlapping times, stale lag (including sub-millisecond boundary), duplicate JSON, deterministic replay/no-overwrite and the real V16 negative control.
- Generated V17 launcher/plan and original V16 screenshots/reports are ignored under `artifacts/update-recovery-20261023-01/`. They are local evidence, **not committed**. Tracked source, tests and this contract are designed to be small and repeatable.
- **Validated release gate:** PowerShell 7.6.8 `scripts/validate.ps1` exited **0** at **2026-10-25T00:34:39Z**. Exactly **660 Python tests** passed (including all 17 new motion tests and the real ignored V16 original negative control), plus 432 .NET 10 tests, 108 Lua lifecycle/encoder checks, 22 Lua→C# cases, locked restore, native publish/smoke, formatting, deterministic replay and 471 documentation links. Evidence: `artifacts/validation/20261025T003336Z-def5acac`.
- **Real independent CLI negative control:** invoking the new direct script on the two actual V16 native originals plus the real earlier advancing Lua pair exited **2** with `before/after observation intervals overlap`; no motion-review output was published.
- V17 is not an active owner until a verified V16 normal STOP and separate approved launch are actually performed.
