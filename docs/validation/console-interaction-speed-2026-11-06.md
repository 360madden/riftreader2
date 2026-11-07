# Console interaction speed — November 6, 2026

The normal cached-credential reviewed command route previously used 14 `vmrun` child processes: five in preparation and nine in execution. These are code-path counts, excluding top-level Python processes, controller handoff and review. Preparation and execution each capture a screenshot and open a VNC connection. Five retained historical execution receipts took 18.38–19.66 seconds (median 19.33 seconds); this excludes preparation, review and handoff and does not isolate individual calls.

Execution now reuses one authenticated, VM-identity-pinned guest session for its two full game PID/start/SHA queries. The normal route consequently has 13 rather than 14 `vmrun` children (execution 8 instead of 9); both identity queries, fresh review, exclusive mutex, capture and release remain. A 20-trial simulated call-delay model excluding the initial `vmrun list`, with 10 ms per call, produced median 82.41 ms before and 72.26 ms after (8 versus 7 guest calls); it measures the assumed delay model, not actual guest performance. At this initial offline checkpoint, no live timing was measured.

`python -m unittest tests.test_addon_command_console tests.test_vm_console_native tests.test_vm_console_reservation -q` passed 113 tests. Independent review checked session cleanup, VM identity checks, pre-input freshness and release ordering. The test suite exercises send/capture failures, stale review and game drift. During that offline implementation, no RIFT input, reload, bind, VM/game restart or live console operation was performed.

Combining open-chat and command entry would type after an unreviewed transition: the current command admission specifically requires an image showing open, focused, empty chat. The two reviews remain separate. Controller handoff and guest query latency remain possible bottlenecks, and actual live performance and failure recovery require separately authorized verification. See [continuation](../handoff-2026-11-06-console-speed-continuation.md).

The historical receipts are the five `execution.json` files under ignored `artifacts/standalone-acceptance/` in `lab1-open-chat-review-20261106-b`, `lab1-final-open-chat-20261106-b`, `lab1-casting-hide-review-20261106-b`, `lab1-reload-command-review-20261106-b`, and `lab1-bind-rr2r1-20261106-b`. The simulation used Python `time.perf_counter`, 20 trials per case and `time.sleep(0.01)` repeated eight versus seven times; it models only a fixed per-call cost and is not a benchmark of the implementation.

## Subsequent authorized live observations

The later Lab1 freshness trials retained four successful ordinary execution
receipts: `artifacts/receiver-migrations/lab1-chat-prep-d`,
`lab1-rebind-prep-b`, `lab1-sustained-chat-c`, and `lab1-sustained-rebind-c`,
each with `execution.json`. All report successful release. Subtracting
`startedAtUtc` from `completedAtUtc` gives **10.380–11.206 seconds**, median
**10.688 seconds** (two open-chat and two fresh-reader rebind operations).
These observations fall within the execution goal of 5–15 seconds for these
healthy sessions. They exclude prepare, review, controller handoff and tool
orchestration, and are not a controlled benchmark or a universal latency claim.
Both session reuse and cached-login validation changed between the retained
historical and later trials, so no single change receives causal credit.
See [short-window](lab1-receiver-freshness-2026-11-06.md) and
[sustained](lab1-sustained480-2026-11-06.md) evidence for the live limits.

## Running-helper status inspection

