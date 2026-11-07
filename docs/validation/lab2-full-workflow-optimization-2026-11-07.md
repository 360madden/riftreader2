# Lab 2 native/UI workflow optimization — November 7, 2026

The complete joined native/UI workflow improved from **5.0824 to 3.7661 seconds
median** across five before and five after samples: **1.3163 seconds / 25.90%**.
Local subprocess dispatch-to-result improved from 5.3282 to 3.9844 seconds median
(25.22%). These boundaries exclude conversational response, connector/model time
and subsequent visual review.

All live operations targeted Lab 2. The VM, running game, controller process,
controller receipt and host runtime sources remained unchanged. A guarded update
replaced only the guest control agent; its new instance, connection and supervisor
epoch are explicitly bound to deployment/readiness evidence. No game input,
focus command, game-memory write, VM/game restart or Windows tuning was performed.

## Measured before and after

| Host stage/boundary | Before median | After median | Reduction |
| --- | ---: | ---: | ---: |
| Complete joined child workflow | 5.082389 s | 3.766136 s | 25.90% |
| Local subprocess dispatch to result | 5.328166 s | 3.984396 s | 25.22% |
| Dependency readiness stage | 0.836222 s | 0.036419 s | 95.64% |
| Native candidate stage | 0.552698 s | 0.529664 s | 4.17%; essentially stable |
| Screenshot stage | 0.403443 s | 0.166646 s | 58.69% |
| Watchdog STOP/cleanup observation | 0.345104 s | 0.168695 s | 51.12% |

The complete child ranges were 4.817715–5.883670 seconds before and
3.656008–3.949876 seconds after. Screenshot ranges were 0.323870–1.016402 seconds
before and 0.154462–0.263545 seconds after. All samples remain included. The
before outlier and the intentional guest restart prevent attributing the entire
screenshot difference to one code change. These are small samples, not percentiles
or a general reliability qualification.

The exact comparison and input provenance are in
[comparison.json](../../artifacts/native-ui-optimization-20261107/comparison.json).
The [before audit](../../artifacts/native-ui-optimization-20261107/before-independent-audit.json)
and [after audit](../../artifacts/native-ui-optimization-20261107/after-independent-audit.json)
independently verify identities, successful stages, native/image hashes and cleanup.

## Investigation findings

One separate instrumented before run contained 28 HTTP requests: 20 status,
six fresh identity, one native acquisition and one capture request. Native stage
HTTP time totaled 0.4726 seconds; the native request itself took 0.2053 seconds.
The native reader already opens a fresh read-only session, hashes executable
bytes, performs its bounded owner/type-bracketed acquisition, then revalidates
process/module/path and hashes executable bytes again. Those native and desktop
identity checks establish distinct facts and were preserved.

The before capture HTTP request took 0.2893 seconds, including 0.0200 seconds for
body reading/parsing. Local capture file flushes totaled about 0.0033 seconds.
The profile therefore did not support blaming local file flushes for the larger
capture delay. It does not independently isolate GDI capture, guest journaling,
serialization or network transport.

A separate after profile contained 27 HTTP requests: 19 status, the same six fresh
identity requests, and one native/capture request each. Its capture request took
0.1245 seconds and native request 0.2246 seconds. These single profiled observations
are separate from the five-run medians; nested body-read spans are not added to
their enclosing HTTP times. There is no claim of accelerated native-core reads.

## Implemented changes

### Ready dependency path, followed by strict admission

The combined workflow first validates the canonical Lab 2 machine, VMX, VNC port
and operator port **before any HTTP request or recovery action**. It obtains an
authenticated readiness observation and rejects unhealthy, closing, contradictory
or misrouted state. An already-ready idle endpoint proceeds directly to the
existing two independent strict admission proofs. Readiness alone grants no
authority. Failed identity, capability or admission checks never trigger recovery.

Only a positively missing endpoint or safely waiting/starting guest enters the
existing recovery routine. Standalone preflight retains its original dependency
handling. The hot path avoids the recovery routine's redundant ownership proof;
its predicates remain independently checked in both strict admission proofs
before native acquisition, lease acquisition or capture.

### Observe attested cleanup sooner

