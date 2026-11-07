# Lab 2 ChatGPT/tool and VMware latency report

**Investigation date:** November 6, 2026, America/New_York; retained end-to-end traces use November 7 UTC.  
**Scope:** VMware Lab 2, Windows 11, one running RIFT game, and the surrounding ChatGPT/Codex tool workflow.  
**Evidence basis:** Completed research, approved light live tests, implementation measurements, independent review, and retained acceptance receipts. This report introduces no new live testing.

**November 7 receipt audit:** The headline measurements reproduce from retained traces. See the [independent artifact audit](validation/lab2-latency-report-audit-2026-11-07.md) for exact test counts, visual-review coverage, source boundaries and evidence limitations.

## Executive finding

The largest measured delays came from workflow orchestration and repeated setup work. Separate remote jobs introduced long gaps between phases; guest operations repeatedly launched scripts, transferred files, and copied a 117 MB executable for a diagnostic whose native read took milliseconds.

The implemented fast path batches related work into one bounded job and obtains native candidates through the existing authenticated guest agent. The same screenshot diagnostic fell from **44.049 seconds and 15 connector calls to 5.898 seconds and three calls**. A joined native-data-and-screenshot diagnostic completed remotely in **5.826 seconds**.

These observations establish specific bottlenecks in the tested workflow. They do not establish the cause of every ChatGPT pause, cloud response delay, Windows 11 slowdown, or game input/frame-time problem. Model reasoning time, provider latency, and hardware contention were not independently isolated.

## Scope and method

All live guest operations in this investigation targeted Lab 2. The VM and game stayed running. Controller and guest-agent reloads were deliberate, identity-checked deployment or reconnect tests. No game input, focus command, game-memory write, Windows security/power change, or Lab 1 guest operation was performed.

Separate agents owned the guest implementation, Python transport/client, workflow integration, timing analysis, and independent identity/concurrency review. The coordinator retained live-operation ownership and serialized guest testing.

The real diagnostic workflow was:

1. Admit the existing controller and verify its process, task, configuration, source, VM and authenticated guest identities.
2. Freshly verify the expected game process/build and optionally acquire bounded native vitals candidates.
3. Acquire the workflow's own named capture lease, capture the game window, and validate target, geometry, timestamp and image integrity.
4. Finish that request and verify the watchdog's cleanup, lease release and final identities.
5. Review the retained screenshot separately, after release.

Connector traces use one root clock. Local child stages use host `perf_counter`; their durations are reported separately. The study does not subtract unsynchronized clocks to manufacture network or model timing. Completion means the verified machine report is available; later image review and the conversational answer are outside that timing boundary.

## Before and after

### End-to-end workflow measurements

| Measurement | Before | After | Sample basis |
| --- | ---: | ---: | --- |
| Screenshot workflow through remote connector | 44.049 s; 15 calls; 3 jobs | 5.898 s; 3 calls; 1 job | One observed run per configuration |
| Joined native/UI child workflow | 16.676 s | 4.105 s median; 4.031–4.300 s | One earlier run; three optimized runs |
| Joined native/UI through remote connector | No matching original joined remote baseline | 5.826 s; 3 calls; 1 job | One optimized run |
| Joined native/UI interval checks | Not performed before optimization | 4.222 s child median; 4.037–4.509 s | Ten checks at one-minute intervals |

The remote screenshot reduction is **86.61% for the observed pair**. The joined local comparison combines several improvements and must not be attributed to one change alone.

### Individual operation measurements

| Operation | Before | After | Samples |
| --- | ---: | ---: | --- |
| Open VM-specific cached guest session | 5.325 s median | 0.580 s median | 3 before / 3 after |
| Fresh game PID/start/SHA query | 4.299 s median | 0.112 s median | 3 before / 5 after |
| Native sampling with a new executable copy each call | 74.142 s | 8.957 s median with verified installed-reader reuse | 1 before / 3 after |
| Native sampling through persistent agent | 74.142 s original wrapper; 8.957 s reuse median | 0.2186 s median; 0.1964–0.2945 s | 5 persistent queries |
| Persistent native query plus outer fresh identity guards | 74.349 s original guarded baseline | 0.4452 s median; 0.4111–0.5228 s | 1 baseline / 5 persistent queries |

