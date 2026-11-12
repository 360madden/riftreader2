# RR2 handoff — settled physical A/D turns and working WGC capture

Recorded November 11, 2026, Eastern time.

## Checkout and host

Actual machine verified AMD-DESKTOP. Repository C:\work\riftreader2, branch codex/modular-foundation, Initial handoff HEAD cacdf91e8dac3ba68c926eccc401815b6167d867. Follow-up implementation through 35b5309. Follow AGENTS.md and reacquire process/build/window/player identity before live work. Physical hosts only. This session operated AMD-DESKTOP.

Concurrent modified files at final check were scripts/fresh_native_actor_pose.py, scripts/observe_physical.py, tests/test_fresh_native_actor_pose.py, tests/test_observe_physical.py, and Application/Domain/Infrastructure packages.lock.json. Untracked energy/anchor scripts and test also remain. Preserve all peer work and index. This list describes the initial handoff. Follow-up implementation is summarized below.

## Workbridge recovery and operational caveat

User explicitly authorized investigation, shutdown/restart, archival of the old quarantine, and one capture. PID 32516 was the main Workbridge dist/server.js child of tunnel-client PID 32444 and scheduled wrapper PID 28196. The recorded quarantine was for request rr2navposebeforeA20261111b, lease d85dd9f0-93e8-4e09-a8ca-ab996efb8586.

Read-only reconciliation found no post-lease descendant candidates but still-present historical owner. Manual archive dry-run originally refused HISTORICAL_OWNER_PID_PRESENT. With user approval, scripts/Restart-Workbridge.ps1 stopped the old task/process tree. Scheduled startup exited 1 and readiness timed out. The configured Start-BackgroundTunnel.ps1 wrapper was then launched directly, hidden, with the scheduled action's existing arguments. Tunnel health subsequently reported ready. A later final health check also returned ready, but Workbridge MCP scheduled task remained Ready, and the final process query returned no tunnel-client.exe row. Therefore service durability and current process ownership need fresh investigation. Do not assume a normal scheduled-task restart or lasting startup recovery.

Archive dry-run subsequently passed review, and scripts/Archive-DesktopQuarantine.ps1 -Execute archived the exact SHA-pinned guard and sidecar to:
C:\work\workbridge-mcp\.tools\desktop-evidence\recovery-archives\rr2capture-recovery-20261112b

The original capture outcome remains unknown. At final check no top-level input-turn lock, admission lock or quarantine sidecar matched the capture gate. Recheck before future operations.

## WGC capture now works on physical RIFT

Used existing tools/physical-wgc-probe Debug executable, backend wgc, one explicit capture per invocation, exact PID/start/SHA/HWND, new PNG paths and JSON receipts.

Historical target this session:
- PID 18092, process start UTC ticks 639300391441133615
- HWND 919618 (0xE0842)
- Executable C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe
- SHA256 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8
- Player key 239816685251645959, character Atank
- User placed RIFT on physical display 3. Win32 Screen reported DISPLAY5 with window at approximately (-1928,-2) to (8,1046). Mapping to Settings display number was not verified.

First usable frame artifacts/rift-visible-20261111-1958.png (actual capture 19:57:36 EST), 1920x1032, capture call ~425.65 ms. Visually shows Atank, practice dummies, Thedeor's Circle, RR2 CASTING v0.4.0. Window was background and uncloaked. Probe reported no input or focus change. Filename minute differs from actual capture timestamp; use JSON receipt timestamps.

## First A/D pair

Existing Debug RiftReader2.Live.exe move-key, explicit PID, --hold-ms 250 --measure-actor-pose --execute --json. Only one pulse each.

A evidence artifacts/physical-a-20261111-195847/
- Original before actor angle -40.1964036699 degrees.
- Immediate after A -79.9534604367, delta -39.7570567668.
- Hold bounds 256.0542–259.6560 ms, midpoint 257.8551.

