# Joey D's Waypoints

The desktop helper and console frontend share **Joey D's Waypoints v1.2.0**
branding. The red panda in the header is also the window icon. Existing
`Waypoints.cmd` and `rr2-waypoints.cmd` entry points stay compatible.

The window groups its controls into **Replay**, **Edit waypoint**, **Scene &
beacons**, **Explore**, **Library**, and **Activity** tabs. The route list, local map, current pose and
STOP/F8 stay visible above them. Replay separates playback, recording and direct
movement; Edit waypoint contains the coordinate fields and route-edit actions.
F2 on a selected row opens Edit waypoint and focuses its name. Full receipt paths
and detailed status remain in Activity. Load/Save and Recent routes stay with the
route list. The radar is a player-relative reference diagram; its dots and lines
do not establish terrain visibility or clearance.

## Longer routes

Routes now support **1,000 world units of planned travel and 500 waypoints**.
Recording accepts up to 30,000 fresh observations; saved routes, Library,
Forward/Reverse playback, explicit Resume and Explore trail export share the
same route limits. Existing route files and checkpoints retain their format and
hashes. No conversion is required.

Each explicit trip has a shared **30-minute** limit. The legacy pulse engine also
has an 8,192-pulse and 600-second requested key-hold budget. STOP/F8 requests
release of this helper's owned input, preserves unfinished playback progress and
prevents further movement. Resume rechecks the saved route, direction,
host/build/player, current position and height before continuing, with a fresh
trip budget. Reconnection never auto-resumes.

These larger trip budgets do not relax the existing progress, drift, freshness,
ownership and release checks. In legacy pulse mode, requested pulses remain at
most 150 ms and intermediate targets remain at most four units apart. Use a
clear taught path: there is still no obstacle avoidance or terrain planner. The
longer envelope is covered by simulated runner and withdrawn-window checks; live
acceptance of continuous travel, map-click movement and a 1,000-unit trip is
still pending.

To keep large routes responsive, world beacons display at most 64 route markers
per frame, favoring nearby points and retaining the saved next waypoint and
selected landmark. The complete route and progress remain intact. The main
preview offers larger zoom ranges and Fit. It draws every waypoint and connector
while displaying up to 64 number badges, prioritizing selected/active points,
nearby points and route coverage. All true nodes remain selectable. Explore's
compact radar retains its separate local ranges.

## Movement modes and map destinations

New Waypoints windows start with **Continuous travel** enabled. Continuous mode
holds RR2's owned forward key while repeatedly checking fresh position, progress,
drift, identity, foreground ownership, deadlines and cancellation. It does not
turn on, detect or cancel RIFT's NumLock autorun. The legacy bounded-pulse engine
remains available as a fallback: clear the **Continuous travel** checkbox, or
change the running helper's setting from the CLI. Changing the setting sends no
game input and applies to subsequent route, playback and direct-move runs.

The controller finishes and settles its initial turn before forward travel.
While running, it tolerates small heading differences and steers only for
meaningful route departure. Corrections are brief nudges separated by settling
time and travel progress, rather than repeated left/right tracking. The last
1.5 units use a straight final approach. The existing 0.50-unit corridor limit
still stops a drifting run; reducing corrections does not widen that limit.

```powershell
.\rr2-waypoints.cmd move mode --engine continuous
.\rr2-waypoints.cmd move mode --engine pulse
```

The local preview also has an explicit **Click to move · clear path only** mode.
When it is off, clicking a route node selects it and clicking open map space adds
a waypoint. When it is on, a click chooses a flat world X/Z destination and
starts a guarded direct move without editing the route or clicking inside RIFT.
Map-click movement uses the continuous mover. It rejects stale map origins when
the player moved more than 0.05 units or turned more than 0.5 degrees since the
map was rendered, and it repeats the normal identity, freshness, ownership,
progress and release checks.

The CLI can inspect the same RR2-owned map projection before committing to the
move. Canvas coordinates are physical pixels in the helper's local preview:

```powershell
.\rr2-waypoints.cmd preview project --canvas-x 220 --canvas-y 120
.\rr2-waypoints.cmd move pick --canvas-x 220 --canvas-y 120 --execute
```

`preview project` uses the existing rendered map and cached pose; it performs no
new RIFT read and sends no game input. `move pick` requires `--execute`, obtains
fresh admission evidence and runs the guarded direct move. A numbered badge
projects to its actual waypoint rather than to the ground drawn beneath the
badge.

This map is a player-relative **flat X/Z reference**, not navigable terrain.
Height, floors, slopes, walls, obstacles and clearance are unavailable. Choose
only a destination with a known clear open-ground path. The practical per-trip
envelope remains 1,000 planned world units, 500 waypoints and 1,800 seconds; map
projection and zoom do not expand it.

**STOP**, Esc in the focused helper, or the temporary F8 listener requests
release of RR2-owned movement and latches cancellation for the active action.
STOP does not cancel arbitrary game autorun or manual input. For interrupted
route playback, use explicit **Resume** after the helper reports it ready;
Resume re-runs admission checks and continues from the saved checkpoint. It does
not automatically resume a one-off map click or direct destination.

These controls and guards are implemented and covered by offline tests. One live
clear-path route/STOP/Resume case passed after the native near-goal correction:
STOP retained `nextIndex: 1`, then Resume completed the remaining seven legs and
the final nine-point cursor over **23.10184156 planned route units** on a repeated
2.89-unit clear segment. Retry-leg errors were 0.135–0.240 units, stationary
verification passed with zero drift, and all seven native receipts reported
successful release with no pressed inputs. This was not a single 23-unit leg and
does not establish obstacle navigation. See the
[retained result](../../artifacts/movement-upgrade/long-route-resumed.json).

A separate straight **ten-unit clear-path out-and-back** passed with one W hold
per leg: 1.601 and 1.560 seconds, ending 0.243274 and 0.252260 units from the two
goals. Both native results released successfully with no pressed inputs, and the
final stationary check measured zero XYZ and yaw drift. See the
[ten-unit result](../../artifacts/movement-upgrade/10-unit-out-and-back.json).

CLI owned-map movement also passed live. `preview project` and `move pick` used
the exact rendered map from an actual mapped **411×182** Waypoints helper and the
same `map-go` backend as the GUI callback. The move arrived 0.203314 units from
the projected destination and left the loaded route's file, revision, count,
selection and clean state unchanged. See the
[map-click result](../../artifacts/movement-upgrade/map-click-move.json) and its
[run receipt](../../artifacts/waypoint-run-1b25a6f82e1b42da9540e8bcd4cdace7.json).

An actual GUI pointer trial also passed. CUA armed **Click to move** and clicked
the owned map. The first stale-origin click was refused before input. After an
explicit new click at screen pixel 879,390, the shared `map-go` backend arrived
0.2644456 units from its goal. The original six-point route, revision 1,
selection 6 and clean state remained unchanged, and the visible UI reported the
saved run receipt and new pose. See the
[GUI status](../../artifacts/movement-upgrade/gui-click-status.json) and
[run receipt](../../artifacts/waypoint-run-18ceec53f31d4b948e6c2fdadf11d197.json).
These scoped live cases accept the v1.2.0 movement helper. Final restoration
returned the character within 0.166 units of the original position and left the
helper visible and idle in continuous mode, Click-to-move off, STOP latched and
no release fault. The original six-point route remained revision 1, point 6
selected and clean; range 10, live pose on and overlays off were restored. Do
not treat these cases as qualified autonomous terrain navigation or a complete
automated player. See the
[final restoration state](../../artifacts/movement-upgrade/final-state.json).

## Header, live pose and STOP

The header keeps the verified host/PID, Refresh, Live pose and STOP together.
Hover the host/PID for the bound process identity. **Details** opens Activity;
hover the status message to reveal its full text, including compacted receipt
paths. The smaller Details button retains route-list space at compact sizes.

