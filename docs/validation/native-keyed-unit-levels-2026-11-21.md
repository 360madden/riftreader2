# Read-only keyed NPC/unit levels — new native retrieval workstream

**November 21, 2026 · ~4:15 PM EST · AMD-DESKTOP · exact 1177/1179 native C#/.NET 10**

## New capability

`CurrentBuildUnitLevelsSampleCommand` reads up to **12 explicitly supplied decimal 64-bit loaded-unit keys** without changing the selected target, issuing input, invoking game getters or scanning unrelated game-client memory.

It reuses RR2's existing exact-build `CurrentBuildPlayerLookup` and keyed native unit table. For each requested key it resolves the referenced unit's independently checked **health-component entity backlink**, the native owner vtable/getter pair and the previously recovered **alternate level component**. It selects current build offsets by executable SHA-256:

| Mapping | Historical 1177 | Updated 1179 |
|---|---|---|
| Manager RVA | `0x33624A8` | `0x3373C68` |
| Health component selector | `0x2F57850` | `0x2F68850` |
| Numeric-level component selector | `0x2F58270` | `0x2F69270` |
| Owner vtable | `0x2927448` | `0x2933218` |
| Owner getter | `0x19D21E0` | `0x19D2020` |

If the alternate-primary level field contains `-1`, the reader tries the existing alternate-secondary level path. Only positive numeric values within the bounded candidate range **1–1000** are published as `numeric-level-candidate`. Unknown, missing, changed or improperly typed entity/owner/component data results in an **explicit unavailable row**, not guessed level zero. Legacy builds additionally retain their historical global-owner fingerprint checks. A bounded shared native session and same-owner byte-anchor revalidation are required for every successful source.

The C# `sample-current-unit-levels` command is exposed through the standard Python `physical_rift.py --read-native unit-levels` dispatch. `native_unit_level_projection.py` validates contract, owner, exact decimal unit keys, ordered rows, candidate-level status, value bounds, typed unavailable reasons and source chronology.

## Next physical command

**RIFT was closed during development** (physical preflight returned `not-running` at approximately 4:11 PM), so this new keyed-level reader has **not yet been run against a real 1179 process**. After launching physical RIFT and verifying its **new PID/start ticks/on-disk executable SHA**, run in **PowerShell 7** from `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid NEW_VERIFIED_PID --read-native unit-levels --unit-keys 9223372039438477006,9223372039438477595 --output artifacts\NEW_UNUSED_UNIT_LEVELS.json
```

The two example decimal keys were previously observed in current-build native nearby-unit candidate data, but **must be reacquired after restarting**; a loaded unit from an old process may no longer exist. Do not treat an absent keyed unit as current-world absence or hostility. The first decimal key corresponded to previously selected `u800000009A0026CE` (Argent Glade Guard) with a separate native level-10 candidate. New keyed-level output for that character remains to be independently tested.

The command does not determine relationship, hostility, elite/group status, actual RIFT UI level, world instance, line of sight, attackability, range or combat suitability. **No movement, casting or target selection is authorized by the result.**

## Validation

- Native C#/.NET 10 build succeeded with **0 warnings / 0 errors**.
- New keyed-reader tests: **8/8 passed**, including primary/secondary level branches, historical/current type ownership, missing units, invalid levels, changed source, strict key bounds and no invented values.
- New Python source projection/admission tests: **7/7 passed**, including 64-bit keys, malformed values, ordering and correct CLI argument forwarding.
- Full RR2 .NET 10 solution: **1,953/1,953 passed** (445 foundation + 1,508 Live).
- Related native Python suites: **70 run, 69 passed, 1 Windows symlink-privilege skip**.
- All selected source changes passed `git diff --check` (line-ending normalization warnings only).

**Next acceptance:** when physical RIFT is available, run the keyed reader against several freshly discovered nearby unit IDs and compare any exact matching **currently selected** unit's numeric level with the restored guarded selected-target reader and independent RIFT UI/Lua evidence. Consider integration into hunt-threat assessment only after the relevant per-unit source meanings and freshness are qualified.
