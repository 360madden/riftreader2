# Physical nearby-unit and NPC API correlation — November 21, 2026

**Original evidence host:** AMD-DESKTOP. The workflow combines native reports, retained Lua 5.1 API observations and an offline join. Live readers require a verified local Windows host and current RIFT process. Saved evidence can replay on another machine.

## New working pieces

- `scripts/npc_survey_live.py` now retains the **exact original Lua wire envelope** for every accepted advancing survey source as `frame-NN.wire` alongside the original survey result. It checks the retained byte digest against the source receipt. Earlier survey summaries without these original wire sources are intentionally **not independently replay-qualified**.
- `scripts/replay_npc_survey.py` opens the survey's original saved Lua wires, verifies each SHA-256, reruns the existing NPC schema/nonce/player/ID decoder, requires advancing source sequence and clock, checks the selected generation and two-frame confirmed IDs, and verifies the published snapshot is the last original frame. Source authenticity and world-instance identity are not established by a hash alone.
- `scripts/join_physical_nearby_npc_survey.py` reopens and validates the **original native nearby position and name reports**, regenerates the existing nearby-unit projection, then compares it with a successfully cold-replayed NPC survey. It requires the same process PID/start/build, exact self and unit IDs, bounded host observation interval, matching native/API names and nearby XYZ within explicit tolerances. Any ID/name/position discrepancy withholds the API level and relation for that unit; unknown fields stay unknown.

The join reports `apiLevelCandidate`, `apiRelationCandidate`, native distance and height difference, name and position agreement, and a refusal reason for unqualified rows. **All rows retain `combatSuitabilityStatus=unqualified`, `castAuthorized=false`, `moveAuthorized=false`**. Even when the Lua API reports `relation=hostile`, the comparison does not establish action permission, world-instance equality, path clearance, line of sight, attackability or a verified combat outcome.

Native/Lua level agreement uses the two latest replayed Lua frames for the same
unit ID. Both frames must carry the same valid level and fall within the
configured comparison window. The report keeps the previous and latest API
level candidates alongside `apiLevelEvidenceStatus`, which identifies changed,
missing or out-of-window evidence.

## CLI use

From the repository root in **PowerShell 7**, verify the local host and current RIFT process. Then use that exact PID in the native nearby inventory command.

```powershell
$rr2Host = [Environment]::MachineName
python -B scripts\physical_rift.py --expected-host $rr2Host
python -B scripts\physical_nearby_units.py --expected-host $rr2Host --physical-pid CURRENT_VERIFIED_PID --radius 35 --max-names 12 --output-dir artifacts\NEW_NATIVE_NEARBY
```

The separate **RR2 NPC survey addon must actually be loaded and nonce-bound to the intended exact IDs** before `npc_survey_live.py` can produce an advancing survey. It has an existing `/rr2survey bind NONCE COMMA_SEPARATED_IDS` command. Use a fresh explicit nonce and up to 12 exact `u`-prefixed IDs taken from the native nearby report. The working addon installation and current nonce-bound source publication must be verified; repository source files or historical captures do not prove the addon is active in the running client.

When those independently established prerequisites exist:

```powershell
python -B scripts\npc_survey_live.py --expected-host $rr2Host --physical-pid CURRENT_VERIFIED_PID --session-id CURRENT_NONCE --unit-ids EXACT_COMMA_SEPARATED_IDS --auto-map --output artifacts\NEW_NPC_API_SURVEY
python -B scripts\replay_npc_survey.py --summary artifacts\NEW_NPC_API_SURVEY\result.json
python -B scripts\join_physical_nearby_npc_survey.py --nearby artifacts\NEW_NATIVE_NEARBY\nearby-report.json --npc-survey artifacts\NEW_NPC_API_SURVEY\result.json --max-gap-seconds 30 --position-tolerance 5 --output artifacts\NEW_NATIVE_API_JOIN.json
```

With `--auto-map`, the API survey searches a bounded 512 MiB of readable private process memory and does not require an earlier native scout seed; the older seeded mode remains available when the flag is omitted. Neither mode issues `/rr2survey bind` or controls the desktop.

A successful join is a **research/candidate** result only. The default interval must encompass the two sequential acquisitions; a stale source or changed owner refuses correlation. Source files and result destinations are never silently overwritten.

### Prepare and replay a saved bind plan

Check the local reader and addon before preparing a plan for a current RIFT
process. The tool looks for the addon under the Windows Documents folder. Use
`--installed-casting-dir` for a custom installation.

```powershell
python -B scripts\prepare_physical_npc_survey.py --expected-host $rr2Host --check-dependencies --include-levels
python -B scripts\prepare_physical_npc_survey.py --expected-host $rr2Host --physical-pid CURRENT_VERIFIED_PID --include-levels --output-dir artifacts\NEW_NPC_BIND_PLAN
```

The dependency check verifies the installed addon and the reader's advertised
nearby-position, name and player-context commands without selecting RIFT.
`--include-levels` adds the keyed native level command, and `--check-addon`
checks the installed files alone. Select a published reader with
`--native-reader $rr2PublishedReader` or `RR2_NATIVE_READER`. Preparation
includes absolute script and reader paths in the capture command, so it can run
in another shell on the capture host. The command carries the plan's process
start ticks, executable SHA-256 and existing native join deadline. Capture
verifies the process and deadline at startup and checks the deadline again
before retaining survey frames.
A direct capture with an explicit seed uses the reader option for its native
scout and fragment reads.

Copy the entire plan folder, including `plan.json`, `native/` and `addon-evidence/`, to run the offline check from any checkout. Replay verifies the original capture identity and times, reconstructs the selected IDs, checks the saved bind text and verifies the retained manifest and Lua file. Older plans still replay with addon evidence reported as `recorded-only`.