D evidence artifacts/physical-d-20261111-200003/
- Before D -83.9642711796, immediate after D -44.5975738554, delta +39.3666973243.
- Hold bounds 255.59–258.81 ms.
- Subsequent read-only settled check artifacts/settled-d-pose-20261111-200215.json returned three identical samples -39.9626068287.
- Settled final difference from original +0.2337968412 degrees, right by angle convention.
- Prior A settled magnitude inferred from later pre-D sample 43.7678675097 degrees. Prior D settled magnitude 44.0016643509 degrees. These observations have different delays, so they are a limited repeatability comparison.

Screenshots visibly confirm viewpoint rotation. scripts/physical_turn_visual_pair.py returned visibleViewChangeCandidate=false for obvious turn images because sampled threshold fraction was low (~9–10%). Original-before-A versus after-D comparison was rejected for time gap. Treat comparator output accordingly. Visual evidence alone does not measure body yaw.

## Repeated pair with explicit settling

Evidence directory artifacts/physical-ad-settled-20261111-201818/ contains summary.json, baseline/a/d PNGs and probe receipts, pulse receipts, and raw pose bursts.

Procedure chose a 500 ms wait after each pulse, then five read-only pose samples at 100 ms intervals. Settled criterion was angle span below 0.01 degrees across all five; all sets passed on first attempt. Same player/build/start ownership checked. A fresh stable baseline preceded input.

| Stage | Actor angle degrees |
| --- | --- |
| Fresh baseline | -39.962606828701084 |
| Immediate after A | -79.34399650306521 |
| Settled after A | -83.84288455706586 |
| Immediate after D | -42.53124919561343 |
| Settled after D | -37.88266044091037 |

- Settled A delta -43.8802777284 degrees.
- Settled D delta +45.9602241162 degrees.
- Final residual from this run baseline +2.0799463878 degrees.
- Final residual from original pre-A +2.3137432290 degrees.
- A hold 256.0862–259.6996 ms, midpoint 257.8929.
- D hold 263.7355–266.8802 ms, midpoint 265.30785.
- Longer D hold is consistent with the larger D turn, but two pairs do not establish a calibrated control model.
- Compared to prior delayed settled observations, A magnitude differs ~0.1124 degrees and D ~1.9586 degrees.

Screenshots baseline.png, a.png and d.png were visually inspected. Dummies shift right after A and return near baseline after D with a small remaining offset.

## Third pair after Atank moved

On AMD-DESKTOP the fresh baseline XYZ was (7423.489, 863.5859, 2944.0254). Each recorded position bracket stayed at those coordinates. The earlier trials used (7425.1733, 863.58105, 2942.7314). Compare each trial with its own baseline.

| Trial | Settled A/D return relative to baseline | Median horizontal scenery displacement |
| --- | ---: | ---: |
| First | +0.234 degrees | -3 px, 14 of 18 patches |
| Repeated | +2.080 degrees | -25 px, 17 of 18 patches |
| Fresh baseline | +1.012 degrees | -9 px, 18 of 18 patches |

The third pair used a 250 ms requested hold and a 500 ms delayed pose observation. The settled readings were -37.3880 degrees before A, -80.8510 degrees after A, and -36.3764 degrees after D. Five-sample bursts confirmed each reading. Input receipts and source frames are under `artifacts/rebased-ad-20261111-203431/`. All three trials used the same player and process epoch. Independent body yaw and camera yaw in degrees remain open.

## Local capture and offline replay

From the repository root on AMD-DESKTOP, use the local WGC observer with a freshly selected RIFT PID. Build instructions are in [the probe README](../tools/physical-wgc-probe/README.md). The observer captures one still without changing focus.

```powershell
python scripts/observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --physical-pid <CURRENT_PID> --physical-capture-backend wgc
```

To replay the third pair without accessing RIFT, run:

```powershell
$d = 'artifacts/rebased-ad-20261111-203431'
python scripts/analyze_physical_turn_pair.py --before "$d/baseline.json" --after "$d/d.json"
python scripts/physical_turn_visual_pair.py --before-png "$d/baseline-frame/image.png" --after-png "$d/d-frame/image.png" --before-receipt "$d/baseline-frame/image.png.json" --after-receipt "$d/d-frame/image.png.json" --landmark-region 688 296 1248 408
```

