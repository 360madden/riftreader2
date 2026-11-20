# RR2 handoff — build-1179 native/Lua recovery and target qualification

**Checkpoint:** Friday, **2026-11-20 ~07:09 EST** (America/New_York)  
**Machine:** **AMD-DESKTOP** only — verified by machine-local PowerShell `[Environment]::MachineName` (exit 0).  
**Repository:** `C:\work\riftreader2`; branch `codex/modular-foundation`.  
**Latest confirmed Git HEAD *before this handoff*:** `f4c0d1b4433b6a98a6d2b0aa54b6b51f65d1cb47`, synced with `origin/codex/modular-foundation`. **Recheck HEAD and origin before resuming.**  
**Workbridge:** `0.16.5-dev`, root `C:\work`. Worker metadata at this checkpoint: **0 running**, 36 available, 12 queued assignments; these are **not evidence of actively executing AI subagents**.

## 1. Exact machine and game boundary

- Physical RIFT x64 only: `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe`. **Do not use LEGION or VMware.**
- Last verified at **07:08 EST**: PID **22532**, start time **2026-11-19 23:58:48 EST**; process-start UTC ticks **639307475284776509**, HWND **9965380** observed in prior identity receipt.
- Exact installed **build 1179** executable SHA-256: `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`. Prior 1177 SHA: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Character: **Atank**, observed level **45 Warrior**; numeric self key **239816685251645959**, Lua unit ID **`u035400012FA2D207`**.
- **The PID, process start, HWND, module allocations, and scan start addresses are historical observations, not permanent bindings.** Reacquire machine/PID/start/build at each new live attempt and use explicit physical PID; never silently switch processes.

## 2. Verified results — do not redo completed recovery

| Area | Confirmed result | Essential limitation |
| --- | --- | --- |
| Build-1179 native player and zone | Exact-SHA-gated player context, native XYZ, HP/vitals, 20 stat selectors / 40 ordinary+unbuffed values, selected-position/facing and guarded zone-context restored | Candidate values; do not promote to route/world-instance authority |
| Game restart survival | Saved composite readers worked on separate physical RIFT process epochs **77980**, **42656**, and **22532**, with hashes/identity and replay | Distinct-epoch repeatability is not continuous identity or a user-caused movement |
| Current native/Lua zone agreement | Independently authored **Telemetry** `RIFTTLM1` Lua API publisher and RR2 native zone reader agree on **`z0000000CB7B53FD7`**, Lua name **Silverwood**, player Atank | Non-atomic source pairing; Lua frame clock is not host UTC; world instance is unavailable |
| Automatic Telemetry scope discovery | `capture_physical_telemetry_zone.py --auto-scope --scope-count 6` surveyed 384 MiB, chose an observed current-generation region, captured fresh Lua frames and passed independent on-disk replay | Selection scope is volatile; a survey by itself never qualifies telemetry |
| Lua/native XYZ | Existing unbound RR2A1 Lua frames advanced and matched native XYZ within ~**0.0045** native units/axis | Does not prove induced movement or exact instantaneous freshness |
| Native no-target | After restart, native selected-position/facing returned appropriate no-target/unavailable fields; two later player-context samples returned **raw getter zero** | Zero is compatible with Lua none, **not independently proven no selection** |
| New target replay tooling | `replay_physical_telemetry_target.py` decodes source-hashed Lua selection IDs, transitions, and **synthetic-only** A→B→A; optional `--include-native-target` adds native target endpoints with independent SHA/timestamp/owner replay | Live target-change A→B→A **not yet accepted** |

**Critical milestone:** The old P1 blocker “no independent Lua zone source on 1179” has been resolved at the bounded same-process **candidate-correlation** level using Telemetry **without any new addon, UI reload or /rr2bind**. The older nonce-bound `RR2R1` path remains optional; its missing frames do not negate the successful separate Telemetry reference.

## 3. Most important source-hashed local evidence

The `artifacts/` files are **ignored and retained locally**, not committed. Treat them as optional machine-specific evidence; independently reread and SHA-check before using.

