# Native nearby-unit readout — physical RIFT 1179

**November 21, 2026 · verified AMD-DESKTOP · one-command read-only CLI**

The new `scripts/physical_nearby_units.py` combines the existing exact-build native `unit-positions` and `unit-names` readers. It samples one bounded loaded-unit manager subset, selects nearby non-player position candidates by horizontal distance, then reacquires their exact **decimal unit keys** in one bounded native name batch.

The original native reports are kept under a caller-chosen new output directory, reloaded from original bytes, SHA-256 checked and compared with the native receipt projection. Both reports must match the same pinned physical process and player. Names are matched to their **exact unit key and entity address**; if the entity changes between sequential reads, the name is withheld rather than assigned to the wrong unit. Successful output includes per-unit XYZ, horizontal distance, height delta, optional normalized screen point and name/unavailability reason. An empty nearby result is valid for this bounded subset and skips name lookup. No gameplay input is sent.

## Command

From the RR2 checkout on the verified local Windows host, use the
[published native reader](../workflows/development.md#publish-the-local-native-reader).

```powershell
$rr2Host = [Environment]::MachineName
python -B scripts/physical_rift.py --expected-host $rr2Host
python -B scripts/physical_nearby_units.py --expected-host $rr2Host --physical-pid CURRENT_VERIFIED_PID --native-reader $rr2PublishedReader --radius 35 --max-names 18 --output-dir artifacts/NEW_UNUSED_NEARBY_READOUT
```

Use the actual PID from the new preflight. `--radius` must be greater than 0 and at most 50 native horizontal units; `--max-names` is bounded to 1–32. The CLI refuses existing output directories rather than overwriting their evidence, returns exit 2 for unavailable/invalid sources, and writes `failure.json` for an acquisition failure after directory creation.

## Numeric level candidates

On the verified local Windows host, add `--include-levels` to the nearby reader or to `scripts/prepare_physical_npc_survey.py`. The reader saves `unit-levels-native.json` alongside the position and name sources. It requests up to 12 keys, prioritizing named units so the NPC plan can use that same batch. A level attaches only when its unit key, entity address, player, process and build match, and the three captures fit within 30 seconds.

NPC correlation replays the original level source against its SHA-256 and reports whether the native and Lua numeric candidates agree when it has both. A level result leaves hostility and combat suitability unqualified.

To compare a saved selected-target profile with a keyed native level report,
copy the profile directory with its original sources and supply the retained
SHA-256 of the keyed report. Replay finds the native sources beside the copied
profile on the analysis machine. It checks the native process and player identity, exact
selected unit and entity, and a 30-second comparison window. It reports matching
or differing native candidates. Independent RIFT UI or Lua confirmation remains
a separate check.

```powershell
python -B scripts/replay_physical_selected_target_profile.py --profile PROFILE_JSON `
  --keyed-levels KEYED_LEVELS_JSON --keyed-levels-sha256 RETAINED_KEYED_SHA256
```

## Physical acceptance

- Verified exact physical RIFT process: AMD-DESKTOP, PID `37676`, process-start ticks `639308565554559088`, executable SHA-256 `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.
- An initial native scan examined **341 unit entries**, found **74 position candidates**, and saw **18 non-player candidate positions within 35 units**. A native name batch returned **16 name candidates and 2 unavailable**. This was an independent scouting command before the new CLI existed.
- The new one-command CLI then completed successfully (exit 0), examining **342 unit entries**, finding **75 position candidates**, **17 within 35 units**, and **15 named candidates**, with 2 unqualified name results. Distances and counts vary between observations; these scans are not atomic.
- Names among nearby candidates included `8th Guard Soldier`, `Sergeant Heilig`, `Bram Gamal`, and `Argent Glade Guard`. These are **name candidates, not evidence of friend/foe, level, elite rank, interaction type or threat**.
- Original saved report: ignored `artifacts/physical-nearby-units-20261121-1234-p37676/nearby-report.json`, SHA-256 `7D43A14D547629A81BC0F00D6C841D4DFF3FDACF4FC297AD82249B5DADDCFA35`; original native position and name JSON files reside in the same ignored folder.

**Tests:** 9/9 new CLI tests and 10/10 existing unit-reader regressions passed. Tests cover explicit wrong host/PID, process owner mismatch, source hash mismatch, entity-address change, name cache miss, time order, empty nearby output and no-input CLI dispatch.

### Qualification boundary

This is a **bounded loaded-unit inventory** with sequential native reads, not complete zone discovery, player-character classification, real-time enemy hostility, correct floor/instance, LOS/occlusion or automatic hunt target eligibility. A names-only match must never authorize combat or movement. Future use in `target_acquire` and hunt missions should require separately qualified relation, unit level, exact selected-target identity and fresh owner/zone/position evidence before action. Existing target-acquire and hunt work-in-progress files were not modified for this milestone.
