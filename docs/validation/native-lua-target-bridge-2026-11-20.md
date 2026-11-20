# RR2 RIFT 1179 — native/Lua selected-target correlation preparation

**2026-11-20, ~07:04 EST · AMD-DESKTOP · physical RIFT only**

## Outcome

A new CLI, `scripts/replay_physical_telemetry_target.py`, independently reopens **source-hashed** Telemetry `RIFTTLM1` Lua frames from an already-accepted RR2 native/Lua zone capture. It projects `selectionState`, `targetId`, and `target.id` with strict schema/identity checks and reports observed target changes and any candidate **A → B → A** return sequence. It does **not** control or select the game target.

The existing `scripts/capture_physical_telemetry_zone.py` now supports **optional** `--include-native-target`. When enabled, it takes separate guarded, one-shot **native player-context** source snapshots immediately before Lua pass 1 and after Lua pass 2, inside the same exact PID/start/build and native zone endpoint bracket. Source files are saved as `native-target-before.json` and `native-target-after.json` and SHA-pinned in the summary. The collector now requires its existing native/Lua zone replay **and** the new independent target replay before returning a positive result for this option. The original zone-only path remains unchanged.

The target replay admits the optional native bracket only after checking: original source SHA, exact module/process/start/build/player identity, strict reader candidate contracts, original time stamps and their ordering relative to both Lua scan windows and native zone endpoints. It reports **matching**, **different**, or **unavailable** native-versus-Lua endpoint candidates rather than silently equating a native zero getter with a verified no-target state. Genuine Lua target A→B→A transitions, if independently observed, remain candidate-only and are not called user-caused unless a separate supervised control record establishes that.

## Physical read-only evidence

**Game:** AMD-DESKTOP physical RIFT PID **22532**, start ticks **639307475284776509**, exact build-1179 SHA **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**, Atank player unit **`u035400012FA2D207`**.

1. The previously source-hashed and independently replayed **06:39 EST** `--auto-scope` zone capture is valid for target-state projection. Its **22 unique advancing Lua source sequences all report `selectionState=none`**; there are **no target-selection transitions** in that saved window. `replay_physical_telemetry_target.py` processed the original zone bundle and returned **`no-target-baseline-candidate`**, exit 0. Ignored replay artifact: `artifacts/physical-telemetry-zone-autoscope-20261120-0640/target-baseline.json`, SHA **C976B750B3495F123BF3915E5755A6046DEAC9BC8AE0268213F55A6D71AE9B8C**. This file references the earlier accepted zone capture; it contains no claimed A→B→A.
2. A separate read-only native **player-context burst** around **06:50 EST** on the same PID returned **two raw target-zero candidates** and stable player key. Original source `artifacts/physical-native-player-context-7bf256ee9a654e09aab309fc1ad002ac.json`, SHA **C2F264149A975B740E0FCA3F1942C06D6201BB27F60C2474BAF34AB19061EEB8**. Another one-shot native context around **06:53 EST** returned the same raw target-zero candidate; original source `artifacts/physical-native-player-context-ab5128c7b87749919dd8fa460ee89b17.json`, SHA **8261914B41528769A19BAD5253624D7EC5A21517F49509A46D38B90387953C78**. **Those reads were not contemporaneous with the Lua baseline**, so they are compatible cross-time samples, not accepted native/Lua target endpoint agreement.
3. The first optional combined capture around **06:56–06:57 EST** automatically selected an observed Telemetry region and acquired both native target endpoints (both raw zero), but the **8+8** copied Lua frames did not advance; the command exited **2**, retaining source-hashed evidence and `status=unqualified`. Saved `artifacts/physical-telemetry-target-20261120-0657/summary.json`, SHA **693F26ED794E819E64AC40A7EDD78FABFDDA8DEE28D7B6647B67F4EA496F140E**.
4. A second targeted, bounded capture around **06:58 EST** acquired **11+11** saved Lua frames and both native target endpoints, still without advancing source sequences; exit **2** and `unqualified`. Saved `artifacts/physical-telemetry-target-20261120-0659/summary.json`, SHA **7931B014B039EE94AC9A3697B034D6672A11C2A312177C90C18BAB539ADB97C5**. Retained Lua frame-clock values did not advance in either attempt, which may reflect frame publication stopping or allocation locality. **No cause was established**; the fail-closed source-sequence gate was preserved.

None of the unsuccessful bundles was promoted into a positive target agreement. No RIFT gameplay input, target selection, focus change, memory write, UI reload or restart was performed by RR2 during this work.

## Validation

The focused target implementation and backward-compatibility suites passed **104/104 Python tests**. The wider native/zone/Telemetry/target composite regression passed **252/252 Python tests**, exit 0, including **synthetic-only** A→B→A, changing native/Lua endpoint mismatches, tampered frame hashes, mismatched module/PID/player, reversed capture chronology, and partial native target metadata. `git diff --check` passed. No .NET native reader code or sibling Telemetry addon code was modified.

## CLI

```powershell
cd C:\work\riftreader2

# Analyze prior independently replayed physical Telemetry source frames (offline):
C:\Python314\python.exe -B scripts\replay_physical_telemetry_target.py --summary artifacts\physical-telemetry-zone-autoscope-20261120-0640\summary.json

# Future bounded live acquisition when Telemetry frames are advancing again:
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\capture_physical_telemetry_zone.py --physical-pid CURRENT_VERIFIED_PID --auto-scope --scope-count 6 --start-address 0x13000000 --scan-bytes 67108864 --include-native-target --output-dir artifacts\NEXT_UNUSED_CAPTURE_DIRECTORY

# Only after a SUCCESSFUL capture above, independently check Lua target frames
# and both native target endpoints from that exact saved bundle:
C:\Python314\python.exe -B scripts\replay_physical_telemetry_target.py --summary artifacts\NEXT_UNUSED_CAPTURE_DIRECTORY\summary.json
```

**Next P1 acceptance:** a user-observed/manual target-selection A → B → A sequence while actual Lua publication is advancing, with source-hashed native before/after target candidates and independent target replay. A native target-zero read is not definitive absence of selection; a selected-ID match in two non-atomic endpoints is not proof of exact transition timing. Full world-instance and navigation authority remain unqualified.
