# Physical RIFT 1179 — source-verified target continuity across capture windows

**2026-11-21, ~10:05 EST · AMD-DESKTOP · physical RIFT process PID 37676**

## New working result

Two small CLI tools let RR2 collect and compare target-state candidates over several separate acquisition windows whose retained source frames can overlap, rather than requiring every selected-target change to appear in one short Lua memory scan.

- `scripts/capture_physical_telemetry_target_series.py` starts with the successful bounded map-aware Telemetry locator, then reuses its **same-process** scope for subsequent windows. Each capture still performs the native-zone, native-selected-target, independent Lua source-clock, hash and replay qualification. The command performs **no game input**, focus changes or reloads; it exits unqualified on a failed constituent capture and retains that capture's evidence.
- `scripts/replay_physical_telemetry_target_series.py` independently replays **each saved original summary** and its underlying native/Lua source bytes, refusing process, player, zone, publisher session/epoch changes, source reuse, or non-advancing sequence endpoints. It compares only the **last actually observed target of each window**, reports unobserved source-sequence gaps, and labels any A→B→A across windows as **candidate-only**, never input-causation or complete movement evidence.

## Live acceptance

The exact current executable SHA-256 was `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`; game process start ticks `639308565554559088`. A guarded three-window read-only run returned **exit 0** and wrote `artifacts/physical-target-series-20261121-1005-p37676/result.json` (SHA-256 `9D478EB6844D6C28D9EC705DE0E0C5D3E02C945B82CEBFDAD357839DC7E56A78`).

| Capture | Lua epoch | Last source sequence | Saved Lua frames | Last selected target |
|---|---:|---:|---:|---|
| 1 | 55 | 39074 | 41 unique | None candidate |
| 2 | 55 | 39128 | 56 unique | None candidate |
| 3 | 55 | 39182 | 60 unique | None candidate |

Each source window independently passed its native/Lua zone and target replay. All were bound to PID 37676, same player, zone `z0000000CB7B53FD7`, and source session `cb9c1a5b6910fb2f457a9c72a392d90d`. The result is `no-target-continuity-candidate` and explicitly contains **zero A→B→A candidates**. The native raw-target-zero endpoints are compatible with the Lua-none observations, not independent proof of no selection.

**Coverage qualification added after a cold replay:** sequence ranges versus unique saved frame counts showed that capture 1 contained all 41 sequence numbers in its observed range, capture 2 missed **at least 38** sequence numbers within its range, and capture 3 missed **at least 6**. Source: ignored `artifacts/physical-target-series-20261121-1005-p37676/continuity-rechecked.json` (SHA-256 `5AC7AC92698CAA657E47F1948F76FA9FEC4B75FCEE7EC05EED04D4CAF8C57336`). Overlap means those per-capture minima cannot be summed into a global missing-sequence total. The combined report now distinguishes per-capture minimum missing sequences from gaps between captures, and never promotes an inferred complete A→B→A history.

## Usage

In PowerShell 7 under `C:\work\riftreader2`, after obtaining a current verified PID with the physical-RIFT preflight:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\capture_physical_telemetry_target_series.py --physical-pid CURRENT_PID --count 3 --interval-ms 500 --scope-count 4 --output-dir artifacts\NEW_TARGET_SERIES
```

To compare two or more individually successful existing captures later:

```powershell
C:\Python314\python.exe -B scripts\replay_physical_telemetry_target_series.py --summary artifacts\FIRST_CAPTURE\summary.json --summary artifacts\SECOND_CAPTURE\summary.json
```

**Validation:** The relevant combined Telemetry Python suite passed **201/201** tests, including the new 15 focused source-bundle and collector regressions. Prior baseline, A→B→A, wrong-owner and source-hash tamper checks remain in effect.

**Next acceptance:** Collect an A→B→A sequence during **actual independently observed target changes** under one exact game process, publisher epoch and source session. This run performed no target selections, movement, casting, RIFT restart, UI reload, process-memory write or external-repository changes. It does not qualify world-instance identity, causal input, or navigation.

## November 21, ~11:04 EST: frame-level cross-window replay

The initial series comparator only compared each capture's final selected target. That could miss a short A → B → A sequence occurring *inside* a capture even when each capture ended with no target selected. The independent target replay now optionally exports **every original, SHA-reverified Lua source frame**, with its source sequence, epoch, source clock, and selected-target candidate. Normal standalone target replay output is unchanged unless the optional frame view is requested.

The series replayer now merges those frame projections by exact source sequence, requires identical original SHA/clock/target when a sequence is present in more than one window, rejects backwards source clocks, and reconstructs source-observed target runs and A → B → A candidates from the **union of actual observations**. Existing last-target-only fields remain available separately; the CLI's A → B → A count uses the reconstructed observed-source evidence rather than potentially missing a short-lived selection. Synthetic regressions explicitly verify a middle-of-capture A → B → A that ends in a no-target state, transient selections that cannot be labeled all-none, wrong source bytes, and conflicting overlapping frames. These are **candidate observations**, not game-input attribution or continuous world-state proof.

**New actual read-only three-window physical acceptance:** The same verified AMD-DESKTOP RIFT PID **37676**, process-start ticks `639308565554559088`, exact executable SHA `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`, Lua publisher epoch **56**, and Silverwood zone-ID candidate `z0000000CB7B53FD7` completed **3/3** successful source-replayed captures. Last source sequences were **28744 → 28795 → 28850**. The merged original evidence includes **121 distinct source frames** across sequence **28697–28850**, with **33 missing sequence numbers**; all **121 observed frames** reported no selected target. Therefore result remains **`no-target-continuity-candidate`**, without A → B → A, action causation, or complete sequence-coverage claims.

**Saved original candidate report:** `artifacts/physical-target-merged-20261121-1104-p37676/result.json`, SHA-256 `2AE1D1F45FC3F8806C8FCB598EF5AE2A60EC7ACABFDED4BB6B404F3C2B9B0EA5`. **207/207 initial Telemetry regressions**, then **209/209 final focused Telemetry regressions** after CLI-count tests, passed. Relevant `git diff --check` passed. No game input, reload, restart, focus change, memory writes, or sibling repository edits occurred.

**Outstanding:** A genuine observed selected-target change is still necessary for live A → B → A qualification; the new tool should capture it with better coverage without inventing missing states.