The pose row rounds display coordinates to three decimals without changing saved
values. Its badge distinguishes **Fresh**, **Cached** and **Pose unavailable**,
with acquisition age, paused refresh and an in-progress read. Hover coordinates
or the badge for source, sample time, age and qualification. Acquisition time is
retained from native samples rather than replaced with the time the GUI received
an event. Expired beacon samples retain only historical timestamp provenance;
they do not supply current coordinates. Live pose reuses the owned beacon reader
while running, otherwise the existing idle reader at two-second intervals.
Pausing keeps an explicitly cached display. The switch is session-only.

```powershell
.\rr2-waypoints.cmd pose status
.\rr2-waypoints.cmd pose refresh
.\rr2-waypoints.cmd pose set --live off
.\rr2-waypoints.cmd pose set --live on
.\rr2-waypoints.cmd stop
```

`pose status` reads existing feedback; `pose refresh` performs one fresh read
through the same path as Refresh. Neither sends game input. `pose set` controls
the same checkbox. Paused samples keep `status: unavailable` for display
freshness, even after a manual refresh, with `sampleStatus: cached` and their
actual age. `status.pose` reports these fields too. Actions retain their
independent fresh-pose and identity checks.

**STOP** always remains available. Its adjacent hint reports whether the global
F8 listener is actually active, unavailable, or inactive; it is registered only
for this helper's movement action. **Esc** invokes STOP while this app has focus.
STOP requests release of the helper's owned continuous hold or prevents the next
legacy pulse, then waits for release evidence; it cancels recording (use Stop
Recording to save) and hides owned overlays. It does not cancel arbitrary game
autorun or manual input. An idle STOP explicitly says game motion is unverified.
A later explicit action can clear the latch.

CLI STOP and `status.controls` separate the latch, owned-action state, actual F8
availability, key-release receipt references and stationary evidence. Only the
action associated with that STOP can contribute a result. An idle STOP reports
both evidence fields as `not-measured`, without reusing an older receipt or
performing a stationary check. These fields also appear in diagnostics.

## Route list and local preview

The main route list shows stable **#** numbers alongside the original waypoint
name and X/Z. Those numbers match the local preview even during reverse playback;
drawing/travel order never renumbers the saved route. Compact rows retain usable
list space, and resizing keeps the selected point visible. Hover a row for its
full name, coordinates, cached player distance and measured/estimated height
context. Double-click or F2 opens Edit waypoint while preserving unapplied fields.
Save Route/Save As require a nonempty route and applied/reset fields.

With **Click to move** off, click a preview node or number badge to select its
route row. This does not add a point or obtain another pose. Click open space
inside the preview to add a waypoint; when an existing row is selected the new
point gets a fresh `Point N` name. Pending fields must be applied/reset before
either action. Addition reuses the existing live pose check: if the player moved
or turned since the plotted sample, the map refreshes and asks for another click
instead of placing the point against the wrong origin. Added map points retain
estimated, rather than measured, height evidence until explicitly measured.

The header reports visible/off-screen point counts for the local viewport.
**+**, **−** and **Fit** affect this reference display only. Fit needs a cached
position and at least one route point; it remains capped at 1,500 units and may leave
distant points off-screen. Its hover explanation and CLI status expose that cap.
No edge-clamped points or terrain clearance are implied. The preview starts at
10 units on reopening; its range is separate from Explore's compact radar.

```powershell
.\rr2-waypoints.cmd preview status
.\rr2-waypoints.cmd preview set --range 5
.\rr2-waypoints.cmd preview fit
.\rr2-waypoints.cmd route select 7
```

Allowed preview ranges are 2, 5, 10, 20, 50, 100, 250, 500, 1,000 and 1,500 units. These commands use existing
cached data, obtain no new pose and send no game input. `status.preview` and live
`route list --json` expose radius, selected numbers, viewport counts, named
off-screen points, cached/fresh/unavailable pose status and age, and
`fitLimited`/`requiredRadius`. Offline route inspection does not fabricate a live
preview. `terrainAvailable` and `inputSent` remain false. Zoom/Fit never alter
route coordinates, saved progress, movement admission or the 1,000-unit trip limit.

## Activity and diagnostics

**Activity** displays the current session's diagnostic events, including startup,
handled-command, callback and worker errors. Each line has a local time and
severity color; messages include command/request context and readable exception
messages. The view uses the same event source as CLI diagnostics rather than a
separate collection of manually appended status lines.

Choose **All**, **Warnings + errors** or **Errors**, and use **Find** to search
structured event details. **Details** adds metadata and multiline tracebacks.
**Follow latest** follows new output; scrolling or clicking in the text pauses it
so selection and position stay stable. Re-enable Follow to catch up. Resizing and
ordinary layout changes do not pause it. **Clear view** hides existing events;
**Show history** restores retained events. Neither action deletes saved logs.
These display controls reset to All/Follow on reopening and send no game input.

The session buffer retains 500 attempted events. Activity shows the latest 100
matching events within a 64 KiB text budget; individual Details blocks are limited
to 8 KiB. Use CLI JSON or log files for more detail. When disk logging fails,
attempted events remain in this bounded buffer with `persisted: false` and a
visible memory-only marker. They can be copied in diagnostics but will be lost
when the app closes if they could not be written. Logging health and its hover
details show the storage error/path.

**Activity → Open logs** opens the local log folder in Explorer. **Copy diagnostics**
puts a bounded plain-text report on the Windows clipboard: app version, helper and
RIFT identity, cached route/pose/overlay/playback state, receipt paths, and recent
warnings/errors with tracebacks. These actions do not send game input or start a
new sampler. The logging caption shows availability; hover for the current log
path or storage error.

Logs are UTF-8 JSON lines in `artifacts/waypoint-logs/`, with timestamps,
severity, thread/context and CLI request IDs where available. Startup failures,
handled operation errors, unexpected Tk callbacks and uncaught worker exceptions
are captured. Repeated identical idle-reader failures are suppressed until the
reader recovers. Logs rotate at 1 MiB with two backups per session; cleanup keeps
the newest ten session groups and protects active processes' logs. Logging storage
failure is reported without preventing ordinary app use.

```powershell
.\rr2-waypoints.cmd diagnostics status
.\rr2-waypoints.cmd diagnostics show
.\rr2-waypoints.cmd diagnostics events --level warning --limit 50
.\rr2-waypoints.cmd diagnostics events --level error --search "route.load" --json
.\rr2-waypoints.cmd diagnostics copy
.\rr2-waypoints.cmd diagnostics open
.\rr2-waypoints.cmd app show --tab activity
```

`--json` retains the CLI envelope (`diagnostics show` returns `data.text`). When
no helper is running and no explicit session is requested, these commands use the
newest saved log without launching Waypoints or reading RIFT. The report clearly
labels this as saved context rather than live state. Explicit missing sessions
and ambiguous running helpers still require selection.

`diagnostics events` returns structured newest-first entries; the GUI presents
them chronologically. `warning` includes errors. Search is case-insensitive and
limited to 200 characters; `--limit` accepts 1–200. JSON retains the available
traceback, exception message, request/context and persistence status. Repeated
event queries do not create their own log entries. CLI filters do not change the
GUI view; current display settings/counts are exposed through `status.activity`
and `diagnostics status --json` under `data.activity`. Saved-log mode reads a
bounded tail of the newest log group and its rotations. Open logs provides access
to earlier sessions.

Reports are limited to 32 KiB; individual tracebacks to 16 KiB. Environment
variables and raw command lines are not collected; sensitive field names are
redacted. Reports contain local paths and game/session details, so review before
sharing. This is Python/application diagnostics, not a native crash-dump recorder;
forced termination or a native crash may leave only the preceding log entries.

## Replay

Replay separates explicit **Playback**, **Record a path**, and **Direct movement**.
Forward, Reverse and Resume each show a readiness reason from the current cached
pose: endpoint distance, measured height, unfinished-leg position, route budget,
zone candidate or missing/completed progress. Each reason now sits beside its
own button inside PLAYBACK. Start/End point numbers and names identify the
direction; Resume shows the saved direction and next original route number.
Ready actions are highlighted. Full names/reasons remain on hover.
This read-only preview shares execution's recording/measurement identity checks
and playback cursor admission rules, and never changes a checkpoint or starts a
reader. Execution still acquires fresh observations and repeats the normal gates.

Saved progress identifies its direction and completed count; the thin progress
bar follows that cursor. Resume stays disabled when the current position is too
far from the unfinished leg, even when a checkpoint exists. Fresh Play starts
within 0.30 units of Start (Forward) or End (Reverse), and replaces progress for
a new admitted run. Resume follows the saved direction and requires a position
within 0.50 units of the unfinished leg. A completed run keeps a full bar and
disabled Resume, including while Live pose is paused or fields are unapplied.
The final verified stopped sample retains its acquisition time, avoiding an
unnecessary Refresh before Resume when the other admission checks pass.

**Play and Resume always face before each leg**, matching the CLI. The separate
**Face before direct / auto-walk** checkbox affects direct movement and automatic
teaching. **Record** follows your manual walk; **Stop Recording** saves it.
**Auto-walk + record** explicitly drives the route and records the visited path.
STOP/F8 cancels automatic work and cancels an unfinished manual recording.

```powershell
.\rr2-waypoints.cmd playback status
.\rr2-waypoints.cmd playback status --json
.\rr2-waypoints.cmd app show --tab replay
.\rr2-waypoints.cmd playback start --direction forward --execute
.\rr2-waypoints.cmd playback start --direction reverse --execute
.\rr2-waypoints.cmd playback resume --execute
```

`status.playback` and `playback status` share `readiness.forward`, `reverse` and
`resume` objects with `ready`, `reason`, `direction`, zero-based ordered
`nextIndex`, `nextName` and `remainingDistance`. They also expose `pointCount`,
`completedCount`, `complete`, original one-based `nextPointNumber` (null when
complete), `startPointNumber`/`startName`, and `endpointDistance` when too far
from an endpoint. Reverse numbering matches the saved list, not traversal order.
Saved progress in CLI output comes from the validated checkpoint; active progress
is separate. These are previews, not movement authority. The console retains
`--execute` for movement. `--checkpoint` selects the helper's checkpoint path;
invalid/missing/completed Resume or a mismatched direction is refused before
starting work and leaves that selection unchanged. Omit Resume's `--direction`
to follow the saved direction. No new persistent setting is introduced.

On November 13 the updated native window was checked at 1120×850 and 980×740,
including completed forward/reverse progress. A 2.5-unit CLI out-and-back trial
passed Play Forward, Play Reverse, STOP and Resume in the saved reverse direction.
All 20 turn/walk pulses released; Resume was ready immediately after STOP without
another Refresh. The return ended 0.0455 units and 0.1726° from the starting pose.
Completed Resume was refused without input. Original route/settings, checkpoint
binding/content and progress archives were restored. This historical trial used
the then-current 20-unit trip limit and open-ground requirement.

## Edit waypoint

The fields describe the selected row, including immediately after adding,
loading or Undo. **New point** clears selection and fields for a new waypoint
without changing the route or its saved progress. Enter new X/Z, then choose
Add X / Z. Apply or Reset an existing edit before starting a new point.
**Enter** or **Update Selected** applies edits. **Reset fields**
restores the selected row without changing the route. Unapplied fields are marked
explicitly and preserved when another row is clicked; Apply or Reset before
switching rows, saving or starting another action. Up/Down, Remove and Update
follow selection and boundary conditions. The selected row is scrolled into view.

An unapplied edit adds a star to the Edit tab and a persistent clickable notice
beside Details, visible from every tab. Click it to return to Edit. Replay/direct
movement, recording, Add X/Z and preview hints update immediately when fields
change, so a hidden draft explains unavailable actions consistently. Add X/Z
cannot convert an unapplied edit into a new point.

The hint shows measured Y or estimated/unknown height. Renaming retains height
evidence. Changing X/Z removes that point's old measurement and recorded-route
provenance, with a visible warning and completion message; other admitted point
measurements remain. **Set selected to current** replaces a point with freshly
observed player XYZ while retaining its name and position in the route. It requires
valid measurement provenance and checks tagged zone context before replacement.
This reads the game and edits the route; it sends no game input. Undo restores the
previous coordinates and evidence, but does not reinstate an invalidated playback
checkpoint. Save the route explicitly to retain changes.

The same operations are available through the attached CLI:

```powershell
.\rr2-waypoints.cmd route update 7 --current
.\rr2-waypoints.cmd route update 7 --current --name "Measured corner"
.\rr2-waypoints.cmd route update 7 --x 7420.25 --z 2940.5
.\rr2-waypoints.cmd route undo
.\rr2-waypoints.cmd route select 7 --discard-draft
.\rr2-waypoints.cmd route select --clear
.\rr2-waypoints.cmd route select --clear --discard-draft
```

`--current` may include `--name` but cannot include manual `--x`/`--z`. Repeated
named `route add --current` calls pass labels with the capture request and leave
existing form fields alone until the point is admitted. An explicit target-add
name is also retained. `route select --clear` matches New point; it requires a
point number or `--clear`, never both. Route list and general `status.route`
report selected numbers and `editDraft`; `status.app.tab` reports the active
workspace (`replay`, `edit`, `scene`, `explore`, `library`, `activity`). Update responses report
`change` fields for renamed coordinates, replaced/discarded measurements and
discarded recording provenance. `--discard-draft` explicitly abandons unapplied
GUI fields; normal selection preserves them. Existing load/new/close `--discard`
also permits discarding a draft. No new persistent setting is introduced.

On November 13, live CLI checks replaced point 7 with measured XYZ, manually
changed X, checked measurement removal, reordered with receipt preservation, and
used Undo to restore each document. The original seven-point file, player pose,
movement basis and absent active checkpoint were preserved. Normal and compact
native-window screenshots were reviewed; no game input was sent.

## Scene & beacons

The World beacons card distinguishes the owned reader from its fresh presenter
feedback: stopped, restarting, waiting for a camera frame, hidden by foreground
rules, visible overlay, or unknown feedback. A running reader alone does not
prove visible markers. Visible overlay feedback does not establish individual
point visibility, terrain or occlusion. Hide stops the shared radar/pose reader
too; the card states this while running.

**Include selected target in markers** can now change while enabled. The helper
stops its owned reader, retains appearance/route/selected-guide/radar settings,
and starts a fresh reader for the new target option. STOP/Hide/close or an identity
change cancels a pending restart. Stop an active manual guide or trail before
changing this option, so their session progress is not interrupted. The selected
marker guide is available only with exactly one selected waypoint.

**Reset** restores size 100%, opacity 100% and labels on; it retains target,
selected-guide and enabled state. The same action is `beacons reset`.

Capture & explore shows the last image/3D availability and capture readiness.
**Open saved…** loads a saved scene JSON manifest's local asset references without
opening a viewer. Open view/Open 3D view are separate explicit actions. An entire
failed capture retains the previous successful assets. Saved image/3D capture
uses the existing strict measured-XYZ path: every route point needs measurement
provenance. A mixed measured/estimated route remains usable for live beacons,
but Save view explains its measured count and stays unavailable until a fully
measured route is loaded.

