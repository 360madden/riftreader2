# Physical world-to-screen markers

**Save Current → Save Route** preserves observed XYZ, source, actor/build identity
and observation time. Independently measured waypoints can use Show markers,
Save view and the 3D viewer without recording a walk. Every point needs measured
height and matching host/build/player provenance; the summary shows **3D: measured
heights N / M**. Typed coordinates and preview clicks retain unknown height.
Coordinate edits invalidate that point's measurement; Undo restores it. Renaming
and reordering preserve each point's observed position. An untouched recording
retains its original metadata; appending/reordering preserves individual known
observations with their original sources and intervals, without claiming a newly
continuous path. Known measured points from another host/build/player are also
refused before playback input. This adds no terrain/world-instance authority.

**Add Target** also preserves the selected target's actual Y and exact uint64
target key as a static measured point, with the observing player identity kept
separately. It reuses existing target age/floor checks. A target that later moves
leaves this saved location unchanged. Missing target-key/provenance information
keeps the existing 2D point and explains its unknown height. Thirty focused tests
passed, including keys above JavaScript's exact integer range. After the user's
restart, the actual Add Target -> Save view workflow passed on AMD-DESKTOP/PID51524
at 16:35 EST. The saved eighth point (`targetKey=9223372045797034558`) projects to
frame pixel `(962,321)`, visibly at the selected friendly guard's foot circle.
All eight measured points rendered; the RRD passed upstream verification. Capture
was focus-neutral WGC with a stable native bracket. Atank's XYZ raw bits/body
bearing and movement basis were unchanged. Reloading the original seven-point
route restored the byte-identical cache; no movement or replacement checkpoint
was created. Evidence:
`artifacts/waypoint-view-a07ef160cdd34d5f9465b13e372c44fb/validation.json`,
with `projection/waypoints.png`, `route.json` and `view.rrd` in that bundle.
This verifies a static saved-point projection, without live-follow, passive
freshness, world-instance, terrain or occlusion qualification.

Live proof on AMD-DESKTOP/PID17212: actual Save Current appended Point 8 with
Y `863.5865478515625`; Save view rendered all eight and its RRD passed verification.
The live Qt beacon at Atank's feet is visible in
`artifacts/measured-waypoint-trial-17212-69dcd609/sampled-current-markers.png`.
The first short desktop sample caught a hidden interval; the longer sample
confirmed pixels. Hide ended the child normally. No movement occurred, and the
original cache and genuine checkpoint were restored after the edit trial. See
that directory's `validation.json` and saved-view bundle
`artifacts/waypoint-view-535de4776556469ab5902782e54a5b1f/`.

After **Save view**, **Open 3D view** opens the optional Rerun recording with the
saved XYZ route and actor bearing beside its screenshot/projections. It starts
only on that click, binds its service to loopback and uses a child-only analytics
opt-out. Close the viewer normally before opening another recording from this
button. A failed capture preserves the previous successful view; a new capture
without an RRD disables its 3D button rather than opening an older recording.
The ordinary **Open view** still opens the annotated PNG. **Recent routes** /
**Load recent** selects up to eight saved local paths through the existing load
checks, without starting playback. Its history shares the existing last-route
cache, and missing/broken history does not prevent route recovery. Live proof:
`artifacts/route-controls-17212-validation.json`.

The 3D pane also shows the retained native optical eye and screen-edge view rays.
These invert the same matrix X/Y/W rows used by projection, using NumPy from the
existing optional visualization environment. Their chosen clip-W display extent
20 is visualization geometry, not measured scene depth or the game's near/far
planes. Each shape retains the native sample timestamp and source/hash; invalid
optional geometry clears the previous camera shape instead of hiding the route.
Use exporter `--no-camera-rays` for a route-only 3D view. Root reviewed actual
Rerun output under `artifacts/rerun-camera-rays-17212-labelled.{rrd,png}`.

The existing native optical camera and combined projection matrix can project
arbitrary world XYZ into normalized client coordinates. Client/frame geometry then
maps those coordinates into a matching RIFT screenshot. This is separate from the
flat, player-facing map in the waypoint window.

**Preferred live presenter: Qt/PySide6-Essentials.** The waypoint window chooses
the installed `.local/overlay-venv` and its Qt presenter automatically. Local setup
and the GitHub tool comparison are in
[third-party workflow tools](../reference/third-party-workflow-tools-2026-11-12.md).
The existing native presenter remains an explicit fallback. Both reuse the same
recorded XYZ, native camera projector, identity/freshness checks and stop lifecycle.

