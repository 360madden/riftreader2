# Fresh short-window Mana reference — November 6, 2026

Two fresh bounded, read-only Lab-1 RRAPIVAL2 scans recovered advancing API
frames for the exact current game process. The selected frames identify player
`u035400012FA2D678` and independently report Mana **3980/3980** in both frames.
This is a fresh API reference baseline, not a changed-state result or native
field qualification.

The operation retained VM identity and reacquired game PID `7164`, process-start
ticks `639294897866244204`, and executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
The published reader SHA-256 was
`1C89D8B29A9A3A523D6B6A32F7F0DAC4E972454B5F4C3C3BD8F3C7F803F5E3C7`.
No game input, addon bind/reload, game restart, or VM restart occurred.

The strict existing cross-run assessor evaluated eight snapshot pairs. Six
advanced; two were blocked by stale copied frames. Its selected pair advanced
sequence `33452 -> 33472` and `Inspect.Time.Frame` `75754.46875 -> 75764.78125`.
The exact selected-snapshot gap was **9.902131 seconds**, inside the declared
15-second comparison window. Player ID and API XYZ remained stable.

`scripts/inspect_typed_resource.py` validates the exact RRAPIVAL2 v2 shape,
checks every successful snapshot chunk SHA-256, joins only contiguous bytes,
rejects malformed/incomplete frames, and exposes the selected player resource.
For the selected strict pair it returned:

| Field | Before | After |
| --- | ---: | ---: |
| Player | `u035400012FA2D678` | same |
| Mana | 3980 | 3980 |
| Mana maximum | 3980 | 3980 |

Evidence is retained under
`artifacts/native-current-reference/runs/lab1/a4a31a4e139248d3a961a3aedc4ac580/`.
The original returned archive SHA-256 is
`D67CBCE72C8B3778F2A980B2A3DFBD86683775258EB6EBB261E16ED69C89C59A`.
The before/after resource reports are `mana-before.json` SHA-256
`5215E68F444B256C57546BB6C27CEB6C86709B346E22DE40987583C43D74B770`
and `mana-after.json` SHA-256
`6A9AF291A8B0645974029166A879FA4678C9F817DBFE8E08D0CA26C68FDF12A0`.
The strict assessment summary SHA-256 is
`0502A712EC053E4428BE08D6E5226351B77A5231CE8BEBB0D82278C18D98DE2E`.

Five focused extractor tests passed, including latest-frame selection,
unavailable Mana, chunk corruption, and duplicate-key rejection. Python
compilation and `git diff --check` passed.

The prepared offline short-window assessor additionally requires strictly
increasing API sequence and `Inspect.Time.Frame`, and retains both deltas. It
validates the source report, selected snapshot and selected wire SHA-256 values,
rejects duplicate JSON keys, non-finite values and invalid snapshot time order,
and reports structured failures. Its comparison gaps are explicitly measured
from host snapshot acquisition timestamps around the native observation. The API
frame clock is not assumed to be directly synchronized with those host/native
timestamps.

This result proves fresh advancing API Mana availability for the current player.
It does not yet pair a native Mana read inside the same window. The next bounded
step is a fresh type-checked native Mana observation adjacent to an advancing API
pair, followed separately by a coordinator-owned Mana-consuming action with
before/after native and API observations. Stable 3980/3980 alone does not prove
changed-state correspondence, passive freshness, continuity, or restart recovery.
