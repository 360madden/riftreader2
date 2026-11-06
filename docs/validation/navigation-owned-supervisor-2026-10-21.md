# NAV-SCHED-02F — Owned supervisor lifecycle

Date: October 21, 2026 (America/New_York). Scope: tested startup, supervision and
shutdown composition. **Not activated on the live RIFT-Lab-1 host.** The recovered
native connection is retained; the user asked for autonomous continuation.

## Current target detection

The existing VM guard freshly matched the exact VMX, VMware log epoch, process
start time, executable and console-listener owner before requesting native status.
At the opening check, the recovered VM PID 52872 and RIFT PID 11748 matched the
prior recovery, as did guest instance ad6bffc45e804a879a00d6f2a4c299df. Status was
connected, foreground, idle, disarmed, without recovery or sampled held inputs.
These are observations, not pinned identities to reuse after another restart.
No image, ARM, movement, STOP, reconnect or runtime restart is needed for this
source-validation milestone. Final live status is separately retained.

## One real startup defect reproduced and corrected

The earlier prepared-authority helper checked that a resource did not exist,
then registered it in a separate transaction. A private interleaving inserted a
competing resource between those operations. The original helper replaced that
resource instead of refusing startup. The expected rejection test failed against
the baseline; its actual exit-1 output remains in the evidence.

Registration now supports `require_absent=True`: existence is tested inside the
same transaction as insertion. Startup never reconciles an existing resource,
even when its epoch matches. Existing trusted registration/reconciliation keeps
its previous default behavior; this is not a new authorization boundary or schema
migration. Six independent test processes proved exactly one successful startup
registration with the winning epoch unchanged.

A session preparation boundary also excludes concurrent composition and cleanup.
It checks for an existing policy before suspending anything, so a rejected second
supervisor does not disable the first. It invalidates old queued control calls,
waits for protected calls to settle and leaves failures suspended. No database
transaction or transport-send lock spans the two identity observations.

## Explicit owned lifecycle

`OwnedSupervisor` in `scripts/nav_supervisor_bootstrap.py` composes the existing
preflight, queue policy and watchdog. Construction sends nothing and starts no
thread. Explicit `start()` creates one non-daemon, joinable thread for one pinned
session and one resource. It cannot restart itself or switch to another session.

The owner does not report running until the original watchdog has completed
identity-bound STOP/drain/status verification, saved its receipt, published queue
cleanup and recorded lifecycle evidence. A policy wrapper checks the supervisor's
running state and live thread at the actual dispatch boundary. Thus a clean queue
row by itself cannot admit actions during the short interval before readiness.
Only the successful start caller opens admission after accepting readiness; a
late cleanup completion cannot publish running after that caller timed out. The
readiness receipt explicitly says admission is still pending, not that startup
already succeeded.
STOP, release and status retain their existing bypass of experiment admission.

The runner continues the existing watchdog ticks. Lease expiry, cancellation or
completion uses the same release-backed cleanup path; it never replays a worker's
action. A disposable two-worker case held the first action, let its lease expire,
observed cancellation and cleanup, and granted the second worker only afterward.
The first token could not send again, and each intended fake action ran once.

Explicit `stop()` closes admission, requests runner termination, and joins for
its caller-supplied wait budget. It does not terminate the thread by force. The
watchdog blocks the resource, attempts STOP/drain/status and retains a blocked
resource even on verified shutdown. Repeated/concurrent stop callers share that
same shutdown rather than issue independent cleanup attempts. A finite join wait
can return `terminationPending: true`; this is not successful termination or
proof of release. The caller must keep ownership and inspect/join again.

A start timeout requests shutdown instead of allowing late readiness. A failed
queue, evidence write, guest response, thread launch, unexpected runner exit or
identity change fails closed. Error reporting omits private exception payloads.
The shared watchdog runner boundary prevents a competing loop from using the
same watchdog. Neither supervisor failure nor shutdown automatically resets an
existing authority, reconnects a guest, restarts a worker, or grants another lease.

## Validation evidence

The expanded focused suite passed **237 tests**, including **25 new lifecycle and
startup-race cases**. The full isolated gate passed **364 C# tests, 358 Python
tests, 108 Lua checks and 22 shared Lua/C# cases**, locked restore, zero-warning
Release, published synthetic native smoke, formatting and deterministic replay.
Focused and repeated checks overlap the full suite; they are not additional
unique regression cases. The evidence directory records each actual run and
complete output, including the original failed baseline.

Tests use disposable authorities, loopback fake guests, bounded threads and
local child processes. They do not establish a live gameplay response or create
AI subagents. The first repetition matrix ran four times with at most two runs
concurrent, passing 92 executions of the same 23 cases while the full gate ran.
Two timeout tests were then strengthened to wait for observed fixture entry
rather than assume entry occurred before the caller deadline. Final run evidence
pins the exact promoted bytes; a final four-run matrix exercises all 25 cases
(100 repeated executions). It includes the final full gate and main-checkout
regression; inspect `milestone-complete.json` for actual completion results.

## Supported use and limits

An integration owner may construct `OwnedSupervisor(session, queue, resource,
journal)`, then call `start(timeout_seconds=10)` and always call
`stop(timeout_seconds=10)` in its shutdown path. The queue must already exist;
resources must not be silently deleted to make startup succeed. A stopped owner
is single-use. Existing resource reconciliation needs separately verified
management, not a new object that pretends to be the former owner.

The wait parameters bound readiness/join waits, not arbitrary filesystem stalls,
OS scheduling, or all work done before/after a wait. A pending thread remains
owned. Hard process/OS failure is not successful shutdown; remote disconnect
behavior and explicit later reconciliation remain necessary. The fence and
management APIs are cooperative, not authentication against direct SQL, old
callers, other authority databases or other Windows sessions.

Normal `control_host.py` startup still does **not** construct the supervisor.
The already running recovered host keeps its loaded code and configuration;
source promotion does not hot-reload it. This increment does not reconcile the
manual panel/CLI, VM-console bootstrap, or legacy callers, and it does not claim
complete multi-controller exclusion. The next integration must route those
callers through the same ownership contract and ensure every newly authenticated
session starts blocked before publishing it to clients. Only then activate and
verify against the freshly detected lab target.

## Resume

Evidence: `artifacts/navsched02f-20261021-01/evidence/`.
Report: this file. Handoff: [current status](../status.md).
See the [queue roadmap](../planning/navigation-access-queue.md),
[watchdog](navigation-watchdog-cleanup-2026-10-21.md), and
[connection recovery](native-control-recovery-2026-10-21.md).

All pre-existing dirty source, Git staging, HEAD and live configuration were
baselined. The final verifier checks only intentional source/document differences.
No dependencies, credentials, firewall, services, global settings, unrelated
projects, commits or pushes are part of this increment. Review is by the
implementing assistant, not an independent reviewer.

Model: GPT-6 Astra Pro. Reasoning level:
