---
kind: riftreader2-codex-task-handoff
repository: 'C:\work\riftreader2'
branch_at_checkpoint: codex/modular-foundation
starting_head: 4c88a231a4de6afc94cb1418ab8ee83d6d24fdfe
checkpoint_date_et: 2026-11-06
active_task: optimize-rift-console-interaction-latency
timebox_minutes: 90
next_priority: remove-remaining-original-riftreader-runtime-dependencies
live_game_input_authorized_by_this_document: false
remote_push_authorized_by_this_document: false
---

# Codex handoff — speed up RIFT interactions, then resume standalone RR2

This is a **coding handoff** for a local Codex session opened against the
existing **Windows** repository `C:\work\riftreader2`, not a separate Linux
scratch clone. Verify `pwd`, branch, HEAD, worktree status, local environment
and any new changes before editing. If the repo is inaccessible from the
Codex execution environment, stop and report the mismatch; do not silently
work on a detached copy.

## First 5 minutes: regain context

1. Read `AGENTS.md`, `docs/status.md`, this handoff and the
   [standalone Lab 1 handoff](handoff-2026-11-06-standalone-lab1-accepted.md).
2. Review latest 10 commits. At transfer, Git HEAD was
   `4c88a231a4de6afc94cb1418ab8ee83d6d24fdfe` on
   `codex/modular-foundation`; worktree was **clean**.
3. Respect all existing exact-build/process/controller/queue freshness and
   STOP/key-release gates. Do not reuse historical PIDs or reader nonces.
4. Other independent ChatGPT sessions might use this repo; preserve their
   edits and avoid concurrent writes to shared files. One coordinator owns
   commits and `docs/status.md`.

## Why this task exists

A comparatively simple reviewed Lab 1 UI task had too much round-trip
overhead. On Nov 6, one successful `/reloadui` was delivered at
`2026-11-06T23:42:47Z`; one successful RR2 binding was delivered at
`23:49:05Z` (~6m18s between *two actions*, **not** a benchmark of either
command or the RIFT UI reload). Windows Terminal initially obscured RIFT;
after an independently reviewed minimize, the game was visible. LuaPadModern's
window was closed and the RR2 Casting panel hidden through reviewed clicks.
An exclusive managed-controller handoff, repeated snapshots/reviews, helper
launches and tool round trips added substantial orchestration overhead.
Actual per-step latency has **not** yet been measured; do not assign
invented proportions to any cause.

Both commands succeeded. **Joey explicitly cancelled a delayed "try again"
instruction. DO NOT REPEAT `/reloadui`, `/rr2guide bind`, or any game input
as part of this coding task.** No VM, RIFT process, or game UI restarts.

## Mission (timebox: 60–90 minutes, then report)

Make the **existing** guarded RIFT console route faster and easier to use,
without designing another automation platform. Prefer one bounded
prepare/focus/approved-command/release/receipt entry point, only if it is
actually simpler and avoids duplicate controller ownership.

Inspect these *existing tracked sources* first:

- `scripts/addon_command_console.py`
- `scripts/vm_console_native.py`
- `scripts/ensure_controller.py`
- `scripts/managed_controller_receipt.py`
- `scripts/controller_host_entry.py` and `scripts/controller_task_entry.py`
- `tests/test_addon_command_console.py`
- `tests/test_vm_console_native.py`
- `tests/test_vm_console_reservation.py`

Suggested sequence, with explicit subtask/file ownership if useful workers
are available:

1. Map the real call chain for window discovery, obstruction handling,
   screenshots/reviews, exclusive controller handoff, text entry, result
   receipt and key release. Record how many remote/process round trips are
   involved; separate observed timings from estimates.
2. Identify 1–3 concrete, low-risk reductions: reuse existing healthy
   capability and identity checks, batch **compatible** read-only metadata,
   avoid unnecessary extra screenshot captures while still requiring
   reviewed foreground/input admission, and restore the same owner safely.
3. Implement the smallest change. Preserve narrow command allowlists,
   screenshot binding/review freshness, process/VM identity, exclusive
   access, key-up/STOP on every failure, timeout bounds and no competing
   controller. Do not automatically dismiss arbitrary dialogs, bypass
   quarantine/permissions, or silently re-arm.
4. Test **offline with mocked/fake console and ownership receipts** first.
   Fail closed for changing PID/start/build, expired screenshots, stale
   leases, overlapping owners, mid-command failure, and release failure.
   Run focused tests plus `git diff --check`, then broader regressions if
   changed scope warrants.
5. Record the measured offline before/after latency and tool/process call
   count. Target **5–15 s preparation and 5–15 s approved command** in a
   healthy live setting, as **engineering goals**, not achieved claims.
   Live timing verification requires a separately authorized harmless
   operation after the code review; this handoff authorizes **none**.
6. Produce one short validation note and a coherent local Git commit for
   each verified milestone; update `docs/status.md` with exact limitations.
   If the route cannot be improved safely within 90 minutes, stop
   optimizing, preserve findings/patch, and resume RR2 core.

## Immediate continuation after timebox

**P0: finish making RiftReader2 independent of the original RiftReader.**
The old checkout `C:\rift modding\RiftReader` and
`RiftReaderApiProbe` are **reference/historical replay only**; current RR2
runtime consumers should depend solely on RR2-owned code and `RR2R1`
when using the live Lua API source. No silent `RRAPIVAL2` fallback.
Prior code commit `f034fc4` hardened the old XYZ workflow's nonce
requirements, but its native movement profile is obsolete; do not use it.

### Verified baseline, not to repeat

- Lab 1 RR2 addon version 0.2.0 had one successful UI reload and one
  acknowledged `/rr2guide bind`, with old probe manifest disabled.
- Two read-only RR2R1 runs (8+8 snapshots) gave 64/64 advancing strict
  cross-run pairings, sequence 413→431; source SHA/evidence and limitations
  are in `docs/validation/self-contained-lab1-live-acceptance-2026-11-06.md`.
- Lab 1 controller restored healthy/disarmed/idle with input keys released.
- Both RR2-owned host receiver services were started and reused at that
  checkpoint; **continuous feed freshness unverified**.
- Lab 2 and physical RIFT: installed-addon disk parity only; no separately
  verified loaded-addon `RR2R1` acceptance. Native changed-state and
  480-second/full-game restart qualification remain pending.
- No game input, reload, binding, restarted VM/game, Git push, or gameplay
  movement is authorized by this handoff.

## Completion contract for Codex

Report (a) exact files changed, (b) measured bottlenecks and improvements,
(c) test commands, counts and exit status, (d) whether any live input was
performed (**expected: none**), (e) exact commit IDs and Git cleanliness,
(f) remaining latency risks, (g) next standalone dependency fix. Create or
refresh a dated handoff with an explicit copy-ready resume point and commit
the documentation. Do not merge experimental scratch receiver-pin fixes or
rewrite unrelated project history.

**Copy-ready mission:** "In the authoritative Windows
`C:\work\riftreader2` repo, read `AGENTS.md`, `docs/status.md`, and
`docs/handoff-2026-11-06-codex-interaction-speed.md`. Timebox 90 minutes
to simplify and offline-test the existing reviewed RIFT console interaction
route. No RIFT UI input or reload, and no VM/game restart. Measure actual
latency and tool calls, preserve controller/freshness/safety gates, commit
verified scoped milestones and a handoff, then resume standalone RR2
runtime-dependency elimination." 
