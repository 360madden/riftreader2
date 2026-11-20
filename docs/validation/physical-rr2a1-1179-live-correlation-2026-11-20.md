# Physical RIFT 1179: RR2A1 Lua/native XYZ source correlation

**2026-11-20 ~05:38 EST | AMD-DESKTOP | Read-only**

## What changed

The existing `collect_physical_rr2a1_pair.py` pipeline can now use the build-1179 native context/XYZ readers and optionally scan from a caller-selected **canonical, current-process user-space cursor** (`--start-address`). The shared `probe_physical_rr2r1.py` scout accepts the same option. Unknown builds, mixed identities, noncanonical cursors and caller-supplied conflicting resume addresses fail closed. The default remains `0x10000`; the option changes scope only, not frame or freshness acceptance.

To recover 1179 support without cloning or weakening a native reader, this milestone changed:
- `scripts/compare_physical_player_context_pair.py`: admit only historical 1177 and source-verified 1179; reflect the actual source executable SHA in comparisons.
- `scripts/project_xyz_track.py`: admit only 1177/1179, require exact source/identity SHA correspondence and retain that SHA in the candidate track.
- `scripts/physical_player_xyz_bracket.py`: admit the same two exact builds for the pre/post native self+XYZ bracket while preserving source-hash, module, time and player checks.
- `scripts/collect_physical_rr2a1_pair.py`: add a bounded `--start-address` parameter and carry it into both scout passes and the bounded fallback, retaining original source receipts.
- `scripts/probe_physical_rr2r1.py`: add `--start-address` with exact-process cursor checks and incompatibility with `--resume-summary`. Legacy default and 1177 replay remain unchanged.

The old broad default can retain stale Lua strings that cause `nonadvancing-or-mixed-lua-frames`, and the full collector **correctly refused** that result. The improvement was to search a smaller *same-process* region where genuine frames had already been source-observed, **not** to disable the strict mixed-generation rejection.

## Physical observations

**Verified physical game:** AMD-DESKTOP `rift_x64.exe` PID **22532**, process start ticks **639307475284776509**, exact 1179 executable SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**. No game input, window focus change, UI reload, memory write, or process restart was sent by this workflow.

**Native-only bracket** (success): `artifacts/physical-xyz-bracket-1179-20261120-0527/summary.json`, two XYZ samples, self key **239816685251645959**, 0.0 sampled planar displacement, candidate-only.

**Broad RR2A1 scan** (correctly blocked): `artifacts/physical-rr2a1-1179-20261120-0528/` retained source-hashed pass-01 (eight frames seq 5910–5918), pass-02 (the same eight retained frames) and broad retry (four advancing frames 5926–5929 plus an anomalous sequence **30849** with a substantially **earlier** clock 16715.62109375). Both individual original passes decoded, but the mixed-generation retry did **not** pass the combined chronology contract. This is not a proven cause or origin for the retained anomalous frame.

**Focused two-pass RR2A1/native acquisition (PASS, exit 0):**

```powershell
cd C:\work\riftreader2
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
# Only for the then-verified PID 22532. Always reacquire current PID/start/build:
C:\Python314\python.exe -B scripts\collect_physical_rr2a1_pair.py --physical-pid 22532 --start-address 0x13000000 --scan-bytes 67108864 --scan-ms 8000 --samples 2 --interval-ms 100 --focus-second-pass --output-dir C:\work\riftreader2\artifacts\physical-rr2a1-1179-20261120-0537-scope
```

