# Lab 1 navigation: scoped feedback and waypoint budget (2026-11-08)

## Confirmed live result

- Host `AMD-DESKTOP`, repository `C:\work\riftreader2`, Lab 1 RIFT PID `8508` (start ticks `639297512849368370`), reader PID `4644` (reader SHA256 `ADBA0EC7047AB056934D52ADFB3F70E657C5C0D251F67A92EF756F413D8646AF`). This is a bounded historical identity, not a durable target for future sessions.
- Fresh scoped source pin: `artifacts/nav-lab1-live-scoped-source-pin-20261108-02.json`; selected source `fastObservation`, scope `candidate-regions`, provenance `recent-full-scan-anchored-candidate-regions/1`.
- Reviewed 150 ms `S` calibration succeeded in `artifacts/nav-lab1-1d-calibration-newreader-run-20261108-04/result.json`: X 7448.189941 -> 7448.679688, Y 864.539978 unchanged, Z 2985.889893 -> 2986.020020; planar displacement 0.506739 units; status `calibrated`.
- Reviewed ~1-unit 1D waypoint attempted in `artifacts/nav-lab1-1d-waypoint-newreader-run-20261108-01`. One 150 ms `S` action was delivered/released and a strict post-action receipt was saved, but the run failed on `elapsed budget` before arrival. No arrival result was produced. Final status verified disarmed, idle, no held desktop inputs, no recovery required.

## Timing evidence

| Receipt | UTC time | Distinct role |
| --- | --- | --- |
| initial | 19:29:44.090 | initial pinned feedback |
| ready-1 | 19:29:53.665 | pre-arm readiness |
| ready-2 | 19:30:05.384 | action readiness |
| barrier | 19:30:07.045 | post-delivery causal barrier |
| after | 19:30:07.864 | qualifying post-barrier scoped sample |
| ready-3 | 19:30:15.495 | next action readiness; elapsed budget exhausted |

Scoped sample scan execution times in these receipts were about 126–166 ms. The delay is between *eligible scoped samples/readiness*, not evidence that candidate-region scanning itself requires 10 seconds. Do not conflate HTTP publication cadence with source admission cadence. See `docs/handoff-2026-11-08-async-fullscan-cadence.md`: the former 256 KiB full-scan chunk experiment was rejected live and reverted to stable 64 KiB.

## Follow-up (practical and bounded)

1. Audit the 64 KiB asynchronous full-scan renewal duration against the 10-second fast-session anchor lifetime, without relaxing anchor age, freshness, identity, or causal barrier gates.
2. Measure eligibility gaps and their causes (anchor expiry, renewal, scanner result, addon advancement) in a read-only observer; retain source hashed receipts and exact reader identity.
3. If an actual scheduling/renewal improvement is demonstrated, add offline regression tests and publish a new reader binary with hash; rebind nonce after reader replacement.
4. Then rerun a freshly reviewed 1D calibration and waypoint. Keep 12-second action elapsed, 900 ms total hold, 6-unit radius, and 6-action budgets unless a separately reviewed safety change is warranted. Never reuse the expired plan, screenshot approval, calibration identity, or prior game process identity.
