# Lab 2 admission and VM inventory optimization — November 7, 2026

The joined read-only native/UI workflow improved from **3.857463 to 3.584552
seconds median**, saving **0.272911 seconds / 7.07%**, across five before and five
after runs. Managed-plan admission improved **21.88%**. Both complete fresh task
proofs remain at their original discovery and constructor boundaries. The safe
change shares one short-lived PowerShell interpreter between those proofs.

Full VM inventory remains unchanged. An isolated vendor-API experiment identified
connection establishment as its principal cost, but did not establish the complete
callback-ordering contract needed to replace the existing ambiguity checks.

## Measurements

| Boundary or stage | Before median | After median | Change |
| --- | ---: | ---: | ---: |
| Complete joined child workflow | 3.857463 s | 3.584552 s | 7.07% faster |
| Local subprocess dispatch to result | 4.193614 s | 3.876943 s | 7.55% faster |
| Managed-plan admission | 1.726293 s | 1.348548 s | 21.88% faster |
| Final full inventory and managed proofs | 0.366088 s | 0.390110 s | 6.56% slower; unchanged implementation |
| Native candidate stage | 0.565128 s | 0.557287 s | Essentially stable |
| Screenshot | 0.143600 s | 0.154350 s | Small increase; unchanged implementation |

Complete-child ranges were **3.697427–4.012597 s before** and
**3.559454–3.901339 s after**. All ten samples remain included. Timings use host
`perf_counter`; nested spans are not added together. The child boundary includes
dependency readiness, admission, fresh identity, candidate native acquisition,
queue-owned screenshot, STOP/watchdog cleanup, artifact verification, and final
full inventory. Dispatch additionally includes local subprocess overhead. Neither
boundary includes model/connector latency, conversational pauses, or later image
review. These small sequential samples are not percentiles or general reliability
qualification.

The raw [comparison](../../artifacts/admission-inventory-optimization-20261107/comparison.json),
[before audit](../../artifacts/admission-inventory-optimization-20261107/before-independent-audit.json),
and [after audit](../../artifacts/admission-inventory-optimization-20261107/after-independent-audit.json)
retain all measurements, identity bindings and artifact hashes. The five after
folders retain the intermediate `admission-only` name; `after-runs.json` is an
exact copy of that run list, not another set of trials.

## Implemented admission change

`prepared_lab2_inspection_pair()` starts one bounded Windows PowerShell process.
Each resolver independently triggers the unchanged helper manager and obtains a
new complete Scheduler proof. The first result is never reused as the second.
Each request has a fresh random token and strict ordinal; both responses must
pass the existing exact-task checks and agree on EnginePID/InstanceGUID. The
first identity is used only to reject an instance change.

The helper enforces one use per boundary, a shared 20-second deadline, bounded
64 KiB frames and successful final child exit. Wrong order, stale or unsolicited
output, malformed/partial/extra frames, mismatched tokens, changed identity and
expiry fail closed. The child is killed and reaped on failure or context exit.
The compatibility single-proof helper still requires successful process exit.
Ordinary managed-controller admission retains its existing path.

Separate instrumented admissions measured **1.683786→1.316729 s**. The first task
proof was **0.736674→0.727215 s**, and the second **0.434759→0.102948 s**. This
supports interpreter/module reuse as the improvement. These are one profile per
version, separate from the five uninstrumented workflow samples.

## Inventory investigation and retained boundary

An isolated, parent-timeout-bounded process loaded the installed VMware VIX DLL
and performed only host connection and running-VM enumeration. Connection took
**357.987 ms**; three separate fresh queries took **5.294, 5.608 and 5.694 ms**.
Fresh `vmrun list` calls immediately before and after took **361.665 and
336.350 ms**. All three path multisets matched both calls, retaining duplicates.
The [observation](../../artifacts/admission-inventory-optimization-20261107/vix-observation.json)
is experimental evidence, not admission qualification.