The waypoint window also has **Save view** and **Open view**. Save view snapshots
the recorded route or independently measured points and defaults to focus-neutral WGC capture. Enable
**Bring RIFT forward for capture** to explicitly choose the DXcam/native-bracket
desktop path; that mode focuses the pinned RIFT window without keys. A successful
`artifacts/waypoint-view-*` bundle contains route, original PNG, copied native
before/after reports with hashes, projection PNG/JSON and `view.json`. If the
optional visualization environment is available, it also saves `view.rrd` without
starting a viewer. Open view opens only the last successfully saved projection.
Failed capture or unstable camera blocks the projection and retains diagnostics.
The desktop event has no exact capture UTC; Rerun explicitly labels its timeline
placement as the native-after start upper bound. This remains separate from WGC.
The explicit desktop Save view/Open view buttons passed on PID17212 after normal relaunch
restored game rendering: seven markers, exact retained native copies, a 2.050 s
capture and 0.790 s native bracket. The resulting `view.rrd` passed upstream verify,
and Open view displayed the correct image. Evidence:
`artifacts/waypoint-view-47cf972e13854170a84dc5852db072e5/`.
The later default WGC Save view button also passed while the waypoint window
remained foreground: exact HWND preserved, all seven markers rendered, a stable
native bracket, and optional Rerun verified. Capture/bracket elapsed 2.906 s;
basis and checkpoint hashes were unchanged. No automatic backend fallback occurs.
The focus option is captured on the UI thread and disabled during acquisition.
Twenty affected GUI/backend/playback coordination checks passed. Evidence:
`artifacts/waypoint-view-9b60d7950aa949f5beaa52ce597a9334/`,
`artifacts/wgc-save-view-17212-validation.json`.
Saved projection labels reuse the live overlay's compact numbers, nonoverlapping
lanes and leader lines; marker coordinates are unchanged. A retained rerender in
`artifacts/waypoint-static-label-check-47cf/` separates the clustered 1/7/Player
labels; 26 affected renderer/backend checks passed.
The earlier black/no-advancing-frame condition and optional HWND pilot are
described in the tools note.

For a selected-target beacon, enable **Include selected target in markers** before
choosing Show markers. The option is disabled while that child is open; Hide
markers allows changing it. A selected unit with fresh, stable, on-screen native
position data within 35 horizontal units gets a magenta diamond, decorative
1.5-unit beam and distance label. Selection clearing removes the target marker;
route numbering, saved progress and movement remain separate. Names, world/zone
identity, passive position freshness, occlusion and target/model height are not
qualified. The displayed beam height is a display choice.

The CLI equivalent is `--target-beacon`. It adds `--include-target true` to each
existing finite native stream burst. Default capture remains unchanged; the
optional target lookup follows the selected key's single bounded bucket rather
than enumerating nearby units. Each row retains its session/lease and camera
bracket checks, then releases ownership before output. Expired rows are withheld.
The presenter also rechecks freshness and window geometry after painting, before
showing. Optional target corruption cannot repair a malformed base report or
bypass the non-stream camera bracket.

On AMD-DESKTOP/PID17212, root selected the nearby friendly guard without combat:
key `9223372045797034555`, measured horizontal distance 7.4406. The first 45-second
Qt pilot presented 214 frames and the actual composite showed the target beacon
at the guard beside the route markers. Root then used the real checkbox and
Show/Hide buttons: the 140.76-second child presented 606 frames, selection/clearing
was observed, and retained cleared-state pixels show the green route without the
target beacon. Hide ended with `stop-requested`; both launcher/worker PIDs were
observed absent. Player-position bits, body bearing, basis and completed checkpoint
were unchanged, and no held inputs remained. Focused checks: 28 native facing/
stream and 62 feed/presenter/GUI lifecycle tests. Evidence:
`artifacts/target-beacon-stream-first-17212.jsonl`,
`artifacts/target-beacon-live-composite-17212/first.png`,
`artifacts/target-beacon-gui-cleared-sustained-17212/last.png`,
`artifacts/waypoint-markers-summary-4372ab1b47884465b8fd8f4f68ee028f.json`,
`artifacts/target-beacon-gui-final-17212-validation.json`.