The region covers stationary scenery in these 1920 x 1032 frames. Select scenery appropriate to each new view. The local patch search measures small return offsets in pixels. For the first trial, the original screenshots were 77.49 seconds apart, beyond the standard 30-second comparison limit. The first row's pixel figure comes from a separate endpoint-only comparison after verifying the individual receipts and matching window identities.

Across six pulses, settled actor-matrix rotation divided by measured hold midpoint ranged from 169.74 to 173.23 degrees per second. This empirical range is specific to the recorded trials. Windows key timing accounts for part of the residual, and the game-consumption time remains unknown.

## Forward movement check at one facing

After the three turn trials, one authorized 250 ms W pulse completed on AMD-DESKTOP. The first attempt lost foreground before input. Its blocked receipt is `artifacts/forward-pose-20261111-205300/pulse.json`. The successful receipt is `retry.json` in the same directory. The measured hold midpoint was 261.28 ms. Before and after observations matched player 239816685251645959 and recorded the same actor angle, -36.376393 degrees.

Displacement was X +0.942871, Y 0, Z +1.280029. Measuring from positive Z toward positive X with atan2(dx, dz) gives +36.375404 degrees. Negating the actor angle predicts +36.376393 degrees. Replay the comparison with:

```powershell
python scripts/physical_move_key_calibration.py --receipt artifacts/forward-pose-20261111-205300/retry.json
```

The nominal difference is 0.00099 degrees. Under a round-to-nearest binary32 model, allowing each endpoint coordinate half its local floating-point spacing gives a travel-angle interval of 36.35602 to 36.39479 degrees. This interval covers coordinate rounding only. The experiment supports agreement at this facing to the resolution of the displacement measurement.

## Forward movement at a second facing

The second trial is in `artifacts/second-facing-20261111-210134/`. The initial A attempt (`a.json`) lost focus before input. The retry (`a-retry.json`) inserted one A keydown and released it when RIFT lost foreground, after an observed 77.5 ms. Exclude that interrupted turn from the 250 ms A/D calibration. Five subsequent pose samples in `after-a.json` agreed at -45.307867 degrees.

One W press completed and released with a hold midpoint of 266.42 ms. The actor angle was -45.307867 degrees both before and after. Horizontal travel was 1.608622 units at +45.307444 degrees, measured from +Z toward +X. The two observed forward bearings span 8.93 degrees in the same quadrant and process epoch. Other quadrants and restart behavior remain open. The images in `after-a/image.png` and `after-w/image.png` bracket this W press.

Replay the W measurement from the repository root using the coordinate precision fix in `c42620e`.

```powershell
python scripts/physical_move_key_calibration.py --receipt artifacts/second-facing-20261111-210134/w.json
```

## Short correction toward the selected dummy

The native template fallback identified the selected target as Normal Practice Dummy. The target key in `artifacts/dummy-bearing-20261111-210353/template.json` matches the before and after position pairs in `artifacts/dummy-align-20261111-210518/`. In those pairs the bearing to the target was +35.553 degrees from +Z toward +X, at a horizontal distance of 5.417 units.

One D press requested for 50 ms had Windows hold bounds of 57.51–60.80 ms (midpoint 59.16 ms). The settled forward bearing moved from +45.308 to +34.996 degrees. The absolute alignment error fell from 9.755 to 0.556 degrees, crossing the target bearing. Use the before/after pose bursts and position pairs alongside `d.json` to replay this observation. This is one short correction at one heading.

## Forward step and two backsteps after alignment

At the corrected facing, one 100 ms W press moved Atank 0.65907 horizontal units. Paired position samples showed the same selected dummy at the same coordinates before and after, with its distance dropping from 5.417 to 4.758 units. Two separate 100 ms S presses then moved Atank back 0.32489 and 0.35197 units. The final horizontal distance from the pre-W player position was 0.01781 units. The hold midpoints were 107.07 ms for W, then 108.44 and 112.08 ms for S. All three receipts report successful release.

