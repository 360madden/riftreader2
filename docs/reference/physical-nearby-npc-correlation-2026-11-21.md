# Physical nearby-unit and NPC API correlation — November 21, 2026

**Owner machine:** AMD-DESKTOP. **Workflow:** source-hashed native retrieval, retained Lua 5.1 API observations, read-only offline joining. The existing native `unit-positions` and `unit-names` readers are reused; no new combat reader or game input is introduced.

## New working pieces

- `scripts/npc_survey_live.py` now retains the **exact original Lua wire envelope** for every accepted advancing survey source as `frame-NN.wire` alongside the original survey result. It checks the retained byte digest against the source receipt. Earlier survey summaries without these original wire sources are intentionally **not independently replay-qualified**.
- `scripts/replay_npc_survey.py` opens the survey's original saved Lua wires, verifies each SHA-256, reruns the existing NPC schema/nonce/player/ID decoder, requires advancing source sequence and clock, checks the selected generation and two-frame confirmed IDs, and verifies the published snapshot is the last original frame. Source authenticity and world-instance identity are not established by a hash alone.
- `scripts/join_physical_nearby_npc_survey.py` reopens and validates the **original native nearby position and name reports**, regenerates the existing nearby-unit projection, then compares it with a successfully cold-replayed NPC survey. It requires the same process PID/start/build, exact self and unit IDs, bounded host observation interval, matching native/API names and nearby XYZ within explicit tolerances. Any ID/name/position discrepancy withholds the API level and relation for that unit; unknown fields stay unknown.

The join reports `apiLevelCandidate`, `apiRelationCandidate`, native distance and height difference, name and position agreement, and a refusal reason for unqualified rows. **All rows retain `combatSuitabilityStatus=unqualified`, `castAuthorized=false`, `moveAuthorized=false`**. Even when the Lua API reports `relation=hostile`, the comparison does not establish action permission, world-instance equality, path clearance, line of sight, attackability or a verified combat outcome.

## CLI use

First acquire the native nearby inventory. In **PowerShell 7**, from `C:\work\riftreader2` on verified AMD-DESKTOP:

```powershell
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\physical_nearby_units.py --expected-host AMD-DESKTOP --physical-pid CURRENT_VERIFIED_PID --radius 35 --max-names 12 --output-dir artifacts\NEW_NATIVE_NEARBY
```

The separate **RR2 NPC survey addon must actually be loaded and nonce-bound to the intended exact IDs** before `npc_survey_live.py` can produce an advancing survey. It has an existing `/rr2survey bind NONCE COMMA_SEPARATED_IDS` command. Use a fresh explicit nonce and up to 12 exact `u`-prefixed IDs taken from the native nearby report. The working addon installation, source publication and memory seed must be verified on the current process; the presence of source code or a historical capture is not proof it is active.

When those independently established prerequisites exist:

```powershell
C:\Python314\python.exe -B scripts\npc_survey_live.py --expected-host AMD-DESKTOP --physical-pid CURRENT_VERIFIED_PID --session-id CURRENT_NONCE --unit-ids EXACT_COMMA_SEPARATED_IDS --output artifacts\NEW_NPC_API_SURVEY
C:\Python314\python.exe -B scripts\replay_npc_survey.py --summary artifacts\NEW_NPC_API_SURVEY\result.json
C:\Python314\python.exe -B scripts\join_physical_nearby_npc_survey.py --nearby artifacts\NEW_NATIVE_NEARBY\nearby-report.json --npc-survey artifacts\NEW_NPC_API_SURVEY\result.json --max-gap-seconds 30 --position-tolerance 5 --output artifacts\NEW_NATIVE_API_JOIN.json
```

The API survey may require an exact same-process native scout seed. It refuses a missing/invalid seed rather than synthesizing one. Existing commands do not automatically issue the in-game `/rr2survey` bind.

A successful join is a **research/candidate** result only. The default interval must encompass the two sequential acquisitions; a stale source or changed owner refuses correlation. Source files and result destinations are never silently overwritten.

## What was verified

1. **Original physical native evidence replayed:** On build 1179, AMD-DESKTOP, PID `37676` and start ticks `639308565554559088`, independently reopening the previously captured `artifacts/physical-nearby-units-20261121-1234-p37676/nearby-report.json` and both original native source files succeeded. The report was source-hashed at `7D43A14D547629A81BC0F00D6C841D4DFF3FDACF4FC297AD82249B5DADDCFA35`, with **17 nearby units / 15 available name candidates**.
2. **Offline Lua survey source-replay tests:** **8/8 passed** without the game or a Lua installation. Synthetic same-schema originals exercised actual `npc_survey_live.acquire` wire retention plus independent replay, byte tampering, summary tampering, changed IDs and source refusal.
3. **Offline native/API join tests:** **9/9 passed**, with two original validated native JSON fixtures and two saved raw NPC Lua source frames. Tests confirm matched level/relation *candidates*, name/XYZ mismatches, wrong process/player, stale capture time, source tampering and zero action authority.
4. **Related Python regression suites:** **47/47 passed** across new replay/join, existing native context join, nearby CLI, and native unit-position/name readers.

**Current blocker:** The current physical RIFT process has **not** supplied a freshly verified, nonce-bound NPC API survey in this session. Thus **native/API level and relation live correlation remains unaccepted**. The existing `test_npc_survey_live.py` full Lua 5.1 producer test could not run under `C:\Python314\python.exe` because `lupa` is not installed; the new pure-Python source tests do run. No dependency installation, gameplay action, focus change, reload, game-memory write or other-repository edit was performed.

**Next:** Establish an advancing nonce-bound NPC survey for several current exact nearby IDs, then validate name/level/relation agreement, and finally add the independent hostility/attacker, level-delta and real response checks required by `target_selection` before any automatic encounter.
