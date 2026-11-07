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

Independent Lab2 repository run completed13:28 Eastern: all eight expected
parents each had TWO typed0061 keys (sixteen references). Parents: Call:
Razorbeast, Empowered Shot, On the Double, Divert Rage, Cadence, Ace Shot,
Splinter Shot, Deadeye Shot. Catalog134 rows/121 names/all54 filter rows named,
zero decoder failures,23.247498s span. Receipt
`artifacts/native-ability-catalog-20261107/runs/lab2/c89e9f59c2fc4e88a14eea18bf4e34ff/catalog-summary.json`,
SHA256`ED675A6C9A74A83302FFAE46722ECF399431FC6C1185B6B7B0FDB4FA3D3D9841`.
Different VM/game epochs were independently checked; no addresses were copied.

## Referenced definitions resolved —13:30–13:33 Eastern

The repository follow-up command is
`python scripts/sample_current_native_variant_definitions.py --lab lab1 --catalog ABSOLUTE_CATALOG_PATH`.
It reuses the same reader/cache, requires the source VM/game epoch, and rechecks
complete ordered parent vectors before AND after fresh definition/dictionary
capture. Lookup deduplication preserves original relationships and holes.
No variant is labelled selected or learned.

Both runs resolved every referenced key to type0051 and a name candidate:
Lab1 twelve/twelve, Lab2 sixteen/sixteen. Every referenced definition had raw
filter0; parent membership/filter must not be transferred to those children.
The Lab2 run included DWORD keys above signed-int32 range without truncation.

| Pair or parent | Captured raw timing inputs |
| --- | --- |
|Legendary Blight / Blight|Base cooldown8000/30000ms|
|Legendary Bloom / Bloom|Both primary0650 input2000ms|
|Legendary Life Leech / Life Leech|Both primary0650 input1500ms|
|Legendary Raging Storm / Raging Storm|Both secondary0678 input4000ms|
|Call: Razorbeast|First primary0648 zero-path/cooldown30000ms; second primary0650 input8000ms|
|Splinter Shot|First primary0648 zero-path; second0650 input1500ms|
|On the Double|Base cooldown0/40000ms|

Zero-path does not by itself establish an instant cast; context and secondary
selection remain distinct. Second reference is fallback ONLY when no immediate
success and no scored row remains. False status2 or7 can enter scoring; minimum
finite score wins, first on ties. Last-slot null/unverified does not scan backward.

Receipts:

- Lab1`artifacts/native-variant-definitions-20261107/runs/lab1/f7635b463e71438e84735c4946f8e2db/summary.json`,
  SHA256`77F54062452AE537AC5DDA8E8AF9DCD90AC08B933FF3681F96FC3CFF941D941B`.
- Lab2`artifacts/native-variant-definitions-20261107/runs/lab2/fcb2b493233144cbbcc0d8af3fe87807/summary.json`,
  SHA256`54C9E1DD88A181435A9476775BC87691B3535E0669482A3515850FE0E1CD3D51`.

Next minimal eligibility fields: signed required level0051+20, actual effective
level (not displayed level), and earlier special-key/mode5/role exceptions.
An above-level first row can then be proven non-scoring; the two-key selector's
only normal return is second. No such exclusion is currently established.
Trace:`artifacts/discovery-20261107-cooldown/variant-eligibility-next-step.md`.

Next useful observation resolves those possible keys to resident0051 definitions,
names and raw timing, with fresh epoch and ordered parent-vector rechecks. Cache
misses are not absence, raw filter is not learned membership, and referenced
variants are not independently selected winners. Static selector evidence:
`artifacts/discovery-20261107-cast/variant-primary-next-step.md` and
`artifacts/discovery-20261107-cooldown/variant-selection-next-step.md`.
