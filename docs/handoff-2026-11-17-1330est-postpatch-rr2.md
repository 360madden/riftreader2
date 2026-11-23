# RiftReader2 handoff — RIFT 1179 post-update continuation

**Created:** 2026-11-17 ~13:30 EST (America/New_York)\
**Scope:** AMD-DESKTOP physical RIFT only; no LEGION or VMware.\
**Verified host:** `C:\Windows\System32\hostname.exe` returned `AMD-DESKTOP` (exit 0) at 13:26 EST. Workbridge 0.16.5-dev.\
**Repo:** `C:\work\riftreader2`, branch `codex/modular-foundation`, upstream `origin/codex/modular-foundation`. Latest pre-handoff HEAD `07500a01f0cd331ca6696eb67383cd84456edc03` (10:49 EST); no upstream divergence observed.\
**Purpose:** Resume useful RR2 functionality after the November 17 game patch. This document supplements, not replaces, `docs/handoff-2026-11-17-rift-1179-postpatch-recovery.md` and `docs/validation/physical-build1179-passive-reader-2026-11-17.md`.

## Confirmed recovery

- RIFT x64 build `STABLE-1-1179-a-1256672`; current executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`. Historical SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` is retained for old-build replay.
- Last qualified game epoch: `rift_x64` PID `77980`, start ticks `639305214834918403`, HWND `0x24B181E`, Atank self key `239816685251645959`. A matching RIFT window/PID was still listed at ~13:26 EST, but **reverify the executable hash, PID/start epoch, player owner and window on every new live operation**. Prior module base was an ASLR address, never a durable pointer.
- Updated native player manager/system and position/facing reader paths worked on that exact build. Validated global RVAs: entity manager `0x3373C68`, player system `0x3373BA0`; position selector `0x2F698A0`, actor selector `0x2F69490`; position vptr `0x26C35C0`. Health selector `0x2F68850` remains discovery-only, **not a qualified health reader**.
- C# current-build position and independent facing read; actor matrix and position bracket sampled successfully (orthonormal error approximately `2.24e-7`). Python `scripts/physical_rift.py --read-native actor-pose` also succeeded. These are exact-build/owner-bound candidate reads; do not overpromote optical-camera or full semantic qualification.
- Supervised physical movement receipts on a cleared inland patch: W/S/Q/E 250 ms planar displacement `1.769/0.784/1.560/1.563` units; A/D 250 ms orientation changes approximately `+44.49/-43.91` degrees. Input keys released. The first W probe at the seaside cliff did not move; no route or combat was initiated. Actual calibrated basis resides at `config/physical-movement-basis.amd-desktop.json` with conservative eligibility flags.
- `scripts/launch_physical_waypoints.py --physical-pid 77980 --check` returned `ready`; Waypoints 1.4.0 GUI was visually accepted with fresh pose. It was successfully launched persistently earlier; the transient scheduled task was then removed. **At 13:26 EST the Waypoints window was not present in the current desktop-window listing** (although RIFT was). Do not report the GUI as currently open; rediscover/relaunch under fresh identity only if asked or required for an authorized operation. Historic saved routes are intentionally refused on the patched build.
- The shared `C:\work\Update Helper` recorded a before/after RIFT manifest: 274 files before, 272 after, 7 modified and 2 removed. Main diff: `C:\work\Update Helper\data\RIFT-Live-diff-20261117-0916EST-rr2.md`; RR2 comparison: `artifacts\patch-analyzer-20261117-0918-postpatch\REPORT.md`. Update Helper owns patch descriptions; RR2 owns code adaptations.

## Verification and commits

| Evidence | Outcome |
| --- | --- |
| Full .NET 10 Release test sweep after actor-pose code change | **1,864/1,864 passed** (444 core, 1,420 live) |
| Earlier Python physical/Waypoints targeted tests | **139/139 passed** |
| Subsequent postpatch admission-focused tests | **79/79 passed**, `0ed7f5a` |
| Subsequent passive native-reader focused unittests | **65/65 passed**, `05cb48b` |
| Native reader cross-correlation | 5 raw reports same build/process/self key and matched paired XYZ brackets; **5/5 replay pairs passed** |

Main shipped commits, in chronological order:

1. `e68c281` — Restore native position, facing, movement basis and Waypoints admission.
2. `1d9dbd7` — Restore exact-build actor-pose sampling and physical wrapper.
3. `0ed7f5a` — Offline native-read admission tests: ten unqualified kinds reject current-build reads; position/facing/actor-pose accept exact SHA.
4. `98d77b0` — Record conservative RRE discovery intake; RRE `InGame` B/+0x6A8 remains conditional static evidence.
5. `05cb48b` — Record five passive position/facing/actor cross-reader observations with raw file SHA pins.
6. `07500a0` — Publish those passive build-1179 results to the RRE intake documentation.

**Important correlation limit:** Two pairs of native XYZ/actor observations and one facing sample agree within their individual brackets; the early XYZ `(683.59796,850.637,359.37646)` and later `(7206.161,843.1973,3117.333)` are separated by an **unobserved interval**. Their 7,081.677-unit planar endpoint gap is **not evidence of travel distance, route, world continuity or cause**. Other sessions/user actions may have intervened. Passive freshness and player semantics are not thereby fully qualified.

## Current limitations / next owner

1. **P0 native telemetry:** Requalify target owner/target projection, optical camera, health/mana/energy and other legacy native readers on exact build 1179; currently unqualified reader kinds must fail closed. Prefer one useful read-only retrieval path with independent changed-state validation and evidence before broad scanning.
2. **P1 Waypoints operational validation:** Recheck current game PID/start/hash and Waypoints process. Use `C:\Python314\python.exe scripts\launch_physical_waypoints.py --physical-pid <fresh-PID> --check` from RR2 root to preflight. Do not reuse old route metadata by changing hashes. A new nearby, collision-qualified route and STOP/release outcome require their own authorized live trial.
3. **P2 survival/progression integration:** Physical hunt -> retreat -> recovery -> rejoin and changed-health/RR2R1 nonce readiness remain unproven. Offline STOP-race regressions have coverage, but that does **not** constitute physical acceptance.

**Safety/coordination:** Do not silently change host, auto-rebind a second multibox process, unlock desktop input, clear STOP, or send game input from a documentation handoff. One coordinator owns any separately authorized live input. Preserve source/build/process epoch and independent receipt freshness. Historical RRE research is read-only input, not a new current-build RR2 pointer without independent verification.

## Working tree at handoff

All cited recovery and passive-documentation commits were on the tracked branch. A separate concurrent work lane has pre-existing modified files (`docs/reference/third-party-workflow-tools-2026-11-12.md`, `scripts/fresh_native_actor_pose.py`, `scripts/hunt_mission.py`, `scripts/waypoint_navigation_candidate.py`, `tests/test_fresh_native_actor_pose.py`, `tests/test_hunt_mission.py`) and untracked `.playwright-cli/`, `output/`, target-selection/anchor scripts and matching tests. **Do not include, clean, reset or commit those files incidentally.** This handoff is documentation-only; no game input or source-code change was made in its creation.