When the validated saved NEXT waypoint leaves the view, the live overlay now
shows a cyan edge chevron and its **direct horizontal native-unit distance**.
The cue uses the real camera viewport, including offset viewports, and retains
the original waypoint number in reverse. It does not select a new waypoint or
write progress. If the waypoint is behind the camera, text replaces the arrow;
near-zero clip W says outside camera view. Finished/missing/invalid progress
produces no cue. Ground rings return when their actual projection is visible.
Distance is not remaining route length or a clearance/reachability claim.

Root qualified the cue on AMD-DESKTOP/PID17212 with genuine reverse progress:
the existing controller confirmed arrival at recorded point 7 with zero pulses,
then explicitly stopped before point 6. A 237.05-second camera-only Qt pilot
presented 1,113 frames: 410 normal, 511 edge-arrow and 192 behind-text states.
Root observed the live downward chevron, behind text and returned NEXT 6 ring;
retained owned images/packets and desktop snapshots preserve the results.
Camera zoom/pitch changed; player position raw bits and body bearing did not.
The owned stop file ended the feed with `stop-requested`. Sixty-one focused
feed/presenter/progress tests passed, including offset viewport, finite overflow,
duplicate NEXT withholding, marker-pixel priority and cue clearing.
Evidence: `artifacts/offscreen-genuine-prefix-17212.json`,
`artifacts/offscreen-cue-live-pilot-17212/`,
`artifacts/offscreen-cue-behind-composite-17212/last.png`,
`artifacts/offscreen-cue-restored-composite-17212/last.png`,
`artifacts/offscreen-camera-restored-17212.json`.
After the camera test, explicit Resume completed the six remaining reverse legs
in 60.993 seconds, endpoint error 0.08283 units. All 36 bounded native action
receipts completed/released, maximum requested hold 150 ms, total requested hold
4,691 ms. Two independent final samples had identical position/body-facing bits;
inspection found no held inputs and the basis was unchanged. The genuine saved
cursor is now **7/7 reverse**, rather than a restored old checkpoint. Receipts:
`artifacts/waypoint-run-e97e66b52055420c8051d46429513977.json`,
`artifacts/offscreen-resume-17212-settled.json`.

Use the exact local host/process and a stationary camera. Capture through the
existing guarded observation path, saving its returned JSON in UTF-8:

```powershell
python scripts/observe_target.py --target physical-amd-desktop --expected-host AMD-DESKTOP --physical-pid PID --physical-capture-backend wgc --native-facing | Set-Content -Encoding utf8 artifacts/projection-observation.json
python scripts/plot_physical_waypoints.py --observation artifacts/projection-observation.json --route artifacts/waypoint-ready-route-69312.json --output artifacts/projection-preview
```

Replace PID with the freshly admitted process. The output directory must be new.
The renderer accepts only a stable native/frame bracket, verified image/geometry,
full native camera projection and complete recorded XYZ/height provenance matching
the snapshot's host, build and player. A historical recording process epoch is
allowed without rewriting its provenance. Missing heights are refused rather than
silently using a flat player-height plane.

`waypoints.png` adds numbered ground markers, +1.5-world-Y beacon lines and a cyan
player-position reference. `waypoints.json` retains exact input hashes/identities,
client/frame mapping, world/pixel projections, withheld-point reasons and limits.
The original screenshot and route remain untouched. Rendering itself reads only
saved files and sends no game input.

The reusable implementation is `physical_rift._project_world_point` plus
`physical_turn_visual_pair.client_frame_mapping` and
`project_client_point_to_frame`. No assumed FOV or newly invented camera model is
used. Behind-camera/near-zero-W and offscreen points are withheld from drawing.
Labels are clipped to the client so they cannot enter window chrome.

## First current-epoch observation

On November 12, AMD-DESKTOP/RIFT PID69312, a stable native-before/WGC/native-after
bracket projected all seven points from the actual recorded route. The cyan
player reference was at frame `(960.00,599.39)` and visually aligned with Atank's
feet. This is one stationary-view candidate, not a calibrated pixel-error claim.

- Observation: `artifacts/world-screen-observation-e5df35324a8541359d2a02d86bda9eb7.json`.
- Original image: `artifacts/observe-wgc-d3f297169731496d9133361407b27c82/image.png`.
- Annotated image/report: `artifacts/waypoint-screen-first-69312/waypoints.png`
  and `waypoints.json`.