```powershell
python -B scripts/prepare_physical_npc_survey.py --replay-plan artifacts/COPIED_NPC_BIND_PLAN/plan.json
```

The replay describes the saved capture. A live API survey still requires a fresh plan, the in-game bind and advancing Lua frames from the active RIFT process.

## What was verified

1. **Original physical native evidence replayed:** On build 1179, AMD-DESKTOP, PID `37676` and start ticks `639308565554559088`, independently reopening the previously captured `artifacts/physical-nearby-units-20261121-1234-p37676/nearby-report.json` and both original native source files succeeded. The report was source-hashed at `7D43A14D547629A81BC0F00D6C841D4DFF3FDACF4FC297AD82249B5DADDCFA35`, with **17 nearby units / 15 available name candidates**.
2. **Offline Lua survey source-replay tests:** **8/8 passed** without the game or a Lua installation. Synthetic same-schema originals exercised actual `npc_survey_live.acquire` wire retention plus independent replay, byte tampering, summary tampering, changed IDs and source refusal.
3. **Offline native/API join tests:** **9/9 passed**, with two original validated native JSON fixtures and two saved raw NPC Lua source frames. Tests confirm matched level/relation *candidates*, name/XYZ mismatches, wrong process/player, stale capture time, source tampering and zero action authority.
4. **Related Python regression suites:** **47/47 passed** across new replay/join, existing native context join, nearby CLI, and native unit-position/name readers.

**November 21 blocker:** That session ended before it obtained a freshly verified,
nonce-bound NPC API survey. Its Python 3.14 environment also lacked `lupa` for
the Lua 5.1 producer tests. The configured [current validation environment](../workflows/development.md#restore-build-and-test)
now runs those tests offline. Live native/API level and relation correlation
still needs an advancing survey from the local RIFT process.

**Next:** Establish an advancing nonce-bound NPC survey for several current exact nearby IDs, then validate name/level/relation agreement, and finally add the independent hostility/attacker, level-delta and real response checks required by `target_selection` before any automatic encounter.

## November 21, ~1:35 PM EST — live map scout and bind preparation

The physical RIFT client on verified **AMD-DESKTOP** remained PID **37676**, process-start ticks **639308565554559088**, exact build-1179 SHA **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**. The **installed** RiftReader2Casting **0.5.1** manifest includes "npc_survey.lua" in its actual RunOnStartup list, and that installed module matches the repo's original Lua by SHA-256 **045E2191FC84A63F10C5EB1F5A3AA2B15E5526AC725FD6F9FEBDC19E27E7C11F**. Installation does **not** prove the running client registered its slash command.

The existing \`npc_survey_live.py\` now offers \`--auto-map\`: it reuses a bounded **read-only Windows private-memory** scanner, requires exact matching player/nonce/unit IDs, re-verifies full game process/window identity before and after reading, retains original accepted Lua wire bytes and saves per-attempt bounded-scan diagnostics. **The first physical invocation revealed a real mismatch between the legacy normalized three-field identity and the full physical Windows target.** That was fixed and covered by an exact normalized/full-owner test. The corrected two-attempt physical run reached the scanner and returned **exit 2 / no-advancing-survey-pair**, with **512 MiB surveyed per attempt**, one raw NPC frame marker each, **zero validated nonce-bound frames**, and \`inputSent=false\`. Original ignored evidence is in \`artifacts/npc-auto-map-unbound-20261121-1331-p37676/\`; attempt-1 locator source SHA **07CE8AFE40EFC1800E37C19F18507526E9F7A9213EE13637A9931AE511B6E6E3**. This is a **bounded negative observation** for a nonce never bound in-game; it is not proof the addon is absent.

New \`scripts/prepare_physical_npc_survey.py\` removes the manual ID/nonce assembly. It checks the **actual** installed Casting manifest, confirms the installed Lua bytes, acquires current native nearby candidates (up to **18** name lookups), chooses at most **12 named exact IDs**, generates a fresh random 32-lowercase-hex nonce, and saves \`plan.json\` with \`inGameBindCommand\`, \`captureCommand\` and \`joinCommand\`. It sends **no** UI/game input. Example in **PowerShell 7** from \`C:\work\riftreader2\`:

\`\`\`powershell
C:\Python314\python.exe -B scripts\prepare_physical_npc_survey.py --expected-host AMD-DESKTOP --physical-pid CURRENT_VERIFIED_PID --radius 35 --max-ids 12 --installed-casting-dir 'C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2Casting' --output-dir artifacts\NEW_UNUSED_NPC_BIND_PLAN
\`\`\`

Only the current in-game operator can complete the one-time \`/rr2survey bind\` from the freshly produced plan. Immediately afterward, run that plan's \`captureCommand\`, and only on successful source advancement run \`joinCommand\`. The native/API join is bounded to **120 seconds** from the sampled native source, so a delayed test requires a **new** plan and nonce. A physical prepared-but-not-activated plan first yielded 6 named IDs; after broadening the bounded native name lookup, a new one yielded **7**. Original ignored output: \`artifacts/npc-bind-prep-20261121-1335-p37676/plan.json\`. Neither was an activated in-game survey.

**Validation:** **110/110** directly relevant Python tests passed across the auto-map scout, bind preparation, retained NPC source replay, native/API correlation, native unit readers and prior Telemetry locator. The Lua 5.1 producer integration suite still needs \`lupa\`, which is unavailable in Python 3.14 and three inspected project virtual environments; no environment was changed. A positive **real-game NPC source capture** is still pending the in-game bind, and no level/relation or encounter permission is claimed.