Comparing the original single native-wrapper baseline with the five-run persistent median gives an observed **99.71% reduction**. Persistent sampling is about **41 times faster** than the already-optimized installed-reader median. These are small, primarily warm operation samples, not percentile estimates or a benchmark of total ChatGPT response time.

The earlier session/identity measurements and their precise boundaries are in the [initial implementation note](validation/lab2-latency-improvements-2026-11-06.md). The consolidated [performance evidence](../artifacts/e2e-latency-20261106/final-performance-summary.json) retains the end-to-end comparisons and provenance.

## What caused the measured delays

### Separate tool jobs and phase transitions

The original remote screenshot workflow had **19.743 seconds of observed return-to-next-dispatch gaps between phases**, split into 8.655 and 11.088 seconds. Batching the same original admission behavior into one job reduced the total observed span from 44.049 to 22.043 seconds before the later admission improvements.

The final remote screenshot trace has zero phase-transition gaps and approximately **0.513 seconds of within-phase gaps**, including deliberate 250 ms polling backoffs. Gaps can include orchestration, rendering and scheduling; call round trips also include transport effects. The traces do not identify the model's internal reasoning time.

### Repeated guest setup and executable transfer

The original native wrapper copied a fresh 117 MB reader into a unique guest directory for every acquisition. Its total operation took 74.142 seconds while the native read itself reported 8.066 milliseconds. This established that the wrapper, transfer and startup path dominated that observation.

The first fix reused an explicitly selected installed executable, verified its full SHA, rejected reparse paths and held a read-only handle through execution. The final fix moved the same bounded acquisition behind a typed authenticated request, removing the recurring executable transfer, guest script launch and report-file transfer.

### Repeated admission and scheduled-task checks

The workflow now retains one admitted host within a bounded local process. Intermediate checks still verify the exact controller/source/configuration and VM epoch. Full VMware inventory checks bracket the run, including rejection of a sibling VMX sharing the running log.

The Lab-2-only task inspection uses fresh Task Scheduler COM queries and the original registration, action, principal, settings and ownership predicates. It validates the exact running root task and absence of a competing legacy registration, with no legacy fallback on inspection failure. Ordinary movement and maintenance admission retain their original behavior.

The existing authenticated login probe also became cheaper, and fresh game identity queries now use the persistent channel while continuing to hash executable bytes.

## Identity, ownership and STOP protections

Performance changes preserve these boundaries:

- Exact VM process/start/log/listener identity, full inventory at entry and exit, and authenticated VM checks around native requests.
- Expected game PID, start time, executable path and supported build, with fresh executable-byte hashing at native session open and post-read revalidation.
- Matching of the actual executing guest-agent instance against authenticated status and the workflow's original admission.
- Fresh native sessions and bounded player/component lookup; no address, process session or executable-hash cache is accepted as authority.
- A named capture lease, original epoch, expected cleanup generation increment, nonempty watchdog receipt and independently verified artifact hashes.
- No silent fallback after a missing capability, wrong identity, invalid executable, stale receipt or unsupported response.

The native operation uses one cancellable background read lane. It requires disarmed, idle control without pending recovery, refuses competing operations while unfinished, and allows STOP to acknowledge without waiting for the read to finish. Disconnect cancels and joins the read before reconnecting.

A delayed-reader integration test proved STOP acknowledgement before read completion. The corrected live watchdog probe observed an active native read, finished its own lease, observed native refusal during cleanup and attested cleanup in **0.488 seconds**. That is finish-to-cleanup time, not isolated HTTP STOP latency or unique proof of cancellation cause. An earlier probe used an idle-only polling predicate and failed closed; its cleanup passed and that attempt is excluded from responsiveness results.

## Stability, reconnect and validation results

All **ten light checks at one-minute intervals passed machine verification**, spanning **9 minutes 4.397 seconds** from first dispatch to final return. Their child median was 4.2219 seconds, and their local subprocess dispatch median was 4.4464 seconds. Native completion preceded screenshot capture by a median 0.569634 seconds. The terminal status was `verified-awaiting-visual-review`; a separate visual-review record is retained only for check 10 among these ten runs.

An independent [stability audit](../artifacts/e2e-latency-20261106/stability-audit.json) verified every retained native report, image/metadata hash, VM/game pin, controller/source/configuration proof, unique named request and distinct cleanup receipt. Approximately 55 seconds between checks were unobserved; this establishes sampled stability, not continuous freshness or general reliability.

