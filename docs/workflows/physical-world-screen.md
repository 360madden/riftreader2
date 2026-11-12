# Physical world-to-screen markers

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
unavailable projection hides markers. Only complete recorded routes with actual
heights matching the host/build/player are admitted.

The waypoint window also has **Show markers / Hide markers** beside the recording
controls. Load a complete recorded route, let its current position refresh, press
Show markers, then return to RIFT. Markers use the route's real saved heights and
hide while another application is foreground. Hide markers, editing/replacing the
route, reconnection and closing the waypoint window stop its one owned child;
it never restarts automatically. Movement and recording currently close markers
first and ask you to retry after that child exits. Simultaneous automatic playback
and marker acquisition has not yet been qualified.

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
Projection inside the viewport does not establish visibility: depth, occlusion,
terrain and obstacle clearance are not checked. World/zone identity is currently
unavailable, so matching host/build/player alone cannot establish the same world.

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
