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
   pending. A queue alone cannot prevent a caller bypassing it.
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

## Next integration task (no automatic live deployment)

Read the native host/client control contract and implement gateway enforcement in
a separate narrowly owned change. Serialize lease validation and actual command
dispatch against revocation; a check-then-send gap must not admit stale commands.
Do not hold a scheduler database transaction open while waiting for network I/O.
Require a lease for every state-changing path, including review/capture/arm where
they invalidate another worker's authorization. Reconcile manual panel ownership,
VM console/bootstrap access, and legacy tooling rather than assuming they already
participate. Passive observation is shareable only where its actual effect is
verified non-disruptive; analyzing saved evidence needs no live slot.

STOP and release must bypass queued experiments. A watchdog must revoke expired
owners, stop/disarm the corresponding control session, await in-flight release,
and obtain fresh identity-bound evidence before calling cleanup. On failed or
uncertain release, keep the resources blocked. Exercise all of this with the
existing fake guest and manual-panel tests before separately approved live trials.

