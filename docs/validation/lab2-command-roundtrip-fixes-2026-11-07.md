# Lab 2 remaining command round trips — November 7, 2026

Implemented three status-request consolidations in the normal joined
`inspect_lab2_workflow.py run --native-vitals` path. The complete workflow
measured **3.572315 to 3.411390 seconds median** in five interleaved before/after
pairs: **4.50% faster**, saving **0.161 s median**. This is a modest local
improvement; model thinking and external tool
dispatch remain outside these measurements.

## What changed

- Admission returns its freshly validated status directly to preflight instead
  of preflight immediately requesting the same status again. The existing
  host-only admission API remains compatible; there is no stored status cache.
- Before native acquisition and before screenshot admission, one fresh status
  request now satisfies both the workflow checks and the adjacent executable
  identity operation. The callable runs inside the existing VM verification
  brackets. Full controller, target geometry, epoch, machine, capability and
  identity predicates remain; the following executable hash is still uncached.
- The identity query compares the complete newly loaded controller configuration
  with the admitted configuration before using the supplied status. This binds
  the GET and POST to the same endpoint and credentials. Failures still execute
  the final VM check. Separate post-hash/post-operation checks remain.

This removes three unnecessary status HTTP requests. Standalone phases retain
their previous requests. Both fresh Scheduler proofs and both canonical full
VM inventories remain at their original boundaries, with queue-owned capture,
STOP/watchdog release and independent artifact verification unchanged.

## Measured result

| Boundary or stage | Before median | After median |
| --- | ---: | ---: |
| Complete child workflow | 3.572315 s | 3.411390 s |
| Benchmark dispatch, including matching source loader | 3.862182 s | 3.704899 s |
| Native candidate stage | 0.534817 s | 0.512156 s |
| Screenshot admission | 0.159037 s | 0.142145 s |
| Final full inventory and managed checks | 0.377186 s | 0.386554 s |

Child means were **3.551968 to 3.435400 s**, and ranges were
**3.387619–3.646299 s before**, **3.292620–3.548969 s after**. All ten controlled
samples remain included, including the fourth pair where after was slower.
Small samples and overlapping ranges do not establish a general speed or
reliability guarantee. The full inventory was not improved.

The initial five before and five after trials are also retained. The first
after group overlapped repository validation and is not the headline comparison.
After that gate completed, a reviewed bootstrap alternated A1/B1 through A5/B5.
It loaded frozen baseline/candidate client sources under their original canonical
filenames without changing the checkout. Baseline bytes match the original
before-source hashes; both arms share the same runtime sources. The child timer
is primary because dispatch also includes matching bootstrap/compile overhead.

See the [controlled comparison](../../artifacts/remaining-command-latency-20261107/controlled-comparison.json),
[source bindings](../../artifacts/remaining-command-latency-20261107/controlled-source-bindings.json),
and [loaded-host trial list](../../artifacts/remaining-command-latency-20261107/after-loaded-runs.json).
Child and dispatch times use host monotonic clocks. The recorded native-to-image
interval uses guest UTC timestamps and is not a measure of model thinking.

## Remaining delay and scope

Explicit `vmrun -T ws list` matched default `vmrun list` in five paired trials but
was not faster. PowerShell 7 did not provide a consistent material improvement
over Windows PowerShell. Removing the unused CIM preload alone saved only about
30 ms in a separate startup test and was not adopted. The VIX replacement's
completion contract remains unqualified, as explained in the
[previous investigation](lab2-admission-inventory-optimization-2026-11-07.md).
Starting inventory earlier could miss a sibling VM that starts during the task
proof; direct target checks would not catch that change. The later inventories
therefore remain required. These fixes do not eliminate all command latency.

The coordinator alone performed live operations, using **Lab 2 only**. No input,
focus change, guest/controller deployment or VM/game restart occurred. Every run
retained identical VM/game/controller/guest/receipt/runtime/supervisor pins.
Workers implemented, reviewed and audited offline. The final screenshot was
visually reviewed after release; native field meanings remain candidates.

## Validation

101 focused tests passed. The full gate exited 0: **719 .NET tests passed**;
**1,823 Python tests ran, 1,821 passed and two skipped**; Lua contracts, native
smoke, helper ownership, formatting and 1,070 relative links passed. Evidence:
`artifacts/validation/20261107T101319Z-223bea74` and the
[gate log](../../artifacts/remaining-command-latency-20261107/full-validation.log).
Final [postflight](../../artifacts/remaining-command-latency-20261107/postflight/verified-status.json)
repeated both task proofs, fresh executable identity and full initial/final
inventory with the baseline pins. Lab 2 was ready/disarmed/idle, with no sampled
held inputs; queue generation 2435 was unblocked/unheld with no active Lab 2
request. No continuous input-absence claim is implied.

Rollback affects only the three client-side source files and their tests; active
runtime files, task registrations and installations require no change.
