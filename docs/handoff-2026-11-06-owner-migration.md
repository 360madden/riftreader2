# Continuation — live helper migration, November 6, 2026

Work in `C:\work\riftreader2`. Read `AGENTS.md`, `docs/status.md`, and this handoff. Reacquire all PIDs, start times, receiver nonces and VM identities; values below are historical observations, not reusable authority. Prior offline context: [RR2 helper manager](handoff-2026-11-06-rr2-helper-manager.md).

## Current resume point — sustained480 and helper ownership accepted

**Latest, 10:54 PM Eastern:** [current-owner sustained480](validation/lab1-current-owner-sustained480-2026-11-06.md)
passed511 samples over480.653s, gaps2.449/2.352s, drift0 and zero unavailable
reads. Independent full/fast production-gate replay and20 sampled helper checks
over578s passed. Lab1 controller is now PID15636/generation
`fcd8e722d34d4758b82f7171ddd2bae0`, receiver63376, queue5216; Lab2 remains
controller24412/receiver65764/queue2334. Both ready/disarmed/idle/free at final
postflight. Reader PID12424/nonce`f335b16b33324c33950af2df29b840bc` expired
after10:57:53 PM Eastern; fresh guest checks verified no readers, deletion of
only its private staging leaf and independent absence. The stale snapshot was
refused with exit2, `not-fresh`, `gameReady:false`. Reacquire identities and
never reuse its cached feed. Evidence:`lab1-newowner-expiry-cleanup` under the
receiver-migrations artifact root.
No further input is needed for this completed interval. The older checkpoints
below remain historical, including the pre-console controller PID61336.

[Strict sustained validation](validation/lab1-sustained480-2026-11-06.md) passed
481.134 seconds with 515 samples; independent replay verified all raw/ledger
hashes, exact identities, advancement, expiry, maximum arrival gap3.058s,
capture gap2.983s and planar drift0.0. The unchanged first attempt failed after
85s with an unavailable receipt; observer-only bounded polling/counting was
implemented and tested in `1802c4b`. Passing run had zero unavailable polls.
The original failed artifact was retained. All acceptance gates remain strict.

Recorded reader PID6464/nonce622041afc6a14371aa45ec5efcc57c8c expired
November6 9:43:08 PM Eastern; a fresh guest check verified its exit and the
receipt reader rejected the stale feed. Never reuse its pin or cached packets.
This is sustained observer-side receiver evidence, not restart, native-field,
movement or Lab2 qualification. No reload/movement/cast/Lab2 input occurred.

The sustained-run gate passed: 380 portable +317 Live .NET, 1,668 Python (2 skipped), Lua,
native smoke, ownership, format and1,022 links; evidence
`artifacts/validation/20261107T023836Z-51b6dc01`. Guest startup race fix
`54d5e95` also has26 focused passing tests. User's five-hour meaningful-work
goal remains active; preserve other sessions' changes and current owners.

### Instance-bound owners accepted, 10:30 PM Eastern

Ownership hardening was merged with the newer Lab2 inspection route, reviewed
and integrated as `23b78fb` (isolated candidate `22f91d0`). Scheduler status
now exposes the sole running PID/GUID, and controller/receiver admission binds
that PID to the verified process receipt and listener. Lab2 fast inspection
checks the same instance across both observations and retains no-legacy
admission. Explicit no-auto-start status stays diagnostic; protected operations
verify an existing owner, while STOP/release remain directly available.

All four old owners were retired before source integration. Both controllers
completed authenticated STOP, generation-specific shutdown, verified cleanup,
queue quarantine and process/port exit. The exact older Lab1 generation was
retired against all nine pinned `b2e3fa1` source blobs and its immutable receipt;
ordinary current-source admission was not relaxed. A transient immediate
receiver-vacancy failure stopped v2b safely; the continuation verified durable
queue history and all vacancies before proceeding. Lab2's intervening successful
diagnostic accounted for generations2331/2332 before shutdown2333. No queue reset,
silent re-arm, game input, reload or VM/game restart occurred.

Independent postflight verified current source/config/process receipts, Scheduler
PID/GUID, listeners, fresh VM identities, unchanged bound guest/game identities,
initial cleanup, ready/disarmed/idle status and free/unheld queues:

| Lab | Controller PID / generation | Receiver PID | Queue generation |
| --- | --- | --- | --- |
| Lab1 | 61336 / `feaac3fdb44e4027a5ad31da2dba7c7f` | 63376 | 5214 |
| Lab2 | 24412 / `37bd686548f241649ca6f5dde0586c98` | 65764 | 2334 |

