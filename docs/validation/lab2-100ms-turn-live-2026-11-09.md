# Lab2 live 100 ms turn — 9 November 2026

**Operator host:** AMD-DESKTOP (verified through its dedicated Workbridge connector).
**Repository:** `C:\work\riftreader2`, branch `codex/modular-foundation`.
**Outcome:** ✅ Guest A-key down/up insertion duration **117.6375 ms** for a requested **100 ms** pulse; successful release, verified disarm, newer source feedback. **Actual heading change is not yet measured.**

## Exact live identities and recovery

- RIFT-LAB-2: RIFT PID **10876**, start UTC ticks `639297512883473394`, game SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Managed guest agent instance `83d1772125fa40c596da50b4390fed0f`, corrected published agent SHA256 `5AC4569580282DDB97BA2A9DCB08AEC2B626FCF97C4EDD04DBA08E5EC18998A3`.
- Reader PID **6500**, nonce `75fa4a7b0e934c9e82cfbacb9a38b77e`, scheduled expiry **14:36:21.951Z**. **Do not reuse it or any review/pin/lease after expiry.**
- The first screenshot-reviewed `/rr2guide rebind lab2 ...` was delivered and released but **game chat explicitly replied “Bind a reader before rebinding.”** That proves the addon load was initially unbound; the runner was not at fault.
- A new screenshot-reviewed `/rr2guide bind lab2 ...` completed. The host receiver independently showed `bound` and `fresh-scoped`, matching current nonce, position and HP **10,635/10,635**. A new source pin passed the existing strict freshness validator.
- The Lab2 managed controller was stopped only through verified idle/queue/owner-specific `stop.request` + clean exit, then recovered through `ensure('lab2')` / `ensure_guest_agent.py`. No competing console owner or guest login was introduced. Lab1 was not changed.

## Turn acceptance evidence

| Check | Observed |
| --- | --- |
| Planned action | One `a` key, hold **100 ms** |
| Down event | `keyDownInserted` at action elapsed **52.2634 ms** |
| Up event | `keyUpInserted` at action elapsed **169.9009 ms** |
| Measured held duration | **117.6375 ms** (within **100 ± 25 ms**) |
| Guest delivery and release | **true / true**; `stateUncertain=false`; `recoveryRequired=false` |
| Independent receiver sequence | **1781 → 1784** |
| Independent addon sequence | **5528 → 5534**, same addon epoch/player/reader |
| Before/after XYZ | **(6989.1499, 845.1000, 3285.1699)**, unchanged |
| Runner result | `success=true`, `status=turn-input-completed`, `headingClaimed=false` |
| Final controller | `ready`, guest idle/disarmed, no held keys, `inFlight=0` |
| Shared navigation queue | Lab1 blocked/unheld (preserved); Lab2 unblocked/unheld |

Evidence: `artifacts/resume-rr2-reader-20261109-0906/`; `artifacts/resume-rr2-rebind-fast2-20261109/` (game rejection after-screen); `artifacts/resume-rr2-bind-command-20261109/`; `artifacts/resume-rr2-source-pin-20261109-0930.json`; `artifacts/resume-rr2-turn-live2-20261109-0934/`; `artifacts/resume-rr2-turn-run-live2-20261109-0934/{action-1.json,result.json,final-status.json}`.

## One failed-closed attempt and the practical next step

The earlier reviewed 100 ms turn **never sent an input**: screenshot review/execution began after its 30-second queue lease expired. The queue protected its resource; the controller was recovered, a new fresh review/lease was obtained, and the successful trial above followed. The repository already has `scripts/hold_review_lease.py` to heartbeat an exact prepared session during review without extending its 120-second absolute deadline. Start it promptly after a future `prepare` if the reviewer will take more than a few seconds; the **45-second screenshot review window remains unchanged**.

Next: after current reader expiry, launch a **new** bounded SHA-pinned reader, use same-lab `/rr2guide rebind` only if the addon still has an existing binding (otherwise `bind`), prove advancing fresh XYZ, then run a screenshot-reviewed **1D forward (`w`) calibration** with the same STOP/release and independent displacement requirements. A successful A-turn alone does not establish heading or waypoint arrival. Preserve Lab1 and the unrelated untracked `scripts/project_current_native_energy_variants.py`.