- Focused renderer/projection/frame tests: 31 passed; the final seven renderer
  cases also passed after the worker's final simplification. Root reviewed the
  code and ran the real saved observation through it.

These are local artifacts; the portable measured route remains tracked under
`docs/validation/gui-taught-route-2026-11-12.json`.

## Off-center native unit check

A second read-only capture on PID69312 at 17:08 UTC bracketed WGC with two
bounded unit-manager scans. Both scans and all four optical-camera snapshots
matched, player position bits were unchanged, and the whole bracket took 2.88 s.
The scan examined 414 entries and found 152 position candidates; 18 nearby,
unchanged, in-view unit candidates were plotted. Root visually reviewed the
crosses against several dummy bases and soldier ground positions across the
image. This supports off-center geometric alignment in this view, without a
calibrated pixel-error or unit-type/name claim. Stored positions may be stale;
matching keys/bits alone do not prove visible presence.

Evidence: `artifacts/unit-screen-bracket-97090a9f867c4248bb8844f04b83778b/`
contains `bracket.json`, original `frame/image.png`, `units.png`, and
`projected.json`. No selection, casting, movement or focus change was sent.

The reusable offline renderer accepts a saved `{before, frame, after}` bracket,
where the sides are the existing `read_native(..., "unit-positions")` results and
the frame is the existing `capture_gpu` result:

```powershell
python scripts/plot_physical_units.py --bracket artifacts/unit-screen-bracket-97090a9f867c4248bb8844f04b83778b/bracket.json --output artifacts/new-unit-preview
```

It independently verifies native identities, four equal camera snapshots, image
hash, acquisition order and unchanged unit position bits, then writes `units.png`
and `units.json` with source hashes and explicit withheld-unit reasons. Defaults
are 18 markers within 35 horizontal units; `--limit` and `--max-distance` can
reduce or expand the bounded view. Root ran the real retained bracket, reviewed
the 18-marker result under `artifacts/unit-screen-reusable-first-69312/`, and the
12 focused saved-file tests passed. These remain unit candidates, without names,
type classification, current-position freshness, occlusion or obstacle clearance.

Six serialized full camera/target reads took 0.282–0.698 s (median 0.474 s),
recorded in `artifacts/projection-read-latency-bbb7bc2180ed4d47b5a56d7a63e378e1.json`.
This motivated the bounded immediate-emission native stream below.

## Bounded camera stream and explicit focus

The native `sample-current-facing-stream` command accepts exact `--pid` and
`--start-ticks`, `--samples` (1–30), and `--interval-ms` (20–200). It emits each full
candidate immediately as NDJSON after strict process revalidation, then a count
receipt. Each row opens a fresh read-only session under the existing read lease,
disposes that session and releases the lease before output or the inter-row
delay. This lets other readers proceed even if the output pipe stalls. The whole
stream has a two-second acquisition window; an individual synchronous operation
may finish later. A deadline returns
`duration-limit` rather than claiming the requested sample count completed.
Each row retains capture timestamps and `captureElapsedMilliseconds`. Consumers
must check identity, age and current window geometry, and release between bursts.

On the current PID69312, 20 rows arrived about 95 ms apart, each 38–50 ms old at
emission. The Python feed then consumed a real 18-row duration-limited burst,
validated every projection and ended with a 0.160-second-old final frame. No keys
were sent. Evidence: `artifacts/projection-native-stream-3375b1ff3a514c8aac03a4301b2114ab.json`
and `artifacts/live-projection-provider-361e2912dbb740f0a6ee864bbc82c318.json`.

The existing native control command now has an explicit no-key focus action:

```text
RiftReader2.Live.exe move-key --focus-only --pid PID --expect-start-ticks TICKS --expect-sha256 SHA256 --expect-hwnd HWND --json
```

