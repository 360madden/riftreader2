# Lab2 fast-versus-full feedback forensics — 2026-11-05 UTC

**Verdict:** The 2026-11-01 Lab2 multi-pulse waypoint attempt **did not fail because every Lua producer observation stopped advancing**. The whole-process scan's cached candidate stopped at sequence **4878** and eventually timed out; the independent **candidate-region fast observation continued advancing to 4890**. The original Workbridge job's exact traceback shows `MovementHalted: elapsed-budget` in `WaypointController.record_feedback()` **after** a validated second post-action receipt. The original 12-second bound remains unchanged; goal arrival was not proven.

Read-only replay of preserved historical RR2 evidence and offline Python corrections only; **no game input, VM lifecycle action, addon rebind, RRE/REA integration, or live telemetry qualification**. Read the prior [November 4 recovery report](lab2-automatic-bind-attempt-2026-11-04.md) for the current session blocker.

## Independently recovered evidence

- Original Workbridge job `rr2-lab2-postreload-reviewed-w1d-movement-run-20261101-02`: exit **1**, executed **22:27:40.530Z–22:28:00.026Z**. Trace at `scripts/run_movement_session.py:902` invokes `controller.record_feedback(..., clock()-started)`; `scripts/movement_controller.py:229` raises `MovementHalted('elapsed-budget')`. No live-receipt timeout is the exception in this job.
- The archived managed-controller arm receipt has `savedAt=2026-11-01T22:27:46.768043Z`, `expiresInSeconds=15`; first W ended **22:27:54.569Z** and second W ended **22:27:57.162Z**, both with independently recorded key-up and delivery success. The second post-action receipt arrived **22:27:58.736Z**, close to 12 seconds after arm. The arm time is a wall-clock proxy: the execution's own `started=clock()` is set just after arm, and its exact monotonic value was not persisted.
- Full and scoped sources are **distinct** fields in each receipt: `observation.riftReader2` and `observation.fastObservation`. Evaluating each saved receipt with the existing strict gate using its preserved host receipt clock (offline historical replay only) produces:

| Archived receipt | Outer | Full producer | Fast producer | Replayed selected source |
| --- | ---: | --- | --- | --- |
| initial / ready-1 | 1584 | seq4856, valid, effective age ~2970ms | seq4860, valid, effective age ~581ms | **fast** |
| ready-2 | 1594 | seq4878, valid, effective age ~1219ms | absent | **full** |
| barrier-1 | 1596 | seq4878, valid, effective age ~2980ms | seq4883, valid | **fast** |
| after-1 / ready-3 | 1597 | seq4878, still valid but age ~3851ms | seq4884, valid, effective age ~595ms | **fast** |
| barrier-2 | 1599 | full expired `freshness-timeout` | seq4888, valid, effective age ~588ms | **fast** |
| after-2 | 1600 | full expired `freshness-timeout` | seq4890, valid, effective age ~603ms | **fast** |

All eight source receipts remain immutable in ignored `artifacts/dual-method-live-reader-20261101-01/lab2-postreload-reader-2157/reviewed-movement-w-02-result/feedback/`. Full-source expiration **must not** be conflated with loss of fast-scoped freshness. The fast source is accepted only under its separate full-anchor, exact-nonce, epoch, hash and effective-age constraints.

## Narrow code hardening

- `scripts/movement_feedback.py`: a **full** source needs at least **2500ms remaining freshness lifetime** to be eligible for the next bounded action; structurally invalid/missing budget fails closed. A subsequent `wait_action_ready()` on the same feedback adapter must exhibit strictly increasing selected addon sequence, addon clock, captured time and outer sequence relative to the previous admitted action-ready sample, with stable player/epoch/pins. This keeps the existing fast-source 6250ms anchor headroom, other strict gates and timeouts unchanged.
- `tests/test_movement_feedback.py`: three new focused tests reproduce repeated addon sequence, nearly expired 3596.7175ms full source, missing full-source budget; a valid boundary and advancing sample remain accepted. New negative tests **failed on original code**, passed after patch.
- Focused results after patch: feedback **30/30**, reviewed-movement runner **43/43**, movement acceptance **3/3**, strict freshness observer **14/14**; whitespace `git diff --check` and Python compilation passed.
- A broader `unittest discover` executed **1268 tests** but exited with **2 import errors** in unrelated Lua-addon modules `test_casting_addon` and `test_guidance_addon` because globally selected Python3.14 lacks optional `lupa` (pinned in `requirements-lua-tests.txt`); 2 tests skipped. This is **not** a clean full-suite PASS. No dependency was installed or other project changed.

**Important limit:** The new guard prevents an independent possible near-expiry/repeated-readiness error, **but it would not by itself have prevented the archived second W**, because `ready-3` selected the independently advancing **fast** source (sequence 4884), not stale full sequence 4878. The actual historical failure was the **overall 12-second elapsed budget**, not a directly proven Lua-publisher stall.

## Next practical development

1. Preserve the 12-second movement cap and existing 6250ms fast-anchor headroom. Instrument or offline-reconstruct why a new full anchor/eligible source after arming took ~6–7 seconds before the first W, rather than blindly increasing limits. A reviewed bounded execution should refuse a pulse if insufficient time remains to collect independent feedback and STOP.
2. Do not infer goal arrival from the two delivered W pulses; none was accepted by the controller as a completed goal. Next live attempt still requires newly qualified game/reader/receiver/addon nonce identity and strict 480-second freshness.
3. Current November 4/5 Lab2 reader `49d2cb83b3ba4d21b14bf3e32d67f128` expired as scheduled at 00:12:24Z without being bound; tool-safety-gated UI binding remains unresolved. Never reuse its old nonce. Consult RRE/REA evidence **before** any future new workaround/alteration if current data is stale, keeping their historical/static facts independent of fresh RR2 proof.
