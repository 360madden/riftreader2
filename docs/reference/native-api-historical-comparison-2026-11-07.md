# Historical native/API comparison — November7,2026

**Different capture times; no current parity, freshness, learned-membership or
variant-selection acceptance.** This compares retained exact-ID records after
Joey explicitly authorized cross-chat coordination. No game/API call was made.

RR2 Lab2 native catalog:134 distinct IDs,54 nonzero C9 filter candidates,
observations18:27:48.466..18:28:11.714Z. Source
`artifacts/native-ability-catalog-20261107/runs/lab2/c89e9f59c2fc4e88a14eea18bf4e34ff/catalog-summary.json`,
SHAED675A6C9A74A83302FFAE46722ECF399431FC6C1185B6B7B0FDB4FA3D3D9841.
All11 listed evidence hashes and raw/summary ID/filter/timing/variant inputs
matched. Name candidates were compared as retained, not independently redecoded.

RRE seq5:54 projected ability Details, manual image clock14:38:30 Eastern,
wire snapshot19:43:07.529..626Z. Source
`C:\work\rre\artifacts\sc622-live-bridge-20261107-1428\wire-seq5\document.json`,
SHAD69414C1B1C2B3E79BCF949D9FB1AE0ABA5FE9E564BD8F09A6026EBD0C98B9D0.
Peer packet SHA isD26FE63D90BD8D6B1A71E18C7DBD27B9192DF01A4BB4F1DD98B4A90081CE8420;
all7 packet source hashes and self/session/sequence/field-presence counts matched.
Both sources identify Lab2 PID9752/start639294897826627677 and game
SHA1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.

## Useful observations

- The54 public IDs EXACTLY equal the54 native nonzero-filter candidate IDs.
  All54 available name candidates match. The native catalog has80 other IDs.
  This supports that exact snapshot filter path; it does not prove durable List
  semantics, learned ranks or that cached records are public abilities.
- Of54 matched IDs,13 typed single-entry0650 primary millisecond inputs agree
  numerically with a present castingTime. One such typed input has no API
  castingTime;40 primary profiles remain unresolved in that primary-only
  classification. Two typed0678 secondary inputs also agree. Four additional
  variant parents have compatible typed child inputs, so all19 present
  castingTime values have at least one compatible input across these captures.
  Equal values do not select a child or establish the actual producer path.
- Using float32(milliseconds)*float32(0.001),17 present API cooldowns agree with
  native parent base inputs,4 differ,33 API cooldown fields are absent.
  Decimal serialization precision and the comparison method remain explicit;
  this is not a bit-exact double claim. Exact-arithmetic results are also retained.

| Exact-ID name | Captured API cooldown seconds | Parent base seconds |
| --- | ---: | ---: |
| Soul Recall |3000.000244|3600.000244|
| Empowered Shot |8|0|
| On the Double |40|0|
| Divert Rage |60.0000038|0|

The last three parent definitions have raw078A variant candidates. Their API
cooldowns versus the ordered child base inputs are Empowered Shot 8 vs 8/8,
On the Double 40 vs 0/40, and Divert Rage 60.0000038 vs
60.0000038/60.0000038 seconds, using float32 conversion. These are compatible
raw inputs, not proof of the selected child or producer. **Do not publish parent
base0 as their API cooldown or select a child from this table.**
State changes, context adjustments and variant selection remain possible causes;
the captures are over an hour apart. Soul Recall also demonstrates a nonzero
base/output difference. None of the projected54 Details contains currentCooldown
Begin/Duration/Remaining/Expired/Paused fields; absence is not an observed zero.

The ordered variant receipt
`artifacts/native-variant-definitions-20261107/runs/lab2/fcb2b493233144cbbcc0d8af3fe87807/summary.json`,
SHA256 `54C9E1DD88A181435A9476775BC87691B3535E0669482A3515850FE0E1CD3D51`,
and all10 listed evidence hashes matched. All16 child records matched raw
receipts; all8 ordered parent vectors matched before/after receipts. Variant
observations span18:31:07.104..18:31:25.036Z, well before the API capture.

Complete comparison and exact records:
`artifacts/rre-peer-reference-20261107/variant-comparison.json`;
`artifacts/rre-peer-reference-20261107/catalog-comparison.json`;
packet verification:`artifacts/rre-peer-reference-20261107/verification.json`.
RRE repositories and owners were read-only here. Keep this independent addon
reference separate from native and derived evidence. The next useful comparison
is a same-epoch exact-ID observation within an authorized ownership window,
not a general selector reconstruction or another broad test campaign.

## Range modifier tag predicate

The bounded static check of the mode-0 modifier call establishes the caller's
actual argument mapping: definition tags at `+0x588` must satisfy **ANY** of
nonempty modifier tags at `P+0x1E0`, **ALL** of nonempty tags at `P+0x2B0`,
and be **DISJOINT** from nonempty tags at `P+0x248`. The groups are combined
with AND after a direct-key miss; a direct-key match bypasses these tag checks.
The all-tags helper compares each untransformed DWORD. See the bounded branch
and ABI evidence in
[range-tag-predicate-check.md](../../artifacts/discovery-20261107-cast/range-tag-predicate-check.md).

The initial offline **0/24** interpretation swapped the ALL and DISJOINT
inputs and is superseded; it was not a live result. The corrected comparison
receipt and reproducer are pending and should be linked here when available.
The meaning and effect of modifier flag `+0x33` remain unresolved. These
separately timed historical API and native captures do not establish adjusted
range parity or changed-state behavior.

## Corrected Lab 2 range-tag comparison

The offline comparison of 24 captured parent definitions against the captured
mode-0 modifier now yields 13 predicate-pass candidates. The correct mapping is
ANY for the +0x1E0 group, ALL for +0x2B0, and DISJOINT for +0x248; the actual
ALL group was empty. One other key takes the special range branch. The earlier
0/24 result used the wrong argument mapping and is explicitly preserved as
superseded. See `artifacts/discovery-20261107-cast/range-applicability-comparison.json`
and `range-tag-predicate-check.md` in that directory.

These cross-phase parent-record results do not identify selected variants,
resolve flag33 scaling, or establish final adjusted range, current API parity,
changed-state freshness, or restart qualification.

The fresh Lab 2 energy-input capture has a flag value of zero on 18 rows and one on
2 rows: Hasted Shot and Head Shot. In the historical comparison, 11 raw energy
inputs agreed with the API values and 9 differed. Mode-2 adjustment and ability
selection remain unresolved; these counts do not establish effective costs or
same-epoch API parity. Sources: the hashed range/input receipt
`artifacts/native-range-inputs-20261107/runs/lab2/a740d2e7fa7249c7bc7382228509f8fd/samples.json`
(SHA256 `E1F49185CEF52ADD7D744116EB1576C892B4CBB579E43D6E70A244B07C7CB5B2`)
and `artifacts/rre-peer-reference-20261107/cost-range-comparison.json`.

The separately captured typed 0E29 range configuration has minimum 5, maximum
105, and special key `1871006214`; Toggle Auto Attack takes the special range
path rather than the ordinary mode-0 adjustment path. Receipt:
`artifacts/native-cooldown-modifiers-20261107/runs/lab2/b05d568527a94122b8d69d7e298f2b89/samples.json`
(SHA256 `0DA2C0FB2CEE9938008B990A3E0CE2F39EB0A007FB0CDD7AC2C480221127A7B6`).
These are cross-phase candidate observations, with variant selection and final
range still unqualified.