It requires every expected identity field, the existing exclusive control lock,
no held desktop inputs, and unchanged target geometry after activation. It cannot
be combined with movement, release or measurement flags. Root exercised it on
AMD-DESKTOP after checking desktop inactivity: RIFT became foreground, its client
remained at `(-1920,29,1920,1009)`, no inputs were held and `inputSent:false`.
Evidence: `artifacts/overlay-focus-only-first-69312.json`. Focus is an explicit
action; the projection feed itself never requests foreground. The stream and
existing/new focus-command tests passed 96 focused native cases; four stream
cases also passed after adding per-row elapsed metadata. After changing lease
ownership to individual rows, the current native stream/focus suites passed 98
cases. Six real competing single reads all completed in 0.325–0.683 seconds while
the overlay ran. One over-age overlay row was withheld, and the owned stop-file
request ended the run cleanly. Evidence:
`artifacts/overlay-reader-interleave-1bb809eea62e46e2bbd816a2f8c3325e/`.

## Remaining qualification

The offline renderer above annotates a retained frame. A separate live desktop
overlay is now available:

```powershell
.\.local\overlay-venv\Scripts\python.exe scripts/live_physical_waypoints.py --presenter qt --expected-host AMD-DESKTOP --physical-pid PID --route docs/validation/gui-taught-route-2026-11-12.json --reader stream --duration 60 --max-age 0.35 --output artifacts/new-overlay-summary.json
```

Use a fresh explicit PID and a new summary path. Focus RIFT separately to display
markers; this command never activates it. The run is bounded (default 60 seconds,
maximum 600) and Ctrl+C closes it. `--reader single` retains the slower existing
reader. In either mode, changed foreground/identity/geometry, expired evidence or
unavailable projection hides markers. Only complete recorded routes or independently
measured points with actual heights matching the host/build/player are admitted.

The waypoint window also has **Show markers / Hide markers** beside the recording
controls. Load a recorded route or independently measured points, wait for its RIFT connection, press
Show markers, then return to RIFT. Markers use the route's real saved heights and
hide while another application is foreground. Hide markers, editing/replacing the
route, reconnection and closing the waypoint window stop its one owned child;
it never restarts automatically. Recorded Play Forward/Reverse and Resume can
keep markers running. STOP/F8 latches movement cancellation first, then requests
owned marker shutdown. Go/Face/Walk + Record/passive Record still close markers
first and ask you to retry after that child exits.

The GUI passes its existing checkpoint to the child for display-only progress:
**cyan/thicker + NEXT** marks the next saved waypoint, **green** marks completed
points and **muted gold** marks pending points. Original waypoint numbers are
preserved during reverse playback. The child reuses `RouteProgress.load` to
validate route/hash, direction, cursor and host/build/player identity. Missing,
malformed or mismatched progress falls back to ordinary yellow markers; it does
not guess a next point or change movement admission. A saved cursor describes
historical progress, not proof that playback is active or that terrain is clear.
CLI callers can opt in with `--progress-file ABSOLUTE_CHECKPOINT_PATH`; the file
may be absent until playback starts. This option never creates or edits it.

On PID60384, root saw and desktop-captured NEXT 2 in cyan, completed point 1 in
green and the remaining points in gold during real forward playback. The route
finished 7/7 at 0.04443-unit error with 35 released pulses/4,657 ms requested hold,
each requested pulse at most 150 ms. Root also observed all-green completion.
The feed presented 576 frames over 143.1 seconds, with 93 foreground/staleness
withholdings; Hide stopped it. Final poses showed zero XYZ/yaw drift and inspection
found no held inputs. Forty-seven focused decoder/feed/marker/presenter tests
passed. Evidence: `artifacts/qt-progress-during-playback-60384/last.png`,
`artifacts/waypoint-run-8f47f15c57a84b0b9169caae75b03152.json`,
`artifacts/waypoint-markers-summary-db8b4511efa74a68aafec656d79a6817.json` and
`artifacts/qt-progress-playback-60384-settled.json`.

On PID60384, root replayed the complete route alongside Qt acquisition: endpoint
error 0.04649, 35 released pulses/4,593 ms requested hold, 303 presentations during
the combined 91-second feed. An actual GUI Play Reverse then displayed beacons
during turning; F8 stopped the action and closed the marker child. Two poses
showed zero XYZ/yaw drift, and saved progress was 1/7. Root used Show + Resume:
only Recorded 6 through 1 ran, completing at 0.05944 units with 27 released pulses,
3,626 ms requested hold, maximum requested pulse 150 ms. That feed displayed 258
frames over 71.5 s, with foreground/staleness withholding; smooth rendering is
not claimed. Hide stopped it. Final poses again had zero drift and desktop
inspection found no held inputs. Forty-three focused GUI/lifecycle/connection
checks passed. Receipts:
`artifacts/waypoint-run-a79b6be79c6541daa143cc9e025a4fb2.json`,
`artifacts/waypoint-run-b2907d4ce7ec4326a2a23237619dbc71.json`,
`artifacts/waypoint-markers-summary-321484257f5e43be9ffaef62975f22e8.json`, and
`artifacts/qt-gui-resume-60384-validation.json`.

