# Physical RIFT 1179 — source-verified target continuity across capture windows

**2026-11-21, ~10:05 EST · AMD-DESKTOP · physical RIFT process PID 37676**

## New working result

Two small CLI tools let RR2 collect and compare target-state candidates over several nonoverlapping capture windows, rather than requiring every selected-target change to appear in one short Lua memory scan.

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

**Validation:** The relevant combined Telemetry Python suite passed **199/199** tests, including the new 15 focused source-bundle and collector regressions. Prior baseline, A→B→A, wrong-owner and source-hash tamper checks remain in effect.

**Next acceptance:** Collect an A→B→A sequence during **actual independently observed target changes** under one exact game process, publisher epoch and source session. This run performed no target selections, movement, casting, RIFT restart, UI reload, process-memory write or external-repository changes. It does not qualify world-instance identity, causal input, or navigation.
