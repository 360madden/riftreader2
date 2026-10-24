# NAV-SCHED-02A — Native gateway admission boundary

Date: 2026-10-21 (America/New_York). Scope: offline-qualified dispatch integration,
not deployment of coordinated live control. Joey approved starting the next
workflow after a current RIFT-Lab-1 status check.

## Live baseline and ownership

The existing native status client reported a connected guest, RIFT PID 3400,
VMware PID 39056, the expected executable hash, foreground target, disarmed/idle
state, no recovery requirement, and no sampled held inputs. These were read-only
facts, not a new visual review or proof of current navigation behavior. No movement,
arming, screenshot replacement, process restart, guest deployment or game-setting
change is part of this slice.

The source checkout was clean at HEAD
`5263615cae38f58fedb9b15ba358aee68ec5f8ad` on `codex/modular-foundation`.
Development is isolated under `artifacts/navsched02-20261021-01/candidate`.
The existing host configuration is preserved by hash, without logging its secrets.
No independent agent or reviewer is claimed; test processes are not AI workers.

## Implemented boundary

`AccessQueue.dispatch_fence()` serializes cooperative queue operations with an
admitted transport send. All normal queue transactions use the same fence.
`QueueDispatchPolicy` accepts an exact trusted resource/epoch set and an out-of-band
`request_id`/`token` pair. It rechecks active state, token, expiry, resource ownership
and generation at the actual send point, including after waiting for another
action or the send lock. A subset or different resource set is not sufficient.

The fence uses a bounded reentrant thread lock plus a canonical-path Windows named
mutex. Windows callers must use the same interactive session and local authority
path. The POSIX fallback uses a persistent advisory lock file; it is not qualified
by the Windows run. Never remove a lock file to recover a lease.

The SQLite transaction ends before transport I/O. The cooperative fence covers
admission and the send call only, not the wait for the guest response. Thus a
cancellation can quarantine the lease while an already-dispatched command is
awaiting its result. No command is replayed automatically.

`AgentGateway` and `AgentSession` accept an optional startup `dispatch_policy`.
The policy is consulted in the session immediately before sequencing/sending,
not merely in an HTTP handler. Direct gateway and session calls therefore share
the same admission path. Presenting a lease to a session without an installed
policy is refused rather than silently implying coordination.

Capture, ARM, action and recovery require admission when a policy is installed.
Status, STOP and release bypass the queue. STOP/release also invalidate older
locally queued requests, so those requests cannot run after the stop just because
their database lease remains active. Tokens are not sent to the guest or written
to the host journal. Guest review/arm/target/release validation remains unchanged.

## Tested evidence

The controlled baseline attached a rejecting policy to the old gateway and proved
that an action was still sent; the expected rejection assertion failed. This
reproduces the missing integration hook, not a spontaneous production incident.
The negative result remains retained as `navsched02-gateway-red-20261021-01`.

Focused Windows/Python 3.14 validation passed **122 tests**, including **27 new
admission/fence tests** and the 95 existing queue/native-host/client/VM-helper
checks. New cases include exact multi-resource scope, malformed/stale tokens,
epoch changes, expiry while waiting to send, cancellation ordering, direct-session
and manual HTTP rejection, STOP/release bypass, queued-input invalidation, no DB
transaction during send work, real cross-process fencing, and worker termination
without freeing or replaying its lease. Existing eight-thread and six-process
queue contention tests still pass.

These are disposable databases, loopback fake guests and bounded child processes.
They are not live RIFT trials, six AI agents, or proof of game response. The
isolated repository full gate passed 364 C# tests, 243 Python tests, 108 Lua
checks and 22 shared Lua/C# cases, plus locked restore, zero-warning Release,
formatting, synthetic native smoke, deterministic replay and 269 relative links.
Job: `navsched02-full-gate-v2-20261021-01`; generated evidence:
`artifacts/validation/20261021T173506Z-3a28a3e0` inside the candidate. The first
launch could not resolve pwsh on PATH; the recorded installed PowerShell 7.6.7
executable was used without changing PATH or system settings. That failed
invocation is retained. Post-promotion focused/preservation checks and final
document links are separate; inspect the final summary under
`artifacts/navsched02-20261021-01/evidence` for their actual results.

## Not ready for live activation

This is the first part of roadmap milestone 3, not completion of milestones 3–5.
The ordinary host CLI/configuration does **not** install this policy yet; the
current running host remains unchanged and uncoordinated by NAV-SCHED.

The next integration must bind resources to fresh VM/game/guest/host identities,
install one authoritative policy, and implement a watchdog that revokes expired
owners, requests STOP, waits for actual release, and supplies fresh cleanup
attestations. Failed or uncertain release must keep the resource unavailable.

Manual panel/CLI lease acquisition and every conflicting VM-console/bootstrap or
legacy path still require reconciliation. The HTTP test proves an unleased route
is denied when a policy is installed; it does not supply a working leased manual
panel. Do not expose an enable flag until these paths and lifecycle checks exist.

The send call still uses the existing transport; this slice does not prove STOP
can interrupt a stalled OS socket write. STOP bypasses experiment admission, not
physical/network failure. A bounded send/stalled-transport qualification remains
a live-enablement gate. Exact target/foreground/text-entry review, fresh screenshots
and independent observations are still required for any later movement trial.

The fence is cooperative: old API versions, direct SQL changes, another database,
or another Windows session can bypass it. Mixed-version or independently managed
writers are not supported. The future deployment must own and pin all participants.
No claim is made of tamper authentication, universal scheduling, power-loss recovery
or an atomic observation of the whole game world.

## Reproduce and resume

From the repository root, the supported offline developer entry point is:

```powershell
python -m unittest tests.test_nav_gateway_fence tests.test_nav_access_queue tests.test_control_host tests.test_control_client tests.test_vm_console_native -v
```

The full gate includes the new module through `scripts/validate.ps1`. No new
package, production service/listener, global setting or standalone framework was introduced.
See [the access roadmap](../planning/navigation-access-queue.md),
[native controls](../reference/native-vm-controls.md), and [status](../status.md).

Model: GPT-6 Astra Pro. Reasoning level:
