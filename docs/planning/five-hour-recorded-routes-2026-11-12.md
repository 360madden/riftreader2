# Five-hour goal: record, replay and resume nearby routes

Status: goal activated November 12 at 11:56:02 UTC. Interruption checkpoint and
verified results: [recorded-route handoff](../handoff-2026-11-12-recorded-routes.md).
The user requested continuing the goal after saving and pushing that checkpoint.
Scope: `C:\work\riftreader2`, verified **AMD-DESKTOP**, physical Atank only.
Start the five-hour window when the user activates the goal.

## Working outcome

Teach the prototype a short path through observed open ground, save it, replay
the same points forward or backward, and explicitly resume the unfinished route
after STOP or a full RIFT restart. Normal use should require buttons and a saved
route, without entering coordinates or rebuilding movement calibration.

The existing prototype already has native position/body-facing reads, named
waypoints, JSON save/load, a local preview, bounded feedback movement, STOP/F8,
same-build/player calibration reuse and idle reconnection. Build on those.

## Five-hour sequence

Time ranges guide priorities; ship working slices as soon as they pass.

| Time from activation | Work | Observable result |
|---|---|---|
| 0:00–1:00 | Implement one small recorder accepting fresh pose samples; save start/end, real corners and useful intermediate points. Feed existing controller observations into it first. | A real short teaching run produces a loadable route through positions Atank actually visited. |
| 1:00–2:00 | Add Record/Stop Recording, save/load and forward/reverse playback to the existing window. Support passive recording of normal movement with sufficient sampling cadence. | Record a short path, then replay it in reverse back toward its start. |
| 2:00–3:00 | Add visible current/next waypoint and durable progress; explicit Resume continues the unfinished waypoint in the chosen direction. | F8 stops; Resume continues without restarting the route or skipping a corner. |
| 3:00–4:15 | Exercise the complete workflow, including a genuine RIFT process exit/relaunch and explicit resume after reconnection. Fix demonstrated failures. | Saved route and progress survive, calibration stays unchanged, and replay reaches the endpoint. |
| 4:15–4:45 | Finish remaining core issues, then take useful follow-ups below in order. | Additional usable capability rather than repeated reporting or green-test sweeps. |
| 4:45–5:00 | Finish active bounded actions, verify cleanup, commit tested files, update usage and leave one concise handoff. | Working committed state, exact live results and honest remaining limitations. |

Get the first actual record/replay result early. Do not hold all live use until
the last hour or build a generalized recording/navigation framework first.

## Implementation choices

- Reuse `physical_waypoints.py`, its `run_route`/`run_leg` feedback, the native
  readers, `waypoint_map.py`, seed checks and connection helper. Add small pure
  recording/progress helpers where they keep the main window manageable.
- One recorder should accept fresh snapshots from both passive observation and
  existing controller callbacks. The controller already observes each released
  pulse. The GUI's two-second idle refresh is too coarse for reliable corners;
  assess practical reader cadence and reuse existing paced samples if needed.
  A new daemon, memory scanner or transport is unnecessary for this goal.
- Preserve initial/final positions and turn/leg boundaries. Deduplicate jitter
  and near-collinear samples conservatively. A simplifier must not cut across a
  corner or bridge missing samples, a teleport, or a process/player change.
- Keep existing `{"waypoints": [["name", x, z]]}` files usable. Optional recording
  metadata and a small progress record can retain route identity and capture
  provenance; do not retag old measurements or persist live process addresses.
- Reverse playback reverses the ordered path. Start forward near its recorded
  start, or reverse near its recorded end. Avoid an automatic direct approach
  from an arbitrary location and avoid guessing a nearest waypoint to skip to.
- Save progress against the exact route contents and direction. Advance the next
  waypoint only after its full settled arrival is confirmed. A partially finished
  waypoint remains unfinished. Editing the route/direction invalidates that cursor.
- Resume reacquires the live identity and a fresh settled pose. Require a suitable
  position on the unfinished recorded leg; refuse an off-route or ambiguous entry
  instead of shortcutting corners. A conservative repeat after a checkpoint-write
  interruption is preferable to silently skipping an unconfirmed point.
- Reconnection restores readiness and progress display. Playback begins only on
  an explicit Play/Resume request. Stop Recording stops passive capture; playback
  STOP retains ownership of only the keys sent by the controller.
- Keep the current **20-unit planned-trip, 20-waypoint, 64-pulse, 9,000-ms requested
  hold and 120-second trip limits**, plus the existing per-segment limits, freshness,
  seed-response, foreground, identity and release checks. Recompute the remaining
  trip length at each explicit start/resume. Do not silently truncate a route.

## Live acceptance

Use a short, reviewed open-ground path with at least two clear corners, normally
10–15 native units in length. Choose it from fresh pose and visual evidence rather
than assuming old world coordinates or a clear route. An open path is useful for
demonstrating reverse replay from its end. A known clear closed path is acceptable
when it gives better evidence or stays inside the current limits.