The retained sources are `artifacts/aligned-step-20261111-210654/w.json`, `artifacts/aligned-backstep-20261111-211022/s.json` and `artifacts/return-backstep-20261111-211119/s.json`. Each directory also has before and after self/target position samples. Compare the first before sample to the last after sample for return error. All three presses used one actor facing and process epoch. The result supports separate forward and backward speed estimates. A single continuous 200 ms S hold was not tested in this trial.

## Continuous and controller-bounded returns

Each trial below started from a fresh baseline and used one requested 100 ms W press. Horizontal residuals compare the final self X/Z with that trial's own pre-W position.

| Trial directory under artifacts | Requested S hold | Forward travel | Backward travel | Residual |
| --- | ---: | ---: | ---: | ---: |
| `continuous-return-20261111-211219` | 200 ms | 0.65555 | 0.64691 | 0.00873 |
| `bounded-return-20261111-211335` | 150 ms | 0.66215 | 0.49862 | 0.16353 |

The live 150 ms trial used the key and duration chosen in a preceding offline replay. Replaying its own records afterward through WaypointController, with the earlier 100 ms W and S calibrations, also selected S for 150 ms and predicted 0.21272 units remaining. The post-S sample moved the replay to confirming-arrival. A subsequent acquisition in `confirm.json` produced the same coordinates and the second confirmation required for arrived. This exercises feedback against saved physical observations. The subsequent trial below exercised the controller live.

## First live controller decision and arrival

On AMD-DESKTOP, one controller instance used a fresh position and the earlier measured W/S vectors to select a pulse toward the previously occupied point in `artifacts/bounded-return-20261111-211335/after-w.json`. The goal was 0.49862 horizontal units away. The decision selected W for 81 ms, the input helper reported successful release, and two successive paired position reads each placed Atank 0.00191 units from the goal. The first read produced confirming-arrival and the second produced arrived.

The decision, input receipt, position reads and controller result are in `artifacts/live-controller-20261111-211518/`. This single forward pulse used a supervised, one-off invocation and a previously sampled heading. The subsequent backward trial exercised a second decision from live feedback.

## Two-step backward waypoint

For `artifacts/two-step-20261111-211631/`, the goal was 0.880 units along the measured backward direction. The controller chose S for 150 ms. Fresh position feedback left 0.39234 units to go, so the same controller chose S for 131 ms. Both keys released. The measured hold midpoints were 163.14 and 143.04 ms. The final and confirmation samples put Atank 0.03740 units from the goal, including 0.03740 units past the goal along the intended path and 0.00070 units of lateral offset. Two in-tolerance readings produced arrived.

The directory contains both decisions, both helper receipts, pre-pulse pose checks, position feedback, confirmation, and the controller result. Live multi-step feedback has now been observed at one facing in one process epoch. Using a calibration collected before a turn or a client restart still needs separate evidence.

## Forward prediction after a 44.43-degree turn

Atank's settled actor angle changed from -34.99636 to +9.42954 degrees. Rotating the previously measured W vector by the pose change gave a 100 ms prediction of X -0.10147 and Z +0.60715. The initial W receipt in `artifacts/rotated-prediction-20261111-211828/` reported uncertain completion and successful release. The executor had observed a delay with no measurable monotonic advancement. Commit `d637c6e` rounds fractional default timer delays up to a whole millisecond.

In the fresh trial with the rebuilt helper, three pose samples agreed before the press. The retained prediction and successful receipt are under `artifacts/rotated-rebuilt-20261111-212002/`. Actual displacement was X -0.11963 and Z +0.71924. The pre-press endpoint error was 0.11355 units. Scaling to the measured hold midpoint of 116.39 ms afterward gives a retrospective error of 0.01266 units. This provides one live forward prediction across a turn in the same process epoch. The next trial used a rotated backward calibration for a controller-driven waypoint.

## Controller return after the turn

