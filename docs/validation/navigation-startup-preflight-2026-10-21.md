# NAV-SCHED-02D — Startup identity preflight (offline)

Date: October 21, 2026. **Preflight-only checkpoint; live coordination is not enabled.**

## Scope

`scripts/nav_startup_preflight.py` provides `qualify_startup(session, resource)`.
It issues two ordinary read-only status requests through an existing authenticated
session and compares durable VM, guest, game-process, executable, window, and
geometry identity. It requires both observations to report disarmed, not busy,
no pending recovery, and no sampled held desktop inputs. It returns a proposed
VM authority epoch and identity fingerprint.

The check intentionally ignores changing command sequence counters, which
increase on each status request; treating full summaries as equal would reject
valid sessions. Foreground status is not a lease, gameplay measurement, or
proof of safe movement. The returned record is **not authorization**: it does
not register a resource, issue or renew a lease, attach a dispatch policy,
start a watchdog, send movement, or restart the game.

Invalid resource names, disconnected/changed sessions, mismatched guest/game
identity, unsafe guest state, or status transport errors fail closed. Error
messages do not reproduce private transport exception payloads.

## Evidence and limits

Focused preflight and existing access/watchdog tests passed; the new suite now
contains **11 tests**, including a real disposable gateway/guest protocol test.
The final full repository gate passed **364 C# and 327 Python tests**, plus
**108 Lua checks and 22 shared Lua/C# cases**, a zero-warning Release build,
synthetic native smoke, deterministic replay, and **288 relative links**.
Verified job: `navsched02d-fullgate-final-20261021-01`; evidence folder:
`artifacts/validation/20261021T225624Z-3ed013d8`.
The earlier full gate (326 Python tests) also passed before the additional
protocol test was introduced.

The native endpoint check from this turn failed with **WinError 10061:
connection refused**. Read-only Windows checks also found no `vmware-vmx.exe`
process and no TCP rows matching the expected control/VM listener ports
49712, 49715, or 5905. This does not prove why the VM stopped, but current
RIFT-Lab-1 connectivity is **not established**. Earlier October 21 checks did
show a live connection.
No attempt was made to restart the host, VMware, or RIFT or to infer its current
state from previous observations.

This is only the first startup integration seam. Remaining gates include:
trusted fresh status and VM identity collection from the actual target at
startup, exclusive resource registration and single-owner policy installation,
a supervised watchdog lifecycle, common ownership by manual/CLI/VM-console
and legacy paths, reviewed activation, and an independently observable
bounded live test. No action was sent to the live game.

## Reproduce

From `C:\work\riftreader2`:

```powershell
python -m unittest tests.test_nav_startup_preflight -v
```

The new tests are included in `scripts/validate.ps1`. Read the
[current handoff](../status.md), [access queue roadmap](../planning/navigation-access-queue.md),
and [watchdog validation](navigation-watchdog-cleanup-2026-10-21.md)
before resuming. No independent review or agent swarm is claimed.
