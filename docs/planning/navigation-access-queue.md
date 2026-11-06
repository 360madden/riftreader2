# NAV-SCHED-01: coordinated navigation experiment access

Updated: 2026-10-21 (America/New_York).

## Authorization and ownership

Joey requested concurrent planning/research for Track A (native navigation reuse),
Track B (world/collision evidence), and Track C (controller/test framework), with
intelligent queuing whenever live experiments would conflict. He authorized
starting this work in this conversation. This increment implements and validates
coordination offline; it does not authorize new live movement or deploy a host.
The existing reviewed live experiment/identity/stop gates still apply.

The current implementation owner is this ChatGPT coordinator. No independent
workers have been launched. Exclusive new-file lane: `scripts/nav_access_queue.py`,
`tests/test_nav_access_queue.py`, and this document. The coordinator also owns the
narrow validation-script and status/index integration. Do not change the RRE
roadmap, native control transport, deployed runtime, or unrelated research files.

## Milestones

1. Inspect existing control and stop/release boundaries: complete. The native host
   serializes individual actions, not durable multi-worker experiment ownership.
2. Durable queue core and offline contention/recovery tests: implemented; 42 new
   tests passed, with 53 existing control-path regressions (95 focused tests).
3. Connect lease enforcement to the native host and all conflicting control paths:
   **partially implemented offline as NAV-SCHED-02A**. The send-boundary fence,
   optional gateway policy and STOP/release queue bypass pass fake-guest tests.
   NAV-SCHED-02B now adds offline-tested pinned-session watchdog and receipt-based
   cleanup. NAV-SCHED-02C now qualifies bounded frame sends and uncertain-delivery
   handling offline. Live startup identity collection and manual/legacy adapters
   remain pending. No runtime enable flag is exposed;
   the running host is unchanged. See [dispatch evidence](../validation/navigation-dispatch-fence-2026-10-21.md).
4. Offline host acceptance: stale tokens, STOP bypass, interrupted action, release
   failure, reconnect, manual operator, and concurrent worker requests: pending.
5. Separately approved bounded live acceptance with fresh identity and screenshot
   evidence: pending. No live client is touched by milestones 1 or 2.

## Shared design

Use one authoritative local SQLite database outside worker worktrees. All clients
must use that exact configured absolute path. Multiple database files would create
independent authorities and are not valid coordination. State belongs in ignored
`artifacts/navigation-access/`; it must not be committed or silently recreated.
No new service, network listener, dependency, or background agent is required for
the offline core.

Requests declare exact resource epochs, owner, research track, dependencies,
priority, estimated duration, and benefit to other tracks. Acquire every required
resource atomically or none. Example resource keys: `vm:rift-lab-1`,
`vm:rift-lab-2`, and `host:desktop-input`. Separate VMs may run concurrently only
when their declared resource sets truly do not overlap. Canonical lowercase keys
prevent accidental case aliases; verified VM/process identity remains the host
adapter's responsibility.

Priority aging raises older eligible requests above newer high-priority work.
It does not guarantee a deadline for work whose required resource set never becomes
available together. Shared-benefit and shorter estimated experiments break equal-priority
ties, followed by FIFO. Dependencies are accepted only for existing requests,
preventing cycles. Idempotency reuses an exact request ID/specification, not an
assumption that superficially similar experiments are equivalent. Completed
requests retain evidence references for reuse by all tracks.

Each grant has a random token, per-resource generation, bounded heartbeat deadline,
and hard experiment deadline. Timeout, cancellation, epoch change, and normal
completion require cleanup; expiry never immediately hands a client to the next
worker. Cleanup needs fresh matching-epoch/generation stop/release evidence for
each resource. Missing or negative evidence keeps that resource unavailable.
The queue records cleanup attestations; only the future trusted host adapter can
establish that they correspond to actual game/input state.

After uncertainty, do not automatically replay an experiment. Preserve its result
and evidence, reconcile cleanup, and submit a new explicit attempt if appropriate.
Persisted leases survive opening another queue instance. Clock rollback blocks
operations and quarantines active work until time catches up and cleanup is
reconciled. None of these offline records proves live game response.

## Evidence and next handoff

Baseline: `5b9e4a37378b5ba89b57654c8f91643925d8ba60` on
`codex/modular-foundation`. The first run found a test-only SQLite connection left
open during Windows temporary-directory cleanup. Explicit connection closing fixed
it; production queue connections already used explicit finally/close handling.

Focused acceptance on Python 3.14: 95 tests passed, including all 42 queue tests.
Workbridge job: `navsched-20261021-regression-01`, exit code 0. The original focused
run is `navsched-20261021-tests-01`; it intentionally remains available as failure
history rather than being overwritten. The new test module is included in
`scripts/validate.ps1`.