The [VMware-maintained VIX header](https://github.com/vmware/open-vm-tools/blob/master/open-vm-tools/lib/include/vix.h)
defines the discovery callback and its item-location event property. The review
did not establish a documented guarantee that terminal completion drains every
already-dispatched item callback, or a supported synchronous exhaustive result
array. A callback already resolving a path could race a completion snapshot;
an omitted same-directory VM entry could defeat the current refusal check.
The incomplete production candidate was removed. There is no new VIX runtime
dependency, inventory cache or persistent service.

Both original full `vmrun list` checkpoints remain. They retain exact target
membership/cardinality, sibling ambiguity refusal, VMX/log binding before and
after acquisition, VMware process image/PID/start, log epoch and VNC listener
ownership. Intermediate direct epoch checks also remain. The unmodified final
inventory median was slightly slower in this sample; no inventory speedup is
claimed. A reusable connection remains a promising future route if exhaustive
completion semantics can be established.

## Scope, identities and cleanup

The root alone performed live operations. Workers separately implemented
admission, reviewed concurrency/identity, researched inventory and audited
measurements; no worker had live ownership. All guest/native/UI operations used
**Lab 2 only**. Host-wide inventory necessarily enumerated the other running VM's
path; it performed no Lab 1 guest operation.

Every run required the identical baseline pin and supervisor epoch. No controller,
guest agent, VM or game restart/deployment occurred:

- VM: `RIFT-Lab-2\RIFT-Lab.vmx`, VNC 5962, VMware PID 17848,
  start ticks `134383662779267832`, log epoch `2026-11-05T15:31:17.951Z`.
- Game: PID 9752, start ticks `639294897826627677`, HWND `0x401BC`, SHA-256
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Host instance: `6d1747b69d984308940c2195d5ed6df8`; guest instance:
  `9d897ea7eddd4ba5998017ca2f387f17`; connection 2.
- Controller receipt SHA-256:
  `A40EEC669DE4F11B733FBF50DCDDDC92AAB99B081A08AF58CAC2B8C243CB1B23`.
  All receipt-pinned runtime files remained baseline-identical.

Audits verified exact pins, source and capture hashes, successful stages, final
ready/disarmed/idle state, no sampled held inputs, and STOP/watchdog release
evidence for every run. The root visually reviewed the final after BMP after
lease release; it showed the expected RIFT world/UI. Native values remain
candidates. No gameplay input, focus change, memory write or Windows tuning was
performed. Snapshot observations do not establish continuous absence of input.

## Validation and rollback

The 154 focused tests passed, including harmless PowerShell fixtures proving
separate manager invocations, changed-instance refusal, framing/deadline failure
and helper cleanup. Independent source review found no blocking admission issue.
The full repository gate exited 0: **719 .NET tests passed** (380 portable and
339 Live); Python **1,803 tests ran: 1,801 passed and two skipped**. Dependency,
locked restore, build, formatting, real Lua/C# contracts, synthetic native smoke,
helper ownership and **1,063 relative links** passed. Retained evidence:
`artifacts/validation/20261107T095909Z-d8ae96c8` and the
[gate log](../../artifacts/admission-inventory-optimization-20261107/full-validation.log).
The later Lab-2-only postflight repeated both current Scheduler proofs, full
initial/final inventory, authenticated fresh executable identity and status;
baseline pins remained identical and the controller was ready/disarmed/idle.
The separate read-only queue check found generation 2395 unblocked/unheld and no
active Lab 2 request. See the [postflight status](../../artifacts/admission-inventory-optimization-20261107/postflight/verified-status.json)
and [queue/visual receipt](../../artifacts/admission-inventory-optimization-20261107/postflight-queue-visual.json).

Rollback consists of reverting this change's two client-side Python source
files and their tests. No runtime receipt, task registration, guest installation
or active controller needs to change. Preserve unrelated work when reverting.
