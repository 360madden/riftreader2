# RiftReader2 live controller/receiver handoff — 2026-10-31

Checkpoint: 2026-10-31 17:15:38 UTC / 13:15 EDT. **Read-only recovery;
no gameplay input, movement, VM/game restart, addon rebind or queue reset.**

## Observed live state at checkpoint

| Dependency | 🟦 RIFT-Lab-1 | 🟪 RIFT-Lab-2 |
|---|---|---|
| Main-PC controller | ✅ Connected; coordination ready; supervisor running | ✅ Connected; coordination ready; supervisor running |
| Guest input state | ✅ Disarmed/idle, zero held keys | ✅ Disarmed/idle, zero held keys |
| RIFT game PID | 8164 | 7012 |
| Foreground game | ❌ **False** | ❌ **False** |
| Host-only receiver | ✅ PID 23264, 192.168.56.1:49813 | ✅ PID 37376, 192.168.56.1:49923 |
| Read-only reader PID at check | 1268 | 11012 |
| Reader expiry | 17:15:57Z (time-scoped) | 17:15:47Z (time-scoped) |
| Receiver sequence at checkpoint | 515 | 665 |
| Addon source | ⚠️ Unbound; no player fields | ⚠️ Unbound; no player fields |

The readers delivered HTTP-200 observations with advancing sequences, but
*unbound* observations are **not** player telemetry. Do not reuse their nonces
after the bounded processes expire. Both installed guest Lua addons matched
source. Main-PC OneDrive guidance.lua became an Offline placeholder again;
addon_sync.py sync --target pc replaced it with pinned, verified source,
without a game reload. Watch for repeat OneDrive offloading.

## Implemented

- ensure_receiver.py automatically reuses or starts each exact, unchanged V1
  read-only receiver under Workbridge on-demand managed tasks, no boot triggers,
  with pinned source SHA256, private config, listener owner/process epoch and
  matching task receipt. Independent second job reused both processes.
- receiver_task_entry.py runs directly under the existing managed-helper task,
  with no escaping child or input endpoints.
- launch_live_reader.py ensures this receiver when the caller supplies the
  canonical per-lab private config. Other configs are never silently started.
- Controller watchdog sends an authenticated, identity-checked read-only status
  every **45 seconds**, inside the guest control agent's 120-second idle read
  timeout. Previously the guest disconnected at ~120 seconds, requiring
  supervisor reconciliation; intermittent queue contention also blocked both.
- ensure_controller.py rejects a live HTTP endpoint whose supervisor is blocked.
  No duplicate owner or unsafe controller takeover is attempted.
- Both controllers underwent verified idle **graceful** task shutdown/exit,
  were restarted with new watchdog code and returned to coordinated readiness.
  Lab1 journal showed status heartbeats at 17:11:53 and 17:12:38 UTC. At
  17:15:38 UTC, both were still ready and guests had no held input.

Focused tests: 9 receiver, 13 dependency and 43 watchdog tests passed.
Broader controller/host regression: **132 tests passed**, Windows Python
compile passed. See repository Git history for the local commit.
See [operational dependencies](operation-dependencies.md).

## Remaining live player-data gate

A reviewed queue-leased Lab1 screenshot request correctly refused with
"RIFT must already be foreground." Its request was canceled, the watchdog
cleaned the resource and an independent read-only queue check returned no
pending/active/cleanup requests. Lab2 also reported isForeground=false.
No attempt was made to evade this protection.

Once RIFT is in the foreground on each guest through an authorized route:

1. Reacquire current game/VM identities, verify installed addon files and
   controllers, and use launch_live_reader.py to start a *new* bounded
   read-only reader; its canonical receiver auto-recovers as needed.
2. Review a fresh screenshot, then perform allowlisted /reloadui and
   /rr2guide bind labN NONCE per game's current UI state. Never
   silently rebind or assume an old nonce still works.
3. Require advancing nonce-pinned fresh observations and qualified player
   fields before presenting player names, level, coordinates or live movement
   readiness. Lab1 still **fails** the 480-second movement freshness criterion.
   No movement trial until a separate strict requalification passes.
