# Player statistics discovery — offline checkpoint

**2026-11-10 19:31 EST · verified AMD-DESKTOP · RR2 codex/modular-foundation**

## Working result

- Commit `9b4e3d3`: new .NET 10 CLI `compare-native-stats --before PATH --after PATH [--output PATH]`.
- Reuses native `sample-current-stats` reports (5- or 20-selector format), including ordinary and unbuffed raw signed values from the existing shared C# stat record.
- Reports raw value deltas, ordinary-minus-unbuffed candidate spreads, unavailable pairs, source SHA-256 hashes, exact game build/player identity, process-epoch match, and limitations. Different players/builds and reversed time order are refused. No process or game access.
- Focused `NativeStatsComparisonCliTests`: **4/4 pass** (.NET 10; `--no-restore`).
- Real offline replay: `artifacts/rr2-stats-cross-epoch-spreads-20261111.json` compares retained Lab1 2026-11-07/08 full 20-selector captures of the same player across distinct process epochs: **20/20 selectors, 40/40 values unchanged; zero spread changes**. Historical agreement only—not current live freshness, cause, or restart qualification.
- No interactive live test, movement, casting, desktop operation, VM operation or RRE repository edit. Other developers' dirty movement files and package locks preserved.

## Safe continuation

1. Reuse `CurrentBuildStatsSampleCommand.cs` and the new comparison CLI; prioritize a non-interactive **physical-host**, exact-PID native stat acquisition only when it will not contend with a movement reader. Retired VM samplers are historical reference, not the default target.
2. Reuse existing native vitals bursts and saved observations to investigate resource/regeneration candidates without changing or casting spells.
3. Broaden selectors or optimize contiguous reads only for a concrete retrieval need; keep candidate labels, same-player/build/epoch checks, and no interference with active movement ownership.

No live work or new game authority is implied by this handoff.