These are historical checkpoint values. Reacquire them before any operation.
Evidence is under `artifacts/receiver-migrations/instance-binding-rollout-v2b`
and `instance-binding-rollout-v2b-continuation`; the latter's
`independent-postflight.json` SHA256 is
`84FBC54678981FE1F7DCB8516D138FA1426357E65B96B7DF00F50ED67A2BD6A3`.
Never rerun the one-shot migration operators against these successors.
Receiver freshness was not requalified after their restart; the earlier
sustained480 evidence applies to its recorded, now-expired reader epoch.

Host PowerShell module imports were made interpreter-local in `8a1815a` after
the first read-only preflight found `Get-FileHash` unavailable under an inherited
module path. Production import prefixes pass fresh-process tests with invalid
module paths and autoload disabled. Cleanup, configuration, replay and import
suites pass33 focused tests. The isolated ownership gate passed716 .NET and
1,724 Python tests (12 skips), Lua/native/ownership checks, then stopped at a
preexisting ignored-artifact link. The25 local evidence links are now represented
as paths. The combined main gate then passed:716 .NET,1,748 Python tests
(2 skips), native/Lua/ownership/format and1,010 links. Evidence:
`artifacts/validation/20261107T033228Z-f42863ae`; log
`artifacts/validation/combined-owner-freshness-20261106.log`.

`d68a398` bounds receipt reads through one verified handle and checks the final
same-file regular leaf and unchanged metadata. It accepts atomic replacement
completed before open;89 console/feedback tests passed. This is for the trusted
atomic publisher, not never-follow confinement or every same-metadata in-place
rewrite. Existing freshness, identity, expiry and STOP/release gates are unchanged.