Root exercised the real buttons on AMD-DESKTOP/app PID53272. The child was pinned
to PID69312/start/build/HWND, displayed 101 frames in the current camera view, and
the Hide button stopped it with `stop-requested`; the process was observed absent
and the button returned to Show markers. Expected foreground withholding occurred
while the waypoint window was active. The seven-point completed checkpoint and
route source stayed loaded. Receipt:
`artifacts/waypoint-markers-summary-279a56d7de3245aa85d999602d4a180f.json`.
The marker lifecycle tests plus affected recording/playback/edit/reconnect window
tests passed 50 cases, using fake processes/observations and withdrawn windows.

An owning application can also pass all three `--expect-start-ticks`,
`--expect-sha256` and `--expect-hwnd` values to bind startup to its admitted epoch.
`--stop-file ABSOLUTE_NEW_PATH` lets that owner stop the child by creating the
unique file. The main thread hides markers immediately, cancels and joins its
reader, then destroys its window. No forced termination or game key is needed.

The preferred Qt window declares input transparency, no focus, frameless/topmost
tool behavior and a translucent background before native creation. QWidget,
QPainter and QTimer own the window/paint/event lifecycle; RR2's small own-window
bridge places it in signed physical pixels. Pillow retains the shared marker
rendering. A 50 ms watchdog checks the target and frame age. Closing hides
immediately, cancels acquisition, joins its owned reader and destroys its owned
widget/resources. No activation veto, focus repair or hook is used. The earlier
Tk prototype was discarded after a real startup check showed its first wrapper
taking foreground; the validated custom native shell is retained as fallback.

The real Qt first-show check preserved foreground and exact physical geometry;
its actual GUI Show/Hide run displayed 685 frames then stopped cleanly. A camera
drag at a marker anchor reached RIFT, changed optical bearing by 8.59424 degrees,
and left XYZ/body bearing unchanged. Detailed receipts and dependency versions
are in the third-party tools note linked above.

On current AMD-DESKTOP/PID69312, a 30-second stream displayed 245 frames with no
reported failures at a 0.35-second age limit. A separate six-second instrumented
run displayed 52 frames, with maximum observed presentation age 0.134 seconds;
RIFT foreground and client geometry were preserved before/after every frame.
Root reviewed the actual composited desktop image with transparent yellow rings,
world-height beacon lines and the cyan player reference. Evidence:
`artifacts/native-overlay-stream-first-69312.json` and
`artifacts/native-overlay-stream-proof-ad0a5c1917784094bd992531cec98472/`.
The presenter/feed focused tests passed 31 cases after native-window replacement.

The per-row-lease version then ran for 86.7 seconds through a real camera-only
drag, displaying 504 frames with zero reported failures. Dragging from the painted
third waypoint ring at frame `(963,753)` to `(1023,753)` reached RIFT and changed
the optical bearing from -29.84676 to -47.03573 degrees (17.18897 degrees). Atank's
XYZ and body bearing were unchanged. Root reviewed the settled markers following
the new view, and a fresh native/WGC/native bracket was stable. This is actual
cross-process click/drag routing through a painted marker, without gameplay keys
or character movement. The owned stop file then ended the feed. Evidence:
`artifacts/overlay-camera-pan-validation-69312.json`,
`artifacts/overlay-camera-pan-desktop-69312.png`,
`artifacts/overlay-camera-pan-observation-69312.json`, and
`artifacts/overlay-camera-guard-69312-1736.json`.

## Window-size and label check

The labels now use nearby nonoverlapping screen-space lanes and short leader
lines. Exact autogenerated `Recorded N` names display as `N`; custom names remain
numbered and preserved. Ground rings, beacon lines and the player reference keep
their original projected anchors. Root reviewed real captures at both sizes;
the 19 focused presenter tests include the captured near-coincident seven-point
arrangement, client-edge names and unchanged ground/beacon reference pixels.

