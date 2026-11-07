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
nonrunning states retain the previous ScheduledTasks path; observing Running
during that fallback refuses the result and requires a fresh call. Ordinary
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

The post-change Lab2 ordinary query was about1.31 s below the earlier mean.
The reader expired between the batches and host load changed, so this is not
a controlled before/after benchmark. No helper start, stop, registration,
lease or game input was issued for measurement. Evidence:
`artifacts/receiver-migrations/helper-status-latency/results.json` and
`postflight.json` (current source/config/process/listener admission, both
controllers ready/disarmed/idle and both queues free). Cold start under this
generalized status path was not repeated against healthy owners.

Focused checks passed99 Python tests and both PowerShell mock suites, including
all IDs, fallback races, ambiguity, null collections, altered registrations and
PID/GUID changes. Independent control review passed. The combined gate passed
716 .NET and1,748 Python tests (2 skips), native/Lua/ownership/format and1,015
links; evidence:`artifacts/validation/20261107T040344Z-13a31e2a`, log
`artifacts/validation/helper-status-fast-20261106.log`.