Full repository gate: passed on 2026-10-21, job
`navsched-20261021-full-gate-01`, exit code 0. Results: 364 C# tests, 216 Python
tests, 108 Lua lifecycle/encoder checks, 22 Lua/C# shared cases, locked restore,
zero-warning Release build, formatting/module checks, deterministic replay,
synthetic published-native smoke, and 266 relative links. Log:
`artifacts/navsched-20261021/full-gate-01.log`. Generated evidence:
`artifacts/validation/20261021T133445Z-4c3b1dd5`. The final handoff additions are
documentation-only and receive a separate final link/whitespace check.

No independent AI or human code review is claimed. The acceptance suite exercises
separate processes, but they are test contenders, not research workers.

Verified offline scenarios include eight competing threads and six synchronized
independent processes, each producing exactly one grant for the shared resource;
three A/B/C simulated owners transferring only after cleanup; independent VMs;
shared host-input exclusion; all-or-none reservations; no partial grant after an
injected database failure; abrupt process exit after a grant and mid-transaction;
restart; failed/stale cleanup; stale epochs; cancellation; clock rollback;
dependencies; request replay; priority aging; and heartbeat hard limits.

These are synthetic experiments, not six AI agents or live navigation. There is no
new production queue database and no host, guest, VMware, RRE, or V1 change.

## Use and important boundaries

`AccessQueue` is a small Python API plus a one-operation JSON CLI. Use Python 3.12
or later (validated here with 3.14), one absolute local database path, and an
existing parent directory. Initialization refuses to overwrite any existing file;
normal operations refuse to recreate missing state. Do not delete or copy a queue
database as a way to recover an uncertain live experiment.

From the repository root in PowerShell, an explicit initialization is:

```powershell
python scripts/nav_access_queue.py --database '<absolute-shared-database-path>' --initialize
python scripts/nav_access_queue.py --database '<absolute-shared-database-path>' --request '<request-json-path>'
```

A status request file is:

```json
{"operation":"status","arguments":{"after_sequence":0,"limit":100}}
```

Supported operations are `register`, `submit`, `dispatch`, `check`, `heartbeat`,
`finish`, `cancel`, `cleanup`, and `status`. The API method signatures in
`scripts/nav_access_queue.py` define their exact argument names. `status` also
reconciles expired leases, so it is not a pure database read. Every operation
checks expiry; nothing runs in the background without a future caller/watchdog.

Resources start blocked. The trusted coordinator/adapter must establish their real
identity and supply fresh cleanup attestations before use. Registration and cleanup
are trusted local management operations, not an authentication boundary. Current
cleanup records reference evidence but do not read or independently validate the
referenced artifact. No real cleanup attestation was fabricated during this work.

`submit` replays only an identical request ID/specification. `dispatch` returns one
private token; status and the database audit omit the token itself. Do not publish
or log dispatch output. An uncertain dispatch response must be reconciled using
status, not blindly repeated: the core deliberately does not reissue a lost token
or replay an experiment. The reserved resources remain held until expiry and
cleanup. Terminal attempts need a new explicit request ID to run again.

Default heartbeat TTL is 5 seconds; allowed TTL is 1-30 seconds. The independent
hard deadline defaults to 30 seconds and is capped at 120 seconds. Cleanup requires
exact current epoch/generation, explicit true stop/release and false in-flight
flags, and an observation no older than 5 seconds that does not predate quarantine.
Tokens and generation checks are necessary but not sufficient for live fencing.

## NAV-SCHED-02A checkpoint — 2026-10-21

The first send-admission slice is implemented and tested offline. All cooperative
queue API transactions share a canonical-path OS fence with send admission.
`QueueDispatchPolicy` checks the exact required resources and current token/epoch/
generation after action/send-lock waits. Guest replies do not hold the fence or a
SQLite transaction. STOP/release bypass lease validation and invalidate older
local queued commands. Direct session and unleased HTTP paths are tested.

The focused gate passed 122 tests (27 new); the full gate passed 364 C#, 243 Python,
108 Lua checks and 22 Lua/C# cases. Same-authority cross-process cancellation,
worker death and existing eight-thread/six-process queue tests passed. These are
fake agents/guests, not live players or AI workers. The full report records
cooperative/mixed-version limits and the unqualified stalled-send boundary.

The optional policy is not wired into production configuration or enabled on the
current host. No real queue database, live cleanup attestation, input pulse,
reconnect or runtime deployment was manufactured to declare readiness.

## NAV-SCHED-02B checkpoint — watchdog cleanup, offline

A pinned one-VM/session watchdog now reconciles expiry, requests STOP, drains
protected calls and verifies fresh matching guest release state before publishing
cleanup with a saved receipt. Failures and shutdown retain blocked ownership.
Shared host/other VM resources cannot be freed using this guest's evidence.
Construction is inert; the explicitly owned stoppable loop is tested only with
fake guests. See [watchdog evidence](../validation/navigation-watchdog-cleanup-2026-10-21.md).

Focused tests passed 163 (41 new); the full gate passed 364 C#, 284 Python, 108 Lua
checks and 22 shared cases. No running host was restarted or live input sent.
The production composition root still enables neither admission nor watchdog.
Remaining deployment prerequisites are bounded transport sends, fresh startup
identity/authority registration, and manual/VM-console/legacy path coordination.

