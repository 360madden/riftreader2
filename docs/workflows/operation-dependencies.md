# On-demand operational dependencies

**Policy:** AGENTS.md, "On-demand operational dependencies" (2026-10-31).
RiftReader2 operations own their prerequisites. A missing process must not
be handed back to Joey as a routine manual start instruction.

## Existing components and ownership

- RIFT addon: `addon/RiftReader2/main.lua` runs inside the game. It cannot
  launch the Windows host controller. File deployment is `addon_sync.py`.
- Main-PC controller: `control_host.py`; durable coordination and console
  ownership are already implemented in `nav_host_runtime.py`.
- Main-PC controller client: `control_client.py`; this is the current
  on-demand controller startup integration point.
- Guest receiver: `guest_receiver_startup.ps1` manages its own guest startup.
- Live reader: `launch_live_reader.py` performs a bounded exact-build launch,
  requires current game identity, and may require a reviewed addon binding.

These are *separate* operational dependencies. Do not require the controller
for a simple read-only guest process inventory, nor treat a controller's HTTP
health as proof that a receiver, addon bind, or player telemetry is ready.

## Behavior implemented

`python scripts/control_client.py --config artifacts/control-fleet-live/lab1/host.json status`
(and `lab2`) performs controller preflight. It reuses the authenticated
endpoint if present; otherwise it serializes same-lab attempts with a
host-side launch lock, checks current VM identity and code/config hashes,
uses the tracked hash-pinned `controller_host_entry.py` and durable queue,
and launches one detached, non-job Pythonw host **only if the caller itself is
not job-contained**. A Workbridge terminal job cannot provide that persistent
launch authority; its call fails closed with
`persistent-launcher-unavailable-in-bounded-job`. The correct next integration
point is a purpose-built persistent process-lifecycle capability in Workbridge,
or a separately running uncontained user-session operator—not a process escape,
Task Scheduler workaround, or loosening the containment check. It waits for a current
authenticated endpoint. No VM/game startup, input, movement, lease reset,
or addon rebind happens. Errors are bounded and sanitized.

`--no-auto-start` disables recovery for explicit diagnostic status checks.
The shared `operation_dependencies.ensure_ready` helper implements ordered
health/recover/reprobe gating for future operation adapters.

## Still separate from controller startup

Controller HTTP startup alone is **not** guest-agent authentication, addon
binding, fresh source selection, or acceptance of sustained telemetry.
Player information operations must acquire their actual reader/receiver/addon
prerequisites before claiming live names, levels or XYZ. A stale game epoch
must be rejected. Windows boot alone is not a trigger; operations activate
only needed services.

If the current Workbridge process cannot launch a detached process or lacks
an interactive Windows session, return a specific blocker. A one-time
Task Scheduler attempt was rejected by the existing containment guard, and its
owned failed task was unregistered; no boot-start task was installed. Do not start a
temporary controller inside a bounded Workbridge job, disable identity
checks, copy cached plans, reset queue state or lower movement gates.

## Verification

Focused tests: `python -m unittest discover -s tests -p test_operation_dependencies.py -v`.
Actual on-demand start must be checked independently on Lab-1 and Lab-2,
with fresh authenticated status. Game input is not needed to verify host
startup. Record any blocked live attempts without claiming success.
