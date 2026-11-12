# Recorded routes: interruption checkpoint, November 12

Checkpoint created around **08:06 EST / 13:06 UTC, November 12, 2026** on
verified **AMD-DESKTOP**, checkout `C:\work\riftreader2`, branch
`codex/modular-foundation`. Joey requested durable findings, a handoff, commit
and push after an apparent crash, then explicitly requested continuing the
five-hour goal after pushing. This is an interruption checkpoint, not completion
of that goal. Original activation was 11:56:02 UTC; original planned end was
16:56:02 UTC. Consult the live goal state before continuing.

## Working result and use

The prototype records actual observed positions, preserves corners, saves/loads
routes, replays forward/reverse, checkpoints confirmed arrivals, and explicitly
resumes the unfinished waypoint across an app restart and a genuine RIFT restart.
The main implementation checkpoint is `9fceb14`; the commit containing this
handoff adds the capture-race and slow-direction fixes described below.

Start with `Waypoints.cmd`. The default launcher can wait before RIFT exists and
bind a unique ready client while idle. Nothing moves on launch or reconnect.
Use **Record → Stop Recording** to save a passive recording; **STOP** cancels it.
Use **Play Forward / Play Reverse** near the corresponding recorded endpoint;
**Resume** continues saved unfinished progress. Route edits invalidate progress.
The usage guide is [physical-waypoints.md](workflows/physical-waypoints.md).

The actual taught route is preserved in Git as
[recorded-route-2026-11-12.json](validation/recorded-route-2026-11-12.json), including
original runtime/calibration provenance and local native-source references:

```powershell
Waypoints.cmd --route docs/validation/recorded-route-2026-11-12.json
```

Do not run it blindly: first inspect the current game view, identity and position.
It describes local open ground near the practice dummies, not terrain navigation.
The native position/facing fields retain their candidate labels. Limits remain
20 planned units, 20 waypoints, 64 pulses, 9,000 ms requested hold and 120 seconds,
with existing per-segment, freshness, ownership, foreground and release guards.

## What actually worked live

| Trial | Observed result | Local evidence |
|---|---|---|
| Controller teaching with recording | 30 samples, four retained points, both corners, 9.998 units; 19 released pulses | `artifacts/recorded-live-bdd34767725c47d9bd8bd8ea0b82dd36/teaching-receipt.json` and `recorded.json` |
| Reverse CLI playback | Four points in reverse, 25 pulses; final error 0.09917 units | `artifacts/waypoint-run-f52468d6a83e40f19244c2fc01a2608c.json` |
| Forward CLI playback | Final error 0.10648 units | `artifacts/waypoint-run-b4c277aafd324c988564fcf60556790e.json` |
| GUI Play Reverse → clickable STOP | Stationary after STOP, no next pulse; reverse cursor 3/4, last waypoint unfinished | `artifacts/waypoint-run-dc32b7e0c93747ccbe11baca1e305f79.json` |
| App restart, full RIFT restart, explicit GUI Resume | Restored cursor 3/4; RIFT PID31696 fully exited, normal Glyph/Atank launch became PID3820; same app PID75780 reconnected. Resume finished only the last leg, error 0.0679574, eight released pulses, 963 ms requested hold | `artifacts/waypoint-run-8d88bf44e6034217ba570b18b6dfd731.json` |
| Fixed-facing partial route → explicit CLI Resume | Backward first leg safely hit its action budget; explicit resume completed remaining route, final error 0.11244 | `artifacts/recorded-live-bdd34767725c47d9bd8bd8ea0b82dd36/forward-after-restart-events.jsonl`, `forward-after-restart-resume-events.jsonl`, `artifacts/waypoint-run-bcc58baca45546d285a8cc7cbee1570b.json` |
| Default app opened without RIFT | PID67424 displayed waiting state and restored saved route; no movement | Observed live immediately before the interruption; subsequent ready-client binding for this particular launch was not reached |

The numerical movement basis was never rebuilt or rewritten. Its unchanged SHA256
is `9A556D85DE26258D94E5A438BBC37D5938CCE762C67BC9B2E693602FDAB39251`.
Build SHA is `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`;
Atank unit key is `239816685251645959`. Reacquire all live identities; old process
IDs and component addresses are not reusable bindings.

## Remaining live gap and concrete fixes

