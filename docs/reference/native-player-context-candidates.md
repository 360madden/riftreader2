# Native self target, level and combat candidates

Updated2026-11-07 at12:14 Eastern. Exact game SHA256:
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

Use `python scripts/sample_current_native_player_context.py --lab lab1|lab2`.
The read-only command reacquires VM/game identity and uses a separate SHA-specific
guest cache. Native command: `sample-current-player-context --pid N
--start-ticks N --output PATH`. No getter, initialization, refcount update,
game input or action-preflight integration is performed.

## Observed cases

| Target | Numeric level candidate | Raw combat byte | Target-key candidate | Native acquisition |
| --- | ---: | ---: | --- | ---: |
| Lab1 |41|0 / false|`u80000002CD0034D1`|9.375ms|
| Lab2 |43|0 / false|zero key|10.957ms|

Lab1 receipt:
`artifacts/native-player-context-20261107/runs/lab1/22accb18dddb400d99bc0e411d437f73/samples.json`,
SHA256`EBEEBC9410C6AF405E1ABFD3F705CD4222A431FE6D796DD7B27115C5B7462252`.
Lab2 receipt:
`artifacts/native-player-context-20261107/runs/lab2/8f1837b51d774559b6af20d934a1bca0/samples.json`,
SHA256`C8A825A1ACBB52C2EAEE019BF1A2651743A2B8208E7214A5DD1AC2566AA4732A`.
Each has its own PID/start/module/player identity. These are two independent
states on different players, not a controlled target change or combat transition.

## Ownership and branch guards

The existing exact-build player lookup resolves self key/entity and health
component H using selector RVA2F57850. The reader verifies `[H+10]==entity`,
the player-system self key and cached entity, then owner O=`[H+40]` with the
initialized0294 fingerprint: objectVT2927448/getter19D21E0,
descriptor34731B0/VT2929BD0/getter19F4D60. These are module RVAs.
All consumed bytes and lookup ownership are reread; final process validation
precedes publication. The read budget is2MiB.

Combat is BYTE`O+19D`, nonzero=true. Zero is a false predicate; the API builder
can omit the combat field rather than explicitly publishing false.
Raw level is signed DWORD`O+100`. Selector RVA2F58270 absent or its table slot
null permits the numeric getter path. A matching cached self context at
system+400==H additionally supports the numeric presentation candidate. A
nonnull alternate component remains unavailable; the API can separately show`??`.

Target fallback is QWORD`O+20`. This is NOT an unconditional selected-target
field. Selector RVA2F582E0 is distinct from the level selector, and its non-FF
slot immediately selects the fallback. With FF, absent/null selection component
(selector2F57260) also selects it. Otherwise both coherent reference pairs at
selection+280/+288 and+290/+298 must be null. The reader then requires a readable
state at`[H+320]+40`: states outside6..11 select fallback; states6..11 also
require a null reference at selection+2A0/+2A8. Unresolved/active/incoherent
override paths retain only the raw fallback and publish no target-key candidate.
A guarded zero key remains a zero observation. Nonzero GUIDs are lossless uint64
and formatted as16-digit unit IDs; Lab1's key exceeds signed int64.

Nine focused native guard cases passed. Host checks accepted the retained Lab2
receipt and rejected mismatched identity and unresolved-target leakage. The
repository command then completed the independent Lab1 live read. No full-suite
or changed-state/API/restart qualification is claimed.

Reader117450592 bytes, SHA256
`3424206628DC6ABF4E22E1EF16A0653E187618FB3BABE8DF04FF655F1B7CBE9C`,
at`artifacts/native-player-context-20261107/publish/`. Existing active readers
and control ownership were not replaced by this sampler.

## Already-selected target vitals —12:30 Eastern

`python scripts/sample_current_native_selected_target.py --lab lab1` now resolves
the exact guarded target key through the unit-manager hash table and reuses the
existing vitals reader's caller-supplied ownership callback. The default self
vitals reader was not changed. Full64 key comparison, tagged chains, target
health-component back-reference, typed fields and self/target rechecks bind
the nested values. An unresolved/zero target does not produce target vitals;
a target change rejects the capture. No target selection or cache writes occur.

The first Lab1 capture returned target`u80000002CD0034D1`, health candidate
1224100/1224100, in13.2605ms total. Mana/Energy were explicitly unavailable for
its kind. Receipt:
`artifacts/native-selected-target-20261107/runs/lab1/d26d36a5496e4c91b58ff0c3b10c351e/samples.json`,
SHA256`307EDA0EF3086A0EDB21CB2AD15772662F9B481802B92E2B67E89818329B7985`.
The repository command independently passed using the cached reader:
`artifacts/native-selected-target-20261107/runs/lab1/860f7c9e8fe546c2b8d0365e7dba4bfc/samples.json`,
SHA256`9431FF5CA79A2AFC62153C9B4652D04236A1B2CF411207BE4BA2CD07CEFD9A27`.
Stable values across these reads are not changed-state or passive-freshness proof.