Capture readiness also explains an active action, missing connection or pending
Edit fields. The GUI button, Scene hint and CLI `view status` share that result;
`measurementReady`/`measurementReason` retain the separate height-evidence result
and measured/total counts. CLI output also shows the latest capture error and
whether a retained nearby-sample path still points to an available file.

```powershell
.\rr2-waypoints.cmd beacons status
.\rr2-waypoints.cmd beacons set --target on
.\rr2-waypoints.cmd beacons reset
.\rr2-waypoints.cmd view status
.\rr2-waypoints.cmd view load saved-scene.json
.\rr2-waypoints.cmd view save new-scene.json
.\rr2-waypoints.cmd view save new-scene.json --bring-forward --nearby-units
```

CLI capture defaults to focus-neutral WGC and no nearby-unit sampling; both
options are explicit per-capture opt-ins and are reflected in the GUI afterward.
Capture gets a 120-second CLI deadline; route playback and direct movement get
1,830 seconds (30 minutes plus completion grace), facing 150 seconds and ordinary
commands including STOP 10 seconds. `view status` reports options, capture readiness and actual
asset availability. `beacons status` adds `visibility` and `restartPending`.

November 13 live checks on AMD-DESKTOP/PID40452 verified target restarts retaining
radar/style, refusal during active manual guidance, and the actual magenta target
and guided estimated waypoint over RIFT. A temporary copy of the two measured
points produced image/3D assets with `inputSent=false` and `focusChanged=false`.
The original seven-point route, body pose, appearance, radar-off state and absent
checkpoint were restored. Local evidence is under `artifacts/scene-ui-*20261113*`;
normal/compact native UI captures were reviewed. No movement input was sent.

## Route library and zone context

**Library** keeps named route copies in `artifacts/waypoint-routes`. Search by
name, ID, saved zone/world context or entry error, and filter by matching,
mismatched or unknown zone context. Search is case-insensitive and shares the CLI's
filtering rules. The list sorts by readable name, shows result counts and explains
no matches; Clear filters restores the complete list. Search filters cached
metadata rather than reopening every file on every keystroke. Refresh library
rescans files; Refresh zone reads a new native zone candidate.

Select a row to inspect its ID, waypoint count, planar distance, modification time,
measured versus estimated heights and zone comparison in the adjacent details
pane. Hover those details for the full file path. Malformed entries stay visible
with their error but cannot be loaded. These summaries do not establish playback
readiness, terrain clearance or floor identity.

**Save copy** uses the labeled Copy name and always creates a new library ID. It
selects the saved entry while preserving the open route, source file and dirty
state. Empty/overlong names, empty routes and unapplied waypoint fields explain
why Save is unavailable. Existing IDs are replaced only through explicit CLI
`--id ID --overwrite`; IDs resolve case-insensitively. **Import file** keeps the
source's saved route name or filename, independently of Copy name; CLI `--name`
overrides the imported name. Import preserves the source and selects the new copy.

**Load selected**, double-click and Enter share the same readiness checks. Pending
fields must be applied/reset, active work must finish, and a selected entry must
be healthy. GUI loading asks what to do with unsaved current-route changes;
Cancel preserves them. CLI loading requires explicit `--discard` to abandon them.

The native zone value is currently a **zone candidate**, not a qualified world or
instance identifier. Legacy routes stay unknown until explicitly tagged. New
routes and recordings retain fresh candidate context when available. A tagged
route is freshly checked before route movement, playback and Resume; mismatch or
unavailable context refuses input. Known mismatches also withhold route markers
and passive guidance. Old route process IDs are provenance, not a requirement to
reuse the old process after a same-build restart. Names are user labels, not an
inferred mapping from native zone IDs.

Use the attached CLI for the same operations:

```powershell
.\rr2-waypoints.cmd zone refresh
.\rr2-waypoints.cmd route context
.\rr2-waypoints.cmd route tag-zone
.\rr2-waypoints.cmd library save "Courtyard loop" --id courtyard-loop
.\rr2-waypoints.cmd library list --zone matching
.\rr2-waypoints.cmd library list --search "Courtyard"
.\rr2-waypoints.cmd library select courtyard-loop
.\rr2-waypoints.cmd library show courtyard-loop
.\rr2-waypoints.cmd library load courtyard-loop
.\rr2-waypoints.cmd library import route.json --name "Old route"
```

`route tag-zone` changes the open document; explicitly save it or save a library
copy to retain the tag. `library save` requires `--overwrite` to replace an ID.
`library show ID --json` exposes the document, saved context, height evidence and
`row` metadata (path, modification time, counts and planar distance). `library
select ID` selects/details an entry without loading it and clears filters that
could hide the selected entry. Malformed entries can be selected for inspection.
`library list --json` reports total/shown counts and filters; its `view` and
`status.routeLibrary` expose GUI selection and Save/Load readiness. A CLI list
query does not change GUI search/filter controls. `app show --tab library` opens
the Library tab without sending game input.

Height labels distinguish measured Y from estimated display heights. Radar
arrows show above/below; `~` means approximate. A measured waypoint more than one
unit above/below the player warns of a possible other floor. Manual guidance
will not confirm that point solely from matching X/Z until measured vertical
separation is within one unit. Estimates never become measurements or a floor
identity; unknown heights retain the existing planar guidance behavior.

Overlay diagnostics are available through `beacons status --json` under
`data.display`. They report native visibility, frame age, clear/recovery reasons,
reader starts and timing from the same owned reader. An expired stream row is
discarded while the reader waits for a newer row; native-hidden Qt windows are
reshown only on a fresh, identity/foreground/geometry-valid frame. Transient
feedback uses atomic replacement without synchronous durable flushes; route and
progress files retain durable writes. The normal 350 ms frame-age limit remains.

On November 13, a 40-second foreground check and a separate 20-second turn check
accepted 1,687 updates with no recorded clears or sampled invisible windows,
including explicit/background zone reads. A later extended-session snapshot did
record one frame-age clear recovering in 46 ms, so intermittent freshness hides
remain possible. Local traces are under
`artifacts/zone-library-overlay-transient-20261113` and
`artifacts/zone-library-overlay-camera-final-20261113`.

## Explore while playing

**Explore** groups three read-only tools. They reuse the owned beacon reader;
starting one can enable that reader and Live pose, but never starts movement.
The compact radar requires the existing Qt overlay environment.

- **Show radar** displays a small player-relative radar over RIFT. It starts near
  the lower left to leave the current minimap/chat clear. **Unlock to move** lets
  you drag it; turn Unlock off for click-through play. Range and Opacity update
  live. Hide, stale samples, unrelated foreground apps and owned shutdown retain
  the existing display rules. The caption distinguishes requested display from
  observed visibility. **Recenter** restores the default corner without changing
  range or opacity. Settled unlocked drags and explicit CLI placement survive
  reopening; the radar always starts hidden and locked.
- **Start guide** guides a route you walk manually. Choose Forward/Reverse, or
  enable **From selected** to begin at the selected route row. **Arrive** sets the
  arrival radius in world units (0.05–10; 0.60 at startup), matching CLI `--radius`.
  The current point advances after distinct fresh samples confirm arrival within
  that radius;
  it never jumps to a later nearby point. Radar and beacon guidance identify the
  same active destination. Route edits stop the guide. Missing data pauses arrival
  confirmation. Guidance never writes the automated Play/Resume checkpoint.
  Readiness explains an empty route, missing selection, invalid radius, busy
  action or known zone mismatch before starting the reader. The active direction,
  next point and confirmed count are visible; Stop before starting another guide
  or changing its options. CLI starts update the same direction/radius controls.
