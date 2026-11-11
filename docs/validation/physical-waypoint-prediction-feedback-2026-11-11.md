# RR2 physical waypoint prediction and offline feedback — November 11, 2026

**Host:** AMD-DESKTOP verified by machine-local PowerShell. **Repository:** `C:\work\riftreader2`, `codex/modular-foundation`. **Scope:** candidate-only offline physical RIFT movement/navigation; no fresh gameplay input, VM, or LEGION operations.

## Practical milestone

The existing `scripts/physical_move_basis_waypoint.py` now includes `candidateAction.predictedDeltaXYZCandidate` and `predictedAfterXYZCandidate` for each proposed bounded action. These are derived from the saved four-direction basis and planned hold. They do not grant execution authority or imply actual movement.

New `scripts/physical_move_step_feedback.py` recomputes the one-action proposal from its exact basis/position files, validates a **separate already completed** `move-key` receipt through `physical_move_key_calibration.py`, and compares observed native XYZ changes with the predicted movement after scaling to the **actual observed hold duration**. It refuses mismatched command key or duration, process/start/build/player key, more than 20 seconds between saved position sample and subsequent pulse, and a starting coordinate mismatch above 0.05 units. It returns planar prediction error, candidate movement progress and `stop-and-review` on divergence, never sends input, and never reports game-consumption or navigation authorization.

## Verified results

- **Four independent synthetic direction checks:** previously recorded real W/S/Q/E velocity model yielded correct W, S, Q, E selection; all proposals bounded at **150 ms**, and no input was sent.
- **Synthetic feedback fixture:** proposed W100; recorded W100 with actual hold 110 ms and native candidate X/Z displacement (-0.66, -0.0825) reproduced the scaled predicted displacement. A divergent (-0.10, -0.0825) example returned `candidate-divergent` and `stop-and-review`.
- **Negative check using real historical data:** `rr2-feedback-real-old-receipt-rejection-20261111a` compared the recent 100 ms preview with the older 400 ms physical W receipt; the tool returned `{"status":"blocked","reason":"feedback-command-mismatch"}` with exit code 2. It correctly refused false correlation.
- **Automated checks:** **25/25 focused Python tests passed** across feedback, waypoint preview, empirical basis and receipt parsing. A test-helper method initially shadowed `unittest.TestCase.run`; renamed to `assess` before successful rerun.

## Command (offline only)

Run from PowerShell at `C:\work\riftreader2`, supplying a saved one-pulse helper receipt that was actually generated **after** a corresponding pre-action native position report:

```powershell
C:\Python314\python.exe scripts/physical_move_step_feedback.py `
  --basis artifacts/physical-move-basis-wsqe-nov11-2026-v2.json `
  --position artifacts/physical-native-position-acecf069b33a42c48b8052b4e650d266.json `
  --receipt artifacts/physical-move-key-receipt-w400-20261111.json `
  --target-x 7429.674590644141 --target-z 2966.531579284686
```

**The example intentionally blocks** because the 400 ms historical receipt is not the proposed 100 ms action. Do not treat the example as an executable movement instruction.

## November 11 continuation: one-step feedback-driven replan

The existing `WaypointController` already provides the correct pending-action state machine. The feedback script now **replays the initial decision and its bounded budget**, applies the receipt's candidate final position through `record_feedback`, and—only when that observation is directionally consistent, useful, and still outside tolerance—calculates **one revised candidate** via the controller's existing `decide` method. Observed key-down milliseconds are charged against the same hold budget. It does **not** reset the controller to a new starting location or send any input.

**Offline tests:** A synthetic W150 receipt with an actual 155 ms hold and matching displacement suggested **Q** as the revised next candidate for a two-axis destination; its hold remained within 20–150 ms. A consistent displacement that exceeded the route's cross-track corridor instead produced `stop-controller-cross-track` and `stop-and-review`, with no next action. A position landing within tolerance produced `requires-independent-arrival-settle`; it did **not** claim arrival. A divergent displacement still stopped without replan. **35/35 focused Python tests passed**, including the existing movement controller tests.

New fields in the feedback record: `controllerFeedbackStatus`, `nextCandidateStatus`, and optional `nextCandidateAction` with its predicted X/Z delta and endpoint. All next actions retain `navigationEligible=false` and `inputSent=false`. A real historical 400 ms W receipt remains unsuitable for the synthetic 100 ms example; **no new physical input or independent changed-state test was performed**.

## Optional separate post-release native capture

The same offline feedback command now accepts `--post-position PATH.json`, referring to a **separate native XYZ burst recorded after the helper's final XYZ sample**. It uses the same existing RR2 position reader, but a different saved capture; this is **not** independent RIFT UI/Lua proof.

When supplied, RR2 requires the original process/build/player identity, distinct report hash, a **0–5 second** post-capture gap, at least two native samples within a 2-second burst, every sample stationary within 0.05 horizontal / 0.10 vertical units of the final sample, and agreement with the helper's reported endpoint (within 0.05 horizontal / 0.10 vertical). Failures block the comparison and yield **no revised action**. A matching later sample becomes the candidate position for the existing controller's next-step arithmetic. Output includes `postPositionReportSha256`, `postCaptureGapSeconds`, `postPositionMatchesReceiptCandidate`, and `postPositionXYZCandidate`.

**39/39 focused tests passed**, including agreement, contradiction, wrong identity, stale after-capture, continuing drift, and the actual `--post-position` CLI route. Real helper/pulse coordination has **not** been performed for this new option; all tests were offline synthetic fixtures. The earlier historical 400 ms W receipt cannot be substituted for a new 100 ms proposal, and the script still never sends gameplay input.

## Qualification boundary

Outputs retain `inputSent=false`, `navigationEligible=false`, `gameResponseVerified=false`, `arrivalQualified=false`, and `sameFacingConfirmed=false`. The old Q/E vectors were reprojected to a later W heading mathematically and **not tested at that newer facing**. Current native XYZ can be cached and does not independently prove game response. An actual same-facing bounded pulse, matched pre/post native readings and independent visual/Lua response are still needed before steering can be qualified.

Related: [empirical basis and cardinal movement](physical-cardinal-movement-basis-2026-11-11.md) and [offline waypoint preview](physical-basis-waypoint-offline-2026-11-11.md).
