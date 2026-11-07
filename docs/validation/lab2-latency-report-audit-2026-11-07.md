# Lab 2 latency report artifact audit, November 7, 2026

The [consolidated report](../lab2-latency-research-report-2026-11-06.md) was
audited against retained local traces, native reports, capture files, validation
logs, release bytes and Git history. Three parallel reviewers divided timing,
identity/cleanup and provenance work; the coordinator reconciled the findings.
The audit started at `42068b6`. No live query, game input, helper mutation,
restart or deployment was performed. All identities below are historical.

## Reproduced measurements

| Claim | Independent result | Retained inputs under `artifacts/e2e-latency-20261106/` |
| --- | --- | --- |
| Remote screenshot | 44.049 to 5.898 s; 15 calls/3 jobs to 3 calls/1 job; 86.61% reduction | `baseline-remote-01-trace.json`, `batch-final-remote-01-trace.json` |
| Original workflow batched before later admission improvements | 22.043 s; 10 calls/1 job | `batch-old-remote-01-trace.json` |
| Joined native/UI remote | 5.826 s; 3 calls/1 job | `joined-final-remote-01-trace.json` |
| Joined local child | 16.6760545 s before; optimized median 4.1049264 s, range 4.0306497-4.3004605 s | `joined-native-ui-01/run-timings.json`, `joined-persistent-local-01` through `03/run-timings.json` |
| Native operation | 74.1424919 s original; verified-reader reuse median 8.9567604 s; persistent median 0.2185915 s | `vitals-baseline.json`, `vitals-reuse-locked.json`, `vitals-persistent.json` |
| Guarded native operation | 74.3492304 s original; persistent median 0.4452016 s | Same benchmark records |
| Ten light checks | Child median 4.2219303 s; subprocess dispatch median 4.4464092 s; total span 544.397046 s | `stability-01` through `10/run-timings.json`, `stability-results.json` |

The raw remote traces reproduce phase-transition gaps of 8.655 + 11.088 =
19.743 s before batching, and 0.513 s of within-phase gaps in the final screenshot
run. The reported 99.71% native-operation reduction and approximately 41-fold
reuse-to-persistent ratio also reproduce. These are distinct timing boundaries,
with one remote run per configuration and small, primarily warm operation samples.
They do not isolate internal model reasoning, provider latency or game frame time.

The earlier session and fresh-identity medians also reproduce from
`artifacts/latency-implementation-20261106/`: login 5.3252239 to 0.5795637 s;
fresh identity 4.2990215 to 0.1123648 s. The remaining stage medians reproduce:
admission 1.7764455 s, native workflow 0.53882875 s, final proofs 0.37176175 s,
watchdog cleanup 0.33986215 s and screenshot 0.18790305 s.

## Corrections and evidence boundaries

- All ten interval runs reached `verified-awaiting-visual-review` with exit 0.
  A separate `visual-review.json` exists only for check 10 among these runs. All ten
  passed machine verification; a separate visual review of every image is not
  established. The coordinator rehashed and viewed check 10 during this audit:
  Bolinao AFK, HP 10635/10635 and resource 100/100 agree with the native candidates.
  Image SHA-256 is
  `5C13A399126B6F98D1E5C33D1F6AD992C73DC686DC1F196117B3E3934B30E2B9`.
- Return-to-next-dispatch gaps were 55.258801-55.734777 s. Those intervals were
  unobserved. This is sampled stability, not continuous receiver freshness,
  changed-state native semantics or restart qualification.
- `full-validation.log` and `full-validation-exit.txt` establish exit 0,
  380 portable plus 336 Live .NET passes, and 1,720 Python tests run:
  1,718 passed and two skipped. The report now states these exact counts.
- That log records **1,029 relative links**, at
  `artifacts/validation/20261107T030027Z-847d055a`. A bounded search of 6,588
  log/text/JSON files under the investigation and validation roots found no
  corroborating raw result for the report's later **1,035** count. This later
  count is uncorroborated, rather than disproven; it is excluded from acceptance.
- Historical source provenance pins `af6662b` and 26 files. Twenty-three hashes
  match raw Git blob bytes exactly. Three differ through LF/CRLF serialization
  (`sample_current_native_vitals.py`, its Python test and `current-native-vitals.md`);
  normalized content reconciles. No substantive historical source mismatch was
  found. This is not a claim of 26 identical raw Git blob hashes.

## Release and source boundary