The existing BlackBox display-recovery helper changed the physical RIFT client
to 1600x900 on `\\.\DISPLAY5`. A six-second overlay run displayed 31 frames with
no reported failures; root reviewed the composited desktop image at client rect
`(-1760,107,1600,900)`. In a separate uninterrupted 12-second feed, the same owned
overlay then followed restoration to `(-1920,53,1920,1009)`, displaying 60 frames.
One `target-foreground-or-geometry-changed` withholding at transition was expected;
all displayed frames had RIFT foreground and maximum observed age was 0.348 s.
Evidence: `artifacts/overlay-small-proof-57df41b9052f4c7890c660386389def3/` and
`artifacts/overlay-resize-live-proof-d6ff675a6a4a4561beaf0b02e9151fea/`.

**Observed desktop-tool failure:** an attempted Computer Use title-bar drag to
restore the original vertical origin instead moved the RIFT window off-screen
to outer rect `(-32768,-2)-(-30832,1046)` and reported `window is not a usable app
window`. Do not repeat that placement method for this RIFT session. The existing
`C:\work\BlackBox\Restore-RiftDisplay3.ps1` helper immediately restored it to the
intended display and outer rect `(-1928,22)-(8,1070)`. A fresh WGC/native bracket
confirmed normal rendering, unchanged XYZ and body bearing, without restarting
the game. Evidence: `artifacts/overlay-after-window-drag-recovery-69312.json` and
`artifacts/observe-wgc-d43e47a476d4419985d06099303834ad/image.png`. Current client
origin is `(-1920,53)`; the pre-test origin was `(-1920,29)`. The standard recovery
helper centers the window, so this is the original size/display, not exact origin.

The subsequent full-game exit/relaunch changed PID69312 to PID60384. The waypoint
app automatically reconnected with its original saved route and byte-identical
7/7 checkpoint/basis. Explicit Show/Hide launched a new epoch-pinned Qt child,
presented 194 frames in 57.8 seconds and stopped cleanly. Withholding occurred
while RIFT lacked foreground or samples expired; this is not continuous-rendering
qualification. Fresh native XYZ matched exactly and body bearing differed by
0.00042 degrees. The old overlay was already stopped before exit, so an active
child across the restart was not tested. Evidence:
`artifacts/qt-restart-before-69312.json`, `artifacts/qt-restart-after-60384.json`,
`artifacts/qt-restart-wgc-observation-60384.json`, and
`artifacts/waypoint-markers-summary-c00e8ebf22b648808ba68acd591bfcb9.json`.
Normal launch placed the new window on the other display; the existing BlackBox
helper restored DISPLAY5 without game input before capture tests.

Mixed-DPI changes still need current overlay qualification.

### Scaled first show and active-child restart

A Windows Qt run with process-local `QT_SCALE_FACTOR=1.25` exposed a first-show
race: the native client was already 1920x1009, but Qt still used its default
640x480 logical size for the first frame. The presenter now keeps its image blank
during placement and refuses a frame until logical dimensions multiplied by
device pixel ratio agree with the physical client within one pixel. It hides
before changed geometry and never divides signed desktop origins by scale or
pumps global events. The fixed six-second real run presented 26 correctly sized
frames, preserved target foreground/geometry and produced a 1920x1009 owned-window
capture with all seven ground anchors within two pixels of expected projection.
Three frames/errors were withheld, including the premature first presentation.
Evidence: `artifacts/qt-scale125-proof-60384/` (before fix) and
`artifacts/qt-scale125-fixed-60384/validation.json`, `presentations.json` and
`owned-window.png`. This qualifies process-local scaling, not a physical
transition between monitors with different Windows DPI settings.

