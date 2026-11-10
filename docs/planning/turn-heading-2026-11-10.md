# RR2 turn-left and actor-heading roadmap — 2026-11-10

**Goal:** deliver one successful, measured `A` turn on RIFT-Lab-2, visibly establish a changed view, then distinguish **actor/body yaw** from **camera yaw** and travel course. Work only on **AMD-DESKTOP** at `C:\work\riftreader2`. The legacy RiftReader is a historical reference, not a runtime dependency.

## Verified starting point

- 2026-11-09 Lab2: requested `A` 100 ms, actual inserted down/up separation **117.6375 ms**, delivery/release succeeded; XYZ unchanged, heading **unmeasured** (`docs/validation/lab2-100ms-turn-live-2026-11-09.md`).
- 2026-11-10 Lab2: requested `A` 100 ms, down/up timestamps separated by **3.8732 ms**, delivery failed at budget, release succeeded; no turn qualification (`artifacts/wall-turn-left-a100-run-20261110-02/action-1.json`).
- RIFT-specific research `rift_player_movement_input_security_research_2026-11-10_v2.md` documents movement after synthetic `W/S/Q` in retained controlled trials; a universal hardware-only movement-input gate is not a justified default explanation.
- Game addon `Inspect.Unit.Detail` has XYZ and `Event.Unit.Detail.Coord` can announce changes. Neither is documented to report actor yaw. A static or travel-course angle is **not** body facing.
- The current exact-build orientation matrix and actor/model render-matrix candidates (see `docs/reference/native-current-coordinate-code-map.md`) are **not** validated actor heading. Historical V1 heading offsets and ~172°/s do not carry forward.

## Execution order — minimal scope

| Priority | Implement and try | Accept only with |
| --- | --- | --- |
| **M1: pulse** | Recover single managed Lab2 controller, get fresh game PID/start/SHA and foreground screenshot, independently advancing addon/reader telemetry, then perform **one** reviewed `A` pulse of 100 ms. | Raw down/up timestamps separated **75–125 ms**, successful delivery, release, disarm, zero held keys and no recovery required. If a guard expires, classify as *pre-input blocked*, not game rejection. |
| **M2: visual** | Capture before and after at a fixed scene/camera without touching `W`, click-to-move, or mouse-look. Record source hashes and actual capture times. | Same build/process, visible view delta, and no unexplained camera orbit/UI changes. This is *view rotation*, **not** body-heading proof. |
| **M3: native heading candidate** | In parallel with offline analysis, inspect slot17 actor/world 3×3 and render matrix plus position matrices in the current process, retaining raw bytes, owner, game SHA/epoch and acquisition times. | Valid self-entity source, same-epoch values changing on a controlled `A` and `D` in opposite direction, stable on no-input settle. Separate camera-only negative control. |
| **M4: angular calibration** | Repeat brief A/D pulses with a validated body yaw in the same game epoch; use shortest signed angular differences. | Actual hold vs signed yaw delta, repeatability and release; do not promote legacy calibration without retesting. |
| **M5: obstacle exit** | Once body facing and open path are confirmed, calibrate short `W` progress and guide out of the railing area. | Independently newer XYZ after release and a stable no-input settle; do not loop blindly into the barrier. |

## Immediate timing diagnostic

Prefer the existing guest `ControlAgent` `keyDownTiming`, `keyUpAttempt`, `keyUpTiming`, and `keyUpInserted` events. Compare target pin check, `SendInput` cost, release scheduling and actual held interval. Do **not** simply raise hold duration to compensate for a late first insertion, and never treat Windows insertion as proof the game consumed the input.

## Stop conditions

Wrong host or game identity; expired capture/lease/reader; game or chat not foreground; an existing active console owner; no fresh bound position feedback; unknown key state; failed STOP/release; or unreviewed controls. When a prerequisite fails, retain exact reason and proceed to nonconflicting offline work. Never label missing yaw as zero degrees.

## Minimal reporting

One bounded action receipt, before/after screenshots with hashes, independent feedback and clear verdict: `not-armed`, `delivery-failed`, `turn-input-completed/viewpoint-only`, or `actor-heading-qualified`. Commit cohesive code/test results separately from ignored raw artifacts. No Codex, Ollama, OpenCode or inactive subagents unless Joey explicitly reauthorizes them.
