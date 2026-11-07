# Lab 1 sustained freshness on the instance-bound receiver

On November 6, the current RR2-managed Lab 1 receiver passed a second strict
480-second validation after the [owner transition](../handoff-2026-11-06-owner-migration.md).
This establishes the recorded receiver interval on the new helper generation;
the [earlier run](lab1-sustained480-2026-11-06.md) remains separate historical
evidence. No acceptance gate was relaxed.

| Check | Observed result |
| --- | --- |
| Observer duration | 480.6532791 seconds |
| Accepted samples | 511 |
| Maximum acceptance / capture gap | 2.4490859 / 2.352035 seconds, both below 4.5 |
| Unavailable reads | 0 |
| Planar drift | 0.0 |
| Selected sources | 468 candidate-region; 43 complete full-block |
| Outer / addon sequence | 274→829 / 28265→29206 |
| Addon clock | 18173.97265625→18655.009765625 |
| Player / addon epoch | `u035400012FA2D678` / 1 |
| Capture interval | 2026-11-07 03:43:52.799692→03:51:53.752931 UTC |

The game was PID 11672, start ticks `639296016581575957`, SHA256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Reader PID 12424/start `639296194732214638` used SHA256
`390072FF17B4D69AB331CF3E4122DE378388F01BD806F4741C6FAE065865E659`
and nonce `f335b16b33324c33950af2df29b840bc`. Receiver PID 63376/start
`639296188357932285`, instance `f316a286652549859ecaf929a250d056`, was
bound independently to its RR2 Scheduler instance, process receipt and listener.
The reader expired after its November6 **10:57:53 PM Eastern** deadline. A
fresh guest check found no non-control readers; the shared guarded native helper
removed only this run's private `riftreader2-live.json`, and a distinct cached-
login session confirmed absence. The snapshot gate returned exit2, `not-fresh`,
`gameReady:false` for its stale receipt. The later cached packets must not be
treated as fresh and the nonce must not be reused.

The root coordinator verified controller STOP, generation-specific shutdown,
cleanup, queue quarantine and exit before console ownership. Fresh screenshots
separately approved one ordinary readiness-toolbar Hide click, one Enter to
open chat, and exactly one new-nonce `/rr2guide rebind lab1`. The after-screen
acknowledged the rebind and all executions confirmed release. No reload,
movement, casting, Lab 2 input or VM/game restart occurred. The Lab 1 controller
was restored before the strict observer began.

Independent replay verified all 511 raw hashes and ledger rows, identity,
advancement, expiry, timing, drift and source-choice consistency. Replaying the
unchanged production full/fast gates at recorded receipt times also verified
all 468 fast-anchor contracts, coverage, hashes and age limits. Maximum effective
selected-source age was 1161.648ms; maximum fast-anchor age was 9528.6867ms,
below 10000ms. This replay does not independently authenticate the files,
reconstruct past observer scheduling or VM provenance, or remove the production
gate's host/guest clock-synchronization assumption. It grants no present freshness.

A separate read-only sampler passed 20 checks over 578.166 seconds,
10:44:34–10:54:12 PM Eastern. All four source/config/process/Scheduler/listener
identities remained pinned at sampled instants; controllers were ready,
disarmed/idle with no sampled held inputs, and queues were free with no pending
work. Lab 1 controller PID 15636/generation `fcd8e722d34d4758b82f7171ddd2bae0`,
receiver 63376, queue 5216; Lab 2 controller 24412, receiver 65764, queue 2334.
Fresh independent postflight verified both owners and two further advancing
Lab 1 samples at03:54:11/03:54:12 UTC. These values are checkpoint observations;
reacquire all identities before future operations.

All following paths are local evidence under `artifacts/receiver-migrations/`:

- `lab1-newowner-reader/summary.json`, `vm-after.json`
- `lab1-newowner-console-handoff/verified-shutdown.json`
- `lab1-newowner-hide-readiness`, `lab1-newowner-chat-b`, `lab1-newowner-rebind`
- `lab1-newowner-source-pin.json`
- `lab1-newowner-strict480/summary.json`, `samples.jsonl`, `raw/`
- `lab1-newowner-strict480/independent-postflight.json`, `postflight-current-raw-b/`
- `offline-acceptance-review/lab1-newowner-strict480-fullgate-review.json`
- `instance-binding-rollout-v2b-continuation/owner-stability-fcd8e722d34d4758b82f7171ddd2bae0/`
- `lab1-newowner-expiry-cleanup/summary.json`, `stale-feed.json`

Ledger SHA256:`A5584A77EF0CA568F4279B476CC0AAB4E9AFAC530448A790ADCEFB94F0961965`.
Full-gate replay SHA256:
`0016D9B0B487D86E6B743FA4389AAD14A33606CC56F584159996696E977B7F58`.
Postflight SHA256:`BB166513ECE764F92A13E42D5639F7D8C320548DE649A3A4DB7FE8592A69A610`.
Helper-stability summary SHA256:
`98F5C3F00C18086716542761E949C8C339C8E8E298FC8C37AF25736170FF2E5F`.

Code milestones: instance admission`23b78fb`, host module imports`8a1815a`,
bounded handle read`d68a398`. The combined main gate passed 716 .NET and 1748
Python tests (2 skips), native/Lua/ownership/format and 1010 links; evidence
`artifacts/validation/20261107T033228Z-f42863ae`. Subsequent changes here are
documentation only. A separate warm-cache NTFS microbenchmark measured 26.05µs
additional median cost for the stronger read on one 2025-byte fixture (2,000 reads
per implementation); this is not an end-to-end speed claim or an explanation of
the earlier failed run. Profile:`receipt-read-profile/results.json`.

This is observer-side receiver freshness for the recorded reader epoch, with
sampled helper stability. It does not establish full-game restart recovery,
native field semantics, movement authority, continuous future availability or
Lab 2 receiver freshness.
