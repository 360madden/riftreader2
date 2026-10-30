# Lab 2 — eight-minute telemetry qualification (2026-10-30)

**Verdict:** PASSED one full 480-second read-only observation. This is not movement acceptance or authority to reuse source identities after expiry.

## Evidence

- Retained ignored artifact: artifacts/two-lab-resume-20261030/phase2-lab2-observation-8min-01.json
- Artifact SHA-256: 27F06D5C4449ADC83102A2843B15DBE8E16D8E23BFDCCF467E59B50A119F249A
- Source pin SHA-256: 6C213B5CB40272116EAA336EAFF2563A84E981B15F38ECB99889B7996ABD6295
- Window: UTC 20:19:57.267733–20:27:57.268263, 480.0 seconds
- Independently checked by Workbridge job rr2-milestone-lab2-eightmin-structural-verify-20261030-a; exit 0. The original observation was produced by the other active conversation, not rerun in this milestone.

| Metric | Observed |
| --- | ---: |
| Polls / valid strict polls | 951 / 946 |
| Distinct advancing receipts | 376 |
| Duplicate polls / transient not-fresh polls | 570 / 5 |
| Maximum no-new-receipt gap | **4.036 s**, below 4.5 s bound |
| Scan p50 / p95 / max | 776.814 / 867.699 / 1505.419 ms |
| Capture age p50 / p95 / max | 659.16 / 1234.8 / 1890.051 ms |
| Delivery skew p50 / p95 / max | 3.829 / 9.955 / 16.381 ms |
| Player / addon epoch | Stable |
| Planar drift / observer inputs | 0 / none |
| Terminal strict gate failure | null |

The independent check validated evidence schema/lab, status, full duration, strict threshold, counts and monotonic advancing outer/addon sequence across all distinct receipts, first/last identity, no observer input and checksum.

## Limits and next action

Five temporary not-fresh polls occurred even though the maximum gap passed. Receiver/guest clock synchronization is assumed, not independently proven. Lab 1's full window still **FAILED** with maximum gap 16.214 seconds. This Lab 2 pass does not authorize movement in either lab without renewed same-epoch source pins, terrain review, controller lease/arm gates and independent release confirmation. Prior readers had configured expiry UTC 20:36:30 (Lab 1) and 20:38:24 (Lab 2); do not treat them as live.

Next: build and validate the newer tracked fast candidate-region reader, preserve previous binaries and source hashes, requalify new nonce/reader/game identity in each lab using a fresh VM-specific cached-credential check on every login, and repeat sustained feedback gating before reviewed motion. Never relax freshness to force acceptance.
