# Build-1179 physical player-state zone bracket — November 18, 2026

**Scope:** RR2 `C:\work\riftreader2`, AMD-DESKTOP physical RIFT only, build `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`. Optional read-only source correlation; no game input, UI reload, focus change, process writes, movement or restart.

## Delivered

`scripts/collect_physical_player_state.py` now accepts `--include-zone`. The option brackets the existing three-source player-context/position/vitals collection (and optional stats) with independent `zone-context` reads. Existing calls **without** the flag retain their original behavior. Both zone sources are separately SHA-256-hashed, pinned to the same host/PID/process-start/build/module/self key as the other sources, and parsed through the existing strict native report path. The completed summary contains `zoneBracketCandidate` only if both zone endpoints are available and agree on `selfKey`, `rawZoneKey`, and `zoneIdCandidate`, with nonreversed acquisition timestamps. Unavailable/changed source, hash, module, player, or epoch refuses summary publication. Source files remain in the new output directory for diagnosis.

**Example (read-only; refresh PID first):**

```powershell
cd C:\work\riftreader2
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\collect_physical_player_state.py --physical-pid CURRENT_PID --samples 2 --interval-ms 100 --include-zone
```

## Actual physical validation

- **Command:** `C:\Python314\python.exe -B scripts\collect_physical_player_state.py --physical-pid 77980 --samples 2 --interval-ms 100 --include-zone --output-dir C:\work\riftreader2\artifacts\physical-state-zonebracket-20261118-1629`
- **Host/process:** machine-local `AMD-DESKTOP`, physical PID `77980`, process-start UTC ticks `639305214834918403`, installed executable SHA `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.
- **Result:** exit **0** and `complete-candidate`; player self key `239816685251645959`, Level **45**, Warrior; two position values `(7452.0957, 886.4349, 3048.7134)` with zero measured planar displacement; HP **18208/18208**; observed resource kind **1**, Mana/Energy correctly unavailable for this kind.
- **Zone before:** raw `1216123138`, ID candidate `z487C9102D2EA79BE`, completed **2026-11-18T21:28:25.4354946Z**.
- **Zone after:** same raw and ID candidate, completed **2026-11-18T21:28:30.8465562Z**, both type/child candidates guarded; `zoneBracketCandidate.status=matching-candidates`, `worldInstanceStatus=unavailable`.
- **Ignored evidence:** `artifacts/physical-state-zonebracket-20261118-1629/summary.json`, SHA-256 **4FD29439811D5A0417403260A1E370EF6E29B7D97E97C157AFAFC70A5B1A3E57**. Individual raw sources `zone-before.json`, `player-context.json`, `position.json`, `vitals.json`, `zone-after.json` are referenced by the summary with their own exact hashes.
- **Tests:** all **94** focused Python tests passed: original physical-state collector, new zone-bracket tests, physical zone parser, physical-only process-selection tests. `git diff --check` passed. No .NET native implementation changes.

## Limits and next use

This is **matching endpoint candidates**, not an atomic world snapshot or proof the zone never briefly changed between samples. It does not independently verify the public RIFT Lua `Inspect.Unit.Detail(...).zone` value, world-instance uniqueness, player movement causation, waypoint clearance, or full-game restart durability. The separate Telemetry v0.5.0 companion currently rejects 1179 by exact build guard; preserve that gate and coordinate its correction with that repository owner. Use this bundle as input to future changed-zone and route-admission tests; never promote candidate fields to navigation authority without additional evidence.
