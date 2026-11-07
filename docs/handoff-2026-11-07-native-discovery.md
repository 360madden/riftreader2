# Native discovery continuation — November7, 2026

Checkpoint13:08 Eastern. Authoritative checkout`C:\work\riftreader2`, branch
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
  b875cb9 (guarded self context),99d8772 (target vitals),25de12d (name seeds),
  015f784 (live-verified target position). Earlier decoder/native milestones are in the
  owner handoff. Commits are local; no push.

## Current work and blockers

Selected-target vitals passed on Lab1 using the EXISTING injected vitals reader
and a bounded exact-full64 target-unit lookup: target`u80000002CD0034D1`, health
candidate1224100/1224100,13.2605ms. The repository command also passed with the
cached reader. [Both receipts and limits](reference/native-player-context-candidates.md).
No selection/input; Mana/Energy unavailable by kind. Reader
E6CD3F1D0F9DD6A0072D7E3D2942C07171EB5A4B85B0025AA6FA96FF690F84BC,
117462880 bytes, under`artifacts/native-selected-target-20261107/publish/`.
Name-enabled follow-up preserved health but found an empty ALTERNATE string,
not a primary-direct name or selected localization key. No name accepted.
Method-address diagnostic passed: entity VT26AE5F0/slot18 method59E940, loaded
bytes match retained PE. No method invocation. Its virtual path checks entity
+1D0 type1E17 ref first, otherwise+1B8 template key via dynamic provider33E3A98
and type0274 result+ A8 name ref. Do not guess which route applies.
Completed route/position diagnostic retained stable target/entity/provider anchors:
entity+1D0 null, template key1847420318 at+1B8, provider WORD selector623.
Receipt directoryartifacts/native-selected-target-name-20261107/lab1/ddf9cd65a5a84b4289aae0cd782fddb8/.
Static trace confirms selector passes unchanged; type0274+A8 type1E17 cache-only
resolution is being implemented in a separate command. Cache miss is not absence.
Position core/caller passed18 core and8 target-focused cases and the repository
command completed13:03:12 Eastern with cached reader: XYZ7428.7246/863.526/2950.8438.
Receiptartifacts/native-selected-target-20261107/runs/lab1/c993ae87a90142e58134894ed8959750/samples.json,
SHA25612639A21472437F19326062994EBA4001A672090D59DA336CC82287123B58189.
Candidate only; no freshness/restart/action readiness.

Lab2 repository selected-target command also passed at13:06:38 Eastern: guarded
zero target produced explicit unavailable with null target position/name, rather
than substituting self values. Receipt
`artifacts/native-selected-target-20261107/runs/lab2/b28d0964730a408db1cfae1e33ae59b8/samples.json`,
SHA256`E8D240818EE567E68EB131464642D63DCCFD26C1CEEFA75BF389D8461E5721D3`.

## Resume point — requested checkpoint,13:07 Eastern

Checkpoint committed6359c38; root resumed immediately. Lab1 template-name host
operation COMPLETED successfully at13:07:15 Eastern; no active process. Command
`C:\Python314\python.exe -B scripts/sample_current_native_target_template_name.py --lab lab1`.
Fresh evidence directory
`artifacts/native-target-template-name-20261107/runs/lab1/9a6ac42b49ad4d519ae7c3cbebda5306/`.
Cache hit passed type0274 and nested1E17 checks; selector623/TLS index20,
template1847420318, localization key1290053851. Captured raw typed fallback
**Normal Practice Dummy**. Dictionary lookup missed, so locale1/API name remains
unavailable; active manager selection/decoration is not inferred. Capture span
34.713ms. Source report SHA256
`60C2053E175017C83652B7496421D5691BD404B9DA1643EDF80DB27E05AD2A14`.
The host summary exposes rawFallbackNameCandidate separately. Retained receipt
replay passed without a new capture.

New template-name sampler, command registration, host launcher and four focused
native tests are ready for the verified milestone commit. Separate published reader:
`artifacts/native-target-template-name-20261107/publish/RiftReader2.Live.exe`,
117491552 bytes, SHA256
`2390DB519546D4884E14D7B00DD78257740104808792E15B8C58F1E57F9806FD`.
It preserves fresh gated full64 target, provider selector, all-thread TLS
unanimity/epoch, composite cache and type0274/name1E17 anchors. Cache misses are
unavailable, never proof of absence. Root reviewed boundaries; four focused
native cases and host synthetic/compile checks passed. Useful live result is
verified; static follow-up is narrowing the active localization-mode branch.

Parallel workers are now complete; root retains sole live ownership. Do not
invent follow-up work to fill slots. Two additional static leads are retained:
`artifacts/discovery-20261107-cast/zero-key-name-next-step.md` (missing3/13 names
cannot be recovered from receipts lacking fallback text; all filter0), and
`artifacts/discovery-20261107-cast/cost-1e2d-next-step.md` (typed context tree
source narrowed, result semantics unresolved). No new input authority.

Optional Lab2 UI corroboration was CLOSED after dependency-admission SessionError;
no image was accepted. Later status was connected/disarmed-idle with supervisor
initial cleanup verified and an existing console reservation held, not cleared.
Do not turn UI repair into a discovery prerequisite or keep retrying it.

Next useful static lead: entity-name branch order in
`artifacts/discovery-20261107-cast/unit-name-next-step.md`. It may use direct
UTF16, a type1E17 localization key, or an unresolved entity virtual method;
do not guess from the GUID prefix. Root can reuse resident dictionary decoding
only after the branch/key/owner is freshly bound. No raw unit name is accepted yet.
Name-capable reader SHA783573AA... is under
`artifacts/native-selected-target-name-20261107/publish/`. The repository launcher
now pins position-capable reader1960292C... under
`artifacts/native-target-position-20261107/publish/` (live repository use passed).
