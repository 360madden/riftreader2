# Physical Telemetry publisher-generation recovery — RIFT build 1179

**2026-11-21, approximately 11:31–11:37 EST · AMD-DESKTOP · physical RIFT x64 only**

## Root cause, not a stale-address workaround

On verified physical RIFT PID **37676**, process-start UTC ticks **639308565554559088** and executable SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**, the existing read-only, map-aware Telemetry acquisition found a candidate current Lua publisher in a low address range. Its **first capture still failed closed** (exit 2, `capture-01-unqualified`) despite unchanged native process and zone endpoints. The original, ignored `artifacts/physical-target-series-recovery-20261121-1131-p37676/capture-01/summary.json` has SHA-256 **F573FF055E799A14D53E94709B28DDD82F4E2D500DCCCFCA8987FABE09055188**.

Inspection of that original summary showed that **both Lua passes contained publisher epochs 57 and 58**, sharing the same process, player, zone and publisher session. The survey preferred the newer/advancing **epoch 58**, but the capture previously accepted *all* otherwise-valid frame rows in the selected address window. The independent source-coherence gate correctly refused the mixed-generation bundle rather than publishing a false native/Lua match. The window location was not by itself the problem.

## Narrow implementation

The existing `scripts/capture_physical_telemetry_zone.py` now takes the selected publisher **session ID and epoch** from its bounded survey and passes them into both newly acquired Lua scans. Valid frames from **other** publisher generations are not silently discarded: each gets its own retained original `frame-NN.wire`, a SHA-256 receipt, and `nonselected-publisher-generation` exclusion status. The accepted frames alone supply candidate source progression and zone correlation.

The independent offline `scripts/replay_physical_telemetry_zone.py` now checks the selected publisher identity against the saved survey, reopens **both accepted and excluded** source files, verifies each SHA and source row, refuses any attempt to mislabel a selected-generation frame as excluded, requires matching exclusion counts and retains the existing native ownership, time-order and advancing-source checks. Original bundles without this optional generation filter remain replayable.

The separate `scripts/capture_physical_telemetry_target_series.py` also supports opt-in `--recover-stale-scope`. It permits **one** new map-discovery attempt for a later window's specifically recognized stale cached scope, preserving the original failed window and recording the new attempt. It does not retry arbitrary unqualified captures or changed process identity, does not loosen any replay gate and never sends game input.

## Physical results and qualification limits

**New successful one-window bracket:** After the code change, `artifacts/physical-telemetry-mixed-generation-20261121-1136-p37676/summary.json` (SHA-256 **9160C69F64D130517987B93591DFF69015722BE3F9F25FB91FC5C709197EA7DC**) returned **exit 0** with **32 + 29** accepted Lua frame occurrences, **42 unique source sequences**, **10 newly advancing pass-2 frames**, selected publisher **epoch 58**, and matching native/Lua Silverwood zone candidates. Independent native/Lua target replay returned exit 0 with all 42 observed frames reporting `selectionState=none` and compatible native raw-target-zero endpoints. **Neither pass contained an excluded older-epoch frame** in this later run. Thus *successful mixed-generation filtering in the same physical capture is not yet demonstrated*; that specific behavior is exercised by the independent synthetic and source-tamper tests.

**New successful two-window series:** Opt-in `--recover-stale-scope` completed **2/2** read-only captures with source sequence endpoints **4344 → 4397**, **69 unique observed frames**, **21 missing source sequences** within the merged range, matching physical PID/build/player/zone and Lua publisher epoch 58. This run required **zero** scope rediscovery attempts, so the actual fallback branch remains offline-tested only. Ignored `artifacts/physical-target-series-recovery-20261121-1137-p37676/result.json` SHA-256 **F2A97358A4CB894E719869EF3F24FCBF906492BDCA49BA388476DCC6A661721A**; exit 0 and `no-target-continuity-candidate`. No live A → B → A occurred.

**Focused validation:** **237/237** Telemetry Python `unittest` cases passed, including source-hashed excluded-frame replay, tamper detection, illegal exclusion rejection, bounded same-process rediscovery, and refusal of unrelated failures. Relevant `git diff --check` passed.

### Reproduction

PowerShell 7 in `C:\work\riftreader2`. Always replace PID and output path after a fresh physical-RIFT preflight:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\capture_physical_telemetry_target_series.py --physical-pid CURRENT_VERIFIED_PID --count 2 --interval-ms 500 --scope-count 4 --recover-stale-scope --output-dir artifacts\NEW_UNUSED_SERIES
```

The saved original native and Lua evidence remains ignored by Git, not committed. The patch changes **no game input, UI focus, RIFT reload/restart, client memory writes, or other repository**. Publisher memory is ephemeral, and even an accepted selected generation remains a candidate, not independently authenticated publisher identity, complete world-state coverage or navigation authority. **Next:** observe actual A → B → A selected-target transitions during advancing telemetry, then correlate with native endpoints; do not infer transitions from a no-target baseline.
