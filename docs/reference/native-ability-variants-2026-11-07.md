# Native ability variant references — November7,2026

The formerly unknown primary vtable283E6C0 belongs to type078A. Its runtime
primary-duration adapter returns+0.0 when that descriptor remains selected;
this does NOT describe duration/cooldown of a different selected variant.
The object contains ordered qword references at+18/+20. Each type0061 child
provides a candidate ability key at DWORD+18. Player/target eligibility and
score branches select a winner; no winner is inferred from this vector alone.

Exact-build passive profiles (RVAs; game SHA1935A05C...F20A4BE8):

| Type | Object VT / getter | Initialized descriptor / VT / type method |
| --- | --- | --- |
|078A|283E6C0 /17BD530|342C310 /2845BD0 /17DBA60|
|0061|2CDE8F0 /229B4B0|359F390 /2CE8820 /22C1850|

`sample-current-ability-records --include-variants true` now exposes bounded
raw vectors. It reads the FIRST primary reference even when the outer vector
has more than one entry. All-thread TLS/epoch, registry, exact type and consumed
byte checks remain. Order, duplicate keys, null and unverified children remain
explicit. Unknown primary type is not classified as nonvariant. Maximum64 refs;
no getter, initialization or refcount calls. Nine focused cases passed.

## First live result —13:26 Eastern

The repository catalog captured all six expected Lab1 parents, each with TWO
type0061 keys: Raging Storm, Blight, Radiant Spores, Ride the Wind, Bloom and
Life Leech. All twelve references were typed candidates. The complete catalog
retained122 rows/119 name candidates/all43 nonzero-filter rows named, zero
decoder failures,16.224062s between its first/last observations. These separate
chunks/observations are not atomic or freshness-qualified.

Receipt`artifacts/native-ability-catalog-20261107/runs/lab1/b4975f0021344082b8802e174cae155c/catalog-summary.json`,
SHA256`0155EDCFBA158A09F22D69EC04E0844A7FE1856095EB012119AAFBA4D4B3B643`.
Reader117503840 bytes, SHA256
`B56216935082462AF9B381EC37C84D83E74B35FBE97BAD515ADCB63DA8C39D62`,
at`artifacts/native-ability-variants-20261107/publish/`.

Next useful observation resolves those possible keys to resident0051 definitions,
names and raw timing, with fresh epoch and ordered parent-vector rechecks. Cache
misses are not absence, raw filter is not learned membership, and referenced
variants are not independently selected winners. Static selector evidence:
`artifacts/discovery-20261107-cast/variant-primary-next-step.md` and
`artifacts/discovery-20261107-cooldown/variant-selection-next-step.md`.