The return goal was the player position before the successful larger-angle W trial. At the new facing the controller used the S vector measured in `artifacts/aligned-backstep-20261111-211022/s.json`, rotated through the observed 44.43-degree change. Starting 0.72912 units away, it selected S for 150 ms and predicted 0.27969 units remaining. The first post-press sample measured 0.22974 units remaining. A second acquisition confirmed arrival within the 0.30-unit tolerance.

In `artifacts/turned-return-20261111-212128/`, `decision1.json` contains the rotated vector and goal, `pulse1.json` records the input and displacement, and `after1.json` and `confirm.json` are the position reads. The rotated S bearing differed from travel by 0.096 degrees. The requested-duration prediction missed the endpoint by 0.04996 units. Scaling retrospectively to the measured 165.40 ms hold midpoint reduced this to 0.00391 units. This trial and the W prediction used the same client process epoch. Reuse after restart remains unverified.

## Four measured directions and a lateral waypoint

The W, S, Q and E receipts each have the same sampled actor angle of +9.429536 degrees at both endpoints. W/S travel differed by 179.95 degrees, Q/E by 179.96 degrees, and W/Q by 89.99 degrees. The two 100 ms Q/E pulses returned within 0.012 horizontal units of the pre-Q position. See `artifacts/strafe-pair-20261111-212614/basis-reviewed.json` for the four vectors and source hashes. Facing between samples and reuse after restart remain unverified.

The lateral waypoint trial used all four measured vectors. The goal was the pre-E position, 0.65382 units away. The controller selected Q for 108 ms and the measured hold midpoint was 124.37 ms. Actual travel was 0.75677 units. Two in-tolerance position readings confirmed arrival 0.10295 units past the goal, with less than 0.001 units of sideways offset. The saved decision, pulse, position reads and result are in `artifacts/lateral-waypoint-20261111-212740/`.

## Two-axis waypoint with live feedback

The controller used the four measured key vectors to approach a waypoint offset 0.54 units along E and 0.39 along S from its fresh starting position. It selected E for 90 ms, reducing the goal distance from 0.66619 to 0.39893 units. From that measured position it selected S for 129 ms. The next read measured 0.10116 units remaining, and a second read confirmed arrival within the 0.30-unit tolerance. Both input receipts report successful release.

The directory `artifacts/two-axis-20261111-212913/` contains both decisions and receipts, the starting and post-press position samples, the confirmation and the controller result. Its `path.png` plots the measured positions and arrival radius. This trial exercised two sequential movement axes at one facing in the same process epoch.

## Command-line preview and return feedback

As of `01b0587`, `scripts/physical_move_basis_waypoint.py` consumes the four measured vectors directly. For the return to the two-axis trial's starting position, the preview selected Q for 103 ms. The separate post-press read left a 0.44056-unit gap. Feedback proposed W for 70 ms, and a fresh preview agreed before that press. The final measured distance was 0.05358 units. Five later same-player actor-translation samples all matched the post-W horizontal endpoint.

The first preview, input, position and feedback files are under `artifacts/cli-feedback-20261111-213237/`. The W step and `settled-actor.json` are under `artifacts/cli-return-20261111-213313/`. Both steps used the measured basis under `artifacts/strafe-pair-20261111-212614/basis-reviewed.json`. The final feedback status is `requires-independent-arrival-settle`; the later actor and XYZ readings corroborate the endpoint within the same client.

## Visual check after the return

The two WGC frames in `artifacts/visual-settle-20261111-213550/` were captured 1.381 seconds apart. Replay the comparison above with the `first` and `second` frame directories. All 18 accepted scenery patches had exactly zero offset. The actor region (890, 462, 1030, 665) also had 18 of 18 at zero. Coordinates refer to the 1920 by 1032 saved frame. The screenshots establish screen stability over that interval. The native samples supply the endpoint coordinates.

For comparison, zero of the 17 accepted scenery patches had zero offset in the repeated A/D trial, and zero of 18 did in the fresh-baseline trial. Their median horizontal shifts were -25 and -9 pixels respectively.
