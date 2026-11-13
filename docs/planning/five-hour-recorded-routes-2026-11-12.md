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

## Delivered exploration priorities — November 13

The three slices below are implemented and passed their local live acceptance.
The implementation checkpoint is `ece5eac`; the later placement correction makes
the radar follow game-window movement while retaining the user's relative offset.
See the [live evidence](../validation/waypoint-overlay-camera-2026-11-12.md#compact-radar-manual-guidance-and-breadcrumb-acceptance--november-13) and
[Explore usage](../workflows/physical-waypoints.md#explore-while-playing).

### 1. Compact radar while playing

A compact radar stays visible over RIFT without opening the full editor. It reuses
`waypoint_map.py`, the existing Qt overlay environment and the owned beacon pose
feed, with no additional native sampler.

- Show player facing, route points and the selected destination with distance.
- Provide simple zoom, opacity, Hide and an explicit unlock for moving the radar.
  Normal play mode should be click-through and should not steal game focus.
- Reuse existing marker visibility, process ownership and stale-data behavior.
  Enabling compact radar should make any required beacon-reader start explicit.

**Verified:** real turn/walk updates, zoom from 10 to 2 units, opacity from 85% to
60%, and locked click-through. Joey confirmed manual dragging; the same radar HWND
changed position. Game geometry also changed, so exact drag distance is unqualified.
Focused checks cover drag handling, saved relative placement and geometry changes.

### 2. Passive route guidance during manual play

The player chooses a route, direction and starting point, then walks it manually
while the radar and existing beacons identify the next waypoint.

- Update distance and advance only after a small arrival radius is satisfied by
  multiple fresh samples. Do not jump to a later nearby point or skip a corner.
- Use the same waypoint number/name/color in the radar and world beacon. Reuse
  the existing selected-marker guide and off-screen cues before adding visuals.
- Keep manual guidance progress separate from the genuine playback checkpoint;
  passive samples must not create movement authority or silently change Resume.
- Pause advancement when samples are unavailable; route edits or identity changes
  require a valid guidance state before continuing. This mode sends no game input.

**Verified:** the read-only guide confirmed points 0, 1 and 2 in order during an
independently driven, bounded W/A/W trial. Both forward steps settled with zero
measured drift. The GUI showed completion; no playback checkpoint was created.
Focused checks cover reverse/selected starts, boundary confirmation and stale data.

### 3. Exploration breadcrumb trail

A recent trail displays positions actually visited, with an explicit option to
save a chosen segment as a route. It reuses the recorder and shared pose feed.

- Keep useful corners and XYZ/height provenance; limit retained samples so normal
  use stays light. Break the trail at missing samples, teleports or owner changes.
- Keep manual map-click points distinguishable from observed positions. Reuse
  route save/load rather than inventing another map storage format.

**Verified:** the live trail retained 129 observations and saved five measured
points at three distinct locations, preserving the actual corner. The existing
route parser loaded the export with original sample times/heights. Focused checks
cover sampling gaps, owner changes, vertical corners, retention and no false
connecting segment. Full saved world mapping remains later work.

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

## Proposed helper CLI — November 13

Status: proposal, not implemented. Source and actual `--help` output were inspected
on AMD-DESKTOP. Keep the existing command lines compatible while adding a console
entry point named `rr2-waypoints.cmd`; `Waypoints.cmd` remains the GUI launcher.

### Existing capabilities to reuse

- `scripts/physical_waypoints.py`: explicit host/PID, go-to X/Z, face bearing,
  route run, recorded-route playback, forward/reverse, Resume, checkpoints and
  recording during a commanded run. Movement requires `--execute`; F8/Ctrl+C
  latch cancellation and native pulses own their release. Output is currently
  JSON event lines followed by a final result, not a selectable single-JSON mode.
- `scripts/launch_physical_waypoints.py`: GUI launch, saved-route startup,
  unique-client waiting/reconnection and read-only `--check`. Its console help
  works, but `Waypoints.cmd` launches `pythonw`, so that wrapper is not a useful
  console-output entry point.
- `scripts/live_physical_waypoints.py`: internal marker/presenter CLI with
  pose, route-update, appearance, radar and exploration files. It starts its own
  feed; it does not attach commands to the open GUI.
- The GUI owns loaded/dirty route state, selection, marker lifecycle, manual guide
  and trail history. Its callbacks and `ExploreControls` are reusable. The missing
  pieces are session discovery, a small dispatcher and correlated command results.

### Command surface

Use noun/verb commands and one-based waypoint/segment numbers matching the UI.
The following names are proposed, not runnable commands yet.

| Group | Commands and intent |
| --- | --- |
| Shared helper basics | `help [COMMAND]`, `--version`, `capabilities`, `status`, `doctor`, `stop` |
| App/session | `app list`, `app open`, `app show`, `app hide`, `app close`; select an existing instance with `--session ID`, choose a RIFT client at launch with `--pid PID` |
| Route | `route list/load/save/new/add/update/remove/reorder/select/undo/validate`; `add --current`, `add --target`, or explicit `--x/--z`; `list --file FILE` and validation can work offline |
| Radar | `radar status/show/hide/lock/unlock/move/set`; range/opacity and position relative to the game client, avoiding desktop-coordinate guessing |
| Beacons | `beacons status/show/hide/set`; size/opacity/labels, selected-target inclusion and selected-point guide |
| Manual guide | `guide status/start/stop`; `start --direction forward|reverse --from N` uses passive arrival confirmation and never sends input |
| Breadcrumbs | `trail status/start/stop/list/save/clear`; `save FILE --segment N|latest` exports a separate existing-format route |
| Existing route recorder | `record status/start/stop/cancel`; keep Stop-to-save and Cancel distinct from breadcrumb history |
| Movement/playback | `move to X Z`, `face BEARING`, `route run`, `playback start/resume/status`; movement requires `--execute`, playback has explicit direction/checkpoint and deterministic walk mode |
| Views/receipts | `view save/open`, `view open-3d`, `receipt list/show`; reuse existing capture bundles and receipts |

### Reusable behavior and help

- No arguments show a short help page. Each group and leaf supports `--help`;
  `help radar set` resolves to the same content as `radar set --help`.
- Top-level help groups commands by purpose and shows a handful of common examples.
  Leaf help states purpose, live-session requirements, side effects, units/ranges,
  defaults and examples. Explicitly distinguish passive `guide` from input-sending
  `playback`. Enable typo suggestions, disable abbreviated long-option guessing.
- Human-readable output is the default. `--json` writes one versioned result to
  stdout, including failures; logs go to stderr. Streaming commands use explicit
  `--jsonl`. No color/progress decoration enters machine-readable output.
- Common flags include `--session`, `--timeout`, `--json` and `--no-color`;
  `--jsonl` is for streaming commands. Timeouts/defaults are documented per command,
  so a movement operation is not accidentally given a short status-query timeout.
- Common result fields: schema version, command, success/status, session/target,
  data, and error code/message/recovery hint. Live pose reports retain source time,
  age and qualification; enabled display and actually visible display are distinct.
- Proposed exit codes: 0 success, 1 operation failure, 2 usage, 3 unavailable or
  ambiguous session/target, 4 busy/refused, 5 timeout/outcome unknown, 130 cancelled.
- Commands do not open file choosers or confirmation dialogs. Paths and save/discard
  decisions are explicit; existing files require an explicit overwrite option.
  Return actionable errors when a decision is missing. Route edits return revision
  information so automation can guard against concurrent changes.
- Quick commands return after the GUI applies the change. Movement commands wait
  for their terminal result by default, retaining receipts and Ctrl+C/F8 behavior.
  Acknowledged/running and completed are separate states; timeouts are not success.
- `stop` mirrors the helper's owned STOP behavior, with release and observed
  stationary evidence reported separately. It does not promise to cancel arbitrary
  in-game autorun. `trail stop` retains history; `record stop` saves and `record
  cancel` discards. Do not silently change existing STOP/F8 semantics.

Use the current `argparse` implementation. Python 3.14.6 is installed; subcommands,
grouped help and typo suggestions are already supported by
[Python's standard library](https://docs.python.org/3.14/library/argparse.html).
Reuse conventions across
future `rr2-<helper>` apps; extract a small shared parser/result helper after a
second app needs it, rather than building a generalized application framework.

### Connecting to the open app

The GUI remains the owner of live state, native readers and actions. CLI requests
enter a small allowlisted dispatcher on the existing Tk poll/worker paths. Reuse
callbacks after separating explicit arguments/results from file dialogs; do not
simulate clicks or let the CLI directly edit the presenter's private state files.

For the first implementation, reuse atomic JSON with one request and response per
ID in an owned local session directory. The GUI publishes its session ID, PID/start
identity and protocol version; the console verifies liveness and selects exactly
one session. Bound work per poll and prioritize STOP. Expire stale requests,
correlate results and deduplicate request IDs. Never silently retry an uncertain
movement request. Keep the command/result contract independent of this transport.
No helper starts an additional sampler just to answer `status`.

### Implementation order

1. Console launcher, command/help tree, JSON/exit conventions, session discovery,
   status/doctor/stop and app attachment. Verify queued versus applied results,
   stale/ambiguous sessions and busy responses.
2. Route editing, radar/beacons and guide/trail controls, including explicit-file
   export. Run a complete CLI-only demonstration against the existing GUI: load
   route, configure radar, guide/record, save trail and inspect status without
   desktop clicking or duplicate readers.
3. Wrap existing movement/playback and recorder/view/receipt operations. Preserve
   explicit execution, target ownership, STOP/release and dirty-route handling;
   verify cancellation and receipts before claiming full UI parity.

Keep the first useful result small: controlling the open radar and querying its
actual state from the console. Broader command coverage follows in coherent slices.

## Keep the workflow practical

Reuse the current implementation, make the smallest coherent change, run focused
checks and try the actual RIFT workflow when authorized and noninterfering. The
root coordinates all live desktop/game actions on the verified host. Delegate
only useful independent work, preserve concurrent edits, and review integrations.
Record meaningful results and limits in the existing evidence notes; avoid new
frameworks, repeated passing test sweeps and per-step reports. Commit verified
files and push when authorized. Update this priority list when a slice ships.