**Passive GUI recording through a full moving path has not passed live acceptance.**
Several attempts correctly discarded incomplete recordings. Findings and fixes:

- Continuous paced capture contended with the native reader's one-second lease
  wait. Recorder bursts now use six samples with a 150-ms yield; facing acquisition
  waits up to three seconds before opening/timestamping the session. A read-only
  contention check completed nine bursts and eight independent reads without
  failure; maximum between-burst sample gap was 0.8173 seconds.
- The passive loop's extra `move-key --inspect` check competed for the input
  semaphore. It was removed because each native batch already verifies pinned
  PID/start/build/player/owners. All movement paths retain their full window,
  reservation, foreground and input checks.
- Moving capture then exposed `Native current-build player ownership or payload
  changed during capture.` The new native fix separates known pose-byte drift
  from ownership failures. Only paced, target-free multi-sample reads may reacquire
  that same logical sample, at most three attempts within 100 ms, using the same
  pinned lookup/component and completing owner/epoch checks. A stable published
  row records `captureAttempts`. Single-shot controller feedback and target-pair
  reads keep first-attempt behavior. **This fix is built and tested offline; it
  has not yet been tested against a moving live player.** No failed rows are
  silently skipped and the recorder's age/gap checks remain.
- A 3.3-unit backward leg exhausted six pulses because S is slower than W.
  Fixed-facing routes now size intermediate legs for 600 ms at the slowest
  calibrated planar speed, capped at four units. Existing input budgets remain.
  The simulator regression passes; this new segmentation is not yet live-tested.
- GUI progress now shows remaining distance, distinguishes completed/next points,
  disables actions without a pose, and directs completed routes to Play rather
  than Resume. Receipt files retain complete GUI successes and failures.

One earlier 150-ms W pulse had a 225.56-ms candidate SendInput hold midpoint;
the reused-seed timing guard stopped the run. Release succeeded. The guard was
kept; no timer defect was established. A second attempt was invalidated by manual
movement, which Joey confirmed. These were not accepted as completed recordings.

## Interruption and cleanup state

RIFT PID3820 later showed a black render surface and returned no WGC frames after
its window returned to the larger main-display rectangle. The normal input desktop
was `Default`, not Screen-saver. Existing BlackBox display recovery moved/resized
the window but did not restore rendering. PID3820 then exited normally.

A normal Glyph launch created PID59816 (start ticks `639300851720753748`, HWND
101848046). The last captured image was a loading splash:
`artifacts/observe-wgc-f143165633304d5f9c865302821be947/image.png`.
After the user reported a crash/interrupted the turn, PID59816 was absent. A local
Windows Application log query for the preceding 20 minutes found no matching
RIFT/native-helper/pythonw crash event. **The crash cause is unknown.**

At checkpoint cleanup, RIFT was not running. Our waiting app PID67424 was closed
normally and exited; unrelated pythonw processes were preserved. No gameplay
input or movement worker was left active. Last successful in-world pose, before
the later loading failure, was `(7423.489746, 863.586548, 2937.861572)`, bearing
58.122557 degrees. This is historical, not a fresh current pose.

Local captures and receipts remain under `artifacts/`; large raw reports are not
being committed. Unrelated peer edits in `fresh_native_actor_pose.py` and its test,
plus energy/anchor-ranking scripts and tests, remain outside this task's commits.

Checkpoint validation: **130 focused native facing/orientation/position tests**
and **30 focused Python controller/observation/Tk tests** passed. The latter
includes slow-backward segmentation, waiting/completed playback controls, receipt
retention, recording stop/cancel and cleanup. These are targeted checks, not a
claim of full-repository validation or live acceptance of the latest capture fix.

## Continue from here

1. Verify AMD-DESKTOP and fresh Git/process state. Keep the root as the sole live
   input coordinator; no Workbridge, LEGION or VMs.
2. Start RIFT normally; do not reuse old command-line authentication material.
   Require a fresh rendered game view and native identity before movement.
3. Use the latest built reader and GUI. Qualify passive Record → bounded nearby
   teaching walk → Stop Recording; inspect retained corners and `captureAttempts`.
   A capture/identity failure must still leave no complete recording.
4. Reverse-replay that newly passive-recorded route and verify settled endpoint
   error within 0.30. Also live-check the slow-direction segmentation when useful.
5. Continue the active five-hour goal using the existing roadmap; do not mark it
   complete just because an interruption handoff and push were requested.
