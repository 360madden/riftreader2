# NAV-SCHED-02H - Shared console exclusion

Started October 21 and validated October 22, 2026 (America/New_York), using the
Windows host's recorded clock. This is an offline-qualified integration increment,
**not activation on the recovered RIFT-Lab-1 host**.

## Conflict closed without rewriting legacy tools

The native VM guard previously acquired the established Windows console mutex
only for individual identity/ARM/action operations. The baseline compatibility
probe confirmed that a legacy process could acquire it after a native operation
completed. That was existing per-command behavior, not a claimed spontaneous
production failure.

A gateway constructed with both `require_supervisor=True` and
`exclusive_console=True` now reserves the same canonical per-VM mutex before
opening its listener and keeps it during idle periods, guest disconnects and
supervisor shutdown. Known console callers receive `controller-busy` rather than
interleaving Windows bootstrap input with native ownership. No second lock naming
scheme, external source patch, dependency, credential or service was introduced.

Native request threads borrow the reservation within the same guard. They still
verify the exact VM identity before and after each protected operation; capture
is included in exclusive mode. Borrowing does not bypass the session's lease,
review/ARM, or supervisor checks. A changed identity blocks later protected calls
while retaining console exclusion. STOP, release and status retain their existing
path and remain available to the authenticated native operator.

New-session publication remains denied-first. A reconnect gets no previous lease
or policy, but it does not relinquish the gateway's console reservation. Status
reports local reservation state even while no guest is connected.

## Ownership and shutdown contract

The Windows mutex belongs to the thread that acquired it. Acquisition and release
must occur on that same thread; wrong-thread release is rejected without closing
the owned handle. A duplicate start or ownership attempt cannot release the
original reservation. A failed initial identity/listener setup releases only its
own new reservation. Startup is single-use.

Release first stops admission and waits for borrowed native requests to finish.
A finite wait can return `releasePending: true`; the mutex remains held until an
explicit owner-thread retry. Returning from the last request alone does not
silently unlock it. Closing during acquisition cannot publish a late reservation.
After release the guard cannot fall back to uncoordinated operation.

The host integration must stop and join its supervisors, perform release-backed
cleanup, close guest sessions, and only then release the console reservation.
**Local mutex release does not certify that guest keys were released.** A stalled
or unverified cleanup must not be converted into a successful handoff. The new
reservation primitive does not force-terminate threads or manufacture cleanup
receipts. A hard owner/process exit may abandon the Windows mutex; the next owner
must still establish identities and fresh guest cleanup rather than inherit trust.

Console bootstrap remains a maintenance operation, not a concurrent queue worker.
During exclusive native ownership, even console capture is conservatively refused.
Native capture remains the supported leased observation path. Restoring a missing
receiver requires explicit native-owner shutdown/maintenance handoff before using
console bootstrap; no automatic bypass is added for connection loss.

## Verification and evidence

The focused control suite passed 286 tests, including 27 new Windows reservation
cases. The tests use disposable VM paths, real named mutexes and child processes,
plus existing fake native guests and queue supervisors. No live game input or
live console reservation was used. The full isolated gate passed **364 C# tests,
407 Python tests, 108 Lua checks and 22 shared Lua/C# cases**, locked restore,
zero-warning Release, synthetic native smoke, formatting and deterministic replay.
Job: `navsched02h-full-gate-20261021-01`; candidate evidence:
`artifacts/validation/20261022T041159Z-10a51a3c`. The focused counts overlap the full
suite. Post-promotion main-checkout and preservation results are separate evidence
in `milestone-complete.json`, not inferred from this isolated gate.

The installed V1 mutex and actual V1 observe entry point were tested with all
state redirected to a disposable directory and transport forbidden. They were
blocked while reserved and could acquire the mutex after explicit release. The
repository's legacy experiment prepare/run/recover entry paths were also tested
with a no-input fake adapter and the actual installed V1 mutex. Source hashes
before/after matched. Python bytecode writes were disabled for external imports.

Two initial compatibility-harness attempts are retained as failed: one captured
an argument after the harness replaced argv, and one omitted the run parser's
required review note. The corrected harness pinned the temporary VM path and
provided the fixture-only required argument. Neither failed attempt accessed the
real VM or was relabelled successful.

The known V1/V2 console namespace is a cooperative lock in the current Windows
session. This does not exclude manual VMware UI input, arbitrary direct socket
clients, altered tools, another Windows session, path aliases producing another
key, or code deliberately bypassing entry-point locks. V1 source remains read-only.
No general security or universal multi-controller exclusion claim is made.

## Resume

Evidence: `artifacts/navsched02h-20261021-01/evidence/`.
Read `milestone-complete.json` for actual final validation and preservation results.
The normal production entry point still uses its previous defaults. Source
promotion does not hot-reload the recovered host or enable this reservation.

Next: wire denied-first per-session supervision and explicit existing-resource /
reconnect reconciliation into production startup, then review activation and a
bounded live trial. Known cooperating console/legacy paths are now excluded by
the shared lifetime reservation when enabled; they are not magically converted
into lease-acquiring workers.

See [status](../status.md), [queue roadmap](../planning/navigation-access-queue.md),
[native callers](navigation-native-callers-2026-10-21.md), and
[native controls](../reference/native-vm-controls.md).

Model: GPT-6 Astra Pro. Reasoning level:
