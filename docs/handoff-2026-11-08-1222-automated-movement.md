# RiftReader2 — Automated movement handoff (2026-11-08 12:22 EST)

**Machine:** AMD-DESKTOP (not LEGION). **Checkout:** `C:\work\riftreader2`, branch `codex/modular-foundation`.

## Functional live milestones — Lab 1

| Capability | Verified result | Evidence |
| --- | --- | --- |
| Reader-bound independent XYZ | Bound live reader PID 9320 to RIFT PID 8508; fresh source pin built | `artifacts/fastmove-hourreader-lab1-source-pin-20261108-01.json` |
| 1D calibrated movement | 150 ms `S` = 0.500 game units | `artifacts/fastmove-lab1-calibration-run-hour-20261108-04/result.json` |
| **1D waypoint arrival** | **arrived**, one `S` pulse, 2 observations and a released settle | `artifacts/fastmove-lab1-waypoint-run-hour-20261108-02/result.json` |
| 2D calibration | `W` / `Q` independent basis, normalized cross 0.999998 | `artifacts/fastmove-lab1-2d-calibration-run-20261108-02/result.json` |
| **2D waypoint arrival** | **arrived**, `W` 90 ms + `Q` 120 ms; final error 0.245 / tolerance 0.300; released settle | `artifacts/fastmove-lab1-2d-waypoint-run-20261108-02/result.json` |
| In-place turn | `A` 100 ms delivered and released, no XYZ drift. **Heading not yet measured** | `artifacts/fastmove-lab1-turn-run-20261108-01/result.json` |

**Both labs recovered/ready:** Lab1 and Lab2 controllers connected, console reserved and fault-free at 12:21 EST. Last verified movement input was released; Lab2 did not participate in movement testing.

## Pushed production improvements

- `4eecbfc`: screenshot-reviewed addon UI cleanup plus cleanup polling retry against a supervisor changing a paginated queue snapshot (preserves fail-closed rejection).
- `bc2a64f`: 10% predicted cross-track headroom; observed hard corridor unchanged. This corrected a real `Q` overshoot and enabled the successful 2D waypoint.
- Validation: **152/152 movement tests**, **80/80 addon console tests**, live calibration/arrival evidence. Both commits pushed to origin.

## Next product milestone

**A convenient route-to-coordinate or named-anchor command:** chain bounded local waypoints from independently verified XYZ, replan from each live result, and handle heading/turn calibration explicitly. Keep exact screenshot review and time-limited ownership; shorten the capture-to-arm workflow instead of bypassing it. Current gameplay model only proves *local* 1D/2D arrival, not obstacle-aware map-wide navigation.

**Ephemeral session:** reader PID 9320 / challenge `a1a8dc13ed8e4744a6d32008727adbcd` expires **2026-11-08 17:48:01 UTC**; never reuse after expiry or a RIFT restart. Lab1 RIFT PID 8508, start ticks 639297512849368370. Do not treat historical source pins as current. Untracked `scripts/navigation_anchor_capture.py` and `scripts/project_current_native_energy_variants.py` belong to other ongoing work; left untouched.

This handoff intentionally links existing artifacts instead of duplicating logs.