| Evidence | Local path | Summary SHA-256 |
| --- | --- | --- |
| Positive auto-scope native↔Lua zone | `artifacts/physical-telemetry-zone-autoscope-20261120-0640/summary.json` | `CEDC593AED367B4FB642B860E6095AECF5E4A28B38E266362E1E987A24FABF6A` |
| Independent cold replay of above | `artifacts/physical-telemetry-zone-autoscope-20261120-0640/independent-replay.json` | `48F54C729F3CDAE845CF2BCCF7BABB3DB1951ACC98B96D30BC37CBA73F88ED95` |
| Positive auto-scope survey | `artifacts/physical-telemetry-zone-autoscope-20261120-0640/scope-survey.json` | `B0B4AF838054820397601CC8D44750B44C11B344A89BA5CFEEC2245BA66090AE` |
| Lua selected-target baseline | `artifacts/physical-telemetry-zone-autoscope-20261120-0640/target-baseline.json` | `C976B750B3495F123BF3915E5755A6046DEAC9BC8AE0268213F55A6D71AE9B8C` |
| Optional native-target capture **unqualified** | `artifacts/physical-telemetry-target-20261120-0657/summary.json` | `693F26ED794E819E64AC40A7EDD78FABFDDA8DEE28D7B6647B67F4EA496F140E` |
| Second native-target capture **unqualified** | `artifacts/physical-telemetry-target-20261120-0659/summary.json` | `7931B014B039EE94AC9A3697B034D6672A11C2A312177C90C18BAB539ADB97C5` |
| Physical composite after another game restart | `artifacts/physical-state-postrestart-20261120-0015/summary.json` | `42A977A925141AA953D3216D32BEADEE018786A8FD9E077BA573E9256FBAC1B0` |
| Earlier positive independent Lua zone | `artifacts/physical-telemetry-zone-20261120-0549/summary.json` | `ACD0E3BF116372C543E8BB4DFBF5B9DC27BB5E265BAFE25832D2C3D61EEECD28` |

The positive auto-scope bundle verified **19 + 22 frame occurrences, 22 unique sequence numbers, three newly advancing second-pass sequences, source epoch 40, and the same Silverwood zone ID in both native endpoints and Lua frames**. Its host native→Lua→native window was **2.0156 seconds**. The target-baseline replay returned **22/22 Lua frames with `selectionState=none`** and zero transitions.

The two newer target-bundled attempts obtained **both real source-hashed native target endpoints** (each raw getter zero) but their Lua frame passes did **not** advance (8+8; 11+11); they returned `unqualified` / exit **2**. **Do not misreport these as successes.** No root cause for the nonadvancement was independently confirmed; the allocation/scope and source-generation can vary.

## 4. Implementation and test entrypoints

- `scripts/physical_rift.py` — physical host/PID/epoch/build verification and guarded native readers.
- `scripts/collect_physical_player_state.py` — opt-in `--include-zone` and `--include-stats` combined physical evidence.
- `scripts/capture_physical_telemetry_zone.py` — source-preserving Lua/native zone capture, opt-in bounded `--auto-scope`, and **`--include-native-target`** (latest work).
- `scripts/replay_physical_telemetry_zone.py` — **offline-only** original frame/native replay, cross-source hash/epoch/time/zone validation.
- `scripts/replay_physical_telemetry_target.py` — **offline-only** Lua target sequence/no-target/A→B→A classification and optional native target endpoint SHA/timing verification.
- `scripts/collect_physical_rr2a1_pair.py` and `scripts/replay_physical_rr2a1.py` — positive separate advancing Lua/native XYZ evidence.
- Tests: `tests/test_replay_physical_telemetry_target.py`, `tests/test_native_telemetry_target_bracket.py`, `tests/test_capture_physical_telemetry_zone.py`, `tests/test_capture_telemetry_auto_scope.py`, `tests/test_replay_physical_telemetry_zone.py`.

**Most recent verified tests:** **104/104** focused target/Telemetry suite and **252/252** wider Python regression suite, both exit 0 on November 20; `git diff --check` passed for owned modified files. These are focused suites, **not** a claim that the entire repository or .NET solutions passed a full build in that session.

For complete exact source receipts, see:
- [Latest target development and negative physical attempts](validation/native-lua-target-bridge-2026-11-20.md)
- [Auto-scope physical acceptance](validation/telemetry-zone-auto-scope-2026-11-20.md)
- [Independent current-build Lua zone acceptance](validation/physical-telemetry-zone-1179-independent-api-2026-11-20.md)
- [Build-1179 RR2A1 XYZ success](validation/physical-rr2a1-1179-live-correlation-2026-11-20.md)
- [Physical restart evidence](validation/physical-1179-postrestart-2026-11-19.md)
- Canonical chronology: `docs/status.md` (read the **newest entries at top**, which supersede older statements of what is blocked).