That fresh-reader/bind/strict480 batch is now complete as recorded above. Root
retains all live-input ownership. The [running-helper status optimization](validation/console-interaction-speed-2026-11-06.md#running-helper-status-inspection)
was integrated as`bb3d95c`. All19 live read-only calls matched current PID/GUID;
ordinary queries averaged0.651–0.673s across four helpers, versus earlier Lab2
normal1.986s/existing inspection0.662s (three measured samples each; changed
host load prevents a controlled before/after claim). No helper restart or input
was needed. Final source/config/process/listener postflight again found both
controllers ready/disarmed/idle, queues free, same current owners. Full gate
passed716 .NET,1748 Python (2 skips), native/Lua/ownership/format and1015 links:
`artifacts/validation/20261107T040344Z-13a31e2a`. No cold start was repeated for
this status-only change.

### Advisory console phase timings integrated

`84fe0fb` integrates the reviewed timing slice (isolated commit`4a42288`, branch
`codex/console-phase-timings`). Fixed-name monotonic events go to separate v1
sidecars only after owned cleanup; canonical plan/review/execution/stdout stay
unchanged. Direct release remains untimed. Tests cover busy mutex, replaced
directories, clock/publish failure, cancellation before input, cleanup visibility,
and cancellation immediately after a successful send with canonical attempt
recording and same-plan retry refusal. The125-test console/feedback/guidance
suite passed; independent review passed69 console tests and the retry repro.
Trusted artifact directories are assumed. The combined gate passed716 .NET,
1758 Python tests (2 skips), native/Lua/ownership/format and1016 links. Evidence:
`artifacts/validation/20261107T042150Z-b4cf4cb7`; log
`artifacts/validation/console-phase-timings-20261106.log`.

No live console operation was performed for the timing change. The
`vnc-connect-initiate` phase only creates a proxy; first input/capture can include
RFB authentication. Prepare game identity is inclusive of its guest session.
Mutex waits, teardown and release are not separately measured. Collect actual
phase records during the next authorized operation; root retains all input
ownership. Do not repeat successful reload/bind merely for a benchmark.

Screenshot reuse is not implemented. Current after-screen is captured before
release and lacks hash/dimensions/actual capture-time proof. Reuse would still
need fresh VM/game admission and a separate new review; first measure the
existing phases rather than claiming the whole prepare duration can be saved.

### Next standalone slice — native-vitals admission and replay

The bounded source audit found three reproduced validator gaps. Two isolated
workers are implementing them; no native operation, helper update, input or
restart has been performed for this slice:

- `.worktrees/native-response-order`, branch`codex/native-response-order`, owns
  `scripts/fresh_native_vitals.py` and its test. Add shared
  `validate_response_time(report, observed_at_utc, before, after)`, preserving
  UTC/host±5s bounds while requiring guest sample completion no later than its
  response timestamp. A response two seconds before completion previously passed.
  Use fixed refusal`native-vitals-response-before-sample`.
- `.worktrees/native-workflow-admission`, branch`codex/native-workflow-admission`,
  owns `scripts/inspect_lab2_workflow.py` and its test. Check exact integer1
  capability versions for both fresh identity and native vitals during requested
  persistent preflight; retain per-operation checks and expose only fixed safe
  refusal reasons. Persistent replay must require reportv2 and a validated
  `observedAtUtc`, using the shared timestamp helper. Keep explicit-reader v1
  historical replay. A retained v1 report with no envelope timestamp previously
  passed a synthetic persistent wrapper.

The response helper is committed as`77e0159` plus`12318fd` (exact100ns guest
timestamps and ordered UTC host brackets), with14 focused tests and independent
review passed. Workflow`49c0170` has88 focused tests and review passed against
the first helper; its public import consumes the stricter follow-up. Both start
from`84fe0fb`. Integrate helper, follow-up, then workflow; run the combined
focused suite before the full gate. No full gate or live acceptance has run for
the new slice. Lab1's recorded idle agent advertised neither native-vitals nor fresh-
identity version, while Lab2 advertised both as1; do not infer unsupported handler
details or update the agent from this observation. The current persistent native
workflow is explicitly Lab2-only. Reuse its exact identity, passive read and
subsequent screenshot lease/STOP/release guards; do not promote candidate field
semantics or restart qualification.

The five-hour goal remains active (started about9:22 PM Eastern; target about
2:22 AM November7), and is not marked complete at this checkpoint.

The bounded current-runtime dependency scan found no confirmed remaining active
default dependency on Workbridge, the original reader or its probe in
scripts/src/addon/config; explicit historical replay/legacy inspection remain.

The [launch-failure cleanup follow-up](validation/lab1-receiver-freshness-2026-11-06.md#launch-failure-cleanup-follow-up-1013-pm-eastern)
passed 19 focused tests and a nonsecret Lab1 deletion/fresh-session absence
smoke check. Only the failed launch's generated config is eligible, inside its
own guest session and with zero readers; unresolved cleanup remains explicit.
No additional game input or owner replacement occurred for that check.

The [offline consistency verifier](validation/lab1-sustained480-2026-11-06.md#offline-consistency-verifier)
reproduces the retained 515-sample metrics and rejects inconsistent rehashed
schemas/timelines/expiry. Its 12 focused tests pass. It checks selected recorded
output only; it grants no current freshness, artifact authenticity, VM/live
admission or full-scan-anchor qualification.

## Prior resume point — short-window cleanup and freshness passed

See [the live validation](validation/lab1-receiver-freshness-2026-11-06.md). The
fixed-file cleanup passed execution review and deleted the physical guest file;
a second fresh GuestSession confirmed absence and no reader. The earlier user
and Tools checks reflected different views; stale receipts and a simple PS
version difference were ruled out, while the exact Windows mechanism remains
unproven. This supersedes the cleanup blocker described chronologically below.

A fresh bounded reader and exactly one screenshot-reviewed Lab 1 rebind produced
12 strict advancing regular-feed samples over 8.934671 seconds (outer236→247,
addon13664→13682, same player/epoch). The managed controller was safely released
before input and restored afterward as PID64320, generation
`d3f5021244604dba97e0214310e5ab16`, ready/disarmed/idle with initial cleanup and
current source pins verified. Queue generation5210 was free/unheld. No reload,
movement, casting or Lab2 input occurred. Reader PID7108 expires at November6
8:49:59 PM Eastern; its future cached packets are not fresh evidence. Do not
reuse its nonce. Short-window feed acceptance does not establish sustained480,
restart or native-field qualification. Lab2 freshness is still unverified.

## Completed live owner transitions

- Both legacy receiver instances were individually pinned by process receipt and Scheduler COM GUID/EnginePID, stopped, checked exited/port-vacant, and replaced by RR2-managed receiver tasks. Independent postflight task/receipt checks passed: Lab 1 PID 5840/start `639296090706474389`; Lab 2 PID 4856/start `639296091161417286`. Legacy XML, registration and receipt backups are under `artifacts/receiver-migrations/lab1-76b0741c7ce14d7c8ebd573bd60adc42` and `lab2-a2804964338741578e60d4d704568bb5`. No feed packets appeared in either new output directory at the check; **advancing freshness is not established**. Migration helper commit `44df5e6`.
- Lab 1 controller old PID 29820 passed direct authenticated STOP, fresh no-input status and generation-specific verified shutdown. `artifacts/controller-migrations/lab1-20261106/verified-shutdown.json` has SHA256 `174534F26F5489F02C65373610D3D868A6FC241D23B1D495944AD55F5B3FBCFB`; its queue moved to blocked generation 5207 before successor reconciliation. Retained task XML/registration are in the same directory. The RR2 successor PID 65564, generation `c0e4e5e474b94ebabfef9a02e7e6ddd7`, passed managed receipt/source verification and connected, ready, initial-cleanup-verified, disarmed/idle/no sampled inputs status. Queue generation 5208 was unblocked, unheld, with no pending work.
- Lab 2 is **recovery**, not a verified clean handoff: prior PID 47952 and old VM PID 20020 were gone; last old-generation emergency STOP was unverified and queue generation 2252 blocked. Exact Ready-state legacy task was independently verified and backed up under `artifacts/controller-migrations/lab2-20261106`; no old task instance or controller listener existed. RR2 successor PID 10904, generation `fb51eb44863a43fcac36aabc299c227d`, subsequently connected with initial cleanup verified, disarmed/idle/no sampled inputs; queue reconciled to a fresh VM epoch, generation 2253, unblocked/unheld. `ensure_guest_agent.py` initially returned `connected-but-not-idle`; subsequent independent status showed ready. Game foreground was false; no game input was sent on Lab 2. This does not retroactively qualify old shutdown.
- At last task inventory, all four RR2 helper tasks were Running; no matching legacy helper task remained. Process/task health is not telemetry freshness.

Full local gate `pwsh -NoProfile -File scripts/validate.ps1` passed: 380 portable and 301 Live .NET tests, 1,604 Python tests (2 skipped), PowerShell ownership mocks, Lua contracts, synthetic native smoke, format and 1,018 relative links. Evidence: `artifacts/validation/20261107T005715Z-1fbf31cc`. The tests do not establish live feed freshness. Ready-state verifier commit `cf8b6bf`; staging-path fix commit `24e01a0`.

A subsequent read-only continuation confirmed Lab 1 controller connected/ready, supervisor initial cleanup verified, disarmed/idle/no sampled inputs, and receiver ownership verified (PID 5840 at that observation). The earlier automatic execution-policy rejection still blocks the guest cleanup; the user granted approval, but this does not itself override that rejection. No new bind or game input was performed.

The user reported manually deleting the staged configuration. A subsequent identity-pinned cached-credential guest check recorded `configExists: true` and `otherReaderCount: 0` in `artifacts/receiver-migrations/lab1-cleanup-verification/inspect.json`. This conflicts with the user report; request a recheck of the exact guest path and require a fresh absence check before reader launch. No new bind or input was sent.

A later identity-pinned guest check again reported `configExists: true`, `otherReaderCount: 0`, machine `RIFT-LAB-1` (evidence `artifacts/receiver-migrations/lab1-cleanup-verification-3/inspect.json`), despite the user reporting deletion and guest PowerShell reporting `False`. Earlier guest metadata recorded the exact file as 411 bytes, without reading its contents. The discrepancy remains unresolved. User requested automation without further questions, but the prior automatic execution-policy rejection still applies to guest cleanup; do not bypass it. No bind or input was sent. Other sessions have concurrent uncommitted work; preserve it.

## Historical cleanup blocker — resolved above

User authorized a fresh **Lab 1-only** reviewed reader bind/rebind solely to verify advancing receiver feed; no UI reload and no Lab 2 game input. Reader launch `artifacts/receiver-migrations/lab1-freshness-reader-20261106` failed `private-staging-cleanup-scope` before its launch step. Host private staging file was removed after same-directory-identity verification. Windows virtualization made the original resolved-path check disagree; commit `24e01a0` fixes it with filesystem identity checks, rejects reparse/symlink targets and has focused tests. No reader-ready receipt and no new bind/input were produced. The guest staging configuration at `C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid\lab1-fed73039b1614151bc92bda5b8501641\riftreader2-live.json` may contain the private receiver token and may remain on Lab 1; do not print its contents. An attempted exact guest cleanup plus no-reader verification was **rejected by automatic execution policy before running**; reason was not specified. Do not bypass that rejection. Resolve the cleanup through an allowed route/user action, verify absence and no unexpected reader, then retry with fresh identity, nonce and screenshot-reviewed controls. No feed freshness claim until strict fresh same-player/epoch receiver samples actually advance.

User did not authorize Lab 2 game input. The prior Lab 1 successful bind and reload must not be replayed. A fresh reader nonce would require a separately reviewed `rebind` only if the existing addon state supports it; never guess or blindly try both bind and rebind. Preserve controller STOP/release, exclusive console ownership, queue, exact identity, screenshot freshness and restore checks. RR2R1 typed-reference evidence is distinct from receiver-feed freshness.

**Copy-ready resume:** Read `AGENTS.md`, `docs/status.md`, this handoff and the
strict sustained validation. Reacquire current identities; reader6464 expires
at9:43:08 PM Eastern and its recorded PASS belongs only to that epoch. Continue
the active five-hour standalone development work with the isolated helper
instance-binding slice, focused tests and strong ownership review. Preserve
current controllers and receipts; no source-pin relaxation, re-arm, movement,
reload, restart or Lab2 game input is implied. Integrate only reviewed scoped
changes and use verified per-owner handoffs for any runtime rollout.