- **Record trail** retains the positions you actually visit and draws a breadcrumb
  line on both radars. **Stop trail** retains it; **Clear** is available when
  stopped. Choose a recorded segment and **Save segment** to write a separate
  waypoint JSON file without replacing the current route. Load that file normally
  to inspect it. Gaps, teleports and owner changes split segments; long trails also
  split at the 1,000-unit recording limit. Exact stationary positions keep
  sparse real heartbeat samples so standing still does not quickly erase a walk.
  Segment selection stays on your chosen segment when a new segment arrives.
  Save is enabled only when the actual export rules accept that segment; the
  caption shows path length or the refusal reason and dropped-history count.
  Clear asks before discarding retained history. Closing also warns that the
  in-memory trail will be discarded; save useful segments before closing.

```powershell
.\rr2-waypoints.cmd radar reset-position
.\rr2-waypoints.cmd guide start --direction reverse --from 7 --radius 0.45
.\rr2-waypoints.cmd guide status
.\rr2-waypoints.cmd guide stop
.\rr2-waypoints.cmd trail list
.\rr2-waypoints.cmd trail save trail.json --segment 1
.\rr2-waypoints.cmd trail clear --discard
```

Guide radius is shared within the current window and returns to 0.60 on reopen.
`guide status` includes start `readiness` and `configuredRadius`; `trail list/status`
include per-segment `exportable`, `exportReason`, path length and output point
count. CLI `app close` requires its existing `--discard` flag if trail history
remains. Rejected radar settings leave the previous configuration intact, and a
settings write failure is an explicit error rather than a reported success.

When the browser or another unrelated app is foreground, fresh beacon pose may
be unavailable. CLI guide/trail starts wait up to four seconds, then refuse with
`pose-unavailable`; they do not remain queued to start later. Focus RIFT or
Waypoints and retry explicitly. Radar changes are saved immediately; if display
application cannot be observed within four seconds, CLI returns `configured`
with `displayPending: true`, rather than claiming visibility or timing out.

Trail history keeps up to 2,000 recent observations, with original XYZ and sample
times. Export preserves corners and measured heights through the existing route
format; stationary-only or excessively complex segments report a save refusal.
The radar is a reference diagram: it supplies no terrain, collision, occlusion or
walkable-route guarantee. A saved trail does not expand the playback budgets.
Detailed acquisition/file errors remain in Activity; compact captions stay short.

The November 12 dark-theme redesign passed focused withdrawn GUI/map checks.
Its offline layout gallery can be regenerated with
`python scripts/preview_waypoint_ui.py`; those SVG representations are not native
screenshots or proof of actual window clipping. Reopen the helper normally to
load new source; reopening never starts playback automatically.

In **Scene & beacons**, choose **Show markers** to display saved world locations
while RIFT or that Waypoints window is foreground. This keeps size and opacity
changes visible while you adjust the sliders. **Guide selected marker** gives the selected point a
gold reticle, short beacon and name/distance pill; **Include selected target**
adds a distinct magenta diamond when a fresh target projection is available.
NEXT is cyan and ordinary/completed points remain subdued. **Hide markers** stops
the owned feed. Markers are click-through and never start route playback.
Map clicks and typed X/Z points also work as beacons without measuring every
height. Unmeasured points borrow Y from the nearest measured route point. If none
are measured, they use the player's freshly read Y when the marker session starts;
that display height stays fixed for the session. The summary shows measured and
estimated counts, and guided estimated points say **est. height**. Estimates are
only for display: saved heights/receipts stay unchanged. They approximate a ground
level rather than finding terrain, so slopes or other floors can leave a beacon
above or below the ground. Once **Show markers** is enabled, add/edit/remove,
rename/reorder, Undo and Load automatically update the same overlay. Clear hides
route beacons while keeping the session ready; the next added point appears
automatically. **Guide selected marker** follows the current selection live.
Edits are coalesced briefly, so completed changes normally appear within a fraction
of a second without restarting the camera reader. Hide/STOP stays off until you
explicitly enable markers again; route edits never respawn a stopped helper.
The same panel has **Size** (50–200%), **Opacity** (20–100%), **Show labels**,
and **Reset**. These update an already enabled overlay without Hide/Show and
persist for the next launch. Size adjusts beacon shapes and beams while label
text stays readable; hiding labels keeps beacon shapes and off-screen arrows.
Preferences are stored in `artifacts/waypoint-marker-style.json`. A malformed or
temporarily unavailable preference file retains the last valid appearance.
There is no marker session timer: the feed stays enabled until you hide it,
close Waypoints or RIFT, or another existing owned-stop condition applies, such
as pressing STOP/F8. Switching to an unrelated app hides
the markers temporarily; returning to RIFT or the owning Waypoints window allows
fresh markers to appear again. During a marker session, **Live pose (beacons)**
updates the position/facing header and player-relative radar from the existing
beacon reader, up to five times per second. No second native sampler runs. The
header shows the original sample time in local time. Missing, stale, foreign or
withheld samples clear the display rather than showing an old pose as current;
the last real sample time remains available. Hiding markers resumes the normal
two-second idle reader after the owned beacon child exits. This shared feedback
is for display; movement still obtains its own fresh, guarded observations.
The display exception binds the exact Waypoints HWND, PID and process epoch;
movement still requires RIFT foreground. Identity/geometry/freshness failures still
withhold markers. See the [camera-motion verification](../validation/waypoint-overlay-camera-2026-11-12.md).

Double-click **`Waypoints.cmd`** in the repository root to open the window for
the single local physical RIFT client. If RIFT is absent or still loading, the
default window opens in a waiting state and retries unique selection while idle.
It validates the current host, process, movement basis and live pose before use;
it never starts movement on launch. `--check` and an explicit PID remain strict.
If several clients are running, use `Waypoints.cmd --physical-pid PID`.
The default single-client launcher reconnects while idle after the old game
process has truly exited and a new unique client has loaded the same player on
the same host and executable build. It freshly pins the new process and native
owners/facing. An explicit `--physical-pid` remains pinned to that process;
changed builds or players and ambiguous processes are refused. Reconnection
does not resume an interrupted trip or start movement.
The launcher defaults to **Face, then walk**. `--route PATH` opens a saved route.
For a read-only readiness check, run `python scripts/launch_physical_waypoints.py --check`.

Cold-start behavior passed a live AMD-DESKTOP case on November 12: the same app
opened with RIFT absent, waited through character selection, then bound the new
Atank process and restored readiness without movement. Its completed route stayed
loaded and the movement basis was unchanged.

For explicit CLI calls, obtain the current PID with the read-only readiness
check. An old PID remains deliberately pinned and is refused after it exits.
Use the default `Waypoints.cmd` launcher for automatic idle reconnection.

```powershell
$riftPid = (python scripts/launch_physical_waypoints.py --check | ConvertFrom-Json).pid
pythonw scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid
```

The window reads the current position and facing. **Save Current** adds a point;
clicking the local route preview adds a waypoint, and **Add X / Z** adds entered
coordinates. The preview faces forward, shows distance rings, selected points
and the route distance. While idle, **Start / End** show the observed planar distance to the first
and last points in the saved order. Forward playback starts within 0.30 units of
Start; reverse playback starts within 0.30 units of End. These hints do not replace
the backend's fresh position, height, identity and route-budget checks.
Initial Play buttons are disabled if the observed endpoint is too far away, its
recorded height differs by more than one unit, or the directed route exceeds 20
units. The backend repeats admission checks using a fresh stationary pose.

**+ / −** change preview radius from 2 through 1,500 units; **Fit** chooses a
radius for the loaded points around the observed player. Rings show half/full radius.
Farther points can remain outside the maximum 1,500-unit preview. Zoom only redraws
the display, preserving world coordinates and movement limits. Each click checks
a fresh pose; if the player moved or
turned, it refreshes the preview and requires another click. It shows waypoint
geometry only, without terrain or obstacle information.