## 5. Next useful sequence (priority order)

1. **P1 — Find advancing Telemetry selected-target source again.** Reacquire current physical PID/start/hash. Run one bounded `--auto-scope` acquisition, and inspect `scope-survey.json`, source epochs, sequence windows and source-clock progression if it refuses. Distinguish empty memory, retained old generation, and nonadvancing publisher. **Do not weaken the fail-closed replay, fake freshness, or assume heap offsets persist.**
2. **P1 — User-observed A → B → A selection.** When there is a genuine advancing Lua publisher and a suitable already-running game, use manually selected target A, target B, then A. Collect the existing guarded `--include-native-target` receipts and run the independent target replay. Do not claim the synthetic A→B→A test is live proof. Player input/control requires its own narrow authorization, exclusive owner and STOP safeguards; read-only observation alone may be run against the selected physical process.
3. **P1 — Positive Mana/Energy resource types.** Kind-3 Mana and kind-4 Energy were tested with fake memory, but **positive live measurements remain absent**. Atank is kind-1 Warrior, and the correct Mana/Energy refusal cannot substitute for a suitable character. Keep RRE's spellcasting lane separate.
4. **P1 — Changed-zone observation and world-instance research.** Existing Silverwood agreement proves one observed state, not a **user-observed zone transition** or instance-unique identity. Only compare fresh same-player/process sources during a real observed change; don't promote a zone-ID string to collision/navigation clearance.
5. **P2 — Better source discovery latency** and selected-target native/visual confirmation after positive changed-state data, rather than speculative refactors.

### Quick continuation commands (PowerShell 7 on AMD-DESKTOP)

```powershell
Set-Location C:\work\riftreader2
[Environment]::MachineName
git status --short --branch
git log -4 --oneline
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP

# Existing positive source bundle — offline-only; never touches the game:
C:\Python314\python.exe -B scripts\replay_physical_telemetry_target.py --summary artifacts\physical-telemetry-zone-autoscope-20261120-0640\summary.json

# Optional new read-only capture. Replace PID with fresh verified PID,
# and choose a NEW output folder, never overwrite earlier source receipts:
C:\Python314\python.exe -B scripts\capture_physical_telemetry_zone.py --physical-pid CURRENT_VERIFIED_PID --auto-scope --scope-count 6 --start-address 0x13000000 --scan-bytes 67108864 --gap-ms 600 --include-native-target --output-dir artifacts\new-target-capture-UNIQUE
```

The `CURRENT_VERIFIED_PID` and `UNIQUE` tokens are placeholders, **not valid executable arguments as written**. Use `--help` for current CLI syntax. A capture that exits 2 or reports `unqualified` is a **negative evidence receipt**, not success. Analyze only source-hashed saved files; do not silently rebind to a different RIFT PID.

## 6. Concurrency, worktree preservation, Git

The shared checkout has unrelated work in progress. **Do not stage, reset, clean, delete, commit or overwrite** these without lane-owner coordination:

`docs/reference/third-party-workflow-tools-2026-11-12.md`, `scripts/fresh_native_actor_pose.py`, `scripts/hunt_mission.py`, `scripts/waypoint_navigation_candidate.py`, `tests/test_fresh_native_actor_pose.py`, `tests/test_hunt_mission.py`; untracked `.playwright-cli/`, `output/`, `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `scripts/target_acquire.py`, `scripts/target_cycle.py`, `scripts/target_selection.py` and related `tests/test_rank_native_anchor_candidates.py`, `tests/test_target_acquire.py`, `tests/test_target_cycle.py`, `tests/test_target_selection.py`.

Workbridge's available/queued worker **metadata does not launch AI models**; check for real active execution before claiming worker progress. If a Codex model launcher is unavailable, continue with bounded machine-local tools and tests rather than invent subagent results. The preferred development loop is small, practical, independently verified outcomes with selected-file commits and user-authorized pushes.

**Session boundary:** All work above used read-only physical game observation. **No RR2 movement, casting, target-selection input, UI reload, process write or game restart was sent.** The next chat should start from this handoff, verify host and Git state, and choose the first *new* measurable target or resource result rather than repeating completed zone-ID discovery.