The executable extracted from `activation/release.zip` hashes to
`221AF549F59BF38FBF792C59BE3C9B7EFF09A3BA85ABB4FC6A1DE4DA6FDF3F9A`,
matching `agent-221af549f59b-zip`, the descriptors and `active-release-proof.json`.
That proof records guest PID 9052/start 639296174027367419 and instance
`3eab0fa28015436cb6ae21a7f3fc1185` at 03:20:35.8178214 UTC. Its retained
generating script checks executable bytes, process path/start and ready instance
against authenticated status. The later acceptance summary names the same guest
instance, but its timestamp does not establish a fresh ready observation (see
the chronology discrepancy below). This audit did not query the live guest.

## Identity, cleanup and material chronology discrepancy

Fourteen retained workflow bundles (ten stability runs and four joined/follow-up
runs) reconcile with their own state/plan/process receipts, source/config pins,
image/metadata/native-report hashes and named cleanup evidence. Native report
content matches the corresponding actual-agent-instance response retained in the
host journal. Holder, epoch, release generation and STOP receipts agree. This
cross-record consistency does not transfer one run's source acceptance to another.

**The final summary overstates readiness at its composition timestamp.** The
final joined workflow ended at 03:21:00.851872 UTC. Its named-holder cleanup
generation2332 is corroborated by `control-host.jsonl` line40015 at
03:20:59.982783 UTC. But the same retained controller log records:

| UTC, November 7 | Direct retained evidence |
| --- | --- |
| 03:21:05.566885 | Line40038: generation2333, holder null, `stopped-still-blocked`; stopped, disarmed, not busy, no sampled held inputs |
| 03:21:05.975067 | Line40039: guest disconnected |
| 03:21:05.985506 | `artifacts/controller-tasks/lab2/55a90b5ab9104ba092038dc4f8719c8a/exited.json`: controller PID59400 exited |
| 03:21:20.063302 | `final-acceptance.json`: assembled summary repeats earlier ready status and generation2332 |
| 03:28:20.561232 | Line40040: next logged guest connection under a later controller |

The log is
`artifacts/control-fleet-live/lab2/host-evidence/control-host.jsonl`.
Thus the earlier workflow release succeeded and the subsequent shutdown retained
safe sampled input state, but **ready at 03:21:20 is not supported**. Preserve
the original summary as evidence; the report and handoff now qualify its copied
status. Later recovery observations belong to their own controller and cannot
retroactively make this summary fresh.

The same host log corroborates the corrected native-read STOP trial:
lines39139 and39144-39149 bind the native request, STOP sequence223,
03:06:03.347525 request and 03:06:03.375791 stopped response, followed by a
cancelled native reply at 03:06:03.375912 and matching holder cleanup generation2306.
The 28.266 ms request-to-response interval is one host-recorded trial, distinct
from the report's 0.488006 s finish-to-cleanup interval. It does not establish
worker completion timing, unique cancellation cause or a general latency bound.
The first probe failed closed and is excluded from responsiveness results.
Lines39164-39165 corroborate rejection of wrong PID9753 against expected9752.

Retained controller reconnect evidence separates old host `ae0562bc...`,
connection2/PID74220, from new host `3a66ba24...`, connection1, while the guest
instance, game PID9752/start639294897826627677/build and VM epoch remain pinned.
No uninterrupted readiness claim follows from deployment/reconnect evidence.
Hash consistency and software cleanup attestations corroborate recorded local
behavior; they do not authenticate the complete historical environment or prove
current ownership, current safety or absence of external input.

Git checkpoints `69112ff`, `c2a29ff` and `af6662b` exist with the documented
implementation and acceptance changes. Later chronology/admission fixes
`287a5b6`, `a310534`, `399d463`, helper changes and startup overlap `926309a`
changed the host workflow. The historical measurements and release proof do not
qualify all subsequent source. Running the report's example now requires fresh
admission to the current source, VM/game/agent and owned lease.

## Retained audit work and continuation

Local audit outputs are under
[`artifacts/lab2-report-audit-20261107/`](../../artifacts/lab2-report-audit-20261107/).
`performance-audit.py` recomputes numerical results offline into
`performance-audit.json`; `provenance-audit.json` records source hashes, release
and gate checks; `safety-receipt-audit.json` records identity/cleanup and controller
log corroboration; `root-input-and-visual-audit.json` pins 11 audit inputs and the
coordinator's screenshot check. The report's seven relative evidence links resolve.
Generated outputs remain local artifacts; this note preserves the conclusions.

No new live acceptance was attempted. Preserve existing owners and STOP/release
gates. The separate [owner-migration handoff](../handoff-2026-11-06-owner-migration.md)
still owns continuation and its open functional review findings; fix its P1
durable console-attempt reservation before further console input. Native HP/Energy
remain candidates, with changed-state, passive freshness and restart meaning
unqualified.
