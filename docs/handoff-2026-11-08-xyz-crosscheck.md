# Retained Lab2 native XYZ vs RRE API cross-check — 2026-11-08

Offline comparison only. **Close numerical correspondence, NOT contemporaneous equality or freshness qualification.** No live test, guest/game/controller access or source-evidence edits.

## Exact common identity

Lab2 PID `9752`, raw process-start ticks `639294897826627677`, executable SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. Earliest/latest native reviews and RRE API both identify self unit `u035400012DFEB5BC` (API: Bolinao).

All **16 matching-epoch** files among 25 inspected `artifacts/native-unit-manager/lab2/*/component-values.json` decode primary `+0x48/+0x4C/+0x50` and secondary `+0x88/+0x8C/+0x90` identically, from component `0x1B0793AEDC0`.

| Axis | Native float32 | RRE API | Native − API | Float32 ULP delta |
| --- | ---: | ---: | ---: | ---: |
| X | 7183.560546875 | 7183.56005859375 | +0.00048828125 | +1 |
| Y | 820.78961181640625 | 820.78997802734375 | −0.0003662109375 | −6 |
| Z | 3156.038330078125 | 3156.0400390625 | −0.001708984375 | −7 |

Euclidean difference **0.0018147056576316536 raw coordinate units**; no physical-unit claim. Native bits `45E07C7C/444D3289/4545409D`; API bits `45E07C7B/444D328F/454540A4`. This is not exact float32 equality and not merely SavedVariables decimal formatting.

## Time separation

Native completion range on November 7: **12:53:58.7607127Z–15:35:34.5868847Z**, unchanged across 2h41m35.8261720s. RRE sequence10 snapshot completed **22:16:05.0512972Z**: **6h40m30.4644125s after latest**, 9h22m06.2905845s after earliest native capture.

RRE screenshot/publication binding observed **22:15:34.552796Z**, 6h39m59.9659113s after latest native capture. Binding/snapshot timestamps are not exact Lua `Unit.Detail` timestamps; actual cross-source temporal skew is unknown.

## Reproducible sources

Paths below are rooted at `C:\work\`. SHA256 values were returned by current reads/file-info. The sibling [machine report](handoff-2026-11-08-xyz-crosscheck.json) retains all 16 native paths/hashes/times.

| Source | SHA256 |
| --- | --- |
| `riftreader2/artifacts/native-unit-manager/lab2/001cf7a517da4dc38971a0041e1f05b8/component-values.json` | `60dd6cde1e81c4a8ddefecdd9c7d81191bfb2010d0739d6e8ac0ddfb6ab0d600` |
| Same directory `review.json` | `38292bdb6d178b73c99636a14e6eb51a8aa919df8e8f36cac70f9d660c238c95` |
| `riftreader2/artifacts/native-unit-manager/lab2/714ab962c2e4487c85fe79f8d481ab6f/component-values.json` | `6d9170e1f6e8478d5b9f7344f4480a6900a03a13b7406869dab828d430879533` |
| Same directory `review.json` | `77978dd00f4fa7f8660bda2ce7299c8c8e79aa25afedaacf2f740dc63978fc6f` |
| `rre/artifacts/sc625-live-adapter-trial3-20261107-1714/observation.json` | `7575c604c3689ada4dd0d7b96067cdca4ba6100fd2516136ae156e20beae3dec` |
| Same directory `binding.json` | `f64a9262be1649f4e4d4af03bfdd390bce8cde9c9e846b8cd40010f0e891c893` |
| Same directory `acquisition/snapshot.json` | `84fc04eaac672bf5e3e087a02c80ac03d3a1576979c2b8b1c84162ef00609f96` |

Earliest/latest native reviews resolve manager `0x1B032669F80`, player system `0x1B0257806A0`, component table `0x1B066B8B4E0`, position selector34/slot6 and stable sampled inputs. Eleven matching-epoch reviews explicitly contain the matching self unit ID; do not generalize independent ownership qualification to every raw sample. Directory `6391975fd6ff4781afcbd924eeadc4b2` lacks `review.json`.

## Limits and practical use

Sequential reads are non-atomic/ABA-possible; on-disk executable SHA is not a loaded-module hash. Constant native values prove neither stationary gameplay nor advancing cache freshness. Small mismatch causes (motion, interpolation, distinct source/transform) remain hypotheses. No world-frame, passive-freshness, writer-execution, changed-state or restart promotion follows.

Reuse this source-hashed historical pairing and quantified mismatch for the next focused investigation; do not repeat discovery of the API reference or report cached values as current. No new runtime dependency or live-test permission is implied.
