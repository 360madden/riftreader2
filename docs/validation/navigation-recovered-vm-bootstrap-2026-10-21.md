# NAV-SCHED-02E — Recovered-VM detection and guarded startup preparation

October 21, 2026 (America/New_York). This checkpoint distinguishes VM presence
from guest-control readiness. Nothing in this milestone starts the host, VM,
guest receiver, watchdog runner, or any game control.

## Detection sequence and findings

First, read-only Windows process/listener inspection found a VMware
`vmware-vmx.exe` process **PID 52872**, started at **8:58:03 p.m. EDT**, owning
the expected VM-console TCP port **5905**. Second, `vmrun -T ws list` returned
exactly one registered running VM at
`C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`. Only after that exact
VM-path check did the control-client issue a **read-only status** request.

The status request failed with **WinError 10061: connection refused**. No
listeners were reported on the configured native control ports 49712 or 49715
at detection time. The matching VM process establishes that VMware has the
right lab VM running; it **does not** establish that RIFT, the in-guest receiver
or host control service is healthy. No game inputs, screenshot capture,
arming or release commands were sent. No restart was attempted.

## Offline prepared-authority component

`scripts/nav_supervisor_bootstrap.py` now provides an explicit
`prepare_authority(session, queue, resource, journal)` composition entrypoint.
It takes an existing authenticated guest session and an **already initialized**
durable queue. It suspends protected control calls first, collects the two
status/identity preflight observations, refuses a previously registered
resource, registers a new resource in the **blocked** state, attaches the
exact-resource dispatch policy, and constructs a watchdog bound to that
session and resource epoch.

The function does **not** start the watchdog runner or attest cleanup.
Successful preparation still leaves control suspended. A failed preparation
also stays deny-first. Only an explicitly owned and supervised later
watchdog lifecycle may perform fresh STOP/status/receipt-based cleanup
and release the local latch. Production startup currently does not invoke
this component, and it has **not** been enabled against RIFT-Lab-1.

Disposable tests covered prepared-but-blocked state, explicit cleanup,
duplicate/existing resources, mismatched game identity, disconnection and
absence of automatic cleanup. These simulate a guest; they do not prove
the recovered VM's guest receiver is reachable.

## Remaining gates

Before any live movement: confirm the control listener and authenticated guest
status against the specific recovered VM, prove fresh game/window/executable
identity, select one durable queue and supervising owner, reconcile legacy
and manual input paths, activate the policy/watchdog together with shutdown
cleanup, capture fresh screenshots, and validate a single bounded supervised
experiment. A VM running is not sufficient authorization.

See [current status](../status.md), [startup preflight](navigation-startup-preflight-2026-10-21.md),
and the [coordination roadmap](../planning/navigation-access-queue.md).
All source changes and validation results remain in the repository's normal
Git/workflow records. No commit, push or unrelated project change was requested.