Combined Lab 2 runs poll for cleanup at 25 ms instead of 250 ms. Existing callers
and standalone phases retain the 250 ms default. Poll sleeps cannot exceed the
remaining deadline. Faster polling changes observation latency; it does not
replace or accelerate the watchdog's actual STOP/release work.

Acceptance still requires the workflow's terminal request, original epoch, free
unblocked resource, expected cleanup generation increment, nonempty watchdog
receipt and independently checked idle queue. Intermediate cleanup states cannot
be accepted early, and the worker does not issue an unconditional STOP after
losing its lease.

### Retain screenshot metadata without serializing the image first

The guest capture response is now typed but serializes to exactly the previous
wire fields, order and content. For its retained journal, metadata is constructed
without `imageBase64` before serialization. This avoids serializing a large image
string into a JSON tree just to remove it. Generic response retention still strips
both `armToken` and `imageBase64`. Durable journal publication remains before
wire transmission; capture bytes, hashes, target checks and capture algorithm
are unchanged.

An offline five-iteration journal-preparation benchmark with a 5 MiB image string
reported 6.305 ms and 15,733,224 allocated bytes per operation for the former
serialize/parse/remove path, versus 0.012 ms and 2,856 bytes for typed metadata.
This microbenchmark excludes capture, disk and network and is not the live
screenshot improvement. No timing threshold is asserted by the test.

## Identity and validation evidence

Preserved checks include fresh VM/game/agent binding, exact task engine PID and
instance GUID, sole controller generation, process epoch and listener ownership,
source/configuration bytes, full VM inventory at admission and completion,
intermediate direct VM checks, fresh game executable hashes, response freshness
at .NET tick precision, image/native artifact integrity and named-lease cleanup.
Native candidate semantics, passive freshness and game-restart qualification
remain unverified. Static HP/resource agreement with the screenshot does not
promote those candidates to qualified telemetry.

The guarded activation is recorded in
[identity-transition.json](../../artifacts/native-ui-optimization-20261107/activation/identity-transition.json).
The [active-process proof](../../artifacts/native-ui-optimization-20261107/active-release-proof.json)
matches the actual executable path, PID/start epoch, full byte SHA and authenticated
agent instance to the launcher and admitted after state. All five after native
receipts bind the new instance. The final after screenshot rendered normally.

Code validation passed 380 portable and 339 Live .NET tests, plus 1,785 Python
tests with two skips. Locked restore/build, formatting, published native smoke,
real Lua/C# contracts and deterministic replay passed. The original full script
then exited 1 on two preexisting Markdown hard-break trailing-space lines in the
latency report. Those report-only lines were corrected, and the final repository
whitespace/newline/link checks passed separately. The original nonzero exit remains
recorded; code tests were not needlessly repeated for that documentation fix.
Evidence: `artifacts/validation/20261107T065111Z-c8e7efcd` and
`artifacts/native-ui-optimization-20261107/`.

## Use and rollback

The existing combined command automatically uses the improvements. RIFT must
already be running, foreground and disarmed; each attempt needs a new directory.

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
$lab2RunRoot = Join-Path 'C:\work\riftreader2\artifacts\e2e-latency-20261106' ([guid]::NewGuid().ToString('N'))
& 'C:\Python314\python.exe' scripts\inspect_lab2_workflow.py run --native-vitals --output $lab2RunRoot
```

The activated guest release is `agent-2a17b9ff5ebd-zip`, SHA-256
`2A17B9FF5EBDBBA4B358F80EE6A6153D9B4F675A6C1EE8027640DD3C55729EAC`.
The previous release remains staged. Optional guarded guest rollback:

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
$lab2RollbackRoot = Join-Path 'C:\work\riftreader2\artifacts\native-ui-optimization-20261107' ('rollback-' + [guid]::NewGuid().ToString('N'))
& 'C:\Python314\python.exe' scripts\guest_agent_launcher.py update --managed-lab lab2 `
  --release artifacts\native-ui-optimization-20261107\activation\rollback-release.json --output $lab2RollbackRoot
```

That descriptor selects the prior `agent-221af549f59b-zip` guest, which supports
the same protocol. This command is provided for recovery; rollback was not executed.
Future runs must reacquire current identities rather than trusting historical pins.
