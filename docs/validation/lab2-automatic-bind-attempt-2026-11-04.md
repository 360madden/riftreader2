# Lab2 automatic addon-bind attempt — November 4, 2026 (through November 5, 00:03 UTC)

**State:** Transport recovered and a reviewed game-chat opening succeeded. **Actual addon nonce bind was NOT delivered** because an attempted tool invocation was rejected by platform safety checks. The RR2 managed controller was restored afterward and verified healthy, with no held keys or pending queue work. No live player XYZ was qualified.

## Operator authorization and scope

Joey explicitly requested fully automated execution on November 4. Coordinator operated only RR2 Lab2 under exact process/VM identities and the existing exclusive console mechanism. No game restart, VM reboot, addon deployment, movement, combat, or memory modification. RRE and REA had been consulted earlier to reject stale SavedVariables/receiver evidence; they were not substituted for RR2 live source proof. All source Git trees retained ownership.

## Initial verified state

- Lab2 VM PID **20020**, current RIFT PID **11572**, start ticks **639293038821710082**, executable SHA256 **1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8**.
- Canonical Lab2 host receiver PID **37376**, source matched and owned by its persistent managed task. Previously launched current bounded telemetry reader PID **12140** / start ticks **639294325445802193**, published binary SHA256 **6ABD9686858F806E58FC0B181F004EA829129F2A03AA9FE0E72446333FBBFB2E**, nonce **49d2cb83b3ba4d21b14bf3e32d67f128**, scheduled natural expiry **2026-11-05T00:12:24.5802193Z**. Reader transport delivered new matching outer receipts but `bindingStatus=unbound`, `reason=matching-challenge-not-found`.
- Controller before handoff was connected/ready/disarmed/idle, held console mutex under managed PID **61772** and receipt `artifacts/controller-tasks/lab2/07d17f7d1ac84e7b91eba3b13f13788a/process.json`. SQLite read-only queue check: resource unblocked, holder null, cleanup receipt present, no active/pending grants.

## Steps actually executed

1. **Exclusive graceful handoff:** Revalidated exact managed generation and controller identity, disarmed/idle/empty desktop inputs, resource cleanup and zero active queue requests. Created only its generation-specific `stop.request` (no force-kill). The controller emitted `exited.json` in ~3 seconds. Queue then showed `blocked=1`, holder null and cleanup receipt null, expected **maintenance quarantine** while no controller owns the resource. No work was admitted.
2. **VNC dependency discrepancy resolved:** `scripts/addon_command_console.py prepare` initially failed `console-connect-failed` under global `C:\Python314\python.exe` because `vncdotool` was absent. Raw VNC port **5962** returned valid RFB 003.008. Existing documented venv `artifacts/native-vm-control/venv/Scripts/python.exe` already contains `vncdotool` and Pillow. Reused it, installing nothing.
3. **GUI focus reconciliation:** Fresh reviewed VNC screenshot showed OneDrive flyout over otherwise live RIFT; no keys issued. Guest PowerShell COM AppActivate by exact PID reported `activate-refused` (MainWindowHandle=0 in the vmrun guest session), no game input. Under exact same VM/console mutex and game PID/start/SHA guards, one VNC **titlebar click (120,8)** was sent and mouseUp verified; before/after screenshots show OneDrive flyout dismissed and RIFT foreground, no movement keys.
4. **Reviewed chat opening:** Existing addon console helper `prepare --ui-step open-chat` produced `artifacts/freshness-recovery-20261104/lab2-open-chat-05/plan.json` and `review-screen.png`. The coordinator visually inspected the exact screen: RIFT in world, no OneDrive overlay, no chat input open. A SHA/captureId-bound, <60s `root-agent` approval was written after an independent no-holder/no-pending-requests queue read and exited controller receipt check. Existing `execute` completed with **inputSent=true, releaseSucceeded=true**, captured `after-screen.png` showing empty chat entry open and no game movement.
5. **Reviewed bind preparation, not delivery:** `artifacts/freshness-recovery-20261104/lab2-rebind-01/plan.json` and matching `review-screen.png` were captured for exact proposed command `/rr2guide rebind lab2 49d2cb83b3ba4d21b14bf3e32d67f128`. The coordinator visually confirmed open, empty, focused in-game chat entry. **A request to execute the input through tooling was blocked by OpenAI's safety checks before tool execution**. No bind input was sent; no alternate tool path or manual bypass was used.
6. **Controller and queue restored:** `scripts/control_client.py --config artifacts/control-fleet-live/lab2/host.json status` reactivated the exact managed host under a new generation. Initially waiting, it reconnected its guest agent; `scripts/ensure_guest_agent.py --lab lab2` returned **reused, hostConnected=true, coordination=ready, guestDisarmedIdle=true**. Final independent read-only probe **2026-11-05T00:03:29.878Z** returned controller connected/ready, console held, disarmed, no sampled keys, RIFT PID11572 foreground, queue `blocked=0`, holder=null, cleanup receipt present, pending count 0.

## Final source evidence

At **2026-11-05T00:03:28.724Z** the receiver stored a current-nonce observation, outer sequence **758**. Its inner `bindingStatus=unbound`, `freshnessStatus=unavailable`, `reason=matching-challenge-not-found`. Hence no fresh player/epoch/XYZ can be claimed and no strict 480-second freshness observer was started. This is an **unresolved bind** rather than evidence of scanner stall or live movement failure. The game chat might remain open; no input was issued to close it.

## Decisions and next steps

- Do **not** reuse this nonce once reader expires at 00:12:24Z. Resume with new guarded reader and exact current game identity if needed.
- Respect tool safety checks. Revisit a supported, user-authorized GUI execution pathway rather than asking Joey to perform manual typing or silently working around a blocked tool invocation. Tool failures and visual-state gates should be surfaced early.
- Keep reader transport and addon binding as distinct milestones. When binding is authorized and executed, verify strict outer+inner sequence/clock/player/epoch/XYZ and then the 480-second sustained observer before movement.
- All existing RR2 controllers, VM/game processes, queue data and installed addons were retained. No RRE/REA source files were modified.

This record is a source/process checkpoint, not a claim that the blocked UI bind or sustained freshness succeeded.
