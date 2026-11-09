# RR2 — Sunday-night watchdog and Lab2 continuation

**Captured:** Monday, 2026-11-09, 02:14 EST. **Machine verified:** AMD-DESKTOP (not LEGION). **Authoritative repo:** `C:\work\riftreader2`, branch `codex/modular-foundation`; pre-handoff HEAD `37b4a05` (already pushed).

## Verified results

- ✅ First measured Lab2 `S` input changed independent XYZ by ~**5.78** horizontal game units, but a requested **150 ms** hold actually lasted **1,850.3 ms**. The guarded runner rejected it. This was **not** a valid calibration or waypoint arrival. Evidence: `artifacts/sunday-night-20261108-2250/lab2-calibration-run-05/`.
- ✅ Fixed that concrete timing hazard: a dedicated watchdog releases bounded input independently of stalled target probes/async scheduling; the native target is pinned and cheap-checked during holds, with no late downs and explicit release uncertainty. **126/126 focused tests passed** (29 Application, 97 Live); published single-file smoke passed. Commit [`083e447`](https://github.com/360madden/riftreader2/commit/083e447).
- ✅ Lab2 guest agent was updated to immutable release `agent-d7a68bc6f884`, SHA256 `D7A68BC6F88437BF08CE5629866A10D4D709FE41AA5484A2A61B55D252CE4D4C`, 118,028,128 bytes. Post-update guest remained disarmed/idle with no keys held; original RIFT PID **10876**/start ticks **639297512883473394** remained. Deployment receipt `artifacts/sunday-night-20261108-2250/lab2-agent-update-watchdog-01/`; status commit [`37b4a05`](https://github.com/360madden/riftreader2/commit/37b4a05).
- ✅ Fresh **02:13 EST** Lab2 controller status: connected/ready, supervisor running, `armed=false`, `busy=false`, `desktopInputsDown=[]`, `recoveryRequired=false`; **02:14 EST** shared queue: both Lab1 and Lab2 unblocked and unheld. Lab1 VM/game/RAM were not changed.

## Limitations and blocker

- 🟡 **The new release is deployed but has never sent a live movement pulse.** A console preparation for `/rr2guide rebind` produced an obscured image, so no rebind/keypress was executed. Lab2 controller was gracefully stopped for console ownership and then restored; its task must be run with `C:\Python314\python.exe` to match the existing registered `pythonw` path (using `.venv` for task registration yielded a conflict).
- 🟡 Reader PID **6172**, nonce `4c3d2eed6b8648e1881663013336228b`, had scheduled expiry **06:23:28 UTC**, now past. **Do not reuse** this reader/nonce, source pin, screenshot, arm, or queue lease; its actual process exit was not rechecked.
- 🔵 Earlier **Lab1 1D and 2D waypoint arrivals** are already recorded separately in [the 12:22 movement handoff](handoff-2026-11-08-1222-automated-movement.md). No general pathfinding/obstacle avoidance is established. The unrelated untracked `scripts/project_current_native_energy_variants.py` was preserved untouched.

## Next practical step

1. Obtain a **readable, current Lab2 RIFT screenshot** through the normal review path; if still obscured, do not send input. Reacquire exact VM/game identity and a new bounded reader/nonce.
2. Review and execute a fresh addon rebind only if warranted; establish a new advancing, source-scoped XYZ pin. Do not reuse expired authorizations.
3. Run **one** guarded short calibration with immediate review-lease heartbeat, watchdog timing evidence, independent before/after XYZ and verified STOP/no-held-key cleanup. If unavailable, continue independent offline navigation work.

Authoritative running context: [`docs/status.md`](status.md) and [`docs/validation/lab2-first-motion-2026-11-09.md`](validation/lab2-first-motion-2026-11-09.md).
