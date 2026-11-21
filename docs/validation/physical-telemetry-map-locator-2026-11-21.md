# RR2 Telemetry map-aware publisher discovery — physical RIFT 1179

**2026-11-21, approximately 08:44–08:46 EST · verified AMD-DESKTOP**
**Observed RIFT process:** PID `37676`, start ticks `639308565554559088`, exact executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.

## Result

A new optional `--discover-scope` mode eliminates the caller's need to supply a process-specific Lua heap scan origin. It uses the existing **read-only** process handle, Windows `VirtualQueryEx` mapping of committed readable private regions, and bounded marker/identity inspection to propose candidate Telemetry windows. It then passes those nonadjacent windows to the existing survey, preferring source-sequence advancement when candidate scopes compete. None of the locator or survey results grants freshness qualification: new two-pass captures, process/build/player/zone constraints, original source bytes/hashes, independent target and zone replay, and source-clock progression remain decisive.

**Bounded locator defaults:** up to 512 MiB of attempted readable-private-region scanning, 12 seconds, and 1,024 marker checks; at most eight candidate windows (CLI default four). A missed marker is a **bounded search miss**, not a proof that the Lua publisher is absent.

The actual physical-client invocation below succeeded **exit 0** without any manual search address. The locator inspected 512 MiB, found 83 envelope marker occurrences, validated 82 candidate frames for the pinned player and zone, and discovered two 64-MiB scope origins (`0x8000000` and `0xC000000`). Its short follow-up chose the **advancing** `0x8000000` region, even though the competing candidate retained a slightly higher historical top sequence. The separate capture then saved **50 + 50** Lua frame occurrences, passed source-clock progression and native/Lua zone candidate agreement for Silverwood `z0000000CB7B53FD7`.

**Independent cold replay:** `scripts/replay_physical_telemetry_target.py` exited **0** with 55 unique Lua source sequences, all 55 showing `selectionState=none`, no A→B→A transitions, and native raw-target-zero endpoints *compatible* with Lua-none endpoints. It is a **no-target-baseline candidate**, not a confirmed no-target state or controlled target-selection experiment.

**Original ignored evidence:** `artifacts/physical-telemetry-target-autolocate-20261121-p37676-01/summary.json` SHA-256 `D871B7514FFD876B52CC5C685757FF382933EA334835D4EBB11CF5DF61A9F06B`; original `scope-survey.json` SHA-256 `98254DA4E3083B5AFA734E3EAAC78027B5CA807AF7770956D9254FB2632F6139`.

## Reproduction command

Run in **PowerShell 7** from `C:\work\riftreader2` on verified AMD-DESKTOP, replacing the PID with the current one after a fresh `scripts\physical_rift.py --expected-host AMD-DESKTOP` preflight:

```powershell
C:\Python314\python.exe -B scripts\capture_physical_telemetry_zone.py --physical-pid CURRENT_VERIFIED_PID --auto-scope --discover-scope --scope-count 4 --include-native-target --output-dir artifacts\NEW_UNUSED_RESULT_DIRECTORY
C:\Python314\python.exe -B scripts\replay_physical_telemetry_target.py --summary artifacts\NEW_UNUSED_RESULT_DIRECTORY\summary.json
```

A capture that exits 2 / `unqualified` must **not** be promoted to success; the replay command is meaningful only for a successful, retained source bundle. Focused Telemetry suite: **184/184 Python unittest tests passed**, including new nonadjacent mapped-location, bounded-budget, source rejection, cross-chunk, and integration checks; targeted `git diff --check` passed.

## Limits and next outcome

The 512-MiB region search is deliberately **not exhaustive** across the current 3+ GiB private readable process space. Region allocation and source publishing may change between process epochs, and even a good survey cannot force an advancing acquisition window. The player target never changed in this capture; a separately observed A→B→A selection with advancing Lua and native evidence remains the next target-specific acceptance. No game movement, casting, UI automation, reload, process memory write, game restart, or sibling-repo modification was used.
