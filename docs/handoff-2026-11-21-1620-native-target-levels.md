# RR2 handoff — November 21, 2026, 16:20 EST

**November 23 follow-up on LEGION:** The retained build-1179 capture and
selected-target profile replayed with matching native level candidates of **14**
for the same unit, entity, player and process epoch. This covers the native
comparison in P0. Independent RIFT UI or Lua evidence remains pending.
[Replaying the native comparison](reference/physical-native-nearby-units-2026-11-21.md#numeric-level-candidates)

A later read-only LEGION observation on PID 31684 found no selected unit at either
endpoint and returned 10 named nearby units with native numeric level candidates.
The standalone nearby replay reproduced those counts from four copied JSON files
without a live reader. [Nearby replay](../artifacts/native-level-passive-legion-p31684-20261123/nearby-replay.json)

LEGION passed the NPC survey's installed-addon and published-reader checks,
including the keyed native level command. Preparation now verifies either the
standalone addon or the Casting fallback. [Addon checks](../artifacts/npc-survey-addon-layouts-legion-20261123.json)
The generated capture command keeps
the reader path, process start ticks, executable hash and deadline from
preparation. The live Lua comparison still needs an
advancing nonce-bound survey. [NPC survey preparation](reference/physical-nearby-npc-correlation-2026-11-21.md#prepare-and-replay-a-saved-bind-plan)

The current Windows workflow verifies the local host before using physical
tools. A fresh checkout can use a published native reader, a calibration
verified for that host, and local Python environments. The fresh LEGION
checkout at `5888d48` passed the full gate with the Python configured for
Waypoints, including the real Lua 5.1 producer checks. The newly published
reader passed the Waypoints, WGC, ReaderBridge, NPC survey, and Telemetry
dependency checks. The Telemetry check found all three installed addon files.
[LEGION dependency results](../artifacts/physical-dependencies-legion-5888d48.json)
A passive LEGION run on build 1179, PID 31684, verified an advancing
Telemetry publisher in two windows. Independent replay from a copied folder
reproduced 106 distinct frames and zero observed A–B–A cycles. Live
changed-target and nonce-bound NPC confirmation remain pending.
[Passive Telemetry replay](../artifacts/telemetry-passive-legion-p31684-20261123/independent-replay.json)

Workbridge capture reports missing `dist/desktop-ui.mjs`,
`dist/desktop-capture.mjs`, and `dist/desktop-turn-admission.mjs` on LEGION.
The staged Workbridge owner returned a version-only WinApp probe to RR2.
The probe uses the service's executable selection. [LEGION WinApp probe](../artifacts/workbridge-winapp-service-legion-20261123.json)
WGC passed its dependency checks with both a private x64 Desktop Runtime and
a copied self-contained publish. The copied build passed all 31 self-checks
with the runtime overrides cleared. [Self-contained WGC setup](../tools/physical-wgc-probe/README.md#publish-with-the-runtime-included)
The AMD-DESKTOP process observations below are dated evidence.
[Portable checkout setup](workflows/development.md#reuse-local-tools-from-a-fresh-checkout)
· [LEGION validation log](../artifacts/validation-legion-5888d48.log)

**Machine verified:** **AMD-DESKTOP**, from machine-local Windows PowerShell `[Environment]::MachineName` (exit 0 at 16:20:19 EST); Workbridge **0.16.5-dev** rooted at `C:\work`.\
**Repository:** `C:\work\riftreader2`; branch **`codex/modular-foundation`**.\
**Git HEAD before this handoff:** `359109f43058fc310e76a2cd37a037141b90c7b4` (synchronized with `origin/codex/modular-foundation` at preflight). **After creating/pushing the handoff, reread `git log` and `git status`; never assume this pre-handoff HEAD remains current.**\
The original handoff covered local physical RIFT on **AMD-DESKTOP**. See
`AGENTS.md` for current requirements and `docs/status.md` for chronological
findings.

## 1. Current physical process — important restart discovery

A **fresh read-only preflight at 16:20 EST** returned:

| Field | Observation |
| --- | --- |
| Machine | AMD-DESKTOP |
| Game | Physical RIFT x64 |
| Executable | `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe` |
| **New live PID** | **48468** |
| **New process-start UTC ticks** | **639308923693997448** |
| **New HWND** | **7145554** |
| On-disk executable SHA-256 | `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01` (build **1179**) |

The previous physical session was **PID 37676**, start ticks **639308565554559088**, HWND **3541956**. At ~16:11 it returned `not-running`, but a newly started process was independently observed at 16:20. **All old process identity, selected unit keys, memory addresses, target selection, scanner scopes, survey nonces, and previous nearby lists are expired for the new epoch.** The new PID is **only a timestamped observation**, not a permanent default. Re-run host + exact PID/start/SHA verification before *every* live acquisition. No new keyed-level physical test was run on PID 48468 during handoff creation.

## 2. What is completed and materially useful

| Capability | Actual evidence | Qualification boundary |
| --- | --- | --- |
| **Native selected-target reader restored on 1179** | Existing C# reader now uses 1179 unit manager, health/position/level selectors and typed owner checks. `physical_rift.py --read-native selected-target` succeeded on real selected `u800000009A0026CE`: HP **522/522**, Energy **100/100**, numeric level **10**, position **(6046.1846, 832.3002, 3125.9717)**. | Static native candidates; UI/Lua meaning, changed-state freshness and hostility unqualified. |
| **Independent selected target ID/position/name** | Two-sample selected-position burst produced the **same** unit ID/XYZ, keyed native name reader `Argent Glade Guard` with same entity. | Sequential, not atomic; two native readers do not establish full independent gameplay semantics. |
| **One-command selected-target profile + offline replay** | `physical_selected_target_profile.py` acquired four original native sources, bracketed matching selected key/entity and retrieved same guard/level/HP/XYZ; `replay_physical_selected_target_profile.py` independently re-verified original source hashes and chronology with exit 0. | `selectedIdentityAtEndpointsMatched=true`, **`intermediateSelectionHistory=unavailable`**; a brief A→B→A between endpoints is not ruled out. |
| **New native keyed multi-unit levels** | `sample-current-unit-levels` (C#/.NET 10) and `physical_rift.py --read-native unit-levels --unit-keys ...`, up to **12 exact decimal unit keys**, correct typed component/owner/alternate-level routing for 1177/1179, positive levels 1–1000 or explicit unavailable. | **Offline-tested, NOT physically qualified**. RIFT was closed at first attempt to test; new PID 48468 appeared afterwards. |
| **Native nearby names and XYZ** | `physical_nearby_units.py` on old process found **17 candidates within 35 units**, **15 cache names** in one physical run. Preserved and SHA-replayed original native files. | Old unit list is stale following restart; presence/name does not establish hostility, type, correct floor or attackability. |
| **Lua/native target continuity** | Bounded multiple capture windows, source-verified frame union, publisher-epoch isolation, per-window sequence gap reporting, optional `--stop-on-aba`, bounded `--recover-stale-scope`. Real advancing capture/replay passed; a two-window baseline had **91 unique source frames**, no selected-target change. | Actual A→B→A **not yet observed**. Synthetic test qualification is not live proof; missing Lua sequences remain unobserved. |
| **NPC Lua source and relation/level join** | `npc_survey_live.py --auto-map`, original wire retention, `replay_npc_survey.py` and `join_physical_nearby_npc_survey.py` implemented with offline source-tamper and owner/ID/XYZ tests; `prepare_physical_npc_survey.py` generates a fresh in-game `/rr2survey bind` command. | **No positive live nonce-bound NPC survey**. Prior two 512-MiB physical surveys had no valid nonce-bound frames; old prepared nonces **expired**. The original Python 3.14 environment lacked `lupa`. The November 23 validation used a prepared Lua 5.1 environment. |
| **1179 actor matrix copy relationship** | Existing physical orientation/actor reader produced nine of nine float32 raw-bit matches on build 1179; bracketed no-input observations. | A copied matrix is not qualified actor heading, turn response or navigation authority. |
| **Navigation, survival, hunt and target selection** | Existing helpers and tests are present, including partly uncommitted work. | Whole-route obstacle-aware navigation, selected-target behavior during change, and live autonomous combat/recovery remain unfinished; **do not overwrite dirty lane files**. |

**Current-build source files:**\
`scripts/physical_rift.py`, `scripts/physical_selected_target_profile.py`, `scripts/replay_physical_selected_target_profile.py`, `scripts/physical_nearby_units.py`, `scripts/native_unit_level_projection.py`, `scripts/capture_physical_telemetry_target_series.py`, `scripts/replay_physical_telemetry_target_series.py`, `scripts/npc_survey_live.py`, `scripts/prepare_physical_npc_survey.py`; native C# `src/RiftReader2.Live/CurrentBuildSelectedTargetCandidateReader.cs` and `CurrentBuildUnitLevelsSampleCommand.cs`.

## 3. Tests and builds actually completed November 21

- **Full .NET 10 solution** at the last keyed-level checkpoint: **1,953 / 1,953 passed** — 445 foundation and 1,508 Live; 0 failures. Command: `dotnet test RiftReader2.slnx --no-restore --configuration Release --verbosity quiet`.
- Keyed level: **8/8 C# tests**, **7/7 Python tests**. A separate **Debug native executable build** succeeded with **0 warnings, 0 errors**. New C# command was **not** run on a live RIFT process.
- Related native Python regression suite: **70 run, 69 passed and 1 symlink-permission skip**. Do not report as 70/70 passed.
- Selected-target profile tests earlier: **53 run, 52 passed, 1 Windows symlink-permission skip**; independently replayed actual old-PID source bundle exit 0.
- Telemetry baseline/observer: **242/242** targeted Python telemetry tests at the relevant milestone; other focused counts are dated and not proof of a complete all-Python suite.
- `git diff --check` passed for each owned completed milestone. All work and tests were conducted on AMD-DESKTOP.

## 4. Commit chronology — all pushed before handoff

In reverse chronological order, on `codex/modular-foundation`:

| Commit | Delivered |
| --- | --- |
| `359109f` | Exact-build native keyed level reader and CLI, **offline only** |
| `61c0f3a` | Four-source selected-target profile and independent cold replay; physical acceptance |
| `20ee529` | Restore selected-target level/vitals/XYZ and exact-SHA native command for build 1179 |
| `201a729` | NPC map-aware nonce survey discovery and fresh bind-plan generator |
| `797219f` | Original NPC Lua wire retention/replay and offline native↔API level/relation join |
| `e423a4c` | Read-only keyed nearby native positions/names CLI and physical acceptance |
| `79b5ad2` | Bounded source-verified target A→B→A observer, optional early stop |
| `cad7d67` | Preserve excluded publisher epochs, exact source replay and stale scope recovery |
| `114d5c8` | Reproduce 1179 actor/position matrix raw-bit copy relationship |
| `d01f26e` | Source-verified full-frame union across captures (rather than last-target-only) |
| `4d58480` | Honest per-window Lua sequence-gap accounting |
| `21e8779` | Multi-window physical target continuity collector/replayer |

The earlier pre-handoff HEAD was `359109f43058fc310e76a2cd37a037141b90c7b4`; **the handoff commit itself advances HEAD**. Recheck actual origin and worktree before resuming.

## 5. Important local original evidence (ignored by Git)

Do **not** infer GitHub has these original process snapshots. They are in local `artifacts/`, ignored/untracked for research and must be reopened with source SHA checks.

| Original evidence | Local repo-relative path | SHA-256 |
| --- | --- | --- |
| **Selected-target profile** (latest positive and replayed, old PID 37676) | `artifacts/physical-target-profile-20261121-1607-p37676/profile.json` | `2345BB4B3608F7A2839DC371896BE916990B18DA911E8A87DF55A1473F16258C` |
| Primary selected-target reader (old process) | `artifacts/physical-selected-target-1179-20261121-1552.json` | `3C1BE94F05B24CAAB63826D944F2F13953516C715827CE1DA4C1833C26F127CF` |
| Cross-window target observer, **no change** | `artifacts/physical-target-aba-observer-20261121-1216-p37676/result.json` | `A7264F8281946114B69142A8510F64A7AA2FF55CBD7CD34E36B88BE193FEF8FD` |
| NPC bind preparation, **never activated; stale** | `artifacts/npc-bind-prep-20261121-1335-p37676/plan.json` | See original local file; do not reuse nonce |
| NPC negative auto-map survey | `artifacts/npc-auto-map-unbound-20261121-1331-p37676/` | Receipts in individual `attempt-*.locator.json` |
| Native keyed-unit-level source from new PID | **Not captured** | Physical acceptance pending |

Detailed exact source paths, hashes and limits:
- [Selected-target recovery](validation/physical-selected-target-1179-recovery-2026-11-21.md)
- [Four-source selected target profile](validation/physical-selected-target-profile-2026-11-21.md)
- [Keyed native levels](validation/native-keyed-unit-levels-2026-11-21.md)
- [Telemetry target continuity](validation/physical-target-series-2026-11-21.md)
- [Mixed publisher epoch recovery](validation/physical-telemetry-publisher-generation-recovery-2026-11-21.md)
- [NPC cross-source correlation](reference/physical-nearby-npc-correlation-2026-11-21.md)
- [Nearby native units](reference/physical-native-nearby-units-2026-11-21.md)

## 6. Highest-value immediate continuation

1. **P0 — First live acceptance of keyed native unit levels on a *fresh* game epoch.** At the 16:20 preflight, physical RIFT had **new PID 48468**, but verify again. Obtain a **fresh** nearby-unit list and exact unit keys; select ≤12 names/keys and run `--read-native unit-levels`, preserving the native source file. Do not copy old PID 37676 or old unit IDs into a new run without discovery. Confirm at least one current unit's numeric-level candidate against the guarded selected-target profile, using matching exact unit ID and updated evidence. Be prepared for benign `unavailable` statuses if units despawn, and don't imply all loaded units or exact threat semantics.
2. **P1 — Positive changed-state target qualification.** In a real advancing Lua telemetry session, perform A→B→A target changes **only under a separately authorized controller/operator action**. Use the existing bounded `capture_physical_telemetry_target_series.py --recover-stale-scope --stop-on-aba`, then independent replay; accept only original source-hashed observations. A same-target beginning/end profile **does not** rule out an intermediate switch.
3. **P1 — Live NPC Lua relation/level.** Generate a **new** `prepare_physical_npc_survey.py` plan for this new process, verify installed Casting module and active addon, enter the generated `/rr2survey bind` in-game (not issued by any read-only CLI), then capture advancing nonce-bound frames with `npc_survey_live.py --auto-map` and replay/join against native IDs within its bounded time window. Previous unbound negative scans are not proof of addon absence.
4. **P1 — Threat assessment for hunt/navigation.** Only after enough genuine named-unit/level/relation and path evidence exists, integrate candidate fields into existing `target_selection` / `hunt_mission` / `waypoint_navigation_candidate` with their lane owner. Avoid assuming every named unit is hostile or climbable/reachable. Do not overwrite pre-existing uncommitted work.
5. **P2 — Actor heading, height/collision and whole-route acceptance** following real selected target/world-state checks. Current actor matrix copy is a useful clue, not verified navigation control.

### Quick safe commands (PowerShell on **AMD-DESKTOP** only)

The paths below record the November 21 workstation. For current host-neutral
commands and published-reader setup, use the
[physical Windows workflow](workflows/development.md#current-live-workflow-on-physical-windows).

```powershell
Set-Location C:\work\riftreader2
[Environment]::MachineName
git status --short --branch
git log -4 --oneline

# Reacquire game PID, start, on-disk SHA, window before EACH live test:
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP

# Replace placeholders with NEW verified PID and a unique unused output folder:
C:\Python314\python.exe -B scripts\physical_nearby_units.py --expected-host AMD-DESKTOP --physical-pid NEW_VERIFIED_PID --radius 35 --max-names 12 --output-dir artifacts\NEW_NEARBY
# Read unitKey strings from NEW_NEARBY\nearby-report.json.
# Unit keys MUST be exact fresh decimal key strings, at most 12:
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid NEW_VERIFIED_PID --read-native unit-levels --unit-keys FRESH_DECIMAL_KEYS_COMMA_SEPARATED --output artifacts\NEW_UNIT_LEVELS.json

# If a target is selected and the process remains the same:
C:\Python314\python.exe -B scripts\physical_selected_target_profile.py --expected-host AMD-DESKTOP --physical-pid NEW_VERIFIED_PID --output-dir artifacts\NEW_TARGET_PROFILE
C:\Python314\python.exe -B scripts\replay_physical_selected_target_profile.py --profile artifacts\NEW_TARGET_PROFILE\profile.json

# Focused offline regressions (no game required):
C:\Python314\python.exe -m unittest -q tests.test_native_unit_level_projection tests.test_physical_selected_target_profile tests.test_replay_physical_selected_target_profile
dotnet test RiftReader2.slnx --no-restore --configuration Release --verbosity quiet
```

`NEW_VERIFIED_PID`, `NEW_NEARBY`, `FRESH_DECIMAL_KEYS_COMMA_SEPARATED` and `NEW_TARGET_PROFILE` are **placeholders**, not working literal arguments. Use new output paths, never overwrite source evidence. No live command should be attempted if process/window/start/SHA changes or the operator has not authorized gameplay actions.

## 7. Protect concurrent developer work

The checkout has the following **pre-existing, unrelated** dirty/untracked files. **Do not use `git add -A`, `git reset`, `git clean`, blanket checkout, mass formatting, deletion or silent commits** on them:

**Modified tracked:**
- `docs/reference/third-party-workflow-tools-2026-11-12.md`
- `scripts/fresh_native_actor_pose.py`
- `scripts/hunt_mission.py`
- `scripts/waypoint_navigation_candidate.py`
- `tests/test_fresh_native_actor_pose.py`
- `tests/test_hunt_mission.py`

**Untracked:** `.playwright-cli/`, `output/`, `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `scripts/target_acquire.py`, `scripts/target_cycle.py`, `scripts/target_selection.py`, `tests/test_rank_native_anchor_candidates.py`, `tests/test_target_acquire.py`, `tests/test_target_cycle.py`, `tests/test_target_selection.py`.

Those are separate in-progress lanes, not artifacts to discard. Commit only explicitly owned files with exact file hashes, and push the authorized branch. Workbridge worker **metadata is not proof of running ChatGPT AI subagents**; verify real worker execution before reporting it. No live action, movement, casting, target selection, game restart, UI reload, memory write, or desktop focus change was initiated in this handoff workflow.

---

**Start next RR2 session from this handoff, `docs/status.md`, `AGENTS.md`, and an actual new AMD-DESKTOP process preflight. The most valuable test waiting right now is new-process physical acceptance of the keyed multi-unit level reader.**
