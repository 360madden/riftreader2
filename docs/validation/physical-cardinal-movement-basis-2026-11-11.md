# Physical RIFT empirical movement basis: W/S/Q/E vectors and later-facing forecast

**Date:** November 11, 2026 (EST). **Host:** independently verified AMD-DESKTOP, physical RIFT x64. **Repository:** `C:\work\riftreader2`, `codex/modular-foundation`. **Mode:** offline replay of previously completed C# helper receipts; **no new gameplay input**.

## Practical discovery

The actual W/S/Q/E displacement vectors form an almost perfectly cardinal pattern. The W/S directions are opposite, Q/E are opposite, and W/Q are perpendicular to within 0.03 degrees. S moves at about half forward speed in these samples, while W/Q/E speeds are close. The later W sample changed direction by 17.435 degrees but maintained essentially the same speed.

All samples have the same historical physical process PID **44888**, process-start UTC ticks **639299470183328173**, current-build executable SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, and player unit key **239816685251645959**. These historical identifiers must be reacquired, not reused for future live operations.

| Command | Recorded time (UTC) | Actual hold | Observed planar speed (units/ms) |
| --- | --- | ---: | ---: |
| W forward, earlier | 13:53:20 | 770.2 ms | 0.006039520 |
| S backward | 14:15:13 | 514.0 ms | 0.003013489 |
| Q strafe left | 14:15:21 | 519.9 ms | 0.006016680 |
| E strafe right | 14:15:28 | 511.1 ms | 0.006016918 |
| W forward, later | 14:54:05 | 408.2 ms | 0.006045615 |

### Pairwise native-displacement geometry

| Comparison | Candidate angle | Candidate speed ratio (first/second) |
| --- | ---: | ---: |
| Earlier W vs S | 179.995803° | 2.004162 |
| Earlier W vs Q | 89.977228° | 1.003796 |
| S vs Q | 90.018574° | 0.500856 |
| Q vs E | 179.997668° | 0.999960 |
| Earlier W vs later W | 17.435280° | 0.998992 |

**Important:** the earlier W reading precedes S by **1311.6 seconds**. S/Q/E follow at **7.3/5.7-second** gaps. The later W follows E by **2316.5 seconds**, after other turning tests. Although this cardinal pattern strongly suggests the expected movement semantics, the samples **cannot prove continuous facing, game input consumption, zone continuity or that there were no intervening manual inputs**.

## New reusable retrieval/analysis capability

`scripts/physical_move_basis.py` reads the original five helper JSON receipts with `scripts/physical_move_key_calibration.py`, checks source integrity, key/identity, sample chronology and unique origins, and produces a candidate basis comparison. It never opens a game process or requests UI control.

The importer now uses the **exact observed floating-point hold duration** to calculate per-millisecond velocity. Earlier `*-validated.json` vectors from a previous implementation used rounded integer holds; prefer the new output `artifacts/physical-move-basis-wsqe-nov11-2026-v2.json` derived from the unchanged raw receipts.

Reproduce from the RR2 repository root in **PowerShell**:

```powershell
C:\Python314\python.exe scripts/physical_move_basis.py `
  --forward artifacts/physical-move-key-receipt-w750-20261111.json `
  --backward artifacts/physical-move-key-receipt-s500-20261111.json `
  --left artifacts/physical-move-key-receipt-q500-20261111.json `
  --right artifacts/physical-move-key-receipt-e500-20261111.json `
  --later-forward artifacts/physical-move-key-receipt-w400-20261111.json `
  --out artifacts/physical-move-basis-new-unique-output.json
```

The optional **later-facing reprojection** rotates the earlier S/Q/E velocity vectors by the difference between the early and late W direction and scales by the later W speed. It only emits an estimate if the earlier sample vectors are roughly cardinal and the later forward direction shift is no more than 45° with a plausible speed ratio. Current example: later Q is *predicted*, not measured, at X **-0.000750637**, Z **+0.005975790** units/ms. This requires a future independent later-Q test before operational use.

All outputs explicitly set `navigationEligible=false`, `movementEligible=false`, `headingQualified=false`, `sameFacingConfirmed=false`, `gameResponseVerified=false`. The predicted motion is not an authority to issue input, and long-hold velocities may not scale linearly to short movement pulses.

## Additional historical actor-matrix evidence

Reviewing **19** saved physical actor-pose captures from the same player/component revealed three separate, repeatable candidate angles: **111.882333°** in earlier captures, **79.719340°** at 10:14 UTC Nov 11, and **10.228062°** in later captures. Same-epoch historical changes exist, but captures were not tightly aligned with A/D key holds. These are *not measured turn rates* or validated body orientation.

## Verification and follow-up

- Real full basis replay: `rr2-physical-basis-real-reprojection-v2-20261111a` completed successfully and wrote `artifacts/physical-move-basis-wsqe-nov11-2026-v2.json`.
- Focused offline checks: **31/31 pass**, including chronological/pinned identity refusal, duplicate/incorrect key, implausible input reports, geometric properties, and conservative later-facing reprojection. No gameplay input was sent.
- **Next productive live experiment when eligible:** pair a W measurement with native actor pose, then Q and E at the *same measured facing*, with short bounded pulses and independent screenshots. Compare the new Q/E against the calculated later-facing candidate. Confirm body/camera angle separation before using absolute yaw in steering.

Source evidence: [real RR2 W/Q/E receipt replay](physical-wqe-helper-receipt-calibration-2026-11-11.md), [A/D visual turn verification](physical-ad-turn-visual-verification-2026-11-11.md), and [the combined C# helper report](rr2-physical-move-key-helper-combined-report-2026-11-11.md).