Root then normally exited PID60384 with the GUI-owned marker feed already open
(50 presentations). The feed now stops on a confirmed ended pinned process epoch,
using the existing read-only epoch check; its actual reason was
`target-process-ended` and both child processes disappeared before relaunch.
Unknown state, foreground loss and geometry changes continue to hide/retry.
Normal Glyph launch produced PID38136/start `639301065710306685`; the same GUI
reconnected without automatically starting markers. Atank's XYZ and optical
bearing were unchanged; body bearing differed by -0.000482 degrees. Checkpoint
and basis remained byte-identical. The standard helper restored DISPLAY5 after
normal launch selected the other display. Explicit Show then presented 147
frames over 40.1 seconds with the original completed route in green; Hide stopped
it. Foreground/staleness withholding remains expected. Sixty-three focused
feed/presenter/progress/connection/Qt checks passed, including 11 offscreen Qt
checks also run at 125%. Evidence: `artifacts/qt-active-restart-before-60384.json`,
`artifacts/qt-active-restart-after-38136.json`,
`artifacts/waypoint-markers-summary-93c884f92e0f4531ab5a9a1fd4e52c06.json` and
`artifacts/waypoint-markers-summary-dd70b32c9bc04cd7a92337912ab6216d.json`.

A final display-metadata check found DISPLAY5's physical desktop origin had
changed from `(-1920,6)` to `(-1920,357)`; the cause was not established. The
existing helper centered RIFT at current client rect `(-1920,404,1920,1009)`.
Fresh DXGI output metadata confirms the entire client fits the current monitor
`(-1920,357)-(0,1437)`, with unchanged monitor-local crop `(0,47)-(1920,1056)`.
No Windows display settings were changed by this check. Evidence:
`artifacts/qt-active-restart-final-placement-38136.json` and
`artifacts/qt-active-restart-current-displays-38136.json`.

Projection inside the viewport does not establish visibility: depth, occlusion,
terrain and obstacle clearance are not checked. Projection packets have no
admitted zone/instance binding, so matching host/build/player alone cannot
establish the same world.

## Native zone context candidate

An existing exact-build cache-only `sample-current-zone-seed` read succeeded on
physical AMD-DESKTOP/PID69312 at 17:45 UTC: `rawZoneKey=1216123138`, selector 113,
typed `type-0073-candidate`, `childKey=650763347`, and
`zoneIdCandidate=z487C9102D2EA79BE`. Raw receipt:
`artifacts/physical-zone-context-6df9d3bef69244428a11513f771ecda0.json`.
This is useful context, not a qualified world-instance token, freshness result or
route-admission rule. The current location reader explicitly reports world
instance unavailable; the historical shard lookup also cannot prove co-instance
geometry. Keep source intervals and candidate labels intact.

The reusable physical wrapper now exposes this existing command directly:

```powershell
python scripts/physical_rift.py --expected-host AMD-DESKTOP --physical-pid CURRENT_PID --read-native zone-context --output C:\work\riftreader2\artifacts\new-zone-context.json
```

Use a freshly admitted PID and new output path. The wrapper retains the raw
report and SHA-256, checks exact process/build identity and source times within
the actual invocation, and returns lossless self key, raw uint32 zone key,
supported typed zone-ID candidate or an explicit unavailable reason. A complete
cache acquisition with no resolved zone remains an unavailable value rather than
a fabricated zone or a missing-zone claim. No focus change or game input occurs.

Fresh PID17212 retrieval at 20:07 UTC returned the same raw key, child key and
`z487C9102D2EA79BE` as retained PID69312, with the same build/player but distinct
process starts. Native acquisition took 45.8844 ms. This reproduces retrieval
after the retained genuine restarts for this one case; API correspondence,
changed-zone semantics and passive freshness remain unverified. World-instance
identity remains unavailable, and equal candidates do not authorize cross-world
route reuse. Seventy-one focused wrapper/selection/facing/unit-position tests
passed, including twelve new zone cases. Evidence:
`artifacts/physical-zone-context-wrapper-first-17212.json`,
`artifacts/zone-context-wrapper-first-17212-result.json`,
`artifacts/zone-context-restart-comparison-69312-17212.json`.

Save view also acquires new `zone-before.json` and `zone-after.json` outside its
existing image/native bracket. `view.json` retains both receipts, exact source
hashes, acquisition intervals and route-player correspondence under
`zoneContextCandidate`. Its comparison is `matching-candidates`,
`changed-candidates` or `unavailable`. A resolved zone/player change withholds
projection while keeping diagnostic sources; unavailable optional context leaves
capture usable. Equal candidates do not prove uninterrupted equality, world
instance, map registration or permission to replay a historical route there.
The recorded route is never retagged with the current zone. Actual focus-neutral
GUI proof: `artifacts/waypoint-view-22b4dcfd927a4786b53dae82849bd851/`, with both
source hashes verified, all seven markers reviewed and Rerun verification passed.