Five focused lookup/gate cases passed. Host validation accepted the retained
report and rejected a nested self-key substituted for the target. Reader
117462880 bytes, SHA256
`E6CD3F1D0F9DD6A0072D7E3D2942C07171EB5A4B85B0025AA6FA96FF690F84BC`,
at`artifacts/native-selected-target-20261107/publish/`. No action preflight uses
these candidates. Selected-target names remain a separate uncaptured seed.

## Target name seeds —12:46 Eastern

Name-enabled follow-up at12:46 Eastern: ordered bounded UTF16/localization/virtual
seeds were added without invoking methods. Eight focused cases passed. Lab1's
receipt `artifacts/native-selected-target-20261107/runs/lab1/88de2bc970e749c5ad52e4d9d8d54240/samples.json`
(SHA256`2CEE76E4B0B9A01526AFD674169A1A7774B6CEF0A6729BC1C44CFD4DF50DB3F9`)
preserved health but returned`branch=alternate`, `status=empty-unresolved-fallback`.
No name accepted. Capture entity VT+18 for static analysis; do not call it or
bypass observed branch order. The source primary-direct empty case is different
and does not fall through to localization. Static trace is in
`artifacts/discovery-20261107-cast/unit-name-next-step.md`.
Name-capable reader117471072 bytes, SHA256
`783573AAE552AC5E6BC6977929B4BEBE88A70908E9F0F1E663F550808662597B`,
at`artifacts/native-selected-target-name-20261107/publish/`. The repository launcher
previously pinned it. Eventual text remains a base/locale1 candidate, with API decoration
and language unverified.

## Selected-target position —13:03 Eastern

The repository selected-target command now also reuses the position reader with
an injected exact-target owner. Position selector2F588A0 must resolve on that
same entity and its component+10 must point back to the entity. Missing position
is explicit and does not substitute self XYZ. Target/epoch/consumed bytes are
rechecked. Eighteen position-core and eight target-focused cases passed.

Lab1 returned target`u80000002CD0034D1`, cached XYZ candidate
`7428.7246,863.526,2950.8438`. Receipt:
`artifacts/native-selected-target-20261107/runs/lab1/c993ae87a90142e58134894ed8959750/samples.json`,
SHA256`12639A21472437F19326062994EBA4001A672090D59DA336CC82287123B58189`.
Position interval18:03:12.4428152Z–18:03:12.4432145Z. Reader SHA256
`1960292C6227F8E14C20050EF73FF67E43003F9336D9F93E76AD1CE2591A0046`,
117475168 bytes at`artifacts/native-target-position-20261107/publish/`.
The launcher pins that reader. Cached XYZ semantics, passive freshness and
restart remain unverified; no distance/action readiness is inferred.

The completed independent name-route diagnostic retained target/entity/provider
anchors: entity+1D0 is null, entity+1B8 key1847420318, provider33E3A98 selector623.
Receipt directory`artifacts/native-selected-target-name-20261107/lab1/ddf9cd65a5a84b4289aae0cd782fddb8/`.
Static trace passes that WORD unchanged to the common composite cache. A hit
requires type0274, then+A8 type1E17 name reference. No getter was called and no
name text has been accepted. A cache miss does not imply template absence.

## Optional UI comparison stopped

The first Lab2 screenshot attempt was rejected before admission because its
output path was outside the helper's canonical directory. The corrected attempt
stopped during dependency admission with SessionError after30.26s, before capture
or a screenshot lease: `artifacts/e2e-latency-20261106/lab2-context-1794071148899/run-failure.json`.
No image or UI agreement was accepted. No accepted recovery/task receipt was
retained. Later read-only status showed connected/disarmed-idle, supervisor
initial cleanup verified and an existing console reservation held; it was not
cleared. Do not turn optional screenshot recovery into a discovery prerequisite.

Static source details are retained in
`artifacts/discovery-20261107-cast/player-context-triad-next-step.md`.
The raw definition condition4 consumer uses the same combat getter: when its
EFFECTIVE vector contains4 it rejects nonzero combat. Context can replace the
definition vector; raw4 alone is not overall eligibility. See
`artifacts/discovery-20261107-cast/ability-condition-next-step.md`.
