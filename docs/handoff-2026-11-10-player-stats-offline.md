# Player statistics discovery — offline checkpoint

**2026-11-10 19:31 EST · verified AMD-DESKTOP · RR2 codex/modular-foundation**

## Working result

- Commit `9b4e3d3`: new .NET 10 CLI `compare-native-stats --before PATH --after PATH [--output PATH]`.
- Reuses native `sample-current-stats` reports (5- or 20-selector format), including ordinary and unbuffed raw signed values from the existing shared C# stat record.
- Reports raw value deltas, ordinary-minus-unbuffed candidate spreads, unavailable pairs, source SHA-256 hashes, exact game build/player identity, process-epoch match, and limitations. Different players/builds and reversed time order are refused. No process or game access.
- Focused `NativeStatsComparisonCliTests`: **4/4 pass** (.NET 10; `--no-restore`).
- Real offline replay: `artifacts/rr2-stats-cross-epoch-spreads-20261111.json` compares retained Lab1 2026-11-07/08 full 20-selector captures of the same player across distinct process epochs: **20/20 selectors, 40/40 values unchanged; zero spread changes**. Historical agreement only—not current live freshness, cause, or restart qualification.
- Separate cross-player offline mapping check: retained Lab1 and Lab2 different player keys, identical executable SHA, **all 20 selector/index mappings match**. One-build structural compatibility only; not current live validation.
- Additional .NET 10 CLI `compare-native-vitals --before PATH --after PATH [--output PATH]` accepts two individual `native-current-vitals-candidate-sample/2` reports, checks build/player/time/resource kinds, and reports HP/Mana/Energy net deltas and per-second arithmetic without claiming regeneration. The existing Python tool remains the burst-format reader.
- Focused stat+vitals C# checks: **8/8 pass**. Retained physical single-sample replay in `artifacts/rr2-physical-vitals-compare-20261111.json`: same player/process for **2238.0873828 s**, HP candidate **18208 → 18208**, Mana/Energy explicitly unavailable; no change or regeneration inferred.
- Existing offline burst reducer separately accepted historical physical **10/10 and 2/2** samples, all with the same HP candidate **18208**; Mana/Energy unavailable. One mismatched burst was correctly rejected by the single-sample CLI, then a valid pair was used. No new game observation occurred.
- No interactive live test, movement, casting, desktop operation, VM operation or RRE repository edit. Other developers' dirty movement files and package locks preserved.

## Safe continuation

1. Reuse `CurrentBuildStatsSampleCommand.cs` and the new comparison CLI; prioritize a non-interactive **physical-host**, exact-PID native stat acquisition only when it will not contend with a movement reader. Retired VM samplers are historical reference, not the default target.
2. Reuse existing native vitals bursts and saved observations to investigate resource/regeneration candidates without changing or casting spells.
3. Broaden selectors or optimize contiguous reads only for a concrete retrieval need; keep candidate labels, same-player/build/epoch checks, and no interference with active movement ownership.

No live work or new game authority is implied by this handoff.

## 2026-11-10 20:41 EST — further offline milestones

- `dec1313`: C# selector-map acquisition batches all 84 map entries into one guarded buffer (two reads including final bracket).
- `dacca83`: adjacent mapped stat values are now grouped in native C#, retaining the per-range reread. Historical 20 selectors map to five contiguous groups per vector: `2..6`, `8..10`, `12..15`, `18..24`, `146`. A fake-memory regression verifies all 40 raw values and exactly two reads per group. This is a read-call model, **not measured live latency**.
- `283f543`: offline comparator reports selector-index drift independently of raw numeric changes and rejects overlapping captures. Six focused comparison tests passed. Retained Nov 7/8 pair replay saved as `artifacts/rr2-stats-cross-epoch-mapping-20261111.json`: 20/20 mappings stable, 40/40 values unchanged, zero changed spreads.
- `a3a64aa`: HP/Mana/Energy `inputs` expose `unclampedRatePerClockUnitCandidate` from already-decoded native coefficients (31 focused reader tests passed). This is **formula arithmetic, not measured regeneration**; clamping, tick quantization and clock calibration remain unresolved.
- Continue in the isolated player-stat lane. No live capture, movement, casting, VM or RRE changes this block. Concurrent developer edits and package locks were preserved.

## 2026-11-10 21:20 EST — physical offline replay and ownership guards

- `33339ec`: native `sample-current-stats` production path now resolves one anchored current-player lookup rather than three context scans; 9/9 focused tests passed. Actual latency change not measured.
- `5ccf0e9`: comparator reports five stat owner-path anchors and detects pointer changes within one process epoch; 7/7 focused tests passed. Physical saved 23:05→23:17 UTC replay `artifacts/rr2-physical-stats-owner-path-20261111.json`: 5/5 addresses, 20/20 mappings and 40/40 raw values unchanged. This is not dynamic freshness proof.
- `423098c`: offline vitals comparator rejects typed Mana/Energy samples contradicting explicit native resource kind; 7/7 tests passed. Legacy kind-absent saved samples remain accepted.
- Only offline saved artifacts and fake-memory/.NET tests were used. Physical RIFT, movement/navigation, RRE and unrelated working-tree changes remained untouched.

## 2026-11-11 EST — full native selector-map milestone

- `sample-current-stats` now exports `selectorMapCandidate`: all **84 signed selector-to-vector-index entries**, including unknown selectors and negative sentinels, from its **existing 336-byte bracketed map read**. The known 20 selectors and their 40 ordinary/unbuffed candidates are unchanged; no extra process read is introduced.
- `compare-native-stats` optionally compares those complete maps and reports changed unnamed selectors separately from named stat values. It rejects invalid map length/entries and any contradiction with named selector mappings. Old saved snapshots without the map remain comparable with `selectorMapComparison.status=unavailable`.
- Focused .NET 10 regression checks: native reader **10/10 pass**; offline comparison CLI **10/10 pass**. Initial concurrent test builds collided on a shared compiler output file; sequential rerun passed.
- No live process sampling, gameplay input, VM access, movement/nav edits or RRE spellcasting work. Candidate map indices do **not** independently establish stat semantics or regeneration rates.