## NAV-SCHED-02C checkpoint — bounded transport, offline

Frame-send progress and send-lock contention are now bounded. Nonblocking receive
framing preserves partial/coalesced responses. Partial/failed writes close the
session, fail pending callers and are not replayed. The watchdog keeps cleanup
blocked when delivery is uncertain. Focused tests passed 195 (32 new), the full
Python gate passed 316, and repeated transport runs passed 96/96 executions.
See [transport evidence](../validation/navigation-bounded-transport-2026-10-21.md).
This closes the offline stalled-send qualification task, not all deployment gates.

## NAV-SCHED-02F checkpoint — owned supervision, offline

The startup preflight/prepared-authority components now feed one explicit owned
supervisor lifecycle. `start()` waits for saved verified cleanup and a running
watchdog before admitting protected sends. `stop()` retains ownership until its
join completes; pending shutdown and unverified release are not called success.
Failure/expiry uses the existing watchdog and never replays experiments.

Startup registration requires an absent row atomically, closing a reproduced
check-then-register race. Same-session preparation excludes competing cleanup;
a refused new supervisor cannot disable the old owner. New tests cover actual
six-process contention, worker handoff, timeouts, faults and shared shutdown.
See [owned supervisor evidence](../validation/navigation-owned-supervisor-2026-10-21.md).
The recovered live native host remains healthy and unchanged; no scheduler
runtime activation occurred as part of this source increment.

## NAV-SCHED-02G checkpoint - native caller ownership, offline

HTTP, CLI and browser callers now forward an explicit lease envelope to the
existing send-time policy. Invalid/missing/stale credentials are rejected by
coordinated sessions; older hosts reject the envelope instead of ignoring it.
STOP/release/status stay credential-free. Private panel imports cannot silently
fall back to unleased mode, and ownership changes invalidate capture review.
An internal denied-first gateway option suspends each new/reconnected session
before publication, with no inherited policy or implicit resource reset.

Focused validation passed 259 tests and eight added panel scenarios; the full
gate passed 364 C# / 380 Python plus Lua contracts. See
[native caller evidence](../validation/navigation-native-callers-2026-10-21.md).
No production activation or new live queue occurred. Credential transport is not
lease acquisition/renewal; the coordinator remains responsible for those operations.

## NAV-SCHED-02H checkpoint - shared console exclusion

The coordinated gateway can hold the established Windows per-VM console mutex
for its lifetime. Native requests borrow it across threads while retaining all
lease/VM checks; known V1/V2 console/bootstrap and legacy experiment callers
cannot interleave, including between native requests or after guest reconnect.
Native STOP remains available. Pending local lock release is reported honestly,
and wrong-thread release is refused. The actual installed legacy entrypoints
were checked on disposable paths without modifying their source.
See [console exclusion evidence](../validation/navigation-console-exclusion-2026-10-22.md).
This is cooperative exclusion, not interception of manual VMware UI input.

## NAV-SCHED-02I — Production startup and live acceptance complete

The production entrypoint now composes denied-first sessions, one existing durable
authority, exact-target owned supervisors and the lifetime console reservation.
Same-target reconnect revokes prior tokens and queued work before verified cleanup;
process restart requires explicit existing-authority reconciliation. Shutdown
retains ownership when pending/unverified, even if diagnostic writes fail.

The recovered host is activated and a leased native capture plus rejection,
cleanup and idle-reconnect trial passed without ARM or gameplay movement. Both
full gates passed 364 C# / 441 Python and the Lua contracts. See
[activation and actual limits](../validation/navigation-coordinated-host-2026-10-22.md).

The ownership integration below is now historical. Future research should use the
existing live system, not repeat its construction or reset its durable database.
Visual review, bindings and movement-response qualification are separate gates.

## Historical pre-activation integration requirements

Gateway send admission, bounded transport, startup qualification and owned watchdog
lifecycle now have offline integration tests. The remaining composition must
install that lifecycle on every authenticated session before exposing it to
clients, without an uncoordinated reconnect window. Keep the existing send fence
and short database transactions; do not move network waiting into a transaction.
Native panel/CLI credential transport is tested, and the existing shared console
mutex now excludes known cooperating bootstrap/legacy entrypoints throughout
coordinated host ownership. Complete production per-session owner/reconnect
lifecycle and explicit maintenance handoff; never bypass the mutex to bootstrap a
missing guest. Unsupported/manual controllers remain outside this contract.
Saved-evidence analysis needs no live slot; passive live observations need their
actual effects reviewed. Only after this reconciliation should a separately
reviewed runtime activation and bounded live experiment take place.

STOP and release must bypass queued experiments. A watchdog must revoke expired
owners, stop/disarm the corresponding control session, await in-flight release,
and obtain fresh identity-bound evidence before calling cleanup. On failed or
uncertain release, keep the resources blocked. Exercise all of this with the
existing fake guest and manual-panel tests before separately approved live trials.

