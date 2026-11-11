# RR2 Physical waypoint preview from empirical movement receipts — November 11, 2026

**Machine:** verified AMD-DESKTOP. **Mode:** offline-only. **Game:** physical RIFT Live x64. No LEGION, VMware, game input, or UI automation.

## Working result

The new `scripts/physical_move_basis_waypoint.py` reuses RR2's existing `WaypointController` with candidate forward velocity and rotated S/Q/E vectors extracted from **five real RR2 move-key receipts**. It checks the recorded game PID/start/build/player key against a separate native position report, requires position sampling after the last forward calibration, and proposes at most **one 20–150 ms pulse**. It neither sends input nor establishes navigation authority.

The physical position read `artifacts/physical-native-position-acecf069b33a42c48b8052b4e650d266.json` contained **3 unchanged same-player samples**, with X=7430.312, Y=863.586, Z=2966.3079, as a candidate native position.

An intentionally **synthetic** nearby destination, X=7429.674590644141, Y=863.586, Z=2966.531579284686, led the existing controller to suggest a single **W 100 ms** pulse, with predicted planar distance **0.675517 → 0.301138**. This is an offline mathematical recommendation, not a completed movement or real waypoint arrival. Evidence was saved to `artifacts/physical-empirical-basis-waypoint-preview-20261111-v2.json`, with inputSent=false, navigationEligible=false, headingQualified=false, worldInstanceMatched=false, arrivalQualified=false, gameResponseVerified=false.

## Reproduce offline

From **PowerShell** in `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe scripts/physical_move_basis_waypoint.py `
  --basis artifacts/physical-move-basis-wsqe-nov11-2026-v2.json `
  --position artifacts/physical-native-position-acecf069b33a42c48b8052b4e650d266.json `
  --target-x 7429.674590644141 --target-z 2966.531579284686 `
  --out artifacts/new-unique-waypoint-preview.json
```

The destination is operator-provided and remains unqualified as a real same-world target. The retained basis includes a **hypothesized** 17.435° rotation mapping earlier strafe vectors to the later forward direction. The corresponding later S/Q/E keys were **not** measured physically; this is not a live steering calibration.

## Validation and next step

- **39/39 focused Python tests passed** across the basis-to-waypoint adapter, empirical basis comparison, helper receipt import, and bounded movement controller.
- Tests include correct W100 output, no-action-within-tolerance, out-of-radius targets, vertical errors, player/process mismatch, old native position relative to calibration, malformed model/source hashes, zero vector, and refusal to overwrite an output file.
- The controlling `WaypointController` remains unchanged; no broad navigation framework or automatic input loop was created.
- **Next:** physically qualify the current facing and short-pulse response, then compare predicted versus observed one-pulse movement using independent RIFT visual/Lua feedback. Keep all live input separately reviewed and bounded; do not use an offline candidate as execution approval.

See [the empirical four-key movement-basis report](physical-cardinal-movement-basis-2026-11-11.md).