Select a point and choose **Go Selected**,
or choose **Run Route** to visit the list in order. **Load** and **Save Route**
use a small JSON file containing `{"waypoints": [["name", x, z]]}`.
The filename/status line shows **Saved** or **Unsaved changes**. **Save Route**
writes directly to the currently loaded/saved file; **Save As** chooses another
file. **Ctrl+S / Ctrl+Shift+S** provide the same actions while idle. Reopening can
remember the source file when the restored route, recovery snapshot and current
local file still match exactly. A changed or missing source stays unbound, so Save
asks for a destination. Older snapshots without a filename also ask on first Save.
Cancelling or failing a Save As keeps the current file and edits.
GUI Save Route and completed recording publication write a synced sibling
temporary file before replacing the destination, reusing checkpoint persistence.
A failed write or replace leaves the previous saved route intact and reports the
error; closing during passive recording discards that unfinished recording.
Use `--route PATH` to open the window with a saved list; loading does not start movement.
Successful Load, Save Route and completed recordings also retain the full route in
`artifacts/waypoint-last-route.json`. Default startup opens the checkpoint's route
when available, otherwise this last saved route; an explicit `--route` takes
precedence. The snapshot retains heights and recording provenance, but creates no
playback progress and never starts movement or enables Resume by itself. Unsaved
edits are not cached. A snapshot-write warning leaves the original saved file and
previous snapshot intact. Reopening before first playback passed a live seven-point
case on AMD-DESKTOP with no checkpoint and no game input.
**Up / Down** reorder the selected point; **Clear** empties the list. A completed
run reports the number of visited waypoints and final distance explicitly.
To edit a waypoint, select its row, adjust **Name / X / Z**, then choose
**Update Selected**. It keeps the point's order and selection. Renaming preserves
recorded heights/provenance; changing coordinates converts the route to manually
edited points and discards recording metadata. An actual edit clears playback
progress and remains unsaved until **Save Route**. An unchanged update, including
coordinates that round to the same six-decimal values, preserves progress.
**Undo** restores up to 20 recent route edits, including removal, reordering,
coordinate edits and Clear. **Ctrl+Z** does the same while the waypoint list has
focus. Undo restores point order, selection and recording metadata, and marks the
route unsaved. It keeps the current filename and leaves saved files unchanged.
Playback progress stays cleared; Undo never revives an old cursor. Loading another
route or completing a recording clears edit history; saving keeps it. History is
held only while the window is open.
In the waypoint list, **F2** selects the point's name for editing,
**Alt+Up / Alt+Down** reorder it, and **Delete** removes selected points.
In Name/X/Z fields, **Ctrl+Enter** applies Update Selected. These shortcuts are
disabled during active work; normal text-field Delete/navigation stay unchanged.
**Add Target** saves the selected entity's freshly read ground position as a
fixed waypoint. It does not follow a moving entity or start a trip. An unavailable
or expired target position, or a target more than one unit above/below the player,
is refused. The point uses the same native candidate source as the target reader.

**Walk + Record** walks the loaded point list and records Atank's actual observed
path through the existing bounded controller. It honors **Face, then walk** and
uses the same distance, pulse, time, identity and foreground guards as Run Route.
On success it saves a `recorded-route-*.json`, loads the observed points, and puts
the saved path in the log. **STOP/F8** cancels the walk and prevents publication
of an unfinished recording, preserving the previous route and saved progress.
The live distance/sample counter applies during this commanded teaching walk.

The [GUI-taught route](../validation/gui-taught-route-2026-11-12.json) is a real
14.13-unit nearby loop captured by this button: 49 samples, seven retained points
and three corners. Its GUI reverse replay finished within 0.08405 units of the
recorded start. Review current position and open ground before reusing it:

```powershell
Waypoints.cmd --route docs/validation/gui-taught-route-2026-11-12.json
```

**Record** passively observes the player's movement without sending input.
While recording, the summary shows accumulated observed distance against the
1,000-unit cap and the accepted sample count (up to 30,000). Stop before the cap; the readout
updates after each capture burst and does not enlarge the recording limits.
After moving along a clear path, choose **Stop Recording** to finish,
save a new `artifacts/recorded-route-*.json`, and load its points into the window.
**STOP** cancels recording without saving; capture or identity errors also leave
the recording incomplete.
If RIFT exits during capture, that recording is discarded. Idle reconnection
does not restart recording or join observations from different process epochs.
Passive GUI recording passed one live two-corner
open-ground case on AMD-DESKTOP: 732 samples became four actual points across
10.2944 units. The reusable
[passive route](../validation/passive-recorded-route-2026-11-12.json) retains its
original provenance; review fresh position and terrain before replaying it.
Paced native capture can reacquire a changing pose payload up to three attempts
within 100 ms, retaining the same owner/epoch checks and reporting
`captureAttempts`. In that live capture, two rows needed a second attempt and
730 completed on the first. Interrupted work and the reusable taught route are preserved
in [the recorded-route handoff](../handoff-2026-11-12-recorded-routes.md).

**Play Forward** starts near the recorded first endpoint; **Play Reverse** starts
near its last endpoint. Playback checkpoints each confirmed waypoint to
`artifacts/waypoint-current-progress.json`. After stopping or restarting the app,
the window can restore the checkpoint's route; choose **Resume** explicitly to
continue the unfinished leg. A fresh stationary pose must be near that leg, and
the host, build and player must match. Reconnection never starts or resumes a trip.
Loading or explicitly opening the same waypoint names/coordinates/heights restores
matching progress. Switching to another saved route shelves the current checkpoint
under `artifacts/waypoint-progress/`; returning restores its original direction,
cursor and starting position for the same verified host, build and player. Loading
a route never starts playback. A deliberate route edit clears that route's saved
cursor, including its archived copy; Undo does not revive it. An unavailable player
identity keeps Resume unavailable until a fresh binding can restore matching progress.
Backend identity/checkpoint
validation still runs before any input. A live saved-file restart/Load/Resume case
preserved its 2/4 cursor and finished within 0.18620 units with four released W
pulses. Existing route and input limits
still apply, and routes have no obstacle avoidance.

Live saved-route switching passed on AMD-DESKTOP/PID51524 after the user-handled
RIFT restart. A registered F8 press sent by the desktop tool stopped forward
playback at 2/7. Normal helper close/reopen with an alternate four-point `--route`
archived the genuine checkpoint; choosing the original file through Recent routes
restored its exact bytes, direction, cursor and starting position. Neither route
load started movement. Explicit Resume confirmed only Recorded 3-7 and finished
0.06794182 units from the endpoint: 26 released pulses, 3,364 ms total requested
hold, maximum 150 ms requested per pulse. Separate settled samples showed zero
XYZ/yaw drift; inspection found no held desktop inputs. The movement basis stayed
unchanged. An earlier desktop-tool STOP click focused the helper and triggered
the foreground guard first; that receipt is a halt, not a verified STOP.
Evidence: `artifacts/route-switch-live-51524/validation.json`, its exact stopped/
completed checkpoints and settled/inspection receipts, and
`artifacts/waypoint-run-dc167877457d4311abe10013d8aa160c.json`.

Failed movement actions also retain two post-halt candidate pose observations when
available, through the existing `stopVerification` receipt field. A failure keeps
its original reason and halted status even if those observations are stationary;
an unavailable read remains explicit. These observations are separate from native
per-pulse key-release evidence. Passive/idle read failures do not add this check.

On AMD-DESKTOP, a controlled taught route retained four points from 30 observed
samples across 9.998 units with 19 released pulses. Reverse playback completed
with 25 pulses and ended 0.09917 units from its endpoint; an earlier forward CLI
playback ended 0.10648 units from its endpoint
(`artifacts/waypoint-run-b4c277aafd324c988564fcf60556790e.json`).