- Saved source/receipt directory: `artifacts/physical-rr2a1-1179-20261120-0537-scope/`
- Original collector summary SHA-256: **EF25D7DE61192EA10A5D57CF705C53536DFE499101A3CE8E9AFD25BCF5DC228F**
- Reader executable SHA-256: **711466EE1DE7F361FE6F7C3FC5B764F97A9DFFC1392D0D695A63655DE83FC9B7**
- First pass source-verified native scout snapshots: **8**, sequence window **7058–7069**, clock **20264.86328125–20270.40625**.
- Second pass source-verified native scout snapshots: **8 raw**, of which **6 overlapping old frames were discarded** and **2 newly advancing frames** (seq **7070–7071**, clock **20270.908203125–20271.408203125**) passed the strict pair check.
- All retained accepted frames report Lua epoch **1** and player `u035400012FA2D207`, matching the native player numeric key **239816685251645959**.
- Lua XYZ: **(6032.81982421875, 832.4400024414062, 3141.679931640625)**.
- Native before/after XYZ: **(6032.8154, 832.4444, 3141.68)**. Maximum absolute axis differences: **X 0.004424218749591091, Y 0.004397558593723261, Z 0.00006835937483629095**.
- Existing `coordinateAgreementScreen.result=consistent` within the empirical **0.05 native coordinate units** threshold. Lua health was stable in **9/9** comparable observed pairs, with no observed increase/decrease.
- Actual native bracket SHA-256s: before **FBEE1CDC1B4D5900EA65BB88CF025B334ED944B02AC83F61F304219B9AB0BC8D**, after **FA2FF342C78CEBF87A30D79751C26E1B5EB4FD73038F30F157A84E09EEC9EC41**.
- Source-hashed scout indexes: first **3ABB7A40C9A2B0995B8655D61AF3581406BDD1BC3FB79418E1EB9B4AD717FA43**, second **06DDE9A7901B713E7A0EF305192A561B703B007DF382E7F8737B4D6A5B632B31**.

**Independent offline replay (PASS, exit 0):** `compare_physical_rr2a1_passes.py --require-bracketed-order` reopened and revalidated the saved original native/scan sources, reproduced **8+2 advancing frames**, matching player and all maximum XYZ differences, and saved `artifacts/physical-rr2a1-1179-20261120-0537-scope/independent-replay.json`; SHA-256 **909FD4DC5FF5E1F7DB27D2C0FC641D66ACADB8CED435DDCAAF43D0053EE23583**.

## RR2R1 zone source remains independently blocked

One additional read-only scan explicitly searching for the **nonce-bound RR2R1** reference marker in the nearby same-epoch region examined two 64 MiB scopes with **0 RR2R1 prefixes and 0 copied frames**: `artifacts/physical-rr2r1-1179-20261120-0538-focus/summary.json`, SHA-256 **8A99751813FD461BF12865D9EDEB9B5E79137E46BA12339E8E1C03645D207D03**. That result covers only the examined private-memory scopes; it **does not** establish addon absence.

RR2R1 contains the Lua `zone` field but requires a currently bound reader nonce (manual `/rr2bind` under the existing addon policy). The unbound RR2A1 stream supports XYZ/health/combat, **not** zone. The already committed `correlate_native_zone_rr2r1.py` must wait for genuine, advancing, nonce-bound RR2R1 frames: do not label these RR2A1 observations as public API zone agreement.

## Validation

The combined focused source/contract regressions passed **134/134 Python tests**: existing player-context, position, native bracket, RR2R1 scout, RR2A1 two-pass capture and replay suites plus the new 1179 and explicit-cursor negative tests. `git diff --check` passed. These tests do not replace the separate source-hashed physical acceptance above; both were performed. No native .NET command implementation changed in this milestone.

## What this qualifies — and does not

The source-pinned evidence establishes an **advancing unbound Lua API producer**, in the current physical build-1179 game process, whose stationary XYZ agrees numerically with separately guarded native XYZ. It does **not** establish source nonce authentication, subsecond host-clock synchronization, unbroken owner/world identity, movement or combat causation, target correctness, native zone-ID equality, world-instance identity, route clearance, or game-restart durability for the Lua reference stream. Scan cursor addresses are specific to this process epoch; they are *not* permanent offsets and must never silently survive a restart.
