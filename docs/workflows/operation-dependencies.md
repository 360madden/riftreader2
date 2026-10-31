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
- Guest control agent: `ensure_guest_agent.py` uses a cached VM-specific guest
  login and the installed launcher to recover a safe, interactive agent on demand.
- Live reader: `launch_live_reader.py` performs a bounded exact-build launch,
  requires current game identity, and may require a reviewed addon binding.

These are *separate* operational dependencies. Do not require the controller
for a simple read-only guest process inventory, nor treat a controller's HTTP
health as proof that a receiver, addon bind, or player telemetry is ready.

## Behavior implemented

`python scripts/control_client.py --config artifacts/control-fleet-live/lab1/host.json status`
(and `lab2`) performs controller preflight. It reuses an authenticated
endpoint if present; otherwise `ensure_controller.py` serializes same-lab
attempts under a Windows lock, checks the current VM and durable queue, and
calls the existing `C:\work\workbridge-mcp\scripts\Manage-HelperTask.ps1`
manager to register/start exactly one `rr2-controller-lab1` or `rr2-controller-lab2`
task. The manager enforces an exact principal/action/argument registration, a
Limited interactive user token, unlimited task lifetime, IgnoreNew duplicates,
and **no AtLogon trigger**. `controller_task_entry.py` runs *as the managed task
process itself* (no escaped child); it independently checks task ownership,
VM identity and loopback ownership, and records source/config hashes before loading the
existing coordinator with the preserved SQLite queue. The caller waits for a
current authenticated API response. No VM/game startup, gameplay input, queue
reset, addon rebind or boot-wide startup happens. Errors fail closed and are
sanitized. The manager's task is only started because a RiftReader2 operation
requested its dependency, and survives the bounded requesting Workbridge job.

`--no-auto-start` disables recovery for explicit diagnostic checks.
For `capture`, reviewed `arm`, and `action`, `control_client.py` also calls
`ensure_guest_agent.py`; `status`, `stop`, `release` and `recover` do not
silently start an absent guest agent. Direct two-lab recovery is
`python scripts/ensure_guest_agent.py --lab all`. It first ensures both main-PC
controllers, then probes authenticated connected/ready/disarmed status. If a
guest is missing, it requires current VM identity, the cached Windows login,
exact launcher/release/game executable hashes, the correct per-lab port, a
logged-in Windows game session, an empty pending-input journal and no
competing agent or launcher. It transfers and hashes a one-time invocation of
`Ensure-GuestAgentTask.ps1`, which registers/reuses one task per VM with a
Limited interactive token, zero triggers, unlimited runtime and IgnoreNew
duplicates. It waits for authenticated guest readiness. Invalid ownership,
unsafe state or failed reconnection blocks without movement, VM/game restarts,
queue reset or forced process termination.

The shared `operation_dependencies.ensure_ready` helper implements ordered
health/recover/reprobe gating for additional operation adapters.

## Still separate from controller startup

Controller HTTP startup alone is **not** guest-agent authentication, addon
binding, fresh source selection, or acceptance of sustained telemetry.
Player information operations must acquire their actual reader/receiver/addon
prerequisites before claiming live names, levels or XYZ. A stale game epoch
must be rejected. Windows boot alone is not a trigger; operations activate
only needed services.

If the manager, interactive session, exact task registration, current VM
identity, durable queue or controller endpoint checks fail, return a specific
blocker and preserve state. The earlier direct-detached and ad hoc scheduler
attempts failed and their owned test tasks were removed; the existing
Workbridge **managed-helper** lifecycle is the supported persistent owner.
Do not start a temporary controller inside a bounded command job, bypass
manager ownership checks, copy stale plans, reset queue state or lower
movement gates. Guest agent startup is still a separate dependency: a running
HTTP endpoint with `host.connected=false` must never be treated as game-ready.

## Verification

Focused tests: `python -m unittest discover -s tests -p test_operation_dependencies.py -v`
(11 passing on 2026-10-31), plus `test_control_client.py` (8 passing).
On October 31 the managed helper started both main-PC controllers, and
separate on-demand guest tasks recovered both missing agents. Independent
bounded jobs authenticated each API with `host.connected=true`, coordination
`ready`, `consoleReservation.held=true`, and guest disarmed/idle, no sampled
held keys. Both guest tasks were independently inspected in Windows Session 1:
Running, Interactive/Limited, zero triggers, unlimited lifetime and IgnoreNew.
A subsequent `ensure_guest_agent.py --lab all` reused both instances.
Guest agent dependency tests (9 passing) cover wiring and fail-closed behavior.
This qualifies *controller connectivity* only; fresh reader/addon source and
sustained telemetry remain separate. No game input was performed.
