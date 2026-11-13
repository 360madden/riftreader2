# Recorded routes and waypoint workspace — evening handoff

Verified development host: **AMD-DESKTOP**. Authoritative checkout:
`C:\work\riftreader2`, branch `codex/modular-foundation`.

## What works

- A real teaching walk retained 49 native pose observations as seven ordered
  points over 14.1347 units, preserving three substantial corners. Passive and
  controller-fed recording share the same continuity checks.
- Route Save/Load, forward/reverse replay, durable progress and explicit Resume
  work in the GUI. CLI replay/resume uses the same backend. Default startup can
  wait for one physical client; idle reconnect reacquires the same-build player.
- Final seven-point reverse replay reached 0.049798 units from its endpoint with
  34 released pulses. Independent settled observations had zero XYZ/yaw drift.
- F8 and clickable STOP preserve unfinished progress. A genuine RIFT process
  exit/relaunch case resumed four remaining legs to 0.029906 units without
  rebuilding the original movement basis. Reconnection never auto-plays.
- Screen-aligned waypoint beacons use the existing native optical camera and
  physical client/frame mapping, with PySide6 click-through presentation. Retained
  live cases cover camera motion, resize, process-level 125% scaling and genuine
  game restart. Stale/changed sources withhold presentation.
- Saved nearby unit samples can become named waypoint bookmarks while retaining
  historical source epoch, XYZ and name provenance. The Olaf two-point trial
  completed Forward at 0.229985 units and Reverse at 0.094865 units; all 35 pulses
  released. The original movement-basis hash remained unchanged.
- The new navy/mint workspace organizes controls into Replay, Edit waypoint,
  Scene & beacons and Activity. STOP remains in the header. Eighty-four focused
  GUI checks and ten map checks passed during development. Final compilation and
  withdrawn fake launch passed; native rendered appearance remains unverified.

## Use

1. Open `Waypoints.cmd` for the default single-client waiting/reconnect workflow.
   With multiple clients, bind explicitly using `--physical-pid PID`.
2. Load a recorded route. Start Forward near its start or Reverse near its end;
   the current admission tolerance is 0.30 units. Recording and playback controls
   are on Replay; coordinate editing is on Edit waypoint.
3. STOP/F8 halts the current trip and retains progress. Explicit Resume continues
   the unfinished route only after fresh identity, position and budget checks.
4. Scene & beacons contains captures, 3D views and markers. These tools do not
   determine traversability. Activity retains detailed outcomes/receipt paths.

See [the workflow](workflows/physical-waypoints.md) for CLI examples and limits.

## Important state at handoff

**Desktop control is stopped at Joey's request.** The automation session was
reset. Do not take screenshots, focus windows, read the live game or send input
without renewed user authority. No live recheck was performed for this handoff.
The isolated headless preview browser and its two owned loopback servers ended.

Last independently observed game identity was PID40452; this is historical,
not a current selection. The old helper PID4388 last displayed the completed
two-point Olaf trial. It has not been restarted to load the new UI. Restoring the
main seven-point route remains pending. Its original genuine 7/7 archived
checkpoint was byte-identical at the final offline file check:
`artifacts/waypoint-progress/c699135cc2bee7ded0ecc1f81ca2852cf01894df3da2593d519843806d4976da.json`.
The route is `artifacts/waypoint-ready-route-69312.json`; choose it from Recent
routes and load explicitly when ready. Do not fabricate or reset its progress.

The 19:03 retained inspection found no held inputs; two final settled samples
had identical entity-position bits and body bearing. Current position/window
state may have changed since. No movement is pending from this work.

## Evidence and limits

- Recorded route: `docs/validation/gui-taught-route-2026-11-12.json`.
- Final reverse: `artifacts/waypoint-run-4e2adb29a285458f80183f9c8d88522f.json`
  and `artifacts/final-replay-69312-validation.json`.
- Restart resume: `artifacts/waypoint-run-d8685dfa2a804a6cbd3a61c33ef8eaef.json`.
- Latest bookmark round trip: `artifacts/nearby-bookmark-travel-40452/validation.json`.
- Daily report: [single-file HTML](reports/2026-11-12-work-report.html), with the
  original 08:00–16:21 snapshot and evening evidence through 19:03 EST.
- UI gallery: `output/playwright/waypoint-ui/index.html`; explicitly intended
  layout representations, not native screenshots or allocation/clipping proof.

The prototype remains supervised, same-build and open-ground only: 20-unit trip,
20-waypoint, 64-pulse, 9,000-ms requested hold and 120-second limits are retained.
There is no terrain/navmesh, obstacle avoidance, occlusion test, arbitrary-world
or patch compatibility claim. Actual mixed-DPI monitor transitions remain
untested. Nearby source names/positions are candidates with separate timestamps.
Peer native-energy edits/untracked files were preserved and are outside this work.