`bb3d95c` reuses the existing two-observation COM inspection for ordinary
Status on all four running RR2 helpers. Both observations verify the exact
registration, owner, settings, absent legacy collision and sole matching
engine PID/instance GUID. Null or ambiguous results fail closed. Known
nonrunning states retain the previous ScheduledTasks path. At this historical
checkpoint, observing Running during fallback required a fresh external call;
the [November 7 bounded retry fix](../handoff-2026-11-06-owner-migration.md#scheduler-startup-retry-p2-fixed--november-7)
now reacquires that full proof internally. Ordinary
Status retains its unsigned task result and note; explicit Lab2 inspection
retains its narrower behavior. Register/Start and STOP/release are unchanged.

The read-only baseline used one warmup and three samples per path on the same
Lab2 controller: normal Status mean **1.986 s**, explicit COM inspection
**0.662 s**, with the same PID/GUID. After integration, 19 read-only calls
(four warmups, twelve ordinary measured calls and three explicit inspections)
all matched their independently pinned owners:

| Helper | Mean / median, seconds |
| --- | --- |
| Lab1 controller | 0.666 / 0.661 |
| Lab2 controller | 0.673 / 0.662 |
| Lab1 receiver | 0.668 / 0.669 |
| Lab2 receiver | 0.651 / 0.652 |
| Explicit Lab2 inspection | 0.663 / 0.666 |

The post-change Lab2 ordinary query was about 1.31 s below the earlier mean.
The reader expired between the batches and host load changed, so this is not
a controlled before/after benchmark. No helper start, stop, registration,
lease or game input was issued for measurement. Evidence:
`artifacts/receiver-migrations/helper-status-latency/results.json` and
`postflight.json` (current source/config/process/listener admission, both
controllers ready/disarmed/idle and both queues free). Cold start under this
generalized status path was not repeated against healthy owners.

Focused checks passed 99 Python tests and both PowerShell mock suites, including
all IDs, fallback races, ambiguity, null collections, altered registrations and
PID/GUID changes. Independent control review passed. The combined gate passed
716 .NET and 1,748 Python tests (2 skips), native/Lua/ownership/format and 1,015
links; evidence:`artifacts/validation/20261107T040344Z-13a31e2a`, log
`artifacts/validation/helper-status-fast-20261106.log`.

## Advisory phase measurements

`84fe0fb` adds `prepare-timings.json` and `execution-timings.json` beside the
owned console artifacts. These version1 sidecars contain fixed phase names and
monotonic elapsed nanoseconds, with no command text or credentials. Plan,
review, execution and stdout contracts remain unchanged. This historical slice
used `execution.json` for same-plan refusal; the November 7 durable-attempt fix
below closes its report-publication and concurrent-caller gaps.
Timing failure cannot turn a blocked or cancelled operation into a successful
attempt, suppress pre-input cancellation, or prevent direct key release and
disconnect. Publication runs after cleanup, checks the original non-reparse
output directory identity and creates its leaf exclusively. This assumes a
trusted artifact tree, not an atomic defense against malicious directory swaps.

Interpret phases by their actual scope: prepare's game-identity phase includes
the guest session and query; execute's acquisition phase includes credential
lookup/login validation and VM rechecks. `vnc-connect-initiate` creates the
proxy; RFB authentication can continue into the first capture or input call.
Mutex waits, teardown and release are not separately measured. Do not sum these
records into a complete end-to-end profile or claim a VNC saving from them.

The focused console, feedback and guidance suite passed125 tests; independent
review passed69 console tests and reproduced interrupted-send refusal with a
single mocked send. No live console operation was performed for this slice.
Collect its actual stage timings during the next independently authorized
operation; do not repeat reload/bind solely to fill a benchmark table.

The combined local gate passed716 .NET and1,758 Python tests (2 skips), plus
native/Lua/ownership/format and1,016 links. Evidence:
`artifacts/validation/20261107T042150Z-b4cf4cb7`; log
`artifacts/validation/console-phase-timings-20261106.log`.

After-screen reuse remains unimplemented. The existing image precedes release
and has no receipt-bound image hash/dimensions/capture timestamp; any future
reuse also needs fresh VM/game checks and a separate new screenshot review.

## Durable console attempt reservation — November 7

The P1 review found that input could be repeated if final `execution.json`
publication failed, or if two callers passed its check before taking the mutex.
Execution now exclusively creates `execution-attempt.json` under the existing
VM console mutex, flushes and fsyncs it before connecting or sending input, and
rechecks legacy `execution.json` under that mutex. The marker records only
schema version, plan hash, capture ID and attempt time.

Any existing attempt marker, including partial or malformed content, blocks
reuse. Marker persistence failure sends no input and retains any created leaf.
Only the successfully reserved caller may publish the final execution report;
a refused or busy caller cannot overwrite the owner's report. Failed report
publication, cancellation and uncertain sends retain the marker. Existing
legacy reports, including dangling links, also prevent reuse.

The operation consumes its reviewed output directory once reservation succeeds,
including a later pre-input rejection. Preserve its artifacts; use a fresh
preparation and screenshot review for a separately authorized new operation.
Do not delete a marker to retry an uncertain command. This assumes the existing
trusted local artifact tree and does not claim resistance to deliberate marker
deletion or directory replacement.

VM/game identity, final review/source freshness, exclusive ownership and direct
key/mouse release/disconnect remain in their existing order. No live console
operation, game input, bind/reload, helper restart or ownership transfer was
performed for this fix. Offline regression and validation results are recorded
in the owner-migration handoff.

The console suite passes 80 tests, including 11 new regressions; the combined
console/native-console/reservation suite passes 140. A separate mocked
report-publication failure reproduction sent twice with vulnerable `c5edf0c`
and once with the fix; its retry was refused while the marker remained and
`execution.json` was absent. Send cancellation still released keys and
disconnected, including when final report publication also failed. Independent
control review found no remaining P1 replay path. Local logs, reproduction and
verified source hashes are under `artifacts/console-replay-fix-20261107/`.

The full shared-checkout recheck passed 719 .NET tests and 1,803 Python tests
run (1,801 passed, two skipped), plus locked restore/build/format, native smoke,
Lua/C# contracts, ownership mocks, deterministic replay and 1,057 links.
Evidence: `artifacts/validation/20261107T095604Z-d546dc58` and
`artifacts/console-replay-fix-20261107/full-validation-recheck.log`.
The initial gate's two failures occurred during concurrent managed-admission
edits; its log is retained, and that module subsequently passed 29 focused tests.
The concurrent admission changes are preserved outside this fix's commit.