The agent can generate the teaching walk with the existing bounded controller
while recording its actual poses. For passive GUI recording, an independently
invoked existing controller can produce the walk; recording itself sends no input.
This allows unattended development without requiring the user to demonstrate it.

Core acceptance criteria:

1. Recording captures a real path and preserves the two corners. Stale, missing
   or identity-changing observations cannot become a falsely continuous route.
2. Save/load preserves point order, and existing manually authored route files
   still load. Forward and reverse replay traverse the same path in opposite order.
3. Playback arrives within the current **0.30-unit** endpoint tolerance, with
   separate settled observations and confirmed release. No no-progress or
   wrong-response condition triggers repeated blind movement.
4. F8 or clickable STOP during playback prevents the next pulse. The progress
   record keeps the unfinished waypoint; explicit Resume completes the remainder.
5. With the route/progress saved, fully exit RIFT, confirm the old process ended,
   launch normally and enter Atank. The app reconnects to the new process without
   modifying the movement basis. Explicit Resume uses fresh guards and completes.
6. Route edits, wrong direction/cursor, changed player/build, excessive distance,
   off-route position and incomplete recording are refused or require a new
   explicit start. Offline tests cover refusal paths that are unsuitable to induce
   in the game. GUI and backend state agree on completion and STOP.

Retain concise before/after screenshots and existing native/input receipts for
meaningful live results. Label simulator results and blocked live acceptance
honestly. One successful same-build case does not qualify arbitrary patches or
terrain navigation.

## Useful follow-ups if core work finishes early

Take these in order while time remains, without displacing unfinished core work:

1. CLI parity for forward/reverse playback and explicit resume, using the same
   backend and progress semantics as the window.
2. Allow the default single-client launcher to open in a waiting state before
   RIFT is ready, then bind when Atank enters the world; retain ambiguity/player/
   build checks and preserve explicit PID pinning.
3. Retain complete GUI run outcomes through the existing receipt mechanism and
   make the active/next/completed waypoints easy to identify in the current preview.

Exclude combat, quests, arbitrary Lua execution, terrain extraction/navmesh work,
automatic stuck detours, indefinite patrol and larger input budgets from this goal.
The earlier DotRecast research remains useful when actual RIFT geometry is available.

## Agent workflow and autonomy

- Root owns UI/controller integration and is the sole coordinator of live game
  input. Useful independent workers: recording geometry/tests; progress/resume
  state/tests; a targeted control/concurrency review when a concrete risk needs it.
  Assign disjoint files and integrate working slices promptly. Idle workers when
  their useful tasks end; do not invent work to fill slots.
- Use the repository's model guidance for routine workers and deeper targeted
  reviews. Keep all agents on the verified local host. Preserve concurrent edits
  and the Git index. Make local coherent commits; do not push without authorization.
- Continue implementation, focused tests and useful live verification without
  asking the user to make routine choices. This goal authorizes nearby bounded
  movement/turning, normal RIFT exit/relaunch and existing display recovery for
  these trials under the established ownership and STOP rules.
- If live RIFT or capture is unavailable, work on independent code, simulations,
  saved-source replay and integration. Authentication still needs the user. Stop
  only for a real blocker that leaves no useful authorized work, or user direction.
- This is five hours of development, testing and integration; live trials remain
  finite. Fix observed problems and use the follow-up queue if ahead of schedule.
  Do not fill time with repeated passing checks, new process layers or reports.

## Text to paste as the goal

Work autonomously for the next five hours in C:\work\riftreader2 on verified
AMD-DESKTOP to deliver a usable recorded-route prototype: record actual nearby
movement with corners, save/load the route, replay it forward or backward, and
explicitly resume the unfinished route after STOP or a full RIFT restart.

Follow docs/planning/five-hour-recorded-routes-2026-11-12.md. Reuse the current
native readers, waypoint controller, calibration-seed reuse, reconnect logic,
preview and STOP/release handling. Keep the existing route/input limits. Build
the smallest working slices and live-test early. Use productive subagents with
disjoint ownership; the root alone coordinates game input. Preserve peer work.

Do not depend on me being present to walk a teaching route: use the existing
bounded controller to produce a reviewed short open-ground demonstration and
record actual fresh poses. Then verify reverse replay, STOP/Resume and a real
RIFT process restart, with endpoint error within 0.30 units and no movement-basis
rebuild. Nearby bounded movement, normal restart and existing display recovery
are authorized for these tests under the existing guards.

Keep making useful progress until the five-hour window ends or a genuine blocker
leaves no authorized work. Make routine choices yourself. If core work finishes
early, take the roadmap's follow-ups in order. If live work is blocked, continue
independent implementation and offline verification. Keep documentation and tests
proportional; avoid process-heavy work and time-filling repetition.

At the end, finish/release owned input, leave a tested usable state, commit the
verified changes, and give one concise handoff with what worked live, remaining
limitations and how to use it. Report unfinished work honestly.
