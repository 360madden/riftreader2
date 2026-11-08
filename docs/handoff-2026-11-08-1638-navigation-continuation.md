# RiftReader2 — Navigation and anchor-renewal continuation

**Captured:** 2026-11-08 16:38 EST. **Verified machine:** AMD-DESKTOP (not LEGION). **Repo:** `C:\work\riftreader2`, branch `codex/modular-foundation`. Pre-handoff HEAD: `84c6eba`.

## Confirmed outcomes

- ✅ Earlier Lab 1 movement milestone: 150 ms `S` calibration, 1D arrived waypoint, independent `W`/`Q` 2D calibration, and 2D arrived waypoint (`W` 90 ms + `Q` 120 ms; final error 0.245 ≤ 0.300). See [12:22 movement handoff](handoff-2026-11-08-1222-automated-movement.md). These are prior live results, not evidence from the later trial.
- ✅ Quarter-age full-scan renewal starts at **2.5 s** versus 5 s, while the 10 s maximum anchor age and 6,250 ms strict action-ready threshold remain unchanged. .NET 10 suites **1,391/1,391**; live 80 s read-only Lab 1 sample **81** unique envelopes, **58** fresh-scoped, **22** strict action-ready (**27.2%**). No matched-baseline improvement claim. Evidence: `artifacts/nav-quarter-renewal-20261108-02/live-freshness-sample.json`.
- ✅ Direct invocation of `scripts/hold_review_lease.py` repaired and regression-tested. Movement failure cleanup now preserves the original expired-lease error without masking verified STOP failure. Console + movement + review-lease Python tests **134/134** pass.
- ✅ At 16:38 EST, both existing managed lab controller endpoints were verified `armed=false`, `busy=false`, `desktopInputsDown=[]`, `recoveryRequired=false`; shared navigation queue had no holders.
- ✅ Changes pushed: `19b18fd`, `0976c61`, `bb5a0f5`, `6ec3e40`, `84c6eba`. The handoff commit follows these.

## Honest boundaries / current blockers

- 🟡 Two later Lab 1 150 ms `S` calibration attempts **failed closed before arming** on expired review leases; no movement was sent. One did not have an operating heartbeat helper at the time. Both final receipts showed disarmed, idle, zero keys held, no recovery.
- 🟡 A new pinned Lab 1 reader launched successfully at 15:30 EST, PID **2444**, nonce `c49f891d82014ea784ae26672b3a4795`, scheduled expiry **20:39:57 UTC** (already past as of handoff). **Do not reuse** this reader, nonce, source pin, or session authorization. Its post-expiry exit was not independently checked.
- 🟡 Two fresh console `open-chat` preparations refused `controller-busy`: the Windows **cross-process ControlMutex** was occupied despite healthy controllers/empty queue. Ownership and current availability are unknown. Never bypass or clear it to force input.
- 🟡 Full Python discovery was **not validated**: one 150 s run timed out; a 50 s verbose run revealed `lupa.lua51` import failures in `test_addon_reference` and `test_guidance_addon`. Neither system Python 3.14 nor repo `.venv` has `lupa`; no install attempted.
- 🔵 Last verified Lab 1 game: PID **8508**, start ticks `639297512849368370`, executable SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. Receiver PID **54912** at last reader launch. All require fresh revalidation.

## Next practical task

1. Confirm exclusive console mutex ownership is available; if still occupied, use **Lab 2 read-only/offline work** and do not compete for the console.
2. For new live movement, verify current VM/game/receiver/reader identities, launch a bounded reader if required, and obtain fresh screenshot-reviewed addon binding (`/reloadui` then `/rr2bind` only if justified). Build a **new** source pin; discard all expired review receipts.
3. Prepare the narrow session, **start the repaired lease-heartbeat helper immediately**, review the exact current capture, and run one guarded bounded pulse inside the original absolute deadline. Preserve action-ready freshness, exclusive lease, STOP/key release, and final idle receipt.
4. Extend from previously proven local waypoints toward a practical named-anchor / route-to-coordinate chain; do not claim obstacle-aware navigation or native heading without new evidence. Resolve the missing Lua test dependency only when needed for addon validation.

**Preserve unrelated untracked:** `scripts/navigation_anchor_capture.py`, `scripts/project_current_native_energy_variants.py`. Do not modify other repos or copy old RiftReader as a runtime dependency. More detailed evidence is in `docs/status.md`.
