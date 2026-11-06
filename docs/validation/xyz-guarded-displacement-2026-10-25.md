# XYZ displacement with the guarded movement helper, October 25

**Result: `candidate-motion-consistent`.** The existing V21 controller issued
one authorized 100 ms W pulse between CLI native/Lua captures. Native displacement
was **0.6129299056 game units**; Lua displacement was **0.6138752290**.

| Measurement | Native | Lua |
| --- | --- | --- |
| Delta X | -0.609375 | -0.6098632812 |
| Delta Y | 0 | 0 |
| Delta Z | 0.0659179688 | 0.0700683594 |

Maximum displacement residual was **0.0041503906 units per axis**, below the
existing 0.04 limit. Maximum endpoint residual was **0.0048828124**, below 0.02.
Native/Lua acquisition separation was **0.326 seconds before / 0.303 after**.

## Observed sequence

- Fresh status verified the same VM and game: RIFT PID **1224**, start ticks
  **639285359295548343**, executable SHA
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
  The existing corrected reader/profile passed their unchanged hash checks.
- CLI baseline completed three stable native reads, an independent 816-byte
  pointer capture, and a bounded Lua scout. Native pointer completion was
  **17:39:25.960763 UTC**. A fresh controller screenshot was reviewed: game
  foreground, open ground ahead, no active text entry or blocking dialog.
- Through the existing access queue and sole V21 controller, one fresh arm
  permitted **one** requested 100 ms W pulse. The guest receipt recorded key-down
  at **17:39:55.5596131 UTC** and key-up at **17:39:55.6710402 UTC**:
  approximately **111.427 ms between recorded insertion events**. Delivery and
  release succeeded; no cancellation, target loss or uncertain state was reported.
  These are Windows insertion events, not exact RIFT input-consumption times.
- CLI after-capture completed three stable native reads and independent pointer
  and Lua acquisition. Native pointer completion was **17:40:03.980280 UTC**.
  Both scouts explicitly stopped at the 512 MiB budget (`partial /
  byte-budget-exceeded`), each retaining three complete 28 KiB snapshots.
- All **9/9** cross-phase strict Lua comparisons advanced. The newest pair
  selected sequences **21218 → 21293**, same player `u035400012FA2D207`.
  The unchanged motion reviewer accepted that pair with its default gates.
- Both guest archives matched transferred length/SHA; all **38 extracted files**
  matched their member sets and hashes. Native owner stayed `0x202BA8B1480`.
- The temporary guest credential session closed normally without saving guest
  credentials. Final status at **17:40:53 UTC** showed the same target, V21
  ready/connected and sole owner, guest disarmed/idle and no held inputs. The
  access queue had no holder or outstanding requests; this trial was succeeded.

Originals, screenshot, action/release receipt, transfer receipts, all comparisons
and derived review are in
`artifacts/validation/xyz-guarded-displacement-20261025-01/`.
Portable export: `artifacts/exports/xyz-guarded-displacement-20261025-01.zip`.
Private arm/access tokens are excluded from the export.

This adds a recorded helper press/release to the preceding manual-movement proof.
It does not establish speed, continuous tracking or precise causal input timing.
No new game restart or patch recovery occurred. ChatGPT Computer Use remains
deferred; the separately authorized guarded helper was used under its existing
identity, screenshot, exclusive-access and release checks. No production code
changed; validation was the actual bounded trial, strict offline reviewers,
archive integrity checks and documentation whitespace check.
