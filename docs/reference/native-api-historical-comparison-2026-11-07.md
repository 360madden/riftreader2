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
  castingTime;40 primary profiles remain unresolved. Two typed0678 secondary
  inputs also agree. Equal values do not distinguish the actual producer path.
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

The last three parent definitions have raw078A variant candidates. **Do not
publish parent base0 as their API cooldown or select a child from this table.**
State changes, context adjustments and variant selection remain possible causes;
the captures are over an hour apart. Soul Recall also demonstrates a nonzero
base/output difference. None of the projected54 Details contains currentCooldown
Begin/Duration/Remaining/Expired/Paused fields; absence is not an observed zero.

Complete comparison and exact records:
`artifacts/rre-peer-reference-20261107/catalog-comparison.json`;
packet verification:`artifacts/rre-peer-reference-20261107/verification.json`.
RRE repositories and owners were read-only here. Keep this independent addon
reference separate from native and derived evidence. The next useful comparison
is a same-epoch exact-ID observation within an authorized ownership window,
not a general selector reconstruction or another broad test campaign.
