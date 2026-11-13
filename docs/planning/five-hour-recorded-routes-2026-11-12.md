# Waypoints roadmap

Updated November 13, 2026. Scope: the Waypoints app in `C:\work\riftreader2`
on verified **AMD-DESKTOP**, using physical RIFT. This is the current capability
and priority list; it does not activate a timed goal or start game input.

The original November 12 five-hour run and its extension through 19:44 EST are
historical. The recorded-route baseline and overlay extension have delivered the
capabilities below. Keep this existing filename so incoming links remain useful.

## Working outcome

Make saved routes useful during normal play: see where you are, identify the next
waypoint, record paths you actually walk, and explicitly replay a nearby recorded
route when appropriate. Reuse the current readers, radar, recorder and beacons.

## What is done

| Capability | Result and evidence |
| --- | --- |
| Native position/facing and same-build restart recovery | Fresh process/player binding and movement-basis reuse work without manually rebuilding the basis. Full-game restart cases were exercised; this does not establish recovery after an arbitrary game patch. |
| Recording and route files | Record/Stop Recording captures actual visited points and corners; save/load retains order, heights and observation provenance. Existing manually authored routes remain usable. |
| Forward/reverse playback and STOP/Resume | GUI and CLI playback, saved progress, explicit Resume, waiting-state launch and run receipts are implemented. Live forward/reverse and F8/Resume cases passed, including full-game restart recovery. One final reverse trial ended 0.04980 units from its endpoint with all 34 pulses released. |
| Everyday Waypoints controls | Replay, Edit waypoint, Scene & beacons and Activity tabs; organized route controls, smaller-window layout fixes, readable recent-route names and full-path hover text. |
| World-to-screen beacons | Live click-through markers, selected-point guidance and optional selected-target cues reuse the native camera projector. Camera-motion flicker fixes and live appearance controls are in place. Marker sessions have no ten-minute GUI limit and can remain visible while their owning Waypoints window has focus. |
| Map-click points and live edits | Unmeasured points receive explicitly estimated display heights. Add/edit/remove, rename/reorder, Undo, Load and guide-selection changes update the running overlay without restarting its reader. Estimates remain separate from measured heights. |
| Shared live radar and player pose | The main window's radar and XYZ/facing header reuse the beacon reader, up to five updates per second. Original sample times are preserved; missing/stale/foreign feedback clears the display. Hide returns to the two-second idle reader after the beacon child exits. |

The latest radar slice passed **88 focused checks** and a visible-scene live test
on November 13: one 150 ms A pulse changed facing **44.40 -> 71.76 degrees** and
rotated the radar; one 150 ms W pulse moved Atank **0.96845 units** and updated the
radar/header with unchanged facing. Both actions confirmed release, and the same
beacon sampler remained running. This is a short local trial, not a claim of
uninterrupted operation across every camera, display or game state.

Use the [Waypoints guide](../workflows/physical-waypoints.md) for operation, the
[recorded-route evidence](../handoff-2026-11-12-recorded-routes.md) for earlier
playback/restart trials, and the
[overlay and radar verification notes](../validation/waypoint-overlay-camera-2026-11-12.md)
for recent beacon and shared-reader checks. Old PID/window values in evidence are
historical; reacquire the actual target before live work.

## Next priorities, in order

Ship one useful slice at a time. These are planned work, not existing features.

### 1. Compact radar while playing

Add a compact radar mode that stays visible over RIFT without opening the full
editor. Reuse `waypoint_map.py`, the existing Qt overlay environment and the owned
beacon pose feed; do not add another native sampler.

- Show player facing, route points and the selected destination with distance.
- Provide simple zoom, opacity, Hide and an explicit unlock for moving the radar.
  Normal play mode should be click-through and should not steal game focus.
- Reuse existing marker visibility, process ownership and stale-data behavior.
  Enabling compact radar should make any required beacon-reader start explicit.

**Done when:** the real radar follows one short turn and walk in RIFT, stays
readable at a compact size, can be moved/hidden, and normal game clicks pass
through. Verify reader reuse and no automatic movement.

### 2. Passive route guidance during manual play

Let the player explicitly choose a route, direction and starting point, then walk
it manually while the radar and existing beacons identify the next waypoint.

- Update distance and advance only after a small arrival radius is satisfied by
  multiple fresh samples. Do not jump to a later nearby point or skip a corner.
- Use the same waypoint number/name/color in the radar and world beacon. Reuse
  the existing selected-marker guide and off-screen cues before adding visuals.
- Keep manual guidance progress separate from the genuine playback checkpoint;
  passive samples must not create movement authority or silently change Resume.
- Pause advancement when samples are unavailable; route edits or identity changes
  require a valid guidance state before continuing. This mode sends no game input.

**Done when:** a short manually walked route advances in order, remains stable
when standing near an arrival boundary, and does not advance on stale samples or
alter saved automated-playback progress.

### 3. Exploration breadcrumb trail

Display a recent trail of positions actually visited, with an explicit option to
save it as a route. Reuse the recorder and shared pose feed.

- Keep useful corners and XYZ/height provenance; limit retained samples so normal
  use stays light. Break the trail at missing samples, teleports or owner changes.
- Keep manual map-click points distinguishable from observed positions. Reuse
  route save/load rather than inventing another map storage format.

**Done when:** walking a short path produces a readable trail, saving/reloading
preserves its corners and measured points, and a sampling gap never becomes a
falsely observed connecting segment. Full saved world mapping is a later step.

## Limits and later work

- Preserve current movement budgets, fresh target/player/build checks, exclusive
  input ownership, foreground checks and STOP/key release. Playback remains an
  explicit action; reconnecting or showing a radar never starts movement.
- Keep display pose separate from movement admission. Route/marker display can
  remain useful even when a route exceeds the existing playback distance limit.
- Estimated beacon heights are display approximations. Slopes and other floors
  can place them above/below terrain. World/zone identity, occlusion, walkability
  and obstacle clearance remain unresolved; a projected point proves none of them.
- Defer automatic obstacle avoidance, terrain extraction/navmeshes, automatic
  stuck detours, combat/quests, indefinite patrol and increased movement budgets.
  Revisit terrain tooling when actual usable geometry is available.
- Black captures alone are not proof that RIFT is black or crashed. Joey reported
  recovery when the main monitor was powered back on; fresh capture then worked
  on the same process without a restart. Check display power and reacquire window
  geometry/capture first. The exact monitor/GPU mechanism remains unconfirmed.

## Keep the workflow practical

Reuse the current implementation, make the smallest coherent change, run focused
checks and try the actual RIFT workflow when authorized and noninterfering. The
root coordinates all live desktop/game actions on the verified host. Delegate
only useful independent work, preserve concurrent edits, and review integrations.
Record meaningful results and limits in the existing evidence notes; avoid new
frameworks, repeated passing test sweeps and per-step reports. Commit verified
files and push when authorized. Update this priority list when a slice ships.
