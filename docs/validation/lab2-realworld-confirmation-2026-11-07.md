# Lab 2 real-world inspection and confirmation — November 7, 2026

Tested the new one-call path on a complete read-only task: acquire native vitals
and a screenshot, take a second fresh observation of the same target, verify
identity continuity and advancing acquisition times, save confirmation evidence,
release control, and return both images for visual review.

The largest remaining avoidable pause was returning to the model solely to
dispatch that already requested second observation. The driver now supports
`--confirm-output <second fresh directory>` and completes both independent
observations in one tool call. **Observed external median task time fell from
19.784 to 8.062 seconds**, saving **11.722 seconds / 59.25%**.

## Before and after

| Actual session-log interval | Before | After |
| --- | ---: | ---: |
| Pair 1 | 20.108 s | 7.889 s |
| Pair 2 | 19.784 s | 8.179 s |
| Pair 3 | 19.199 s | 8.062 s |
| Median complete task | **19.784 s** | **8.062 s** |
| Mean complete task | 19.697 s | 8.043 s |
| Median first-image-return to confirmation dispatch | 10.652 s | No separate model-facing dispatch |
| Model-facing calls per task | 2 | 1 |

The primary boundary is first tool dispatch through return of the second image.
Root JS stamps independently measured medians 19.741 to 7.993 seconds and reconcile
with session events within 57 ms. All three complete before and after tasks are
included. Each task contains two full observations. The underlying workflow-sum
medians were 7.269872 to 6.984107 seconds; that small uncontrolled variation is
not evidence of faster VM processing. The major saving removes model-facing
orchestration, preparation and scheduling between predetermined operations.
Logs cannot separate reasoning, review, scheduling and transport inside that gap.
Three sequential trials per mode are not a latency percentile or general guarantee.

Both routes perform the same offline pair comparison and save `confirmation.json`.
The baseline uses the existing one-call driver twice; its second call also runs
the comparison before returning. The new path returns both images only after the
pair passes. This delays the first image until the second observation completes.
Use it when the confirmation is preauthorized and independent of interpreting
the first image. Keep separate calls for decisions that require that interpretation.

Evidence: [comparison](../../artifacts/realworld-handoff-optimization-20261107/comparison.json),
[before audit](../../artifacts/realworld-handoff-optimization-20261107/before-independent-audit.json),
[after audit](../../artifacts/realworld-handoff-optimization-20261107/after-independent-audit.json),
and [independent session timing](../../artifacts/realworld-handoff-optimization-20261107/independent-session-pairs.json).
Timings use UTC wall-clock/session records, not a model-internal reasoning clock.
Full repository validation started after all timed observations finished.

## Checks and actual observations

Each observation independently performs both fresh Scheduler proofs, initial and
final full VMware inventories, fresh executable hashing, native acquisition,
queue-owned screenshot and STOP/watchdog cleanup. No identity or authority proof
is shared between observations. The pair additionally requires identical complete
managed plans, targets, VM and supervisor epochs; distinct capture/request IDs
and native source paths; advancing native/capture times; and revalidated deliveries
before publication. The native source bytes used for timing are hash checked.
Failure suppresses the successful pair/image list while retaining the artifacts.

All **12 comparison observations** passed exact shared identity, state/plan/native
source/image/metadata hash, unique-observation, cleanup and ready/disarmed/idle
checks. All nine running-controller source hashes still matched their receipt.
The root reviewed all 12 images after release and observed the expected RIFT
world/UI. Candidate HP was 10635/10635 and Energy 100/100; Mana was unavailable
with `not-mana-kind-three`. Acquisitions advanced from 12:03:03.8975495 through
12:06:10.6027933 UTC. These establish new acquisitions and preserved provenance,
not changed-state field semantics, passive freshness or restart durability.

## A correctly blocked attempt and controller recovery

A concurrent task changed receipt publication in `controller_task_entry.py`
during the initial baseline. The next admission correctly refused the changed
runtime source hash before native acquisition or capture. The completed old pair,
partial pair and refusal remain in
[pre-recovery trials](../../artifacts/realworld-handoff-optimization-20261107/pre-recovery-trials.json).
They are separate from the headline comparison.

After independent review of the startup-only change, the root verified the old
controller's exact process, task, VM, listener, receipt and historical source
hashes against commit `fc2b3da` for shutdown only. STOP and the normal shutdown
marker were followed by positive process-exit, listener-closure and console-lock
release proofs. The normal dependency manager started the Lab 2 successor.
No receipt hash was patched and no unrelated source edit was reverted.

The VM, game and guest-agent identities stayed unchanged; host instance changed
from `6d1747b69d984308940c2195d5ed6df8` to
`a31f17b16e2e48c59d91e81b1fdf7777`. Both comparison arms were then measured under
that same recovered controller and runtime-source pin. Recovery and rebaselining
are excluded from steady-state task timings. See
[recovery proof](../../artifacts/realworld-handoff-optimization-20261107/recovery-proof.json),
[verified exit](../../artifacts/realworld-handoff-optimization-20261107/recovery-old-exit.json)
and [successor receipt](../../artifacts/realworld-handoff-optimization-20261107/recovery-result.json).

## Validation and final state

The revised driver passed 15 focused tests and independent review, including a
real retained pair accepted forward and rejected in reverse order. The full gate
exited 0: **719 .NET tests passed; 1,874 Python tests ran, 1,872 passed and two
skipped**, plus native smoke, real Lua contracts, helper ownership, formatting
and 1,096 relative links. Evidence: `artifacts/validation/20261107T120702Z-cff92240`
and [the validation log](../../artifacts/realworld-handoff-optimization-20261107/full-validation.log).
The final [postflight](../../artifacts/realworld-handoff-optimization-20261107/postflight.json)
repeated fresh admission, executable identity and full inventories with the same
recovered pins. Lab 2 remained ready/disarmed/idle, no sampled held inputs, queue
generation 2481 unblocked/unheld and no active Lab 2 request.

The root alone performed live operations. Agents implemented, reviewed and audited
offline. All guest operations and controller recovery targeted **Lab 2 only**.
No gameplay input, focus change, VM/game restart or Lab 1 guest operation occurred.
See the [operating recipe](../workflows/lab2-tool-handoff.md).
