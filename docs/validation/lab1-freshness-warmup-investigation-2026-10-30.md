# RiftReader2 — Lab 1 freshness warmup investigation

2026-10-30, comparative read-only diagnostics around 20:00–20:08 UTC. Starting source commit 9a3385b. No changes were made to RIFT, VM snapshots, reader binaries, receiver or movement controller. No gameplay input was issued.

**Finding:** The observed Lab-1 full-source movement-feedback outage is an intentional fail-closed response to transient upstream reader freshness warmup, rather than blocked CPU time in the monitor or a receiver crash.

## Two independent observation paths

| Probe | Window | Accepted strict samples | Worst observed full-source gap | Other facts |
| --- | --- | --- | --- | --- |
| Earlier strict full-source window | 480 s | 297 distinct new receipts | 5.043 s (fail) | 23 transient not-fresh polls; zero planar drift |
| Precise 250ms strict full-source probe | 120 s | 44 distinct strict receipts; 330 valid polls | 18.327 s monitor gap / 18.179 s accepted-receiver gap (fail) | 142 gate failures, all reason live-receipt-not-fresh |
| Independent direct receiver sampler | 60 s overlapping above | 25 distinct raw sequences | 4.189 s maximum gap between receiver timestamps | 0 JSON read errors, no strict movement acceptance |
| Later per-receipt forensic sampler | 120 s | 63 distinct accepted full-source receipts | 3.174 s maximum gap (pass for its shorter window only) | All gate classifications accepted; zero schema-read failures |

The 120s strict probe call duration: median 3.74 ms, p95 5.42 ms and maximum 23.19 ms. Its 18.18-second accepted-receiver gap was between sequence 894 at 20:02:00.427 UTC and sequence 900 at 20:02:18.606 UTC, delta +6. The independent raw sampler captured **intermediate sequences 895, 896, 897, 898, 899** at approximately 20:02:03.482, 06.510, 10.077, 14.266 and 16.687 UTC. Therefore the receiver continued receiving; the strict gate withheld those observations. Raw sampling is diagnostic evidence only and must never be substituted for the strict identity/age checks for gameplay.

## Exact guest reader log corroboration

A fresh authenticated VMware guest session (every-login cached credentials checked) copied only timestamped and bounded status lines from the reader's existing stdout under its unique guest hybrid run directory. See ignored artifact phase2-lab1-reader-stdout-20utc-01.txt. The guest reader process at source was PID8120, nonce 67717fe706df4aec92bb2e3828b0d61c, exact game PID9928. The filtered log contains 178 entries.

During 20:02:03.490–20:02:16.693 UTC, **six consecutive delivered-http-200 observations reported scan=complete, selection=selected, freshness=warming**. Each was delivered, but the strict gate correctly rejected them. A fresh full-source observation at 20:02:18.613 resumed status freshness=fresh. Immediately before the six rejected observations, 20:02:00.434 had freshness=fresh. This isolates the acceptance failure to the reader's internal freshness/warmup state. The log also shows selected/warming around 20:01:54 and 20:01:57, plus two incomplete-scan/unavailable entries in the broader 178-line interval. Do not label the event an 18-second stalled memory scan or stopped HTTP receiver.

The source tracker in src/RiftReader2.Application/LiveAddonFreshnessTracker.cs deliberately returns warming after a gap larger than the configured freshness timeout and does not accept duplicate addon observation sequences as renewal. It withholds when the scan cannot select a candidate, and requires convincing advancing source timing before returning fresh. Which internal predicate caused each warmup transition, and whether candidate sequences temporarily plateaued, are **not established** by these status-only reader lines. A per-sequence future diagnostic should retain reader-selected candidateSequence, freshness Reason, lastAdvanceAgeMilliseconds and independent outer received/captured times. Keep fail-closed behavior; do not relax freshness timeout or stale-source requirements.

Read-only snapshots also showed no usable fastObservation block on one current receipt; movement_feedback.py can accept a separately validated fast observation, but it cannot be presumed present in this reader epoch.

## Evidence and next acceptance gate

- phase2-lab1-precise-gap-120s-01.json: full raw strict-poll timestamps, failures and selected receipts
- phase2-lab1-raw-receiver-60s-01.json: independent per-sequence receiver arrival timestamps
- phase2-lab1-gate-forensics-120s-01.json: later shorter window accepted all 63 new samples
- phase2-lab1-reader-stdout-20utc-01.txt: authenticated guest stdout around the failure
- Job IDs: rr2-phase2-lab1-precise-gap-120s-1030-01, rr2-phase2-lab1-raw-receiver-60s-run-1030-01, rr2-phase2-lab1-gate-forensics-120s-1030-01, rr2-phase2-lab1-reader-guest-log-extract-1030-01

Continue with a bounded read-only per-observation log of binding/freshness/selection, candidate sequence, tracker reason, and timing. Improve reader source stability only if a reproducible upstream cause is shown. Repeat sustained eight-minute qualification, including all failed windows, before motion. The restored detached Lab1 host PID51076 remains disarmed/idle and must retain exclusive console ownership. Lab2 remains unbound and input-gated until a new safe reviewed scene and correct nonce bind. Existing motion limits remain unchanged.
