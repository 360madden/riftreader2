# RiftReader2 — two-lab live anchor checkpoint (2026-11-08)

**Checkout:** AMD-DESKTOP `C:\work\riftreader2`, branch `codex/modular-foundation`.
**Pushed code:** `872a167` (scanner error classification), `c72157f` (retain full-scan anchor diagnostic during heartbeats). Full solution tests: **1,390 passed, 0 failed**. No new reader binary was deployed after those commits.

## Verified live results (UTC)

| Evidence | Lab 1 | Lab 2 |
|---|---|---|
| Game PID before exit | 6820 | 10612 |
| Fresh-scoped addon receipts | **65** | **707** |
| Last confirmed fresh scoped source | 16:03:52.588 | 16:10:55.541 |
| Source-hashed offline XYZ (x,y,z) | (7450.369629, 864.309998, 2984.609863) | (7182.459961, 820.519958, 3159.669922) |
| Local catalog | `artifacts/live-reliability-20261108-03/lab1-captured-xyz-reference-01.json` | `artifacts/live-reliability-20261108-03/lab2-captured-xyz-reference-01.json` |
| Catalog receipt SHA-256 | `B8B1E937123B0C063A6FDBD6FE6DFE93AD4912338E4A3204B37AB6525F8B7394` | `9DF8708B673746E734D3EEA5F39382B899821BC3D6E7B43A21F2A610637F0AD9` |
| First confirmed game exit | 16:10:49.704 | 16:10:56.760 |

**Important:** The two game exits were **7.056 seconds apart**; coordination is possible but **cause is unproven**. Lab 1 separately lost its matching addon challenge at **16:03:53.445**, nearly seven minutes *before* game exit, with the same reader nonce and game PID. The full scanner's cached prior selections after that instant are not new fresh evidence. The 5-second freshness timeout and 10-second fast-anchor limit worked as designed; do **not** relax them or classify a cached/expired sample as fresh.

The native fast-observation reader was verified working in both labs. The two saved XYZ catalogs are historical, **`offline-reference-only`**, never movement-eligible. Coordinates use `rift-addon-xyz-xz-planar-y-vertical`; neither current zone/world match nor native coordinate freshness is established.

## Next practical actions

1. Recheck **both** game processes and managed console owners first. Both VMware VMs were running at 16:12 UTC, but receiver journals last recorded game exits. Both controller tasks had been restarted and were holding their independent lanes; Lab 1 screenshot-reviewed status preparation failed `controller-busy`. Do not stop, bypass, or race the controllers.
2. When a lane is genuinely available and RIFT is back, screenshot-review one `/rr2guide status` check to diagnose source loss. Inspect addon producer/reload evidence; no source of the 16:03:53 nonce loss was confirmed.
3. Re-establish a **new** nonce-bound, verified fresh-scoped source with short bounded tests on both labs. Prefer reliable default scanner behavior; 256 KiB/8 GiB on Lab 1 was an opt-in experiment and cannot justify live movement alone.
4. Recheck independent current native XYZ and matching world context before any navigation or movement. Keep the two original proof receipts immutable; local `artifacts/` content is not pushed to GitHub.

No game movement, unguarded input, VM reboot, or controller override was performed in this checkpoint.
