# Power test — October 25, 2026

**Result:** A coordinated hands-off Light's Balm test demonstrated Power
consumption and recovery. Twelve contract-validated Lua frames contain
**100 → 89 → 95 → 100**. A responding process-memory candidate contains
**100 → 89 → 96 → 100**. This is session-level behavioral evidence, not a
qualified durable native field.

Atank is a level 45 Warrior, role `tank`. The live slot-7 tooltip identifies
Light's Balm as an instant heal costing 20 Power with a three-second cooldown.
The tooltip also describes a legendary version with nearby-enemy damage; the
reviewed scene had no selected target or visible hostile enemies. One left
click was delivered and released at **2026-10-25T21:37:11.500–11.602Z**. The
receipt shows screen position **(623,676)**, inside the reviewed slot, without
recentering. No movement keys or second cast were issued in this clean run.

Health remained **18208/18208** and Lua XYZ stayed unchanged. A heal at full
health cannot establish a changed-health field. Health-change testing remains
explicitly deferred. The typed combat field is unavailable; do not infer false.

## Evidence and interpretation

- Exact RIFT SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- PID/start: `1224` / `639285359295548343`; player `u035400012FA2D207`.
- Collector: `RR2-ValueScout-oct25-01`, SHA-256
  `5134A45352ABF3CC65F1116C623C14D650FD92FBA34609A3CC2B03A961199293`.
- Six paired rounds read 28 retained candidate-neighborhood pages, **114688
  bytes per native read**, plus bounded Lua captures. No broad rescan occurred.
- Lua sequence **49281** reports Power 89; **49282** reports 95; **49283**
  reports 100. All 12 retained frames passed the existing C# typed-wire
  inspection, with exact source and wire hashes. Their frame clocks increase
  when ordered by sequence.
- Candidate **`0x202DBECE9C8`**, `float64`: 89 at native capture start
  `21:37:12.6657313Z`, 96 at `21:37:13.2309430Z`, then 100. This address
  belongs only to the current process epoch. Its owner is unresolved: it may
  be an addon/Lua numeric copy rather than the game-owned resource field.
- Samples are sequential and non-simultaneous. The 95/96 recovery readings
  are not an atomic equality comparison. The actual minimum Power, exact
  regeneration rate and exact consumed amount were not captured; 20 is the
  tooltip cost.

The original per-round summary selected only the newest valid Lua copy and
therefore displayed six 100s. **For transient behavior, retain every distinct
validated frame and order by API sequence/time.** Offline review recovered the
89 and 95 frames from the already saved originals; no recast was needed.

The click helper's post-delivery check incorrectly required exactly y675 and
rejected y676. Both are inside the reviewed button. Preserve that failure;
the retained receipt and button bounds establish the actual location. This
check was post-delivery and must not be described as preventing wrong clicks.

## Earlier attempts and VMware recovery

The first attempt showed UI Power 88 and Lua 100 → 93 → 100 while four
suspected integer Power values stayed 100. Joey later reported interacting
with the guest during that testing, with no precise interference interval.
Those observations remain retained but are not exclusively controlled trials.
A later click was recentered to the middle of the game and produced no Power
change; it is not a valid cast stimulus. A readiness failure also withheld a
click. Do not count those as additional successful casts or use the no-cast
follow-up to reject nearby candidates.

A 24-round collector exceeded the existing 128-file packaging cap after
acquisition. Four bounded six-round archives recovered and verified the
originals without resampling. A subsequent larger inline guest command showed
`vmrun` error `bora/lib/string/str.c:443 Buffer too small` and timed out. The
precise cause is unconfirmed. Copying the script to a unique guest path,
verifying its SHA, and evaluating it through a short bootstrap worked for the
read-only baseline and subsequent captures. Reuse that route for larger
scripts; do not repeat the failing oversized inline command. No global
execution-policy changes, credential re-entry or VM restart was required.

RIFT's official [interface documentation](https://support.gamigo.com/en/support/solutions/articles/201000105477-customizing-the-user-interface)
describes optional Auto Self-Cast and ability queuing. These are settings,
not grounds to assume a cast succeeded; retain the actual Power response.

## Saved result and next work

Raw clean run: `artifacts/validation/health-scout-20261025-02/paired-power-trial-04/`.
Its transfer verified **82 original files**. Click evidence:
`artifacts/validation/resource-lua-20261025-01/power-cast-05/`.
The later read-only screenshot is `clean-power-after-01/` beside it.

Combined export: `artifacts/exports/power-clean-20261025-01/evidence.zip`,
**16 files, 3055831 bytes**, SHA-256
`EB745A358AE6C424A2266A2FB4BB9C4276901EE12A25149D268CE4C29092D197`.
It preserves the original capture archive, all validated Lua frames, the native
trace, action/release evidence, the exact-pixel failure and final controller
state. Private arm tokens are excluded. The final controller was disarmed,
idle, with no held inputs and a clear access queue.

Next: inspect the candidate's owner/layout and distinguish game-owned data
from an addon copy; derive a reusable locator before a normal full-game
exit/relaunch check. Before further UI automation, bind click intent to the
reviewed button and refuse cursor drift/recentering. No input-blocking utility
was enabled. Health-change testing and patch recovery remain deferred.
