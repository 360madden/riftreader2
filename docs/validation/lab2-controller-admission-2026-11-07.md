# Lab 2 controller admission optimization — November 7, 2026

The remaining admission stage is faster with both fresh task proofs retained.
The change overlaps startup of the second PowerShell interpreter with discovery;
it does not cache identity evidence or remove a validation boundary.

All live checks targeted Lab 2. This round required no controller/agent deployment,
VM/game restart, game input, focus command or Windows configuration change.
Unrelated working-tree changes were preserved.

## Current before and after

Three complete joined native/UI workflows were measured before edits and three
after. All retained the same full VM/game target, controller/guest generation,
process receipt, connection and running-controller source hashes.

| Host measurement | Before median | After median | Observation |
| --- | ---: | ---: | --- |
| Managed-plan admission inside joined workflow | 1.811809 s | 1.627895 s | 0.183913 s / 10.15% faster |
| Complete joined child workflow | 4.856581 s | 4.900452 s | 0.043872 s / 0.90% slower in these samples |
| Local subprocess dispatch to result | 5.073926 s | 5.121508 s | No demonstrated end-to-end improvement |

Before admission samples were 1.902677, 1.811809 and 1.748843 seconds; after
samples were 1.635917, 1.627895 and 1.605025 seconds. All samples remain included.
The first before workflow took 6.132789 seconds, versus 4.856581 and 4.838117
seconds for the other two. Most of that elevation occurred in fresh identity and
screenshot stages; the observations do not establish a cold-start cause.

Native-stage and screenshot variation offset the admission saving in the complete
workflow comparison. These small samples support an admission-stage improvement,
not a claim that the entire ChatGPT/tool workflow became faster.

## Paired attribution check

Six additional read-only admissions alternated preparation order in three pairs:
sequential/preloaded, preloaded/sequential, sequential/preloaded. Both paths used
the same current admission function, two complete fresh task proofs and unchanged
VM/process/source checks. The sequential variant replaced only the prepared
second-proof provider with the original fresh verifier; no proof was bypassed.

| Paired admission mode | Median | Samples |
| --- | ---: | ---: |
| Sequential interpreter startup | 1.830493 s | 3 |
| Second interpreter preloaded | 1.620772 s | 3 |

The difference between mode medians is 0.209721 seconds, or 11.46%. Each pair improved, by
0.252184, 0.193118 and 0.215613 seconds. The final full inventory check ran outside
the isolated admission timer for both modes. These are host `perf_counter`
measurements; no clocks from different processes or guests were subtracted.

The separate before profile measured 1.836080 seconds of admission. Its two fresh
task proofs took 0.661760 and 0.682224 seconds, totaling 73.20% of admission.
The after profile measured 1.634063 seconds: the first proof remained 0.664278
seconds and the prepared second proof took 0.471949 seconds. Profile observations
are separate from the uninstrumented headline samples.

## Implementation and preserved checks

`prepared_lab2_inspection_task()` creates one hidden, bounded, one-shot PowerShell
child. It preloads the same inbox modules, then waits for a fixed private stdin
signal. It performs no Task Scheduler observation before that signal. The original
manager script runs only when the constructor reaches its existing second proof.

The first discovery proof remains unchanged. The second still independently:

- Resolves the sole current controller generation and exact reviewed receipt.
- Validates process epoch, source/config bytes, canonical paths and listener owner.
- Runs the existing manager's registration, principal, action, settings and legacy
  absence checks, including its two fresh task observations.
- Requires one running task instance, the exact expected engine PID, a valid
  instance GUID and stable PID/GUID across the manager's observations.
- Refuses errors without a legacy fallback.

The prepared callback is single-use and Lab-2-only. EOF, a wrong signal, invalid
target, expiration or failed proof cannot authorize admission. Unused and failed
children are killed and reaped; consumed children exit and are reaped. A monotonic
20-second deadline bounds the prepared process. Ordinary movement/maintenance
admission keeps its existing path and cannot accept this inspection callback.

Initial and final full VM inventory checks, intermediate direct VM epoch checks,
authenticated guest generation, expected game identity, native freshness, named
capture lease, artifact verification and watchdog cleanup are unchanged.

## Verification and evidence

The focused managed receipt/host/workflow/launcher/native-VM checks passed 151
tests. Real Windows PowerShell fixture tests verified that missing or incorrect
signals do not invoke the fixture manager, correct signaling returns the expected
PID/GUID, and an unsignaled child exits on its own deadline. Tests also cover
single use, escaped callbacks, invalid targets, timeout/early-failure cleanup,
first-proof refusal and a changed task instance refusing the second proof.

Complete host Python discovery then passed 1,777 tests with two skips using the
repository's configured Lua-enabled validation interpreter. The initial default
interpreter run could not import `lupa`; the configured rerun passed. No .NET or
guest runtime source changed in this round.

Independent before/after artifact audits verified identity continuity, successful
stages, native/image integrity, final full inventory, disarmed/idle state without
sampled held inputs, and named lease release with attested watchdog cleanup.
The final after screenshot was visually reviewed and rendered normally; matching
static HP/resource candidates retain their existing semantic/freshness limits.

The final live admission also verified the actual prepared child had exited with
code zero, was reaped and had all three redirected streams closed. Controller,
guest, game and VM pins still matched the baseline; Lab 2 was disarmed/idle, with
no pending workflow request or held lease. See the
[final acceptance receipt](../../artifacts/admission-optimization-20261107/final-acceptance.json).

Evidence is retained under `artifacts/admission-optimization-20261107/`:

- [Before runs](../../artifacts/admission-optimization-20261107/before-runs.json) and
  [after runs](../../artifacts/admission-optimization-20261107/after-runs.json).
- [Independent joined comparison](../../artifacts/admission-optimization-20261107/independent-joined-comparison.json).
- [Paired results](../../artifacts/admission-optimization-20261107/paired-admission-results.json)
  and [provider/source provenance](../../artifacts/admission-optimization-20261107/paired-provenance.json).
- [Before audit](../../artifacts/admission-optimization-20261107/baseline-independent-audit.json)
  and [after audit](../../artifacts/admission-optimization-20261107/after-independent-audit.json).

The existing [joined diagnostic command](lab2-end-to-end-latency-2026-11-06.md#reuse-the-workflow)
automatically uses this optimization. No new command or service is required.