A later GUI reverse playback was stopped by clicking **STOP** and settled with
three of four waypoints confirmed. Closing and reopening the app without
`--route` restored that reverse checkpoint. RIFT then fully exited (PID 31696)
and was normally relaunched through Glyph into Atank (PID 3820, start ticks
639300839889408581). The same app (PID 75780) reconnected without changing the
movement basis. An explicit **Resume** completed only the final leg, ending
0.0679574 units from its endpoint after eight released pulses and 963 ms of
requested hold. The interrupted and resumed run receipts are
`artifacts/waypoint-run-dc32b7e0c93747ccbe11baca1e305f79.json` and
`artifacts/waypoint-run-8d88bf44e6034217ba570b18b6dfd731.json`. This covers
that same-build/player restart case. Later direct GUI reverse/forward replays of
the passive-recorded route ended 0.15947/0.28199 units from their endpoints, with
26/17 released pulses. The forward case used fixed-facing S/E/W travel, exercising
the slow-direction segmentation. These are specific open-ground cases, not a
qualification of arbitrary routes or terrain.

**Face Selected** turns toward a waypoint without walking. **Face, then walk**
aligns to each waypoint and uses W for travel. Unchecked, the existing W/S/Q/E
controller approaches the point with the current facing. Facing uses the retained
settled A/D measurements as numerical seeds and checks the observed response
after every release. Alignment allows eight 20–150-ms presses and 20 seconds,
stopping within 4 degrees. It refuses unexpected XYZ movement during a turn.
Turns share the trip's hold/pulse budget; facing mode uses segments up to 3.5
units long. Fixed-facing W/S/Q/E routes use shorter intermediate legs when the
slowest calibrated direction needs them, targeting 600 ms of requested travel
per segment and capping segment distance at four units. The existing translation
controller retains its six-pulse, 900-ms and 12-second limits.

For a requested facing without walking:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --face-bearing -4.7 --execute
```

Add `--face-waypoints` to a CLI `--go` or a GUI launch to enable forward walking.

**Live pose (2 s)** refreshes position, facing and the preview while idle. It is
read-only, pauses during GUI actions and preserves entered waypoint coordinates.
With markers enabled, the same checkbox uses their reader as **Live pose (beacons)**.
The current pose has a separate timestamped readout. A control request waits for
an in-flight observation; closing waits for it as well. Before starting a route
or facing action, two fresh observations must show settled XYZ and bearing.

Repeated ownership checks use the native helper's read-only `move-key --inspect`
mode, which verifies the pinned process, executable hash and window without
focusing RIFT or sending input. On AMD-DESKTOP the measured identity-check time
fell from 411 ms through PowerShell to 230–234 ms through the native helper.

Live updates were checked against an independently issued facing command: the
preview updated to the new -16.51-degree bearing while an edited X coordinate
remained unchanged.

Each route is limited to 1,000 world units of planned travel, 500 waypoints,
8,192 pulses, 600 seconds total requested key hold and 30 minutes overall. Actual Windows insertion-time
bounds remain in the native pulse receipts. Long waypoints are split into targets
at most 4 units apart. Each target retains the existing controller's six-pulse,
900-ms hold, 12-second and 6-unit radius limits. Input ownership and the trip
budget span every target and waypoint; only the first actual pulse can focus
RIFT. Arrival requires two settled observations within 0.30 units.
This is a supervised open-ground prototype: it does not route around obstacles.
The measured W/S/Q/E speeds are rotated using the current entity body facing;
the native position/facing fields retain their candidate labels. On the same
host, executable build and player, the measured
speed/turn model can be reused as a seed across process epochs without manually
rebuilding the basis. The original basis and measurement provenance retain
their original epoch; they are never retagged as new measurements. The live
adapter always pins the current process afresh and reads its native owners and
facing. Every pulse using a reused seed must pass signed direction, speed and
drift consistency checks before another pulse is allowed. A different basis can
still be supplied via `--basis PATH`. Same-build full-game restart recovery was
exercised on AMD-DESKTOP as described below.

Live restart acceptance, November 12: physical RIFT fully exited and relaunched
as PID18092 → PID79012 → PID31696, on the same executable build and Atank player
identity. After the reader's signed-zero decoding fix was loaded, the same
waypoint app (PID69060) stayed open across the latter full restart, reconnected
automatically and retained its route and entered coordinates. The original
basis bytes were unchanged (SHA256
`9A556D85DE26258D94E5A438BBC37D5938CCE762C67BC9B2E693602FDAB39251`).
No separate movement calibration or basis rewrite was performed.

The retained three-point triangle then completed in forward-facing mode,
finishing **0.08265 units** from its final waypoint. All 27 pulses (14 W, 9 A,
4 D; 3,781 ms requested hold) passed the reused-seed checks and native release
checks, with no target loss. Five subsequent D turns restored the starting
bearing within **1.248°**, with unchanged XYZ. The CLI facing receipt retains
each turn's timing/model comparison and before/after native source paths:
`artifacts/waypoint-run-04b0b0e8cab74168ad7dfae2f0c8e86b.json`.
Before/middle/after binding and settled route results are in
`artifacts/waypoint-restart-8f221c26b1994205bea0375d3323b889/`.

The first restart exposed native negative-zero matrix entries serialized as JSON
integer zero. The decoder now accepts that zero-sign equivalence and still
rejects other bit mismatches. Native `move-key --expect-hwnd` also pins the
current window before focus/input; passing the old window was refused without
input. Focused checks passed: 98 Python waypoint/reader tests and 75 native
move-key tests. These observations cover this same-build/player restart case,
not arbitrary patches, character changes or obstacle routing.

**STOP / F8** latches cancellation. F8 is registered only during a trip and does
not change foreground. The waypoint window uses `WS_EX_NOACTIVATE` during the
trip so an ordinary STOP click also preserves foreground; editing is disabled
until cleanup. The current pulse finishes its bounded release; another pulse
is never sent. Closing waits for cleanup, and STOP checks for actual stationary
native XYZ and body bearing. Only the first actual pulse can request RIFT foreground.
An already dispatched child may still be performing identity/focus checks when
STOP arrives; it finishes that one bounded pulse and release. GUI run receipts
retain the existing two post-STOP observations in `stopVerification`, including
source paths, candidate poses, XYZ/yaw drift and pass/movement-detected/unavailable
status. This is separate from native key-release evidence in the pulse receipts.
Each GUI input operation has its own `waypoint-input-*.jsonl` path; run receipts
include `inputReceiptPresent`. A refusal before input leaves that path absent.
After playback becomes idle, the preview and Resume button reconcile with the
saved checkpoint, including when an entry request is refused.

Foreground loss aborts the run. The native helper sends unconditional global
key-up, then may additionally post one release-only `WM_KEYUP` to the exact
focused RIFT HWND observed before this pulse's successful key-down. The pinned
process must remain alive, with matching window owner/thread/root ancestry.
Observed blur is latched through the action result. The fallback never sends
key-down or restores foreground. Windows queue acceptance and observed game
motion remain separate evidence. All GUI pulse receipts, including failures,
are retained as `artifacts/waypoint-input-*.jsonl`.

For explicit recovery of a key owned by an interrupted action, `move-key`
accepts `--release-only` with one key and the normal exact identity/foreground
guards. It cannot also request a hold or movement measurement. Each normal pulse
retains exclusive native input ownership, held-input refusal and bounded release.

For the same backend without the window:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --go 7422.455078125 2948.04931640625 --execute
```

Headless `--go`, `--run-route` and `--play-route` use continuous held-forward
travel by default. Add `--movement-engine pulse` to choose the legacy bounded
pulse runner for that command; `--movement-engine continuous` is accepted when
an explicit setting is useful in a script.

