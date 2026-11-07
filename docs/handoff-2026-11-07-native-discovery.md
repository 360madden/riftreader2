# Native discovery continuation — November7, 2026

Checkpoint12:30 Eastern. Authoritative checkout`C:\work\riftreader2`, branch
`codex/modular-foundation`. Read`AGENTS.md`, this note and the latest status.
Use PowerShell with login profiles disabled. Preserve other writers' changes;
documentation-only commit1056ff4 from the parallel runtime audit was retained.

## Current objective and policy

The five-hour goal started08:26:48 Eastern and ends13:26:48 Eastern. It is still
ACTIVE. Do not complete it early. Continue useful discovery; refinement can be
later or never. No broad validation campaign, framework or review loop is a
default follow-up. Run only checks relevant to a concrete change/failure and
use the result. This policy is durable in AGENTS/development workflow.

Root owns all live operations. Workers do static/source work only. Preserve
existing owners, exact VM/PID/start/build, freshness and STOP/release gates.
No game input, reload/rebind/restart, getter invocation, debugger/injection,
memory/refcount writes or active-reader replacement occurred in this discovery.
New casting/combat/target-selection input is not implied by the discovery goal.

## Working commands

```powershell
C:\Python314\python.exe -B scripts/sample_current_native_ability_catalog.py --lab lab1
C:\Python314\python.exe -B scripts/sample_current_native_ability_catalog.py --lab lab2
C:\Python314\python.exe -B scripts/sample_current_native_player_context.py --lab lab1
C:\Python314\python.exe -B scripts/sample_current_native_selected_target.py --lab lab1
```

Commands reacquire identities and use RR2-owned code/per-SHA guest caches.
The catalog imports repository helpers only. Each record/dictionary request
retains its128-key limit; larger sets are separate provenance-bearing chunks.
Pinned local reader binaries are required; never overwrite an earlier publish.
Game SHA is1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.

## Verified useful results

| Track | Lab1 | Lab2 |
| --- | --- | --- |
| Ability catalog |122 rows,119 name candidates,43/43 filter rows named|134 rows,121 names,54/54 filter rows named|
| Catalog interval |15.36s repository run|25.09s range-enabled run|
| Decoder/parser failures |0|0|
| Raw costs |62 typed Mana/Charge inputs,5 typed-unhandled1E2D,55 empty vectors|64 typed Energy inputs,11 typed-unhandled1E2D|
| Raw cast inputs |21 primary0650,3 secondary0678|23 primary0650,4 secondary0678|
| Self context |level41,combat byte0,target`u80000002CD0034D1`|level43,combat byte0,guarded zero target|

Sixty shared full-ID candidates agreed on compared name/timing/cost/filter
fields. Missing names have typed child key0, not decoder errors; fallback names
are not ruled out. Names come from the resident dictionary's strict locale1
record shape; three first seeds also matched the typed hot-cache text/locale.

Cooldown+94 and cast vectors+5F0/+8E8 are BASE inputs, not adjusted API values
or active cast progress. Unsupported primary cast types stay unknown. Raw range
min/max+B4/+9C has equipment/player exceptions. Condition1 membership drives
stealthRequired candidate; no positive was seen. Lab2 had eight raw condition4
entries. Effective condition4 rejects combat, but context can replace the vector.

Lab1 Charge modifier list was nonempty, so the empty-list shortcut cannot yield
final Charge amounts. Mana uses level-based Mana plus branch-dependent Wisdom/
Intelligence terms and modifiers; do not substitute displayed manaMax. Active
duration remains without a matching live object. Repeated idle samples are not
the next default step. No changed-state/API/freshness/restart claim follows.

## Receipts and commits

- Catalog/reference/profile details: [ability findings](reference/native-ability-ownership-findings-2026-11-06.md).
- Both self-context receipts and conditional guards: [player context](reference/native-player-context-candidates.md).
- Detailed prior chronology/ownership: [owner handoff](handoff-2026-11-06-owner-migration.md).
- Latest verified code commits:9e1f956 (catalog/timing),60acdfb (range/conditions),
  b875cb9 (guarded self context). Earlier decoder/native milestones are in the
  owner handoff. Commits are local; no push.

## Current work and blockers

Selected-target vitals passed on Lab1 using the EXISTING injected vitals reader
and a bounded exact-full64 target-unit lookup: target`u80000002CD0034D1`, health
candidate1224100/1224100,13.2605ms. The repository command also passed with the
cached reader. [Both receipts and limits](reference/native-player-context-candidates.md).
No selection/input; Mana/Energy unavailable by kind. Reader
E6CD3F1D0F9DD6A0072D7E3D2942C07171EB5A4B85B0025AA6FA96FF690F84BC,
117462880 bytes, under`artifacts/native-selected-target-20261107/publish/`.
No live tool handles remain at this checkpoint; do not repeat reads as a default
qualification loop or claim a stable value proves changed-state behavior.

Optional Lab2 UI corroboration was CLOSED after dependency-admission SessionError;
no image was accepted. Later status was connected/disarmed-idle with supervisor
initial cleanup verified and an existing console reservation held, not cleared.
Do not turn UI repair into a discovery prerequisite or keep retrying it.

Next useful static lead: entity-name branch order in
`artifacts/discovery-20261107-cast/unit-name-next-step.md`. It may use direct
UTF16, a type1E17 localization key, or an unresolved entity virtual method;
do not guess from the GUID prefix. Root can reuse resident dictionary decoding
only after the branch/key/owner is freshly bound. No raw unit name is accepted yet.
