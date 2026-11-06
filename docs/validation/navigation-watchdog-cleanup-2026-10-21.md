# NAV-SCHED-02B — Pinned-session expiry watchdog and cleanup

Date: 2026-10-21 (America/New_York). Scope: implemented and offline-validated
watchdog/cleanup logic; **not installed on the running RIFT-Lab-1 host**.

## Delivered behavior

The previous queue could quarantine an expired owner without sending STOP to its
already-dispatched action. A controlled fake-guest probe demonstrated the gap:
the request entered cleanup, the resource stayed blocked, and the original action
still awaited a response with only `action` sent. The expected STOP assertion
failed. This is retained evidence, not a spontaneous live-game incident.

`scripts/nav_control_watchdog.py` now provides `LeaseWatchdog`. Construction sends
no commands and starts no thread. An explicit `tick()` reconciles queue expiry;
an explicit, caller-owned `run(stop_event)` can poll it. That loop is used only in
bounded disposable tests here, not started in production.

One watchdog owns exactly one VM resource and one native session. A canonical
binding includes the supplied VMware identity, guest instance/machine, game
process/start time, executable hash/path, window and geometry. `resource_epoch`
hashes that binding. Foreground is deliberately excluded: losing focus must not
prevent a release-only STOP. Binding validates/copies supplied identity; it is not
a replacement for a future live startup identity collector.

When a resource needs cleanup, the watchdog:

1. Suspends new protected controls and invalidates older queued requests.
2. Checks fresh guest status against the pinned session/target, then requests STOP.
3. Requires explicit `stopped: true` and no pending recovery; waits for local
   protected requests to drain, including requests queued behind an action.
4. Obtains a later matching guest status: disarmed, not busy, no recovery, and no
   sampled Windows keys/buttons down.
5. Writes a hash-referenced receipt through the existing durable evidence journal,
   rechecks local identity, then publishes cleanup against the original resource
   epoch/generation. Queue cleanup enforces freshness and quarantine ordering.
6. Releases the local suspension only after successful cleanup and no intervening
   local generation change. No movement/capture/arming is replayed.

There is no SQLite transaction or queue fence held during guest status/STOP waits.
Positive evidence for this VM cannot clear shared host-input or another VM's
resource. Other resources of a multi-resource request remain blocked until their
own trusted cleanup succeeds. The journal receipt records readiness to publish;
the queue's cleanup event is authoritative for whether publication occurred.

## Failure and shutdown semantics

Missing/negative STOP, held inputs, a busy/armed guest, recovery requirements,
changed session/target/policy, old evidence, failed receipt storage or failed queue
publication leave access blocked. A failure latches the local session and the
watchdog. Subsequent ordinary ticks do not repeat commands; `tick(retry=True)` is
an explicit fresh cleanup attempt, not a replay of the original experiment.

A queue error or clock rollback attempts a release-only STOP on the still-matching
session and retains the local block. Queue state is quarantined where available;
unavailable storage cannot be magically made durable. No database is recreated,
no reconnect is silently adopted, and `recover` is never invoked automatically.

The owned runner's shutdown quarantines its resource, requests STOP and retains
that block. It does not mark the resource freely usable after supervision ends.
The loop is not an operating-system service or an independently launched AI agent.

## Disconnect issue found and corrected

The first expanded focused run passed 153 of 154 checks. In the withheld-action
response case, closing the session left its owned request waiting for the response
deadline while the reader remained blocked in the OS receive. A separate recorded
diagnostic observed both stacks and settlement near the existing timeout.

`AgentSession.close()` now explicitly fails pending local response waiters rather
than depending on the reader's eventual exit. A missing response therefore settles
as an error, never as verified release. The corresponding test still requires
cleanup to remain blocked. The original failed run and diagnostic are retained.

## Verification

Final focused suite: **163 passed**, including **41 new watchdog tests** and the
122 prior gateway/queue/control checks. Coverage includes expiry of an active
fake action, cancellation and normal finish, ownership transfer only after
cleanup, stale identities, receipt-storage failure, clock rollback, queue loss,
withheld replies, queued requests, concurrent ticks, explicit retry, reconstruction,
shutdown, exact scope and no token disclosure.

The isolated full repository gate passed **364 C# tests**, **284 Python tests**,
**108 Lua checks**, **22 Lua/C# shared cases**, locked restore, zero-warning Release,
formatting, native synthetic smoke and deterministic replay. These counts overlap:
the focused tests are a subset of the full Python gate. Full job:
`navsched02b-full-gate-20261021-01`. Generated evidence:
`artifacts/validation/20261021T200245Z-4c84f416` inside the isolated candidate.
The full gate checked 272 links before these final documentation additions;
post-promotion links and preservation have their own final record.

All deliberate failures used disposable databases, fake loopback guests and owned
test threads. No actual game movement, screenshot replacement, ARM, host/VM restart,
guest deployment or live watchdog was used to manufacture acceptance. The nine
inherited NAV-SCHED-02A changes were preserved in the starting baseline.

## Still required before live coordination

The production host configuration still installs neither the queue admission
policy nor the watchdog. Next work must qualify bounded send/stalled-transport
handling, supply fresh authoritative VM/game/guest identity at startup, and route
manual panel/CLI plus VM-console/bootstrap/legacy access through the same owner.
A suspended OS send can still block locks before a watchdog obtains control;
the 100 ms polling interval is not a hard real-time STOP guarantee.

Cooperative queue fencing does not control direct SQL, another database, old
callers, another Windows session, physical user input or external tooling. Status
samples and STOP acknowledgments are control/cleanup evidence, not proof of RIFT
consumption or autonomous navigation. New session identity needs explicit trusted
rebinding and cleanup; it is never accepted because a stale PID happens to match.

No live enable flag, new dependency, server/listener, global setting or Workbridge
change was added. Review was by the implementing assistant, not an independent
reviewer. No commit or push was created.

## Resume

Evidence: `artifacts/navsched02b-20261021-01/evidence/`. Inspect
`milestone-complete.json` for post-promotion checks and fresh closing status.
Use [current status](../status.md) and the
[access queue roadmap](../planning/navigation-access-queue.md).
The [prior dispatch fence report](navigation-dispatch-fence-2026-10-21.md) remains
historical evidence and must not be relabelled as live coordination.

From the repository root, offline validation is:

```powershell
python -m unittest tests.test_nav_control_watchdog tests.test_nav_gateway_fence tests.test_nav_access_queue tests.test_control_host tests.test_control_client tests.test_vm_console_native -v
```

Model: GPT-6 Astra Pro. Reasoning level:
