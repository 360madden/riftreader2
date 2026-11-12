# Recorded routes: interruption checkpoint, November 12

Checkpoint created around **08:06 EST / 13:06 UTC, November 12, 2026** on
verified **AMD-DESKTOP**, checkout `C:\work\riftreader2`, branch
`codex/modular-foundation`. Joey requested durable findings, a handoff, commit
and push after an apparent crash, then explicitly requested continuing the
five-hour goal after pushing. This is an interruption checkpoint, not completion
of that goal. Original activation was 11:56:02 UTC; original planned end was
16:56:02 UTC. Consult the live goal state before continuing.

## Continued progress after the interruption

**08:25 EST / 13:25 UTC:** RIFT was already running as fresh PID19440 when work
resumed; its build and Atank identity matched. The latest native capture fix has
now passed a live moving-player trial. GUI **Record → Stop Recording** saved
732 valid samples as four actual points over **10.2944 units**, preserving both
corners. Two observations used two acquisition attempts; 730 used one. None were
skipped. Maximum sample gap was 0.9845 seconds, during no XYZ movement. All sources
share PID19440/start `639300852881240356`, build and player identity.

The actual passive recording is preserved as
[passive-recorded-route-2026-11-12.json](validation/passive-recorded-route-2026-11-12.json).
Its original local file is
`artifacts/recorded-route-d5d30434ce344153ad529b7e97a6b8d7.json`;
the compact local audit is the same filename stem with `-validation.json`.
All four retained XYZ/heights equal actual samples after six-decimal rounding.
Maximum **sampled** point-to-saved-polyline deviation is 0.00095 units; corner
changes are approximately 82.3 and 93.4 degrees. This does not prove an unobserved
continuous path or obstacle clearance.

Direct GUI **Play Reverse** on that passive recording completed at **0.15947
units** with 26 released pulses (7 A, 7 D, 12 W), 3,526 ms requested hold; receipt
`artifacts/waypoint-run-25c26e81d2fa4a52b2cfad6b403466ef.json`.
GUI **Play Forward**, with Face then walk unchecked, completed at **0.28199
units** with 17 released pulses (8 S, 5 E, 4 W), 2,261 ms requested hold and
unchanged bearing. Receipt:
`artifacts/waypoint-run-831bda478c77430dad981b8687008d4d.json`.
The slower-direction segmentation therefore also passed a live route.

Normal GUI **Save Route** preserved the entire recording document exactly,
including metadata and heights, at
`artifacts/saved-passive-route-20261112-1322-f31b.json`. Load restored its four
ordered points. That live round trip exposed a UI issue: loading an identical
route cleared even matching progress and left stale completion text. The focused
fix now retains/restores matching progress for both Load and explicit `--route`
startup, resets changed-route progress, and reports successful Save Route paths.
Six fake-reader Tk cases passed, followed by **15 combined GUI callback tests**.

**08:32 EST live saved-file check:** a reverse playback stopped at cursor 2/4
while the next arrival was geometrically close but not yet settled/confirmed.
Receipt: `artifacts/waypoint-run-235994c357e54f398742429b984fb786.json`.
App PID74672 closed normally in the background, without restarting RIFT; new app
PID48904 launched with `--route artifacts/saved-passive-route-20261112-1322-f31b.json`
and restored Resume at 2/4. Loading that same file again kept both cursor and
checkpoint SHA256 unchanged (`384717BBC20F4E4D736B45D56145C45D4CBF729C059C8B202C1DB4A124B8E1E4`).
Explicit Resume confirmed the unfinished point with zero pulses, then completed
the last leg within **0.18620 units**, four released W pulses and 522 ms requested
hold. Receipt: `artifacts/waypoint-run-d7eaf590e6864ec6b72a470002cd04fa.json`.
The matching-file progress fix therefore passed this live case.

**08:42 EST cold-start acceptance:** RIFT PID19440 exited normally, then app
PID78236/window3938168 opened with no game present and restored the completed
4/4 route. Record/Play/Resume/Go stayed disabled while waiting, including at
character selection. After normal Glyph launch and Atank entry, that same app
bound RIFT PID79136/start `639300875003883614`/HWND5967620 and displayed a fresh
pose without starting movement. Read-only `--check` reported `inputSent=false`
and the unchanged basis SHA. WGC: `artifacts/observe-wgc-024d2b76681a417f889f782877c21b75/image.png`.
Before any later playback, native XYZ was exactly the prior settled position;
the body-bearing difference was approximately 0.00051 degrees. Source and binding:
`artifacts/cold-start-79136-before-f8.json`.

**08:44 EST physical F8 check:** Play Forward confirmed the first endpoint,
then physical F8 stopped the next leg during facing at cursor 1/4. Four D pulses
released; two STOP observations and a later independent native observation agreed
on unchanged XYZ and bearing -44.461653 degrees. Stopped receipt:
`artifacts/waypoint-run-f3a6c155226a40bbb62d0cf752a8af89.json`.
Explicit GUI Resume completed the remaining three points with 22 released pulses,
2,908 ms requested hold and final error **0.05712 units**. Receipt:
`artifacts/waypoint-run-d82e504aa9ed4cdf84811967fdae377d.json`.
F8 prevents the next pulse; an already dispatched native child, including its
startup checks, finishes its one bounded pulse and release before STOP completes.
The subsequent receipt-only change retains those existing two STOP observations
under `stopVerification`, with source paths, poses, XYZ/yaw drift, thresholds and
explicit pass/movement-detected/unavailable status. Seven focused fake-Tk receipt
tests passed; this changes neither reads nor input timing. Older receipts above
predate that structured field and must not be described as containing it.

The interruption/cleanup and unverified-capture notes below describe the earlier
checkpoint. The continued app is PID78236 and RIFT is PID79136; these are historical
identifiers to reacquire before further input, not durable selectors.

**08:48–08:50 EST interruption cases:** the updated app PID67052 received
physical F8 during fixed-facing reverse translation after one released 150-ms S
pulse. Cursor stayed 1/4; the new structured `stopVerification` retained two
identical native poses (zero XYZ/yaw drift). Receipt:
`artifacts/waypoint-run-29d66be1770c45368a513b4f64936bb3.json`.
Record → STOP cancellation then left checkpoint SHA256
`513038a272956c552e7185bc5b7844845ddee2f23b97cf960a7bde18b1dd8f12`
unchanged and created no recording file. Explicit Resume completed with 14
released pulses, 1,962 ms requested hold and **0.17762-unit** endpoint error;
receipt `artifacts/waypoint-run-3dda97a1b2e341258ab30f44d01afe60.json`.

A deliberately wrong-endpoint Play Reverse correctly refused before movement
and preserved the completed checkpoint byte-for-byte, but exposed a UI defect:
the preview switched to a provisional zero cursor and enabled Resume while the
old completion label remained. Receipt:
`artifacts/waypoint-run-2c197459066b4ad58ba234fb883b6d29.json`.
The app also reused a cumulative input receipt path across actions: that rejected
run's referenced file contains earlier inputs, ending at 13:49:10 UTC, not new
inputs from the rejected request. Do not infer new movement merely from that
older referenced file's existence.

**08:53 EST refusal fix accepted:** sixteen focused fake-reader Tk tests passed.
The GUI now reconciles playback display from the actual saved checkpoint when
the operation becomes idle, retaining both previous completed progress after an
entry refusal and newly saved partial progress after interruption. Foreground
setup failure keeps the prior display. Each GUI input operation also has a unique
input receipt path; `inputReceiptPresent` reports whether it wrote pulse evidence.
The owned app restarted normally as PID74388/window5510068. Repeating the wrong-
endpoint request preserved checkpoint bytes, restored 4/4 and zero remaining
distance, and left Resume disabled after a fresh pose. No input file was created,
and native XYZ/bearing were unchanged. Receipt:
`artifacts/waypoint-run-131259ab7d7b44378765cb53e081d710.json`.
RIFT remains PID79136. Reacquire all runtime identities before new input.

**08:55–08:58 EST close-during-playback recovery:** normal CloseMainWindow on
the exact owned app PID74388 during fixed-facing translation requested STOP and
waited for cleanup; the process exited without forced termination. All six S
pulses released, cursor stayed 1/4 forward, and two retained post-STOP poses had
zero XYZ/yaw drift. Receipt:
`artifacts/waypoint-run-e393c4a5323b401889757798bf390e40.json`.
New app PID71916/window21104234 restored 1/4 and stayed idle. Explicit Resume
completed the remaining three points with nine released pulses, 1,177 ms hold,
and **0.07079-unit** endpoint error. Receipt:
`artifacts/waypoint-run-58c06c6da5864b17af716fb96f95bf40.json`.

The game window had moved to the main display during the Computer Use F8 focus
tests. With no action active, the existing BlackBox restore ran under the exact
physical reservation and returned RIFT to `\\.\DISPLAY5`, rect
`(-1928,22)-(8,1070)`, without a game restart or gameplay input. Fresh WGC showed
Atank rendered normally: `artifacts/observe-wgc-3f9d0facd0d340b0bcc42e218ce09c58/image.png`.
Native inspection reported `desktopInputsDown=[]`; basis SHA is still unchanged.
Current checkpoint is 4/4 forward and app PID71916 is idle. Fresh native pose was
`(7421.657715, 863.586548, 2941.027100)`, bearing 60.980718 degrees, with identity
and source saved in `artifacts/recorded-route-checkpoint-1358-79136.json`.

**09:02–09:06 EST recording closure and saved-file durability:** closing owned
app PID71916 during passive capture exited normally without publishing a route
or input file; the existing 4/4 checkpoint stayed byte-for-byte unchanged.
Before/after checks: `artifacts/record-close-before-79136.json` and
`artifacts/record-close-after-79136.json`. Reopening restored that route and
completion state without movement.

GUI Save Route previously used a direct overwrite. It and completed recording
publication now reuse the checkpoint's existing sibling-temp/flush/fsync/replace
writer. Nine persistence tests and thirteen GUI callback tests passed, including
injected fsync/replace failures preserving prior bytes and temporary-file cleanup.
Normal Save Route through the updated real app wrote
`artifacts/route-atomic-save-20261112-1406-a91f.json`; its full decoded document
exactly matches the checkpoint route (all points, heights and provenance), with
no temporary file left behind and no checkpoint change. No game input was sent
for these tests. Current owned app is PID76124/window5248196, idle at 4/4;
RIFT is still PID79136. This is failure-safe replacement evidence, not a tested
guarantee against every filesystem or power-loss scenario.

**09:11–09:18 EST CLI/window handoff accepted:** GUI STOP saved cursor 2/4 reverse
and zero measured post-stop drift; receipt
`artifacts/waypoint-run-6f2046f5d78a49098a647615eb263c2c.json`.
The public CLI resumed that same checkpoint, visiting only Recorded 2 and 1:
six released pulses, 803 ms requested hold, **0.12380-unit** endpoint error.
Receipt: `artifacts/waypoint-run-a96934030e634d2d8d9a55408ba97ff7.json`;
stdout retained at `artifacts/cli-resume-79136.stdout.jsonl`.

That trial exposed two omissions now fixed: CLI failures did not retain run/input
receipt paths or measured STOP evidence, and GUI Refresh kept a stale cursor after
CLI changed the checkpoint. CLI failures now save original reason, all emitted
events/completed legs, checkpoint/input paths, binding and structured STOP evidence.
The same existing two-read STOP helper is shared with the GUI, without changing
timing or thresholds; ordinary errors add no reads. Successful CLI receipt schemas
are unchanged. Refresh/idle pose updates reconcile only matching saved progress,
without deleting malformed/unrelated checkpoint files or replacing the loaded route.
**28 focused CLI/GUI state/GUI receipt tests passed.**

Live terminal Ctrl+C through ConPTY then stopped a forward CLI run at 2/4. All
nine pulses released (1,329 ms total), and the saved `stopVerification` retained
two identical native poses with zero XYZ/yaw drift. Receipt:
`artifacts/waypoint-run-9874cb2240d14437a19f0d9d07772c05.json`.
GUI Refresh updated its former completed display to the actual 2/4 forward cursor
and enabled Resume. Explicit GUI Resume visited only Recorded 3 and 4, finishing
**0.06348 units** from the endpoint, six released pulses and 765 ms hold; receipt
`artifacts/waypoint-run-195ed726ea194085b9e385f863e199e1.json`.
This proves the tested GUI→CLI and CLI→GUI handoffs; it was a terminal Ctrl+C
test, not a user pressing a physical keyboard. The basis stayed unchanged.
Current app is PID71280/window15534380, idle at 4/4 forward, RIFT PID79136.

## Working result and use

The prototype records actual observed positions, preserves corners, saves/loads
routes, replays forward/reverse, checkpoints confirmed arrivals, and explicitly
resumes the unfinished waypoint across an app restart and a genuine RIFT restart.
The main implementation checkpoint is `9fceb14`; `e5ab946` adds the capture-race
and slow-direction fixes and the initial interruption handoff.

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

## Live gap at the initial interruption and concrete fixes

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
2. Require a fresh rendered game view and native identity before movement. Start
   RIFT normally only if needed; do not reuse authentication command lines.
3. Core recorded-route, matching-file, cold-start launcher and interruption
   workflows have the specific live results above. All three roadmap follow-ups
   now work; keep the active goal's remaining work tied to a useful unresolved
   case or the user's next priority, rather than repeating passing routes.
4. Do not repeat already-passing route trials without a change, failure or
   unresolved concern. Passive capture, its reverse/forward playback, and slow
   segmentation now have the specific live evidence recorded above.
5. Continue the active five-hour goal using the existing roadmap; do not mark it
   complete just because an interruption handoff and push were requested.