CLI outcomes retain run receipts under `artifacts/waypoint-run-*.json`. Failed or
stopped runs retain the original reason, completed-leg events, checkpoint and
native pulse-file paths. STOP also retains the same two-pose `stopVerification`
as the window; missing observations remain explicitly unavailable. If the receipt
cannot be written, the final CLI JSON reports `receiptError` alongside the action
failure. Successful receipt contents retain their existing format.

Run a saved multi-point route through the same backend:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --run-route my-route.json --face-waypoints --execute
```

To save observations from an explicitly commanded `--go` or `--run-route`, add
`--record-to` with a new output path. This teaching operation deliberately uses
the bounded pulse runner, even though continuous is the normal headless default;
`--movement-engine continuous` does not override that recording exception. It
is not the passive window recording control. Replay and resume use
`--play-route`:

```powershell
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --run-route my-route.json --record-to taught-route.json --face-waypoints --execute
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --play-route taught-route.json --reverse --progress taught-progress.json --face-waypoints --execute
# Use --resume only if that playback was interrupted and left the checkpoint unfinished.
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid $riftPid --play-route taught-route.json --reverse --progress taught-progress.json --resume --face-waypoints --execute
```

Omit `--reverse` for forward playback. Resume must use the saved direction and
checkpoint. Without `--progress`, the checkpoint uses the route path with a
`.progress.json` suffix. `--execute` is required for each commanded trip.
To resume a checkpoint created by the window, use the same loaded route and
`--progress artifacts/waypoint-current-progress.json`, with its saved direction.
Leave the window idle while CLI input runs. Afterward, **Refresh** or an idle live
pose update reloads matching saved progress without replacing the loaded route.

This requires explicit `--execute` and preserves every leg in one receipt. The
same ownership, progress, release and whole-trip limits apply. **F8** cancels CLI
execution without changing game focus; **Ctrl+C** also cancels. CLI input refuses
to start if its temporary F8 listener is unavailable. Omit `--face-waypoints` to
use the W/S/Q/E movement basis while keeping the current facing.

CLI Ctrl+C uses a temporary SIGINT handler that latches STOP instead of raising
inside `subprocess.run`; this lets the native child's key-up finish. An unexpected
F8-listener exit also latches STOP. Startup failure requests listener shutdown,
and cleanup restores the GUI's original window style even if shutdown reports
an error. Native listener checks covered registration conflict, owned hotkey
messages, unexpected exit, startup-timeout cleanup and subsequent re-registration.
A controlled live trial raised SIGINT during one native W subprocess: it finished
and released, no second pulse was dispatched, and separate native reads found the
player settled. This was a programmatic SIGINT test, not a physical Ctrl+C press.
Receipt: `artifacts/waypoint-cli-sigint-trial.json`.

A live two-point CLI route went one unit forward and returned home with one W
and two S presses (450 ms requested hold total). Outbound error was 0.0102 units;
return error was 0.00414 units. Bearing stayed unchanged and all three native
releases succeeded. The receipt retains both named legs:
`artifacts/waypoint-run-dba8ed0a046c4036a33437a61912766d.json`.

Existing solutions were checked before adding this adapter. [TomTom Rift](https://www.curseforge.com/rift/addons/tomtom-rift)
already provides waypoint lists and guidance, but its last release was in 2013
and it does not know terrain obstacles. [DotRecast](https://github.com/ikpil/DotRecast)
provides reusable .NET navmesh generation/pathfinding and is the candidate for
terrain routing if suitable RIFT geometry becomes available. The prototype
reuses RR2's existing `WaypointController`, native reader, physical reservation
and `move-key` helper; no third-party source was copied.

Live use on AMD-DESKTOP, 2026-11-12: a two-pulse 2-unit outbound leg stopped
0.111 units from its waypoint. **Go Selected** returned within 0.097 units of
its waypoint. A subsequent three-point **Run Route** finished 0.00352 units
from the original position. A latched STOP after one released 150-ms pulse
prevented the next pulse. These are historical open-ground observations from
their recorded process epoch,
not restart or obstacle-routing qualification.

The longer-trip extension crossed an 8-unit open-road waypoint in two segments
and eight released 150-ms pulses, finishing 0.213 units from the target.

A GUI focus-loss STOP exposed a real release failure: Atank kept moving into
the barrier; Joey confirmed no manual movement in that incident. The interrupted
receipt was not retained, so the precise missed-release sequence is unknown.
The changes above address the demonstrated failure rather than treating Windows
`SendInput` acceptance alone as proof the game stopped.

After the fix, F8 stopped a moving trip after one pulse, and a clickable STOP
also left the character stationary. A targeted open-road blur trial interrupted
a 750-ms E hold at about 178 ms: native `targetLost=true`, Windows key-up accepted,
and the exact owned-window release message queued. Two native samples while
blurred showed zero displacement. Returning focus to RIFT without pressing a
key, then sampling again, also showed zero displacement. Receipt:
`artifacts/blur-release-008ba70a0329416fbceab819cd1607e7.json`.

The local preview was exercised by saving the current point, clicking a point
2.09 units to the right, and using **Go Selected**. Atank stopped 0.216 units
from that clicked point and the preview recentered from the new observation.
Returning to the saved start finished 0.023 units from it. The GUI's Save Route
dialog wrote both points to `artifacts/waypoint-map-demo-4c6a750f.json` for reuse.

Use the native helper for physical game focus and the WGC observer for game
screenshots. Generic Computer Use activation restored the maximized game into
its smaller normal window during a focus test, leaving fresh WGC frames
unavailable. Reusing the existing BlackBox recovery script on the verified
AMD-DESKTOP display (`DISPLAY5`), with a 1936×1048 normal window, restored fresh
1922×1041 WGC frames without restarting the game or sending movement input.
Keep Computer Use interactions on the waypoint window; avoid activating,
dragging or restoring the physical RIFT window through that API.

Facing live use on the same process epoch: **Face Selected** aligned to the
sideways waypoint within 0.98 degrees without XYZ movement. Forward mode reached
it with two W presses, 0.088 units away. A combined turn-around-and-W sequence
finished 0.122 units from its waypoint. An initial 12-second facing timeout
expired after a successful 0.28-degree alignment, before any W; the separate
facing phase now allows 20 seconds for process checks and settling while retaining
the eight-pulse, 150-ms per-press and shared trip input budgets. F8 interrupted
another facing phase before W; subsequent XYZ and bearing drift were both zero.
Resuming finished 0.037 units from the saved start. The separate facing command
restored the earlier bearing within 2.63 degrees without changing XYZ.

A longer three-point triangle covered 13.66 planned units using **Run Route**
with forward-facing travel. It completed in approximately one minute with
27 pulses (14 W, 9 A, 4 D), 3,700 ms total requested hold, all native releases
successful and no target loss. Atank returned 0.150 units from the saved start.
Separate settled observations confirmed the endpoint. Five subsequent D turns
restored the pre-route bearing within 0.361 degrees without XYZ movement.
Route input receipt: `artifacts/waypoint-input-7aaf3780a54e4a3da35eb9030dcf56d3.jsonl`;
facing receipt: `artifacts/waypoint-run-314b50d1257b4cce97ec8c9c98c5ad4b.json`.

**Add Target → Face Selected** was exercised against the selected practice dummy,
6.234 units away. The point was added without input; two subsequent A turns
faced it within **0.236 degrees**, with unchanged XYZ. A fresh WGC/native bracket
put the selected dummy at frame X962.105 versus player X961.000 in a 1922-pixel
frame, matching its visible placement directly ahead. Capture:
`artifacts/observe-wgc-fe6fe17cdf544e1488bf54ccfbde4935/image.png` and `.png.json`.
Restoring the prior bearing used two D turns, finishing within 1.434 degrees,
again with unchanged XYZ. No travel to or attack on the target was attempted.
