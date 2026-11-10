# RR2 turn-left and actor-heading roadmap — 2026-11-10

**Goal:** deliver one successful, measured `A` turn on RIFT-Lab-2, visibly establish a changed view, then distinguish **actor/body yaw** from **camera yaw** and travel course. Work only on **AMD-DESKTOP** at `C:\work\riftreader2`. The legacy RiftReader is a historical reference, not a runtime dependency.

## Verified starting point

- 2026-11-09 Lab2: requested `A` 100 ms, actual inserted down/up separation **117.6375 ms**, delivery/release succeeded; XYZ unchanged, heading **unmeasured** (`docs/validation/lab2-100ms-turn-live-2026-11-09.md`).
- 2026-11-10 Lab2: requested `A` 100 ms, down/up timestamps separated by **3.8732 ms**, delivery failed at budget, release succeeded; no turn qualification (`artifacts/wall-turn-left-a100-run-20261110-02/action-1.json`).
- RIFT-specific research `rift_player_movement_input_security_research_2026-11-10_v2.md` documents movement after synthetic `W/S/Q` in retained controlled trials; a universal hardware-only movement-input gate is not a justified default explanation.
- Game addon `Inspect.Unit.Detail` has XYZ and `Event.Unit.Detail.Coord` can announce changes. Neither is documented to report actor yaw. A static or travel-course angle is **not** body facing.
- **Historical proven body-yaw route:** V1's 2026-10-18 report (`C:\\rift modding\\RiftReader\\docs\\workflow\\player-yaw-recovery-result-2026-10-18.md`) used `QWORD(module+0x32E0200)+0x304` (float32 radians), distinct from camera-only rotation and stable across two full game restarts on **SHA 7C356C9D...**. Current RR2 is on **SHA 1935A05C...**; re-use as a cached current-build **candidate**, not an assumed qualified locator. Cross-check the same historical owner's +0x320/+0x324/+0x328 XYZ against current RR2 player position.
- Current exact-build position and actor/model render-matrix candidates (see `docs/reference/native-current-coordinate-code-map.md`) remain useful fallback scaffolding; no fixed camera/body mapping is presumed. Old ~172°/s does not carry forward.

## Execution order — minimal scope

| Priority | Implement and try | Accept only with |
| --- | --- | --- |
| **M0: facing baseline** | Try the historical V1 owner-yaw root on the current exact build with `probe_native_unit_manager.py --lab lab2 --historical-yaw-candidate`; read raw angle and cached owner XYZ, cross-check against RR2's current self position. If unavailable, sample current-build position matrices/slot17 render candidate instead. | Explicit current PID/start/build/unit, numeric finite candidate or honest unavailable reason, and captured **pre-turn** facing/matrix value. This is scaffolding, not claimed qualified body yaw. |
| **M1: pulse** | Recover single managed Lab2 controller, get fresh game PID/start/SHA and foreground screenshot, advancing addon/reader telemetry, then perform **one** reviewed `A` pulse of 100 ms. | Raw down/up timestamps separated **75–125 ms**, successful delivery, release, disarm, zero held keys and no recovery required. Expired guards mean pre-input blocked, not game rejection. |
| **M2: paired evidence** | Capture post-release facing from the **same source and epoch** plus before/after screenshots at a fixed camera. Record source hashes, capture times and shortest signed candidate-angle delta. | Correct sequence, same process/build/owner, visible view delta if any, and explicit distinction between candidate yaw, camera, and XYZ. A valid pre-turn baseline is mandatory for turn-angle calculation. |
| **M3: improve source** | If V1 root is absent or uncorrelated, use current actor slot17/world 3×3 and render matrix; validate direction with controlled A/D then camera-only negative control when ready. | Candidate changes with A and D in opposite directions and stays stable in no-input settle; promote only when enough evidence, never invent missing facing. |
| **M4: angular calibration** | Repeat brief A/D pulses using consistent before/after candidate facing, shortest signed angular differences, actual measured hold. | Useful provisional angle/rate with candidate label; independently qualify actor/body mapping later. |
| **M5: obstacle exit** | Once body facing and open path are confirmed, calibrate short `W` progress and guide out of the railing area. | Independently newer XYZ after release and a stable no-input settle; do not loop blindly into the barrier. |

## Immediate timing diagnostic

Prefer the existing guest `ControlAgent` `keyDownTiming`, `keyUpAttempt`, `keyUpTiming`, and `keyUpInserted` events. Compare target pin check, `SendInput` cost, release scheduling and actual held interval. Do **not** simply raise hold duration to compensate for a late first insertion, and never treat Windows insertion as proof the game consumed the input.

## Stop conditions

Wrong host or game identity; expired capture/lease/reader; game or chat not foreground; an existing active console owner; no fresh bound position feedback; unknown key state; failed STOP/release; or unreviewed controls. When a prerequisite fails, retain exact reason and proceed to nonconflicting offline work. Never label missing yaw as zero degrees.

## Minimal reporting

One bounded action receipt, before/after screenshots with hashes, independent feedback and clear verdict: `not-armed`, `delivery-failed`, `turn-input-completed/viewpoint-only`, or `actor-heading-qualified`. Commit cohesive code/test results separately from ignored raw artifacts. No Codex, Ollama, OpenCode or inactive subagents unless Joey explicitly reauthorizes them.