Additional acceptance results:

- A live wrong-PID native request was rejected in about 0.050 seconds without publishing a report.
- After a controller-only graceful reconnect, the old admission was refused in 0.0152 seconds and a fresh joined workflow passed in 4.0796 seconds.
- The running agent's actual process epoch, executable path, instance ID and full executable SHA matched the activated release.
- The final joined workflow recorded ready, disarmed, idle control, no active native read, no sampled held inputs and an attested released lease. Its generation-2332 cleanup preceded a generation-2333 shutdown at 03:21:05 UTC. The controller then disconnected and exited. `final-acceptance.json`, assembled at 03:21:20 UTC, repeats the earlier workflow status; it does not prove readiness at its own timestamp. The shutdown record showed stopped control and no sampled held inputs, with the resource marked `stopped-still-blocked`.
- Full validation passed 380 portable and 336 Live .NET tests; Python ran 1,720 tests, with 1,718 passed and two skipped. Locked restore/build/format, published native smoke, Lua/C# contracts and deterministic replay passed. The retained full-gate log records 1,029 relative links. The originally reported later 1,035-link check has no corroborating raw result in the bounded artifact search and is excluded from the verified findings.

The [acceptance summary](../artifacts/e2e-latency-20261106/final-acceptance.json), [release proof](../artifacts/e2e-latency-20261106/active-release-proof.json) and [source provenance](../artifacts/e2e-latency-20261106/final-source-provenance.json) retain historical evidence. The summary's composition timestamp is not a fresh status observation; the [artifact audit](validation/lab2-latency-report-audit-2026-11-07.md) reconciles it with the subsequent shutdown. None is reusable authority for a later run.

## Remaining cost and limits

Across the ten interval checks, the largest child-stage medians were:

| Stage | Median |
| --- | ---: |
| Managed-plan admission | 1.7764 s |
| Native candidate stage, including surrounding workflow validation | 0.5388 s |
| Final full inventory and managed proofs | 0.3718 s |
| Watchdog cleanup | 0.3399 s |
| Screenshot capture | 0.1879 s |

The native workflow stage is distinct from the 0.2186-second standalone query and the raw memory read. The largest remaining measured cost is admission and ownership proof. Further work should profile those boundaries before removing checks or changing VM settings.

Screenshots showed HP 10635/10635 and resource 100/100 matching the native HP/Energy candidates. This is static corroboration only. Changed-state semantics, passive freshness and full-game restart qualification remain unverified; Mana correctly remained unavailable for the current non-Mana kind. Screenshot FPS values are isolated UI observations and were not used to claim improved game frame rate.

This study did not independently isolate cloud/provider response time, browser or app rendering overhead, host/guest resource contention, or game input/frame pacing. The measurements do not justify claiming that all ChatGPT/VMware lag has been solved or that a Windows security, CPU, RAM or graphics change is required.

## Recommended operating path

Use the bounded joined diagnostic for Lab 2 native/UI inspection. RIFT must already be running and foreground, and control must be disarmed. Choose a fresh result directory for every attempt:

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
$lab2RunRoot = Join-Path 'C:\work\riftreader2\artifacts\e2e-latency-20261106' ([guid]::NewGuid().ToString('N'))
& 'C:\Python314\python.exe' scripts\inspect_lab2_workflow.py run --native-vitals --output $lab2RunRoot
```

Inspect the returned `report.json` and `capture/image.bmp` after lease release. On refusal, inspect stderr and the retained failure/stage evidence; do not reuse old admission state or silently select another backend. Omit `--native-vitals` for screenshot-only inspection.

The activated release at acceptance was `agent-221af549f59b-zip`, SHA-256 `221AF549F59BF38FBF792C59BE3C9B7EFF09A3BA85ABB4FC6A1DE4DA6FDF3F9A`. The [detailed validation and operating note](validation/lab2-end-to-end-latency-2026-11-06.md) includes the explicit-reader alternative and guarded rollback command. The previous release lacks the persistent native capability.

Implementation checkpoints were saved locally as `69112ff` (persistent native path), `c2a29ff` (batched guarded workflow) and `af6662b` (stability/reconnect documentation). Future use must reacquire current identities and verify capability rather than trusting these recorded values.
