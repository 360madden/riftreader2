# Joey D's Waypoints

The desktop helper and console frontend share **Joey D's Waypoints v1.1.0**
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

## Replay

Replay separates explicit **Playback**, **Record a path**, and **Direct movement**.
Forward, Reverse and Resume each show a readiness reason from the current cached
pose: endpoint distance, measured height, unfinished-leg position, route budget,
zone candidate or missing/completed progress. This read-only preview reuses the
playback cursor's admission rules and never changes a checkpoint or starts a
reader. Execution still acquires fresh observations and repeats the normal gates.

Saved progress identifies its direction and completed count; the thin progress
bar follows that cursor. Resume stays disabled when the current position is too
far from the unfinished leg, even when a checkpoint exists. Fresh Play starts
within 0.30 units of Start (Forward) or End (Reverse).

**Play and Resume always face before each leg**, matching the CLI. The separate
**Face before direct / auto-walk** checkbox affects direct movement and automatic
teaching. **Record** follows your manual walk; **Stop Recording** saves it.
**Auto-walk + record** explicitly drives the route and records the visited path.
STOP/F8 cancels automatic work and cancels an unfinished manual recording.

```powershell
.\rr2-waypoints.cmd playback status
.\rr2-waypoints.cmd playback status --json
.\rr2-waypoints.cmd app show --tab replay
```

`status.playback` and `playback status` share `readiness.forward`, `reverse` and
`resume` objects with `ready`, `reason`, `direction`, zero-based ordered
`nextIndex`, `nextName` and `remainingDistance`. These are previews, not movement
authority. The console retains `--execute` for movement; no new setting is needed.

On November 13 the updated native window was visually checked at compact and
normal sizes. CLI playback of two colocated measured points completed with zero
movement/turn pulses; completed Resume was correctly unavailable. The original
seven-point route and its absent active checkpoint were restored. This checks
the updated admission/display path; it is not a new moving-route/STOP trial.

## Edit waypoint

The fields always describe the selected row, including immediately after adding,
loading or Undo. **Enter** or **Update Selected** applies them. **Reset fields**
restores the selected row without changing the route. Unapplied fields are marked
explicitly and preserved when another row is clicked; Apply or Reset before
switching rows, saving or starting another action. Up/Down, Remove and Update
follow selection and boundary conditions. The selected row is scrolled into view.

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
```

`--current` may include `--name` but cannot include manual `--x`/`--z`. Route list
reports selected point numbers and `editDraft` state. Update responses report
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
Capture gets a 120-second CLI deadline; movement remains 150 seconds and ordinary
commands 10 seconds. `view status` reports options, capture readiness and actual
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
name and filter by matching, mismatched or unknown zone context. Save copy never
replaces the source route by default; Load selected retains the usual unsaved-edit
refusal. Import copies an existing JSON file without changing its source.

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
.\rr2-waypoints.cmd library load courtyard-loop
.\rr2-waypoints.cmd library import route.json --name "Old route"
```

`route tag-zone` changes the open document; explicitly save it or save a library
copy to retain the tag. `library save` requires `--overwrite` to replace an ID.
`library show ID --json` exposes saved context and height evidence. `app show
--tab library` opens the Library tab without sending game input.

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
  the existing display rules.
- **Start guide** guides a route you walk manually. Choose Forward/Reverse, or
  enable **Start at selected** to begin at the selected route row. The current
  point advances after distinct fresh samples confirm arrival within 0.6 units;
  it never jumps to a later nearby point. Radar and beacon guidance identify the
  same active destination. Route edits stop the guide. Missing data pauses arrival
  confirmation. Guidance never writes the automated Play/Resume checkpoint.
- **Record trail** retains the positions you actually visit and draws a breadcrumb
  line on both radars. **Stop trail** retains it; **Clear** is available when
  stopped. Choose a recorded segment and **Save segment** to write a separate
  waypoint JSON file without replacing the current route. Load that file normally
  to inspect it. Gaps, teleports and owner changes split segments; long trails also
  split at the existing 20-unit recording limit. Exact stationary positions keep
  sparse real heartbeat samples so standing still does not quickly erase a walk.

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

**+ / −** change preview radius through 2, 5, 10 and 20 units; **Fit** chooses a
radius for the loaded points around the observed player. Rings show half/full radius.
Farther points can remain outside the maximum 20-unit preview. Zoom only redraws
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
20-unit cap and the accepted sample count. Stop before the cap; the readout
updates after each capture burst and does not enlarge the recording limits.
After moving along a short open-ground path, choose **Stop Recording** to finish,
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

Each route is limited to 20 world units of planned travel, 64 pulses, 9 seconds
total requested key hold and 120 seconds overall. Actual Windows insertion-time
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
`--record-to` with a new output path. This teaches from that bounded run; it is
not the passive window recording control. Replay and resume use `--play-route`:

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
