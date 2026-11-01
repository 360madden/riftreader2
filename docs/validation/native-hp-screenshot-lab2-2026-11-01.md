# Lab-2 native HP / independent HUD screenshot — November 1, 2026

## Result

**One guarded same-process baseline matches visually; changed-state and restart qualification remain pending.**

A new exact-build, read-only native HP record and separately captured foreground RIFT HUD show **10,635 / 10,635 health (100%)** for Bolinao [AFK], level 43, Lab-2. The screenshot also visibly shows a purple **100 / 100 (100%)** resource bar, consistent with the prior Energy candidate but *not* proof of its live type or dynamic behavior. I inspected the original BMP screenshot and a derived, enlarged JPEG crop of the top-left HUD; no automated OCR is claimed.

The native sample and HUD screenshot were approximately **46.50 seconds apart**. That is same-process corroboration, not an atomic/time-aligned read or changed-state validation.

## Exact evidence

- Lab: `RIFT-Lab-2`; game PID `7012`; start ticks `639290507554340644`.
- Installed executable SHA-256: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Native HP observation: `2026-11-01T13:37:46.5355685Z`; exact type `0x2C2`; stable revision `60/60`; raw base/max `10635/10635`; candidate calculated current/max `10635/10635`.
- Native review: `artifacts/native-unit-manager/lab2/fbcc7b697ba14209aecb19d7f7628589/review.json`, SHA-256 `EBBD60F5A3C301F6A36C062B52E72229892C53F5550C08F63C26A12A3EA14A6B`.
- Screenshot timestamp: `2026-11-01T13:38:33.036003+00:00`. Exact game PID/start/SHA matched the native review; window reported foreground.
- Original screenshot: `artifacts/native-hp-screenshots/lab2/hp-20261101-1338/image.bmp`, SHA-256 `C5F14253551D9E764720BF66A0C066C871717AB2EB81CB880D98984D5E14F1DC`.
- Capture metadata: same directory `capture.json`, SHA-256 `9DCB80BFF62D215E2DFAE592B5EB26E4EB74E246C1562F1D4F2F1B519496D8B7`; capture ID `5898d550987148628eb9eebf624e0113`.
- Derived visual review files `overview.jpg` and `hud-review.jpg` live alongside the original screenshot under ignored `artifacts/`, not tracked as source files.

## Commands and safety results

| Workbridge job | Exit | Evidence |
|---|---:|---|
| `rr2-resume-lab2-guest-agent-preflight-20261101-01` | 0 | Controller and guest agent reused, connected, coordination ready, console reserved, guest disarmed/idle |
| `rr2-resume-lab2-fresh-typed-hp-20261101-01` | 0 | Exact-build/type/ownership-pinned native read-only HP record, end anchors and process rechecked |
| `rr2-resume-lab2-hp-screenshot-20261101-01` | 0 | Protected screenshot-only lease; explicit STOP confirmation and independent watchdog cleanup; `captured-after-watchdog-release` |

No movement, keypresses, macro, arm, game memory write, native getter invocation, game restart, VM restart or addon deployment was performed. The screenshot helper sends a release-only STOP as part of cleanup. Its code and offline guard tests are committed in `95ea6ed`; the related four-module offline integration run `rr2-hp-screenshot-integration-offline-tests-20261101-01` passed **104/104**, exit 0.

## Still unresolved

1. Demonstrate at least two distinct, independently time-correlated HP values under the same exact game process; unchanged 10,635 is only a baseline.
2. Correlate changed Energy values independently; a static purple 100/100 bar does not qualify Energy current-value telemetry.
3. Prove passive native freshness, a complete same-build RIFT exit/relaunch with fresh address resolution, and the separate Lab-1 sustained 480-second feedback gate. The historical Lab-1 result remains **FAIL**; no live requalification occurred here.
